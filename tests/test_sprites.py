"""Sprite playback and fallback checks without extra test dependencies."""

import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from app.sprites import SpriteAnimation


class SpriteAnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fallback = QPixmap(60, 100)
        self.fallback.fill(QColor('purple'))

    def tearDown(self):
        self.temp.cleanup()

    def frame(self, state, name, color='red', size=QSize(140, 200), body=QRect(40, 30, 50, 100)):
        path = self.root / state / name
        path.parent.mkdir(parents=True, exist_ok=True)
        image = QImage(size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.fillRect(body, QColor(color))
        painter.end()
        self.assertTrue(image.save(str(path)))
        return path

    def player(self):
        return SpriteAnimation(self.root, self.fallback, QSize(200, 150))

    def test_natural_order_and_looping_walk_frames(self):
        self.frame('walk', 'walk_10.png', 'blue')
        self.frame('walk', 'walk_2.png', 'green')
        self.frame('walk', 'walk_1.png', 'red')
        player = self.player()
        player.set_walking(True)
        colors = []
        for _ in range(4):
            state, index = player.frame_key
            colors.append(player.frames[state][index].toImage().pixelColor(0, 0).name())
            player.advance(0.125)
        self.assertEqual(colors, ['#ff0000', '#008000', '#0000ff', '#ff0000'])

    def test_missing_insufficient_and_invalid_frames_use_static(self):
        path = self.frame('walk', 'walk_1.png')
        (path.parent / 'walk_2.png').write_bytes(b'invalid image')
        self.frame('walk', 'walk_3.png', body=QRect())  # Fully transparent.
        with self.assertLogs('app.sprites', level='WARNING'):
            player = self.player()
        self.assertEqual(player.frame_key, ('static', 0))
        player.set_walking(True)
        player.advance(1)
        self.assertEqual(player.frame_key, ('static', 0))
        self.assertEqual(player.frames['static'][0].toImage(), self.fallback.toImage())
        player.set_walking(False)
        self.assertFalse(player.show_expression('happy'))

    def test_idle_sequence_and_single_frame_pose_are_supported(self):
        self.frame('idle', 'idle_1.png')
        player = self.player()
        player.advance(1)
        self.assertEqual(player.frame_key, ('idle', 0))
        self.frame('idle', 'idle_2.png', 'blue')
        player = self.player()
        player.advance(0.5)
        self.assertEqual(player.frame_key, ('idle', 1))
        player.advance(0.5)
        self.assertEqual(player.frame_key, ('idle', 0))

    def test_random_blink_returns_to_idle_and_walk_takes_priority(self):
        self.frame('idle', 'idle.png')
        self.frame('blink', 'blink.png', 'blue')
        player = self.player()
        player._blink_remaining = 0.01
        player.advance(0.02)
        self.assertEqual(player.frame_key, ('blink', 0))
        self.assertTrue(3 <= player._blink_remaining <= 6)
        player.advance(0.23)
        self.assertEqual(player.frame_key, ('idle', 0))
        self.assertTrue(player.show_expression('blink', 0.22))
        player.set_walking(True)
        self.assertEqual(player.state, 'walk')
        self.assertEqual(player.frame_key, ('static', 0))
        self.assertFalse(player.show_expression('blink'))
        player.set_walking(False)
        self.assertEqual(player.frame_key, ('idle', 0))

    def test_temporary_expression_plays_once_then_restores_idle(self):
        self.frame('idle', 'idle.png')
        for index, color in enumerate(('red', 'green', 'blue'), 1):
            self.frame('happy', f'happy_{index}.png', color)
        player = self.player()
        self.assertTrue(player.show_expression('happy', 0.6))
        self.assertEqual(player.frame_key, ('happy', 0))
        player.advance(0.21)
        self.assertEqual(player.frame_key, ('happy', 1))
        player.advance(0.21)
        self.assertEqual(player.frame_key, ('happy', 2))
        player.advance(0.21)
        self.assertEqual(player.frame_key, ('idle', 0))
        self.assertFalse(player.show_expression('happy', 0))
        self.assertFalse(player.show_expression('happy', float('nan')))

    def test_random_expression_uses_available_pose(self):
        self.frame('surprised', 'surprise.png')
        player = self.player()
        player._blink_remaining = 99
        player._expression_remaining = 0
        player.advance(0.016)
        self.assertEqual(player.frame_key, ('surprised', 0))
        self.assertTrue(12 <= player._expression_remaining <= 22)
        player.advance(1.3)
        self.assertEqual(player.frame_key, ('static', 0))

    def test_alignment_size_and_transparency_remain_stable(self):
        self.frame('walk', 'walk_1.png', size=QSize(140, 200), body=QRect(2, 30, 50, 100))
        self.frame('walk', 'walk_2.png', size=QSize(300, 300), body=QRect(140, 70, 80, 160))
        player = self.player()
        player.set_walking(True)
        first = player.pixmap(1).toImage()
        player.advance(0.125)
        second = player.pixmap(1).toImage()
        # Different source sizes/margins, same character proportions and anchor.
        self.assertEqual(first, second)
        self.assertEqual(first.size(), player.size)
        self.assertEqual(first.pixelColor(0, 0).alpha(), 0)
        self.assertEqual(first.pixelColor(first.width() // 2, first.height() - 1).alpha(), 255)

    def test_scaled_frames_are_cached_and_refresh_for_new_display_scale(self):
        self.frame('idle', 'idle.png')
        player = self.player()
        first = player.pixmap(1)
        self.assertEqual(first.cacheKey(), player.pixmap(1).cacheKey())
        second = player.pixmap(2)
        self.assertEqual(second.width(), first.width() * 2)
        self.assertEqual(second.height(), first.height() * 2)
        self.assertNotEqual(first.cacheKey(), second.cacheKey())
        self.assertEqual(second.cacheKey(), player.pixmap(2).cacheKey())


if __name__ == '__main__':
    unittest.main()
