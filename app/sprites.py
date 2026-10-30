"""Folder-based sprite playback, driven by the window's existing timer."""

import logging
import math
import re
from enum import Enum, auto
from pathlib import Path
from random import Random

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from app.actions import ACTION_FOLDERS, ACTION_SECONDS, normalize_action
from app.images import png_image, read_image_bytes
from app.resources import SPRITE_PATH


FRAME_RATES = {"walk": 8, "running": 12, "idle": 2, "dance": 8, "sleeping": 2}
BLINK_SECONDS = (3.0, 6.0)
DANCE_SECONDS = 6.0


class AnimationState(Enum):
    IDLE = auto()
    WALKING = auto()
    BLINKING = auto()
    REACTING = auto()
    DANCING = auto()
    DRAGGING = auto()
    RUNNING = auto()
    SITTING = auto()
    WAVING = auto()
    HAPPY = auto()
    SLEEPING = auto()
    SAD = auto()
    ANGRY = auto()
    SHY = auto()
    PEEKING = auto()


ACTION_STATES = {name: AnimationState[name.upper()] for name in ACTION_FOLDERS
                 if name.upper() in AnimationState.__members__}
ACTION_STATES.update(walk=AnimationState.WALKING, dance=AnimationState.DANCING,
                     blink=AnimationState.BLINKING, surprised=AnimationState.REACTING)


def _frame_order(path: Path) -> list:
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", path.name)]


def _visible_bounds(image: QImage) -> QRect:
    # Include every nonzero alpha value, including faint hair/antialiased edges.
    # A one-bit Qt alpha mask would discard pixels below its alpha threshold.
    rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
    alpha = bytes(rgba.constBits())[3::4]
    visible = alpha.rstrip(b"\0")
    if not visible:
        return QRect()
    width = image.width()
    top = (len(alpha) - len(alpha.lstrip(b"\0"))) // width
    bottom = (len(visible) - 1) // width
    left, right = width, 0
    for y in range(top, bottom + 1):
        row = alpha[y * width:(y + 1) * width]
        if row.strip(b"\0"):
            left = min(left, width - len(row.lstrip(b"\0")))
            right = max(right, len(row.rstrip(b"\0")))
    return QRect(left, top, right - left, bottom - top + 1)


def load_frames(root: Path | None, fallback_root: Path | None = None, cancelled=lambda: False) -> dict[str, list[QImage]]:
    """Prepare aligned QImages off the GUI thread; QPixmaps stay in the GUI."""
    folders_by_root = []
    for source_root in (root, fallback_root):
        try:
            folders = ({p.name.lower(): p for p in source_root.iterdir() if p.is_dir()}
                       if source_root is not None else {})
        except OSError:
            logging.getLogger(__name__).warning("Sprite folder unavailable; using available fallback frames.")
            folders = {}
        folders_by_root.append(folders)
    result = {}
    budgets = [{"pixels": 0, "loaded": 0} for _ in folders_by_root]
    for name, aliases in ACTION_FOLDERS.items():
        for root_index, folders in enumerate(folders_by_root):
            budget = budgets[root_index]
            frames, source_sizes, paths = [], [], []
            for alias in aliases:
                folder = folders.get(alias)
                if folder is not None:
                    try:
                        paths = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".png"), key=_frame_order)
                    except OSError:
                        logging.getLogger(__name__).warning("Sprite action folder unavailable: %s", name)
                    if paths:
                        break
            for path in paths:
                if cancelled():
                    raise InterruptedError("Pack loading cancelled.")
                if budget["loaded"] >= 256 or budget["pixels"] >= 24 * 1024 * 1024:
                    logging.getLogger(__name__).warning("Sprite budget reached; using available frames.")
                    break
                try:
                    image = png_image(read_image_bytes(path, 12 * 1024 * 1024),
                                      max_pixels=max(0, 24 * 1024 * 1024 - budget["pixels"]), max_side=2048)
                    budget["pixels"] += image.width() * image.height()
                    budget["loaded"] += 1
                except (OSError, ValueError):
                    logging.getLogger(__name__).warning("Skipping unreadable or oversized sprite in action: %s", name)
                    continue
                bounds = _visible_bounds(image)
                if not bounds.isEmpty():
                    source_sizes.append((image.width(), image.height()))
                    frames.append(image.copy(bounds).convertToFormat(QImage.Format.Format_RGBA8888))
            if frames:
                extents = {}
                for size, frame in zip(source_sizes, frames):
                    extents[size] = extents.get(size, QSize()).expandedTo(frame.size())
                for index, (size, frame) in enumerate(zip(source_sizes, frames)):
                    canvas = QImage(extents[size], QImage.Format.Format_RGBA8888)
                    canvas.fill(Qt.GlobalColor.transparent)
                    painter = QPainter(canvas)
                    painter.drawImage((canvas.width() - frame.width()) // 2,
                                      canvas.height() - frame.height(), frame)
                    painter.end()
                    frames[index] = canvas
                if all(frame == frames[0] for frame in frames[1:]):
                    frames = frames[:1]
                result[name] = frames
                break
    return result


