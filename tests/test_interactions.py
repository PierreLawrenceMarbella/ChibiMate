"""Native Qt interaction checks for clicks, bubbles, pause, and cleanup."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QContextMenuEvent, QImage, QMouseEvent, QPainter
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from app.dialogue import BUBBLE_MILLISECONDS
from app.window import CharacterWindow
from app.preferences import CharacterPreferences
from app.sprites import AnimationState, DANCE_SECONDS


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
        for widget in self.app.topLevelWidgets():
            widget.close()
            widget.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
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

    def enable_dance(self):
        # Colored test rectangles exercise playback without adding character art.
        root = Path(self.temp.name) / 'sprites'
        folder = root / 'dance'
        folder.mkdir(parents=True)
        for number, color in enumerate(('red', 'blue'), 1):
            image = QImage(60, 100, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.fillRect(10, 10, 40, 80, QColor(color))
            painter.end()
            self.assertTrue(image.save(str(folder / f'dance_{number:02d}.png')))
        self.window._default_sprite_path = root
        self.window.restore_default()

    def test_dance_menu_requires_assets_and_restores_suspended_walk(self):
        window = self.window
        self.open_menu()
        self.assertFalse(window._dance_action.isEnabled())
        window._menu.close()
        self.assertFalse(window.start_dance())
        self.enable_dance()
        window._start_walk()
        before = window.pos()
        remaining = window._remaining
        self.click_menu_action(window._dance_action)
        self.assertEqual(window.animation_state, AnimationState.DANCING)
        self.assertEqual(window._sprites.frame_key, ('dance', 0))
        window._advance(0.125)
        self.assertEqual(window._sprites.frame_key, ('dance', 1))
        self.assertEqual(window.pos(), before)
        self.assertEqual(window._remaining, remaining)
        random_remaining = window._behavior.remaining
        window._advance(0.1)
        self.assertEqual(window._behavior.remaining, random_remaining)
        self.assertFalse(window.trigger_random_reaction())
        self.open_menu()
        self.assertTrue(window._reaction_action.isEnabled())
        self.assertTrue(window._dance_action.isEnabled())
        snapshot = (window.pos(), window._sprites._dance_remaining)
        window._timer.start()
        QTest.qWait(80)
        self.assertEqual((window.pos(), window._sprites._dance_remaining), snapshot)
        window._timer.stop()
        window._menu.close()
        window._advance(DANCE_SECONDS)
        self.assertEqual(window.animation_state, AnimationState.WALKING)
        window._advance(0.1)
        self.assertNotEqual(window.pos(), before)

    def test_pause_and_drag_during_dance_preserve_user_control(self):
        self.enable_dance()
        window = self.window
        window._start_walk()
        self.assertTrue(window.start_dance())
        self.click_menu_action(window._pause_action)
        self.assertTrue(window._movement_paused)
        self.assertEqual(window.animation_state, AnimationState.DANCING)
        window._advance(DANCE_SECONDS)
        self.assertEqual(window.animation_state, AnimationState.IDLE)
        self.assertTrue(window.start_dance())
        local = QPoint(30, 50)
        start = window.mapToGlobal(local)
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=local)
        delta = QPoint(-40, -20)
        self.app.sendEvent(window, QMouseEvent(
            QEvent.Type.MouseMove, QPointF(local + delta), QPointF(start + delta),
            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        ))
        self.assertEqual(window.animation_state, AnimationState.DRAGGING)
        self.assertEqual(window._sprites._dance_remaining, 0)
        before = window.pos()
        window._advance(0.5)
        self.assertEqual(window.pos(), before)
        self.assertFalse(window.start_dance())  # Dragging takes priority over commands.
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=local)
        self.assertEqual(window.animation_state, AnimationState.IDLE)
        self.assertTrue(window._movement_paused)
        self.assertFalse(window._bubble.isVisible())
        self.assertEqual(window._reaction_remaining, 0)

    def test_character_switch_and_resize_during_dance_keep_preferences_and_identity(self):
        self.enable_dance()
        window = self.window
        self.assertTrue(window.start_dance())
        window.set_character_size(200)
        self.assertEqual(window.animation_state, AnimationState.DANCING)
        self.assertEqual(window._character_size.height(), 200)
        self.assertTrue(window._available_area().contains(window.geometry()))
        source = Path(self.temp.name) / 'custom.png'
        image = QImage(60, 100, QImage.Format.Format_ARGB32)
        image.fill(QColor('green'))
        self.assertTrue(image.save(str(source)))
        with patch('app.window.QFileDialog.getOpenFileName', return_value=(str(source), '')):
            window.change_character()
        self.assertEqual(window.animation_state, AnimationState.IDLE)
        self.assertEqual(set(window._sprites.frames), {'static'})
        self.assertFalse(window._dance_action.isEnabled())
        self.assertFalse(window.start_dance())
        self.assertEqual(window._preferences.height, 200)
        self.assertEqual(window._preferences.load_character()[0], window._custom_file)
        window.restore_default()
        self.assertEqual(window._character_height, 200)
        self.assertTrue(window._dance_action.isEnabled())
        self.assertEqual(window._preferences.load_character(), ('', None))

    def test_exit_during_dance_stops_existing_timers(self):
        self.enable_dance()
        self.assertTrue(self.window.start_dance())
        self.window._timer.start()
        self.click_menu_action(self.window._menu.actions()[-1])
        self.assertFalse(self.window.isVisible())
        self.assertFalse(self.window._timer.isActive())
        self.assertFalse(self.window._bubble._timer.isActive())

    def test_happy_and_surprised_click_poses_expire_into_idle(self):
        window = self.window
        for name in ('happy', 'surprised'):
            with patch.object(window._reaction_random, 'choice', side_effect=[name, 'Hello!']):
                QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=QPoint(50, 75))
            self.assertEqual(window.animation_state, AnimationState.REACTING)
            self.assertEqual(window._sprites.frame_key, (name, 0))
            self.assertTrue(1 <= window._reaction_remaining <= 2)
            self.assertFalse(window.start_dance())
            window._advance(2.1)
            self.assertEqual(window.animation_state, AnimationState.IDLE)
            self.assertEqual(window._sprites.frame_key, ('idle', 0))
            window._bubble.dismiss()

    def test_temporary_expression_defers_automatic_walk_until_finished(self):
        window = self.window
        window._remaining = 0.01
        self.assertTrue(window.show_expression('happy', 1.2))
        window._advance(0.5)
        self.assertEqual(window.animation_state, AnimationState.REACTING)
        self.assertFalse(window._walking)
        self.assertFalse(window.trigger_random_reaction())
        window._advance(0.8)
        self.assertEqual(window.animation_state, AnimationState.IDLE)
        window._advance(0.02)
        self.assertEqual(window.animation_state, AnimationState.WALKING)

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
        window._behavior.remaining = 0
        window._advance(0.05)
        self.assertFalse(window._bubble.isVisible())
        window._start_idle()
        with patch.object(window._behavior.random, 'choices', return_value=['happy']):
            window._advance(0.05)
        self.assertTrue(window._bubble.isVisible())
        self.assertTrue(20 <= window._behavior.remaining <= 45)
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
        self.assertTrue(window._reaction_action.isEnabled())  # Explicit actions have priority.
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
        expired = QSignalSpy(bubble._timer.timeout)
        bubble._timer.start(30)
        self.assertTrue(expired.wait(1000))
        self.assertFalse(bubble.isVisible())
        self.assertFalse(bubble._timer.isActive())


if __name__ == '__main__':
    unittest.main()
