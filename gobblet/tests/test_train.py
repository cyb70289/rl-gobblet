"""Tests for the training loop (smoke test: 1 iteration with tiny config)."""
import sys
import time
from pathlib import Path

import torch

from gobblet.config import Config
from gobblet.train import Trainer


def test_trainer_one_iteration_smoke(tmp_path):
    """Run 1 full iteration (self-play → train → eval → checkpoint) with tiny config."""
    cfg = Config.for_smoke()
    cfg.max_iters = 1
    cfg.run_dir = str(tmp_path / "test_run")
    cfg.eval.prev_vs_new_games = 4  # skip prev eval on iter 0

    trainer = Trainer(cfg)
    trainer.run()

    # Check checkpoint was saved
    run = Path(cfg.run_dir)
    assert (run / "ckpt_iter0.pt").exists()
    assert (run / "state.json").exists()
    assert (run / "replay.pt").exists()

    # Check state.json has iteration info
    import json
    state = json.loads((run / "state.json").read_text())
    assert state["iteration"] >= 1


def test_trainer_resume(tmp_path):
    """Resume from a checkpoint and run another iteration."""
    cfg = Config.for_smoke()
    cfg.max_iters = 1
    cfg.run_dir = str(tmp_path / "test_resume")
    cfg.eval.prev_vs_new_games = 4

    trainer = Trainer(cfg)
    trainer.run()

    # Resume with max_iters=2
    cfg.max_iters = 2
    trainer2 = Trainer(cfg)
    trainer2.resume(cfg.run_dir)
    trainer2.run()

    import json
    state = json.loads((Path(cfg.run_dir) / "state.json").read_text())
    assert state["iteration"] >= 2
