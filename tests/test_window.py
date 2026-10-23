"""Phase 2 behavior checks using Qt's native event loop and standard unittest."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QContextMenuEvent, QMouseEvent, QTransform
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from app.window import BOB_AMPLITUDE, BOB_PADDING, WALK_SPEED, CharacterWindow


class CharacterWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.window = CharacterWindow()
        self.window.show()
        self.window._timer.stop()
        self.app.processEvents()

    def tearDown(self):
        self.window._menu.close()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_idle_bobs_inside_a_stationary_window(self):
        window = self.window
        window._remaining = 8
        position = window.pos()
        offsets = []
        for _ in range(240):
            window._advance(0.01)
            offsets.append(window._bob_offset)
            self.assertEqual(window.pos(), position)
            top = BOB_PADDING + window._bob_offset
            self.assertGreaterEqual(top, 0)
            self.assertLessEqual(top + window._character_size.height(), window.height())
        self.assertGreater(max(offsets) - min(offsets), 2)
        self.assertLessEqual(max(offsets) - min(offsets), 2 * BOB_AMPLITUDE)

    def test_walk_speed_is_consistent_across_tick_intervals(self):
        window = self.window
        area = window._available_area()
        start = QPoint(area.center().x() - window.width() // 2, area.top() + 30)
        for direction in (-1, 1):
            for interval in (0.01, 0.025):
                window.move(start)
                window._start_walk()
                window._direction = direction
                window._remaining = 5
                for _ in range(round(1 / interval)):
                    window._advance(interval)
                self.assertEqual(window.pos(), start + QPoint(round(direction * WALK_SPEED), 0))

    def test_random_idle_and_walk_periods_alternate(self):
        window = self.window
        with patch('app.window.random.uniform', side_effect=[4.5, 2.5, 7.0]), \
             patch('app.window.random.choice', return_value=-1) as choose:
            window._start_idle()
            self.assertEqual(window._remaining, 4.5)
            window._remaining = 0.01
            window._advance(0.02)
            self.assertTrue(window._walking)
            self.assertEqual(window._remaining, 2.5)
            self.assertEqual(window._direction, -1)
            choose.assert_called_once_with((-1, 1))
            window._remaining = 0.01
            window._advance(0.02)
            self.assertFalse(window._walking)
            self.assertEqual(window._remaining, 7.0)

    def test_both_edges_reverse_without_leaving_available_area(self):
        window = self.window
        area = window._available_area()
        for x, direction in ((area.left(), -1), (area.right() + 1 - window.width(), 1)):
            window.move(x, area.bottom() + 1 - window.height())
            window._start_walk()
            window._direction = direction
            window._advance(0.02)
            self.assertEqual(window._direction, -direction)
            self.assertTrue(area.contains(window.geometry()))
            for _ in range(20):
                window._advance(0.02)
                self.assertTrue(area.contains(window.geometry()))

    def test_nearest_monitor_recovery_and_geometry_changes(self):
        window = self.window
        left_area = QRect(-1280, -200, 1280, 960)
        primary_area = QRect(0, 0, 1920, 1040)
        left = SimpleNamespace(availableGeometry=lambda: left_area)
        primary = SimpleNamespace(availableGeometry=lambda: primary_area)
        with patch.object(QApplication, 'screenAt', return_value=None), \
             patch.object(QApplication, 'screens', return_value=[primary, left]):
            window.move(-1600, -300)
            window._resume_behavior()
            self.assertTrue(left_area.contains(window.geometry()))
        # Simulate monitor removal or a work-area reduction, e.g. a taskbar move.
        with patch.object(window, '_available_area', return_value=primary_area):
            window._advance(0.016)
            self.assertTrue(primary_area.contains(window.geometry()))
        reduced = QRect(40, 50, 600, 400)
        window.move(900, 900)
        with patch.object(window, '_available_area', return_value=reduced):
            window._advance(0.016)
            self.assertTrue(reduced.contains(window.geometry()))

    def test_drag_pauses_behavior_and_release_recovers_offscreen(self):
        window = self.window
        window._start_walk()
        local = QPoint(50, 75)
        start = window.pos()
        global_start = window.mapToGlobal(local)
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=local)
        before = (window._remaining, window._bob_offset, window.pos())
        window._timer.start()
        QTest.qWait(100)
        self.assertEqual((window._remaining, window._bob_offset, window.pos()), before)
        delta = QPoint(-50, -30)
        self.app.sendEvent(window, QMouseEvent(
            QEvent.Type.MouseMove, QPointF(local + delta), QPointF(global_start + delta),
            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        ))
        self.assertEqual(window.pos(), start + delta)
        area = window._available_area()
        window.move(area.right(), area.bottom())
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=local)
        self.assertIsNone(window._drag_offset)
        self.assertFalse(window._walking)
        self.assertTrue(window._available_area().contains(window.geometry()))
        self.assertGreaterEqual(window._remaining, 3)
        remaining = window._remaining
        QTest.qWait(60)
        self.assertLess(window._remaining, remaining)

    def test_facing_mirrors_rendering_without_mutating_source(self):
        window = self.window
        original = window._character.toImage()
        window._direction = 1
        right = window.grab().toImage()
        window._direction = -1
        left = window.grab().toImage()
        expected = right.transformed(QTransform().scale(-1, 1))
        # Raster rounding can differ by a few channel levels at antialiased edges.
        differences = [abs(a - b) for a, b in zip(bytes(left.constBits()), bytes(expected.constBits()))]
        self.assertLess(sum(differences) / len(differences), 1)
        self.assertNotEqual(left, right)
        self.assertEqual(window._character.toImage(), original)
        window._direction = 1
        self.assertEqual(window.grab().toImage(), right)
        self.assertEqual(right.pixelColor(0, 0).alpha(), 0)

    def test_menu_pauses_and_exit_stops_timer(self):
        window = self.window
        local = QPoint(50, 75)
        self.app.sendEvent(window, QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse, local, window.mapToGlobal(local),
        ))
        self.assertTrue(window._menu.isVisible())
        before = (window._remaining, window.pos(), window._bob_offset)
        window._timer.start()
        QTest.qWait(80)
        self.assertEqual((window._remaining, window.pos(), window._bob_offset), before)
        spy = QSignalSpy(window._timer.timeout)
        action = window._menu.actions()[0]
        self.assertEqual(action.text(), 'Exit')
        QTest.mouseClick(window._menu, Qt.MouseButton.LeftButton,
                         pos=window._menu.actionGeometry(action).center())
        self.assertFalse(window.isVisible())
        self.assertFalse(window._timer.isActive())
        count = spy.count()
        QTest.qWait(50)
        self.assertEqual(spy.count(), count)

    def test_real_timer_transitions_and_caps_long_stalls(self):
        window = self.window
        window._remaining = 0.01
        window._clock.restart()
        window._timer.start()
        QTest.qWait(100)
        self.assertTrue(window._walking)
        window._remaining = 0.01
        QTest.qWait(100)
        self.assertFalse(window._walking)
        window._timer.stop()
        window._start_walk()
        start = window.pos()
        with patch.object(window, '_clock', SimpleNamespace(restart=lambda: 60000)):
            window._tick()
        self.assertLessEqual(abs(window.x() - start.x()), round(WALK_SPEED * 0.05))

    def test_missing_image_still_warns_and_animates_placeholder(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertLogs('app.window', level='WARNING'):
                fallback = CharacterWindow(Path(folder) / 'missing.png')
            try:
                self.assertFalse(fallback._character.isNull())
                fallback._advance(0.02)
                self.assertGreater(fallback._bob_offset, 0)
            finally:
                fallback.close()
                self.assertFalse(fallback._timer.isActive())


if __name__ == '__main__':
    unittest.main()
