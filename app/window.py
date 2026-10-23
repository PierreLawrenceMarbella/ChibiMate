"""A transparent desktop character with gentle idle and walking behavior."""

import logging
import math
import random
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QPoint, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QCloseEvent,
    QContextMenuEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from app.character import create_placeholder


CHARACTER_PATH = Path(__file__).resolve().parent.parent / "assets" / "alya.png"
MAX_CHARACTER_SIZE = QSize(200, 150)
WALK_SPEED = 32.0  # Logical pixels per second.
IDLE_SECONDS = (3.0, 8.0)
WALK_SECONDS = (2.0, 5.0)
BOB_AMPLITUDE = 1.5  # Three pixels of total vertical travel.
BOB_PERIOD = 2.4  # Seconds per idle bob.
BOB_PADDING = math.ceil(BOB_AMPLITUDE)


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
            logging.getLogger(__name__).warning(
                "Character PNG is missing or unreadable: %s. Using the built-in placeholder.",
                character_path,
            )
            self._character = create_placeholder()
        self._character_size = self._character.size().scaled(
            MAX_CHARACTER_SIZE, Qt.AspectRatioMode.KeepAspectRatio
        )
        self._paint_character = QPixmap()
        self._paint_dpr = 0.0
        # Reserve transparent space so bobbing never crops the head or feet.
        self.setFixedSize(
            self._character_size.width(),
            self._character_size.height() + 2 * BOB_PADDING,
        )

        self._menu = QMenu(self)
        self._menu.addAction("Exit", self.close)
        self._menu.aboutToHide.connect(self._resume_behavior)
        self._position_initially()

        self._direction = 1  # The untouched PNG is the right-facing pose.
        self._bob_offset = 0.0
        self._start_idle()
        self._clock = QElapsedTimer()
        self._clock.start()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

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

    def _available_area(self) -> QRect | None:
        center = self.frameGeometry().center()
        screen = QApplication.screenAt(center)
        if screen is None:
            # A drag can end in a gap or outside all monitors. Choose the nearest
            # available rectangle, including monitors with negative coordinates.
            def distance(candidate) -> int:
                area = candidate.availableGeometry()
                dx = max(area.left() - center.x(), 0, center.x() - area.right())
                dy = max(area.top() - center.y(), 0, center.y() - area.bottom())
                return dx * dx + dy * dy

            screen = min(QApplication.screens(), key=distance, default=None)
        return screen.availableGeometry() if screen is not None else None

    def _keep_on_screen(self) -> QRect | None:
        area = self._available_area()
        if area is not None:
            position = QPoint(
                max(area.left(), min(self.x(), area.right() + 1 - self.width())),
                max(area.top(), min(self.y(), area.bottom() + 1 - self.height())),
            )
            if position != self.pos():
                self.move(position)
                self._walk_x = float(position.x())
        return area

    def _start_idle(self) -> None:
        self._walking = False
        self._remaining = random.uniform(*IDLE_SECONDS)
        self._idle_phase = 0.0
        self._walk_x = float(self.x())

    def _start_walk(self) -> None:
        self._walking = True
        self._direction = random.choice((-1, 1))
        self._remaining = random.uniform(*WALK_SECONDS)
        self._walk_x = float(self.x())

    def _resume_behavior(self) -> None:
        self._keep_on_screen()
        self._start_idle()
        self._clock.restart()

    def _tick(self) -> None:
        # Elapsed time keeps speed consistent; cap long stalls to avoid jumps
        # after suspend, a debugger pause, or a busy desktop.
        elapsed = min(self._clock.restart() / 1000.0, 0.05)
        if self._drag_offset is not None or self._menu.isVisible() or not self.isVisible():
            return
        self._advance(elapsed)

    def _advance(self, elapsed: float) -> None:
        # Rechecking geometry also handles taskbar changes and removed monitors.
        area = self._keep_on_screen()
        self._remaining -= elapsed
        if self._remaining <= 0:
            if self._walking:
                self._start_idle()
            else:
                self._start_walk()

        if self._walking and area is not None:
            left = area.left()
            right = max(left, area.right() + 1 - self.width())
            self._walk_x += self._direction * WALK_SPEED * elapsed
            if self._walk_x <= left:
                self._walk_x = float(left)
                self._direction = 1
            elif self._walk_x >= right:
                self._walk_x = float(right)
                self._direction = -1
            self.move(round(self._walk_x), self.y())

        target_bob = 0.0
        if not self._walking:
            self._idle_phase = (self._idle_phase + elapsed) % BOB_PERIOD
            target_bob = BOB_AMPLITUDE * math.sin(math.tau * self._idle_phase / BOB_PERIOD)
        # Ease to neutral when walking starts instead of snapping vertically.
        self._bob_offset += (target_bob - self._bob_offset) * (1 - math.exp(-12 * elapsed))
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        # Scale once per display pixel ratio, not from the full PNG every frame.
        dpr = self.devicePixelRatioF()
        if self._paint_dpr != dpr:
            self._paint_character = self._character.scaled(
                round(self._character_size.width() * dpr),
                round(self._character_size.height() * dpr),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._paint_dpr = dpr
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._direction < 0:
            painter.translate(self.width(), 0)
            painter.scale(-1, 1)
        target = QRectF(
            0, BOB_PADDING + self._bob_offset,
            self._character_size.width(), self._character_size.height(),
        )
        painter.drawPixmap(target, self._paint_character, QRectF(self._paint_character.rect()))

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
            self._resume_behavior()
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self._drag_offset = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._menu.popup(event.globalPos())
        event.accept()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._timer.stop()
        super().closeEvent(event)
