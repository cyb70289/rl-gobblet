"""Port of ui/tests/*.test.js + new edge cases (draws, value, both-win).

Python engine API (size-based place, per plan):
  RED=0, BLUE=1 ; S=0, M=1, L=2
  State.initial() -> State
  state.apply(Action) -> State   (immutable, returns new state)
  state.legal_actions() -> tuple[Action]
  state.top_at(cell) -> Optional[tuple[color,size]]
  state.stack_at(cell) -> tuple[(color,size), ...]
  state.tray_count(color, size) -> int
  state.current_player -> int
  state.winner -> Optional[int]
  state.is_draw -> bool
  state.is_terminal() -> bool
  state.value_for_current() -> float  (terminal only: +1 win, -1 lose, 0 draw)
  state.find_winning_lines() -> dict[int, list[(cells, sizes)]]
  state.winning_cells() -> list[int]
  state.position_key -> hashable (board + trays + player, for repetition)
  Action.place(size, to) ; Action.move(from_, to)

  Game(state) : mutable self-play driver enforcing 3-fold repetition draw.
  game.apply(action) ; game.is_terminal() ; game.value_for_current()
"""
import pytest
from gobblet.game import State, Action, RED, BLUE, S, M, L, Game, MAX_PLY


# ---- helpers (sequencing assumes alternating turns) ----
def place(st, color, size, cell):
    assert st.current_player == color, f"not {color}'s turn"
    a = Action.place(size, cell)
    new = st.apply(a)
    assert new is not None, "place returned None"
    return new


def move(st, from_, to):
    a = Action.move(from_, to)
    return st.apply(a)


# =================== initial state ===================
def test_initial_state():
    st = State.initial()
    assert st.current_player == RED
    assert st.winner is None
    assert not st.is_terminal()
    for cell in range(9):
        assert st.top_at(cell) is None
        assert st.stack_at(cell) == ()
    for c in (RED, BLUE):
        for sz in (S, M, L):
            assert st.tray_count(c, sz) == 2
    assert st.ply == 0


# =================== place ===================
def test_place_basic():
    st = State.initial()
    st = place(st, RED, S, 0)
    top = st.top_at(0)
    assert top == (RED, S)
    assert st.tray_count(RED, S) == 1
    assert st.tray_count(BLUE, S) == 2
    assert st.current_player == BLUE
    assert st.winner is None
    assert not st.is_terminal()


def test_place_removes_a_size_piece():
    st = State.initial()
    assert st.tray_count(RED, S) == 2
    st = place(st, RED, S, 0)
    assert st.tray_count(RED, S) == 1  # one S used, one remains


# =================== place cover rules ===================
def test_place_cover_larger_over_smaller_any_color():
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, L, 0)  # blue L covers red S
    assert st.top_at(0) == (BLUE, L)
    assert st.stack_at(0) == ((RED, S), (BLUE, L))


def test_place_cannot_cover_same_size():
    st = State.initial()
    st = place(st, RED, S, 0)
    # blue's turn; blue S cannot cover red S
    new = st.apply(Action.place(S, 0))
    assert new is None  # illegal
    assert st.current_player == BLUE  # turn did not pass (st unchanged)
    assert st.top_at(0) == (RED, S)


def test_place_cannot_cover_larger():
    st = State.initial()
    st = place(st, RED, M, 0)
    new = st.apply(Action.place(S, 0))  # blue S cannot cover red M
    assert new is None
    assert st.current_player == BLUE
    assert st.top_at(0) == (RED, M)


def test_place_requires_size_in_tray():
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 4)
    st = place(st, RED, S, 1)  # red uses 2nd S
    # red now has 0 S in tray; not red's turn anyway (blue). Move a couple turns:
    st = place(st, BLUE, S, 5)  # blue uses 2nd S
    # red's turn, red has no S; trying to place S must fail
    new = st.apply(Action.place(S, 2))
    assert new is None


