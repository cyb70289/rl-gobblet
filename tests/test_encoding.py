"""Tests for encoding: state<->21-plane tensor, action<->99-dim index, mask."""
import numpy as np
import torch

from gobblet.game import State, Action, RED, BLUE, S, M, L
from gobblet import encoding as E


def _st(*moves):
    """Build a state by applying (kind, ...) tuples. moves are Action objects."""
    st = State.initial()
    for a in moves:
        st = st.apply(a)
    return st


# ============ state -> tensor ============
def test_tensor_shape_and_dtype():
    st = State.initial()
    t = E.state_to_tensor(st)
    assert t.shape == (21, 3, 3)
    assert t.dtype == torch.float32


def test_initial_state_tensor_channels():
    st = State.initial()
    t = E.state_to_tensor(st).numpy()
    # channels 0..5 (stack presence) all zero
    for c in range(6):
        assert t[c].sum() == 0
    # channels 6..11 (top) all zero
    for c in range(6, 12):
        assert t[c].sum() == 0
    # channel 12 (turn): red to move -> all 1
    assert (t[12] == 1).all()
    # channel 13 (own-top): no tops -> all 0
    assert (t[13] == 0).all()
    # channel 14 (ply/100): 0
    assert (t[14] == 0).all()
    # channels 15..20 (tray counts broadcast): all 2
    for c in range(15, 21):
        assert (t[c] == 2).all()


def test_after_red_S_at_cell0():
    st = State.initial()
    st = st.apply(Action.place(S, 0))
    t = E.state_to_tensor(st).numpy()
    r, c = 0, 0  # cell 0 -> (0,0)
    # presence channel for (RED,S) = channel 0
    assert t[0, r, c] == 1
    # top channel for (RED,S) = channel 6
    assert t[6, r, c] == 1
    # turn plane (12): blue to move -> all 0
    assert (t[12] == 0).all()
    # own-top (13): player is BLUE, no blue tops -> 0
    assert (t[13] == 0).all()
    # tray plane for (RED,S) = channel 15 -> 1 (one S used); others 2
    assert (t[15] == 1).all()
    for ch in range(16, 21):
        assert (t[ch] == 2).all()


def test_covered_piece_appears_in_presence_not_top():
    st = State.initial()
    st = st.apply(Action.place(S, 0))   # red S @0
    st = st.apply(Action.place(M, 0))   # blue M covers red S @0
    t = E.state_to_tensor(st).numpy()
    r, c = 0, 0
    # presence: (RED,S) channel 0 and (BLUE,M) channel 10 both 1 at (0,0)
    assert t[0, r, c] == 1
    assert t[10, r, c] == 1
    # top: only (BLUE,M) channel 10 (top index = 6 + color*3+size = 6 + 1*3+1 = 10)
    assert t[6, r, c] == 0   # red S not top
    assert t[10, r, c] == 1  # blue M is top


def test_own_top_plane_marks_player_to_move_tops():
    # red S@0, blue S@4 -> red to move (2 plies); own-top marks red's top at cell 0
    st = State.initial()
    st = st.apply(Action.place(S, 0))
    st = st.apply(Action.place(S, 4))
    t = E.state_to_tensor(st).numpy()
    assert t[13, 0, 0] == 1   # red S top at cell 0 is own (red to move)
    assert t[13, 1, 1] == 0   # blue S top at cell 4 is not own

    # add red M@1 -> blue to move (3 plies); own-top now marks blue's top at cell 4
    st = st.apply(Action.place(M, 1))
    t = E.state_to_tensor(st).numpy()
    assert t[13, 1, 1] == 1   # blue S top at cell 4 is own (blue to move)
    assert t[13, 0, 0] == 0   # red S top at cell 0 is not own
    assert t[13, 0, 1] == 0   # red M top at cell 1 is not own


def test_ply_plane_increments():
    st = State.initial()
    st = st.apply(Action.place(S, 0))
    t = E.state_to_tensor(st).numpy()
    assert (t[14] == 1 / 100).all()
    st2 = st.apply(Action.place(S, 4))
    t2 = E.state_to_tensor(st2).numpy()
    assert (t2[14] == 2 / 100).all()


