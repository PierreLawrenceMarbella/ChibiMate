"""Scoped Qt styling; never applied to the transparent companion window."""

MENU_STYLE = """
QMenu { background: #20202a; color: #eeeaf7; border: 1px solid #454153;
        border-radius: 8px; padding: 6px; font-family: 'Segoe UI'; font-size: 10pt; }
QMenu::item { padding: 5px 22px 5px 12px; border-radius: 4px; }
QMenu::item:selected { background: #514365; color: #ffffff; }
QMenu::item:disabled { color: #858090; }
QMenu::separator { height: 1px; background: #403c4c; margin: 5px 8px; }
"""

SETTINGS_STYLE = """
QDialog#CharacterSettings { background: #181820; color: #eeeaf7; }
QWidget { font-family: 'Segoe UI'; font-size: 10pt; }
QLabel, QCheckBox { color: #eeeaf7; }
QLabel#Title { font-size: 20pt; font-weight: 600; }
QLabel#Subtitle, QLabel[muted="true"] { color: #b6afc6; }
QLabel#SectionTitle { font-size: 13pt; font-weight: 600; }
QTabWidget::pane { background: #22222d; border: 1px solid #3e394d; border-radius: 8px; }
QTabBar::tab { background: #181820; color: #b6afc6; padding: 10px 14px;
              border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #f4e9ff; border-bottom-color: #d5a8eb; }
QTabBar::tab:hover { background: #302a3b; color: #ffffff; }
QScrollArea { border: none; background: transparent; }
QWidget#SettingsPage { background: #22222d; }
QPushButton { color: #eeeaf7; background: #34303f; border: 1px solid #51485f;
              border-radius: 7px; padding: 8px 12px; min-height: 18px; }
QPushButton:hover { background: #463b55; border-color: #b69bd8; }
QPushButton:pressed { background: #59466c; }
QPushButton:focus { border-color: #e1b2ef; }
QPushButton:disabled { color: #888191; background: #292631; border-color: #393340; }
QPushButton[primary="true"] { background: #75518d; border-color: #a77dbd; color: #ffffff; }
QPushButton[primary="true"]:hover { background: #8860a3; }
QCheckBox { spacing: 10px; padding: 6px 0; }
QCheckBox::indicator { width: 18px; height: 18px; }
QComboBox, QSpinBox, QDoubleSpinBox { background: #191820; color: #eeeaf7;
    border: 1px solid #51485f; border-radius: 6px; padding: 6px 10px; min-height: 20px; }
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #d5a8eb; }
QComboBox:disabled, QDoubleSpinBox:disabled { color: #888191; border-color: #393340; }
QComboBox QAbstractItemView { background: #302a3b; color: #eeeaf7;
    selection-background-color: #75518d; selection-color: white; }
QSlider::groove:horizontal { background: #494050; height: 5px; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #bc94d4; border-radius: 2px; }
QSlider::handle:horizontal { background: #eee0f7; width: 16px; margin: -6px 0;
    border-radius: 8px; border: 1px solid #c6a2de; }
QSlider::handle:horizontal:hover { background: #ffffff; }
QTableWidget { background: #1c1b24; alternate-background-color: #272330;
    color: #eeeaf7; border: 1px solid #40394d; border-radius: 6px;
    selection-background-color: #514365; gridline-color: #383240; }
QHeaderView::section { background: #34303f; color: #dbd2e7; border: none; padding: 6px; }
QScrollBar:vertical { background: #22222d; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #665871; border-radius: 5px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QToolTip { background: #34303f; color: #ffffff; border: 1px solid #a487b5; padding: 5px; }
"""
