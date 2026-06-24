"""All hyperparameters in one place (plan Q5-Q13)."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field


@dataclass
class NetConfig:
    in_planes: int = 21
    filters: int = 64
    blocks: int = 6
    policy_filters: int = 32
    value_filters: int = 32
    value_hidden: int = 64
    num_actions: int = 99


@dataclass
class MCTSConfig:
    simulations: int = 128
    c_puct: float = 1.0
    dirichlet_alpha: float = 0.3
    dirichlet_weight: float = 0.25
    temperature_plies: int = 10     # tau=1 for first N plies, then 0
    virtual_loss: float = 1.0
    eval_simulations: int = 128     # sims used in arena eval


@dataclass
class SelfPlayConfig:
    games_per_iter: int = 1000
    concurrent_games: int = 64


@dataclass
class TrainConfig:
    buffer_size: int = 50_000
    batch_size: int = 256
    steps_per_iter: int = 1000
    lr: float = 1e-3
    weight_decay: float = 1e-4
    grad_clip: float = 1.0
    value_loss_weight: float = 0.5
    policy_target_eps: float = 1e-6   # for visit-count normalization stability


@dataclass
class EvalConfig:
    prev_vs_new_games: int = 100
    accept_threshold: float = 0.55
    gate_c_random_games: int = 100
    gate_c_greedy_games: int = 200
    gate_c_greedy_winrate: float = 0.70


@dataclass
class Config:
    net: NetConfig = field(default_factory=NetConfig)
    mcts: MCTSConfig = field(default_factory=MCTSConfig)
    selfplay: SelfPlayConfig = field(default_factory=SelfPlayConfig)
    train: TrainConfig = field(default_factory=TrainConfig)
    eval: EvalConfig = field(default_factory=EvalConfig)
    run_dir: str = "runs/default"
    seed: int = 0
    max_iters: int = 20
    time_budget_hours: float = 24.0

    def device(self) -> str:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        return "cpu"

    @classmethod
    def for_smoke(cls) -> "Config":
        """Tiny config for fast smoke tests / end-to-end checks."""
        c = cls()
        c.net.filters = 32
        c.net.blocks = 2
        c.mcts.simulations = 4
        c.mcts.eval_simulations = 4
        c.selfplay.games_per_iter = 4
        c.selfplay.concurrent_games = 4
        c.train.buffer_size = 200
        c.train.batch_size = 16
        c.train.steps_per_iter = 2
        c.eval.prev_vs_new_games = 4
        c.eval.gate_c_random_games = 4
        c.eval.gate_c_greedy_games = 4
        c.max_iters = 1
        return c


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-dir", default=None, help="run output directory")
    parser.add_argument("--device", default=None, help="cuda | cpu (auto-detect if omitted)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--smoke", action="store_true", help="use tiny smoke config")


def config_from_args(args) -> Config:
    if getattr(args, "smoke", False):
        c = Config.for_smoke()
    else:
        c = Config()
    if getattr(args, "run_dir", None):
        c.run_dir = args.run_dir
    if getattr(args, "seed", None) is not None:
        c.seed = args.seed
    return c
