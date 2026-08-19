from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget

from ..backend import AgentBridge


class ChatPage(QWidget):
    def __init__(self, agent: AgentBridge, parent=None):
        super().__init__(parent)
        self.agent = agent; self.pending = None
        root = QVBoxLayout(self)
        title = QLabel("Talk to DarwinChess"); title.setObjectName("SectionTitle"); root.addWidget(title)
        note = QLabel("This is the chess-native language layer backed by DarwinChess's real lifetime memory."); note.setObjectName("Subtle"); root.addWidget(note)
        self.chat = QTextEdit(); self.chat.setReadOnly(True); root.addWidget(self.chat, 1)
        row = QHBoxLayout(); self.input = QLineEdit(); self.input.setPlaceholderText("Ask about its games, learning, or the current position…")
        self.send = QPushButton("Send"); self.send.setObjectName("Primary"); self.send.clicked.connect(self.submit); self.input.returnPressed.connect(self.submit)
        row.addWidget(self.input, 1); row.addWidget(self.send); root.addLayout(row)
        self.agent.talk_ready.connect(self._ready); self.agent.error.connect(self._error)

    def submit(self):
        text = self.input.text().strip()
        if not text or self.pending: return
        self.chat.append(f"<b>You</b><br>{text}<br>"); self.input.clear(); self.send.setEnabled(False)
        self.pending = self.agent.request_talk(text)

    def _ready(self, rid, text):
        if rid != self.pending: return
        self.pending = None; self.send.setEnabled(True); self.chat.append(f"<b>DarwinChess</b><br>{text}<br>")

    def _error(self, rid, text):
        if rid == self.pending:
            self.pending = None; self.send.setEnabled(True); self.chat.append(f"<b>Error</b><br>{text}<br>")
