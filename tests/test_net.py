"""Tests for net.py: shapes, masking, value range, batched eval."""
import torch

from gobblet.config import NetConfig, Config
from gobblet.net import GobbletNet
from gobblet.game import State, Action, S
from gobblet.encoding import state_to_tensor, states_to_batch, legal_mask, NUM_ACTIONS


def _default_cfg():
    return NetConfig()


def test_forward_shapes():
    cfg = _default_cfg()
    net = GobbletNet(cfg)
    x = torch.randn(8, cfg.in_planes, 3, 3)
    policy_logits, value = net(x)
    assert policy_logits.shape == (8, NUM_ACTIONS)
    assert value.shape == (8, 1)


def test_value_in_range():
    cfg = _default_cfg()
    net = GobbletNet(cfg)
    net.eval()
    x = torch.randn(4, cfg.in_planes, 3, 3)
    _, value = net(x)
    assert (value >= -1.0).all() and (value <= 1.0).all()


def test_policy_logits_not_nan():
    cfg = _default_cfg()
    net = GobbletNet(cfg)
    net.eval()
    x = torch.randn(4, cfg.in_planes, 3, 3)
    policy_logits, _ = net(x)
    assert not torch.isnan(policy_logits).any()


def test_apply_illegal_mask_sets_logits_to_neg_inf():
    cfg = _default_cfg()
    net = GobbletNet(cfg)
    net.eval()
    st = State.initial()
    x = state_to_tensor(st).unsqueeze(0)
    mask = legal_mask(st).unsqueeze(0)
    logits, _ = net(x)
    masked = net.apply_illegal_mask(logits, mask)
    # illegal positions are -inf
    illegal = ~mask[0]
    assert torch.isinf(masked[0, illegal]).all()
    assert (masked[0, illegal] < 0).all()
    # legal positions are finite
    assert torch.isfinite(masked[0, mask[0]]).all()


def test_policy_softmax_over_legal_sums_to_one():
    cfg = _default_cfg()
    net = GobbletNet(cfg)
    net.eval()
    st = State.initial()
    x = state_to_tensor(st).unsqueeze(0)
    mask = legal_mask(st).unsqueeze(0)
    logits, _ = net(x)
    probs = net.policy_probs(logits, mask)
    # sums to ~1 over the 27 legal actions
    assert abs(probs.sum().item() - 1.0) < 1e-4
    # illegal are zero
    assert (probs[0, ~mask[0]] == 0).all()


def test_forward_on_real_state():
    cfg = _default_cfg()
    net = GobbletNet(cfg)
    net.eval()
    st = State.initial()
    x = state_to_tensor(st).unsqueeze(0)
    logits, value = net(x)
    assert logits.shape == (1, 99)
    assert value.shape == (1, 1)


def test_parameter_count_small():
    cfg = _default_cfg()
    net = GobbletNet(cfg)
    n_params = sum(p.numel() for p in net.parameters())
    # expect a few hundred K; sanity bounds
    assert 50_000 < n_params < 2_000_000


def test_smoke_config_net_forward():
    cfg = Config.for_smoke().net
    net = GobbletNet(cfg)
    x = torch.randn(4, cfg.in_planes, 3, 3)
    logits, value = net(x)
    assert logits.shape == (4, 99)
    assert value.shape == (4, 1)


def test_save_load_roundtrip(tmp_path):
    cfg = _default_cfg()
    net = GobbletNet(cfg)
    st = State.initial()
    x = state_to_tensor(st).unsqueeze(0)
    out_before, _ = net(x)
    p = tmp_path / "net.pt"
    net.save(p)
    net2 = GobbletNet(cfg)
    net2.load(p)
    out_after, _ = net2(x)
    assert torch.allclose(out_before, out_after, atol=1e-5)


def test_eval_batch_no_grad():
    cfg = _default_cfg()
    net = GobbletNet(cfg)
    net.eval()
    states = [State.initial(), State.initial().apply(Action.place(S, 0))]
    x = states_to_batch(states)
    with torch.no_grad():
        logits, value = net(x)
    assert logits.shape == (2, 99)
    assert value.shape == (2, 1)
