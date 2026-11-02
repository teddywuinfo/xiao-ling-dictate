"""听写引擎：采集 → VAD 断句 → 识别 → 上屏。"""

from __future__ import annotations

import threading
import time
import traceback
from typing import Callable

import numpy as np

from . import inject
from .asr import SenseVoice, VadSegmenter, is_noise, only_wake_words
from .audio import MicCapture
from .config import Config

STATE_LOADING = "loading"
STATE_LISTENING = "listening"
STATE_PAUSED = "paused"
STATE_RECOGNIZING = "recognizing"
STATE_ERROR = "error"
STATE_WAITING = "waiting"


class DictationEngine:
    """在后台线程里跑完整链路，通过回调把状态交给界面。"""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.on_state: Callable[[str, str], None] = lambda state, detail: None
        self.on_level: Callable[[float], None] = lambda level: None
        self.on_text: Callable[[str], None] = lambda text: None
        self.on_error: Callable[[str], None] = lambda message: None
        self.on_device: Callable[[str], None] = lambda label: None

        self._thread: threading.Thread | None = None
        self._running = threading.Event()
        # 是否处于「听写模式」：只有设备端/热键主动开启才会上屏
        self._armed = threading.Event()
        self._mic: MicCapture | None = None
        self._state = STATE_LOADING
        self._lock = threading.Lock()
        self._device_ok = True
        self._suppress_until = 0.0

    # ---- 对外接口 -------------------------------------------------
    @property
    def state(self) -> str:
        return self._state

    @property
    def armed(self) -> bool:
        return self._armed.is_set()

    # 兼容旧名字
    @property
    def paused(self) -> bool:
        return not self._armed.is_set()

    @property
    def device_label(self) -> str:
        return self._mic.device_label if self._mic else ""

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running.set()
        if self.cfg.autostart_dictation:
            self._armed.set()
        else:
            self._armed.clear()
        self._set_state(STATE_LOADING, "正在加载识别模型…")
        self._thread = threading.Thread(target=self._run, name="dictation", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running.clear()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=3.0)
        self._thread = None
        if self._mic is not None:
            self._mic.stop()
            self._mic = None

    def set_armed(self, armed: bool) -> None:
        """开启/关闭听写模式。关闭时只采集不进识别，也不会上屏。"""
        if armed:
            self._armed.set()
            if self._state in (STATE_PAUSED, STATE_ERROR, STATE_WAITING):
                self._set_state(STATE_LISTENING, "听写已开启")
        else:
            self._armed.clear()
            if self._state not in (STATE_ERROR, STATE_WAITING):
                self._set_state(STATE_PAUSED, "听写已关闭")

    def set_paused(self, paused: bool) -> None:
        self.set_armed(not paused)

    def toggle(self) -> bool:
        armed = not self._armed.is_set()
        self.set_armed(armed)
        return armed

    def suppress_for(self, seconds: float) -> None:
        """无线文本正在上屏时，先让 USB 音频链路别重复上屏。"""
        self._suppress_until = time.time() + max(0.0, seconds)

    # ---- 内部实现 -------------------------------------------------
    def _set_state(self, state: str, detail: str = "") -> None:
        with self._lock:
            self._state = state
        try:
            self.on_state(state, detail)
        except Exception:  # noqa: BLE001
            pass

    def _run(self) -> None:
        try:
            self._run_inner()
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._set_state(STATE_ERROR, str(exc))
            self.on_error(str(exc))

    def _run_inner(self) -> None:
        cfg = self.cfg
        recognizer = SenseVoice(
            model=cfg.asr_model,
            tokens=cfg.asr_tokens,
            num_threads=cfg.num_threads,
            language=cfg.language,
            use_itn=cfg.use_itn,
        )
        segmenter = VadSegmenter(
            cfg.vad_model,
            threshold=cfg.vad_threshold,
            min_silence_ms=cfg.min_silence_ms,
            min_speech_ms=cfg.min_speech_ms,
            max_speech_s=cfg.max_speech_s,
        )
        mic = MicCapture(
            keyword=cfg.mic_keyword,
            device_index=cfg.mic_device_index,
            channel=cfg.mic_channel,
            gain=cfg.input_gain,
            fallback=cfg.allow_fallback_mic,
        )
        self._mic = mic
        while self._running.is_set():
            try:
                label = mic.start()
                break
            except Exception as exc:  # noqa: BLE001
                if cfg.input_source == "usb":
                    raise
                # 自动/无线模式：板子没插不算错误，等它回来
                self._set_state(STATE_WAITING, "等待板子接入（无线模式可直接说话）…")
                self.on_device("")
                self._device_ok = False
                for _ in range(20):
                    if not self._running.is_set():
                        return
                    time.sleep(0.1)
                _ = exc
        if not self._running.is_set():
            return

        self.on_device(label)
        self._device_ok = True
        self._set_state(
            STATE_LISTENING if self._armed.is_set() else STATE_PAUSED,
            "听写已开启，请开始说话" if self._armed.is_set() else "等待设备开启听写模式",
        )

        last_health = 0.0
        while self._running.is_set():
            now = time.time()
            if now - last_health >= 0.5:
                last_health = now
                self._check_device(mic, segmenter)

            block = mic.read(timeout=0.25)
            if block is None:
                continue

            level = float(np.sqrt(np.mean(np.square(block)))) if block.size else 0.0
            self.on_level(min(1.0, level * 6.0))

            if not self._armed.is_set():
                segmenter.reset()
                continue

            for segment in segmenter.push(block):
                self._handle_segment(recognizer, segment)

    def _check_device(self, mic: MicCapture, segmenter: VadSegmenter) -> None:
        """每 2 秒确认板子还在：拔掉就立刻提示，插回来自动恢复。"""
        present = mic.device_present()
        if not present:
            if self._device_ok:
                self._device_ok = False
                self.on_device("")
                segmenter.reset()
                # 立刻停掉采集，别把板子掉线前残留的尾巴音频识别上屏
                try:
                    mic.stop()
                except Exception:  # noqa: BLE001
                    pass
                if self.cfg.input_source == "usb":
                    self._set_state(STATE_ERROR, "板子未连接（USB 已拔掉？），插好后会自动恢复")
                    self.on_error("板子未连接：请检查 USB 线和设备管理器里的 CherryUSB UAC1 Audio")
                else:
                    self._set_state(STATE_WAITING, "等待板子接入（无线模式可直接说话）…")
            return

        if not self._device_ok:
            self._device_ok = True
            try:
                mic.stop()
                label = mic.start()
                self.on_device(label)
                self._set_state(
                    STATE_LISTENING if self._armed.is_set() else STATE_PAUSED,
                    "板子已重新连接" if self._armed.is_set() else "等待设备开启听写模式",
                )
            except Exception as exc:  # noqa: BLE001
                self._device_ok = False
                self.on_error(f"板子重连失败：{exc}")
            return

        if not mic.alive():
            try:
                mic.stop()
                self.on_device(mic.start())
            except Exception as exc:  # noqa: BLE001
                self._device_ok = False
                self.on_error(f"麦克风重连失败：{exc}")

    def _handle_segment(self, recognizer: SenseVoice, segment: np.ndarray) -> None:
        if time.time() < self._suppress_until:
            # 正在从无线收文本，避免同一次说话被上屏两次
            return
        duration_s = segment.size / 16000.0
        if duration_s < 0.2:
            return
        prev_state = self._state
        self._set_state(STATE_RECOGNIZING, "识别中…")
        try:
            text = recognizer.transcribe_with_gain(segment, gain=self.cfg.segment_gain)
        except Exception as exc:  # noqa: BLE001
            self.on_error(f"识别失败：{exc}")
            text = ""
        if text and (only_wake_words(text, self.cfg.strip_prefixes)
                     or text.strip("，。！？、,.!? ") in (self.cfg.ignore_phrases or [])):
            text = ""
        if text and not is_noise(text, duration_s):
            if self.cfg.append_space:
                text = text + " "
            try:
                inject.insert_text(text, mode=self.cfg.inject_mode, char_delay_ms=self.cfg.char_delay_ms)
            except Exception as exc:  # noqa: BLE001
                self.on_error(f"上屏失败：{exc}")
            self.on_text(text)
        if self._state == STATE_RECOGNIZING:
            self._set_state(
                STATE_LISTENING if self._armed.is_set() else STATE_PAUSED,
                "听写中" if self._armed.is_set() else "听写已关闭",
            )
        else:  # 状态已被别处改动（暂停/退出），保持现状
            _ = prev_state
