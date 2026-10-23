"""Offline pack selection and preview using the desktop sprite player."""
import tempfile
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QSize, Qt, QTimer
from PySide6.QtWidgets import QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout

from app.packs import ACTIONS, validate_pack
from app.sprites import SpriteAnimation


class PackDialog(QDialog):
    def __init__(self, character, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Animation Pack")
        self.character = character
        self.fallback_description = "Missing or insufficient actions use the static PNG/dialogue."
        self.staging = None
        self.player = None
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        choices = QHBoxLayout()
        for title, zipped in (("Choose Folder", False), ("Choose ZIP", True)):
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, zipped=zipped: self.choose(zipped))
            choices.addWidget(button)
        layout.addLayout(choices)
        self.preview = QLabel("Choose an animation pack for this character.")
        self.preview.setFixedSize(400, 240)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)
        self.preview.setStyleSheet("background: #eeeaf4; border-radius: 8px;")
        layout.addWidget(self.preview)
        self.actions = QComboBox()
        self.actions.currentTextChanged.connect(self.select_action)
        layout.addWidget(self.actions)
        speed = QHBoxLayout()
        speed.addWidget(QLabel("Walking / dancing FPS:"))
        self.fps = QSpinBox()
        self.fps.setRange(8, 12)
        self.fps.setValue(8)
        self.fps.valueChanged.connect(self.speed_changed)
        speed.addWidget(self.fps)
        layout.addLayout(speed)
        self.status = QLabel("Frames must already exist as PNG files. Nothing is generated.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        self.apply = QPushButton("Apply Animation Pack")
        self.apply.setEnabled(False)
        self.apply.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(self.apply)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        self.clock = QElapsedTimer()
        self.clock.start()
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)
        self.finished.connect(self.timer.stop)

    def choose(self, zipped):
        source = (QFileDialog.getOpenFileName(self, "Choose Animation ZIP", "", "ZIP archives (*.zip)")[0]
                  if zipped else QFileDialog.getExistingDirectory(self, "Choose Animation Folder"))
        if source:
            self.load_source(Path(source))

    def load_source(self, source):
        candidate = tempfile.TemporaryDirectory(prefix="chibimate-pack-")
        try:
            counts = validate_pack(source, Path(candidate.name))
            player = SpriteAnimation(Path(candidate.name), self.character, QSize(220, 220), self.fps.value())
            available = [name for name in ACTIONS if name in player.frames]
            if not available:
                raise ValueError("No usable actions. Walking and dancing each need at least two different poses.")
        except (OSError, ValueError) as error:
            candidate.cleanup()
            self.status.setText(str(error))
            return
        if self.staging:
            self.staging.cleanup()
        self.staging = candidate
        self.player = player
        self.actions.blockSignals(True)
        self.actions.clear()
        self.actions.addItems(available)
        self.actions.blockSignals(False)
        self.actions.setCurrentText("walk" if "walk" in available else available[0])
        self.select_action(self.actions.currentText())
        missing = [name for name in ACTIONS if name not in available]
        self.status.setText("Available: " + ", ".join(f"{name} ({counts[name]})" for name in available)
                            + ".\nUnavailable in pack: " + (", ".join(missing) or "none")
                            + ". " + self.fallback_description
                            + " Walking and dancing require two different poses.")
        self.apply.setEnabled(True)
        self.clock.restart()
        self.timer.start()

    def speed_changed(self, value):
        if self.player:
            self.player.motion_fps = value

    def select_action(self, name):
        if not self.player:
            return
        self.player.end_reaction()
        self.player.end_dance()
        self.player.set_walking(name == "walk")
        if name == "dance":
            self.player.begin_dance()
        elif name not in ("idle", "walk"):
            self.player.show_expression(name, 0.22 if name == "blink" else 1.5)
        self.preview.setPixmap(self.player.pixmap(1))

    def tick(self):
        if self.player:
            self.player.advance(min(self.clock.restart() / 1000, 0.1))
            self.preview.setPixmap(self.player.pixmap(1))

    def cleanup(self):
        self.timer.stop()
        if self.staging:
            self.staging.cleanup()
            self.staging = None
