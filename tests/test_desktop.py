"""Local cursor/monitor simulations and native interaction priority checks."""

import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import QImage, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.behavior import Priority
from app.movement import EDGE_MARGIN, FOLLOW_GAP
from app.preferences import CharacterPreferences
from app.sprites import AnimationState
from app.window import CharacterWindow, RUN_SPEED


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "character.png"
        self.pack = self.root / "sprites"
        image = QImage(60, 100, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.red)
        image.save(str(self.source))
        for name in ("idle", "walk", "running", "peeking", "sitting", "sleeping", "waving", "dance", "happy"):
            folder = self.pack / name
            folder.mkdir(parents=True)
            image.fill(Qt.GlobalColor.red)
            image.save(str(folder / "pose_01.png"))
            if name in ("walk", "running"):
                image.fill(Qt.GlobalColor.blue)
                image.save(str(folder / "pose_02.png"))
        self.prefs = CharacterPreferences(self.root / "data")
        self.w = CharacterWindow(self.source, self.pack, self.prefs)
        self.w.show()
        self.w._timer.stop()
        self.area = QRect(-1200, -300, 1200, 850)
        self.area_mock = patch.object(self.w, "_available_area", return_value=self.area)
        self.area_mock.start()
        self.w.move(self.area.center() - self.w.rect().center())
        self.w._start_idle()

    def tearDown(self):
        self.area_mock.stop()
        for widget in self.app.topLevelWidgets():
            widget.close()
            widget.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.temp.cleanup()

    def follow(self, enabled=True):
        self.w.set_display_options(100, True, enabled)

    def test_follow_is_optional_independent_of_autonomy_and_stops_sampling(self):
        self.assertFalse(self.w._follow_cursor)
        self.w.set_behavior_options(enabled=False)
        with patch("app.window.QCursor.pos", side_effect=AssertionError("Cursor sampled while disabled")):
            self.w._advance(0.1)
        self.follow()
        start = self.w.pos()
        cursor = self.area.topLeft() + QPoint(40, 40)
        with patch("app.window.QCursor.pos", return_value=cursor) as sample:
            for _ in range(20):
                self.w._advance(0.02)
            self.assertGreater(sample.call_count, 0)
            self.assertLessEqual(sample.call_count, 9)
        self.assertNotEqual(self.w.pos(), start)
        self.assertLess(self.w.x(), start.x())
        self.assertLess(self.w.y(), start.y())
        self.assertEqual(self.w._direction, -1)
        self.follow(False)
        position = self.w.pos()
        with patch("app.window.QCursor.pos", side_effect=AssertionError("Sampling did not stop")):
            for _ in range(100):
                self.w._advance(0.05)
        self.assertEqual(self.w.pos(), position)

    def test_follow_eases_walk_run_idle_preserves_frames_and_standoff(self):
        self.follow()
        cursor = self.area.topLeft() + QPoint(30, 30)
        states, frames = set(), set()
        previous = self.w.pos()
        with patch("app.window.QCursor.pos", return_value=cursor):
            for _ in range(550):
                self.w._advance(0.05)
                delta = self.w.pos() - previous
                self.assertLessEqual(math.hypot(delta.x(), delta.y()), RUN_SPEED * 0.05 + 1.5)
                self.assertTrue(self.area.contains(self.w.geometry()))
                states.add(self.w.animation_state)
                frames.add(self.w._sprites.frame_key)
                previous = self.w.pos()
        self.assertTrue({AnimationState.RUNNING, AnimationState.WALKING, AnimationState.IDLE} <= states)
        self.assertTrue({("walk", 0), ("walk", 1), ("running", 0), ("running", 1)} <= frames)
        gap = math.hypot(self.w.width() / 2, self.w.height() / 2) + FOLLOW_GAP
        delta = QPointF(cursor) - (QPointF(self.w.pos()) + QPointF(self.w.width() / 2, self.w.height() / 2))
        self.assertAlmostEqual(math.hypot(delta.x(), delta.y()), gap, delta=3)
        self.assertFalse(self.w.geometry().contains(cursor))
        settled = self.w.pos()
        for offset in (QPoint(2, 1), QPoint(-2, -1), QPoint(0, 0)):
            with patch("app.window.QCursor.pos", return_value=cursor + offset):
                for _ in range(10):
                    self.w._advance(0.05)
            self.assertEqual(self.w.pos(), settled)

    def test_target_outside_monitor_is_clamped_and_does_not_jitter(self):
        self.follow()
        with patch("app.window.QCursor.pos", return_value=QPoint(3000, -1000)):
            for _ in range(600):
                self.w._advance(0.05)
                self.assertTrue(self.area.contains(self.w.geometry()))
            position = self.w.pos()
            for _ in range(30):
                self.w._advance(0.05)
                self.assertEqual(self.w.pos(), position)
        self.assertEqual(self.w.animation_state, AnimationState.IDLE)

    def test_manual_actions_pause_sleep_and_drag_override_following(self):
        self.follow()
        with patch("app.window.QCursor.pos", return_value=self.area.topLeft()):
            self.w._advance(0.05)
        self.assertTrue(self.w._following)
        self.assertTrue(self.w.perform_action("waving"))
        before = self.w.pos()
        with patch("app.window.QCursor.pos", side_effect=AssertionError("Manual action interrupted")):
            self.w._advance(0.5)
        self.assertEqual(self.w.pos(), before)
        self.w.perform_action("sleeping")
        with patch("app.window.QCursor.pos", side_effect=AssertionError("Sleep interrupted")):
            self.w._advance(10)
        self.w.return_to_idle()
        self.w.set_behavior_options(paused=True)
        with patch("app.window.QCursor.pos", side_effect=AssertionError("Pause ignored")):
            self.w._advance(1)
        self.w.set_behavior_options(paused=False)
        local = QPoint(10, 20)
        start = self.w.mapToGlobal(local)
        QTest.mousePress(self.w, Qt.MouseButton.LeftButton, pos=local)
        delta = QPoint(40, -20)
        self.app.sendEvent(self.w, QMouseEvent(
            QEvent.Type.MouseMove, QPointF(local + delta), QPointF(start + delta),
            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        self.assertEqual(self.w.behavior_priority, Priority.DRAGGING)
        with patch("app.window.QCursor.pos", side_effect=AssertionError("Drag interrupted")):
            self.w._advance(1)
        QTest.mouseRelease(self.w, Qt.MouseButton.LeftButton, pos=local)
        with patch("app.window.QCursor.pos", return_value=self.area.topLeft()):
            self.w._advance(0.05)
        self.assertTrue(self.w._following)

    def test_edge_approach_plays_pose_and_returns_to_idle_fully_visible(self):
        for name in ("peeking", "sitting"):
            self.w.return_to_idle()
            self.w.move(self.area.left() + 100, self.area.top() + 100)
            before = self.w.pos()
            self.assertTrue(self.w.approach_edge(name))
            self.assertEqual(self.w.pos(), before)
            self.assertEqual(self.w.behavior_priority, Priority.MANUAL)
            for _ in range(200):
                self.w._advance(0.05)
                self.assertTrue(self.area.contains(self.w.geometry()))
                if self.w._sprites.action_active:
                    break
            self.assertEqual(self.w._sprites.frame_key, (name, 0))
            self.assertAlmostEqual(self.w.x(), self.area.left() + EDGE_MARGIN, delta=1)
            self.assertEqual(self.w.y(), before.y())
            self.w._advance(10)
            self.assertEqual(self.w.animation_state, AnimationState.IDLE)
            self.assertFalse(self.w._manual_movement)
            self.assertIsNone(self.w._edge_action)

    def test_optional_automatic_edges_and_manual_override_cancel_journey(self):
        self.assertFalse(self.w._edge_behaviors)
        self.w._behavior.edge_remaining = 0
        self.w._advance(0.05)
        self.assertIsNone(self.w._edge_action)
        self.w.set_edge_behaviors(True)
        self.w._behavior.edge_remaining = 0
        self.w._advance(0.05)
        self.assertIn(self.w._edge_action, ("peeking", "sitting"))
        self.assertEqual(self.w.behavior_priority, Priority.AUTONOMOUS)
        self.w.perform_action("happy")
        self.assertIsNone(self.w._edge_action)
        self.assertEqual(self.w.animation_state, AnimationState.HAPPY)
        self.w.return_to_idle()
        self.w.approach_edge("peeking", automatic=True)
        self.w.set_edge_behaviors(False)
        self.assertIsNone(self.w._edge_action)
        self.assertFalse(self.w._walking)

    def test_missing_sprites_static_follow_and_character_switch_cancel_edge(self):
        self.w.approach_edge()
        filename, image = self.prefs.import_character(self.source, 150)
        self.w._apply_character(image, filename)
        self.assertIsNone(self.w._edge_action)
        self.assertFalse(self.w.approach_edge())
        self.w._update_menu()
        self.assertFalse(self.w._peek_action.isEnabled())
        self.follow()
        with patch("app.window.QCursor.pos", return_value=self.area.topLeft()):
            for _ in range(20):
                self.w._advance(0.05)
        self.assertEqual(set(self.w._sprites.frames), {"static"})
        self.assertEqual(self.w._sprites.frame_key, ("static", 0))
        self.assertFalse(self.w._running)

    def test_preferences_resume_controls_unique_actions_and_cleanup(self):
        self.follow()
        self.w.set_edge_behaviors(True)
        self.w.set_behavior_options(enabled=False, frequency="High", paused=True)
        reopened = CharacterWindow(self.source, self.pack, CharacterPreferences(self.prefs.directory))
        self.assertTrue(reopened._follow_cursor)
        self.assertTrue(reopened._edge_behaviors)
        self.assertEqual(reopened._behavior.frequency, "High")
        reopened._autonomy_action.trigger()
        self.assertFalse(reopened._follow_cursor)
        self.assertTrue(reopened.autonomous_active)
        self.assertFalse(reopened._movement_paused)
        self.assertFalse(CharacterPreferences(self.prefs.directory).display_options[2])
        self.assertEqual(reopened.animation_state, AnimationState.IDLE)
        def labels(menu):
            result = []
            for action in menu.actions():
                if action.menu():
                    result.extend(labels(action.menu()))
                elif not action.isSeparator():
                    result.append(action.text().split(" (")[0])
            return result
        names = labels(reopened._menu)
        for name in ("Sit", "Sleep", "Wave", "Dance", "Peek", "Follow Cursor"):
            self.assertEqual(names.count(name), 1)
        reopened.close()
        self.assertEqual(len(reopened.findChildren(QTimer)), 2)
        self.assertTrue(all(not timer.isActive() for timer in reopened.findChildren(QTimer)))

    def test_resize_and_changed_work_area_retarget_without_hiding(self):
        self.w.approach_edge()
        self.w._advance(0.1)
        self.w.set_character_size(200)
        self.area.setRect(-1000, -100, 800, 600)
        for _ in range(100):
            self.w._advance(0.05)
            self.assertTrue(self.area.contains(self.w.geometry()))
        self.area.setRect(-1000, -100, 100, 120)
        self.w._advance(0.05)
        self.assertTrue(self.area.contains(self.w.geometry()))
        self.assertEqual(self.w._character_height, 200)


if __name__ == "__main__":
    unittest.main()
