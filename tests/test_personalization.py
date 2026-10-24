"""Import, persistence, resizing, and animation isolation checks."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.preferences import CharacterPreferences
from app.window import BOB_PADDING, CHARACTER_PATH, CharacterWindow


class PersonalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.preferences = CharacterPreferences(self.root / 'app-data')
        self.source = self.root / 'user-original.png'
        image = QImage(600, 900, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.fillRect(100, 50, 400, 800, QColor('#64b5bd'))
        painter.end()
        self.assertTrue(image.save(str(self.source)))
        self.window = CharacterWindow(preferences=self.preferences)
        self.window.show()
        self.window._timer.stop()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        for widget in self.app.topLevelWidgets():
            widget.close()
            widget.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.temp.cleanup()

    def choose(self, filename=None):
        with patch('app.window.QFileDialog.getOpenFileName', return_value=(str(filename or self.source), 'PNG images (*.png)')):
            self.window.change_character()

    def reopen(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.window = CharacterWindow(preferences=CharacterPreferences(self.preferences.directory))
        self.window.show()
        self.window._timer.stop()
        self.app.processEvents()

    def test_import_copies_exact_png_and_survives_original_deletion_and_restart(self):
        original = self.source.read_bytes()
        self.choose()
        saved = self.preferences.directory / self.window._custom_file
        self.assertEqual(saved.read_bytes(), original)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(self.window._character.size(), QImage(str(self.source)).size())
        self.assertEqual(self.window._character_size.height(), 150)
        self.assertEqual(self.window.grab().toImage().pixelColor(0, 0).alpha(), 0)
        self.window.set_character_size(200)
        self.source.unlink()
        self.reopen()
        self.assertEqual(saved.name, self.window._custom_file)
        self.assertEqual(self.window._character_height, 200)
        self.assertEqual(self.window._character_size.height(), 200)
        self.assertEqual(set(self.window._sprites.frames), {'static'})

    def test_cancel_and_invalid_selection_keep_character_and_preferences(self):
        self.choose()
        before = self.window._character.toImage()
        selection = self.window._custom_file
        settings = self.preferences.settings.value('character')
        with patch('app.window.QFileDialog.getOpenFileName', return_value=('', '')):
            self.window.change_character()
        invalid = self.root / 'invalid.png'
        invalid.write_text('not an image')
        with patch('app.window.QMessageBox.warning') as warning:
            self.choose(invalid)
        warning.assert_called_once()
        self.assertIn('PNG', warning.call_args.args[2])
        self.assertEqual(self.window._character.toImage(), before)
        self.assertEqual(self.window._custom_file, selection)
        self.assertEqual(self.preferences.settings.value('character'), settings)

    def test_storage_failure_reports_error_and_keeps_current_selection(self):
        before = self.window._character.toImage()
        with patch.object(self.preferences, 'save', side_effect=OSError('Cannot save preferences')), \
             patch('app.window.QMessageBox.warning') as warning:
            self.choose()
        warning.assert_called_once()
        self.assertEqual(self.window._character.toImage(), before)
        self.assertEqual(self.window._custom_file, '')

    def test_static_character_never_uses_alya_frames_in_any_state(self):
        self.choose()
        window = self.window
        self.assertEqual(set(window._sprites.frames), {'static'})
        window._start_walk()
        window._sprites.advance(0.5)
        self.assertEqual(window._sprites.frame_key, ('static', 0))
        for reaction in ('happy', 'surprised', 'shy', 'blink'):
            window._sprites.begin_reaction(reaction, 2)
            window._sprites.advance(0.5)
            self.assertEqual(window._sprites.frame_key, ('static', 0))
            window._sprites.end_reaction()
        window._start_idle()
        window._sprites.advance(7)
        self.assertEqual(window._sprites.frame_key, ('static', 0))

    def test_switch_during_reaction_and_restore_default_preserve_size_and_originals(self):
        alya = CHARACTER_PATH.read_bytes()
        self.window.set_character_size(100)
        self.window._start_walk()
        self.assertTrue(self.window.trigger_random_reaction())
        self.choose()
        stored = self.preferences.directory / self.window._custom_file
        self.assertFalse(self.window._bubble.isVisible())
        self.assertEqual(self.window._reaction_remaining, 0)
        self.assertFalse(self.window._walking)
        self.window.restore_default()
        self.assertEqual(self.window._custom_file, '')
        self.assertEqual(self.window._character_height, 100)
        self.assertEqual(len(self.window._sprites.frames['walk']), 8)
        self.assertTrue(stored.is_file())
        self.assertTrue(self.source.is_file())
        self.assertEqual(CHARACTER_PATH.read_bytes(), alya)
        self.reopen()
        self.assertEqual(self.window._custom_file, '')
        self.assertEqual(self.window._character_height, 100)
        self.assertIn('walk', self.window._sprites.frames)

    def test_missing_and_corrupt_saved_png_fall_back_to_alya(self):
        self.choose()
        self.window.set_character_size(200)
        saved = self.preferences.directory / self.window._custom_file
        for corrupt in (True, False):
            if corrupt:
                saved.write_bytes(b'broken png')
            else:
                saved.unlink()
            with self.assertLogs('app.preferences', level='WARNING'):
                self.reopen()
            self.assertEqual(self.window._custom_file, '')
            self.assertEqual(self.window._character_height, 200)
            self.assertIn('walk', self.window._sprites.frames)

    def test_all_sizes_keep_aspect_ratio_on_screen_and_reuse_loaded_frames(self):
        self.choose()
        window = self.window
        source_key = window._character.cacheKey()
        area = window._available_area()
        for height in (100, 150, 200):
            window.move(area.right() + 1 - window.width(), area.top())
            with patch('app.sprites.QImage', side_effect=AssertionError('Unexpected image reload')):
                window._size_actions[height].trigger()
            self.assertEqual(window._character_size.height(), height)
            self.assertLessEqual(abs(window._character_size.width() - height * 2 / 3), 1)
            self.assertEqual(window.height(), height + 2 * BOB_PADDING)
            self.assertTrue(area.contains(window.geometry()))
            self.assertEqual(window._character.cacheKey(), source_key)
            self.assertTrue(window._size_actions[height].isChecked())
        # Resizing a walking character must not reuse its old fractional x position.
        window._start_walk()
        window.set_character_size(100)
        position = window.pos()
        window._advance(0.016)
        self.assertLessEqual(abs(window.x() - position.x()), 1)

    def test_picker_pauses_behavior_and_resumes_after_cancel(self):
        window = self.window
        window._start_walk()
        window._timer.start()
        def picker(*args):
            before = (window.pos(), window._sprites.frame_key, window._remaining)
            self.assertFalse(window._timer.isActive())
            QTest.qWait(80)
            self.assertEqual((window.pos(), window._sprites.frame_key, window._remaining), before)
            self.assertFalse(window.trigger_random_reaction())
            return '', ''
        with patch('app.window.QFileDialog.getOpenFileName', side_effect=picker):
            window.change_character()
        self.assertTrue(window._timer.isActive())
        self.assertTrue(window._walking)

    def test_custom_character_keeps_dragging_click_reactions_and_pause(self):
        self.choose()
        window = self.window
        window._toggle_movement()
        local = QPoint(30, 60)
        before = window.pos()
        start = window.mapToGlobal(local)
        delta = QPoint(-40, -25)
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=local)
        self.app.sendEvent(window, QMouseEvent(
            QEvent.Type.MouseMove, QPointF(local + delta), QPointF(start + delta),
            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        ))
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=local)
        self.assertEqual(window.pos(), before + delta)
        self.assertTrue(window._movement_paused)
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=local)
        self.assertTrue(window._bubble.isVisible())
        self.assertEqual(window._sprites.frame_key, ('static', 0))

    def test_extreme_image_proportions_and_bad_settings_remain_safe(self):
        image = QImage(1, 10000, QImage.Format.Format_ARGB32)
        image.fill(QColor('green'))
        self.assertTrue(image.save(str(self.source)))
        self.choose()
        self.assertGreater(self.window.width(), 0)
        self.assertFalse(self.window._sprites.pixmap(1).isNull())
        self.preferences.settings.setValue('height', 'invalid')
        self.preferences.settings.setValue('character', '../outside.png')
        self.preferences.settings.sync()
        with self.assertLogs('app.preferences', level='WARNING'):
            self.reopen()
        self.assertEqual(self.window._character_height, 150)
        self.assertEqual(self.window._custom_file, '')


if __name__ == '__main__':
    unittest.main()
