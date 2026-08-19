from __future__ import annotations

import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from .backend import AgentBridge, ProcessController
from .pages.chat import ChatPage
from .pages.dashboard import DashboardPage
from .pages.evolution import EvolutionPage
from .pages.play import PlayPage
from .pages.research import ResearchPage
from .theme import APP_QSS


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DarwinChess Studio")
        self.resize(1380, 900)
        self.setMinimumSize(1080, 720)

        self.agent = AgentBridge(mode="normal", parent=self)
        self.process = ProcessController(self)
        self._close_when_finished = False
        self.process.finished.connect(self._finish_pending_close)

        shell = QWidget(); main = QHBoxLayout(shell); main.setContentsMargins(0, 0, 0, 0); main.setSpacing(0)
        sidebar = QFrame(); sidebar.setObjectName("Sidebar"); sidebar.setFixedWidth(210); sl = QVBoxLayout(sidebar); sl.setContentsMargins(16, 22, 16, 18)
        brand = QLabel("DarwinChess"); brand.setObjectName("Brand"); sl.addWidget(brand)
        sub = QLabel("STUDIO 1.0.2"); sub.setObjectName("Subtle"); sl.addWidget(sub); sl.addSpacing(24)

        self.stack = QStackedWidget()
        self.pages = [
            ("Dashboard", DashboardPage(self.agent, self.process)),
            ("Play Champion", PlayPage(self.agent)),
            ("Evolution", EvolutionPage(self.process)),
            ("Research", ResearchPage(self.process)),
            ("Conversation", ChatPage(self.agent)),
        ]
        self.nav = []
        for i, (name, page) in enumerate(self.pages):
            btn = QPushButton(name); btn.setObjectName("Nav"); btn.setCheckable(True); btn.clicked.connect(lambda checked=False, idx=i: self.set_page(idx))
            sl.addWidget(btn); self.nav.append(btn); self.stack.addWidget(page)
        sl.addStretch()
        footer = QLabel("Uses the same champion,\nSQLite memory & checkpoints."); footer.setObjectName("Subtle"); footer.setWordWrap(True); sl.addWidget(footer)
        main.addWidget(sidebar); main.addWidget(self.stack, 1)
        self.setCentralWidget(shell); self.set_page(0)

    def set_page(self, idx):
        self.stack.setCurrentIndex(idx)
        for i, btn in enumerate(self.nav): btn.setChecked(i == idx)

    def closeEvent(self, event):
        if self.process.running and not self._close_when_finished:
            choice = QMessageBox.question(
                self,
                "Evolution is running",
                "Stop DarwinChess safely and close Studio when it reaches the safe boundary?",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if choice != QMessageBox.Yes:
                event.ignore()
                return
            self._close_when_finished = True
            self.process.stop_safely()
            event.ignore()
            return
        if self.process.running:
            event.ignore()
            return
        self.agent.close()
        super().closeEvent(event)

    def _finish_pending_close(self, _exit_code):
        if self._close_when_finished:
            self._close_when_finished = False
            self.close()


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("DarwinChess Studio")
    app.setStyleSheet(APP_QSS)
    window = MainWindow(); window.show()
    return app.exec()
