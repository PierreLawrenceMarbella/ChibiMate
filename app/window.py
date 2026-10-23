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
from app.bubble import SpeechBubble
from app.dialogue import (
    BUBBLE_MILLISECONDS, CLICK_REACTIONS, DIALOGUE, RANDOM_REACTION_SECONDS, REACTION_SECONDS,
)
from app.sprites import SPRITE_PATH, SpriteAnimation


CHARACTER_PATH = Path(__file__).resolve().parent.parent / "assets" / "alya.png"
MAX_CHARACTER_SIZE = QSize(200, 150)
WALK_SPEED = 32.0  # Logical pixels per second.
IDLE_SECONDS = (3.0, 8.0)
WALK_SECONDS = (2.0, 5.0)
BOB_AMPLITUDE = 1.5  # Three pixels of total vertical travel.
BOB_PERIOD = 2.4  # Seconds per idle bob.
BOB_PADDING = math.ceil(BOB_AMPLITUDE)


class CharacterWindow(QWidget):
    def __init__(self, character_path: Path = CHARACTER_PATH,
                 sprite_path: Path = SPRITE_PATH) -> None:
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
        self._press_position: QPoint | None = None
        self._dragging = False
        self._movement_paused = False
        self._reaction_remaining = 0.0
        self._reaction_random = random.Random()
        self._random_reaction_remaining = self._reaction_random.uniform(*RANDOM_REACTION_SECONDS)

        self._character = QPixmap()
        if character_path.is_file():
            self._character.load(str(character_path), "PNG")
        if self._character.isNull():
            logging.getLogger(__name__).warning(
                "Character PNG is missing or unreadable: %s. Using the built-in placeholder.",
                character_path,
            )
            self._character = create_placeholder()
        self._sprites = SpriteAnimation(sprite_path, self._character, MAX_CHARACTER_SIZE)
        self._character_size = self._sprites.size
        # Reserve transparent space so bobbing never crops the head or feet.
        self.setFixedSize(
            self._character_size.width(),
            self._character_size.height() + 2 * BOB_PADDING,
        )

        self._bubble = SpeechBubble(self)
        self._menu = QMenu(self)
        self._pause_action = self._menu.addAction("Pause Movement", self._toggle_movement)
        self._reaction_action = self._menu.addAction(
            "Trigger Random Reaction", lambda: self.trigger_random_reaction(),
        )
        self._menu.addSeparator()
        self._menu.addAction("Exit ChibiMate", self.close)
        self._menu.aboutToShow.connect(self._update_menu)
        self._menu.aboutToHide.connect(self._menu_closed)
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
        self._sprites.set_walking(False)
        self._remaining = random.uniform(*IDLE_SECONDS)
        self._idle_phase = 0.0
        self._walk_x = float(self.x())

    def _start_walk(self) -> None:
        self._walking = True
        self._sprites.set_walking(True)
        self._direction = random.choice((-1, 1))
        self._remaining = random.uniform(*WALK_SECONDS)
        self._walk_x = float(self.x())

    def _resume_behavior(self) -> None:
        self._keep_on_screen()
        self._start_idle()
        self._clock.restart()

    def _menu_closed(self) -> None:
        self._keep_on_screen()
        self._clock.restart()

    def _update_menu(self) -> None:
        self._pause_action.setText("Resume Movement" if self._movement_paused else "Pause Movement")
        self._reaction_action.setEnabled(self._reaction_remaining <= 0 and not self._bubble.isVisible())

    def _toggle_movement(self) -> None:
        self._movement_paused = not self._movement_paused
        self._start_idle()
        self._update_menu()

    def trigger_random_reaction(self, automatic: bool = False) -> bool:
        if (self._drag_offset is not None or self._menu.isVisible()
                or self._reaction_remaining > 0 or self._bubble.isVisible()):
            return False
        if automatic and self._walking:
            return False
        area = self._available_area()
        if area is None:
            return False
        names = tuple(DIALOGUE) if automatic else CLICK_REACTIONS
        name = self._reaction_random.choice(names)
        message = self._reaction_random.choice(DIALOGUE[name])
        self._reaction_remaining = self._reaction_random.uniform(*REACTION_SECONDS)
        self._sprites.begin_reaction(name, self._reaction_remaining)
        self._random_reaction_remaining = self._reaction_random.uniform(*RANDOM_REACTION_SECONDS)
        self._bubble.show_message(message, self.geometry(), area, BUBBLE_MILLISECONDS)
        self.update()
        return True

    def _cancel_reaction(self) -> None:
        self._reaction_remaining = 0.0
        self._sprites.end_reaction()
        self._bubble.dismiss()

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
        if self._reaction_remaining > 0:
            if self._bubble.isVisible() and area is not None:
                self._bubble.place_near(self.geometry(), area)
            self._sprites.advance(elapsed)
            self._reaction_remaining = max(0.0, self._reaction_remaining - elapsed)
            if self._reaction_remaining == 0:
                self._sprites.end_reaction()
            self.update()
            return
        self._random_reaction_remaining -= elapsed
        if not self._movement_paused:
            self._remaining -= elapsed
        if self._remaining <= 0 and not self._movement_paused:
            if self._walking:
                self._start_idle()
            else:
                self._start_walk()

        if self._walking and not self._movement_paused and area is not None:
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
        self._sprites.advance(elapsed)
        if self._random_reaction_remaining <= 0 and not self._walking:
            self.trigger_random_reaction(automatic=True)
        if self._bubble.isVisible() and area is not None:
            self._bubble.place_near(self.geometry(), area)
        self.update()

    def show_expression(self, name: str, duration: float = 1.2) -> bool:
        if self._drag_offset is not None or self._menu.isVisible():
            return False
        shown = self._sprites.show_expression(name, duration)
        if shown:
            self.update()
        return shown

    def paintEvent(self, event: QPaintEvent) -> None:
        frame = self._sprites.pixmap(self.devicePixelRatioF())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._direction < 0:
            # Align the mirror axis to physical pixels on fractional-DPI screens.
            dpr = self.devicePixelRatioF()
            painter.translate(round(self.width() * dpr) / dpr, 0)
            painter.scale(-1, 1)
        target = QRectF(
            0, BOB_PADDING + self._bob_offset,
            self._character_size.width(), self._character_size.height(),
        )
        painter.drawPixmap(target, frame, QRectF(frame.rect()))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_position = event.globalPosition().toPoint()
            self._dragging = False
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            position = event.globalPosition().toPoint()
            if not self._dragging and (position - self._press_position).manhattanLength() >= QApplication.startDragDistance():
                self._dragging = True
                self._cancel_reaction()
            if self._dragging:
                self.move(position - self._drag_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._press_position is not None:
            dragged = self._dragging or (
                event.globalPosition().toPoint() - self._press_position
            ).manhattanLength() >= QApplication.startDragDistance()
            self._drag_offset = None
            self._press_position = None
            self._dragging = False
            if dragged:
                self._cancel_reaction()
                self._resume_behavior()
            else:
                self.trigger_random_reaction()
                self._clock.restart()
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self._drag_offset = None
        self._press_position = None
        self._dragging = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._menu.popup(event.globalPos())
        event.accept()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._timer.stop()
        self._bubble.close()
        super().closeEvent(event)