class SpriteAnimation:
    def __init__(self, root: Path | None, fallback: QPixmap, max_size: QSize, motion_fps: int | None = None,
                 fallback_root: Path | None = None, prepared_frames: dict | None = None) -> None:
        self.motion_fps = motion_fps
        self.playback_speed = 1.0
        self.walking_fps: int | None = None
        self.frames: dict[str, list[QPixmap]] = {"static": [fallback]}
        prepared = load_frames(root, fallback_root) if prepared_frames is None else prepared_frames
        self.frames.update({name: [QPixmap.fromImage(image) for image in frames]
                            for name, frames in prepared.items()})

        self._random = Random()
        self._blink_remaining = self._random.uniform(*BLINK_SECONDS)
        self._reaction_frame: tuple[str, int] | None = None
        self._reaction_time = 0.0
        self._reaction_duration = 1.0
        self._temporary_remaining = 0.0
        self._temporary_duration = 0.0
        self._action_remaining = 0.0
        self._action_name: str | None = None
        self._hold_action = False
        self._walking = False
        self._running = False
        self.state = "idle"
        self._time = 0.0
        self._cache: dict[tuple[str, int], QPixmap] = {}
        self._dpr = 0.0
        self.set_max_size(max_size)

    def _fitted_size(self, source: QPixmap) -> QSize:
        size = source.size().scaled(self._max_size, Qt.AspectRatioMode.KeepAspectRatio)
        return size.expandedTo(QSize(1, 1))

    def set_max_size(self, max_size: QSize) -> None:
        max_size = max_size.expandedTo(QSize(1, 1))
        if getattr(self, "_max_size", None) == max_size:
            return
        self._max_size = max_size
        sizes = [self._fitted_size(frame) for frames in self.frames.values() for frame in frames]
        self.size = QSize(max(size.width() for size in sizes), max(size.height() for size in sizes))
        self._cache.clear()

    def _select(self, name: str) -> None:
        if self.state != name:
            self.state = name
            self._time = 0.0

    def set_walking(self, walking: bool, running: bool = False) -> None:
        self._walking = walking
        self._running = walking and running
        if self.action_active:
            return  # Update the state to resume after the action finishes.
        self._temporary_remaining = 0.0
        self._select(self._base_state)

    @property
    def _base_state(self) -> str:
        return ("running" if self._running else "walk") if self._walking else "idle"

    @property
    def action_active(self) -> bool:
        return self._action_remaining > 0

    @property
    def _dance_remaining(self) -> float:
        return self._action_remaining if self._action_name == "dance" else 0.0

    @property
    def animation_state(self) -> AnimationState:
        if self._reaction_frame is not None:
            return AnimationState.REACTING
        if self.action_active:
            return ACTION_STATES[self._action_name]
        if self._temporary_remaining > 0:
            return AnimationState.BLINKING if self.state == "blink" else AnimationState.REACTING
        return ACTION_STATES[self._base_state]

    @property
    def can_dance(self) -> bool:
        return "dance" in self.frames

    def begin_dance(self, duration: float = DANCE_SECONDS) -> bool:
        return self.begin_action("dance", duration)

    def begin_action(self, name: str, duration: float | None = None, *, hold: bool = False) -> bool:
        name = normalize_action(name)
        duration = ACTION_SECONDS.get(name, 2.0) if duration is None else duration
        if (name not in self.frames or name not in ACTION_STATES or self.action_active
                or self.animation_state == AnimationState.REACTING
                or not math.isfinite(duration) or duration <= 0):
            return False
        self._temporary_remaining = 0.0
        self._action_remaining = duration
        self._action_name = name
        self._hold_action = hold
        self._select(name)
        return True

    def end_dance(self) -> None:
        if self._dance_remaining > 0:
            self.end_action()

    def end_action(self) -> None:
        self._action_remaining = 0.0
        self._hold_action = False
        self._action_name = None
        self._select(self._base_state)

    def cancel_overrides(self) -> None:
        self.end_reaction()
        self._temporary_remaining = 0.0
        self.end_action()

    def show_expression(self, name: str, duration: float = 1.2) -> bool:
        name = normalize_action(name)
        if (self._reaction_frame is not None or self.action_active or self._temporary_remaining > 0
                or self._walking or name not in ACTION_STATES or name not in self.frames):
            return False
        if not math.isfinite(duration) or duration <= 0:
            return False
        self._select(name)
        self._time = 0.0
        self._temporary_duration = duration
        self._temporary_remaining = duration
        return True

    def begin_reaction(self, name: str, duration: float) -> bool:
        name = normalize_action(name)
        if (self.animation_state == AnimationState.REACTING or self.action_active
                or not math.isfinite(duration) or duration <= 0):
            return False
        # Overlay the pose while keeping the underlying walk/idle phase intact.
        # If the pose is absent, freeze the exact frame that was already visible.
        self._reaction_frame = (name, 0) if name in self.frames else self.frame_key
        # A reaction interrupts a blink; do not resume closed eyes afterward.
        self._temporary_remaining = 0.0
        self._select(self._base_state)
        self._reaction_duration = duration
        self._reaction_time = 0.0
        self._reaction_animated = name in self.frames
        return True

    def end_reaction(self) -> None:
        self._reaction_frame = None

    def advance(self, elapsed: float) -> None:
        if self._reaction_frame is not None:
            self._reaction_time += elapsed
            if self._reaction_time >= self._reaction_duration:
                self.end_reaction()
            return
        if self.action_active:
            self._time += elapsed * self.playback_speed
            if self._hold_action:
                return
            if elapsed >= self._action_remaining:
                self.end_action()
            else:
                self._action_remaining -= elapsed
            return
        if not self._walking:
            if self._temporary_remaining > 0:
                self._temporary_remaining = max(0.0, self._temporary_remaining - elapsed)
                if self._temporary_remaining == 0:
                    self._select("idle")
            else:
                self._blink_remaining -= elapsed
                if self._blink_remaining <= 0:
                    self._blink_remaining = self._random.uniform(*BLINK_SECONDS)
                    self.show_expression("blink", 0.22)
        self._time += elapsed * self.playback_speed

    @property
    def frame_key(self) -> tuple[str, int]:
        if self._reaction_frame is not None:
            name, index = self._reaction_frame
            if self._reaction_animated:
                count = len(self.frames[name])
                index = min(count - 1, int(self._reaction_time / self._reaction_duration * count))
            return name, index
        name = self.state if self.state in self.frames else ("idle" if "idle" in self.frames else "static")
        count = len(self.frames[name])
        if self._temporary_remaining > 0:
            progress = 1 - self._temporary_remaining / self._temporary_duration
            index = min(count - 1, int(progress * count))
        else:
            rate = self.motion_fps if self.motion_fps is not None and name not in ("idle", "blink", "sleeping") else FRAME_RATES.get(name, 8)
            if name == "walk" and self.walking_fps is not None:
                rate = self.walking_fps
            index = int(self._time * rate) % count
        return name, index

    def pixmap(self, dpr: float) -> QPixmap:
        if dpr != self._dpr:
            self._cache.clear()
            self._dpr = dpr
        key = self.frame_key
        if key not in self._cache:
            source = self.frames[key[0]][key[1]]
            fitted = self._fitted_size(source)
            # Cache the full aligned canvas at the current monitor's resolution.
            canvas = QPixmap(round(self.size.width() * dpr), round(self.size.height() * dpr))
            canvas.fill(Qt.GlobalColor.transparent)
            painter = QPainter(canvas)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            target = QRectF(
                QPointF((self.size.width() - fitted.width()) * dpr / 2,
                        (self.size.height() - fitted.height()) * dpr),
                QSize(round(fitted.width() * dpr), round(fitted.height() * dpr)),
            )
            # SmoothTransformation downsamples large PNGs without the speckling
            # produced by sampling the full-resolution art on every paint.
            scaled = source.scaled(
                target.size().toSize(), Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap(target, scaled, QRectF(scaled.rect()))
            painter.end()
            self._cache[key] = canvas
        return self._cache[key]
