"""Offline regressions for bounded imports, resource use, and recovery."""

import tempfile
import time
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEvent, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.images import png_image
from app.pack_dialog import PackDialog
from app.packs import validate_pack
from app.preferences import CharacterPreferences, read_png
from app.sprites import SpriteAnimation, load_frames
from app.window import CharacterWindow


class StabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pack = self.root / "pack"
        self.png(self.root / "character.png")
        self.png(self.pack / "idle" / "idle.png")
        for i, color in enumerate((Qt.GlobalColor.red, Qt.GlobalColor.blue)):
            self.png(self.pack / "walk" / f"walk_{i}.png", color)
        self.png(self.pack / "sleeping" / "sleep.png")
        self.prefs = CharacterPreferences(self.root / "data")
        self.w = CharacterWindow(self.root / "character.png", self.pack, self.prefs)
        self.w.show()
        self.w._timer.stop()
        self.app.processEvents()

    def tearDown(self):
        for obj in self.app.topLevelWidgets():
            obj.close()
            obj.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.temp.cleanup()

    def png(self, path, color=Qt.GlobalColor.red, size=QSize(60, 100)):
        path.parent.mkdir(parents=True, exist_ok=True)
        image = QImage(size, QImage.Format.Format_ARGB32)
        image.fill(color)
        self.assertTrue(image.save(str(path), "PNG"))

    def wait_worker(self, dialog):
        deadline = time.monotonic() + 10
        while dialog.worker is not None and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertIsNone(dialog.worker, "Import worker did not finish")

    def test_repaint_requests_follow_frames_and_idle_bob_remains_smooth(self):
        self.w._start_walk(manual=True)
        self.w._remaining = 100
        self.w.move(300, 300)
        with patch.object(self.w, "update") as redraw:
            for _ in range(600):
                self.w._advance(1 / 60)
        self.assertGreaterEqual(redraw.call_count, 79)
        self.assertLessEqual(redraw.call_count, 83)
        self.w._start_idle()
        self.w.set_behavior_options(enabled=False)
        with patch.object(self.w, "update") as redraw:
            for _ in range(60):
                self.w._advance(1 / 60)
        self.assertGreater(redraw.call_count, 40)

    def test_static_sleep_needs_no_repeated_repaint_and_wakes_normally(self):
        self.assertTrue(self.w.perform_action("sleeping"))
        self.w._advance(0.1)
        with patch.object(self.w, "update") as redraw:
            for _ in range(120):
                self.w._advance(1 / 60)
        self.assertEqual(redraw.call_count, 0)
        self.w.return_to_idle()
        self.assertFalse(self.w._sprites.action_active)

    def test_single_root_scan_and_unchanged_size_preserve_scaled_cache(self):
        scans = []
        original = Path.iterdir
        def scan(path):
            scans.append(path)
            return original(path)
        with patch.object(Path, "iterdir", scan):
            player = SpriteAnimation(self.pack, self.w._character, QSize(200, 150))
        self.assertEqual(scans.count(self.pack), 1)
        first = player.pixmap(1).cacheKey()
        with patch("app.sprites.load_frames", side_effect=AssertionError("Reload during playback")):
            player.set_max_size(QSize(200, 150))
            player.advance(0.01)
            self.assertEqual(player.pixmap(1).cacheKey(), first)

    def test_unreadable_sprite_folder_falls_back_without_losing_character(self):
        with patch.object(Path, "iterdir", side_effect=PermissionError("denied")), \
                self.assertLogs("app.sprites", level="WARNING"):
            self.w._apply_character(self.w._character, "")
        self.assertEqual(set(self.w._sprites.frames), {"static"})
        self.assertFalse(self.w._sprites.pixmap(1).isNull())

    def test_failed_character_preparation_preserves_identity_and_player(self):
        before = (self.w._custom_file, self.w._sprites, self.w._character.cacheKey())
        with patch("app.window.SpriteAnimation", side_effect=OSError("Unavailable")), self.assertRaises(OSError):
            self.w._apply_character(self.w._character, "new-character")
        self.assertEqual((self.w._custom_file, self.w._sprites, self.w._character.cacheKey()), before)

    def test_switch_loading_failure_restores_saved_selection(self):
        filename, image = self.prefs.import_character(self.root / "character.png", 150)
        self.w._apply_character(image, filename)
        before = set(self.prefs.directory.iterdir())
        with patch("app.window.QFileDialog.getOpenFileName", return_value=(str(self.root / "character.png"), "PNG")), \
                patch("app.window.SpriteAnimation", side_effect=OSError("Read failed")), \
                patch.object(self.w, "_show_character_error") as error:
            self.w.change_character()
        error.assert_called_once()
        self.assertEqual(self.prefs.load_character()[0], filename)
        self.assertEqual(self.w._custom_file, filename)
        self.assertEqual(set(self.prefs.directory.iterdir()), before)

    def test_png_limits_corruption_and_invisible_characters_are_rejected(self):
        self.png(self.root / "large.png", size=QSize(8193, 1))
        with self.assertRaisesRegex(ValueError, "dimensions"):
            read_png(self.root / "large.png")
        with self.assertRaises(ValueError):
            png_image((self.root / "character.png").read_bytes(), max_pixels=1)
        with self.assertRaises(ValueError):
            png_image(b"damaged")
        self.png(self.root / "empty.png", Qt.GlobalColor.transparent)
        with self.assertRaisesRegex(ValueError, "visible"):
            read_png(self.root / "empty.png")

    def test_failed_preference_save_removes_new_copy_and_retains_previous(self):
        old, _ = self.prefs.import_character(self.root / "character.png", 150)
        before = set(self.prefs.directory.iterdir())
        with patch.object(self.prefs, "save", side_effect=OSError("Read only")), self.assertRaises(OSError):
            self.prefs.import_character(self.root / "character.png", 150)
        self.assertEqual(set(self.prefs.directory.iterdir()), before)
        self.assertEqual(self.prefs.load_character()[0], old)

    def test_damaged_deflate_stream_is_a_friendly_validation_error(self):
        archive = self.root / "pack.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("idle/idle.png", (self.root / "character.png").read_bytes())
        with patch.object(zipfile.ZipFile, "open", side_effect=zlib.error("bad stream")):
            with self.assertRaisesRegex(ValueError, "damaged"):
                validate_pack(archive, self.root / "stage")

    def test_pack_copy_failure_rolls_back_association_and_partial_directory(self):
        self.prefs.accept_pack("", self.pack, 8)
        before = self.prefs.pack_for("")
        existing = set((self.prefs.directory / "animation-packs").iterdir())
        def broken_copy(source, destination):
            destination.mkdir()
            (destination / "partial.png").write_bytes(b"partial")
            raise OSError("Disk full")
        with patch("app.preferences.shutil.copytree", broken_copy), self.assertRaises(OSError):
            self.prefs.accept_pack("", self.pack, 10)
        self.assertEqual(self.prefs.pack_for(""), before)
        self.assertEqual(set((self.prefs.directory / "animation-packs").iterdir()), existing)

    def test_worker_keeps_gui_responsive_and_preview_uses_prepared_frames(self):
        dialog = PackDialog(self.w._character, self.w)
        dialog.show()
        real_validate = validate_pack
        def delayed(*args):
            time.sleep(0.12)  # Simulate slow storage in the worker only.
            return real_validate(*args)
        ticks = []
        timer = QTimer(dialog)
        timer.setInterval(10)
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start()
        try:
            with patch("app.pack_dialog.validate_pack", delayed), \
                    patch("socket.socket.connect", side_effect=AssertionError("Network used")):
                dialog.start_loading(self.pack)
                worker = dialog.worker
                dialog.start_loading(self.pack)
                self.assertIs(dialog.worker, worker)
                self.assertFalse(dialog.apply.isEnabled())
                self.wait_worker(dialog)
            self.assertGreaterEqual(len(ticks), 3)
            self.assertTrue(dialog.apply.isEnabled())
            self.assertEqual(len(dialog.player.frames["walk"]), 2)
            dialog.select_action("sleeping")
            self.assertFalse(dialog.timer.isActive())
            dialog.select_action("walk")
            self.assertTrue(dialog.timer.isActive())
        finally:
            timer.stop()
            dialog.cleanup()

    def test_cancel_worker_closes_safely_and_cleans_staging(self):
        dialog = PackDialog(self.w._character, self.w)
        dialog.show()
        candidates = []
        def cancellable(source, destination, cancelled):
            candidates.append(destination)
            while not cancelled():
                time.sleep(0.005)
            raise InterruptedError()
        with patch("app.pack_dialog.validate_pack", cancellable):
            dialog.start_loading(self.pack)
            dialog.close()
            self.wait_worker(dialog)
        self.assertFalse(dialog.isVisible())
        self.assertFalse(dialog.timer.isActive())
        self.assertTrue(candidates)
        self.assertTrue(all(not candidate.exists() for candidate in candidates))
        self.assertIsNone(dialog.staging)

    def test_exit_during_modal_import_waits_for_worker_cleanup(self):
        candidates = []
        def cancellable(source, destination, cancelled):
            candidates.append(destination)
            while not cancelled():
                time.sleep(0.005)
            raise InterruptedError()
        def begin():
            dialog = self.w._pack_dialog
            dialog.start_loading(self.pack)
            self.w.close()
        with patch("app.pack_dialog.validate_pack", cancellable):
            QTimer.singleShot(20, begin)
            self.w.import_animation_pack()
            self.app.processEvents()
        self.assertIsNone(self.w._pack_dialog)
        self.assertFalse(self.w.isVisible())
        self.assertFalse(self.w._timer.isActive())
        self.assertTrue(candidates)
        self.assertTrue(all(not candidate.exists() for candidate in candidates))

    def test_worker_failure_keeps_previous_preview_and_character(self):
        dialog = PackDialog(self.w._character, self.w)
        dialog.load_source(self.pack)
        previous = dialog.player
        with patch("app.pack_dialog.validate_pack", side_effect=ValueError("Invalid PNG")):
            dialog.start_loading(self.pack)
            self.wait_worker(dialog)
        self.assertIs(dialog.player, previous)
        self.assertTrue(dialog.apply.isEnabled())
        self.assertIn("Invalid PNG", dialog.status.text())
        self.assertIsNone(self.prefs.pack_for("")[0])
        dialog.cleanup()

    def test_screen_refit_restores_preferred_size_and_repositions_bubble(self):
        self.w.set_character_size(300)
        self.w._bubble.show_message("Hello!", self.w.geometry(), QRect(0, 0, 1000, 800), 1000)
        for area in (QRect(-200, -50, 100, 100), QRect(0, 0, 1000, 800)):
            with patch.object(self.w, "_available_area", return_value=area):
                self.w._advance(0.01)
            self.assertTrue(area.contains(self.w.geometry()))
            self.assertTrue(area.contains(self.w._bubble.geometry()))
        self.assertEqual(self.w._character_height, 300)
        self.assertEqual(self.w._character_size.height(), 300)

    def test_settings_and_menu_suspend_timer_and_resume_once(self):
        self.w._timer.start()
        def inspect():
            self.assertFalse(self.w._timer.isActive())
            self.w._settings_dialog.accept()
        QTimer.singleShot(30, inspect)
        self.w.open_settings()
        self.assertTrue(self.w._timer.isActive())
        self.w._menu.popup(self.w.pos())
        self.assertFalse(self.w._timer.isActive())
        self.w._menu.hide()
        self.assertTrue(self.w._timer.isActive())
        self.w.close()
        self.assertFalse(self.w._timer.isActive())


if __name__ == "__main__":
    unittest.main()
