"""A transparent desktop character with gentle idle and walking behavior."""

import logging
import math
import random
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QPoint, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QActionGroup,
    QCloseEvent,
    QContextMenuEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QMessageBox, QWidget

from app.character import create_placeholder
from app.bubble import SpeechBubble
from app.dialogue import (
    BUBBLE_MILLISECONDS, CLICK_REACTIONS, DIALOGUE, RANDOM_REACTION_SECONDS, REACTION_SECONDS,
)
from app.sprites import AnimationState, DANCE_SECONDS, SPRITE_PATH, SpriteAnimation
from app.preferences import CHARACTER_HEIGHTS, CharacterPreferences


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
                 sprite_path: Path = SPRITE_PATH,
                 preferences: CharacterPreferences | None = None) -> None:
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
        self._dialog_open = False
        self._generator = None
        self._exit_after_generator = False
        self._preferences = preferences if preferences is not None else CharacterPreferences()
        self._default_character_path = character_path
        self._default_sprite_path = sprite_path
        self._character_height = self._preferences.height
        self._custom_file, saved_character = self._preferences.load_character()

        self._character = saved_character if saved_character is not None else self._load_default_character()
        self._sprites = SpriteAnimation(
            None if self._custom_file else sprite_path, self._character, self._display_limit(),
        )
        self._character_size = self._sprites.size
        # Reserve transparent space so bobbing never crops the head or feet.
        self.setFixedSize(
            self._character_size.width(),
            self._character_size.height() + 2 * BOB_PADDING,
        )

        self._bubble = SpeechBubble(self)
        self._menu = QMenu(self)
        self._menu.addAction("Change Character", self.change_character)
        self._size_menu = self._menu.addMenu("Character Size")
        self._size_group = QActionGroup(self)
        self._size_group.setExclusive(True)
        self._size_actions = {}
        for name, height in CHARACTER_HEIGHTS.items():
            action = self._size_menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(height == self._character_height)
            action.triggered.connect(lambda checked=False, height=height: self.set_character_size(height))
            self._size_group.addAction(action)
            self._size_actions[height] = action
        self._menu.addAction("Restore Default Alya", self.restore_default)
        self._menu.addAction("AI Chibi Generator", self.open_generator)
        self._menu.addSeparator()
        self._pause_action = self._menu.addAction("Pause Movement", self._toggle_movement)
        self._reaction_action = self._menu.addAction(
            "Trigger Random Reaction", lambda: self.trigger_random_reaction(),
        )
        self._dance_action = self._menu.addAction("Dance", lambda: self.start_dance())
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
        self._update_menu()

    def _load_default_character(self) -> QPixmap:
        character = QPixmap()
        if self._default_character_path.is_file():
            character.load(str(self._default_character_path), "PNG")
        if character.isNull():
            logging.getLogger(__name__).warning(
                "Character PNG is missing or unreadable: %s. Using the built-in placeholder.",
                self._default_character_path,
            )
            character = create_placeholder()
        return character

    def _display_limit(self) -> QSize:
        area = self._available_area()
        width = round(self._character_height * MAX_CHARACTER_SIZE.width() / MAX_CHARACTER_SIZE.height())
        height = self._character_height
        if area is not None:
            width = min(width, area.width())
            height = min(height, max(1, area.height() - 2 * BOB_PADDING))
        return QSize(width, height)

    def _resize_character(self) -> None:
        # Keep the feet in place, then clamp the entire window onto the monitor.
        anchor = QPoint(self.x() + self.width() // 2, self.y() + self.height())
        self._sprites.set_max_size(self._display_limit())
        self._character_size = self._sprites.size
        self.setFixedSize(self._character_size.width(), self._character_size.height() + 2 * BOB_PADDING)
        self.move(anchor.x() - self.width() // 2, anchor.y() - self.height())
        area = self._keep_on_screen()
        self._walk_x = float(self.x())
        if self._bubble.isVisible() and area is not None:
            self._bubble.place_near(self.geometry(), area)
        self.update()

    def _apply_character(self, character: QPixmap, filename: str) -> None:
        self._cancel_reaction()
        self._drag_offset = self._press_position = None
        self._dragging = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._character = character
        self._custom_file = filename
        self._sprites = SpriteAnimation(
            None if filename else self._default_sprite_path, character, self._display_limit(),
        )
        self._bob_offset = 0.0
        self._resize_character()
        self._start_idle()
        self._clock.restart()
        self._update_menu()

    def _show_character_error(self, error: Exception) -> None:
        was_active = self._timer.isActive()
        self._timer.stop()
        try:
            QMessageBox.warning(self, "Character Preferences", str(error))
        finally:
            self._clock.restart()
            if was_active and self.isVisible():
                self._timer.start()

    def change_character(self) -> None:
        was_active = self._timer.isActive()
        self._timer.stop()
        self._dialog_open = True
        try:
            selected, _ = QFileDialog.getOpenFileName(self, "Change Character", "", "PNG images (*.png)")
            if selected:
                filename, character = self._preferences.import_character(Path(selected), self._character_height)
                self._apply_character(character, filename)
        except (OSError, ValueError) as error:
            self._show_character_error(error)
        finally:
            self._dialog_open = False
            self._clock.restart()
            if was_active and self.isVisible():
                self._timer.start()

    def set_character_size(self, height: int) -> None:
        if height not in CHARACTER_HEIGHTS.values():
            return
        try:
            self._preferences.save(self._custom_file, height)
            self._character_height = height
            self._resize_character()
        except OSError as error:
            self._show_character_error(error)
        self._update_menu()

    def restore_default(self) -> None:
        try:
            self._preferences.save("", self._character_height)
            self._apply_character(self._load_default_character(), "")
        except OSError as error:
            self._show_character_error(error)

    def open_generator(self) -> None:
        if self._generator is None:
            from app.generator_dialog import GeneratorDialog
            self._generator = GeneratorDialog(self)
            self._generator.use_character.connect(self._accept_generated)
            self._generator.finished.connect(self._generator_closed)
        self._generator.show()
        self._generator.raise_()
        self._generator.activateWindow()

    def _accept_generated(self, data: bytes) -> None:
        try:
            filename, character = self._preferences.accept_generated(data, self._character_height)
            self._apply_character(character, filename)
            self._generator.accept()
        except (OSError, ValueError):
            self._generator.status.setText("Could not save the generated character. Check available disk space and permissions.")

    def _generator_closed(self) -> None:
        if self._generator is None:
            return
        self._generator.deleteLater()
        self._generator = None
        if self._exit_after_generator:
            self.close()

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
        for height, action in self._size_actions.items():
            action.setChecked(height == self._character_height)
        self._pause_action.setText("Resume Movement" if self._movement_paused else "Pause Movement")
        busy = self.animation_state in (AnimationState.REACTING, AnimationState.DANCING, AnimationState.DRAGGING)
        available = not busy and not self._bubble.isVisible() and not self._dialog_open
        self._reaction_action.setEnabled(available)
        self._dance_action.setEnabled(available and self._sprites.can_dance)

    @property
    def animation_state(self) -> AnimationState:
        # Mouse ownership has priority over all automatic animation states.
        if self._dragging:
            return AnimationState.DRAGGING
        return self._sprites.animation_state

    def start_dance(self, duration: float = DANCE_SECONDS) -> bool:
        if (self._dialog_open or self._drag_offset is not None or self._menu.isVisible()
                or self._reaction_remaining > 0 or self._bubble.isVisible()):
            return False
        if not self._sprites.begin_dance(duration):
            return False
        self._clock.restart()
        self.update()
        return True

    def _toggle_movement(self) -> None:
        self._movement_paused = not self._movement_paused
        self._start_idle()
        self._update_menu()

    def trigger_random_reaction(self, automatic: bool = False) -> bool:
        if (self._dialog_open or self._drag_offset is not None or self._menu.isVisible()
                or self.animation_state in (AnimationState.REACTING, AnimationState.DANCING)
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
        duration = self._reaction_random.uniform(*REACTION_SECONDS)
        if not self._sprites.begin_reaction(name, duration):
            return False
        self._reaction_remaining = duration
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
        if self._dialog_open or self._drag_offset is not None or self._menu.isVisible() or not self.isVisible():
            return
        self._advance(elapsed)

    def _advance(self, elapsed: float) -> None:
        if self._drag_offset is not None:
            return
        # Rechecking geometry also handles taskbar changes and removed monitors.
        area = self._keep_on_screen()
        if self.animation_state == AnimationState.DANCING:
            self._sprites.advance(elapsed)
            self._bob_offset *= math.exp(-12 * elapsed)
            self.update()
            return
        if self.animation_state == AnimationState.REACTING or self._reaction_remaining > 0:
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
        if self._dialog_open or self._drag_offset is not None or self._menu.isVisible():
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
                self._sprites.end_dance()
                self._start_idle()
                self.update()
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
        if self._generator is not None:
            if self._generator.worker is not None:
                self._exit_after_generator = True
                event.ignore()
                self._generator.reject()
                return
            self._generator.reject()
        self._timer.stop()
        self._cancel_reaction()
        self._sprites.end_dance()
        self._bubble.close()
        super().closeEvent(event)
