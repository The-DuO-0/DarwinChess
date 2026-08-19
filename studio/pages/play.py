from __future__ import annotations

import chess

from PySide6.QtCore import QRectF, Signal, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..sound import MoveSoundBank


PIECES = {
    chess.KING: ("♔", "♚"),
    chess.QUEEN: ("♕", "♛"),
    chess.ROOK: ("♖", "♜"),
    chess.BISHOP: ("♗", "♝"),
    chess.KNIGHT: ("♘", "♞"),
    chess.PAWN: ("♙", "♟"),
}


class BoardWidget(QWidget):
    move_chosen = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.board = chess.Board()
        self.flipped = False
        self.selected: int | None = None
        self.last_move: chess.Move | None = None
        self.input_enabled = True
        self.setMinimumSize(560, 560)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.PointingHandCursor)

    def set_board(self, board: chess.Board, last_move: chess.Move | None = None):
        self.board = board.copy(stack=False)
        self.last_move = last_move
        self.selected = None
        self.update()

    def toggle_flip(self):
        self.flipped = not self.flipped
        self.selected = None
        self.update()

    def _square_from_xy(self, x: float, y: float) -> int | None:
        side = min(self.width(), self.height())
        ox = (self.width() - side) / 2
        oy = (self.height() - side) / 2
        if not (ox <= x < ox + side and oy <= y < oy + side):
            return None
        cell = side / 8
        file_display = int((x - ox) / cell)
        rank_display = int((y - oy) / cell)
        if self.flipped:
            file_idx = 7 - file_display
            rank_idx = rank_display
        else:
            file_idx = file_display
            rank_idx = 7 - rank_display
        return chess.square(file_idx, rank_idx)

    def mousePressEvent(self, event):
        if not self.input_enabled:
            return
        sq = self._square_from_xy(event.position().x(), event.position().y())
        if sq is None:
            return
        piece = self.board.piece_at(sq)

        if self.selected is None:
            if piece is not None and piece.color == self.board.turn:
                self.selected = sq
                self.update()
            return

        if sq == self.selected:
            self.selected = None
            self.update()
            return

        candidates = [m for m in self.board.legal_moves if m.from_square == self.selected and m.to_square == sq]
        if candidates:
            # If several promotion moves are legal, queen is the natural UI default.
            move = next((m for m in candidates if m.promotion == chess.QUEEN), candidates[0])
            self.move_chosen.emit(move.uci())
            self.selected = None
            return

        if piece is not None and piece.color == self.board.turn:
            self.selected = sq
        else:
            self.selected = None
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height())
        ox = (self.width() - side) / 2
        oy = (self.height() - side) / 2
        cell = side / 8

        light = QColor("#e6d8be")
        dark = QColor("#8b6b52")
        selected = QColor(92, 142, 255, 150)
        legal = QColor(77, 199, 132, 150)
        last = QColor(235, 197, 77, 125)
        check = QColor(226, 78, 78, 165)

        legal_targets = set()
        if self.selected is not None:
            legal_targets = {m.to_square for m in self.board.legal_moves if m.from_square == self.selected}

        checked_king = self.board.king(self.board.turn) if self.board.is_check() else None

        piece_font = QFont("Arial Unicode MS")
        piece_font.setPixelSize(max(26, int(cell * 0.68)))
        p.setFont(piece_font)

        for display_rank in range(8):
            for display_file in range(8):
                if self.flipped:
                    file_idx = 7 - display_file
                    rank_idx = display_rank
                else:
                    file_idx = display_file
                    rank_idx = 7 - display_rank
                sq = chess.square(file_idx, rank_idx)
                rect = QRectF(ox + display_file * cell, oy + display_rank * cell, cell, cell)
                p.fillRect(rect, light if (file_idx + rank_idx) % 2 == 0 else dark)

                if self.last_move and sq in (self.last_move.from_square, self.last_move.to_square):
                    p.fillRect(rect, last)
                if sq == self.selected:
                    p.fillRect(rect, selected)
                if sq == checked_king:
                    p.fillRect(rect, check)

                if sq in legal_targets:
                    p.setPen(Qt.NoPen)
                    p.setBrush(legal)
                    radius = cell * (0.13 if self.board.piece_at(sq) is None else 0.34)
                    p.drawEllipse(rect.center(), radius, radius)

                piece = self.board.piece_at(sq)
                if piece:
                    glyph = PIECES[piece.piece_type][0 if piece.color == chess.WHITE else 1]
                    # subtle outline via pen keeps glyphs visible on both square colors
                    p.setPen(QPen(QColor("#f8f8f8") if piece.color == chess.WHITE else QColor("#151515"), 1))
                    p.drawText(rect, Qt.AlignCenter, glyph)

        # Coordinates
        coord = QFont()
        coord.setPixelSize(max(9, int(cell * 0.14)))
        coord.setBold(True)
        p.setFont(coord)
        p.setPen(QColor(30, 30, 30, 160))
        for i in range(8):
            file_idx = 7 - i if self.flipped else i
            rank_idx = i if self.flipped else 7 - i
            p.drawText(QRectF(ox + i * cell + 4, oy + side - 18, cell - 6, 14), Qt.AlignLeft, chess.FILE_NAMES[file_idx])
            p.drawText(QRectF(ox + 3, oy + i * cell + 2, 18, 14), Qt.AlignLeft, str(rank_idx + 1))


