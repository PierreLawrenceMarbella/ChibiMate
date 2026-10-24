"""The existing settings dialog, with scoped styling and live controls."""

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout,
    QHeaderView, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSlider,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.actions import ACTION_LABELS, ACTIONS
from app.behavior import FREQUENCIES
from app.character import create_placeholder
from app.preferences import MIN_HEIGHT, MAX_HEIGHT
from app.theme import SETTINGS_STYLE


class CharacterPreview(QWidget):
    """Fit cached source art on a checkerboard, including at fractional DPI."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(140, 190)
        self.setAccessibleName("Current character preview")
        self.source = QPixmap()
        self._scaled = QPixmap()
        self._cache_key = None

    def sizeHint(self):
        return QSize(210, 200)

    def set_character(self, source):
        self.source = source if not source.isNull() else create_placeholder()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        for y in range(0, self.height(), 16):
            for x in range(0, self.width(), 16):
                painter.fillRect(x, y, 16, 16, QColor("#292631" if (x // 16 + y // 16) % 2 else "#24212c"))
        if self.source.isNull():
            return
        space = self.rect().adjusted(12, 12, -12, -12)
        dpr = self.devicePixelRatioF()
        key = (self.source.cacheKey(), space.size(), dpr)
        if key != self._cache_key:
            self._scaled = self.source.scaled(
                round(space.width() * dpr), round(space.height() * dpr),
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self._cache_key = key
        size = self._scaled.size() / dpr
        target = QRectF(space.center().x() - size.width() / 2,
                        space.center().y() - size.height() / 2, size.width(), size.height())
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(target, self._scaled, QRectF(self._scaled.rect()))


class CharacterSettingsDialog(QDialog):
    def __init__(self, companion):
        super().__init__(companion)
        self.setObjectName("CharacterSettings")
        self.setWindowTitle("ChibiMate - Character Settings")
        self.setStyleSheet(SETTINGS_STYLE)
        self.companion = companion
        self._refreshing = False
        self.setMinimumSize(430, 340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        title = QLabel("ChibiMate")
        title.setObjectName("Title")
        layout.addWidget(title)
        subtitle = QLabel("Your companion, your preferences.")
        subtitle.setObjectName("Subtitle")
        layout.addWidget(subtitle)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        general = self._page("General")
        self.on_top = QCheckBox("Always on top")
        general.addWidget(self.on_top)
        general.addWidget(self._hint("Keep your companion visible above normal application windows."))
        general.addSpacing(10)
        general.addWidget(self._heading("Launch position"))
        general.addWidget(self._hint("Starts near the bottom-right of the primary screen, above the taskbar. Drag to reposition."))
        general.addSpacing(10)
        general.addWidget(self._heading("Restore defaults"))
        general.addWidget(self._hint("Reset appearance, behavior, and playback controls. Your selected character and imported packs stay saved."))
        self.reset_button = self._button("Restore Default Settings", companion.restore_settings)
        general.addWidget(self.reset_button)
        general.addStretch()

        appearance = self._page("Character")
        card = QHBoxLayout()
        card.setSpacing(16)
        self.preview = CharacterPreview()
        card.addWidget(self.preview, 1)
        choices = QVBoxLayout()
        self.selection = QLabel()
        self.selection.setWordWrap(True)
        self.selection.setObjectName("SectionTitle")
        choices.addWidget(self.selection)
        self.change_button = self._button("Change Character", companion.change_character)
        choices.addWidget(self.change_button)
        choices.addWidget(self._button("Restore Default Alya", companion.restore_default))
        self.import_button = self._button("Import Animation Pack", companion.import_animation_pack)
        choices.addWidget(self.import_button)
        choices.addStretch()
        card.addLayout(choices, 1)
        appearance.addLayout(card)
        self.size_label = QLabel()
        appearance.addWidget(self.size_label)
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(MIN_HEIGHT, MAX_HEIGHT)
        self.size_slider.setAccessibleName("Character size")
        appearance.addWidget(self.size_slider)
        self.opacity_label = QLabel()
        appearance.addWidget(self.opacity_label)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setAccessibleName("Character opacity")
        appearance.addWidget(self.opacity_slider)
        appearance.addWidget(self._hint("PNG transparency and proportions are preserved. Opacity stays at 20% or above so the character remains accessible."))
        appearance.addStretch()

        behaviors = self._page("Behaviors")
        self.autonomous = QCheckBox("Enable autonomous behavior")
        behaviors.addWidget(self.autonomous)
        self.frequency = QComboBox()
        self.frequency.addItems(FREQUENCIES)
        form = QFormLayout()
        form.addRow("Behavior frequency", self.frequency)
        behaviors.addLayout(form)
        self.follow = QCheckBox("Follow cursor")
        self.pause = QCheckBox("Pause movement")
        self.edges = QCheckBox("Screen-edge behaviors")
        for control in (self.follow, self.pause, self.edges):
            behaviors.addWidget(control)
        behaviors.addWidget(self._hint("Dragging and manual actions take priority. Following stays on the current monitor. Edge poses require matching frames."))
        behaviors.addStretch()

        animations = self._page("Animations")
        self.playback_speed = QDoubleSpinBox()
        self.playback_speed.setRange(0.5, 2.0)
        self.playback_speed.setSingleStep(0.25)
        self.playback_speed.setSuffix(" x")
        self.walking_fps = QComboBox()
        self.walking_fps.addItem("Use character default", None)
        for fps in range(8, 13):
            self.walking_fps.addItem(f"{fps} FPS", fps)
        form = QFormLayout()
        form.addRow("Animation playback speed", self.playback_speed)
        form.addRow("Walking animation FPS", self.walking_fps)
        animations.addLayout(form)
        animations.addWidget(self._hint("Speed scales looping frames. Movement speed and action duration stay the same. Single-frame poses remain static."))
        self.pack_info = QLabel()
        self.pack_info.setWordWrap(True)
        animations.addWidget(self.pack_info)
        self.actions = QTableWidget(len(ACTIONS), 2)
        self.actions.setHorizontalHeaderLabels(["Action", "Available frames"])
        self.actions.verticalHeader().hide()
        self.actions.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.actions.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.actions.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.actions.setAlternatingRowColors(True)
        self.actions.setShowGrid(False)
        self.actions.setMinimumHeight(170)
        animations.addWidget(self.actions, 1)

        footer = QHBoxLayout()
        footer.addWidget(self._hint("Changes are saved automatically."), 1)
        close = QPushButton("Close")
        close.setProperty("primary", True)
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        layout.addLayout(footer)
        self.on_top.toggled.connect(self.update_display)
        self.follow.toggled.connect(self.update_display)
        self.opacity_slider.valueChanged.connect(self.update_display)
        self.size_slider.valueChanged.connect(self.resize_character)
        self.autonomous.toggled.connect(self.update_behavior)
        self.pause.toggled.connect(self.update_behavior)
        self.frequency.currentTextChanged.connect(self.update_behavior)
        self.edges.toggled.connect(self.update_edges)
        self.playback_speed.valueChanged.connect(self.update_animation)
        self.walking_fps.currentIndexChanged.connect(self.update_animation)
        self.tabs.setCurrentIndex(1)
        self.refresh()
        area = companion.screen().availableGeometry()
        self.resize(min(540, area.width() - 32), min(620, area.height() - 60))
        self.move(area.center() - self.rect().center())

    def _page(self, name):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("SettingsPage")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        scroll.setWidget(content)
        self.tabs.addTab(scroll, name)
        return layout

    @staticmethod
    def _hint(text):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setProperty("muted", True)
        return label

    @staticmethod
    def _heading(text):
        label = QLabel(text)
        label.setObjectName("SectionTitle")
        return label

    def _button(self, text, callback):
        button = QPushButton(text)
        button.clicked.connect(lambda: self.select_character(callback))
        return button

    def refresh(self):
        self._refreshing = True
        try:
            w = self.companion
            self.selection.setText("Custom character" if w._custom_file else "Default Alya")
            self.size_slider.setValue(w._character_height)
            self.size_label.setText(f"Character size: {w._character_height}px")
            self.opacity_slider.setValue(w._opacity)
            self.opacity_label.setText(f"Character opacity: {w._opacity}%")
            self.on_top.setChecked(w._always_on_top)
            self.follow.setChecked(w._follow_cursor)
            self.autonomous.setChecked(w._behavior.enabled)
            self.frequency.setCurrentText(w._behavior.frequency)
            self.pause.setChecked(w._movement_paused)
            self.edges.setChecked(w._edge_behaviors)
            self.playback_speed.setValue(w._sprites.playback_speed)
            self.walking_fps.setCurrentIndex(self.walking_fps.findData(w._sprites.walking_fps))
            frames = w._sprites.frames
            self.playback_speed.setEnabled(any(len(f) > 1 for f in frames.values()))
            self.walking_fps.setEnabled(len(frames.get("walk", [])) > 1)
            source = frames.get("idle", frames["static"])[0]
            self.preview.set_character(source)
            if w._pack_root is not None:
                info = "Imported animation pack" + (" with bundled Alya fallbacks" if not w._custom_file else "")
            elif w._custom_file:
                info = "Static PNG. Import an animation pack to add action frames."
            else:
                info = "Bundled Alya sprites"
            self.pack_info.setText(info + f"\nDefault walking rate: {w._sprites.motion_fps or 8} FPS")
            for row, name in enumerate(ACTIONS):
                count = len(frames.get(name, []))
                state = "Not supplied" if count == 0 else ("1 - static pose" if count == 1 else f"{count} - animated")
                self.actions.setItem(row, 0, QTableWidgetItem(ACTION_LABELS[name]))
                self.actions.setItem(row, 1, QTableWidgetItem(state))
        finally:
            self._refreshing = False

    def select_character(self, callback):
        callback()
        self.refresh()

    def resize_character(self, height):
        if not self._refreshing:
            self.companion.set_character_size(height)
            self.refresh()

    def update_display(self):
        if not self._refreshing:
            self.companion.set_display_options(self.opacity_slider.value(), self.on_top.isChecked(), self.follow.isChecked())
            self.refresh()

    def update_behavior(self):
        if not self._refreshing:
            self.companion.set_behavior_options(self.autonomous.isChecked(), self.frequency.currentText(), self.pause.isChecked())
            self.refresh()

    def update_edges(self, enabled):
        if not self._refreshing:
            self.companion.set_edge_behaviors(enabled)
            self.refresh()

    def update_animation(self):
        if not self._refreshing:
            self.companion.set_animation_options(self.playback_speed.value(), self.walking_fps.currentData())
            self.refresh()
