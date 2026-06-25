# Gobblet — Training Guide

Command-line guide for training, monitoring, evaluating, and playing the
AlphaZero-style model. See `docs/game-rules.md` for the rules and
`plans/training-plan.md` for the design decisions.

## Prerequisites

One-time setup (local venv, never global pip):

```bash
python3 -m venv .venv          # or: virtualenv -p python3 .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

Requires PyTorch with a GPU for practical training. Supported GPUs:
NVIDIA CUDA or Apple Silicon (M3/M4) via Metal (MPS). The device is
auto-detected (CUDA → MPS → CPU). Verify:

```bash
# NVIDIA:
python -c "import torch; print(torch.cuda.is_available())"          # True on the RTX 3060
# Apple Silicon:
python -c "import torch; print(torch.backends.mps.is_available())"  # True on M3/M4
```

All commands below assume the venv is activated (`. .venv/bin/activate`).

## Train

Start a fresh training run (self-play → train → eval → checkpoint, repeated):

```bash
python -m gobblet.train --run-dir runs/gobblet-v1 --max-iters 3
```

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--run-dir DIR` | `runs/default` | output directory (checkpoints, logs, TensorBoard) |
| `--max-iters N` | 20 | stop after N iterations |
| `--resume DIR` | — | resume an interrupted run from a run directory |
| `--seed N` | 0 | RNG seed |
| `--smoke` | off | tiny config for a fast end-to-end sanity check |

Expected throughput on the RTX 3060: **~28 min/iteration**, ~7h for 15
iterations. Each iteration produces ~40k self-play samples, runs 1000 gradient
steps, then plays an arena match vs the previous best checkpoint.

### What gets written

```
runs/gobblet-v1/
  ckpt_iter0.pt      # per-iteration checkpoint (weights + optimizer + cfg)
  ckpt_iter1.pt
  ...
  best.pt            # copy of the latest accepted checkpoint
  replay.pt          # 50k-sample FIFO replay buffer
  state.json         # iteration count, Elo history, LR, timing
  train.log          # one line per phase (self-play / train / eval)
  tensorboard/       # scalars: losses, win-rates, Elo, lr
```

Checkpoint writes are atomic (write to `.tmp`, rename) — a crash never leaves a
corrupt checkpoint.

## Monitor

### Tail the text log

```bash
tail -f runs/gobblet-v1/train.log
```

Example lines:

```
--- Iteration 1 ---
[self-play] 39812 samples in 1584.2s (buffer: 50000)
[train] 1000 steps in 5.3s (policy_loss=1.42 value_loss=0.09)
[eval] vs previous: win-rate=61.0% in 0.4s
[eval] checkpoint ACCEPTED as best
```

### TensorBoard

In a second terminal:

```bash
. .venv/bin/activate
tensorboard --logdir runs/gobblet-v1/tensorboard --port 6006
```

Open `http://localhost:6006`. Scalars tracked:

- `train/policy_loss`, `train/value_loss`, `train/total_loss`
- `eval/winrate_vs_prev`, `eval/elo`
- `gate_c/random_winrate`, `gate_c/greedy_winrate`

### Check progress without starting TensorBoard

```bash
python -c "import json; s=json.load(open('runs/gobblet-v1/state.json')); print(s)"
```

Key fields: `iteration`, `accepted_iter` (which iteration became `best.pt`),
`gate_c_history`, `elo_history`.

## Continue / resume

Resume an interrupted or completed run — loads the latest checkpoint, replay
buffer, and state.json, then continues from the next iteration:

```bash
python -m gobblet.train --resume runs/gobblet-v1 --max-iters 3
```

`--max-iters` is the **total** target, not additional. If the run already
reached `--max-iters`, bump it higher to continue:

```bash
python -m gobblet.train --resume runs/gobblet-v1 --max-iters 3
```

## Evaluate

Run the current best model against a baseline (outside the training loop):

```bash
# vs greedy-1-ply
python -m gobblet.arena --ckpt runs/gobblet-v1/best.pt --opponent greedy --n-games 200

# vs random
python -m gobblet.arena --ckpt runs/gobblet-v1/best.pt --opponent random --n-games 100
```

Output: `MCTS vs greedy: 146W / 8D / 46L (win rate: 75.0%)`.

## Play against the model

Interactive CLI game:

```bash
python -m gobblet.play --ckpt runs/gobblet-v1/best.pt
```

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--ckpt PATH` | required | checkpoint to play against (usually `best.pt`) |
| `--color red\|blue` | blue | your color (red moves first) |
| `--sims N` | 128 | MCTS simulations per model move (higher = stronger/slower) |

### Move format

Cells are 0–8, row-major:

```
0 1 2
3 4 5
6 7 8
```

- Place: `p <S|M|L> <cell>`  →  e.g. `p S 0` places a Small piece on cell 0
- Move:  `m <from> <to>`     →  e.g. `m 0 1` moves the top piece from cell 0 to cell 1
- Quit:  `q`

Example session:

```
=== Gobblet — You are Blue, model is Red ===
Commands: 'p <S|M|L> <cell>' to place, 'm <from> <to>' to move

Red's turn (ply 0):
  .  |  .  |  .
-----------------
  .  |  .  |  .
-----------------
  .  |  .  |  .
Red tray: S=2 M=2 L=2
Blue tray: S=2 M=2 L=2

Model thinking...
Model plays: Place(size=S,to=0)

Blue's turn (ply 1):
  RS |  .  |  .
...
Your move: p M 4
```

## Quick smoke test

Verify the full pipeline (self-play → train → checkpoint) runs end-to-end in
under a minute with a tiny config — useful after code changes:

```bash
python -m gobblet.train --smoke --run-dir runs/smoke --max-iters 1
```

## Test suite

The Python engine and pipeline tests (port of the JS tests + new edge cases):

```bash
python -m pytest            # all 100 tests
python -m pytest tests/test_game.py        # engine + draw rules
python -m pytest tests/test_mcts.py        # MCTS
python -m pytest -k selfplay               # self-play + replay
```

## Tips

- **First run is noisiest**: iteration 0 self-plays with a random-initialized
  net. Policy/value losses drop sharply over iterations 1–3 as the buffer fills.
- **Checkpoint ladder**: every `ckpt_iterN.pt` is a saved strength level. To
  play a specific iteration instead of the best, pass its path to `--ckpt`.
- **If training stalls** (win-rate vs prev < 55% for 2 iterations), the loop
  auto step-downs the LR by 3×. Two more step-downs land at ~1e-4.
- **GPU vs CPU**: CPU is fine for tests and `--smoke`; GPU is required for
  real training (CPU would be ~50× slower).
