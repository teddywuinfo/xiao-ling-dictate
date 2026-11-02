"""语音识别：Silero VAD 断句 + SenseVoice 离线识别。"""

from __future__ import annotations

import re
import time

import numpy as np
import sherpa_onnx

SAMPLE_RATE = 16000
_PUNCT_ONLY = re.compile(r"^[\s，。、！？；：…—\-,.!?;:\"'“”‘’（）()《》<>·~～]+$")


def clean_text(text: str) -> str:
    """去掉识别结果里的多余空白与纯标点。"""
    text = (text or "").strip()
    text = re.sub(r"[ \t]{2,}", " ", text)
    if not text or _PUNCT_ONLY.match(text):
        return ""
    return text


_FILLERS = {"嗯", "啊", "呃", "哦", "噢", "咦", "诶", "唉", "哎", "额", "唔"}
_NON_WORD = re.compile(r"[，。！？、,.!?…\s]")


def is_noise(text: str, duration_s: float) -> bool:
    """极短的语气词/单字多半是环境噪声，不应上屏。"""
    core = _NON_WORD.sub("", text or "")
    if not core:
        return True
    if duration_s < 1.5 and core in _FILLERS:
        return True
    if len(core) <= 1 and duration_s < 0.8:
        return True
    return False


def only_wake_words(text: str, wake_words: list[str]) -> bool:
    """整句只是唤醒词（或重复唤几次）时不要上屏。

    板子麦克风会把「小聆小聆」这类唤醒词一起录进来，USB 模式下本地识别会把它
    当成普通句子打出来；这里按配置的唤醒词表整句过滤。
    """
    core = _NON_WORD.sub("", text or "")
    if not core:
        return True
    for word in wake_words or []:
        w = _NON_WORD.sub("", word or "")
        if not w:
            continue
        if core == w or core == w * 2 or core == w * 3:
            return True
    return False


class VadSegmenter:
    """把连续音频切成一句一句的语音片段（带一点前置缓冲，避免吞掉第一个字）。"""

    def __init__(
        self,
        model_path: str,
        threshold: float = 0.5,
        min_silence_ms: int = 500,
        min_speech_ms: int = 250,
        max_speech_s: int = 25,
        pre_roll_ms: int = 400,
    ) -> None:
        cfg = sherpa_onnx.VadModelConfig()
        cfg.silero_vad.model = model_path
        cfg.silero_vad.threshold = float(threshold)
        cfg.silero_vad.min_silence_duration = max(0.1, min_silence_ms / 1000.0)
        cfg.silero_vad.min_speech_duration = max(0.05, min_speech_ms / 1000.0)
        cfg.silero_vad.max_speech_duration = float(max_speech_s)
        cfg.sample_rate = SAMPLE_RATE
        self._vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=60)
        self._window = int(cfg.silero_vad.window_size) or 512
        self._pending = np.zeros(0, dtype=np.float32)
        self._pre_roll = int(SAMPLE_RATE * max(0, pre_roll_ms) / 1000)
        self._history = np.zeros(0, dtype=np.float32)
        self._total = 0  # 已经喂进来的样本总数
        self._history_limit = int(SAMPLE_RATE * (max_speech_s + 8))

    def push(self, samples: np.ndarray) -> list[np.ndarray]:
        if samples.size:
            samples = samples.astype(np.float32, copy=False)
            self._history = np.concatenate([self._history, samples])
            self._total += samples.size
            if self._history.size > self._history_limit:
                self._history = self._history[-self._history_limit :]
            self._pending = np.concatenate([self._pending, samples])
        segments: list[np.ndarray] = []
        while self._pending.size >= self._window:
            chunk = self._pending[: self._window]
            self._pending = self._pending[self._window :]
            self._vad.accept_waveform(chunk)
            while not self._vad.empty():
                segment = self._take(self._vad.front.start, len(self._vad.front.samples))
                self._vad.pop()
                if segment.size:
                    segments.append(segment)
        return segments

    def _take(self, start: int, length: int) -> np.ndarray:
        """按绝对样本序号从历史缓冲里取语音，并向前多取一段前置音频。"""
        begin = max(0, int(start) - self._pre_roll)
        end = int(start) + int(length)
        offset = self._total - self._history.size
        lo = max(0, begin - offset)
        hi = max(0, end - offset)
        if hi <= lo:
            return np.zeros(0, dtype=np.float32)
        return self._history[lo:hi].copy()

    def flush(self) -> list[np.ndarray]:
        """把说话人停顿时还没吐出来的最后一句强制结束。"""
        segments: list[np.ndarray] = []
        if self._pending.size:
            padded = np.zeros(self._window, dtype=np.float32)
            padded[: min(self._window, self._pending.size)] = self._pending[: self._window]
            self._pending = np.zeros(0, dtype=np.float32)
            self._history = np.concatenate([self._history, padded])
            self._total += padded.size
            self._vad.accept_waveform(padded)
        self._vad.flush()
        while not self._vad.empty():
            segment = self._take(self._vad.front.start, len(self._vad.front.samples))
            self._vad.pop()
            if segment.size:
                segments.append(segment)
        return segments

    def reset(self) -> None:
        try:
            self._vad.reset()
        except Exception:  # noqa: BLE001
            pass
        self._pending = np.zeros(0, dtype=np.float32)
        self._history = np.zeros(0, dtype=np.float32)
        self._total = 0


class SenseVoice:
    """SenseVoiceSmall 离线识别（中英日韩粤）。"""

    def __init__(
        self,
        model: str,
        tokens: str,
        num_threads: int = 4,
        language: str = "zh",
        use_itn: bool = True,
    ) -> None:
        self.language = language
        t0 = time.time()
        self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=model,
            tokens=tokens,
            num_threads=int(num_threads),
            use_itn=bool(use_itn),
            language=None if language == "auto" else language,
            debug=False,
        )
        self.load_seconds = time.time() - t0

    def transcribe(self, samples: np.ndarray) -> str:
        if samples.size < int(SAMPLE_RATE * 0.15):
            return ""
        stream = self._recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, samples)
        self._recognizer.decode_stream(stream)
        return clean_text(stream.result.text)

    def transcribe_with_gain(self, samples: np.ndarray, gain: float = 1.0) -> str:
        """识别前先把电平拉到舒服的区间，弱信号和强信号都能稳定识别。"""
        if samples.size:
            samples = np.asarray(samples, dtype=np.float32)
            peak = float(np.max(np.abs(samples)))
            if peak > 1e-4:
                scale = min(4.0, 0.6 / peak)
                if scale > 1.0 or gain != 1.0:
                    samples = np.clip(samples * scale * gain, -1.0, 1.0)
        return self.transcribe(samples)
