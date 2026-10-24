"""Bound image reads before decoding untrusted or damaged local PNGs."""

from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage, QImageReader

MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_IMAGE_PIXELS = 24 * 1024 * 1024


def png_image(data: bytes, *, max_pixels: int = MAX_IMAGE_PIXELS, max_side: int = 8192) -> QImage:
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("PNG exceeds the 32 MB image limit.")
    buffer = QBuffer()
    buffer.setData(data)
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buffer, b"PNG")
    size = reader.size()
    if not size.isValid():
        raise ValueError("Please choose a readable PNG image. This file is invalid or damaged.")
    if max(size.width(), size.height()) > max_side or size.width() * size.height() > max_pixels:
        raise ValueError("PNG dimensions exceed the supported image limit.")
    image = reader.read()
    if image.isNull():
        raise ValueError("Please choose a readable PNG image. This file is invalid or damaged.")
    return image


def read_image_bytes(path: Path, limit: int = MAX_IMAGE_BYTES) -> bytes:
    with path.open("rb") as source:
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError("PNG exceeds the supported file size limit.")
    return data
