"""测试用接收窗口：一直保持焦点，把收到的文字实时写到 tools/focus_sink.txt。"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QTextEdit, QVBoxLayout, QWidget

OUT = Path(__file__).with_name("focus_sink.txt")


class Sink(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("上屏接收器")
        self.resize(560, 260)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("这个窗口会一直保持焦点，收到的文字实时写入 focus_sink.txt"))
        self.editor = QTextEdit()
        layout.addWidget(self.editor)
        self.editor.setFocus()

    def dump(self) -> None:
        OUT.write_text(self.editor.toPlainText(), "utf-8")

    def force_foreground(self) -> None:
        hwnd = int(self.winId())
        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        self.activateWindow()
        self.editor.setFocus()


def main() -> None:
    app = QApplication(sys.argv)
    sink = Sink()
    sink.show()
    sink.raise_()
    sink.force_foreground()

    timer = QTimer()
    timer.timeout.connect(sink.dump)
    timer.start(300)

    keep_focus = QTimer()
    keep_focus.timeout.connect(sink.force_foreground)
    keep_focus.start(1500)
    app.exec()


if __name__ == "__main__":
    main()
