"""小聆听写：板子当麦克风，说话就上屏。"""

from __future__ import annotations

import ctypes
import logging
import sys
import time
from collections import deque

from PySide6.QtCore import QObject, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from dictation import audio, inject
from dictation.bridge import Bridge
from dictation.config import APP_DIR, CONFIG_PATH, Config
from dictation.engine import (
    STATE_ERROR,
    STATE_LISTENING,
    STATE_LOADING,
    STATE_PAUSED,
    STATE_RECOGNIZING,
    STATE_WAITING,
    DictationEngine,
)
from dictation.net_text import NetTextReceiver

ACCENT = "#4ee1a0"
ACCENT_DIM = "#2f9d75"
WARN = "#f0b35c"
DANGER = "#f2646b"
TEXT_MAIN = "#eaf3ef"
TEXT_SUB = "#8fa3a0"
BG_TOP = "#141d22"
BG_BOTTOM = "#0d1417"

STATE_TEXT = {
    STATE_LOADING: ("加载中", WARN),
    STATE_LISTENING: ("聆听中", ACCENT),
    STATE_RECOGNIZING: ("识别中", WARN),
    STATE_PAUSED: ("待命", "#7f8f8c"),
    STATE_ERROR: ("出错", DANGER),
    STATE_WAITING: ("等待板子", "#7f8f8c"),
}


def normalize_hotkey(spec: str) -> str:
    """把用户写的热键整理成 pynput 认识的形式（space → <space>）。"""
    specials = {
        "space", "tab", "enter", "esc", "escape", "backspace", "delete", "insert",
        "home", "end", "page_up", "page_down", "up", "down", "left", "right",
        "caps_lock", "num_lock", "print_screen", "pause", "menu", "shift", "ctrl",
        "alt", "cmd",
    }
    parts = []
    for raw in (spec or "").split("+"):
        part = raw.strip()
        if not part:
            continue
        low = part.strip("<>").lower()
        if part.startswith("<") and part.endswith(">"):
            parts.append(part)
        elif len(low) == 1:
            parts.append(low)
        elif low in specials or (low.startswith("f") and low[1:].isdigit()):
            parts.append(f"<{low}>")
        else:
            parts.append(part)
    return "+".join(parts)


def pick_font() -> str:
    families = set(QFontDatabase.families())
    for name in ("Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC"):
        if name in families:
            return name
    return QApplication.font().family()


def make_tray_icon(color: str = ACCENT) -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    painter.drawRoundedRect(QRectF(24, 10, 16, 26), 8, 8)
    pen = QPen(QColor(color), 4)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawArc(QRectF(16, 20, 32, 30), 180 * 16, 180 * 16)
    painter.drawLine(QPointF(32, 42), QPointF(32, 52))
    painter.drawLine(QPointF(23, 53), QPointF(41, 53))
    painter.end()
    return QIcon(pix)


