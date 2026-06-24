"""Gobblet game engine — Python port of game.js + draw rules.

Pure positional logic. The State is an immutable frozen dataclass; apply()
returns a new State (or None for illegal actions). Win detection and the
100-ply cap live in State. 3-fold repetition requires history, so it is
enforced by the Game wrapper used by self-play; MCTS handles cycle detection
along its search path.

Action encoding is size-based (per plan): Action.place(size, to) and
Action.move(from_, to). Piece identity is irrelevant to gameplay (the two
same-size pieces of a color are interchangeable), so the engine never tracks
piece ids.
"""
from __future__ import annotations

import dataclasses
from collections import Counter
from dataclasses import dataclass
from typing import Optional, Tuple

RED, BLUE = 0, 1
S, M, L = 0, 1, 2
SIZES = (S, M, L)
COLORS = (RED, BLUE)
MAX_PLY = 100

LINES = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8),   # rows
    (0, 3, 6), (1, 4, 7), (2, 5, 8),   # cols
    (0, 4, 8), (2, 4, 6),              # diagonals
)
WIN_ORDERS = ((S, M, L), (L, M, S))

CELL = Tuple[int, int]  # (color, size)


def _tray_index(color: int, size: int) -> int:
    return color * 3 + size


@dataclass(frozen=True)
class Action:
    kind: str        # "place" or "move"
    to: int
    size: int = -1   # for place
    from_: int = -1  # for move

    @classmethod
    def place(cls, size: int, to: int) -> "Action":
        return cls(kind="place", to=to, size=size)

    @classmethod
    def move(cls, from_: int, to: int) -> "Action":
        return cls(kind="move", to=to, from_=from_)

    def __repr__(self) -> str:
        if self.kind == "place":
            return f"Place(size={self.size},to={self.to})"
        return f"Move(from={self.from_},to={self.to})"


@dataclass(frozen=True)
class State:
    board: Tuple[Tuple[CELL, ...], ...]   # 9 cells, each a stack bottom->top
    trays: Tuple[int, int, int, int, int, int]  # counts: color*3+size
    player: int                            # player to move
    ply: int
    winner: Optional[int] = None
    is_draw: bool = False

    @classmethod
    def initial(cls) -> "State":
        board = tuple(() for _ in range(9))
        trays = (2, 2, 2, 2, 2, 2)
        return cls(board=board, trays=trays, player=RED, ply=0)

    # ---- accessors ----
    def top_at(self, cell: int) -> Optional[CELL]:
        st = self.board[cell]
        return st[-1] if st else None

    def stack_at(self, cell: int) -> Tuple[CELL, ...]:
        return self.board[cell]

    def tray_count(self, color: int, size: int) -> int:
        return self.trays[_tray_index(color, size)]

    @property
    def current_player(self) -> int:
        return self.player

    def is_terminal(self) -> bool:
        return self.winner is not None or self.is_draw

    def value_for_current(self) -> float:
        if self.winner is not None:
            return 1.0 if self.winner == self.player else -1.0
        if self.is_draw:
            return 0.0
        raise ValueError("state is not terminal")

    @property
    def position_key(self):
        # board + trays + player to move (excludes ply/winner for repetition)
        return (self.board, self.trays, self.player)

    # ---- winning lines ----
    def find_winning_lines(self) -> dict:
        result: dict = {RED: [], BLUE: []}
        for line in LINES:
            tops = []
            ok = True
            for c in line:
                t = self.top_at(c)
                if t is None:
                    ok = False
                    break
                tops.append(t)
            if not ok:
                continue
            color = tops[0][0]
            if any(t[0] != color for t in tops):
                continue
            sizes = tuple(t[1] for t in tops)
            if sizes not in WIN_ORDERS:
                continue
            result[color].append((tuple(line), sizes))
        return result

    def winning_cells(self) -> list:
        if self.winner is None:
            return []
        lines = self.find_winning_lines()
        if lines[self.winner]:
            return list(lines[self.winner][0][0])
        return []

    # ---- legality & apply ----
    def _can_place_on(self, size: int, cell: int) -> bool:
        st = self.board[cell]
        if not st:
            return True
        return size > st[-1][1]

    def legal_actions(self) -> Tuple[Action, ...]:
        if self.is_terminal():
            return ()
        p = self.player
        actions = []
        for sz in SIZES:
            if self.trays[_tray_index(p, sz)] > 0:
                for cell in range(9):
                    if self._can_place_on(sz, cell):
                        actions.append(Action.place(sz, cell))
        for frm in range(9):
            top = self.top_at(frm)
            if top is None or top[0] != p:
                continue
            ps = top[1]
            for to in range(9):
                if to == frm:
                    continue
                if self._can_place_on(ps, to):
                    actions.append(Action.move(frm, to))
        return tuple(actions)

    def apply(self, action: Action) -> Optional["State"]:
        if self.is_terminal():
            return None
        p = self.player
        if action.kind == "place":
            sz, cell = action.size, action.to
            if cell < 0 or cell > 8:
                return None
            if self.trays[_tray_index(p, sz)] <= 0:
                return None
            if not self._can_place_on(sz, cell):
                return None
            new_stack = self.board[cell] + ((p, sz),)
            new_board = self.board[:cell] + (new_stack,) + self.board[cell + 1:]
            new_trays = list(self.trays)
            new_trays[_tray_index(p, sz)] -= 1
            new_trays = tuple(new_trays)
            mover = p
        else:
            frm, to = action.from_, action.to
            if frm < 0 or frm > 8 or to < 0 or to > 8:
                return None
            if frm == to:
                return None
            top = self.top_at(frm)
            if top is None or top[0] != p:
                return None
            if not self._can_place_on(top[1], to):
                return None
            frm_stack = self.board[frm]
            moved = frm_stack[-1]
            new_frm = frm_stack[:-1]
            new_to = self.board[to] + (moved,)
            nb = list(self.board)
            nb[frm] = new_frm
            nb[to] = new_to
            new_board = tuple(nb)
            new_trays = self.trays
            mover = p

        new_ply = self.ply + 1
        new_player = 1 - p
        new_state = State(
            board=new_board, trays=new_trays, player=new_player,
            ply=new_ply, winner=None, is_draw=False,
        )
        wins = new_state.find_winning_lines()
        mover_wins = len(wins[mover]) > 0
        opp_wins = len(wins[1 - mover]) > 0
        if mover_wins and opp_wins:
            new_state = dataclasses.replace(new_state, winner=1 - mover)
        elif mover_wins:
            new_state = dataclasses.replace(new_state, winner=mover)
        elif opp_wins:
            new_state = dataclasses.replace(new_state, winner=1 - mover)
        elif new_ply >= MAX_PLY:
            new_state = dataclasses.replace(new_state, is_draw=True)
        return new_state


class Game:
    """Mutable self-play driver enforcing 3-fold repetition draw on top of State."""

    def __init__(self, state: Optional[State] = None):
        self.state = state if state is not None else State.initial()
        self._counts: Counter = Counter()
        self._counts[self.state.position_key] = 1

    def apply(self, action: Action) -> Optional[State]:
        new_state = self.state.apply(action)
        if new_state is None:
            return None
        if new_state.is_terminal():
            # win or ply-cap already decided; do not override with repetition
            self.state = new_state
            return new_state
        key = new_state.position_key
        self._counts[key] += 1
        if self._counts[key] >= 3:
            new_state = dataclasses.replace(new_state, is_draw=True)
        self.state = new_state
        return new_state

    def is_terminal(self) -> bool:
        return self.state.is_terminal()

    def value_for_current(self) -> float:
        return self.state.value_for_current()
