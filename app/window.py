"""A transparent, draggable desktop character."""

from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import (
    QContextMenuEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from app.character import create_placeholder


CHARACTER_PATH = Path(__file__).resolve().parent.parent / "assets" / "character.png"
MAX_CHARACTER_SIZE = QSize(200, 240)


class CharacterWindow(QWidget):
    def __init__(self, character_path: Path = CHARACTER_PATH) -> None:
        super().__init__()
        self.setWindowTitle("ChibiMate")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_offset: QPoint | None = None

        self._character = QPixmap()
        if character_path.is_file():
            self._character.load(str(character_path), "PNG")
        if self._character.isNull():
            self._character = create_placeholder()
        self.setFixedSize(
            self._character.size().scaled(
                MAX_CHARACTER_SIZE, Qt.AspectRatioMode.KeepAspectRatio
            )
        )

        self._menu = QMenu(self)
        self._menu.addAction("Exit", self.close)
        self._position_initially()

    def _position_initially(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        # availableGeometry excludes the Windows taskbar and uses Qt logical pixels.
        area = screen.availableGeometry()
        margin = 24
        self.move(
            max(area.left(), area.right() + 1 - self.width() - margin),
            max(area.top(), area.bottom() + 1 - self.height() - margin),
        )

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(self.rect(), self._character)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self._drag_offset = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._menu.popup(event.globalPos())
        event.accept()
