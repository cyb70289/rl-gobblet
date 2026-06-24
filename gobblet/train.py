"""Training loop: self-play → train → eval → checkpoint, with resume support."""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.tensorboard import SummaryWriter

from .arena import Arena, RandomPlayer, Greedy1PlyPlayer, MCTSPlayer, compute_elo
from .config import Config
from .net import GobbletNet
from .replay import ReplayBuffer
from .selfplay import SelfPlayRunner


class Trainer:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.device = torch.device(cfg.device() if cfg.device != "cpu" else "cpu")
        if cfg.device == "cuda" and torch.cuda.is_available():
            self.device = torch.device("cuda")

        self.run_dir = Path(cfg.run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.tb_dir = self.run_dir / "tensorboard"
        self.log_path = self.run_dir / "train.log"

        self.net = GobbletNet(cfg.net).to(self.device)
        self.optimizer = torch.optim.AdamW(
            self.net.parameters(), lr=cfg.train.lr,
            weight_decay=cfg.train.weight_decay,
        )
        self.replay = ReplayBuffer(max_size=cfg.train.buffer_size)

        self.iteration = 0
        self.accepted_iter = 0
        self.elo_history: list = []   # list of (iter, elo)
        self.gate_c_history: list = []  # list of (iter, random_wr, greedy_wr)
        self.prev_best_state: dict | None = None  # state dict of previous best
        self.plateau_count = 0
        self.start_time = time.time()

        self.writer: SummaryWriter | None = None

    def _log(self, msg: str) -> None:
        print(msg, flush=True)
        with open(self.log_path, "a") as f:
            f.write(msg + "\n")

    def _save_checkpoint(self, path: Path, extra: dict | None = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        data = {
            "state_dict": self.net.state_dict(),
            "optimizer_state": self.optimizer.state_dict(),
            "iteration": self.iteration,
            "cfg": self.cfg,
        }
        if extra:
            data.update(extra)
        torch.save(data, tmp)
        os.replace(tmp, path)

    def _save_state(self) -> None:
        state = {
            "iteration": self.iteration,
            "accepted_iter": self.accepted_iter,
            "elo_history": self.elo_history,
            "gate_c_history": self.gate_c_history,
            "plateau_count": self.plateau_count,
            "lr": self.optimizer.param_groups[0]["lr"],
            "elapsed_sec": time.time() - self.start_time,
        }
        tmp = self.run_dir / "state.tmp"
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, self.run_dir / "state.json")

    def _save_best(self) -> None:
        """Copy current checkpoint as best.pt."""
        src = self.run_dir / f"ckpt_iter{self.iteration}.pt"
        dst = self.run_dir / "best.pt"
        if src.exists():
            shutil.copy2(src, dst)

    def resume(self, run_dir: str) -> None:
        """Resume from a run directory."""
        run_dir = Path(run_dir)
        ckpt_path = run_dir / "best.pt"
        if not ckpt_path.exists():
            # try latest iteration checkpoint
            ckpts = sorted(run_dir.glob("ckpt_iter*.pt"),
                           key=lambda p: int(p.stem.replace("ckpt_iter", "")))
            if ckpts:
                ckpt_path = ckpts[-1]
            else:
                raise FileNotFoundError(f"No checkpoint found in {run_dir}")

        ckpt = torch.load(ckpt_path, map_location=self.device, weights_only=False)
        self.net.load_state_dict(ckpt["state_dict"])
        self.optimizer.load_state_dict(ckpt["optimizer_state"])
        self.run_dir = run_dir
        self.tb_dir = run_dir / "tensorboard"
        self.log_path = run_dir / "train.log"

        # Load state (source of truth for iteration count and history)
        state_path = run_dir / "state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text())
            self.iteration = state.get("iteration", 0)
            self.accepted_iter = state.get("accepted_iter", 0)
            self.elo_history = state.get("elo_history", [])
            self.gate_c_history = state.get("gate_c_history", [])
            self.plateau_count = state.get("plateau_count", 0)
        else:
            self.iteration = ckpt.get("iteration", 0) + 1

        # Load replay
        replay_path = run_dir / "replay.pt"
        if replay_path.exists():
            self.replay = ReplayBuffer.load(replay_path)

        # Load previous best state dict
        if ckpt_path.name == "best.pt":
            self.prev_best_state = ckpt["state_dict"]
        else:
            best_path = run_dir / "best.pt"
            if best_path.exists():
                bk = torch.load(best_path, map_location="cpu", weights_only=False)
                self.prev_best_state = bk["state_dict"]

        self._log(f"[resume] loaded iter {self.iteration} from {ckpt_path}")

    def _train_step(self) -> tuple[float, float]:
        """One gradient step. Returns (policy_loss, value_loss)."""
        states, policies, values = self.replay.sample(self.cfg.train.batch_size)
        states = states.to(self.device)
        policies = policies.to(self.device)
        values = values.to(self.device)

        self.net.train()
        logits, value_pred = self.net(states)
        mask = policies > 0
        masked_logits = torch.where(mask, logits, torch.full_like(logits, -1e9))
        log_probs = F.log_softmax(masked_logits, dim=1)
        policy_loss = -(policies * log_probs).sum(dim=1).mean()
        value_loss = F.mse_loss(value_pred.squeeze(-1), values)
        loss = policy_loss + self.cfg.train.value_loss_weight * value_loss

        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.net.parameters(), self.cfg.train.grad_clip)
        self.optimizer.step()

        return policy_loss.item(), value_loss.item()

    def _eval_prev_vs_new(self) -> float:
        """Arena: current net vs previous best. Returns win-rate from current's perspective."""
        if self.prev_best_state is None:
            return 1.0  # auto-accept first iteration

        prev_net = GobbletNet(self.cfg.net).to(self.device)
        prev_net.load_state_dict(self.prev_best_state)
        prev_net.eval()

        cur_player = MCTSPlayer(self.net, self.cfg.mcts, temperature=0.0)
        prev_player = MCTSPlayer(prev_net, self.cfg.mcts, temperature=0.0)
        arena = Arena(seed=42)
        results = arena.play_match(cur_player, prev_player,
                                   n_games=self.cfg.eval.prev_vs_new_games)
        wr = (sum(r for r in results) / len(results) + 1) / 2
        return wr

    def _eval_gate_c(self) -> tuple[float, float]:
        """Gate C: vs random and vs greedy. Returns (random_wr, greedy_wr)."""
        arena = Arena(seed=42)
        cur_player = MCTSPlayer(self.net, self.cfg.mcts, temperature=0.0)
        random_p = RandomPlayer()
        greedy_p = Greedy1PlyPlayer()
        r_wr = arena.winrate(cur_player, random_p, n_games=self.cfg.eval.gate_c_random_games)
        cur_player.reset()
        g_wr = arena.winrate(cur_player, greedy_p, n_games=self.cfg.eval.gate_c_greedy_games)
        return r_wr, g_wr

    def run(self) -> None:
        """Main training loop."""
        self.writer = SummaryWriter(str(self.tb_dir))
        self._log(f"=== Training started: run_dir={self.run_dir} device={self.device} ===")

        while self.iteration < self.cfg.max_iters:
            elapsed = (time.time() - self.start_time) / 3600
            if elapsed > self.cfg.time_budget_hours:
                self._log(f"[time] budget {self.cfg.time_budget_hours}h exceeded, stopping")
                break

            t0 = time.time()
            self._log(f"\n--- Iteration {self.iteration} ---")

            # 1. Self-play
            self.net.eval()
            runner = SelfPlayRunner(self.cfg, self.net)
            samples = runner.run(
                num_games=self.cfg.selfplay.games_per_iter,
                show_progress=True,
            )
            self.replay.add_many(samples)
            self.replay.save(self.run_dir / "replay.pt")
            sp_time = time.time() - t0
            self._log(f"[self-play] {len(samples)} samples in {sp_time:.1f}s "
                      f"(buffer: {len(self.replay)})")

            # 2. Training
            t0 = time.time()
            total_pl, total_vl = 0.0, 0.0
            n_steps = self.cfg.train.steps_per_iter
            for step in range(n_steps):
                pl, vl = self._train_step()
                total_pl += pl
                total_vl += vl
            avg_pl = total_pl / n_steps
            avg_vl = total_vl / n_steps
            tr_time = time.time() - t0
            self._log(f"[train] {n_steps} steps in {tr_time:.1f}s "
                      f"(policy_loss={avg_pl:.4f} value_loss={avg_vl:.4f})")
            self.writer.add_scalar("train/policy_loss", avg_pl, self.iteration)
            self.writer.add_scalar("train/value_loss", avg_vl, self.iteration)
            self.writer.add_scalar("train/total_loss", avg_pl + 0.5 * avg_vl, self.iteration)

            # 3. Save checkpoint
            self._save_checkpoint(self.run_dir / f"ckpt_iter{self.iteration}.pt")

            # 4. Evaluation: prev vs new
            t0 = time.time()
            wr = self._eval_prev_vs_new()
            eval_time = time.time() - t0
            self._log(f"[eval] vs previous: win-rate={wr:.1%} in {eval_time:.1f}s")
            self.writer.add_scalar("eval/winrate_vs_prev", wr, self.iteration)

            if wr >= self.cfg.eval.accept_threshold:
                self.accepted_iter = self.iteration
                self.prev_best_state = {k: v.clone() for k, v in self.net.state_dict().items()}
                self._save_best()
                self.plateau_count = 0
                self._log(f"[eval] checkpoint ACCEPTED as best")
            else:
                self.plateau_count += 1
                self._log(f"[eval] checkpoint REJECTED (plateau_count={self.plateau_count})")
                # LR step-down on plateau
                if self.plateau_count >= 2:
                    old_lr = self.optimizer.param_groups[0]["lr"]
                    new_lr = max(old_lr / 3.0, 1e-5)
                    if new_lr < old_lr:
                        self.optimizer.param_groups[0]["lr"] = new_lr
                        self._log(f"[lr] step down {old_lr:.1e} -> {new_lr:.1e}")
                        self.plateau_count = 0

            # Elo: simple relative from accepted checkpoints
            self.elo_history.append((self.iteration, 1000 + self.accepted_iter * 50))
            self.writer.add_scalar("eval/elo", self.elo_history[-1][1], self.iteration)

            # 5. Gate C milestone check
            if (self.iteration + 1) % self.cfg.eval.milestone_every == 0:
                t0 = time.time()
                r_wr, g_wr = self._eval_gate_c()
                gc_time = time.time() - t0
                self._log(f"[gate-C] vs random={r_wr:.1%} vs greedy={g_wr:.1%} "
                          f"in {gc_time:.1f}s")
                self.gate_c_history.append((self.iteration, r_wr, g_wr))
                self.writer.add_scalar("gate_c/random_winrate", r_wr, self.iteration)
                self.writer.add_scalar("gate_c/greedy_winrate", g_wr, self.iteration)

                if (r_wr >= 0.99 and g_wr >= self.cfg.eval.gate_c_greedy_winrate):
                    self._log(f"[gate-C] PASSED! Stopping.")
                    self.iteration += 1
                    self._save_state()
                    break

            self.iteration += 1
            self._save_state()

        self._log(f"\n=== Training finished: {self.iteration} iterations, "
                  f"best=iter{self.accepted_iter} ===")
        if self.writer:
            self.writer.close()


def main():
    import argparse
    from .config import add_common_args, config_from_args

    parser = argparse.ArgumentParser(description="Gobblet AlphaZero training")
    add_common_args(parser)
    parser.add_argument("--resume", default=None, help="run directory to resume from")
    parser.add_argument("--max-iters", type=int, default=None)
    args = parser.parse_args()

    cfg = config_from_args(args)
    if args.max_iters is not None:
        cfg.max_iters = args.max_iters
    if args.resume:
        cfg.run_dir = args.resume

    if args.smoke:
        cfg.run_dir = "runs/smoke"

    trainer = Trainer(cfg)
    if args.resume:
        trainer.resume(args.resume)
    trainer.run()


if __name__ == "__main__":
    main()
