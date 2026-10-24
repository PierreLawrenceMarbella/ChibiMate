"""A transparent desktop character with gentle idle and walking behavior."""

import logging
import math
import random
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QActionGroup,
    QCursor,
    QIcon,
    QCloseEvent,
    QContextMenuEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMenu, QMessageBox, QSystemTrayIcon, QWidget

from app.character import create_placeholder
from app.bubble import SpeechBubble
from app.dialogue import (
    BUBBLE_MILLISECONDS, CLICK_REACTIONS, DIALOGUE, REACTION_SECONDS,
)
from app.behavior import BehaviorController, FREQUENCIES, Priority
from app.sprites import AnimationState, DANCE_SECONDS, SPRITE_PATH, SpriteAnimation, load_frames
from app.preferences import CHARACTER_HEIGHTS, MIN_HEIGHT, MAX_HEIGHT, CharacterPreferences, read_png
from app.actions import ACTIONS, ACTION_LABELS, normalize_action
from app.theme import MENU_STYLE
from app.movement import (
    CURSOR_SAMPLE_SECONDS, EDGE_MARGIN, FOLLOW_GAP, FOLLOW_HYSTERESIS, clamp_position, step_towards,
)


CHARACTER_PATH = Path(__file__).resolve().parent.parent / "assets" / "alya.png"
MAX_CHARACTER_SIZE = QSize(200, 150)
WALK_SPEED = 32.0  # Logical pixels per second.
RUN_SPEED = 70.0
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
        self._action_priority = Priority.IDLE
        self._bubble_priority = Priority.IDLE
        self._manual_movement = False
        self._following = False
        self._follow_target: QPointF | None = None
        self._cursor_sample_remaining = 0.0
        self._velocity = QPointF()
        self._edge_action: str | None = None
        self._edge_priority = Priority.IDLE
        self._edge_side = -1
        self._reaction_remaining = 0.0
        self._reaction_random = random.Random()
        self._dialog_open = False
        self._generator = None
        self._settings_dialog = None
        self._pack_dialog = None
        self._exit_after_pack = False
        self._closing = False
        self._paint_key = None
        self._exit_after_generator = False
        self._quit_from_tray = False
        self._preferences = preferences if preferences is not None else CharacterPreferences()
        enabled, frequency, self._movement_paused = self._preferences.behavior_options
        self._behavior = BehaviorController(enabled, frequency)
        self._edge_behaviors = self._preferences.edge_behaviors
        self._opacity, self._always_on_top, self._follow_cursor = self._preferences.display_options
        self.setWindowOpacity(self._opacity / 100)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self._always_on_top)
        self._default_character_path = character_path
        self._default_sprite_path = sprite_path
        self._character_height = self._preferences.height
        self._custom_file, saved_character = self._preferences.load_character()

        self._character = saved_character if saved_character is not None else self._load_default_character()
        pack_root, pack_fps = self._preferences.pack_for(self._custom_file)
        self._pack_root = pack_root
        self._sprites = SpriteAnimation(
            pack_root or (None if self._custom_file else sprite_path), self._character, self._display_limit(),
            pack_fps if pack_root is not None else None,
            fallback_root=sprite_path if pack_root is not None and not self._custom_file else None,
        )
        self._character_size = self._sprites.size
        self._sprites.playback_speed, self._sprites.walking_fps = self._preferences.animation_options
        # Reserve transparent space so bobbing never crops the head or feet.
        self.setFixedSize(
            self._character_size.width(),
            self._character_size.height() + 2 * BOB_PADDING,
        )

        self._bubble = SpeechBubble(self)
        self._bubble.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self._always_on_top)
        self._menu = QMenu(self)
        self._menu.setStyleSheet(MENU_STYLE)
        change_action = self._menu.addAction("Change Character", self.change_character)
        settings_action = self._menu.addAction("Character Settings", self.open_settings)
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
        restore_action = self._menu.addAction("Restore Default Alya", self.restore_default)
        generator_action = self._menu.addAction("AI Chibi Generator", self.open_generator)
        self._pack_action = self._menu.addAction("Import Animation Pack", self.import_animation_pack)
        self._menu.addSeparator()
        self._pause_action = self._menu.addAction("Pause Movement", self._toggle_movement)
        self._autonomy_action = self._menu.addAction("Disable Autonomous Behavior", self._toggle_autonomy)
        self._follow_action = self._menu.addAction("Follow Cursor", self._toggle_follow)
        self._edge_toggle = self._menu.addAction("Screen-Edge Behaviors")
        self._edge_toggle.setCheckable(True)
        self._edge_toggle.triggered.connect(self.set_edge_behaviors)
        frequency_menu = self._menu.addMenu("Behavior Frequency")
        self._frequency_group = QActionGroup(self)
        self._frequency_group.setExclusive(True)
        self._frequency_actions = {}
        for frequency in FREQUENCIES:
            action = frequency_menu.addAction(frequency)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, frequency=frequency: self.set_behavior_options(frequency=frequency))
            self._frequency_group.addAction(action)
            self._frequency_actions[frequency] = action
        self._reaction_action = self._menu.addAction(
            "Trigger Random Reaction", lambda: self.trigger_random_reaction(explicit=True),
        )
        self._dance_action = self._menu.addAction("Dance", lambda: self.start_dance())
        self._pet_action = self._menu.addAction("Pet / Trigger Happy", lambda: self.trigger_random_reaction(name="happy", explicit=True))
        self._sit_action = self._menu.addAction("Sit", lambda: self.perform_action("sitting"))
        self._sleep_action = self._menu.addAction("Sleep", lambda: self.perform_action("sleeping"))
        self._wave_action = self._menu.addAction("Wave", lambda: self.perform_action("waving"))
        self._peek_action = self._menu.addAction("Peek", lambda: self.approach_edge("peeking"))
        actions_menu = self._menu.addMenu("Actions")
        self._action_controls = {"sitting": self._sit_action, "sleeping": self._sleep_action,
                                 "waving": self._wave_action, "peeking": self._peek_action,
                                 "dance": self._dance_action}
        for name in ACTIONS:
            if name in self._action_controls or name in ("idle", "happy"):
                continue  # Already exposed directly through the menu or Pet/Wake Up.
            action = actions_menu.addAction(ACTION_LABELS[name])
            action.triggered.connect(lambda checked=False, name=name: self.perform_action(name))
            self._action_controls[name] = action
        wake_action = self._menu.addAction("Return to Idle / Wake Up", self.return_to_idle)
        self._menu.addSeparator()
        self._hide_action = self._menu.addAction("Hide (restore from tray)", self.hide_companion)
        exit_action = self._menu.addAction("Exit ChibiMate", self.close)
        # Reuse the same QAction objects and callbacks in compact groups.
        for action in self._menu.actions():
            self._menu.removeAction(action)
        self._menu.addSection("Character actions")
        for action in (self._pet_action, self._sit_action, self._wave_action, self._dance_action,
                       self._sleep_action, wake_action, self._peek_action, self._reaction_action,
                       actions_menu.menuAction()):
            self._menu.addAction(action)
        self._menu.addSection("Movement")
        self._menu.addAction(self._pause_action)
        self._menu.addAction(self._follow_action)
        behavior_menu = self._menu.addMenu("Behavior Options")
        for action in (self._autonomy_action, frequency_menu.menuAction(), self._edge_toggle):
            behavior_menu.addAction(action)
        self._menu.addSection("Customization")
        for action in (change_action, self._pack_action, settings_action):
            self._menu.addAction(action)
        more = self._menu.addMenu("More Customization")
        for action in (self._size_menu.menuAction(), restore_action, generator_action):
            more.addAction(action)
        self._menu.addSection("Application")
        self._menu.addAction(self._hide_action)
        self._menu.addAction(exit_action)
        self._tray = QSystemTrayIcon(QIcon(self._character), self)
        self._tray.setToolTip("ChibiMate — click to show")
        self._tray_menu = QMenu(self)
        self._tray_menu.setStyleSheet(MENU_STYLE)
        self._tray_menu.addAction("Show ChibiMate", self.show_companion)
        self._tray_menu.addAction("Exit ChibiMate", self._exit_from_tray)
        self._tray.setContextMenu(self._tray_menu)
        self._tray.activated.connect(self._tray_activated)
        self._menu.aboutToShow.connect(self._menu_opened)
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
        try:
            _, character = read_png(self._default_character_path)
        except (OSError, ValueError):
            pass
        if character.isNull():
            logging.getLogger(__name__).warning(
                "Default character PNG is missing or unreadable. Using the built-in placeholder.",
            )
            character = create_placeholder()
        return character

    def _display_limit(self, area: QRect | None = None) -> QSize:
        area = self._available_area() if area is None else area
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
        self._walk_y = float(self.y())
        self._velocity = QPointF()
        self._cursor_sample_remaining = 0.0
        if self._bubble.isVisible() and area is not None:
            self._bubble.place_near(self.geometry(), area)
        self.update()

    def _apply_character(self, character: QPixmap, filename: str, prepared_frames: dict | None = None) -> None:
        # Prepare first so a loading failure cannot mix the old player with a
        # newly selected identity. Saved/missing frames fall back inside the loader.
        if character.isNull():
            raise ValueError("The selected character image could not be loaded.")
        pack_root, pack_fps = self._preferences.pack_for(filename)
        if prepared_frames is not None and not filename:
            prepared_frames = load_frames(self._default_sprite_path) | prepared_frames
        sprites = SpriteAnimation(
            pack_root or (None if filename else self._default_sprite_path), character, self._display_limit(),
            pack_fps if pack_root is not None else None,
            fallback_root=self._default_sprite_path if pack_root is not None and not filename else None,
            prepared_frames=prepared_frames,
        )
        self._cancel_reaction()
        self._action_priority = Priority.IDLE
        self._behavior.reset()
        self._drag_offset = self._press_position = None
        self._dragging = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._character = character
        self._custom_file = filename
        self._pack_root = pack_root
        self._sprites = sprites
        self._bob_offset = 0.0
        self._sprites.playback_speed, self._sprites.walking_fps = self._preferences.animation_options
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
        was_dialog_open = self._dialog_open
        self._timer.stop()
        self._dialog_open = True
        try:
            selected, _ = QFileDialog.getOpenFileName(self, "Change Character", "", "PNG images (*.png)")
            if selected:
                previous = self._custom_file
                filename, character = self._preferences.import_character(Path(selected), self._character_height)
                try:
                    self._apply_character(character, filename)
                except (OSError, ValueError):
                    self._preferences.save(previous, self._character_height)
                    (self._preferences.directory / filename).unlink(missing_ok=True)
                    raise
        except (OSError, ValueError) as error:
            self._show_character_error(error)
        finally:
            self._dialog_open = was_dialog_open
            self._clock.restart()
            if was_active and self.isVisible():
                self._timer.start()

    def set_character_size(self, height: int) -> None:
        if not MIN_HEIGHT <= height <= MAX_HEIGHT:
            return
        try:
            self._preferences.save(self._custom_file, height)
            self._character_height = height
            self._resize_character()
        except OSError as error:
            self._show_character_error(error)
        self._update_menu()

    def open_settings(self) -> None:
        from app.settings_dialog import CharacterSettingsDialog
        if self._settings_dialog is not None:
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return
        dialog = CharacterSettingsDialog(self)
        self._settings_dialog = dialog
        was_dialog_open = self._dialog_open
        was_active = self._timer.isActive()
        self._timer.stop()
        self._dialog_open = True
        try:
            dialog.exec()
        finally:
            self._dialog_open = was_dialog_open
            self._settings_dialog = None
            self._clock.restart()
            dialog.deleteLater()
            if was_active and self.isVisible() and not self._closing:
                self._timer.start()

    def set_animation_options(self, speed: float, fps: int | None) -> None:
        try:
            self._preferences.save_animation_options(speed, fps)
        except (OSError, ValueError) as error:
            self._show_character_error(error)
            return
        self._sprites.playback_speed, self._sprites.walking_fps = speed, fps
        self.update()

    def restore_settings(self) -> None:
        try:
            self._preferences.reset_options()
        except OSError as error:
            self._show_character_error(error)
            return
        self._character_height = self._preferences.height
        self._behavior.configure(True, "Normal")
        self._movement_paused = False
        self._edge_behaviors = False
        self._sprites.playback_speed, self._sprites.walking_fps = self._preferences.animation_options
        self.set_display_options(100, True, False)
        self._resize_character()
        self.return_to_idle()
        self._update_menu()

    def set_display_options(self, opacity: int, top: bool, follow: bool) -> bool:
        opacity = max(20, min(100, opacity))
        try:
            self._preferences.save_display_options(opacity, top, follow)
        except OSError as error:
            self._show_character_error(error)
            return False
        changed_follow = follow != self._follow_cursor
        self._opacity, self._follow_cursor = opacity, follow
        if changed_follow:
            # Cancel a target journey, but preserve an explicit pose or sleep.
            if not self._manual_movement and not self._sprites.action_active:
                self._start_idle()
            self._follow_target = None
            self._cursor_sample_remaining = 0.0
        self.setWindowOpacity(opacity / 100)
        if top != self._always_on_top:
            visible = self.isVisible()
            self._always_on_top = top
            self._bubble.dismiss()
            self._bubble.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, top)
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, top)
            if visible:
                self.show()
            self._keep_on_screen()
        self._update_menu()
        return True

    def _toggle_follow(self) -> None:
        self.set_display_options(self._opacity, self._always_on_top, not self._follow_cursor)

    def set_edge_behaviors(self, enabled: bool) -> None:
        try:
            self._preferences.save_edge_behaviors(enabled)
        except OSError as error:
            self._show_character_error(error)
            self._update_menu()
            return
        self._edge_behaviors = enabled
        self._behavior.reset()
        if not enabled and self._edge_action and self._edge_priority == Priority.AUTONOMOUS:
            self._start_idle()
        self._update_menu()

    def resume_autonomous(self) -> None:
        if self.set_display_options(self._opacity, self._always_on_top, False):
            if self.set_behavior_options(enabled=True, paused=False):
                self.return_to_idle()

    def hide_companion(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray.setIcon(QIcon(self._character))
        self._tray.show()
        self._timer.stop()
        self._cancel_reaction()
        self.hide()

    def show_companion(self) -> None:
        self.show()
        self._tray.hide()
        self._keep_on_screen()
        self._clock.restart()
        self._timer.start()

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_companion()

    def _exit_from_tray(self) -> None:
        # A hidden last window does not emit lastWindowClosed on every platform.
        self._quit_from_tray = True
        self.close()

    def restore_default(self) -> None:
        try:
            self._preferences.restore_default(self._character_height)
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

    def import_animation_pack(self) -> None:
        from app.pack_dialog import PackDialog
        was_dialog_open = self._dialog_open
        was_active = self._timer.isActive()
        self._timer.stop()
        filename = self._custom_file
        dialog = PackDialog(self._character, self)
        self._pack_dialog = dialog
        if not filename:
            dialog.setWindowTitle("Import Animation Pack - Alya")
            dialog.fallback_description = (
                "Missing or insufficient actions keep bundled Alya animations when available, otherwise her static PNG/dialogue."
            )
            dialog.status.setText("Import new Alya actions. Actions absent from the pack keep their bundled animations.")
        dialog.fps.setValue(self._preferences.pack_for(filename)[1])
        self._dialog_open = True
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted and dialog.staging and filename == self._custom_file:
                self._preferences.accept_pack(filename, Path(dialog.staging.name), dialog.fps.value())
                prepared = {name: [frame.toImage() for frame in frames]
                            for name, frames in dialog.player.frames.items() if name != "static"}
                self._apply_character(self._character, filename, prepared_frames=prepared)
        except (OSError, ValueError) as error:
            self._show_character_error(error)
        finally:
            dialog.cleanup()
            dialog.deleteLater()
            self._pack_dialog = None
            self._dialog_open = was_dialog_open
            self._clock.restart()
            self._update_menu()
            if was_active and self.isVisible() and not self._closing:
                self._timer.start()
            if self._exit_after_pack:
                QTimer.singleShot(0, self.close)

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
            limit = self._display_limit(area)
            if limit != self._sprites._max_size:
                # A drag or monitor change can put a large character on a smaller
                # work area. Restore its preferred size when space returns, too.
                anchor = QPoint(self.x() + self.width() // 2, self.y() + self.height())
                self._sprites.set_max_size(limit)
                self._character_size = self._sprites.size
                self.setFixedSize(self._character_size.width(), self._character_size.height() + 2 * BOB_PADDING)
                self.move(anchor.x() - self.width() // 2, anchor.y() - self.height())
            position = QPoint(
                max(area.left(), min(self.x(), area.right() + 1 - self.width())),
                max(area.top(), min(self.y(), area.bottom() + 1 - self.height())),
            )
            if position != self.pos():
                self.move(position)
                self._walk_x = float(position.x())
                self._walk_y = float(position.y())
                self._velocity = QPointF()
        return area

    def _start_idle(self) -> None:
        self._walking = False
        self._manual_movement = False
        self._running = False
        self._sprites.set_walking(False)
        self._remaining = random.uniform(*IDLE_SECONDS) * self._behavior.interval_scale
        self._idle_phase = 0.0
        self._walk_x = float(self.x())
        self._walk_y = float(self.y())
        self._velocity = QPointF()
        self._following = False
        self._follow_target = None
        self._edge_action = None
        self._edge_priority = Priority.IDLE

    def _start_walk(self, running: bool = False, manual: bool = False) -> None:
        self._walking = True
        self._manual_movement = manual
        self._running = running
        self._sprites.set_walking(True, running)
        self._direction = random.choice((-1, 1))
        self._remaining = random.uniform(*WALK_SECONDS)
        self._walk_x = float(self.x())
        self._walk_y = float(self.y())
        self._velocity = QPointF()

    def _resume_behavior(self) -> None:
        self._keep_on_screen()
        self._sprites.cancel_overrides()
        self._action_priority = Priority.IDLE
        self._behavior.reset()
        self._start_idle()
        self._clock.restart()

    def _menu_closed(self) -> None:
        self._keep_on_screen()
        self._clock.restart()
        if self._menu_timer_active and self.isVisible() and not self._closing and not self._dialog_open:
            self._timer.start()

    def _menu_opened(self) -> None:
        self._menu_timer_active = self._timer.isActive()
        self._timer.stop()
        self._update_menu()

    def _update_menu(self) -> None:
        for height, action in self._size_actions.items():
            action.setChecked(height == self._character_height)
        self._pause_action.setText("Resume Movement" if self._movement_paused else "Pause Movement")
        self._autonomy_action.setText("Resume Autonomous Behavior" if (
            not self._behavior.enabled or self._follow_cursor or self._movement_paused
            or self.behavior_priority == Priority.MANUAL) else "Disable Autonomous Behavior")
        self._follow_action.setText("Stop Following" if self._follow_cursor else "Follow Cursor")
        self._edge_toggle.setChecked(self._edge_behaviors)
        for name, action in self._frequency_actions.items():
            action.setChecked(name == self._behavior.frequency)
        # Explicit controls can replace lower-priority automatic poses/reactions.
        available = not self._dragging and not self._dialog_open
        self._reaction_action.setEnabled(available)
        self._dance_action.setEnabled(available and self._sprites.can_dance)
        self._dance_action.setText("Dance (static pose)" if len(self._sprites.frames.get("dance", [])) == 1 else "Dance")
        self._pet_action.setEnabled(available)
        self._sit_action.setEnabled(available and "sitting" in self._sprites.frames)
        self._sleep_action.setEnabled(available and "sleeping" in self._sprites.frames)
        for name, action in self._action_controls.items():
            action.setEnabled(available and (name == "idle" or name in self._sprites.frames)
                              and not (self._movement_paused and name in ("walk", "running", "peeking")))
            count = len(self._sprites.frames.get(name, []))
            label = {"dance": "Dance", "sitting": "Sit", "sleeping": "Sleep",
                     "waving": "Wave", "peeking": "Peek"}.get(name, ACTION_LABELS[name])
            action.setText(label + (" (static pose)" if count == 1 else ""))
        self._hide_action.setEnabled(QSystemTrayIcon.isSystemTrayAvailable())

    @property
    def animation_state(self) -> AnimationState:
        # Mouse ownership has priority over all automatic animation states.
        if self._dragging:
            return AnimationState.DRAGGING
        return self._sprites.animation_state

    def start_dance(self, duration: float = DANCE_SECONDS) -> bool:
        return self.perform_action("dance", duration)

    @property
    def behavior_priority(self) -> Priority:
        if self._drag_offset is not None:
            return Priority.DRAGGING
        if self._sprites.action_active or self.animation_state == AnimationState.REACTING:
            return self._action_priority
        if self._edge_action:
            return self._edge_priority
        if self._walking:
            return Priority.MANUAL if self._manual_movement else Priority.AUTONOMOUS
        return Priority.IDLE

    @property
    def autonomous_active(self) -> bool:
        return self._behavior.enabled and not self._movement_paused

    def _prepare_action(self, priority: Priority) -> bool:
        if self._dialog_open or self._drag_offset is not None or self._menu.isVisible():
            return False
        if priority == Priority.AUTONOMOUS:
            return (self.autonomous_active and self.behavior_priority == Priority.IDLE
                    and not self._bubble.isVisible())
        if priority < Priority.MANUAL:
            if self.behavior_priority >= priority:
                return False
            if self._bubble.isVisible() and self._bubble_priority >= priority:
                return False
        if self._following or self._edge_action:
            self._start_idle()
        # User commands replace automatic actions, without ever stacking poses.
        if (self._sprites.action_active or self.animation_state == AnimationState.REACTING
                or self._bubble.isVisible()):
            self._cancel_reaction()
            self._sprites.cancel_overrides()
        self._behavior.reset()
        return True

    def perform_action(self, name: str, duration: float | None = None, automatic: bool = False) -> bool:
        name = normalize_action(name)
        if duration is not None and (not math.isfinite(duration) or duration <= 0):
            return False
        priority = Priority.AUTONOMOUS if automatic else Priority.MANUAL
        if name != "idle" and name not in self._sprites.frames:
            return False
        if name in ("walk", "running") and self._movement_paused:
            return False
        if not self._prepare_action(priority):
            return False
        if name == "idle":
            self.return_to_idle()
            return True
        if name in ("walk", "running"):
            self._start_walk(running=name == "running", manual=not automatic)
        else:
            if name == "sleeping":
                self._start_idle()  # Never resume a stale walk after waking.
            if not self._sprites.begin_action(name, duration, hold=name == "sleeping"):
                return False
            self._action_priority = priority
        if name in DIALOGUE:
            area = self._available_area()
            if area is not None:
                self._bubble.show_message(self._reaction_random.choice(DIALOGUE[name]), self.geometry(), area, BUBBLE_MILLISECONDS)
                self._bubble_priority = priority
        self._clock.restart()
        self.update()
        return True

    def return_to_idle(self) -> None:
        self._cancel_reaction()
        self._resume_behavior()
        self.update()

    def _toggle_movement(self) -> None:
        self.set_behavior_options(paused=not self._movement_paused)

    def _toggle_autonomy(self) -> None:
        if not self._behavior.enabled or self._follow_cursor or self._movement_paused or self.behavior_priority == Priority.MANUAL:
            self.resume_autonomous()
        else:
            self.set_behavior_options(enabled=False)

    def set_behavior_options(self, enabled: bool | None = None, frequency: str | None = None,
                             paused: bool | None = None) -> bool:
        enabled = self._behavior.enabled if enabled is None else enabled
        frequency = self._behavior.frequency if frequency is None else frequency
        paused = self._movement_paused if paused is None else paused
        try:
            self._preferences.save_behavior_options(enabled, frequency, paused)
        except (OSError, ValueError) as error:
            self._show_character_error(error)
            return False
        changed = enabled != self._behavior.enabled or frequency != self._behavior.frequency
        self._movement_paused = paused
        if changed:
            self._behavior.configure(enabled, frequency)
        if paused or (not enabled and not self._manual_movement):
            self._start_idle()
        if not enabled and self._action_priority == Priority.AUTONOMOUS and self.animation_state != AnimationState.SLEEPING:
            self._cancel_reaction()
            self._sprites.cancel_overrides()
            self._action_priority = Priority.IDLE
        self._clock.restart()
        self._update_menu()
        return True

    def trigger_random_reaction(self, automatic: bool = False, name: str | None = None, explicit: bool = False) -> bool:
        if automatic and self._walking:
            return False
        area = self._available_area()
        if area is None:
            return False
        names = tuple(n for n in CLICK_REACTIONS if n in self._sprites.frames) if automatic else CLICK_REACTIONS
        if name is None and not names:
            return False
        name = name or self._reaction_random.choice(names)
        if name not in DIALOGUE or (automatic and name not in self._sprites.frames):
            return False
        priority = Priority.AUTONOMOUS if automatic else (Priority.MANUAL if explicit else Priority.REACTION)
        if not self._prepare_action(priority):
            return False
        message = self._reaction_random.choice(DIALOGUE[name])
        duration = self._reaction_random.uniform(*REACTION_SECONDS)
        if not self._sprites.begin_reaction(name, duration):
            return False
        self._reaction_remaining = duration
        self._action_priority = priority
        self._bubble_priority = priority
        self._bubble.show_message(message, self.geometry(), area, BUBBLE_MILLISECONDS)
        self.update()
        return True

    def _cancel_reaction(self) -> None:
        self._reaction_remaining = 0.0
        self._sprites.end_reaction()
        self._bubble.dismiss()
        self._bubble_priority = Priority.IDLE

    def _tick(self) -> None:
        # Elapsed time keeps speed consistent; cap long stalls to avoid jumps
        # after suspend, a debugger pause, or a busy desktop.
        elapsed = min(self._clock.restart() / 1000.0, 0.05)
        if self._dialog_open or self._drag_offset is not None or self._menu.isVisible() or not self.isVisible():
            return
        self._advance(elapsed)

    def _move_towards(self, target: QPointF, speed: float, elapsed: float, area: QRect) -> bool:
        if QPoint(round(self._walk_x), round(self._walk_y)) != self.pos():
            self._walk_x, self._walk_y = float(self.x()), float(self.y())
            self._velocity = QPointF()
        position = QPointF(self._walk_x, self._walk_y)
        target = clamp_position(target, area, self.size())
        position, self._velocity = step_towards(position, self._velocity, target, speed, elapsed)
        bounded = clamp_position(position, area, self.size())
        if bounded != position:
            self._velocity = QPointF()
        self._walk_x, self._walk_y = bounded.x(), bounded.y()
        if abs(self._velocity.x()) > 1:
            self._direction = 1 if self._velocity.x() > 0 else -1
        self.move(round(self._walk_x), round(self._walk_y))
        return math.hypot(target.x() - self._walk_x, target.y() - self._walk_y) < 0.5

    def _advance_follow(self, elapsed: float, area: QRect) -> None:
        self._cursor_sample_remaining -= elapsed
        if self._cursor_sample_remaining <= 0:
            self._cursor_sample_remaining = CURSOR_SAMPLE_SECONDS
            cursor = QPointF(QCursor.pos())
            half = QPointF(self.width() / 2, self.height() / 2)
            delta = cursor - (QPointF(self.pos()) + half)
            distance = math.hypot(delta.x(), delta.y())
            gap = math.hypot(half.x(), half.y()) + FOLLOW_GAP
            threshold = gap + (0 if self._following else FOLLOW_HYSTERESIS)
            if distance <= threshold:
                self._follow_target = None
            else:
                self._follow_target = clamp_position(cursor - delta * (gap / distance) - half, area, self.size())
        target = self._follow_target
        if target is None or math.hypot(target.x() - self.x(), target.y() - self.y()) < 1:
            if self._walking:
                self._start_idle()
            return
        distance = math.hypot(target.x() - self.x(), target.y() - self.y())
        running = "running" in self._sprites.frames and distance > (160 if self._running else 240)
        if not self._following:
            self._start_walk(running=running)
            self._following = True
        elif running != self._running:
            self._running = running
            self._sprites.set_walking(True, running)
        if abs(target.x() - self.x()) > 1 and self._velocity.isNull():
            self._direction = 1 if target.x() > self.x() else -1
        if self._move_towards(target, RUN_SPEED if running else WALK_SPEED, elapsed, area):
            self._start_idle()

    def approach_edge(self, name: str = "peeking", automatic: bool = False) -> bool:
        name = normalize_action(name)
        area = self._available_area()
        if name not in ("peeking", "sitting") or name not in self._sprites.frames or area is None or self._movement_paused:
            return False
        priority = Priority.AUTONOMOUS if automatic else Priority.MANUAL
        if not self._prepare_action(priority):
            return False
        self._start_idle()
        self._start_walk(manual=not automatic)
        self._edge_action = name
        self._edge_priority = priority
        self._edge_side = -1 if self.geometry().center().x() <= area.center().x() else 1
        self._direction = self._edge_side
        self._clock.restart()
        return True

    def _advance_edge(self, elapsed: float, area: QRect) -> None:
        right = max(area.left(), area.right() + 1 - self.width())
        margin = min(EDGE_MARGIN, (right - area.left()) / 2)
        target_x = area.left() + margin if self._edge_side < 0 else right - margin
        target = QPointF(target_x, self.y())
        if self._move_towards(target, WALK_SPEED, elapsed, area):
            name, priority = self._edge_action, self._edge_priority
            self._start_idle()
            # The approach and pose are one action with the same ownership.
            self.perform_action(name, automatic=priority == Priority.AUTONOMOUS)

    def _animate_motion(self, elapsed: float, area: QRect | None) -> None:
        target_bob = 0.0
        if not self._walking:
            self._idle_phase = (self._idle_phase + elapsed) % BOB_PERIOD
            target_bob = BOB_AMPLITUDE * math.sin(math.tau * self._idle_phase / BOB_PERIOD)
        self._bob_offset += (target_bob - self._bob_offset) * (1 - math.exp(-12 * elapsed))
        self._sprites.advance(elapsed)
        if self._bubble.isVisible() and area is not None:
            self._bubble.place_near(self.geometry(), area)
        self._update_animation()

    def _visual_key(self):
        # Qt rasterizes at subpixel precision. Ignore the vanishing tail of
        # exponential bob easing once it is below 1/64 of a physical pixel.
        dpr = self.devicePixelRatioF()
        return (id(self._sprites), self._sprites.frame_key, self._direction,
                round(self._bob_offset * dpr * 64), dpr)

    def _update_animation(self) -> None:
        key = self._visual_key()
        if key != self._paint_key:
            self._paint_key = key
            self.update()

    def _advance(self, elapsed: float) -> None:
        if self._drag_offset is not None:
            return
        # Rechecking geometry also handles taskbar changes and removed monitors.
        area = self._keep_on_screen()
        if self._sprites.action_active:
            if self._action_priority == Priority.AUTONOMOUS and not self.autonomous_active:
                return
            self._sprites.advance(elapsed)
            if not self._sprites.action_active:
                self._action_priority = Priority.IDLE
            self._bob_offset *= math.exp(-12 * elapsed)
            if self._bubble.isVisible() and area is not None:
                self._bubble.place_near(self.geometry(), area)
            self._update_animation()
            return
        if self.animation_state == AnimationState.REACTING or self._reaction_remaining > 0:
            if self._action_priority == Priority.AUTONOMOUS and not self.autonomous_active:
                return
            if self._bubble.isVisible() and area is not None:
                self._bubble.place_near(self.geometry(), area)
            self._sprites.advance(elapsed)
            self._reaction_remaining = max(0.0, self._reaction_remaining - elapsed)
            if self._reaction_remaining == 0:
                self._sprites.end_reaction()
            if self.animation_state != AnimationState.REACTING:
                self._action_priority = Priority.IDLE
            self._update_animation()
            return
        if self._edge_action:
            if not self._movement_paused and area is not None:
                self._advance_edge(elapsed, area)
                self._animate_motion(elapsed, area)
            return
        if self._follow_cursor and not self._manual_movement:
            if not self._movement_paused and area is not None:
                self._advance_follow(elapsed, area)
            self._animate_motion(elapsed, area)
            return
        if self.autonomous_active and not self._manual_movement:
            self._behavior.advance(elapsed, idle=not self._walking, edges=self._edge_behaviors)
            if not self._walking and not self._bubble.isVisible():
                name = self._behavior.choose_action(self._sprites.frames)
                if name == "idle":
                    self._remaining = max(self._remaining, random.uniform(*IDLE_SECONDS) * self._behavior.interval_scale)
                elif name in ("sitting", "sleeping", "waving"):
                    if self.perform_action(name, automatic=True):
                        return
                elif name not in (None, "idle"):
                    if self.trigger_random_reaction(automatic=True, name=name):
                        return
                if self._edge_behaviors:
                    edge = self._behavior.choose_edge_action(self._sprites.frames)
                    if edge and self.approach_edge(edge, automatic=True):
                        return
        if not self._movement_paused and (self.autonomous_active or self._manual_movement):
            self._remaining -= elapsed
        if (self._remaining <= 0 and not self._movement_paused
                and (self._manual_movement or (self.autonomous_active and not self._follow_cursor))):
            if self._walking:
                self._start_idle()
            else:
                self._start_walk(running=self._behavior.choose_motion(self._sprites.frames) == "running")

        if self._walking and not self._movement_paused and area is not None:
            left = area.left()
            right = max(left, area.right() + 1 - self.width())
            direction = self._direction
            target = QPointF(right if direction > 0 else left, self.y())
            speed = (RUN_SPEED if self._running else WALK_SPEED) * min(1, max(0, self._remaining / 0.35))
            reached = self._move_towards(target, speed, elapsed, area)
            if reached and direction < 0:
                self._direction = 1
            elif reached:
                self._direction = -1
        self._animate_motion(elapsed, area)

    def show_expression(self, name: str, duration: float = 1.2) -> bool:
        if name not in self._sprites.frames or not self._prepare_action(Priority.REACTION):
            return False
        shown = self._sprites.show_expression(name, duration)
        if shown:
            self._action_priority = Priority.REACTION
            self.update()
        return shown

    def paintEvent(self, event: QPaintEvent) -> None:
        self._paint_key = self._visual_key()
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
            self._behavior.reset()
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
                self._sprites.cancel_overrides()
                self._action_priority = Priority.IDLE
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
            elif self.animation_state == AnimationState.SLEEPING:
                self.return_to_idle()
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
        if self._pack_dialog is not None:
            if self._pack_dialog.worker is not None:
                self._exit_after_pack = True
                event.ignore()
                self._pack_dialog.reject()
                return
            self._pack_dialog.reject()
        if self._generator is not None:
            if self._generator.worker is not None:
                self._exit_after_generator = True
                event.ignore()
                self._generator.reject()
                return
            self._generator.reject()
        self._closing = True
        self._timer.stop()
        self._cancel_reaction()
        self._sprites.end_action()
        self._tray.hide()
        self._bubble.close()
        super().closeEvent(event)
        if self._quit_from_tray:
            QApplication.instance().quit()
