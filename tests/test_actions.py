"""Multi-action playback, offline imports, controls, and display preferences."""

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEvent, QPoint, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.actions import ACTION_FOLDERS
from app.pack_dialog import PackDialog
from app.packs import validate_pack
from app.preferences import CharacterPreferences
from app.settings_dialog import CharacterSettingsDialog
from app.sprites import AnimationState, SpriteAnimation
from app.window import CharacterWindow, RUN_SPEED


class ActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pack = self.root / "pack"
        self.png(self.root / "character.png", "purple")
        self.fallback = QPixmap(str(self.root / "character.png"))
        self.prefs = CharacterPreferences(self.root / "preferences")
        self.window = None

    def tearDown(self):
        if self.window:
            self.window.close()
            self.window.deleteLater()
        self.app.processEvents()
        for widget in self.app.topLevelWidgets():
            widget.close()
            widget.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.temp.cleanup()

    def png(self, path, color):
        path.parent.mkdir(parents=True, exist_ok=True)
        image = QImage(60, 100, QImage.Format.Format_ARGB32)
        image.fill(QColor(color))
        self.assertTrue(image.save(str(path), "PNG"))

    def all_actions(self):
        for aliases in ACTION_FOLDERS.values():
            self.png(self.pack / aliases[0] / "pose_01.PNG", "red")

    def make_window(self):
        self.window = CharacterWindow(self.root / "character.png", self.pack, self.prefs)
        self.window.show()
        self.window._timer.stop()
        self.app.processEvents()
        return self.window

    def test_all_actions_accept_single_poses_and_restore_running(self):
        self.all_actions()
        player = SpriteAnimation(self.pack, self.fallback, QSize(200, 150))
        self.assertEqual(set(player.frames), {*ACTION_FOLDERS, "static"})
        player.set_walking(True, running=True)
        self.assertEqual(player.animation_state, AnimationState.RUNNING)
        for name in ACTION_FOLDERS:
            self.assertTrue(player.begin_action(name, 1))
            self.assertFalse(player.begin_action("happy"))
            self.assertFalse(player.begin_reaction("happy", 1))
            player.advance(0.5)
            self.assertEqual(player.frame_key, (name, 0))
            player.advance(0.5)
            self.assertEqual(player.animation_state, AnimationState.RUNNING)
            self.assertEqual(player.frame_key, ("running", 0))

    def test_aliases_numerical_order_and_cached_variable_frame_playback(self):
        for number, color in ((10, "blue"), (2, "green"), (1, "red")):
            self.png(self.pack / "waving" / f"wave_{number}.PNG", color)
        self.png(self.pack / "running" / "run.png", "red")
        player = SpriteAnimation(self.pack, self.fallback, QSize(200, 150), motion_fps=10)
        self.assertTrue(player.begin_action("wave", 2))
        with patch("app.sprites.QImage", side_effect=AssertionError("Disk read during playback")):
            for index in range(6):
                self.assertEqual(player.frame_key, ("waving", index % 3))
                image = player.pixmap(1)
                self.assertEqual(image.cacheKey(), player.pixmap(1).cacheKey())
                player.advance(0.101)
            player.set_max_size(QSize(267, 200))
            self.assertEqual(player.pixmap(1).height(), 200)

    def test_pack_zip_normalizes_all_actions_previews_and_persists(self):
        self.all_actions()
        archive = self.root / "actions.zip"
        with zipfile.ZipFile(archive, "w") as zipped:
            for path in self.pack.rglob("*.PNG"):
                zipped.write(path, "character/" + path.relative_to(self.pack).as_posix())
        with patch("socket.socket.connect", side_effect=AssertionError("Network used")):
            counts = validate_pack(archive, self.root / "stage")
            self.assertEqual(counts, {name: 1 for name in ACTION_FOLDERS})
            filename, character = self.prefs.import_character(self.root / "character.png", 175)
            dialog = PackDialog(character)
            try:
                dialog.load_source(archive)
                self.assertTrue(dialog.apply.isEnabled())
                for name in ACTION_FOLDERS:
                    dialog.select_action(name)
                    dialog.player.advance(0.5)
                    self.assertEqual(dialog.player.frame_key, (name, 0))
                self.prefs.accept_pack(filename, Path(dialog.staging.name), 10)
            finally:
                dialog.cleanup()
                dialog.close()
            fresh = CharacterPreferences(self.prefs.directory)
            saved, fps = fresh.pack_for(filename)
            self.assertEqual(fps, 10)
            self.assertEqual(fresh.height, 175)
            self.assertEqual(set(SpriteAnimation(saved, character, QSize(200, 150)).frames), {*ACTION_FOLDERS, "static"})
        # Aliases may not silently overwrite each other's matching filenames.
        self.png(self.pack / "walk" / "pose_01.png", "blue")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate_pack(self.pack, self.root / "duplicate-stage")

    def test_manual_actions_pause_locomotion_resume_and_drag_interrupts(self):
        self.all_actions()
        window = self.make_window()
        window._start_walk(running=True)
        self.assertTrue(window.perform_action("sit", duration=1))
        before = window.pos()
        window._advance(0.5)
        self.assertEqual(window.animation_state, AnimationState.SITTING)
        self.assertEqual(window.pos(), before)
        self.assertFalse(window.trigger_random_reaction())
        window._advance(0.5)
        self.assertEqual(window.animation_state, AnimationState.RUNNING)
        window._bubble.dismiss()
        self.assertTrue(window.perform_action("sleep"))
        # A release beyond the drag threshold must interrupt any action, even
        # if Qt didn't deliver the intermediate move event.
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=QPoint(20, 30))
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=QPoint(70, 30))
        self.assertEqual(window.animation_state, AnimationState.IDLE)
        self.assertFalse(window._sprites.action_active)

    def test_running_speed_manual_rest_sleep_and_peek(self):
        self.all_actions()
        window = self.make_window()
        area = window._available_area()
        window.move(area.center() - window.rect().center())
        window._start_walk(running=True)
        window._direction = 1
        before = window.x()
        window._advance(0.1)
        self.assertEqual(window.x() - before, round(RUN_SPEED * 0.1))
        window._start_idle()
        self.assertTrue(window.perform_action("sitting"))
        self.assertEqual(window.animation_state, AnimationState.SITTING)
        window.return_to_idle()
        self.assertTrue(window.perform_action("sleeping"))
        self.assertEqual(window.animation_state, AnimationState.SLEEPING)
        window.return_to_idle()
        window.move(area.left(), window.y())
        self.assertTrue(window.perform_action("peeking"))
        self.assertEqual(window.animation_state, AnimationState.PEEKING)
        self.assertTrue(area.contains(window.geometry()))

    def test_missing_frames_and_custom_character_keep_their_identity(self):
        self.all_actions()
        window = self.make_window()
        filename, character = self.prefs.import_character(self.root / "character.png", 150)
        window._apply_character(character, filename)
        before = window._sprites.pixmap(1).toImage()
        for name in ACTION_FOLDERS:
            if name != "idle":
                self.assertFalse(window.perform_action(name))
        self.assertEqual(set(window._sprites.frames), {"static"})
        self.assertEqual(window._sprites.pixmap(1).toImage(), before)
        self.assertTrue(window.trigger_random_reaction(name="angry"))
        self.assertEqual(window._sprites.pixmap(1).toImage(), before)
        self.assertTrue(window._bubble.isVisible())
        window._update_menu()
        self.assertFalse(window._sleep_action.isEnabled())

    def test_settings_dialog_persistence_follow_cursor_and_hide_restore(self):
        self.all_actions()
        window = self.make_window()
        dialog = CharacterSettingsDialog(window)
        dialog.show()
        dialog.size_slider.setValue(175)
        dialog.transparency.setValue(35)
        dialog.on_top.setChecked(False)
        dialog.follow.setChecked(True)
        self.assertTrue(window.isVisible())
        self.assertEqual(window._character_height, 175)
        self.assertFalse(window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        fresh = CharacterPreferences(self.prefs.directory)
        self.assertEqual(fresh.height, 175)
        self.assertEqual(fresh.display_options, (65, False, True))
        self.assertTrue(window._available_area().contains(window.geometry()))
        dialog.close()
        window._start_idle()
        with patch("app.window.QCursor.pos", return_value=window.pos() - QPoint(100, 0)):
            window._advance(0.05)
        self.assertTrue(window._walking)
        self.assertEqual(window._direction, -1)
        window._toggle_movement()
        before = window.pos()
        window._advance(0.1)
        self.assertEqual(window.pos(), before)
        with patch("app.window.QSystemTrayIcon.isSystemTrayAvailable", return_value=True), patch.object(window._tray, "show"):
            window.hide_companion()
        self.assertFalse(window.isVisible())
        self.assertFalse(window._timer.isActive())
        window.show_companion()
        self.assertTrue(window.isVisible())
        self.assertTrue(window._timer.isActive())
        with patch.object(self.app, "quit") as quit_app:
            window._exit_from_tray()
        quit_app.assert_called_once()
        self.assertFalse(window._timer.isActive())
        self.assertFalse(window._bubble._timer.isActive())
        window._quit_from_tray = False


if __name__ == "__main__":
    unittest.main()
