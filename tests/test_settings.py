"""Live settings, persisted playback, and native UI regression checks (offline)."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QDialog

from app.actions import ACTIONS
from app.preferences import CharacterPreferences
from app.settings_dialog import CharacterSettingsDialog
from app.sprites import SpriteAnimation
from app.window import CharacterWindow


class SettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.prefs = CharacterPreferences(self.root / "data")
        self.pack = self.root / "pack"
        self.png(self.root / "character.png", "purple")
        for i in range(8):
            self.png(self.pack / "walk" / f"walk_{i + 1}.png", QColor(i * 30, 20, 50))
        self.png(self.pack / "idle" / "idle.png", "red")
        self.window = CharacterWindow(self.root / "character.png", self.pack, self.prefs)
        self.window.show()
        self.window._timer.stop()
        self.dialog = CharacterSettingsDialog(self.window)
        self.dialog.show()
        self.app.processEvents()

    def tearDown(self):
        for widget in self.app.topLevelWidgets():
            widget.close()
            widget.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.temp.cleanup()

    def png(self, path, color, width=60, height=100):
        path.parent.mkdir(parents=True, exist_ok=True)
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(QColor(color))
        self.assertTrue(image.save(str(path), "PNG"))

    def test_live_controls_survive_restart_and_preserve_transparent_window(self):
        d, w = self.dialog, self.window
        self.assertEqual([d.tabs.tabText(i) for i in range(d.tabs.count())],
                         ["General", "Character", "Behaviors", "Animations"])
        d.size_slider.setValue(185)
        d.opacity_slider.setValue(55)
        d.on_top.setChecked(False)
        self.assertTrue(d.isVisible())
        d.follow.setChecked(True)
        d.autonomous.setChecked(False)
        d.frequency.setCurrentText("High")
        d.pause.setChecked(True)
        d.edges.setChecked(True)
        d.playback_speed.setValue(1.5)
        d.walking_fps.setCurrentIndex(d.walking_fps.findData(12))
        fresh = CharacterPreferences(self.prefs.directory)
        restarted = CharacterWindow(self.root / "character.png", self.pack, fresh)
        restarted._timer.stop()
        self.assertEqual(restarted._character_height, 185)
        self.assertEqual(fresh.display_options, (55, False, True))
        self.assertEqual(fresh.behavior_options, (False, "High", True))
        self.assertTrue(restarted._edge_behaviors)
        self.assertEqual((restarted._sprites.playback_speed, restarted._sprites.walking_fps), (1.5, 12))
        self.assertTrue(w.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        self.assertTrue(w.windowFlags() & Qt.WindowType.FramelessWindowHint)
        self.assertFalse(w.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self.assertTrue(w._available_area().contains(w.geometry()))

    def test_reset_preserves_custom_character_and_imported_pack(self):
        filename, character = self.prefs.import_character(self.root / "character.png", 200)
        self.prefs.accept_pack(filename, self.pack, 10)
        self.window._apply_character(character, filename)
        before_pack = self.prefs.pack_for(filename)
        self.dialog.refresh()
        self.dialog.opacity_slider.setValue(40)
        self.dialog.follow.setChecked(True)
        self.dialog.pause.setChecked(True)
        self.dialog.playback_speed.setValue(2)
        self.dialog.walking_fps.setCurrentIndex(3)
        self.dialog.reset_button.click()
        self.assertEqual(self.prefs.load_character()[0], filename)
        self.assertEqual(self.prefs.pack_for(filename), before_pack)
        self.assertEqual(self.window._custom_file, filename)
        self.assertEqual(self.prefs.height, 150)
        self.assertEqual(self.prefs.display_options, (100, True, False))
        self.assertEqual(self.prefs.animation_options, (1, None))
        self.assertEqual(self.prefs.behavior_options, (True, "Normal", False))
        self.assertEqual(self.window._sprites.motion_fps, 10)
        self.assertEqual(len(self.window._sprites.frames["walk"]), 8)
        self.assertIn("Imported animation pack", self.dialog.pack_info.text())

    def test_switch_updates_cached_preview_and_disables_unavailable_playback(self):
        filename, character = self.prefs.import_character(self.root / "character.png", 150)
        self.dialog.select_character(lambda: self.window._apply_character(character, filename))
        self.assertEqual(self.dialog.preview.source.toImage(), character.toImage())
        self.assertFalse(self.dialog.walking_fps.isEnabled())
        self.assertFalse(self.dialog.playback_speed.isEnabled())
        self.assertIn("Static PNG", self.dialog.pack_info.text())
        walk_row = list(ACTIONS).index("walk")
        self.assertEqual(self.dialog.actions.item(walk_row, 1).text(), "Not supplied")
        self.assertEqual(set(self.window._sprites.frames), {"static"})
        self.dialog.select_character(self.window.restore_default)
        self.assertEqual(self.dialog.actions.item(walk_row, 1).text(), "8 - animated")
        self.assertTrue(self.dialog.walking_fps.isEnabled())

    def test_preview_fits_wide_transparent_image_and_reuses_scaled_cache(self):
        self.png(self.root / "wide.png", "transparent", 900, 100)
        source = QPixmap(str(self.root / "wide.png"))
        self.dialog.preview.set_character(source)
        self.dialog.preview.grab()
        scaled = self.dialog.preview._scaled
        self.assertTrue(scaled.hasAlphaChannel())
        self.assertAlmostEqual(scaled.width() / scaled.height(), 9, delta=0.3)
        dpr = self.dialog.preview.devicePixelRatioF()
        self.assertLessEqual(scaled.width() / dpr, self.dialog.preview.width() - 23)
        self.assertLessEqual(scaled.height() / dpr, self.dialog.preview.height() - 23)
        self.dialog.preview.grab()
        self.assertEqual(scaled.cacheKey(), self.dialog.preview._scaled.cacheKey())
        self.dialog.preview.set_character(QPixmap())
        self.assertFalse(self.dialog.preview.source.isNull())

    def test_playback_controls_change_frames_without_changing_action_duration(self):
        player = SpriteAnimation(self.pack, QPixmap(str(self.root / "character.png")), QSize(200, 150))
        player.playback_speed = 2
        player.walking_fps = 10
        player.set_walking(True)
        player.advance(0.11)
        self.assertEqual(player.frame_key, ("walk", 2))
        self.assertTrue(player.begin_action("walk", 1))
        player.advance(0.6)
        self.assertTrue(player.action_active)
        player.advance(0.4)
        self.assertFalse(player.action_active)

    def test_invalid_preferences_recover_without_losing_valid_pack(self):
        self.prefs.accept_pack("", self.pack, 10)
        path, _ = self.prefs.pack_for("")
        for key in ("height", "opacity", "animation/walk_fps", "packs/default-alya/fps"):
            self.prefs.settings.setValue(key, float("inf"))
        for key in ("always_on_top", "follow_cursor", "behavior/enabled", "behavior/paused", "behavior/edges"):
            self.prefs.settings.setValue(key, "damaged")
        self.prefs.settings.setValue("animation/speed", "nan")
        self.prefs.settings.setValue("behavior/frequency", "invalid")
        self.assertEqual(self.prefs.height, 150)
        self.assertEqual(self.prefs.display_options, (100, True, False))
        self.assertEqual(self.prefs.animation_options, (1, None))
        self.assertEqual(self.prefs.behavior_options, (True, "Normal", False))
        self.assertFalse(self.prefs.edge_behaviors)
        self.assertEqual(self.prefs.pack_for(""), (path, 8))

    def test_nested_pack_cancel_keeps_settings_pause_and_selection(self):
        self.window._dialog_open = True
        before = self.window._sprites
        with patch("app.pack_dialog.PackDialog.exec", return_value=QDialog.DialogCode.Rejected):
            self.dialog.import_button.click()
        self.assertTrue(self.window._dialog_open)
        self.assertIs(self.window._sprites, before)
        self.window._dialog_open = False

    def test_open_settings_is_singleton_and_does_not_modify_preferences(self):
        before = self.prefs.settings.allKeys()
        self.window._settings_dialog = self.dialog
        with patch("app.settings_dialog.CharacterSettingsDialog", side_effect=AssertionError("Duplicate dialog")):
            self.window.open_settings()
        self.window._settings_dialog = None
        self.assertEqual(self.prefs.settings.allKeys(), before)

    def test_accept_pack_from_settings_updates_preview_without_unpausing(self):
        self.window._dialog_open = True
        self.png(self.root / "replacement" / "idle" / "idle.png", "blue")
        source = self.root / "replacement"
        def accept_pack(dialog):
            dialog.load_source(source)
            return QDialog.DialogCode.Accepted
        with patch("app.pack_dialog.PackDialog.exec", accept_pack):
            self.dialog.import_button.click()
        self.assertTrue(self.window._dialog_open)
        self.assertIn("Imported animation pack", self.dialog.pack_info.text())
        self.assertEqual(self.dialog.preview.source.toImage().pixelColor(30, 50), QColor("blue"))
        self.assertEqual(len(self.window._sprites.frames["walk"]), 8)
        self.window._dialog_open = False

    def test_modal_settings_pause_then_resume_without_extra_timer(self):
        self.dialog.close()
        observations = []
        before = self.window.pos()
        def inspect_dialog():
            dialog = self.window._settings_dialog
            observations.append((self.window._dialog_open, dialog.isVisible()))
            self.window._tick()
            observations.append(self.window.pos() == before)
            dialog.accept()
        QTimer.singleShot(30, inspect_dialog)
        self.window.open_settings()
        self.assertEqual(observations, [(True, True), True])
        self.assertFalse(self.window._dialog_open)
        self.assertIsNone(self.window._settings_dialog)

    def test_failed_save_restores_controls_to_live_values(self):
        with patch.object(self.prefs, "save_animation_options", side_effect=OSError("Read only")), \
                patch.object(self.window, "_show_character_error") as error:
            self.dialog.playback_speed.setValue(2)
        error.assert_called_once()
        self.assertEqual(self.dialog.playback_speed.value(), 1)
        self.assertEqual(self.window._sprites.playback_speed, 1)

    def test_menu_keeps_existing_commands_once_and_disables_missing_actions(self):
        self.window._update_menu()
        def commands(menu):
            for action in menu.actions():
                if action.menu():
                    yield from commands(action.menu())
                elif not action.isSeparator():
                    yield action.text()
        names = list(commands(self.window._menu))
        for name in ("Change Character", "Import Animation Pack", "Character Settings", "AI Chibi Generator",
                     "Restore Default Alya", "Pause Movement", "Follow Cursor", "Exit ChibiMate"):
            self.assertEqual(names.count(name), 1)
        self.assertEqual(len(names), len(set(names)))
        self.assertFalse(self.window._sleep_action.isEnabled())
        self.assertFalse(self.window._dance_action.isEnabled())


if __name__ == "__main__":
    unittest.main()
