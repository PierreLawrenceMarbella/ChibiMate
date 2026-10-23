"""Launch ChibiMate's Phase 1 desktop companion."""

import sys

from PySide6.QtWidgets import QApplication

from app.window import CharacterWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ChibiMate")
    app.setQuitOnLastWindowClosed(True)

    window = CharacterWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