class LevelBars(QWidget):
    """音量波形：最近若干帧的平滑曲线 + 渐变填充。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: deque[float] = deque([0.0] * 56, maxlen=56)
        self._smooth = 0.0
        self._color = QColor(ACCENT)
        self.setMinimumHeight(34)

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def push(self, value: float) -> None:
        value = max(0.0, min(1.0, value))
        # 上升快、下落慢，看起来更像真实音量
        self._smooth = value if value > self._smooth else self._smooth * 0.82 + value * 0.18
        self._values.append(self._smooth)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = float(self.width())
        h = float(self.height())
        values = list(self._values)
        if len(values) < 2:
            return
        step = w / (len(values) - 1)

        def point(i: int, v: float) -> QPointF:
            y = h - 2 - max(0.0, min(1.0, v)) * (h - 8)
            return QPointF(i * step, y)

        line = QPainterPath()
        line.moveTo(point(0, values[0]))
        for i in range(1, len(values)):
            prev = point(i - 1, values[i - 1])
            cur = point(i, values[i])
            mid_x = (prev.x() + cur.x()) / 2
            line.cubicTo(QPointF(mid_x, prev.y()), QPointF(mid_x, cur.y()), cur)

        area = QPainterPath(line)
        area.lineTo(QPointF(w, h))
        area.lineTo(QPointF(0, h))
        area.closeSubpath()

        gradient = QLinearGradient(0, 0, 0, h)
        top = QColor(self._color)
        top.setAlpha(110)
        bottom = QColor(self._color)
        bottom.setAlpha(0)
        gradient.setColorAt(0, top)
        gradient.setColorAt(1, bottom)
        painter.fillPath(area, gradient)

        pen = QPen(self._color, 1.6)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawPath(line)
        painter.end()


class Panel(QWidget):
    """无边框悬浮面板。"""

    def __init__(self, app: "DictateApp") -> None:
        super().__init__()
        self.app = app
        self._drag_offset: QPointF | None = None
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(392, 196)

        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.brand = QLabel("小聆听写")
        self.brand.setObjectName("brand")
        self.dot = QLabel("●")
        self.dot.setObjectName("dot")
        self.status = QLabel("加载中")
        self.status.setObjectName("status")
        header.addWidget(self.brand)
        header.addSpacing(4)
        header.addWidget(self.dot)
        header.addWidget(self.status)
        header.addStretch(1)
        self.device_chip = QLabel("未连接")
        self.device_chip.setObjectName("chip")
        header.addWidget(self.device_chip)
        outer.addLayout(header)

        self.level = LevelBars()
        outer.addWidget(self.level)

        self.hint = QLabel("对着板子说话，文字会直接落到光标处")
        self.hint.setObjectName("hint")
        self.hint.setWordWrap(True)
        self.hint.setFixedHeight(38)
        outer.addWidget(self.hint)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.toggle_btn = QPushButton("暂停")
        self.toggle_btn.setObjectName("primary")
        self.toggle_btn.clicked.connect(self.app.toggle_dictation)
        self.settings_btn = QPushButton("设置")
        self.settings_btn.clicked.connect(self.app.open_settings)
        self.hide_btn = QPushButton("收起")
        self.hide_btn.clicked.connect(self.app.hide_to_tray)
        footer.addWidget(self.toggle_btn, 2)
        footer.addWidget(self.settings_btn, 1)
        footer.addWidget(self.hide_btn, 1)
        outer.addLayout(footer)

        self.hotkey_label = QLabel("")
        self.hotkey_label.setObjectName("hotkey")
        outer.addWidget(self.hotkey_label)

    def _apply_style(self) -> None:
        family = pick_font()
        self.setStyleSheet(
            f"""
            QWidget {{ font-family: "{family}"; color: {TEXT_MAIN}; }}
            QLabel#brand {{ font-size: 15px; font-weight: 600; letter-spacing: 1px; }}
            QLabel#dot {{ font-size: 11px; color: {ACCENT}; }}
            QLabel#status {{ font-size: 12px; color: {TEXT_SUB}; }}
            QLabel#chip {{ font-size: 11px; color: {TEXT_SUB}; background: rgba(255,255,255,0.06);
                          border-radius: 8px; padding: 2px 8px; }}
            QLabel#hint {{ font-size: 13px; color: {TEXT_MAIN}; }}
            QLabel#hotkey {{ font-size: 11px; color: {TEXT_SUB}; }}
            QPushButton {{ background: rgba(255,255,255,0.08); border: none; border-radius: 9px;
                           padding: 8px 10px; font-size: 12px; color: {TEXT_MAIN}; }}
            QPushButton:hover {{ background: rgba(255,255,255,0.14); }}
            QPushButton:pressed {{ background: rgba(255,255,255,0.2); }}
            QPushButton#primary {{ background: rgba(78,225,160,0.16); color: {ACCENT}; font-weight: 600; }}
            QPushButton#primary:hover {{ background: rgba(78,225,160,0.26); }}
            """
        )

    def set_state(self, state: str, detail: str = "") -> None:
        text, color = STATE_TEXT.get(state, ("未知", TEXT_SUB))
        self.status.setText(text)
        self.dot.setStyleSheet(f"color: {color}; font-size: 11px;")
        self.level.set_color(ACCENT if state == STATE_LISTENING else color)
        self.toggle_btn.setText("关闭听写" if state in (STATE_LISTENING, STATE_RECOGNIZING) else "开启听写")
        if detail:
            self.setToolTip(detail)

    def set_device(self, label: str) -> None:
        short = label.split("[")[0].strip()
        self.device_chip.setText("板子已连接" if "CherryUSB" in label else (short or "未连接"))

    def set_text(self, text: str) -> None:
        if text:
            self.hint.setText(text)

    def set_hotkey(self, hint: str) -> None:
        self.hotkey_label.setText(hint)

    # 拖动窗口
    def mousePressEvent(self, event) -> None:  # noqa: ANN001, N802
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition() - QPointF(self.frameGeometry().topLeft())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001, N802
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move((event.globalPosition() - self._drag_offset).toPoint())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: ANN001, N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 18, 18)
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor(BG_TOP))
        gradient.setColorAt(1, QColor(BG_BOTTOM))
        painter.fillPath(path, gradient)
        pen = QPen(QColor(255, 255, 255, 22))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(path)
        painter.end()


class SettingsDialog(QDialog):
    def __init__(self, app: "DictateApp", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.cfg = app.cfg
        self.setWindowTitle("小聆听写 · 设置")
        self.setMinimumWidth(460)
        self._build()
        self._load()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(8)

        self.mic_combo = QComboBox()
        self.mic_combo.addItem("自动（按关键字匹配板子）", -1)
        for dev in audio.list_input_devices(""):
            label = f"[{dev['index']}] {dev['name']} ({dev['hostapi']}, {dev['channels']}ch)"
            self.mic_combo.addItem(label, dev["index"])
        form.addRow("麦克风设备", self.mic_combo)

        self.source_combo = QComboBox()
        self.source_combo.addItem("自动：插线用 USB，拔线走无线", "auto")
        self.source_combo.addItem("只用 USB 麦克风（本地离线识别）", "usb")
        self.source_combo.addItem("只用无线（设备识别文本回传）", "net")
        form.addRow("输入来源", self.source_combo)

        self.net_port_spin = QSpinBox()
        self.net_port_spin.setRange(1024, 65535)
        self.net_port_spin.setToolTip("设备把识别文本 UDP 广播到这个端口")
        form.addRow("无线接收端口", self.net_port_spin)

        self.keyword_edit = QLineEdit()
        self.keyword_edit.setPlaceholderText("CherryUSB")
        form.addRow("设备名关键字", self.keyword_edit)

        self.channel_spin = QSpinBox()
        self.channel_spin.setRange(0, 3)
        self.channel_spin.setToolTip("板子有 4 个通道：0=原始麦克风，1=参考，2=降噪后，3=上传云端")
        form.addRow("音频通道", self.channel_spin)

        self.fallback_check = QCheckBox("找不到板子时改用系统默认麦克风（否则直接报错）")
        self.fallback_check.setToolTip("默认关闭：保证听到的声音一定来自板子，不会悄悄用电脑自带麦克风")
        form.addRow("", self.fallback_check)

        self.lang_combo = QComboBox()
        for code, name in (
            ("zh", "中文（含英文）"),
            ("en", "English"),
            ("ja", "日本語"),
            ("ko", "한국어"),
            ("yue", "粤语"),
            ("auto", "自动"),
        ):
            self.lang_combo.addItem(name, code)
        form.addRow("识别语言", self.lang_combo)

        self.itn_check = QCheckBox("数字与标点规范化")
        form.addRow("", self.itn_check)

        self.gain_spin = QDoubleSpinBox()
        self.gain_spin.setRange(0.5, 8.0)
        self.gain_spin.setSingleStep(0.5)
        form.addRow("识别前增益", self.gain_spin)

        self.input_gain_spin = QDoubleSpinBox()
        self.input_gain_spin.setRange(1.0, 30.0)
        self.input_gain_spin.setSingleStep(1.0)
        self.input_gain_spin.setToolTip("采集后先放大，板子空闲送出的麦克风电平偏低，一般 4~10 合适")
        form.addRow("采集放大倍数", self.input_gain_spin)

        self.silence_spin = QSpinBox()
        self.silence_spin.setRange(200, 3000)
        self.silence_spin.setSingleStep(100)
        self.silence_spin.setSuffix(" ms")
        form.addRow("停顿断句", self.silence_spin)

        self.maxlen_spin = QSpinBox()
        self.maxlen_spin.setRange(5, 60)
        self.maxlen_spin.setSuffix(" 秒")
        form.addRow("最长一句", self.maxlen_spin)

        self.inject_combo = QComboBox()
        self.inject_combo.addItem("逐字键入（兼容性最好）", "type")
        self.inject_combo.addItem("剪贴板粘贴（长文本更快）", "paste")
        form.addRow("上屏方式", self.inject_combo)

        self.space_check = QCheckBox("每句结束后补一个空格")
        form.addRow("", self.space_check)

        self.hotkey_edit = QLineEdit()
        self.hotkey_edit.setPlaceholderText("<ctrl>+<alt>+space")
        form.addRow("开始/暂停热键", self.hotkey_edit)

        self.hotkey_show_edit = QLineEdit()
        form.addRow("显示/隐藏热键", self.hotkey_show_edit)

        self.bridge_check = QCheckBox("开启设备联动（设备上的小应用可查询状态/触发开关）")
        form.addRow("", self.bridge_check)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        form.addRow("联动端口", self.port_spin)

        self.autostart_check = QCheckBox("启动后自动开始听写")
        form.addRow("", self.autostart_check)

        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 16)
        form.addRow("识别线程数", self.threads_spin)

        layout.addLayout(form)

        note = QLabel(
            "提示：热键写成 pynput 形式，例如 <ctrl>+<alt>+space、<f9>。"
            "修改音频/识别相关设置后会自动重载模型，大约需要 2 秒。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#7f8f8c;font-size:11px;")
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        defaults = QPushButton("恢复默认")
        buttons.addButton(defaults, QDialogButtonBox.ResetRole)
        defaults.clicked.connect(self._restore_defaults)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load(self) -> None:
        cfg = self.cfg
        index = self.mic_combo.findData(cfg.mic_device_index)
        self.mic_combo.setCurrentIndex(index if index >= 0 else 0)
        self.source_combo.setCurrentIndex(max(0, self.source_combo.findData(cfg.input_source)))
        self.net_port_spin.setValue(cfg.net_port)
        self.keyword_edit.setText(cfg.mic_keyword)
        self.channel_spin.setValue(cfg.mic_channel)
        self.fallback_check.setChecked(cfg.allow_fallback_mic)
        lang_index = self.lang_combo.findData(cfg.language)
        self.lang_combo.setCurrentIndex(max(0, lang_index))
        self.itn_check.setChecked(cfg.use_itn)
        self.gain_spin.setValue(cfg.segment_gain)
        self.input_gain_spin.setValue(cfg.input_gain)
        self.silence_spin.setValue(cfg.min_silence_ms)
        self.maxlen_spin.setValue(cfg.max_speech_s)
        inject_index = self.inject_combo.findData(cfg.inject_mode)
        self.inject_combo.setCurrentIndex(max(0, inject_index))
        self.space_check.setChecked(cfg.append_space)
        self.hotkey_edit.setText(cfg.hotkey_toggle)
        self.hotkey_show_edit.setText(cfg.hotkey_show)
        self.bridge_check.setChecked(cfg.bridge_enabled)
        self.port_spin.setValue(cfg.bridge_port)
        self.autostart_check.setChecked(cfg.autostart_dictation)
        self.threads_spin.setValue(cfg.num_threads)

    def _restore_defaults(self) -> None:
        defaults = Config()
        self.cfg = defaults
        self._load()

    def _save(self) -> None:
        cfg = self.cfg
        cfg.mic_device_index = int(self.mic_combo.currentData())
        cfg.input_source = self.source_combo.currentData()
        cfg.net_port = self.net_port_spin.value()
        cfg.mic_keyword = self.keyword_edit.text().strip()
        cfg.mic_channel = self.channel_spin.value()
        cfg.allow_fallback_mic = self.fallback_check.isChecked()
        cfg.language = self.lang_combo.currentData()
        cfg.use_itn = self.itn_check.isChecked()
        cfg.segment_gain = float(self.gain_spin.value())
        cfg.input_gain = float(self.input_gain_spin.value())
        cfg.min_silence_ms = self.silence_spin.value()
        cfg.max_speech_s = self.maxlen_spin.value()
        cfg.inject_mode = self.inject_combo.currentData()
        cfg.append_space = self.space_check.isChecked()
        cfg.hotkey_toggle = self.hotkey_edit.text().strip() or "<ctrl>+<alt>+space"
        cfg.hotkey_show = self.hotkey_show_edit.text().strip()
        cfg.bridge_enabled = self.bridge_check.isChecked()
        cfg.bridge_port = self.port_spin.value()
        cfg.autostart_dictation = self.autostart_check.isChecked()
        cfg.num_threads = self.threads_spin.value()
        cfg.normalize()
        cfg.save()
        self.accept()
        self.app.on_config_changed()


class BridgeAPI(QObject):
    """把引擎状态暴露给 HTTP 服务（线程安全地读快照）。"""

    def __init__(self, app: "DictateApp") -> None:
        super().__init__()
        self.app = app

    def get_state(self) -> dict:
        return self.app.state_snapshot()

    def toggle(self) -> dict:
        self.app.toggle_dictation()
        return self.app.state_snapshot()

    def set_armed(self, armed: bool) -> dict:
        self.app.set_armed(bool(armed))
        return self.app.state_snapshot()


class DictateApp(QObject):
    state_signal = Signal(str, str)
    level_signal = Signal(float)
    text_signal = Signal(str)
    error_signal = Signal(str)
    device_signal = Signal(str)

    def __init__(self, qt_app: QApplication) -> None:
        super().__init__()
        self.qt_app = qt_app
        self.cfg = Config.load()
        self.engine = DictationEngine(self.cfg)
        self.engine.on_state = self.state_signal.emit
        self.engine.on_level = self.level_signal.emit
        self.engine.on_text = self.text_signal.emit
        self.engine.on_error = self.error_signal.emit
        self.engine.on_device = self.device_signal.emit

        self.last_text = ""
        self.inserted_count = 0
        self._last_error = ""
        self.levels: deque[float] = deque([0.0] * 12, maxlen=12)
        self._bridge: Bridge | None = None
        self._hotkeys = None
        self._net: NetTextReceiver | None = None

        self.panel = Panel(self)
        self.tray = None
        self._build_tray()

        self.state_signal.connect(self.panel.set_state)
        self.level_signal.connect(self._on_level)
        self.text_signal.connect(self._on_text)
        self.device_signal.connect(self.panel.set_device)
        self.error_signal.connect(self._on_error)

        self._position_panel()
        self._start_bridge()
        self._start_net()
        self._register_hotkeys()
        if self._engine_needed():
            self.engine.start()
        self.panel.show()

    def _engine_needed(self) -> bool:
        return self.cfg.input_source in ("auto", "usb")

    def _start_net(self) -> None:
        self._stop_net()
        if self.cfg.input_source == "usb":
            return
        receiver = NetTextReceiver(self.cfg.net_port, self._on_net_text)
        try:
            receiver.start()
        except RuntimeError as exc:
            self._on_error(str(exc))
            return
        self._net = receiver

    def _stop_net(self) -> None:
        if self._net is not None:
            self._net.stop()
            self._net = None

    def _on_net_text(self, text: str) -> None:
        """板子云端识别完的文字，直接从无线通道过来。"""
        if not text:
            return
        if not self.engine.armed:
            self.panel.set_text(text)
            return
        text = self._strip_wake_prefix(text)
        if not text:
            return
        self.engine.suppress_for(120.0)
        if self.cfg.append_space:
            text = text + " "
        try:
            inject.insert_text(text, mode=self.cfg.inject_mode, char_delay_ms=self.cfg.char_delay_ms)
        except Exception as exc:  # noqa: BLE001
            self._on_error(f"上屏失败：{exc}")
        self.last_text = text
        self.inserted_count += len(text)
        self.panel.set_text(text)
        self.panel.set_device("无线（WiFi）")
        if self.engine.armed:
            self.panel.set_state(STATE_LISTENING, "无线听写")

    def _strip_wake_prefix(self, text: str) -> str:
        """云端识别有时会把唤醒词也带上，这里按配置去掉开头。"""
        for prefix in self.cfg.strip_prefixes or []:
            if prefix and text.startswith(prefix):
                return text[len(prefix) :].lstrip("，,。.、！!?？：: 　")
        return text

    # ---- 启动辅助 -------------------------------------------------
    def _build_tray(self) -> None:
        from PySide6.QtWidgets import QSystemTrayIcon

        self.tray = QSystemTrayIcon(make_tray_icon(), self.qt_app)
        menu = QMenu()
        self.act_show = QAction("显示面板", menu)
        self.act_show.triggered.connect(self.show_panel)
        self.act_toggle = QAction("开启听写", menu)
        self.act_toggle.triggered.connect(self.toggle_dictation)
        self.act_settings = QAction("设置…", menu)
        self.act_settings.triggered.connect(self.open_settings)
        self.act_device = QAction("在设备上开启听写（推送小应用）", menu)
        self.act_device.triggered.connect(self.push_device_app)
        self.act_folder = QAction("打开配置目录", menu)
        self.act_folder.triggered.connect(self.open_config_folder)
        self.act_quit = QAction("退出", menu)
        self.act_quit.triggered.connect(self.quit)
        for action in (
            self.act_show,
            self.act_toggle,
            self.act_settings,
            self.act_device,
            None,
            self.act_folder,
            self.act_quit,
        ):
            if action is None:
                menu.addSeparator()
            else:
                menu.addAction(action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.setToolTip("小聆听写")
        self.tray.show()

    def _position_panel(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        self.panel.move(screen.right() - self.panel.width() - 36, screen.bottom() - self.panel.height() - 60)

    def _start_bridge(self) -> None:
        if self._bridge is not None:
            self._bridge.stop()
            self._bridge = None
        if not self.cfg.bridge_enabled:
            return
        api = BridgeAPI(self)
        self._bridge = Bridge(self.cfg.bridge_port, api.get_state, api.toggle, api.set_armed)
        try:
            self._bridge.start()
        except RuntimeError as exc:
            self._on_error(str(exc))

    def _register_hotkeys(self) -> None:
        if self._hotkeys is not None:
            try:
                self._hotkeys.stop()
            except Exception:  # noqa: BLE001
                pass
            self._hotkeys = None
        try:
            from pynput import keyboard
        except Exception as exc:  # noqa: BLE001
            self._on_error(f"热键不可用：{exc}")
            return
        mapping = {}
        toggle_spec = normalize_hotkey(self.cfg.hotkey_toggle)
        show_spec = normalize_hotkey(self.cfg.hotkey_show)
        if toggle_spec:
            mapping[toggle_spec] = lambda: self.toggle_dictation()
        if show_spec:
            mapping[show_spec] = lambda: self.show_panel()
        if not mapping:
            return
        try:
            self._hotkeys = keyboard.GlobalHotKeys(mapping)
            self._hotkeys.daemon = True
            self._hotkeys.start()
        except Exception as exc:  # noqa: BLE001
            self._hotkeys = None
            self._on_error(f"热键注册失败：{exc}")
            return
        self.panel.set_hotkey(
            f"{self._human_hotkey(self.cfg.hotkey_toggle)} 开始/暂停"
            + (f"   ·   {self._human_hotkey(self.cfg.hotkey_show)} 显示/隐藏" if self.cfg.hotkey_show else "")
        )

    @staticmethod
    def _human_hotkey(spec: str) -> str:
        parts = []
        for raw in spec.split("+"):
            part = raw.strip().strip("<>").upper()
            if part in ("CTRL", "CONTROL"):
                parts.append("Ctrl")
            elif part == "ALT":
                parts.append("Alt")
            elif part == "SHIFT":
                parts.append("Shift")
            elif part == "SPACE":
                parts.append("空格")
            else:
                parts.append(part)
        return "+".join(parts)

    # ---- 交互 -----------------------------------------------------
    def toggle_dictation(self) -> None:
        enabled = self.engine.toggle()
        self.act_toggle.setText("关闭听写" if enabled else "开启听写")
        if self.tray is not None:
            self.act_toggle.setText("关闭听写" if enabled else "开启听写")

    def set_armed(self, armed: bool) -> None:
        self.engine.set_armed(armed)
        self.act_toggle.setText("关闭听写" if armed else "开启听写")

    def show_panel(self) -> None:
        self.panel.show()
        self.panel.raise_()

    def hide_to_tray(self) -> None:
        self.panel.hide()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self, None)
        dialog.exec()

    def on_config_changed(self) -> None:
        self.engine.stop()
        self.engine.cfg = self.cfg
        if self._engine_needed():
            self.engine.start()
        self._start_bridge()
        self._start_net()
        self._register_hotkeys()

    def open_config_folder(self) -> None:
        import os

        os.startfile(str(APP_DIR))

    def push_device_app(self) -> None:
        """把设备端听写小应用推到板子上并让它运行；小应用启动时会把电脑端切到听写模式。"""
        import subprocess

        lua = APP_DIR / "device" / "ling-dictate.lua"
        if not lua.exists():
            self._on_error(f"找不到设备端脚本：{lua}")
            return
        try:
            result = subprocess.run(
                ["adb", "push", str(lua), "/miniapp/ling-dictate.lua"],
                capture_output=True,
                timeout=20,
            )
            if result.returncode != 0:
                message = (result.stderr or result.stdout or b"").decode("utf-8", "replace").strip()
                self._on_error(f"推送到板子失败：{message or '请确认 USB 已连接且 adb devices 能看到设备'}")
        except Exception as exc:  # noqa: BLE001
            self._on_error(f"调用 adb 失败：{exc}")

    def trigger_device_session(self) -> None:
        import subprocess

        try:
            subprocess.run(["adb", "shell", "interact", "start"], capture_output=True, timeout=5)
        except Exception as exc:  # noqa: BLE001
            self._on_error(f"调用 adb 失败：{exc}")

    def quit(self) -> None:
        try:
            if self._hotkeys is not None:
                self._hotkeys.stop()
        except Exception:  # noqa: BLE001
            pass
        if self._bridge is not None:
            self._bridge.stop()
        self._stop_net()
        self.engine.stop()
        self.tray.hide()
        self.qt_app.quit()

    # ---- 回调 -----------------------------------------------------
    def _on_text(self, text: str) -> None:
        self.last_text = text
        self.inserted_count += len(text)
        self.panel.set_text(text)

    def _on_level(self, level: float) -> None:
        self.levels.append(level)
        self.panel.level.push(level)

    def _on_error(self, message: str) -> None:
        self.panel.set_state(STATE_ERROR, message)
        self.panel.set_text(message)
        if self.tray is not None and message != self._last_error:
            self.tray.showMessage("小聆听写", message, self.tray.MessageIcon.Warning, 4000)
        self._last_error = message

    def _on_tray_activated(self, reason) -> None:  # noqa: ANN001
        from PySide6.QtWidgets import QSystemTrayIcon

        if reason == QSystemTrayIcon.Trigger:
            if self.panel.isVisible():
                self.panel.hide()
            else:
                self.show_panel()

    def state_snapshot(self) -> dict:
        return {
            "app": "xiao-ling-dictate",
            "state": self.engine.state,
            "armed": self.engine.armed,
            "paused": self.engine.paused,
            "text": self.last_text,
            "device": self.engine.device_label,
            "inserted_chars": self.inserted_count,
            "levels": [round(v, 2) for v in self.levels],
            "source": self.cfg.input_source,
            "net_hits": self._net.hits if self._net else 0,
            "net_last_client": self._net.last_client if self._net else "",
            "bridge_hits": self._bridge.hits if self._bridge else 0,
            "bridge_last_client": self._bridge.last_client if self._bridge else "",
        }


def single_instance_guard() -> bool:
    """用命名互斥量保证只跑一个实例，避免两个进程同时上屏。"""
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW(None, False, "Global\\XiaoLingDictate")
    return kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def setup_logging() -> None:
    log_dir = APP_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        filename=str(log_dir / "app.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )


def main() -> int:
    setup_logging()
    if not single_instance_guard():
        logging.info("已有实例在运行，退出本次启动")
        ctypes.windll.user32.MessageBoxW(0, "小聆听写已经在运行了。", "小聆听写", 0x40)
        return 0
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("小聆听写")
    qt_app.setQuitOnLastWindowClosed(False)
    app = DictateApp(qt_app)

    def excepthook(exc_type, exc, tb) -> None:  # noqa: ANN001
        logging.error("未捕获异常", exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = excepthook

    # 让 Ctrl+C 也能退出
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(500)

    return qt_app.exec()


if __name__ == "__main__":
    sys.exit(main())
