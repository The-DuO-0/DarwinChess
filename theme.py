APP_QSS = r"""
QWidget {
    background: #111318;
    color: #e8ebf2;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog { background: #0c0e13; }
QFrame#Sidebar { background: #0a0c10; border-right: 1px solid #222632; }
QLabel#Brand { font-size: 22px; font-weight: 750; color: #f5f7fb; }
QLabel#Subtle { color: #8d96a8; }
QLabel#SectionTitle { font-size: 25px; font-weight: 750; }
QLabel#CardValue { font-size: 24px; font-weight: 750; }
QLabel#RunBadge {
    background: #171b24; color: #aeb8ca; border: 1px solid #2b3240;
    border-radius: 9px; padding: 6px 9px; font-weight: 700;
}
QLabel#RunBadge[active="true"] {
    background: #17273f; color: #cfe0ff; border-color: #4169e1;
}
QLabel#StageBox {
    background: #11151c; color: #8f99aa; border: 1px solid #303644;
    border-radius: 10px; padding: 10px; font-weight: 700;
}
QLabel#StageBox[active="true"] {
    background: #1f3159; color: #eef4ff; border: 2px solid #4d78ee;
}
QLabel#InfoNote {
    background: #111c2a; color: #b9c9e8; border: 1px solid #294062;
    border-radius: 10px; padding: 10px;
}
QFrame#Card { background: #171a21; border: 1px solid #282d38; border-radius: 14px; }
QFrame#Panel { background: #15181f; border: 1px solid #282d38; border-radius: 14px; }
QPushButton {
    background: #202530; border: 1px solid #323846; border-radius: 9px;
    padding: 9px 13px; color: #edf0f6; font-weight: 650;
}
QPushButton:hover { background: #2a3140; border-color: #465064; color: #ffffff; }
QPushButton:pressed { background: #171b22; padding-top: 10px; padding-bottom: 8px; }
QPushButton:disabled { background: #151820; color: #596171; border-color: #242936; }
QPushButton#Primary { background: #4169e1; border-color: #4169e1; color: white; }
QPushButton#Primary:hover { background: #5278e9; border-color: #6d8df0; }
QPushButton#Primary:pressed { background: #3457c2; }
QPushButton#Danger { background: #472126; border-color: #6d3038; color: #ffd7dc; }
QPushButton#Danger:hover { background: #5b252c; border-color: #8a3b46; }
QPushButton#Nav { background: transparent; border: 0; text-align: left; padding: 11px 14px; color: #aeb6c6; }
QPushButton#Nav:hover { background: #161b26; color: #ffffff; }
QPushButton#Nav:pressed { background: #10141c; }
QPushButton#Nav:checked { background: #1c2537; color: #ffffff; }
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QTextEdit, QPlainTextEdit, QListWidget, QTableWidget {
    background: #0f1217; border: 1px solid #2b303b; border-radius: 8px; padding: 7px;
    selection-background-color: #385dc7;
}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {
    border-color: #46536b;
}
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QHeaderView::section { background: #181c24; color: #aeb6c6; padding: 7px; border: 0; }
QTabWidget::pane { border: 0; }
QProgressBar { background: #0e1116; border: 1px solid #2b303b; border-radius: 7px; text-align: center; min-height: 18px; }
QProgressBar::chunk { background: #4169e1; border-radius: 6px; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: #303642; border-radius: 5px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: #414958; }
"""
