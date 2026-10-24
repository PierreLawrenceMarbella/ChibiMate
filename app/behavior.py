"""Offline behavior decisions, advanced by the existing GUI timer only."""

from enum import IntEnum
from random import Random


class Priority(IntEnum):
    IDLE = 0
    AUTONOMOUS = 1
    REACTION = 2
    MANUAL = 3
    DRAGGING = 4


# Times are active seconds without interaction with the companion. Pauses,
# dialogs, dragging, and explicit actions do not consume these deadlines.
FREQUENCIES = {"Low": 1.7, "Normal": 1.0, "High": 0.65}
REACTION_INTERVAL = (20.0, 45.0)
SIT_AFTER_SECONDS = 30.0
SIT_IDLE_SECONDS = 12.0
SLEEP_INTERVAL = (90.0, 150.0)
REACTION_WEIGHTS = {"idle": 2, "waving": 3, "happy": 3, "shy": 2, "surprised": 1}


class BehaviorController:
    def __init__(self, enabled: bool = True, frequency: str = "Normal", rng: Random | None = None):
        self.random = rng if rng is not None else Random()
        self.enabled = enabled
        self.frequency = frequency if frequency in FREQUENCIES else "Normal"
        self.last_action = None
        self.last_motion = None
        self.reset()

    @property
    def interval_scale(self) -> float:
        return FREQUENCIES[self.frequency]

    def reset(self) -> None:
        self.quiet_seconds = 0.0
        self.idle_seconds = 0.0
        self.remaining = self.random.uniform(*REACTION_INTERVAL) * self.interval_scale
        self.sleep_after = self.random.uniform(*SLEEP_INTERVAL) * self.interval_scale

    def configure(self, enabled: bool, frequency: str) -> None:
        self.enabled = enabled
        self.frequency = frequency
        self.reset()

    def advance(self, elapsed: float, idle: bool) -> None:
        if not self.enabled:
            return
        self.quiet_seconds += elapsed
        if idle:
            self.idle_seconds += elapsed
        # A pending decision is a single deadline, never an accumulating queue.
        self.remaining = max(0.0, self.remaining - elapsed)

    def choose_action(self, available) -> str | None:
        if not self.enabled:
            return None
        if "sleeping" in available and self.quiet_seconds >= self.sleep_after:
            return "sleeping"
        if self.remaining > 0:
            return None
        self.remaining = self.random.uniform(*REACTION_INTERVAL) * self.interval_scale
        choices = {name: weight for name, weight in REACTION_WEIGHTS.items()
                   if name == "idle" or name in available}
        if ("sitting" in available and self.quiet_seconds >= SIT_AFTER_SECONDS * self.interval_scale
                and self.idle_seconds >= SIT_IDLE_SECONDS * self.interval_scale):
            choices["sitting"] = 5
        # Prefer another pose; even a pack with just happy alternates with idle.
        if self.last_action in choices and len(choices) > 1:
            del choices[self.last_action]
        name = self.random.choices(tuple(choices), weights=tuple(choices.values()), k=1)[0]
        self.last_action = name
        if name == "sitting":
            self.idle_seconds = 0.0
        return name

    def choose_motion(self, available) -> str:
        # Walking has a static PNG fallback. Running requires its own art and
        # cannot occur on consecutive outings; walking remains much more common.
        running = ("running" in available and self.last_motion != "running"
                   and self.random.random() < 0.12)
        self.last_motion = "running" if running else "walk"
        return self.last_motion
