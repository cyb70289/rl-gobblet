"""Tests for mcts.py: terminal handling, visit counts, batching, tree reuse."""
import torch

from gobblet.config import Config, MCTSConfig
from gobblet.game import State, Action, RED, BLUE, S, M, L, Game
from gobblet.net import GobbletNet
from gobblet.encoding import action_to_index, index_to_action, NUM_ACTIONS
from gobblet.mcts import MCTS, batched_mcts_search


def _make_net(cfg=None):
    c = cfg or Config.for_smoke()
    net = GobbletNet(c.net)
    net.eval()
    return net, c


# ============ single-tree MCTS ============
def test_mcts_returns_visit_counts_over_legal_actions():
    net, cfg = _make_net()
    st = State.initial()
    mcts = MCTS(cfg.mcts, net)
    counts = mcts.search(st)
    # 99-dim, sums to simulations, only legal actions have nonzero counts
    assert counts.shape == (NUM_ACTIONS,)
    assert counts.sum().item() == cfg.mcts.simulations
    legal = st.legal_actions()
    legal_idx = {action_to_index(a) for a in legal}
    nonzero = set(counts.nonzero(as_tuple=True)[0].tolist())
    assert nonzero.issubset(legal_idx)


def test_mcts_terminal_state_returns_empty_counts():
    net, cfg = _make_net()
    st = State.initial()
    for a in [Action.place(S, 0), Action.place(S, 3), Action.place(M, 1),
              Action.place(S, 5), Action.place(L, 2)]:
        st = st.apply(a)
    assert st.is_terminal()
    mcts = MCTS(cfg.mcts, net)
    counts = mcts.search(st)
    assert counts.sum().item() == 0


def test_mcts_immediate_win_is_preferred():
    # set up red one-move-from-win: red S@0, M@1; placing any size at 2 wins row 0.
    net, cfg = _make_net()
    cfg = Config.for_smoke()
    cfg.mcts.simulations = 100
    net = GobbletNet(cfg.net)
    net.eval()
    st = State.initial()
    st = st.apply(Action.place(S, 0))   # red S@0
    st = st.apply(Action.place(S, 3))   # blue S@3
    st = st.apply(Action.place(M, 1))   # red M@1
    st = st.apply(Action.place(S, 5))   # blue S@5
    # red to move; placing S@2, M@2, or L@2 all complete a red row 0 (sizes ignored).
    mcts = MCTS(cfg.mcts, net)
    counts = mcts.search(st)
    winning_indices = {action_to_index(Action.place(sz, 2)) for sz in (S, M, L)}
    # the most-visited action should be a winning action
    best_idx = counts.argmax().item()
    assert best_idx in winning_indices, f"expected a winning action to be top, got {best_idx}"
    assert counts[best_idx].item() > 0


def test_mcts_tree_reuse():
    net, cfg = _make_net()
    cfg.mcts.simulations = 16
    st = State.initial()
    mcts = MCTS(cfg.mcts, net)
    counts1 = mcts.search(st)
    # pick an action, update root to reuse subtree, search the new state
    a = index_to_action(counts1.argmax().item())
    mcts.update_root(a)
    st2 = st.apply(a)
    counts2 = mcts.search(st2)
    # With tree reuse, counts = previous visits + new simulations (>= simulations)
    assert counts2.sum().item() >= cfg.mcts.simulations
    # tree reuse: root of st2 should already exist in the tree
    assert mcts.root.state.position_key == st2.position_key


def test_mcts_respects_draw_terminal():
    # if MCTS hits a draw terminal (ply cap), it should back up 0
    net, cfg = _make_net()
    import dataclasses
    st = State.initial()
    st = st.apply(Action.place(S, 0))
    st = st.apply(Action.place(S, 8))
    st = dataclasses.replace(st, ply=99, player=RED)
    mcts = MCTS(cfg.mcts, net)
    counts = mcts.search(st)
    # one move crosses ply 100 -> draw; counts should still sum to simulations
    assert counts.sum().item() == cfg.mcts.simulations


# ============ batched MCTS (multiple roots) ============
def test_batched_mcts_returns_counts_per_root():
    net, cfg = _make_net()
    cfg.mcts.simulations = 8
    states = [State.initial(), State.initial().apply(Action.place(S, 0))]
    counts_list, roots = batched_mcts_search(states, cfg.mcts, net, add_noise=True)
    assert len(counts_list) == 2
    assert len(roots) == 2
    for st, counts in zip(states, counts_list):
        assert counts.shape == (NUM_ACTIONS,)
        assert counts.sum().item() == cfg.mcts.simulations
        legal_idx = {action_to_index(a) for a in st.legal_actions()}
        nonzero = set(counts.nonzero(as_tuple=True)[0].tolist())
        assert nonzero.issubset(legal_idx)


def test_batched_mcts_handles_terminal_root():
    net, cfg = _make_net()
    cfg.mcts.simulations = 8
    st = State.initial()
    for a in [Action.place(S, 0), Action.place(S, 3), Action.place(M, 1),
              Action.place(S, 5), Action.place(L, 2)]:
        st = st.apply(a)
    assert st.is_terminal()
    counts_list, _ = batched_mcts_search([st], cfg.mcts, net, add_noise=False)
    assert counts_list[0].sum().item() == 0


# ============ choose action with temperature ============
def test_mcts_choose_action_tau_zero_is_argmax():
    net, cfg = _make_net()
    st = State.initial()
    mcts = MCTS(cfg.mcts, net)
    counts = mcts.search(st)
    a = mcts.choose_action(counts, temperature=0.0)
    assert a is not None
    assert action_to_index(a) == counts.argmax().item()


def test_mcts_choose_action_tau_one_samples_legal():
    net, cfg = _make_net()
    st = State.initial()
    mcts = MCTS(cfg.mcts, net)
    counts = mcts.search(st)
    legal_idx = {action_to_index(a) for a in st.legal_actions()}
    for _ in range(10):
        a = mcts.choose_action(counts, temperature=1.0)
        assert action_to_index(a) in legal_idx
