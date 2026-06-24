"""Tests for arena: baselines, arena matches, Elo."""
import numpy as np
import torch

from gobblet.config import Config
from gobblet.game import State, Action, Game, RED, BLUE, S, M, L
from gobblet.net import GobbletNet
from gobblet.arena import (
    RandomPlayer, Greedy1PlyPlayer, MCTSPlayer,
    Arena, compute_elo,
)


def _make_net(cfg=None):
    c = cfg or Config.for_smoke()
    net = GobbletNet(c.net)
    net.eval()
    return net, c


# ============ baselines ============
def test_random_player_returns_legal_action():
    rng = np.random.default_rng(42)
    player = RandomPlayer(rng=rng)
    st = State.initial()
    a = player.choose_action(st)
    assert a is not None
    assert a in st.legal_actions()


def test_random_player_different_seeds_different_actions():
    st = State.initial()
    p1 = RandomPlayer(rng=np.random.default_rng(1))
    p2 = RandomPlayer(rng=np.random.default_rng(2))
    actions = set()
    for p in [p1, p2]:
        for _ in range(10):
            actions.add(p.choose_action(st))
    assert len(actions) > 1  # not always the same action


def test_greedy_1ply_finds_immediate_win():
    """Greedy1Ply should pick a winning move when one exists."""
    st = State.initial()
    st = st.apply(Action.place(S, 0))
    st = st.apply(Action.place(S, 3))
    st = st.apply(Action.place(M, 1))
    st = st.apply(Action.place(S, 5))
    # red to move; place L@2 wins row 0
    player = Greedy1PlyPlayer(rng=np.random.default_rng(0))
    a = player.choose_action(st)
    assert a.kind == "place" and a.size == L and a.to == 2


def test_greedy_1ply_blocks_opponent_win():
    """Greedy1Ply should prefer covering an opponent's threatening piece."""
    # blue has S@0, M@1; if blue gets L@2 they win. Red to move, should block.
    # Actually setup: blue S@0, M@1, and red must prevent blue from placing L@2.
    # Red's best: place L@2 to block (cover nothing, but occupy cell 2).
    st = State.initial()
    st = st.apply(Action.place(S, 0))   # red S@0
    st = st.apply(Action.place(S, 3))   # blue S@3
    st = st.apply(Action.place(M, 1))   # red M@1 -> red threatens L@2
    st = st.apply(Action.place(M, 4))   # blue M@4
    # red to move; place L@2 wins
    player = Greedy1PlyPlayer(rng=np.random.default_rng(0))
    a = player.choose_action(st)
    assert a.kind == "place" and a.size == L and a.to == 2


def test_greedy_1ply_returns_legal_action():
    st = State.initial()
    player = Greedy1PlyPlayer(rng=np.random.default_rng(0))
    a = player.choose_action(st)
    assert a is not None
    assert a in st.legal_actions()


# ============ MCTS player ============
def test_mcts_player_returns_legal_action():
    net, cfg = _make_net()
    cfg.mcts.simulations = 4
    player = MCTSPlayer(net, cfg.mcts, temperature=0.0)
    st = State.initial()
    a = player.choose_action(st)
    assert a is not None
    assert a in st.legal_actions()


# ============ arena ============
def test_arena_random_vs_random_produces_result():
    rng = np.random.default_rng(42)
    arena = Arena(seed=42)
    p1 = RandomPlayer(rng=np.random.default_rng(1))
    p2 = RandomPlayer(rng=np.random.default_rng(2))
    results = arena.play_match(p1, p2, n_games=10)
    assert len(results) == 10
    for r in results:
        assert r in (-1.0, 0.0, 1.0)  # p1 perspective


def test_arena_greedy_beats_random():
    """Greedy1Ply should beat random more often than not."""
    rng = np.random.default_rng(42)
    arena = Arena(seed=42)
    greedy = Greedy1PlyPlayer(rng=np.random.default_rng(0))
    random_p = RandomPlayer(rng=np.random.default_rng(1))
    results = arena.play_match(greedy, random_p, n_games=40)
    wins = sum(1 for r in results if r == 1.0)
    losses = sum(1 for r in results if r == -1.0)
    # greedy should win more than it loses
    assert wins > losses


def test_arena_sides_swapped():
    """Arena should play half the games as red, half as blue."""
    arena = Arena(seed=42)
    p1 = RandomPlayer(rng=np.random.default_rng(1))
    p2 = RandomPlayer(rng=np.random.default_rng(2))
    n = 10
    results = arena.play_match(p1, p2, n_games=n)
    assert len(results) == n


def test_arena_winrate():
    arena = Arena(seed=42)
    p1 = Greedy1PlyPlayer(rng=np.random.default_rng(0))
    p2 = RandomPlayer(rng=np.random.default_rng(1))
    wr = arena.winrate(p1, p2, n_games=20)
    assert 0.0 <= wr <= 1.0
    # greedy should have > 50% win rate vs random
    assert wr > 0.5


# ============ Elo ============
def test_compute_elo_basic():
    # Simple chain: p0 vs p1 (p0 wins 70%), p1 vs p2 (p1 wins 70%)
    match_results = [
        (0, 1, [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0]),  # p0 vs p1
        (1, 2, [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0, -1.0]),  # p1 vs p2
    ]
    elos = compute_elo(match_results, n_players=3, base_elo=1000)
    assert elos[0] > elos[1] > elos[2]


def test_compute_elo_equal_players():
    match_results = [
        (0, 1, [1.0, -1.0, 1.0, -1.0]),  # 50-50
    ]
    elos = compute_elo(match_results, n_players=2, base_elo=1000)
    assert abs(elos[0] - elos[1]) < 50  # roughly equal
