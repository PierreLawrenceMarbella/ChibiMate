"""Folder-based sprite playback, driven by the window's existing timer."""

import logging
import math
import re
from pathlib import Path
from random import Random

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QBitmap, QImage, QPainter, QPixmap, QRegion


SPRITE_PATH = Path(__file__).resolve().parent.parent / "assets" / "characters" / "alya"
FRAME_RATES = {"walk": 8, "idle": 2}
BLINK_SECONDS = (3.0, 6.0)
EXPRESSION_SECONDS = (12.0, 22.0)


def _frame_order(path: Path) -> list:
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", path.name)]


class SpriteAnimation:
    def __init__(self, root: Path, fallback: QPixmap, max_size: QSize) -> None:
        self.frames: dict[str, list[QPixmap]] = {"static": [fallback]}
        for name in ("walk", "idle", "blink", "happy", "surprised"):
            frames = []
            folder = root / name
            paths = sorted(folder.glob("*.png"), key=_frame_order)
            for path in paths:
                image = QImage(str(path), "PNG")
                if image.isNull():
                    logging.getLogger(__name__).warning("Skipping unreadable sprite: %s", path)
                    continue
                # Remove transparent margins in memory, then anchor all poses at
                # bottom-center. The source files and their aspect ratios stay intact.
                bounds = QRegion(QBitmap.fromImage(image.createAlphaMask())).boundingRect()
                if not bounds.isEmpty():
                    frames.append(QPixmap.fromImage(image.copy(bounds)))
            # Walking needs a sequence; idle and brief expressions can be held poses.
            if len(frames) >= (2 if name == "walk" else 1):
                self.frames[name] = frames

        sizes = [frame.size().scaled(max_size, Qt.AspectRatioMode.KeepAspectRatio)
                 for frames in self.frames.values() for frame in frames]
        self.size = QSize(max(size.width() for size in sizes),
                          max(size.height() for size in sizes))
        self._max_size = QSize(max_size)
        self._random = Random()
        self._blink_remaining = self._random.uniform(*BLINK_SECONDS)
        self._expression_remaining = self._random.uniform(*EXPRESSION_SECONDS)
        self._temporary_remaining = 0.0
        self._temporary_duration = 0.0
        self._walking = False
        self.state = "idle"
        self._time = 0.0
        self._cache: dict[tuple[str, int], QPixmap] = {}
        self._dpr = 0.0

    def _select(self, name: str) -> None:
        if self.state != name:
            self.state = name
            self._time = 0.0

    def set_walking(self, walking: bool) -> None:
        self._walking = walking
        self._temporary_remaining = 0.0
        self._select("walk" if walking else "idle")

    def show_expression(self, name: str, duration: float = 1.2) -> bool:
        if self._walking or name not in ("blink", "happy", "surprised") or name not in self.frames:
            return False
        if not math.isfinite(duration) or duration <= 0:
            return False
        self._select(name)
        self._time = 0.0
        self._temporary_duration = duration
        self._temporary_remaining = duration
        return True

    def advance(self, elapsed: float) -> None:
        if not self._walking:
            if self._temporary_remaining > 0:
                self._temporary_remaining = max(0.0, self._temporary_remaining - elapsed)
                if self._temporary_remaining == 0:
                    self._select("idle")
            else:
                self._blink_remaining -= elapsed
                self._expression_remaining -= elapsed
                if self._blink_remaining <= 0:
                    self._blink_remaining = self._random.uniform(*BLINK_SECONDS)
                    self.show_expression("blink", 0.22)
                elif self._expression_remaining <= 0:
                    self._expression_remaining = self._random.uniform(*EXPRESSION_SECONDS)
                    available = [name for name in ("happy", "surprised") if name in self.frames]
                    if available:
                        self.show_expression(self._random.choice(available))
        self._time += elapsed

    @property
    def frame_key(self) -> tuple[str, int]:
        name = self.state if self.state in self.frames else "static"
        count = len(self.frames[name])
        if self._temporary_remaining > 0:
            progress = 1 - self._temporary_remaining / self._temporary_duration
            index = min(count - 1, int(progress * count))
        else:
            index = int(self._time * FRAME_RATES.get(name, 1)) % count
        return name, index

    def pixmap(self, dpr: float) -> QPixmap:
        if dpr != self._dpr:
            self._cache.clear()
            self._dpr = dpr
        key = self.frame_key
        if key not in self._cache:
            source = self.frames[key[0]][key[1]]
            fitted = source.size().scaled(self._max_size, Qt.AspectRatioMode.KeepAspectRatio)
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