class PlayPage(QWidget):
    def __init__(self, agent, parent=None):
        super().__init__(parent)
        self.agent = agent
        self.board = chess.Board()
        self.human_color = chess.WHITE
        self.pending_move_request: str | None = None
        self.game_active = False
        self.last_move: chess.Move | None = None
        self.sounds = MoveSoundBank(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 24)
        root.setSpacing(14)

        title_row = QHBoxLayout()
        title = QLabel("Play dog_matist")
        title.setObjectName("SectionTitle")
        title_row.addWidget(title)
        title_row.addStretch()
        self.state_label = QLabel("Ready for a new game")
        self.state_label.setObjectName("RunBadge")
        title_row.addWidget(self.state_label)
        root.addLayout(title_row)

        body = QHBoxLayout()
        body.setSpacing(18)
        self.board_widget = BoardWidget()
        self.board_widget.move_chosen.connect(self._human_move)
        body.addWidget(self.board_widget, 4)

        panel = QFrame()
        panel.setObjectName("Panel")
        panel.setFixedWidth(330)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(18, 18, 18, 18)
        pl.setSpacing(12)

        pl.addWidget(QLabel("New game"))
        self.color_box = QComboBox()
        self.color_box.addItems(["Play White", "Play Black"])
        pl.addWidget(self.color_box)

        self.new_btn = QPushButton("New game")
        self.new_btn.setObjectName("Primary")
        self.new_btn.setCursor(Qt.PointingHandCursor)
        self.new_btn.clicked.connect(self.new_game)
        pl.addWidget(self.new_btn)

        pl.addSpacing(8)
        self.undo_btn = QPushButton("↶  Undo full turn")
        self.resign_btn = QPushButton("Resign")
        self.abort_btn = QPushButton("Abort without saving")
        self.flip_btn = QPushButton("Flip board")
        for btn in (self.undo_btn, self.resign_btn, self.abort_btn, self.flip_btn):
            btn.setCursor(Qt.PointingHandCursor)
            pl.addWidget(btn)
        self.resign_btn.setObjectName("Danger")
        self.abort_btn.setObjectName("Danger")

        self.undo_btn.clicked.connect(self.undo_turn)
        self.resign_btn.clicked.connect(self.resign)
        self.abort_btn.clicked.connect(self.abort_game)
        self.flip_btn.clicked.connect(self.board_widget.toggle_flip)

        self.sound_check = QCheckBox("Move sounds")
        self.sound_check.setChecked(True)
        self.sound_check.toggled.connect(self._sound_toggle)
        pl.addWidget(self.sound_check)

        pl.addSpacing(12)
        pl.addWidget(QLabel("Game status"))
        self.info = QLabel("This page never adds a human game to training replay automatically.")
        self.info.setObjectName("Subtle")
        self.info.setWordWrap(True)
        pl.addWidget(self.info)
        pl.addStretch()

        help_text = QLabel("Click a piece → legal destinations light up → click a destination.\n\nUndo removes your previous move and dog_matist's reply. Abort discards this UI game.")
        help_text.setObjectName("Subtle")
        help_text.setWordWrap(True)
        pl.addWidget(help_text)
        body.addWidget(panel)
        root.addLayout(body, 1)

        self.agent.move_ready.connect(self._ai_move_ready)
        self.agent.error.connect(self._agent_error)
        self._refresh_controls()

    def _sound_toggle(self, enabled: bool):
        self.sounds.enabled = enabled

    def new_game(self):
        self.board = chess.Board()
        self.last_move = None
        self.human_color = chess.WHITE if self.color_box.currentIndex() == 0 else chess.BLACK
        self.game_active = True
        self.pending_move_request = None
        self.board_widget.flipped = self.human_color == chess.BLACK
        self.board_widget.set_board(self.board)
        self.state_label.setText("● YOUR TURN" if self.board.turn == self.human_color else "● dog_matist THINKING")
        self.info.setText("Game started. Champion snapshot is used through this UI session.")
        self._refresh_controls()
        if self.board.turn != self.human_color:
            self._request_ai_move()

    def _refresh_controls(self):
        human_turn = self.game_active and self.pending_move_request is None and self.board.turn == self.human_color
        self.board_widget.input_enabled = human_turn
        self.undo_btn.setEnabled(self.game_active and self.pending_move_request is None and len(self.board.move_stack) >= 1)
        self.resign_btn.setEnabled(self.game_active)
        self.abort_btn.setEnabled(self.game_active)

    def _human_move(self, uci: str):
        if not self.game_active or self.board.turn != self.human_color or self.pending_move_request:
            return
        try:
            move = chess.Move.from_uci(uci)
            if move not in self.board.legal_moves:
                return
        except ValueError:
            return
        was_capture = self.board.is_capture(move)
        self.board.push(move)
        self.last_move = move
        self._post_move_sound(was_capture)
        self.board_widget.set_board(self.board, move)
        if self._finish_if_over():
            return
        self._request_ai_move()

    def _request_ai_move(self):
        if not self.game_active:
            return
        self.state_label.setText("● dog_matist THINKING…")
        self.pending_move_request = self.agent.request_move(self.board.fen())
        self._refresh_controls()

    def _ai_move_ready(self, request_id: str, uci: str):
        if request_id != self.pending_move_request or not self.game_active:
            return
        self.pending_move_request = None
        try:
            move = chess.Move.from_uci(uci)
            if move not in self.board.legal_moves:
                raise ValueError(f"core returned illegal move {uci}")
            was_capture = self.board.is_capture(move)
            self.board.push(move)
            self.last_move = move
            self._post_move_sound(was_capture)
            self.board_widget.set_board(self.board, move)
        except Exception as exc:
            self.state_label.setText("● ENGINE ERROR")
            self.info.setText(str(exc))
            self._refresh_controls()
            return
        if not self._finish_if_over():
            self.state_label.setText("● YOUR TURN")
        self._refresh_controls()

    def _post_move_sound(self, was_capture: bool):
        if self.board.is_check():
            self.sounds.play("check")
        elif was_capture:
            self.sounds.play("capture")
        else:
            self.sounds.play("move")

    def _finish_if_over(self) -> bool:
        if not self.board.is_game_over(claim_draw=True):
            return False
        self.game_active = False
        result = self.board.result(claim_draw=True)
        reason = self.board.outcome(claim_draw=True)
        self.state_label.setText(f"● GAME OVER · {result}")
        self.info.setText(str(reason.termination.name).replace("_", " ").title() if reason else "Game over")
        self.sounds.play("end")
        self._refresh_controls()
        return True

    def undo_turn(self):
        if not self.game_active or self.pending_move_request:
            return
        # Return to the same human side to move when possible.
        popped = 0
        while self.board.move_stack and popped < 2:
            self.board.pop()
            popped += 1
        while self.board.move_stack and self.board.turn != self.human_color:
            self.board.pop()
        self.last_move = self.board.peek() if self.board.move_stack else None
        self.board_widget.set_board(self.board, self.last_move)
        self.state_label.setText("● YOUR TURN" if self.board.turn == self.human_color else "● dog_matist THINKING…")
        self.info.setText("Takeback applied locally. No training replay was modified.")
        self._refresh_controls()

    def resign(self):
        if not self.game_active:
            return
        answer = QMessageBox.question(self, "Resign", "Resign this game?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        self.game_active = False
        result = "0-1" if self.human_color == chess.WHITE else "1-0"
        self.state_label.setText(f"● RESIGNED · {result}")
        self.info.setText("Resignation recorded only in this UI session. This game is not inserted into training replay.")
        self.sounds.play("end")
        self._refresh_controls()

    def abort_game(self):
        if not self.game_active:
            return
        answer = QMessageBox.question(
            self,
            "Abort game",
            "Abort this game without saving it as a completed human game?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return
        self.game_active = False
        self.pending_move_request = None
        self.board = chess.Board()
        self.last_move = None
        self.board_widget.set_board(self.board)
        self.state_label.setText("● ABORTED")
        self.info.setText("Game discarded. Start a new game when you are ready.")
        self._refresh_controls()

    def _agent_error(self, request_id: str, message: str):
        if request_id != self.pending_move_request:
            return
        self.pending_move_request = None
        self.state_label.setText("● ENGINE ERROR")
        self.info.setText(message)
        self._refresh_controls()
