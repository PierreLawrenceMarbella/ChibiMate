"""Small local controls for the existing character and display preferences."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout,
)

from app.preferences import MIN_HEIGHT, MAX_HEIGHT


class CharacterSettingsDialog(QDialog):
    def __init__(self, companion):
        super().__init__(companion)
        self.setWindowTitle("Character Settings")
        self.setMinimumWidth(340)
        self.companion = companion
        layout = QVBoxLayout(self)
        self.preview = QLabel()
        self.preview.setFixedSize(320, 200)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.preview)
        self.selection = QLabel()
        layout.addWidget(self.selection)
        choices = QHBoxLayout()
        for label, callback in (("Choose PNG", companion.change_character), ("Default Alya", companion.restore_default)):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, callback=callback: self.select_character(callback))
            choices.addWidget(button)
        layout.addLayout(choices)
        self.size_label = QLabel()
        layout.addWidget(self.size_label)
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(MIN_HEIGHT, MAX_HEIGHT)
        self.size_slider.setValue(companion._character_height)
        self.size_slider.valueChanged.connect(self.resize_character)
        layout.addWidget(self.size_slider)
        self.transparency_label = QLabel()
        layout.addWidget(self.transparency_label)
        self.transparency = QSlider(Qt.Orientation.Horizontal)
        self.transparency.setRange(0, 80)  # Keep a visible, draggable companion.
        self.transparency.setValue(100 - companion._opacity)
        layout.addWidget(self.transparency)
        self.on_top = QCheckBox("Always on top")
        self.on_top.setChecked(companion._always_on_top)
        self.follow = QCheckBox("Follow cursor")
        self.follow.setChecked(companion._follow_cursor)
        layout.addWidget(self.on_top)
        layout.addWidget(self.follow)
        self.transparency.valueChanged.connect(self.update_display)
        self.on_top.toggled.connect(self.update_display)
        self.follow.toggled.connect(self.update_display)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh()

    def refresh(self):
        self.selection.setText("Custom character" if self.companion._custom_file else "Default Alya")
        self.size_label.setText(f"Character size: {self.companion._character_height}px")
        self.transparency_label.setText(f"Transparency: {100 - self.companion._opacity}%")
        self.preview.setPixmap(self.companion._sprites.pixmap(1).scaled(
            self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def select_character(self, callback):
        callback()
        self.refresh()

    def resize_character(self, height):
        self.companion.set_character_size(height)
        self.refresh()

    def update_display(self):
        self.companion.set_display_options(100 - self.transparency.value(), self.on_top.isChecked(), self.follow.isChecked())
        self.refresh()
