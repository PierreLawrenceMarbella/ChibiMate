"""Offline pack selection and preview using the desktop sprite player."""
import tempfile
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QSize, Qt, QTimer, QThread
from PySide6.QtWidgets import QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout

from app.packs import ACTIONS, validate_pack
from app.sprites import SpriteAnimation, load_frames


class PackWorker(QThread):
    """Only file validation and QImage preparation run in this worker."""
    def __init__(self, source, parent):
        super().__init__(parent)
        self.source = source
        self.staging = None
        self.frames = None
        self.counts = None
        self.error = ""

    def run(self):
        try:
            self.staging = tempfile.TemporaryDirectory(prefix="chibimate-pack-")
            root = Path(self.staging.name)
            self.counts = validate_pack(self.source, root, self.isInterruptionRequested)
            self.frames = load_frames(root, cancelled=self.isInterruptionRequested)
        except InterruptedError:
            pass
        except (OSError, ValueError) as error:
            self.error = str(error)
        except Exception:
            # Do not include arbitrary exception data or user paths in logs/UI.
            self.error = "Could not prepare this pack. Check its PNG files and try again."

    def cleanup(self):
        self.frames = None
        if self.staging:
            self.staging.cleanup()
            self.staging = None


class PackDialog(QDialog):
    def __init__(self, character, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Animation Pack")
        self.character = character
        self.fallback_description = "Missing actions use idle or the character PNG/dialogue. One frame holds a static pose."
        self.staging = None
        self.player = None
        self.worker = None
        self._closing = False
        self._preview_key = None
        self.choice_buttons = []
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        choices = QHBoxLayout()
        for title, zipped in (("Choose Folder", False), ("Choose ZIP", True)):
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, zipped=zipped: self.choose(zipped))
            choices.addWidget(button)
            self.choice_buttons.append(button)
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
        speed.addWidget(QLabel("Action animation FPS:"))
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
            self.start_loading(Path(source))

    def start_loading(self, source):
        if self.worker is not None:
            return
        self.timer.stop()
        self.apply.setEnabled(False)
        for button in self.choice_buttons:
            button.setEnabled(False)
        self.status.setText("Validating animation pack...")
        self.worker = PackWorker(source, self)
        self.worker.finished.connect(self._loaded)
        self.worker.start()

    def _loaded(self):
        worker, self.worker = self.worker, None
        try:
            if self._closing:
                return
            if worker.error or not worker.frames:
                self.status.setText(worker.error or "No usable action frames found.")
                self.apply.setEnabled(self.player is not None)
                self._start_preview_timer()
            else:
                player = SpriteAnimation(None, self.character, QSize(220, 220), self.fps.value(),
                                         prepared_frames=worker.frames)
                candidate, worker.staging = worker.staging, None
                self._install_preview(candidate, player, worker.counts)
        finally:
            worker.cleanup()
            worker.deleteLater()
            for button in self.choice_buttons:
                button.setEnabled(True)
            if self._closing:
                super().reject()

    def load_source(self, source):
        # Synchronous entry point for local checks; file-picker imports use a worker.
        candidate = tempfile.TemporaryDirectory(prefix="chibimate-pack-")
        try:
            counts = validate_pack(source, Path(candidate.name))
            player = SpriteAnimation(Path(candidate.name), self.character, QSize(220, 220), self.fps.value())
            available = [name for name in ACTIONS if name in player.frames]
            if not available:
                raise ValueError("No usable actions. Add a readable PNG inside an action folder.")
        except (OSError, ValueError) as error:
            candidate.cleanup()
            self.status.setText(str(error))
            return
        self._install_preview(candidate, player, counts)

    def _install_preview(self, candidate, player, counts):
        available = [name for name in ACTIONS if name in player.frames]
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
                            + ". " + self.fallback_description)
        self.apply.setEnabled(True)
        self._start_preview_timer()

    def _start_preview_timer(self):
        self.timer.stop()
        if self.player and self.worker is None:
            name = self.player.state
            if len(self.player.frames.get(name, [])) > 1 or (name == "idle" and "blink" in self.player.frames):
                self.clock.restart()
                self.timer.start()

    def speed_changed(self, value):
        if self.player:
            self.player.motion_fps = value

    def select_action(self, name):
        if not self.player:
            return
        self.player.end_reaction()
        self.player.end_action()
        self.player.set_walking(name in ("walk", "running"), running=name == "running")
        if name not in ("idle", "walk", "running"):
            self.player.begin_action(name, 3600)
        self.preview.setPixmap(self.player.pixmap(1))
        self._preview_key = self.player.frame_key
        self._start_preview_timer()

    def tick(self):
        if self.player:
            self.player.advance(min(self.clock.restart() / 1000, 0.1))
            if self.player.frame_key != self._preview_key:
                self.preview.setPixmap(self.player.pixmap(1))
                self._preview_key = self.player.frame_key

    def reject(self):
        if self.worker is not None:
            self._closing = True
            self.worker.requestInterruption()
            self.status.setText("Canceling import...")
        else:
            super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            event.ignore()
            self.reject()
        else:
            super().closeEvent(event)

    def cleanup(self):
        self.timer.stop()
        self.player = None
        self.preview.clear()
        if self.staging:
            self.staging.cleanup()
            self.staging = None
