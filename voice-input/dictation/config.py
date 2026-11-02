"""配置读写。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_DIR / "config.json"
MODEL_DIR = APP_DIR / "models"


@dataclass
class Config:
    # 音频
    mic_keyword: str = "CherryUSB"      # 设备名关键字，留空表示使用系统默认麦克风
    mic_device_index: int = -1           # >=0 时强制指定 PortAudio 设备序号
    mic_channel: int = 0                 # 使用第几个通道（设备有 4 通道: mic/ref/algo/cloud）
    allow_fallback_mic: bool = False     # 找不到板子时是否退回系统默认麦克风（默认不回退）
    sample_rate: int = 16000

    # 输入来源：auto=有 USB 就用 USB，拔线后自动用无线；usb=只用 USB 麦克风；net=只用无线回传
    input_source: str = "auto"
    net_port: int = 8899                 # 设备把识别文本广播到这个 UDP 端口
    strip_prefixes: list[str] = field(
        default_factory=lambda: ["小聆小聆", "小艺小艺", "小聆", "嗨小聆", "小琳小琳", "小林小林"]
    )                                    # 唤醒词：无线回传时去掉开头，USB 模式下整句只有唤醒词则不上屏
    ignore_phrases: list[str] = field(
        default_factory=lambda: ["退出", "关闭", "关机", "拜拜", "再见"]
    )                                    # 板子开关机/语音助手常用的短句，避免被当成听写内容
    voice_command: bool = True           # 允许用语音指令开关听写（说「打开小聆听写」）
    command_subjects: list[str] = field(
        default_factory=lambda: ["听写", "小聆", "小林", "小玲", "小琳", "语音输入", "听写模式"]
    )                                    # 指令里出现这些词才认为是针对本工具

    # 识别
    language: str = "zh"                 # zh / en / ja / ko / yue / auto
    use_itn: bool = True                 # 数字、标点等文本规范化
    num_threads: int = 4
    vad_threshold: float = 0.5
    min_silence_ms: int = 500            # 停顿多久判定一句话结束
    min_speech_ms: int = 250
    max_speech_s: int = 25
    input_gain: float = 6.0              # 采集后先放大（板子空闲时送出的麦克风电平偏低）
    segment_gain: float = 1.0            # 送给识别前的额外增益（1.0 = 不变）

    # 上屏
    inject_mode: str = "type"            # type=逐字键入 / paste=剪贴板粘贴
    append_space: bool = False           # 每句后补一个空格
    char_delay_ms: int = 0               # 逐字键入的字符间隔

    # 交互
    hotkey_toggle: str = "<ctrl>+<alt>+<space>"
    hotkey_show: str = "<ctrl>+<alt>+l"
    autostart_dictation: bool = False   # 启动后是否自动开启听写（默认关闭，等设备端开启听写模式）

    # 设备联动（HTTP 服务，给设备上的 Lua 小应用用）
    bridge_enabled: bool = True
    bridge_port: int = 8898

    # 其它
    sound_feedback: bool = False
    asr_model: str = field(default_factory=lambda: str(MODEL_DIR / "sensevoice" / "model.int8.onnx"))
    asr_tokens: str = field(default_factory=lambda: str(MODEL_DIR / "sensevoice" / "tokens.txt"))
    vad_model: str = field(default_factory=lambda: str(MODEL_DIR / "silero_vad.onnx"))

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "Config":
        cfg = cls()
        fresh = not path.exists()
        if not fresh:
            try:
                data = json.loads(path.read_text("utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
                fresh = True
            known = {f.name for f in fields(cls)}
            for key, value in data.items():
                if key in known:
                    setattr(cfg, key, value)
        cfg.normalize()
        if fresh:
            try:
                cfg.save(path)
            except OSError:
                pass
        return cfg

    def normalize(self) -> None:
        """修正手工改坏或旧版本遗留的值。"""
        if not os.path.exists(self.asr_model):
            self.asr_model = str(MODEL_DIR / "sensevoice" / "model.int8.onnx")
        if not os.path.exists(self.asr_tokens):
            self.asr_tokens = str(MODEL_DIR / "sensevoice" / "tokens.txt")
        if not os.path.exists(self.vad_model):
            self.vad_model = str(MODEL_DIR / "silero_vad.onnx")
        self.mic_channel = max(0, min(3, int(self.mic_channel)))
        self.min_silence_ms = max(200, min(3000, int(self.min_silence_ms)))
        self.min_speech_ms = max(100, min(2000, int(self.min_speech_ms)))
        self.max_speech_s = max(5, min(60, int(self.max_speech_s)))
        self.num_threads = max(1, min(16, int(self.num_threads)))
        self.input_gain = max(0.5, min(40.0, float(self.input_gain)))
        self.bridge_port = max(1024, min(65535, int(self.bridge_port)))
        if self.inject_mode not in ("type", "paste"):
            self.inject_mode = "type"
        if self.language not in ("zh", "en", "ja", "ko", "yue", "auto"):
            self.language = "zh"
        if self.input_source not in ("auto", "usb", "net"):
            self.input_source = "auto"
        self.net_port = max(1024, min(65535, int(self.net_port)))
        if not isinstance(self.strip_prefixes, list):
            self.strip_prefixes = ["小聆小聆", "小艺小艺", "小聆"]

    def save(self, path: Path = CONFIG_PATH) -> None:
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), "utf-8")
