"""Sprite playback and fallback checks without extra test dependencies."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from app.sprites import AnimationState, FRAME_RATES, SPRITE_PATH, SpriteAnimation


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

    def test_surprised_reaction_restores_underlying_state(self):
        self.frame('surprised', 'surprise.png')
        player = self.player()
        player.set_walking(True)
        player.begin_reaction('surprised', 2)
        player.advance(0.016)
        self.assertEqual(player.frame_key, ('surprised', 0))
        player.end_reaction()
        self.assertEqual(player.frame_key, ('static', 0))
        self.assertEqual(player.state, 'walk')

    def test_optional_shy_pose_and_missing_reaction_preserve_current_frame(self):
        self.frame('walk', 'walk_1.png')
        self.frame('walk', 'walk_2.png', 'blue')
        self.frame('shy', 'shy.png', 'green')
        player = self.player()
        player.set_walking(True)
        player.advance(0.125)
        original = player.frame_key
        player.begin_reaction('happy', 2)
        player.advance(0.5)
        self.assertEqual(player.frame_key, original)
        player.end_reaction()
        player.begin_reaction('shy', 2)
        self.assertEqual(player.frame_key, ('shy', 0))
        player.end_reaction()
        self.assertEqual(player.frame_key, original)

    def test_alignment_size_and_transparency_remain_stable(self):
        self.frame('walk', 'walk_1.png', size=QSize(140, 200), body=QRect(2, 30, 50, 100))
        self.frame('walk', 'walk_2.png', 'blue', size=QSize(300, 300), body=QRect(140, 70, 80, 160))
        player = self.player()
        player.set_walking(True)
        first = player.pixmap(1).toImage()
        player.advance(0.125)
        second = player.pixmap(1).toImage()
        # Different source sizes/margins, same character proportions and anchor.
        self.assertEqual(bytes(first.constBits())[3::4], bytes(second.constBits())[3::4])
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

    def test_installed_alya_walk_sequence_plays_all_eight_frames_then_idle(self):
        player = SpriteAnimation(SPRITE_PATH, self.fallback, QSize(200, 150))
        self.assertEqual(len(player.frames['walk']), 8)
        player.set_walking(True)
        for index in range(16):
            self.assertEqual(player.frame_key, ('walk', index % 8))
            player.advance(1 / FRAME_RATES['walk'])
        player.set_walking(False)
        self.assertEqual(player.frame_key, ('idle', 0))
        self.assertEqual(player.animation_state, AnimationState.IDLE)

    def test_motion_requires_at_least_two_distinct_readable_poses(self):
        player = self.player()
        self.assertFalse(player.can_dance)
        self.assertFalse(player.begin_dance())
        for state in ('dance', 'walk'):
            first = self.frame(state, f'{state}_01.png')
            self.assertNotIn(state, self.player().frames)
            self.frame(state, f'{state}_02.png')  # Duplicate pose is not a cycle.
            self.assertNotIn(state, self.player().frames)
            self.frame(state, f'{state}_03.png', body=QRect())
            (first.parent / f'{state}_04.png').write_bytes(b'broken')
            with self.assertLogs('app.sprites', level='WARNING'):
                player = self.player()
            self.assertNotIn(state, player.frames)
            (first.parent / f'{state}_04.png').unlink()
            self.frame(state, f'{state}_02.png', 'blue')
            self.assertEqual(len(self.player().frames[state]), 2)

    def test_dance_uses_configured_fps_loops_and_restores_underlying_behavior(self):
        for number, color in ((10, 'blue'), (2, 'green'), (1, 'red')):
            self.frame('dance', f'dance_{number}.png', color)
        self.frame('idle', 'idle.png')
        player = self.player()
        with patch.dict(FRAME_RATES, dance=4):
            self.assertTrue(player.begin_dance(1.3))
            for index, color in enumerate(('#ff0000', '#008000', '#0000ff', '#ff0000')):
                self.assertEqual(player.animation_state, AnimationState.DANCING)
                name, frame = player.frame_key
                self.assertEqual((name, frame), ('dance', index % 3))
                self.assertEqual(player.frames[name][frame].toImage().pixelColor(0, 0).name(), color)
                player.advance(0.25)
            player.advance(0.31)
        self.assertEqual(player.animation_state, AnimationState.IDLE)
        self.assertEqual(player.frame_key, ('idle', 0))
        player.set_walking(True)
        self.assertTrue(player.begin_dance(0.5))
        player.advance(0.5)
        self.assertEqual(player.animation_state, AnimationState.WALKING)
        self.assertTrue(player.begin_dance(0.5))
        player.set_walking(False)  # Pause Movement during a dance.
        self.assertEqual(player.animation_state, AnimationState.DANCING)
        player.advance(0.5)
        self.assertEqual(player.animation_state, AnimationState.IDLE)
        for invalid in (0, -1, float('nan'), float('inf')):
            self.assertFalse(player.begin_dance(invalid))

    def test_reaction_and_dance_override_blink_and_never_overlap(self):
        for name in ('idle', 'blink', 'happy', 'surprised', 'dance'):
            self.frame(name, f'{name}_1.png')
        self.frame('dance', 'dance_2.png', 'blue')
        player = self.player()
        self.assertTrue(player.show_expression('blink', 0.22))
        self.assertEqual(player.animation_state, AnimationState.BLINKING)
        self.assertTrue(player.begin_reaction('happy', 1.5))
        self.assertFalse(player.begin_reaction('surprised', 2))
        self.assertFalse(player.show_expression('blink'))
        self.assertFalse(player.begin_dance())
        self.assertEqual(player.animation_state, AnimationState.REACTING)
        player.advance(1.5)
        self.assertEqual(player.animation_state, AnimationState.IDLE)
        self.assertEqual(player.frame_key, ('idle', 0))
        self.assertTrue(player.show_expression('blink', 0.22))
        self.assertTrue(player.begin_dance(1))
        blink_remaining = player._blink_remaining
        self.assertFalse(player.begin_reaction('happy', 1.5))
        self.assertFalse(player.show_expression('blink'))
        self.assertFalse(player.begin_dance())
        player.advance(1)
        self.assertEqual(player._blink_remaining, blink_remaining)
        self.assertEqual(player.animation_state, AnimationState.IDLE)

    def test_faint_edges_are_preserved_when_removing_transparent_margins(self):
        path = self.frame('idle', 'idle.png', size=QSize(20, 30), body=QRect(5, 5, 10, 20))
        image = QImage(str(path))
        for point in ((0, 0), (19, 0), (0, 29), (19, 29)):
            image.setPixelColor(*point, QColor(255, 255, 255, 32))
        self.assertTrue(image.save(str(path)))
        frame = self.player().frames['idle'][0].toImage()
        self.assertEqual(frame.size(), image.size())
        self.assertEqual(frame.pixelColor(0, 0).alpha(), 32)
        self.assertEqual(frame.pixelColor(19, 29).alpha(), 32)

    def test_resizing_active_dance_reuses_sources_and_updates_cached_canvas(self):
        self.frame('dance', 'dance_1.png')
        self.frame('dance', 'dance_2.png', 'blue')
        player = self.player()
        self.assertTrue(player.begin_dance())
        player.advance(0.125)
        key = player.frame_key
        before = player.pixmap(1)
        with patch('app.sprites.QImage', side_effect=AssertionError('Image reloaded during playback')):
            player.set_max_size(QSize(267, 200))
            self.assertEqual(player.frame_key, key)
            after = player.pixmap(1)
            self.assertEqual(after.height(), 200)
            self.assertNotEqual(before.cacheKey(), after.cacheKey())
            self.assertEqual(after.cacheKey(), player.pixmap(1).cacheKey())
            player.advance(0.125)
            self.assertFalse(player.pixmap(1.25).isNull())


if __name__ == '__main__':
    unittest.main()
