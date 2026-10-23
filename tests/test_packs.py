"""Local pack import, preview, persistence, and archive safety checks."""
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QDialog

from app.packs import validate_pack
from app.pack_dialog import PackDialog
from app.preferences import CharacterPreferences
from app.window import CharacterWindow


class PackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pack = self.root / 'source'
        self.pack.mkdir()
        self.source = self.root / 'character.png'
        self.png(self.source, 'purple')
        self.prefs = CharacterPreferences(self.root / 'user-data')
        self.filename, self.character = self.prefs.import_character(self.source, 150)
        self.window = CharacterWindow(preferences=self.prefs)
        self.window.show()
        self.window._timer.stop()
        self.dialog = PackDialog(self.character, self.window)
        self.dialog.show()

    def tearDown(self):
        self.dialog.cleanup()
        self.dialog.close()
        self.dialog.deleteLater()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def png(self, path, color):
        path.parent.mkdir(parents=True, exist_ok=True)
        image = QImage(60, 100, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        for x in range(10, 50):
            for y in range(10, 90):
                image.setPixelColor(x, y, QColor(color))
        self.assertTrue(image.save(str(path)))

    def frames(self, count=8):
        for index in range(1, count + 1):
            self.png(self.pack / 'walk' / f'walk_{index}.png', QColor(index * 20, 40, 80))
        for action in ('idle', 'blink', 'happy', 'surprised'):
            self.png(self.pack / action / f'{action}_01.png', 'blue')
        for index, color in enumerate(('red', 'blue'), 1):
            self.png(self.pack / 'dance' / f'dance_{index}.png', color)

    def test_folder_preview_and_apply_are_offline_and_preserve_originals(self):
        self.frames()
        original = self.source.read_bytes()
        with patch('socket.socket.connect', side_effect=AssertionError('Network used')):
            self.dialog.load_source(self.pack)
            self.assertTrue(self.dialog.apply.isEnabled())
            self.assertIn('shy', self.dialog.status.text())
            self.assertEqual(len(self.dialog.player.frames['walk']), 8)
            self.dialog.select_action('walk')
            first = self.dialog.player.frame_key
            self.dialog.player.advance(0.125)
            self.assertNotEqual(self.dialog.player.frame_key, first)
            self.assertEqual(set(self.window._sprites.frames), {'static'})
            self.prefs.accept_pack(self.filename, Path(self.dialog.staging.name), 12)
            self.window._apply_character(self.character, self.filename)
            self.assertEqual(self.window._sprites.motion_fps, 12)
            self.assertEqual(len(self.window._sprites.frames['walk']), 8)
            self.window._start_walk()
            self.window._sprites.advance(1 / 12)
            self.assertEqual(self.window._sprites.frame_key, ('walk', 1))
            self.window._start_idle()
            self.assertEqual(self.window._sprites.frame_key, ('idle', 0))
            self.window._sprites._blink_remaining = 0
            self.window._sprites.advance(0.01)
            self.assertEqual(self.window._sprites.frame_key, ('blink', 0))
            self.assertTrue(self.window.start_dance())
        self.assertEqual(original, self.source.read_bytes())

    def test_zip_wrapper_and_four_frame_numerical_order(self):
        for number, color in ((10, 'blue'), (2, 'green'), (1, 'red'), (3, 'yellow')):
            self.png(self.pack / 'walk' / f'walk_{number}.png', color)
        archive = self.root / 'pack.zip'
        with zipfile.ZipFile(archive, 'w') as zipped:
            for path in self.pack.rglob('*.png'):
                zipped.write(path, 'character_pack/' + path.relative_to(self.pack).as_posix())
        self.dialog.load_source(archive)
        self.assertTrue(self.dialog.apply.isEnabled())
        frames = self.dialog.player.frames['walk']
        self.assertEqual([frame.toImage().pixelColor(0, 0).name() for frame in frames],
                         ['#ff0000', '#008000', '#ffff00', '#0000ff'])

    def test_persistence_character_switch_reimport_and_missing_pack(self):
        self.frames(4)
        self.dialog.load_source(self.pack)
        self.prefs.accept_pack(self.filename, Path(self.dialog.staging.name), 10)
        fresh = CharacterPreferences(self.prefs.directory)
        saved, fps = fresh.pack_for(self.filename)
        self.assertEqual(fps, 10)
        self.assertTrue((saved / 'walk' / 'walk_1.png').is_file())
        other = self.root / 'other.png'
        self.png(other, 'green')
        other_id, other_image = fresh.import_character(other, 200)
        self.window._apply_character(other_image, other_id)
        self.assertEqual(set(self.window._sprites.frames), {'static'})
        same_id, same_image = fresh.import_character(self.source, 200)
        self.window._apply_character(same_image, same_id)
        self.assertEqual(len(self.window._sprites.frames['walk']), 4)
        self.window.restore_default()
        self.assertEqual(len(self.window._sprites.frames['walk']), 8)
        # Move only this test-owned directory to simulate a deleted pack.
        saved.rename(saved.with_name(saved.name + '-missing'))
        with self.assertLogs('app.preferences', level='WARNING'):
            self.window._apply_character(same_image, same_id)
        self.assertEqual(set(self.window._sprites.frames), {'static'})

    def test_reject_and_invalid_second_import_keep_existing_pack(self):
        self.frames(4)
        self.dialog.load_source(self.pack)
        self.prefs.accept_pack(self.filename, Path(self.dialog.staging.name), 8)
        before = self.prefs.pack_for(self.filename)
        self.png(self.pack / 'walk' / 'walk_9.png', 'pink')
        self.dialog.load_source(self.pack)
        self.dialog.reject()
        self.assertEqual(self.prefs.pack_for(self.filename), before)
        self.assertFalse(self.dialog.timer.isActive())
        (self.pack / 'walk' / 'bad.png').write_bytes(b'broken')
        self.dialog.load_source(self.pack)
        self.assertIn('Invalid', self.dialog.status.text())
        self.assertEqual(self.prefs.pack_for(self.filename), before)

    def test_rejects_unsafe_archive_paths_and_symlinks(self):
        for name in ('../escape.png', '/absolute.png', 'C:/evil.png', 'walk/../bad.png', 'walk\\evil.png', 'walk/CON.png'):
            archive = self.root / 'unsafe.zip'
            with zipfile.ZipFile(archive, 'w') as zipped:
                zipped.writestr(name, self.source.read_bytes())
            # Windows ZipInfo normalizes backslashes when writing; restore the
            # malicious spelling in both headers to exercise a received ZIP.
            if '\\' in name:
                archive.write_bytes(archive.read_bytes().replace(name.replace('\\', '/').encode(), name.encode()))
            with self.assertRaises(ValueError):
                validate_pack(archive, self.root / 'stage')
        archive = self.root / 'link.zip'
        with zipfile.ZipFile(archive, 'w') as zipped:
            entry = zipfile.ZipInfo('walk/link.png')
            entry.create_system = 3
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            zipped.writestr(entry, 'target')
        with self.assertRaises(ValueError):
            validate_pack(archive, self.root / 'stage')
        self.assertFalse((self.root / 'escape.png').exists())

    def test_limits_invalid_empty_and_duplicate_images(self):
        with self.assertRaises(ValueError):
            validate_pack(self.pack, self.root / 'stage')

        self.frames(4)
        with patch('app.packs.MAX_BYTES', 1), self.assertRaises(ValueError):
            validate_pack(self.pack, self.root / 'stage')
        with patch('app.packs.MAX_PIXELS', 1), self.assertRaises(ValueError):
            validate_pack(self.pack, self.root / 'stage')
        image = QImage(2050, 1, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.red)
        image.save(str(self.pack / 'walk' / 'huge.png'))
        with self.assertRaises(ValueError):
            validate_pack(self.pack, self.root / 'stage')
        (self.pack / 'walk' / 'huge.png').unlink()
        image = QImage(60, 100, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        image.save(str(self.pack / 'idle' / 'empty.png'))
        with self.assertRaises(ValueError):
            validate_pack(self.pack, self.root / 'stage')


    def test_duplicate_zip_names_and_corrupt_archives_are_rejected(self):
        archive = self.root / 'duplicate.zip'
        with zipfile.ZipFile(archive, 'w') as zipped:
            zipped.writestr('walk/a.png', self.source.read_bytes())
            zipped.writestr('WALK/A.PNG', self.source.read_bytes())
        with self.assertRaises(ValueError):
            validate_pack(archive, self.root / 'stage')
        archive.write_bytes(b'not a zip')
        with self.assertRaises(ValueError):
            validate_pack(archive, self.root / 'stage')

    def test_menu_accept_uses_preview_and_keeps_size(self):
        self.frames(4)
        self.window.set_character_size(200)
        def accept(dialog):
            dialog.load_source(self.pack)
            dialog.fps.setValue(11)
            return QDialog.DialogCode.Accepted
        with patch.object(PackDialog, 'exec', accept):
            self.window.import_animation_pack()
        self.assertEqual(self.window._character_height, 200)
        self.assertEqual(self.window._sprites.motion_fps, 11)
        self.assertEqual(len(self.window._sprites.frames['walk']), 4)
        self.assertTrue(self.window._available_area().contains(self.window.geometry()))


if __name__ == '__main__':
    unittest.main()
