"""录屏用的输入框窗口：白底大字，启动时自己抢前台，收到的文字实时写文件。"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QTextEdit

OUT = Path(__file__).with_name("demo_sink.txt")


class Editor(QTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("演示 · 输入框")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setStyleSheet(
            "QTextEdit { background:#FFFFFF; color:#142D39; border:none; padding:26px 30px; }"
        )
        font = QFont("Microsoft YaHei", 15)
        self.setFont(font)

    def force_foreground(self) -> None:
        hwnd = int(self.winId())
        ctypes.windll.user32.ShowWindow(hwnd, 9)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        self.activateWindow()
        self.setFocus()

    def dump(self) -> None:
        OUT.write_text(self.toPlainText(), "utf-8")


def main() -> None:
    app = QApplication(sys.argv)
    editor = Editor()
    editor.setGeometry(360, 150, 1000, 620)
    editor.show()
    editor.force_foreground()

    QTimer.singleShot(600, editor.force_foreground)

    timer = QTimer()
    timer.timeout.connect(editor.dump)
    timer.start(300)

    app.exec()


if __name__ == "__main__":
    main()
