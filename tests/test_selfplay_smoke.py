"""Tests for replay buffer and self-play smoke."""
import torch
import pytest

from gobblet.config import Config
from gobblet.game import State, Action, Game, RED, BLUE, S
from gobblet.net import GobbletNet
from gobblet.encoding import state_to_tensor, action_to_index, NUM_ACTIONS
from gobblet.replay import ReplayBuffer
from gobblet.selfplay import SelfPlayRunner


# ============ replay buffer ============
def test_replay_buffer_add_and_len():
    buf = ReplayBuffer(max_size=100)
    assert len(buf) == 0
    sample = (
        state_to_tensor(State.initial()),  # state tensor (21,3,3)
        torch.zeros(NUM_ACTIONS),           # policy target (99,)
        0.0,                                 # value target
    )
    buf.add(sample)
    assert len(buf) == 1


def test_replay_buffer_fifo_eviction():
    buf = ReplayBuffer(max_size=3)
    for i in range(5):
        st = State.initial()
        buf.add((state_to_tensor(st), torch.zeros(NUM_ACTIONS), float(i)))
    assert len(buf) == 3  # only last 3 retained
    # values should be 2.0, 3.0, 4.0 (FIFO evicted 0.0 and 1.0)
    values = [s[2] for s in buf.samples]
    assert sorted(values) == [2.0, 3.0, 4.0]


def test_replay_buffer_sample_batch():
    buf = ReplayBuffer(max_size=100)
    for i in range(10):
        st = State.initial()
        buf.add((state_to_tensor(st), torch.zeros(NUM_ACTIONS), float(i)))
    batch = buf.sample(batch_size=4)
    states, policies, values = batch
    assert states.shape == (4, 21, 3, 3)
    assert policies.shape == (4, 99)
    assert values.shape == (4,)


def test_replay_buffer_sample_more_than_available():
    buf = ReplayBuffer(max_size=100)
    buf.add((state_to_tensor(State.initial()), torch.zeros(99), 0.0))
    buf.add((state_to_tensor(State.initial()), torch.zeros(99), 1.0))
    batch = buf.sample(batch_size=4)
    # should sample with replacement or return all available
    states, policies, values = batch
    assert states.shape[0] == 4  # padded with replacement


def test_replay_buffer_save_load(tmp_path):
    buf = ReplayBuffer(max_size=100)
    for i in range(5):
        buf.add((state_to_tensor(State.initial()), torch.zeros(99), float(i)))
    p = tmp_path / "replay.pt"
    buf.save(p)
    buf2 = ReplayBuffer.load(p)
    assert len(buf2) == len(buf)
    # compare stored values directly (not random samples)
    v1 = sorted(s[2] for s in buf.samples)
    v2 = sorted(s[2] for s in buf2.samples)
    assert v1 == v2


# ============ self-play smoke ============
def test_selfplay_produces_valid_samples():
    cfg = Config.for_smoke()
    cfg.selfplay.games_per_iter = 2
    cfg.selfplay.concurrent_games = 2
    cfg.mcts.simulations = 4
    net = GobbletNet(cfg.net)
    runner = SelfPlayRunner(cfg, net)
    samples = runner.run(num_games=2)
    # each sample is (state_tensor, policy_target, value_target)
    assert len(samples) > 0
    for state_t, policy_t, value_t in samples:
        assert state_t.shape == (21, 3, 3)
        assert policy_t.shape == (99,)
        assert policy_t.sum().item() > 0  # non-empty policy
        assert -1.0 <= value_t <= 1.0


def test_selfplay_sample_count_matches_games():
    cfg = Config.for_smoke()
    cfg.selfplay.games_per_iter = 4
    cfg.selfplay.concurrent_games = 4
    cfg.mcts.simulations = 4
    net = GobbletNet(cfg.net)
    runner = SelfPlayRunner(cfg, net)
    samples = runner.run(num_games=4)
    # each game produces at least 1 sample (a game has >= 2 plies)
    # total samples should be at least 4 * 2 = 8
    assert len(samples) >= 8


def test_selfplay_policy_targets_are_normalized():
    cfg = Config.for_smoke()
    cfg.selfplay.games_per_iter = 2
    cfg.selfplay.concurrent_games = 2
    cfg.mcts.simulations = 8
    net = GobbletNet(cfg.net)
    runner = SelfPlayRunner(cfg, net)
    samples = runner.run(num_games=2)
    for _, policy_t, _ in samples:
        assert abs(policy_t.sum().item() - 1.0) < 1e-4 or policy_t.sum().item() == 0


def test_selfplay_value_targets_are_terminal():
    """All value targets should be +1, -1, or 0 (terminal results)."""
    cfg = Config.for_smoke()
    cfg.selfplay.games_per_iter = 2
    cfg.selfplay.concurrent_games = 2
    cfg.mcts.simulations = 4
    net = GobbletNet(cfg.net)
    runner = SelfPlayRunner(cfg, net)
    samples = runner.run(num_games=2)
    for _, _, value_t in samples:
        assert value_t in (-1.0, 0.0, 1.0)
