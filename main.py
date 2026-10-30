"""Launch the ChibiMate desktop companion."""

import sys
from pathlib import Path

from PySide6.QtCore import QLockFile, QStandardPaths
from PySide6.QtWidgets import QApplication, QMessageBox

from app.window import CharacterWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ChibiMate")
    app.setQuitOnLastWindowClosed(True)

    # Keep the same writable location in source and executable mode. A second
    # launch exits; an existing hidden companion remains available in the tray.
    data = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
    try:
        data.mkdir(parents=True, exist_ok=True)
    except OSError:
        QMessageBox.critical(None, "ChibiMate", "Cannot access the application data folder. Check its permissions and try again.")
        return 1
    lock = QLockFile(str(data / "instance.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        if lock.error() == QLockFile.LockError.LockFailedError:
            return 0
        QMessageBox.critical(None, "ChibiMate", "Cannot create the application lock in the data folder.")
        return 1

    try:
        window = CharacterWindow()
        window.show()
        return app.exec()
    finally:
        lock.unlock()


if __name__ == "__main__":
    sys.exit(main())
