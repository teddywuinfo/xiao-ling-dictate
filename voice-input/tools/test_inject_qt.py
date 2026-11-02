"""上屏自测（Qt 版本）：用一个自己的编辑窗口验证 SendInput / 剪贴板上屏。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QTextEdit

from dictation import inject

TEXT = "你好，世界！这是小聆听写的上屏测试 123。"


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "type"
    app = QApplication(sys.argv)
    editor = QTextEdit()
    editor.setWindowTitle("上屏测试")
    editor.resize(520, 220)
    editor.show()
    editor.raise_()
    editor.activateWindow()

    result = {"ok": False}

    def run() -> None:
        editor.setFocus()
        inject.insert_text(TEXT, mode=mode)
        QTimer.singleShot(700, check)

    def check() -> None:
        got = editor.toPlainText().strip()
        print("期望:", TEXT)
        print("实际:", got)
        print("结果:", "OK" if got == TEXT else "MISMATCH")
        result["ok"] = got == TEXT
        app.quit()

    QTimer.singleShot(600, run)
    app.exec()
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
