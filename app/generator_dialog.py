"""Preview and approve one generated character without changing the active pet."""

import os
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QSaveFile, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from app.generation import DEFAULT_PROMPT, GenerationWorker, OpenAIImageProvider


class GeneratorDialog(QDialog):
    use_character = Signal(bytes)

    def __init__(self, parent=None, provider=None):
        super().__init__(parent)
        self.setWindowTitle("AI Chibi Generator")
        self.setWindowFlag(Qt.WindowType.Tool)
        self.setMinimumWidth(480)
        self.provider = provider if provider is not None else OpenAIImageProvider()
        self.worker = None
        self.closing = False
        self.reference = b""
        self.generated = b""
        layout = QVBoxLayout(self)
        self.upload = QPushButton("Upload Reference Image")
        self.upload.clicked.connect(self.choose_reference)
        layout.addWidget(self.upload)
        previews = QHBoxLayout()
        self.reference_preview = QLabel("Reference image")
        self.generated_preview = QLabel("Generated image")
        for label in (self.reference_preview, self.generated_preview):
            label.setFixedSize(220, 220)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("background: #eeeaf4; border: 1px solid #cfc5df; border-radius: 8px;")
            previews.addWidget(label)
        layout.addLayout(previews)
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText("Optional details: clothing, colors, expression...")
        self.prompt.setMaximumHeight(70)
        layout.addWidget(self.prompt)
        notice = QLabel("Generate sends your reference and prompt to OpenAI and may incur charges. "
                        "Resemblance and transparency may vary. Canceling may not prevent charges.")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.generate = QPushButton("Generate Chibi")
        self.generate.clicked.connect(self.start_generation)
        layout.addWidget(self.generate)
        self.status = QLabel("Choose a reference image to begin.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        self.use = QPushButton("Use as ChibiMate")
        self.save = QPushButton("Save PNG")
        self.cancel = QPushButton("Cancel")
        self.use.clicked.connect(lambda: self.use_character.emit(self.generated))
        self.save.clicked.connect(self.save_png)
        self.cancel.clicked.connect(self.reject)
        for button in (self.use, self.save, self.cancel):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self._controls()

    def _controls(self):
        busy = self.worker is not None
        self.upload.setEnabled(not busy)
        self.prompt.setEnabled(not busy)
        self.generate.setEnabled(not busy and bool(self.reference))
        self.use.setEnabled(not busy and bool(self.generated))
        self.save.setEnabled(not busy and bool(self.generated))

    def _preview(self, label, data):
        pixmap = QPixmap.fromImage(QImage.fromData(data))
        label.setPixmap(pixmap.scaled(label.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation))

    def choose_reference(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Reference Image", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if not filename:
            return
        try:
            path = Path(filename)
            if path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp") or path.stat().st_size > 20 * 1024 * 1024:
                raise ValueError()
            image = QImage.fromData(path.read_bytes())
            if image.isNull():
                raise ValueError()
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            if not image.save(buffer, "PNG") or buffer.size() >= 50 * 1024 * 1024:
                raise ValueError()
            self.reference = bytes(buffer.data())
            self.generated = b""
            self.generated_preview.clear()
            self._preview(self.reference_preview, self.reference)
            self.status.setText("Reference ready.")
            self._controls()
        except (OSError, ValueError):
            self.status.setText("Choose a readable PNG, JPG, JPEG, or WebP image under 20 MB.")

    def start_generation(self):
        if self.worker is not None or not self.reference:
            return
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            self.status.setText("Set OPENAI_API_KEY in your environment, then restart ChibiMate.")
            return
        self.generated = b""
        self.generated_preview.clear()
        self.status.setText("Generating Chibi...")
        prompt = DEFAULT_PROMPT + "\nAdditional details: " + self.prompt.toPlainText().strip()
        self.worker = GenerationWorker(self.provider, self.reference, prompt, key, self)
        self.worker.result.connect(self._result)
        self.worker.error.connect(self._error)
        self.worker.finished.connect(self._finished)
        self._controls()
        self.worker.start()

    def _result(self, data):
        if not self.closing:
            self.generated = data
            self._preview(self.generated_preview, data)
            self.status.setText("Ready to preview. Use as ChibiMate or save a PNG.")

    def _error(self, message):
        if not self.closing:
            self.status.setText(message)

    def _finished(self):
        self.worker.wait()
        self.worker.deleteLater()
        self.worker = None
        self._controls()
        if self.closing:
            super().reject()

    def save_png(self):
        if not self.generated:
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Save Chibi PNG", "chibimate.png", "PNG images (*.png)")
        if filename:
            file = QSaveFile(filename)
            if not file.open(QIODevice.OpenModeFlag.WriteOnly):
                self.status.setText("Could not save the PNG at that location.")
                return
            if file.write(self.generated) != len(self.generated):
                file.cancelWriting()
                self.status.setText("Could not write the PNG.")
            elif not file.commit():
                self.status.setText("Could not finish saving the PNG.")
            else:
                self.status.setText("PNG saved.")

    def reject(self):
        if self.worker is not None:
            self.closing = True
            self.worker.cancelled.set()
            self.status.setText("Canceling generation...")
        else:
            super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            event.ignore()
            self.reject()
        else:
            super().closeEvent(event)
