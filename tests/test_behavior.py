"""Deterministic offline scheduling and Qt behavior priority checks."""

import tempfile
import unittest
from pathlib import Path
from random import Random
from unittest.mock import patch

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QImage, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.behavior import BehaviorController, FREQUENCIES, Priority, SIT_AFTER_SECONDS, SIT_IDLE_SECONDS
from app.preferences import CharacterPreferences
from app.sprites import AnimationState
from app.window import CharacterWindow


class ControllerTests(unittest.TestCase):
    def test_choices_use_available_art_and_do_not_repeat_poses(self):
        controller = BehaviorController(rng=Random(7))
        previous = None
        for _ in range(200):
            controller.remaining = 0
            name = controller.choose_action({"happy", "shy", "static"})
            self.assertIn(name, {"idle", "happy", "shy"})
            self.assertNotEqual(name, previous)
            previous = name
        controller.remaining = 0
        self.assertEqual(controller.choose_action({"static"}), "idle")

    def test_run_is_rare_and_never_back_to_back(self):
        controller = BehaviorController(rng=Random(1))
        motions = [controller.choose_motion({"walk", "running"}) for _ in range(2000)]
        self.assertGreater(motions.count("running"), 0)
        self.assertLess(motions.count("running"), len(motions) * 0.2)
        self.assertNotIn(("running", "running"), list(zip(motions, motions[1:])))
        for _ in range(20):
            self.assertEqual(controller.choose_motion({"static"}), "walk")

    def test_frequencies_and_no_backlog_after_a_long_wait(self):
        intervals = []
        for frequency in FREQUENCIES:
            controller = BehaviorController(frequency=frequency, rng=Random(5))
            intervals.append(controller.remaining)
            controller.advance(10000, idle=False)
            self.assertEqual(controller.remaining, 0)
            controller.choose_action({"happy"})
            self.assertIsNone(controller.choose_action({"happy"}))
            controller.configure(False, frequency)
            before = (controller.remaining, controller.quiet_seconds, controller.idle_seconds)
            controller.advance(10000, idle=True)
            self.assertEqual((controller.remaining, controller.quiet_seconds, controller.idle_seconds), before)
            self.assertIsNone(controller.choose_action({"sleeping", "happy"}))
        self.assertGreater(intervals[0], intervals[1])
        self.assertGreater(intervals[1], intervals[2])

    def test_rest_requires_inactivity_and_its_own_sprites(self):
        controller = BehaviorController(rng=Random(3))
        choices = []
        def pick(names, **kwargs):
            choices.append(names)
            return [names[-1]]
        with patch.object(controller.random, "choices", side_effect=pick):
            controller.remaining = 0
            controller.choose_action({"sitting"})
            self.assertNotIn("sitting", choices[-1])
            controller.quiet_seconds = SIT_AFTER_SECONDS
            controller.idle_seconds = SIT_IDLE_SECONDS
            controller.remaining = 0
            self.assertEqual(controller.choose_action({"sitting"}), "sitting")
            self.assertEqual(controller.idle_seconds, 0)
        controller.quiet_seconds = controller.sleep_after
        self.assertEqual(controller.choose_action({"sleeping"}), "sleeping")
        self.assertNotEqual(controller.choose_action({"static"}), "sleeping")


class BehaviorWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        image = QImage(40, 80, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.magenta)
        self.character = self.root / "character.png"
        image.save(str(self.character))
        self.pack = self.root / "pack"
        for name in ("idle", "walk", "running", "sitting", "sleeping", "waving", "happy", "shy", "dance"):
            folder = self.pack / name
            folder.mkdir(parents=True)
            image.save(str(folder / "pose.png"))
        self.prefs = CharacterPreferences(self.root / "data")
        self.window = CharacterWindow(self.character, self.pack, self.prefs)
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

    def test_manual_over_reaction_over_autonomous_and_drag_over_all(self):
        w = self.window
        self.assertTrue(w.perform_action("sitting", automatic=True))
        self.assertEqual(w.behavior_priority, Priority.AUTONOMOUS)
        self.assertTrue(w.trigger_random_reaction(name="happy"))
        self.assertEqual(w.behavior_priority, Priority.REACTION)
        self.assertFalse(w.perform_action("waving", automatic=True))
        self.assertTrue(w.perform_action("dance"))
        self.assertEqual(w.behavior_priority, Priority.MANUAL)
        self.assertFalse(w.trigger_random_reaction(name="happy"))
        deadline = w._behavior.remaining
        w._advance(0.5)
        self.assertEqual(w._behavior.remaining, deadline)
        local = QPoint(10, 20)
        start = w.mapToGlobal(local)
        QTest.mousePress(w, Qt.MouseButton.LeftButton, pos=local)
        delta = QPoint(-40, -20)
        self.app.sendEvent(w, QMouseEvent(
            QEvent.Type.MouseMove, QPointF(local + delta), QPointF(start + delta),
            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        ))
        self.assertEqual(w.behavior_priority, Priority.DRAGGING)
        self.assertFalse(w.perform_action("happy"))
        self.assertFalse(w._sprites.action_active)
        QTest.mouseRelease(w, Qt.MouseButton.LeftButton, pos=local)
        self.assertEqual(w.behavior_priority, Priority.IDLE)
        self.assertFalse(w._bubble.isVisible())

    def test_sleep_latches_until_click_or_wake_then_starts_fresh_idle(self):
        w = self.window
        w._behavior.quiet_seconds = w._behavior.sleep_after
        w._advance(0.01)
        self.assertEqual(w.animation_state, AnimationState.SLEEPING)
        before = w.pos()
        for _ in range(20):
            w._advance(10)
        self.assertEqual(w.animation_state, AnimationState.SLEEPING)
        self.assertEqual(w.pos(), before)
        self.assertFalse(w._walking)
        QTest.mouseClick(w, Qt.MouseButton.LeftButton, pos=QPoint(10, 20))
        self.assertEqual(w.animation_state, AnimationState.IDLE)
        self.assertEqual(w._behavior.quiet_seconds, 0)
        self.assertFalse(w._bubble.isVisible())
        self.assertTrue(w.perform_action("sleeping"))
        wake = next(action for action in w._menu.actions() if "Wake Up" in action.text())
        wake.trigger()
        self.assertEqual(w.animation_state, AnimationState.IDLE)
        self.assertGreater(w._behavior.remaining, 0)

    def test_pause_freezes_autonomous_action_and_deadlines_but_allows_manual(self):
        w = self.window
        w.perform_action("sitting", duration=4, automatic=True)
        w._advance(1)
        w._toggle_movement()
        before = (w._sprites._action_remaining, w._behavior.remaining, w.pos())
        w._advance(1000)
        self.assertEqual((w._sprites._action_remaining, w._behavior.remaining, w.pos()), before)
        w._toggle_movement()
        w._advance(1)
        self.assertAlmostEqual(w._sprites._action_remaining, 2)
        w._toggle_movement()
        self.assertTrue(w.trigger_random_reaction(name="happy", explicit=True))
        w._advance(3)
        self.assertEqual(w.animation_state, AnimationState.IDLE)
        self.assertFalse(w._walking)
        deadline = w._behavior.remaining
        w._advance(1000)
        self.assertEqual(w._behavior.remaining, deadline)

    def test_disable_stops_autonomy_and_manual_walk_remains_finite(self):
        w = self.window
        w.perform_action("waving", automatic=True)
        w.set_behavior_options(enabled=False)
        self.assertEqual(w.animation_state, AnimationState.IDLE)
        before = w.pos()
        w._advance(1000)
        self.assertEqual(w.pos(), before)
        self.assertFalse(w._bubble.isVisible())
        self.assertFalse(w.perform_action("sitting", automatic=True))
        self.assertTrue(w.perform_action("walk"))
        self.assertEqual(w.behavior_priority, Priority.MANUAL)
        w._remaining = 0.01
        w._advance(0.02)
        self.assertEqual(w.animation_state, AnimationState.IDLE)
        w._advance(1000)
        self.assertFalse(w._walking)

    def test_sleep_stays_asleep_when_disabled_or_paused(self):
        w = self.window
        w.perform_action("sleeping", automatic=True)
        w.set_behavior_options(enabled=False, paused=True)
        w._advance(1000)
        self.assertEqual(w.animation_state, AnimationState.SLEEPING)
        QTest.mouseClick(w, Qt.MouseButton.LeftButton, pos=QPoint(10, 20))
        w._advance(1000)
        self.assertEqual(w.animation_state, AnimationState.IDLE)
        self.assertTrue(w._movement_paused)

    def test_preferences_menu_restore_and_invalid_values(self):
        w = self.window
        w._frequency_actions["Low"].trigger()
        w._autonomy_action.trigger()
        w._pause_action.trigger()
        fresh = CharacterPreferences(self.prefs.directory)
        self.assertEqual(fresh.behavior_options, (False, "Low", True))
        reopened = CharacterWindow(self.character, self.pack, fresh)
        try:
            self.assertFalse(reopened.autonomous_active)
            self.assertTrue(reopened._frequency_actions["Low"].isChecked())
            self.assertEqual(reopened._pause_action.text(), "Resume Movement")
            self.assertEqual(reopened._autonomy_action.text(), "Resume Autonomous Behavior")
        finally:
            reopened.close()
            reopened.deleteLater()
        fresh.settings.setValue("behavior/frequency", ["invalid"])
        self.assertEqual(fresh.behavior_options[1], "Normal")
        before = (w._behavior.enabled, w._behavior.frequency, w._movement_paused)
        with patch.object(w._preferences, "save_behavior_options", side_effect=OSError("read only")), patch.object(w, "_show_character_error"):
            w.set_behavior_options(enabled=True, frequency="High", paused=False)
        self.assertEqual((w._behavior.enabled, w._behavior.frequency, w._movement_paused), before)

    def test_custom_static_switch_during_sleep_has_no_foreign_sprites(self):
        w = self.window
        w.perform_action("sleeping")
        filename, character = self.prefs.import_character(self.character, 150)
        w._apply_character(character, filename)
        self.assertEqual(w.animation_state, AnimationState.IDLE)
        self.assertEqual(set(w._sprites.frames), {"static"})
        w._behavior.quiet_seconds = 1000
        w._behavior.remaining = 0
        w._advance(0.01)
        self.assertFalse(w._sprites.action_active)
        self.assertFalse(w._bubble.isVisible())
        w._start_walk()
        self.assertEqual(w._sprites.frame_key, ("static", 0))
        self.assertFalse(w.perform_action("sleeping"))
        self.assertTrue(w.trigger_random_reaction(name="happy"))
        self.assertEqual(w._sprites.frame_key, ("static", 0))

    def test_no_new_timers_cleanup_and_autonomous_choices_wait_for_idle(self):
        w = self.window
        self.assertEqual(len(w.findChildren(QTimer)), 2)
        w._start_walk()
        w._behavior.remaining = 0
        w._advance(0.1)
        self.assertFalse(w._bubble.isVisible())
        w._start_idle()
        with patch.object(w._behavior.random, "choices", return_value=["waving"]):
            w._advance(0.01)
        self.assertEqual(w.animation_state, AnimationState.WAVING)
        w.close()
        self.assertTrue(all(not timer.isActive() for timer in w.findChildren(QTimer)))


if __name__ == "__main__":
    unittest.main()
