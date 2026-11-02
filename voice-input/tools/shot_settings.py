"""把设置窗口渲染成图片，方便检查排版。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from dictation.config import Config


class Dummy:
    def __init__(self) -> None:
        self.cfg = Config.load()

    def on_config_changed(self) -> None:
        pass


def main() -> None:
    from app import SettingsDialog

    qt = QApplication(sys.argv)
    dummy = Dummy()
    dialog = SettingsDialog(dummy, None)
    dialog.show()

    def grab() -> None:
        path = Path(__file__).resolve().parent.parent / "docs" / "settings.png"
        dialog.grab().save(str(path))
        print("saved", path)
        qt.quit()

    QTimer.singleShot(900, grab)
    qt.exec()


if __name__ == "__main__":
    main()
