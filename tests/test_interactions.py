"""Native Qt interaction checks for clicks, bubbles, pause, and cleanup."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QContextMenuEvent, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.dialogue import BUBBLE_MILLISECONDS
from app.window import CharacterWindow
from app.preferences import CharacterPreferences


class InteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.window = CharacterWindow(preferences=CharacterPreferences(Path(self.temp.name)))
        self.window.show()
        self.window._timer.stop()
        self.app.processEvents()

    def tearDown(self):
        self.window._menu.close()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def trigger(self, kind='happy'):
        with patch.object(self.window._reaction_random, 'choice', side_effect=[kind, 'Hehe~!']):
            return self.window.trigger_random_reaction()

    def open_menu(self):
        window = self.window
        local = QPoint(50, 75)
        self.app.sendEvent(window, QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse, local, window.mapToGlobal(local),
        ))
        self.assertTrue(window._menu.isVisible())

    def click_menu_action(self, action):
        self.open_menu()
        QTest.mouseClick(self.window._menu, Qt.MouseButton.LeftButton,
                         pos=self.window._menu.actionGeometry(action).center())

    def test_click_reacts_once_then_resumes_walking(self):
        window = self.window
        window._start_walk()
        before = window.pos()
        duration_before = window._remaining
        with patch.object(window._reaction_random, 'choice', side_effect=['happy', 'Yay!']):
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=QPoint(50, 75))
        self.assertEqual(window._sprites.frame_key, ('happy', 0))
        self.assertTrue(window._bubble.isVisible())
        self.assertTrue(1 <= window._reaction_remaining <= 3)
        self.assertEqual(window._bubble._timer.interval(), BUBBLE_MILLISECONDS)
        remaining = window._reaction_remaining
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=QPoint(50, 75))
        self.assertEqual(window._reaction_remaining, remaining)
        window._advance(0.5)
        self.assertEqual(window.pos(), before)
        self.assertEqual(window._remaining, duration_before)
        window._advance(3)
        self.assertEqual(window._sprites.state, 'walk')
        self.assertEqual(window._sprites.frame_key[0], 'walk')
        # A lingering bubble still prevents stacking another reaction.
        self.assertFalse(window.trigger_random_reaction())
        window._advance(0.05)
        self.assertNotEqual(window.pos(), before)

    def test_missing_shy_sprite_keeps_exact_current_image(self):
        window = self.window
        window._start_walk()
        window._sprites.advance(0.3)
        before = window.grab().toImage()
        self.assertTrue(self.trigger('shy'))
        window._advance(0.5)
        self.assertEqual(window.grab().toImage(), before)
        self.assertTrue(window._bubble.isVisible())

    def test_jitter_counts_as_click_but_drag_and_return_do_not(self):
        window = self.window
        local = QPoint(50, 75)
        def move(delta):
            self.app.sendEvent(window, QMouseEvent(
                QEvent.Type.MouseMove, QPointF(local + delta), QPointF(start + delta),
                Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
            ))
        start = window.mapToGlobal(local)
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=local)
        move(QPoint(1, 1))
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=local)
        self.assertTrue(window._bubble.isVisible())
        start = window.mapToGlobal(local)
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=local)
        move(QPoint(40, -30))
        self.assertFalse(window._bubble.isVisible())
        move(QPoint(0, 0))
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=local)
        self.assertEqual(window._reaction_remaining, 0)
        self.assertFalse(window._bubble.isVisible())

    def test_random_idle_reaction_waits_for_idle_and_resets_interval(self):
        window = self.window
        window._start_walk()
        window._random_reaction_remaining = 0
        window._advance(0.05)
        self.assertFalse(window._bubble.isVisible())
        window._start_idle()
        window._advance(0.05)
        self.assertTrue(window._bubble.isVisible())
        self.assertTrue(20 <= window._random_reaction_remaining <= 45)
        bubble_text = window._bubble._text
        window._advance(0.05)
        self.assertEqual(window._bubble._text, bubble_text)

    def test_menu_pause_allows_clicks_and_dragging_then_resumes(self):
        window = self.window
        window._start_walk()
        self.click_menu_action(window._pause_action)
        self.assertTrue(window._movement_paused)
        self.assertEqual(window._pause_action.text(), 'Resume Movement')
        before = window.pos()
        for _ in range(100):
            window._advance(0.1)
        self.assertEqual(window.pos(), before)
        self.assertFalse(window._walking)
        self.assertTrue(self.trigger())
        window._cancel_reaction()
        # A drag remains available while movement is paused.
        local = QPoint(50, 75)
        start = window.mapToGlobal(local)
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=local)
        delta = QPoint(-40, -20)
        self.app.sendEvent(window, QMouseEvent(
            QEvent.Type.MouseMove, QPointF(local + delta), QPointF(start + delta),
            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        ))
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=local)
        self.assertEqual(window.pos(), before + delta)
        self.assertTrue(window._movement_paused)
        self.click_menu_action(window._pause_action)
        self.assertFalse(window._movement_paused)
        window._remaining = 0
        window._advance(0.02)
        self.assertTrue(window._walking)

    def test_menu_reaction_and_exit_clean_up_both_timers(self):
        window = self.window
        self.click_menu_action(window._reaction_action)
        self.assertTrue(window._bubble.isVisible())
        self.assertTrue(window._bubble._timer.isActive())
        self.open_menu()
        self.assertFalse(window._reaction_action.isEnabled())
        window._timer.start()
        action = window._menu.actions()[-1]
        QTest.mouseClick(window._menu, Qt.MouseButton.LeftButton,
                         pos=window._menu.actionGeometry(action).center())
        self.assertFalse(window.isVisible())
        self.assertFalse(window._bubble.isVisible())
        self.assertFalse(window._timer.isActive())
        self.assertFalse(window._bubble._timer.isActive())

    def test_bubble_fits_screen_edges_is_click_through_and_expires(self):
        bubble = self.window._bubble
        for area in (QRect(0, 0, 800, 600), QRect(-1280, -200, 1280, 960)):
            for anchor in (QRect(area.topLeft(), self.window.size()),
                           QRect(area.right() - 100, area.bottom() - 154, 100, 154)):
                bubble.show_message("I-It's not like I was waiting!", anchor, area, 3000)
                self.assertTrue(area.contains(bubble.geometry()))
                self.assertFalse(bubble.geometry().intersects(anchor))
        self.assertEqual(bubble.grab().toImage().pixelColor(0, 0).alpha(), 0)
        self.assertTrue(bubble.windowFlags() & Qt.WindowType.WindowTransparentForInput)
        self.assertTrue(bubble.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus)
        self.assertEqual(bubble.windowType(), Qt.WindowType.Tool)
        bubble._timer.start(30)
        QTest.qWait(70)
        self.assertFalse(bubble.isVisible())
        self.assertFalse(bubble._timer.isActive())


if __name__ == '__main__':
    unittest.main()