# ============ action <-> index ============
def test_action_index_place_roundtrip():
    for size in (S, M, L):
        for to in range(9):
            a = Action.place(size, to)
            idx = E.action_to_index(a)
            assert 0 <= idx < 27
            assert idx == size * 9 + to
            b = E.index_to_action(idx)
            assert b.kind == "place" and b.size == size and b.to == to


def test_action_index_move_roundtrip():
    for frm in range(9):
        for to in range(9):
            if frm == to:
                continue
            a = Action.move(frm, to)
            idx = E.action_to_index(a)
            assert 27 <= idx < 99
            b = E.index_to_action(idx)
            assert b.kind == "move" and b.from_ == frm and b.to == to


def test_index_range_covers_99():
    # all 99 indices decode to valid actions
    kinds = set()
    for idx in range(99):
        a = E.index_to_action(idx)
        kinds.add(a.kind)
        assert E.action_to_index(a) == idx
    assert kinds == {"place", "move"}


# ============ legal mask ============
def test_legal_mask_matches_legal_actions_initial():
    st = State.initial()
    mask = E.legal_mask(st)
    assert mask.shape == (99,)
    assert mask.dtype == torch.bool
    legal_idx = {E.action_to_index(a) for a in st.legal_actions()}
    true_idx = set(mask.nonzero(as_tuple=True)[0].tolist())
    assert true_idx == legal_idx
    # initial: 27 legal place actions
    assert mask.sum().item() == 27


def test_legal_mask_matches_legal_actions_complex():
    st = State.initial()
    st = st.apply(Action.place(S, 0))
    st = st.apply(Action.place(M, 4))
    st = st.apply(Action.place(M, 1))
    mask = E.legal_mask(st)
    legal_idx = {E.action_to_index(a) for a in st.legal_actions()}
    true_idx = set(mask.nonzero(as_tuple=True)[0].tolist())
    assert true_idx == legal_idx


def test_legal_mask_empty_when_terminal():
    st = State.initial()
    for a in [Action.place(S, 0), Action.place(S, 3), Action.place(M, 1),
              Action.place(S, 5), Action.place(L, 2)]:
        st = st.apply(a)
    assert st.is_terminal()
    mask = E.legal_mask(st)
    assert mask.sum().item() == 0


# ============ batched encoding ============
def test_states_to_batch_tensor():
    s1 = State.initial()
    s2 = s1.apply(Action.place(S, 0))
    batch = E.states_to_batch([s1, s2])
    assert batch.shape == (2, 21, 3, 3)
    assert batch.dtype == torch.float32
    # first is initial (turn plane all 1), second turn plane all 0
    assert (batch[0, 12] == 1).all()
    assert (batch[1, 12] == 0).all()


def test_legal_mask_batch():
    s1 = State.initial()
    s2 = s1.apply(Action.place(S, 0))
    m = E.legal_mask_batch([s1, s2])
    assert m.shape == (2, 99)
    assert m.dtype == torch.bool
    assert m[0].sum().item() == 27
    assert m[1].sum().item() == 26


# ============ completeness: distinct states -> distinct tensors ============
def test_distinct_states_distinct_tensors():
    s1 = State.initial()
    s2 = s1.apply(Action.place(S, 0))
    t1 = E.state_to_tensor(s1)
    t2 = E.state_to_tensor(s2)
    assert not torch.equal(t1, t2)


def test_states_differing_only_in_turn_distinct():
    # same board, different player to move -> turn plane + own-top differ
    s = State.initial()
    s = s.apply(Action.place(S, 0))
    s = s.apply(Action.place(S, 4))
    # now red to move; flip player only via a synthetic replace
    import dataclasses
    s_flipped = dataclasses.replace(s, player=RED if s.player == BLUE else BLUE)
    t1 = E.state_to_tensor(s)
    t2 = E.state_to_tensor(s_flipped)
    assert not torch.equal(t1, t2)


# ============ apply_index convenience ============
def test_apply_index_matches_action_apply():
    st = State.initial()
    st = st.apply(Action.place(S, 0))
    st = st.apply(Action.place(M, 4))
    for a in st.legal_actions():
        idx = E.action_to_index(a)
        via_idx = E.apply_index(st, idx)
        via_act = st.apply(a)
        assert via_idx.position_key == via_act.position_key