def test_place_cell_out_of_range():
    st = State.initial()
    assert st.apply(Action.place(S, -1)) is None
    assert st.apply(Action.place(S, 9)) is None
    assert st.current_player == RED  # unchanged


# =================== move ===================
def test_move_relocates_own_top_to_empty():
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 4)
    st = move(st, 0, 1)
    assert st.top_at(0) is None
    assert st.top_at(1) == (RED, S)
    assert st.current_player == BLUE


def test_move_can_cover_smaller_at_dest():
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 4)
    st = place(st, RED, M, 1)
    st = place(st, BLUE, M, 4)
    # red's turn: move red M from 1 -> 0 covering red S
    st = move(st, 1, 0)
    assert st.top_at(0) == (RED, M)
    assert st.stack_at(0) == ((RED, S), (RED, M))
    assert st.top_at(1) is None


def test_move_cannot_from_empty():
    st = State.initial()
    new = st.apply(Action.move(0, 1))
    assert new is None
    assert st.current_player == RED


def test_move_cannot_move_opponent_top():
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 4)
    # red's turn: try to move blue's piece at cell 4
    new = st.apply(Action.move(4, 1))
    assert new is None
    assert st.current_player == RED


def test_move_cannot_same_cell():
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 4)
    new = st.apply(Action.move(0, 0))
    assert new is None
    assert st.current_player == RED
    assert st.top_at(0) == (RED, S)


def test_move_cannot_cover_same_or_larger():
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 4)
    new = st.apply(Action.move(0, 4))  # red S onto blue S -> same size
    assert new is None
    assert st.current_player == RED


def test_move_only_top_piece_covered_exposed():
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 4)
    st = place(st, RED, M, 0)  # red M covers red S at 0
    st = place(st, BLUE, M, 4)
    # red's turn: move cell 0 -> moves TOP (red M), exposes red S
    st = move(st, 0, 1)
    assert st.top_at(0) == (RED, S)
    assert st.top_at(1) == (RED, M)


def test_move_allowed_even_with_tray_pieces():
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 4)
    assert st.tray_count(RED, S) == 1 and st.tray_count(RED, M) == 2
    st = move(st, 0, 1)
    assert st.tray_count(RED, S) == 1  # move doesn't change tray


# =================== win detection ===================
def test_win_row_SML():
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 3)
    st = place(st, RED, M, 1)
    st = place(st, BLUE, S, 5)
    st = place(st, RED, L, 2)
    assert st.winner == RED
    assert st.is_terminal()
    assert sorted(st.winning_cells()) == [0, 1, 2]


def test_win_row_LMS_reverse():
    st = State.initial()
    st = place(st, RED, L, 0)
    st = place(st, BLUE, S, 3)
    st = place(st, RED, M, 1)
    st = place(st, BLUE, S, 5)
    st = place(st, RED, S, 2)
    assert st.winner == RED
    assert sorted(st.winning_cells()) == [0, 1, 2]


def test_win_col_SML():
    st = State.initial()
    st = place(st, RED, S, 2)
    st = place(st, BLUE, S, 0)
    st = place(st, RED, M, 5)
    st = place(st, BLUE, M, 3)
    st = place(st, RED, M, 8)
    st = place(st, BLUE, L, 6)
    assert st.winner == BLUE
    assert sorted(st.winning_cells()) == [0, 3, 6]


def test_win_diag_main():
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 7)
    st = place(st, RED, M, 4)
    st = place(st, BLUE, M, 6)
    st = place(st, RED, L, 8)
    assert st.winner == RED
    assert sorted(st.winning_cells()) == [0, 4, 8]


def test_win_antidiag_LMS():
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, L, 2)
    st = place(st, RED, S, 1)
    st = place(st, BLUE, M, 4)
    st = place(st, RED, M, 8)
    st = place(st, BLUE, S, 6)
    assert st.winner == BLUE
    assert sorted(st.winning_cells()) == [2, 4, 6]


