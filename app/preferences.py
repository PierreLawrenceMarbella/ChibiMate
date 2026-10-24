"""Local character preferences and app-owned copies of imported PNGs."""

import logging
import hashlib
import shutil
import re
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QIODevice, QSaveFile, QSettings, QStandardPaths
from PySide6.QtGui import QImage, QPixmap
from app.behavior import FREQUENCIES


CHARACTER_HEIGHTS = {"Small": 100, "Medium": 150, "Large": 200}
MIN_HEIGHT, MAX_HEIGHT = 75, 300


def read_png(path: Path) -> tuple[bytes, QPixmap]:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise OSError(f"Cannot read the character image: {path.name}") from error
    image = QImage.fromData(data, "PNG")
    if image.isNull():
        raise ValueError("Please choose a readable PNG image. This file is invalid or damaged.")
    return data, QPixmap.fromImage(image)


class CharacterPreferences:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory if directory is not None else Path(
            QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
        )
        self.settings = QSettings(str(self.directory / "preferences.ini"), QSettings.Format.IniFormat)

    @property
    def height(self) -> int:
        try:
            height = int(self.settings.value("height", 150))
        except (TypeError, ValueError):
            return 150
        return height if MIN_HEIGHT <= height <= MAX_HEIGHT else 150

    @property
    def display_options(self) -> tuple[int, bool, bool]:
        try:
            opacity = max(20, min(100, int(self.settings.value("opacity", 100))))
        except (TypeError, ValueError):
            opacity = 100
        top = str(self.settings.value("always_on_top", "true")).lower() == "true"
        follow = str(self.settings.value("follow_cursor", "false")).lower() == "true"
        return opacity, top, follow

    def save_display_options(self, opacity: int, top: bool, follow: bool) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        for name, value in (("opacity", opacity), ("always_on_top", top), ("follow_cursor", follow)):
            self.settings.setValue(name, value)
        self.settings.sync()
        if self.settings.status() != QSettings.Status.NoError:
            raise OSError("Could not save display preferences.")

    @property
    def edge_behaviors(self) -> bool:
        return str(self.settings.value("behavior/edges", "false")).lower() == "true"

    def save_edge_behaviors(self, enabled: bool) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        previous = self.edge_behaviors
        self.settings.setValue("behavior/edges", enabled)
        self.settings.sync()
        if self.settings.status() != QSettings.Status.NoError:
            self.settings.setValue("behavior/edges", previous)
            self.settings.sync()
            raise OSError("Could not save screen-edge preferences.")

    @property
    def behavior_options(self) -> tuple[bool, str, bool]:
        enabled = str(self.settings.value("behavior/enabled", "true")).lower() != "false"
        frequency = self.settings.value("behavior/frequency", "Normal")
        if not isinstance(frequency, str) or frequency not in FREQUENCIES:
            frequency = "Normal"
        paused = str(self.settings.value("behavior/paused", "false")).lower() == "true"
        return enabled, frequency, paused

    def save_behavior_options(self, enabled: bool, frequency: str, paused: bool) -> None:
        if frequency not in FREQUENCIES:
            raise ValueError("Choose Low, Normal, or High behavior frequency.")
        self.directory.mkdir(parents=True, exist_ok=True)
        values = {"enabled": enabled, "frequency": frequency, "paused": paused}
        previous = {key: self.settings.value("behavior/" + key) for key in values}
        for key, value in values.items():
            self.settings.setValue("behavior/" + key, value)
        self.settings.sync()
        if self.settings.status() != QSettings.Status.NoError:
            for key, value in previous.items():
                if value is None:
                    self.settings.remove("behavior/" + key)
                else:
                    self.settings.setValue("behavior/" + key, value)
            self.settings.sync()
            raise OSError("Could not save behavior preferences.")

    def load_character(self) -> tuple[str, QPixmap | None]:
        filename = self.settings.value("character", "")
        if not filename:
            return "", None
        try:
            # Settings may only refer to copies inside this app's own directory.
            if not isinstance(filename, str) or not re.fullmatch(r"(?:generated-characters/)?character-[0-9a-f]{32}\.png", filename):
                raise ValueError("Invalid saved character filename")
            _, pixmap = read_png(self.directory / filename)
            return filename, pixmap
        except (OSError, ValueError) as error:
            logging.getLogger(__name__).warning("Saved character unavailable; using default Alya: %s", error)
            return "", None

    def save(self, filename: str, height: int) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        previous = (self.settings.value("character", ""), self.settings.value("height", 150))
        self.settings.setValue("character", filename)
        self.settings.setValue("height", height)
        self.settings.sync()
        if self.settings.status() != QSettings.Status.NoError:
            self.settings.setValue("character", previous[0])
            self.settings.setValue("height", previous[1])
            self.settings.sync()
            raise OSError("Could not save character preferences in the application data folder.")

    def import_character(self, path: Path, height: int) -> tuple[str, QPixmap]:
        data, pixmap = read_png(path)
        self.directory.mkdir(parents=True, exist_ok=True)
        filename = f"character-{uuid4().hex}.png"
        destination = QSaveFile(str(self.directory / filename))
        if not destination.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError("Could not create a character copy in the application data folder.")
        if destination.write(data) != len(data):
            destination.cancelWriting()
            raise OSError("Could not write the imported character image.")
        if not destination.commit():
            raise OSError("Could not finish saving the imported character image.")
        self.save(filename, height)
        return filename, pixmap

    def accept_generated(self, data: bytes, height: int) -> tuple[str, QPixmap]:
        image = QImage.fromData(data, "PNG")
        if image.isNull():
            raise ValueError("The generated image is not a readable PNG.")
        folder = self.directory / "generated-characters"
        folder.mkdir(parents=True, exist_ok=True)
        filename = f"generated-characters/character-{uuid4().hex}.png"
        destination = QSaveFile(str(self.directory / filename))
        if not destination.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError("Could not save the generated character.")
        if destination.write(data) != len(data):
            destination.cancelWriting()
            raise OSError("Could not save the generated character.")
        if not destination.commit():
            raise OSError("Could not finish saving the generated character.")
        try:
            self.save(filename, height)
        except OSError:
            (self.directory / filename).unlink(missing_ok=True)
            raise
        return filename, QPixmap.fromImage(image)

    def _pack_key(self, filename: str) -> str:
        if not filename:
            return "packs/default-alya"
        # Identical imported PNGs recover their association even from a new path.
        return "packs/" + hashlib.sha256((self.directory / filename).read_bytes()).hexdigest()

    def pack_for(self, filename: str) -> tuple[Path | None, int]:
        try:
            key = self._pack_key(filename)
            name = self.settings.value(key + "/folder", "")
            fps = int(self.settings.value(key + "/fps", 8))
            if not isinstance(name, str) or not re.fullmatch(r"pack-[0-9a-f]{32}", name):
                return None, 8
            path = self.directory / "animation-packs" / name
            if path.is_dir():
                return path, fps if 8 <= fps <= 12 else 8
            logging.getLogger(__name__).warning("Saved animation pack is missing; using the character's default appearance.")
        except (OSError, ValueError, TypeError):
            logging.getLogger(__name__).warning("Saved animation pack is unavailable; using the character's default appearance.")
        return None, 8

    def accept_pack(self, filename: str, staged: Path, fps: int) -> None:
        if fps not in range(8, 13):
            raise ValueError("Select a speed from 8 to 12 FPS.")
        key = self._pack_key(filename)
        parent = self.directory / "animation-packs"
        parent.mkdir(parents=True, exist_ok=True)
        destination = parent / ("pack-" + uuid4().hex)
        previous = (self.settings.value(key + "/folder", ""), self.settings.value(key + "/fps", 8))
        try:
            shutil.copytree(staged, destination)
            self.settings.setValue(key + "/folder", destination.name)
            self.settings.setValue(key + "/fps", fps)
            self.settings.sync()
            if self.settings.status() != QSettings.Status.NoError:
                raise OSError("Could not save the animation pack association.")
        except OSError:
            self.settings.setValue(key + "/folder", previous[0])
            self.settings.setValue(key + "/fps", previous[1])
            self.settings.sync()
            if destination.resolve().parent == parent.resolve() and destination.exists():
                shutil.rmtree(destination)
            raise

    def restore_default(self, height: int) -> None:
        """Restore bundled Alya without deleting any imported pack files."""
        key = self._pack_key("")
        previous = {name: self.settings.value(key + "/" + name) for name in ("folder", "fps")}
        self.settings.remove(key)
        try:
            # Flush the character selection and removed override together.
            self.save("", height)
        except OSError:
            for name, value in previous.items():
                if value is not None:
                    self.settings.setValue(key + "/" + name, value)
            self.settings.sync()
            raise
