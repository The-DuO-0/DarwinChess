from __future__ import annotations

from datetime import datetime
from pathlib import Path

import chess
import chess.pgn
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
                               QListWidget, QMessageBox, QPushButton, QVBoxLayout, QWidget)

from ..backend import AgentBridge
from ..data import state_dir
from ..widgets.chessboard import ChessBoardWidget


class PlayPage(QWidget):
    def __init__(self, agent: AgentBridge, parent=None):
        super().__init__(parent)
        self.agent = agent
        self.board = chess.Board()
        self.human_color = chess.WHITE
        self.pending_move = None
        self.last_move = None
        self.game = None
        self.node = None

        root = QVBoxLayout(self)
        head = QHBoxLayout()
        title = QLabel("Play champion"); title.setObjectName("SectionTitle")
        self.status = QLabel("Ready"); self.status.setObjectName("Subtle")
        head.addWidget(title); head.addStretch(); head.addWidget(self.status)
        root.addLayout(head)

        body = QHBoxLayout()
        self.board_widget = ChessBoardWidget()
        self.board_widget.move_requested.connect(self._clicked_move)
        body.addWidget(self.board_widget, 3)

        side = QFrame(); side.setObjectName("Panel"); side.setMinimumWidth(300)
        sl = QVBoxLayout(side)
        sl.addWidget(QLabel("You play"))
        self.color = QComboBox(); self.color.addItems(["White", "Black"]); sl.addWidget(self.color)
        row = QHBoxLayout()
        self.new_btn = QPushButton("New game"); self.new_btn.setObjectName("Primary")
        self.new_btn.clicked.connect(self.new_game)
        self.flip_btn = QPushButton("Flip board"); self.flip_btn.clicked.connect(self.flip_board)
        row.addWidget(self.new_btn); row.addWidget(self.flip_btn); sl.addLayout(row)
        self.resign_btn = QPushButton("Resign"); self.resign_btn.setObjectName("Danger"); self.resign_btn.clicked.connect(self.resign)
        sl.addWidget(self.resign_btn)
        sl.addWidget(QLabel("Move history"))
        self.history = QListWidget(); sl.addWidget(self.history, 1)
        self.fen = QLabel(); self.fen.setWordWrap(True); self.fen.setTextInteractionFlags(Qt.TextSelectableByMouse); self.fen.setObjectName("Subtle")
        sl.addWidget(QLabel("FEN")); sl.addWidget(self.fen)
        self.saved = QLabel("Human games are saved as PGN by Studio and are never added to replay automatically.")
        self.saved.setWordWrap(True); self.saved.setObjectName("Subtle"); sl.addWidget(self.saved)
        body.addWidget(side, 1)
        root.addLayout(body, 1)

        self.agent.move_ready.connect(self._ai_move_ready)
        self.agent.error.connect(self._agent_error)
        self.new_game()

    def _new_pgn(self):
        self.game = chess.pgn.Game()
        self.game.headers["Event"] = "DarwinChess Studio Human vs Champion"
        self.game.headers["Date"] = datetime.now().strftime("%Y.%m.%d")
        self.game.headers["White"] = "Human" if self.human_color == chess.WHITE else "DarwinChess Champion"
        self.game.headers["Black"] = "DarwinChess Champion" if self.human_color == chess.WHITE else "Human"
        self.node = self.game

    def new_game(self):
        if self.board.move_stack and not self.board.is_game_over() and self.pending_move is None:
            # Keep interaction lightweight; simply archive the unfinished game.
            self._save_pgn("*")
        self.board = chess.Board()
        self.last_move = None
        self.pending_move = None
        self.human_color = chess.WHITE if self.color.currentText() == "White" else chess.BLACK
        self._new_pgn()
        self.history.clear()
        self.board_widget.set_flipped(self.human_color == chess.BLACK)
        self._refresh_board()
        if self.board.turn != self.human_color:
            self._request_ai_move()

    def flip_board(self):
        self.board_widget.set_flipped(not self.board_widget.flipped)

    def resign(self):
        if not self.board.move_stack or self.board.is_game_over():
            return
        result = "0-1" if self.human_color == chess.WHITE else "1-0"
        self.game.headers["Termination"] = "Human resigned"
        self._finish(result)

    def _clicked_move(self, from_name: str, to_name: str):
        if self.pending_move or self.board.turn != self.human_color or self.board.is_game_over():
            return
        promotion = None
        if to_name.endswith("?"):
            promotion = self._choose_promotion()
            if promotion is None:
                return
            to_name = to_name[:-1] + promotion
        uci = from_name + to_name
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            return
        if move not in self.board.legal_moves:
            return
        san = self.board.san(move)
        self._push_move(move, san, "You")
        if self.board.is_game_over():
            self._finish(self.board.result(claim_draw=True))
        else:
            self._request_ai_move()

    def _choose_promotion(self):
        dlg = QDialog(self); dlg.setWindowTitle("Promote pawn")
        layout = QVBoxLayout(dlg); layout.addWidget(QLabel("Choose promotion piece"))
        combo = QComboBox(); combo.addItem("Queen", "q"); combo.addItem("Rook", "r"); combo.addItem("Bishop", "b"); combo.addItem("Knight", "n")
        layout.addWidget(combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); buttons.accepted.connect(dlg.accept); buttons.rejected.connect(dlg.reject); layout.addWidget(buttons)
        return combo.currentData() if dlg.exec() == QDialog.Accepted else None

    def _push_move(self, move: chess.Move, san: str, who: str):
        self.board.push(move)
        self.node = self.node.add_variation(move)
        self.last_move = move
        self.history.addItem(f"{who}: {san}")
        self.history.scrollToBottom()
        self._refresh_board()

    def _request_ai_move(self):
        self.status.setText("Champion is thinking…")
        self.board_widget.set_user_enabled(False)
        self.pending_move = self.agent.request_move(self.board.fen())

    def _ai_move_ready(self, rid: str, move_text: str):
        if rid != self.pending_move:
            return
        self.pending_move = None
        try:
            try:
                move = chess.Move.from_uci(move_text.strip().lower())
            except ValueError:
                move = self.board.parse_san(move_text.strip())
            if move not in self.board.legal_moves:
                raise ValueError(f"Champion returned illegal move: {move_text}")
            san = self.board.san(move)
            self._push_move(move, san, "DarwinChess")
        except Exception as exc:
            QMessageBox.critical(self, "Champion move error", str(exc))
            self.status.setText("Move error")
            self.board_widget.set_user_enabled(True)
            return
        if self.board.is_game_over():
            self._finish(self.board.result(claim_draw=True))
        else:
            self.status.setText("Your move")
            self.board_widget.set_user_enabled(True)

    def _agent_error(self, rid, message):
        if rid == self.pending_move:
            self.pending_move = None
            self.status.setText("Champion error")
            self.board_widget.set_user_enabled(True)
            QMessageBox.critical(self, "DarwinChess error", message)

    def _refresh_board(self):
        self.board_widget.set_board(self.board, self.last_move)
        self.board_widget.set_user_enabled(self.pending_move is None and self.board.turn == self.human_color and not self.board.is_game_over())
        self.fen.setText(self.board.fen())
        if not self.pending_move and not self.board.is_game_over():
            self.status.setText("Your move" if self.board.turn == self.human_color else "Champion to move")

    def _save_pgn(self, result: str):
        if self.game is None:
            return None
        self.game.headers["Result"] = result
        folder = state_dir() / "studio_games"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"human_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.pgn"
        with path.open("w", encoding="utf-8") as fh:
            print(self.game, file=fh, end="\n\n")
        return path

    def _finish(self, result: str):
        path = self._save_pgn(result)
        self.status.setText(f"Game over: {result}")
        self.board_widget.set_user_enabled(False)
        QMessageBox.information(self, "Game over", f"Result: {result}\nSaved: {path}")