def test_win_covered_does_not_count():
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 3)
    st = place(st, RED, M, 1)
    st = place(st, BLUE, L, 1)  # blue L covers red M at 1
    st = place(st, RED, L, 2)
    assert st.winner is None
    assert not st.is_terminal()
    assert st.winning_cells() == []


def test_win_mixed_colors_no_win():
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, M, 1)
    st = place(st, RED, L, 2)
    assert st.winner is None


def test_win_wrong_order_no_win():
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 3)
    st = place(st, RED, L, 1)
    st = place(st, BLUE, S, 5)
    st = place(st, RED, M, 2)  # row 0 = S, L, M -> not monotonic
    assert st.winner is None


def test_game_locked_after_win():
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 3)
    st = place(st, RED, M, 1)
    st = place(st, BLUE, S, 5)
    st = place(st, RED, L, 2)
    assert st.winner == RED
    assert st.apply(Action.place(L, 4)) is None  # blue place rejected
    assert st.apply(Action.move(3, 4)) is None   # blue move rejected


def test_find_winning_lines_reports_both_colors():
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 3)
    st = place(st, RED, M, 1)
    st = place(st, BLUE, S, 5)
    st = place(st, RED, L, 2)
    lines = st.find_winning_lines()
    assert any(c == (0, 1, 2) and s == (S, M, L) for (c, s) in lines[RED])
    assert lines[BLUE] == []


# =================== resolution (move-based) ===================
def test_move_completes_own_line_mover_wins():
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 5)
    st = place(st, RED, M, 1)
    st = place(st, BLUE, M, 7)
    st = place(st, RED, L, 4)
    st = place(st, BLUE, M, 6)
    # red's turn: move red L from 4 -> 2 completing row 0 S-M-L
    st = move(st, 4, 2)
    assert st.winner == RED
    assert sorted(st.winning_cells()) == [0, 1, 2]


def test_move_uncovers_opponent_line_opponent_wins():
    # blue S@3, M@4, L@5 row 1; blue M@4 hidden under red L@4
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 3)
    st = place(st, RED, M, 1)
    st = place(st, BLUE, M, 4)
    st = place(st, RED, L, 4)   # red L covers blue M at 4
    st = place(st, BLUE, L, 5)
    # red's turn: move red L 4 -> 8, uncovers blue M -> blue row 1 S-M-L
    st = move(st, 4, 8)
    assert st.winner == BLUE
    assert sorted(st.winning_cells()) == [3, 4, 5]


def test_move_both_win_opponent_wins():
    # red move L 4->2 completes red row0 AND uncovers blue row1 -> blue wins
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 3)
    st = place(st, RED, M, 1)
    st = place(st, BLUE, M, 4)
    st = place(st, RED, L, 4)   # red L covers blue M at 4
    st = place(st, BLUE, L, 5)
    st = move(st, 4, 2)
    assert st.winner == BLUE  # opponent of mover wins
    lines = st.find_winning_lines()
    assert len(lines[RED]) >= 1
    assert len(lines[BLUE]) >= 1


# =================== legal actions (size-based) ===================
def test_legal_initial_27_place_actions():
    st = State.initial()
    actions = st.legal_actions()
    places = [a for a in actions if a.kind == "place"]
    moves = [a for a in actions if a.kind == "move"]
    assert len(places) == 27  # 3 sizes x 9 cells
    assert len(moves) == 0
    # each size can target all 9 cells
    for sz in (S, M, L):
        targets = {a.to for a in places if a.size == sz}
        assert targets == set(range(9))


def test_legal_after_red_S_26_place():
    st = State.initial()
    st = place(st, RED, S, 0)
    actions = st.legal_actions()
    places = [a for a in actions if a.kind == "place"]
    moves = [a for a in actions if a.kind == "move"]
    assert len(moves) == 0
    # blue S cannot target cell 0 (cover same size); M and L can
    s_targets = {a.to for a in places if a.size == S}
    assert 0 not in s_targets
    assert s_targets == set(range(9)) - {0}
    bigger_targets = {a.to for a in places if a.size in (M, L)}
    assert 0 in bigger_targets
    # total = 8 + 9 + 9 = 26
    assert len(places) == 26


