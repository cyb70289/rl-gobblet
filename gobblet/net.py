"""AlphaZero-style ResNet for Gobblet: policy (99 logits) + value (tanh, [-1,1]).

Architecture (plan Q7):
  stem: Conv(21->f, 3x3, pad=1) -> BN -> ReLU
  body: N residual blocks [Conv3x3(f->f)->BN->ReLU -> Conv3x3(f->f)->BN -> +skip -> ReLU]
  policy head: Conv3x3(f->pf)->BN->ReLU -> flatten(pf*9) -> Linear(pf*9 -> 99)
  value head:  Conv3x3(f->vf)->BN->ReLU -> flatten(vf*9) -> Linear(vf*9 -> vh) -> ReLU
               -> Linear(vh -> 1) -> tanh
"""
from __future__ import annotations

from pathlib import Path

import torch
import torch.nn as nn

from .config import NetConfig
from .encoding import NUM_ACTIONS


class ResBlock(nn.Module):
    def __init__(self, filters: int):
        super().__init__()
        self.conv1 = nn.Conv2d(filters, filters, 3, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(filters)
        self.conv2 = nn.Conv2d(filters, filters, 3, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(filters)

    def forward(self, x):
        identity = x
        out = torch.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        out = out + identity
        return torch.relu(out)


class GobbletNet(nn.Module):
    def __init__(self, cfg: NetConfig):
        super().__init__()
        self.cfg = cfg
        f = cfg.filters
        self.stem = nn.Sequential(
            nn.Conv2d(cfg.in_planes, f, 3, padding=1, bias=False),
            nn.BatchNorm2d(f),
            nn.ReLU(inplace=True),
        )
        self.body = nn.Sequential(*[ResBlock(f) for _ in range(cfg.blocks)])
        pf = cfg.policy_filters
        self.policy_conv = nn.Conv2d(f, pf, 3, padding=1, bias=False)
        self.policy_bn = nn.BatchNorm2d(pf)
        self.policy_fc = nn.Linear(pf * 3 * 3, NUM_ACTIONS)
        vf = cfg.value_filters
        self.value_conv = nn.Conv2d(f, vf, 3, padding=1, bias=False)
        self.value_bn = nn.BatchNorm2d(vf)
        self.value_fc1 = nn.Linear(vf * 3 * 3, cfg.value_hidden)
        self.value_fc2 = nn.Linear(cfg.value_hidden, 1)

    def forward(self, x):
        h = self.body(self.stem(x))
        # policy
        p = torch.relu(self.policy_bn(self.policy_conv(h)))
        p = p.flatten(1)
        logits = self.policy_fc(p)
        # value
        v = torch.relu(self.value_bn(self.value_conv(h)))
        v = v.flatten(1)
        v = torch.relu(self.value_fc1(v))
        value = torch.tanh(self.value_fc2(v))
        return logits, value

    @staticmethod
    def apply_illegal_mask(logits: torch.Tensor, legal_mask: torch.Tensor) -> torch.Tensor:
        # legal_mask: (B, NUM_ACTIONS) bool
        neg_inf = torch.full_like(logits, float("-inf"))
        return torch.where(legal_mask, logits, neg_inf)

    @staticmethod
    def policy_probs(logits: torch.Tensor, legal_mask: torch.Tensor) -> torch.Tensor:
        masked = GobbletNet.apply_illegal_mask(logits, legal_mask)
        return torch.softmax(masked, dim=1)

    def save(self, path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({"state_dict": self.state_dict(), "cfg": self.cfg}, path)

    def load(self, path) -> None:
        ckpt = torch.load(path, map_location="cpu", weights_only=False)
        self.load_state_dict(ckpt["state_dict"])
