from __future__ import annotations

import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from .backend import AgentBridge, ProcessController
from .pages.chat import ChatPage
from .pages.dashboard import DashboardPage
from .pages.evolution import EvolutionPage
from .pages.play import PlayPage
from .pages.research import ResearchPage
from .theme import APP_QSS
from .widgets import DogMatistMascot


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("dog_matist Studio")
        self.resize(1420, 920)
        self.setMinimumSize(1120, 740)

        # Compatibility: the chess brain/state is still the existing DarwinChess install.
        # Rebranding must never silently reset ~/.darwinchess or the champion lineage.
        self.agent = AgentBridge(mode="normal", parent=self)
        self.process = ProcessController(self)
        self._close_when_finished = False
        self.process.finished.connect(self._finish_pending_close)

        shell = QWidget()
        main = QHBoxLayout(shell)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(224)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(16, 20, 16, 18)

        brand_row = QHBoxLayout()
        self.mascot = DogMatistMascot()
        brand_text = QVBoxLayout()
        brand = QLabel("dog_matist")
        brand.setObjectName("Brand")
        sub = QLabel("STUDIO 2.0 · evolution build")
        sub.setObjectName("Subtle")
        brand_text.addWidget(brand)
        brand_text.addWidget(sub)
        brand_row.addWidget(self.mascot)
        brand_row.addLayout(brand_text, 1)
        sl.addLayout(brand_row)

        self.run_badge = QLabel("● IDLE")
        self.run_badge.setObjectName("RunBadge")
        sl.addWidget(self.run_badge)
        sl.addSpacing(18)

        self.stack = QStackedWidget()
        self.pages = [
            ("Dashboard", DashboardPage(self.agent, self.process)),
            ("Play dog_matist", PlayPage(self.agent)),
            ("Evolution", EvolutionPage(self.process)),
            ("Research", ResearchPage(self.process)),
            ("Conversation", ChatPage(self.agent)),
        ]
        self.nav = []
        for i, (name, page) in enumerate(self.pages):
            btn = QPushButton(name)
            btn.setObjectName("Nav")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, idx=i: self.set_page(idx))
            sl.addWidget(btn)
            self.nav.append(btn)
            self.stack.addWidget(page)

        sl.addStretch()
        footer = QLabel("Same champion · same SQLite memory\nsame checkpoints · new interface")
        footer.setObjectName("Subtle")
        footer.setWordWrap(True)
        sl.addWidget(footer)

        main.addWidget(sidebar)
        main.addWidget(self.stack, 1)
        self.setCentralWidget(shell)
        self.set_page(0)

        self.process.stage_changed.connect(self._stage_changed)
        self.process.state_changed.connect(self._run_state_changed)

    def set_page(self, idx):
        self.stack.setCurrentIndex(idx)
        for i, btn in enumerate(self.nav):
            btn.setChecked(i == idx)

    def _run_state_changed(self, running: bool):
        self.mascot.set_busy(running)
        if not running:
            self.run_badge.setText("● IDLE")
            self.run_badge.setProperty("active", False)
            self.run_badge.style().unpolish(self.run_badge)
            self.run_badge.style().polish(self.run_badge)

    def _stage_changed(self, stage: str, detail: str):
        label = stage.upper().replace("_", " ")
        self.run_badge.setText(f"● {label}" + (f" · {detail}" if detail else ""))
        self.run_badge.setProperty("active", True)
        self.run_badge.style().unpolish(self.run_badge)
        self.run_badge.style().polish(self.run_badge)

    def closeEvent(self, event):
        if self.process.running and not self._close_when_finished:
            choice = QMessageBox.question(
                self,
                "Evolution is running",
                "Stop dog_matist safely and close Studio at the next safe boundary?",
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
    app.setApplicationName("dog_matist Studio")
    app.setStyleSheet(APP_QSS)
    window = MainWindow()
    window.show()
    return app.exec()
