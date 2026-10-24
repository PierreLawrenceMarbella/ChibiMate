"""Small, timer-independent movement helpers in Qt logical coordinates."""

import math

from PySide6.QtCore import QPointF, QRect, QSize

RESPONSE = 10.0
FOLLOW_GAP = 28.0
FOLLOW_HYSTERESIS = 14.0
CURSOR_SAMPLE_SECONDS = 0.05
EDGE_MARGIN = 12


def clamp_position(position: QPointF, area: QRect, size: QSize) -> QPointF:
    return QPointF(
        max(area.left(), min(position.x(), area.right() + 1 - size.width())),
        max(area.top(), min(position.y(), area.bottom() + 1 - size.height())),
    )


def step_towards(position: QPointF, velocity: QPointF, target: QPointF,
                 speed: float, elapsed: float) -> tuple[QPointF, QPointF]:
    """Ease speed, brake near the target, and never overshoot either axis."""
    delta = target - position
    distance = math.hypot(delta.x(), delta.y())
    if distance < 0.5:
        return QPointF(target), QPointF()
    desired = delta * (min(speed, distance * 4) / distance)
    decay = math.exp(-RESPONSE * elapsed)
    # Integrate the eased velocity, keeping travel consistent across tick rates.
    step = desired * elapsed + (velocity - desired) * ((1 - decay) / RESPONSE)
    velocity = desired + (velocity - desired) * decay
    result = position + step
    for axis, set_axis in (("x", "setX"), ("y", "setY")):
        remaining = getattr(delta, axis)()
        travel = getattr(step, axis)()
        if remaining * travel < 0:  # A changed target must not cause a backwards lurch.
            getattr(result, set_axis)(getattr(position, axis)())
            getattr(velocity, set_axis)(0)
        elif abs(travel) >= abs(remaining):
            getattr(result, set_axis)(getattr(target, axis)())
            getattr(velocity, set_axis)(0)
    return result, velocity
