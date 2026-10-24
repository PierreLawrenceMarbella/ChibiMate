"""Bounded offline PNG pack validation; archives are never extracted directly."""
import os
import re
import stat
import zipfile
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImageReader
from app.sprites import _visible_bounds
from app.actions import ACTIONS, ALIASES, normalize_action

MAX_BYTES = 100 * 1024 * 1024
MAX_FILE = 12 * 1024 * 1024
MAX_PIXELS = 24 * 1024 * 1024
MAX_ENTRIES = 512


def safe_parts(name):
    if "\\" in name or "\x00" in name or name.startswith("/"):
        raise ValueError("The pack contains an unsafe path.")
    parts = name.rstrip("/").split("/")
    for part in parts:
        if (part in ("", ".", "..") or re.search(r'[<>:"|?*]', part)
                or part.endswith((".", " ")) or part.split(".")[0].upper() in
                {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))}):
            raise ValueError("The pack contains an unsafe path.")
    return parts


def validate_pack(source: Path, destination: Path):
    """Copy validated frame bytes into a caller-owned temporary directory."""
    archive = None
    try:
        entries = []
        if source.is_dir():
            if source.is_symlink():
                raise ValueError("Linked folders are not supported.")
            for root, dirs, files in os.walk(source, followlinks=False):
                for name in dirs + files:
                    path = Path(root) / name
                    if path.is_symlink() or not path.resolve().is_relative_to(source.resolve()):
                        raise ValueError("Linked files or folders are not supported.")
                    if len(entries) >= MAX_ENTRIES:
                        raise ValueError("Pack contains too many entries (maximum 512).")
                    entries.append((path.relative_to(source).as_posix(), path.stat().st_size if path.is_file() else 0, path if path.is_file() else None))
        else:
            if source.stat().st_size > MAX_BYTES:
                raise ValueError("ZIP archive exceeds 100 MB.")
            archive = zipfile.ZipFile(source)
            if len(archive.infolist()) > MAX_ENTRIES:
                raise ValueError("Pack contains too many entries (maximum 512).")
            for item in archive.infolist():
                # ZipInfo normalizes backslashes on Windows. Validate the raw
                # archive spelling before using its normalized filename.
                safe_parts(item.orig_filename)
                mode = item.external_attr >> 16
                if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)) or item.flag_bits & 1:
                    raise ValueError("Linked, special, or encrypted ZIP entries are not supported.")
                entries.append((item.filename, item.file_size, None if item.is_dir() else item))
        if sum(size for _, size, _ in entries) > MAX_BYTES:
            raise ValueError("Expanded pack exceeds 100 MB.")
        candidates = []
        roots = set()
        names = set()
        for name, size, item in entries:
            parts = safe_parts(name)
            folded = name.rstrip("/").casefold()
            if folded in names:
                raise ValueError("Pack contains duplicate paths.")
            names.add(folded)
            if item is None or not name.lower().endswith(".png"):
                continue
            if len(parts) in (2, 3) and parts[-2].lower() in ALIASES:
                if size > MAX_FILE:
                    raise ValueError("A PNG exceeds the 12 MB frame limit.")
                roots.add(tuple(parts[:-2]))
                candidates.append((normalize_action(parts[-2]), parts[-1], item))
        if not candidates:
            raise ValueError("No PNG frames found. Choose a pack containing idle/, walk/, or other action folders.")
        if len(roots) != 1:
            raise ValueError("Choose a pack with one character root folder.")
        if len(candidates) > 256:
            raise ValueError("Pack exceeds 256 PNG frames.")
        pixels = 0
        counts = {}
        targets = set()
        for action, name, item in candidates:
            with (archive.open(item) if archive else item.open("rb")) as stream:
                data = stream.read(MAX_FILE + 1)
            if len(data) > MAX_FILE:
                raise ValueError("A PNG exceeds the 12 MB frame limit.")
            buffer = QBuffer()
            buffer.setData(QByteArray(data))
            buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            reader = QImageReader(buffer, b"PNG")
            size = reader.size()
            if not size.isValid() or max(size.width(), size.height()) > 2048:
                raise ValueError(f"Invalid or oversized PNG: {action}/{name} (maximum 2048px per side).")
            pixels += size.width() * size.height()
            if pixels > MAX_PIXELS:
                raise ValueError("Pack exceeds the decoded image budget (24 megapixels).")
            image = reader.read()
            if image.isNull() or _visible_bounds(image).isEmpty():
                raise ValueError(f"Unreadable or entirely transparent PNG: {action}/{name}.")
            target = destination / action / (Path(name).stem + ".png")
            if str(target).casefold() in targets:
                raise ValueError("Duplicate frame names in an action folder.")
            targets.add(str(target).casefold())
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            counts[action] = counts.get(action, 0) + 1
        return counts
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as error:
        raise ValueError("The ZIP archive is damaged, encrypted, or unsupported.") from error
    finally:
        if archive:
            archive.close()