def test_legal_includes_moves_excludes_invalid():
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 4)
    actions = st.legal_actions()
    moves = [a for a in actions if a.kind == "move"]
    assert any(a.from_ == 0 and a.to == 1 for a in moves)  # 0->1 empty legal
    assert not any(a.from_ == 0 and a.to == 0 for a in moves)  # same cell
    assert not any(a.from_ == 0 and a.to == 4 for a in moves)  # cover same-size


def test_legal_every_action_playable():
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, M, 4)
    st = place(st, RED, M, 1)
    # blue's turn
    for a in st.legal_actions():
        new = st.apply(a)
        assert new is not None, f"action {a} not playable"


def test_legal_empty_when_over():
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 3)
    st = place(st, RED, M, 1)
    st = place(st, BLUE, S, 5)
    st = place(st, RED, L, 2)
    assert st.winner == RED
    assert st.legal_actions() == ()


# =================== value for current player ===================
def test_value_after_red_win_blue_to_move_is_loss():
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 3)
    st = place(st, RED, M, 1)
    st = place(st, BLUE, S, 5)
    st = place(st, RED, L, 2)
    # red won; it is now (terminal) blue's "turn" -> blue loses
    assert st.current_player == BLUE
    assert st.value_for_current() == -1.0


def test_value_after_blue_win_red_to_move_is_loss():
    st = State.initial()
    st = place(st, RED, S, 2)
    st = place(st, BLUE, S, 0)
    st = place(st, RED, M, 5)
    st = place(st, BLUE, M, 3)
    st = place(st, RED, M, 8)
    st = place(st, BLUE, L, 6)
    assert st.winner == BLUE
    assert st.current_player == RED
    assert st.value_for_current() == -1.0


# =================== draws (new) ===================
def test_ply_cap_draw_via_synthetic_state():
    # Build a synthetic state at ply = MAX_PLY-1 with a non-winning move available.
    import dataclasses
    st = State.initial()
    # add two harmless pieces (no lines) by replaying 2 plies
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 8)
    # fast-forward ply to MAX_PLY-1 (synthetic; engine doesn't validate ply/board consistency)
    st = dataclasses.replace(st, ply=MAX_PLY - 1, player=RED)
    # a non-winning move: 0 -> 1
    new = st.apply(Action.move(0, 1))
    assert new.ply == MAX_PLY
    assert new.winner is None
    assert new.is_draw is True
    assert new.is_terminal()
    assert new.value_for_current() == 0.0


def test_position_key_excludes_ply_and_winner():
    st = State.initial()
    k0 = st.position_key
    st2 = place(st, RED, S, 0)
    assert st2.position_key != k0  # board changed


def test_game_threefold_repetition_is_draw():
    # Cycle a position 3 times via reversible moves -> 3-fold draw.
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 8)
    g = Game(st)
    # red 0->1, blue 8->7, red 1->0, blue 7->8  (one cycle, back to start pos)
    # After 2 full cycles the start position has occurred 3 times -> draw.
    for _ in range(2):
        g.apply(Action.move(0, 1))
        g.apply(Action.move(8, 7))
        g.apply(Action.move(1, 0))
        g.apply(Action.move(7, 8))
    assert g.is_terminal(), "expected 3-fold repetition draw"
    assert g.state.is_draw
    assert g.value_for_current() == 0.0


def test_game_win_takes_precedence_over_repetition():
    # A winning move should win, not draw, even if it repeats a position.
    st = State.initial()
    st = place(st, RED, S, 0)
    st = place(st, BLUE, S, 8)
    st = place(st, RED, M, 1)
    st = place(st, BLUE, S, 7)
    # red has L in tray; place L at 2 -> red row0 S-M-L win
    g = Game(st)
    g.apply(Action.place(L, 2))
    assert g.state.winner == RED
    assert not g.state.is_draw
    assert g.value_for_current() == -1.0  # blue to move loses
