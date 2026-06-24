# Gobblet AlphaZero — Code Architecture

## Overview

An AlphaZero-style self-play system for the 3×3 Gobblet board game. No
external AlphaZero framework — only PyTorch + NumPy. The pipeline:

```
self-play (MCTS + neural net) → replay buffer → train (SGD) → eval (arena) → checkpoint
                ↑__________________________|
```

Each **iteration**:
1. **Self-play**: play N games using MCTS guided by the current net. Record
   `(state, policy_target, value_target)` per move.
2. **Train**: sample minibatches from the FIFO replay buffer, optimize
   policy (cross-entropy) + value (MSE) heads.
3. **Eval**: arena match — new checkpoint vs previous best. Accept if
   win-rate ≥ 55%; save as `best.pt`.
4. **Gate-C probe** (every 5 iters): vs random and greedy-1-ply baselines.
   Stop when win-rate vs random ≥ 99% and vs greedy ≥ 70%.

## Key design decisions

- **Game**: 3×3 board, 12 pieces (2S/2M/2L per player). Win = 3 same-color
  tops in a line with strictly monotonic sizes (S-M-L or L-M-S). Draws via
  3-fold repetition or 100-ply cap. Value ∈ {−1, 0, +1} from
  player-to-move's view.
- **State encoding**: 21-channel (3×3) tensor — stack presence (6), tops
  (6), turn (1), own-tops (1), ply/100 (1), tray counts (6).
- **Action space**: 99-dim — 27 place(size, cell) + 72 move(from, to).
  Illegal actions masked to −∞ before softmax.
- **Network**: 6-block / 64-filter ResNet. Policy head → 99 logits; value
  head → tanh ∈ [−1, 1].
- **MCTS**: 128 sims/move, PUCT selection, Dirichlet root noise, tree reuse.
  Batched NN evaluation across concurrent games. τ=1 for first 10 plies
  (exploration), then τ=0 (greedy).
- **Self-play**: 64 concurrent games, batched leaf evaluation (one GPU
  forward pass per MCTS round across all games).
- **Training**: AdamW lr=1e-3, batch 256, 1000 steps/iter, grad-clip 1.0.
  50k FIFO replay buffer. LR step-down on plateau.
- **Device**: auto-detects CUDA (primary) or CPU (dev/tests).

## Source files

All source lives in `gobblet/`. Python tests in `gobblet/tests/`. JS tests in `ui/tests/`.

| File | Lines | Role |
|------|-------|------|
| `game.py` | 254 | Game engine: `State` (immutable frozen dataclass), `Action`, `Game` (mutable, enforces 3-fold repetition draw). Port of `game.js` + draw rules. Start here to understand rules. |
| `encoding.py` | 109 | State ↔ 21-channel tensor, action ↔ 99-dim index, legal masks. The bridge between the game engine and the neural net. |
| `net.py` | 89 | `GobbletNet`: the ResNet (stem + 6 residual blocks + policy/value heads). Forward pass returns `(logits, value)`. Includes illegal-action masking and save/load. |
| `mcts.py` | 295 | `batched_mcts_search`: AlphaZero PUCT with batched leaf evaluation, Dirichlet noise, tree reuse. `MCTS` class wraps single-tree search for arena/play. `_Node` uses lazy state creation for speed. |
| `selfplay.py` | 111 | `SelfPlayRunner`: runs N concurrent self-play games with batched MCTS, records `(state, policy, value)` samples. Temperature schedule τ=1→0. |
| `replay.py` | 57 | `ReplayBuffer`: 50k FIFO buffer with `sample(batch_size)` and `save`/`load` for resume. |
| `arena.py` | 198 | `RandomPlayer`, `Greedy1PlyPlayer`, `MCTSPlayer` (wraps MCTS for eval). `Arena.play_match` with sides swapped. `compute_elo` from match chains. |
| `train.py` | 335 | `Trainer`: the main loop (self-play → train → eval → checkpoint). Handles resume, logging (stdout + TensorBoard), LR step-down, Gate-C. Entry point: `python -m gobblet.train`. |
| `config.py` | 113 | All hyperparameters in one `Config` dataclass. `Config.for_smoke()` for fast tests. |
| `play.py` | 139 | Interactive CLI: human vs model. Entry point: `python -m gobblet.play --ckpt best.pt`. |
| `webui.py` | 200+ | FastAPI server that hosts the web UI and exposes `/api/move` / `/api/health`. Entry point: `python -m gobblet.webui --ckpt best.pt`. See `docs/ui.md`. |

## Tests

`gobblet/tests/` — 112 tests, all passing. Key suites:

| File | Tests | Covers |
|------|-------|--------|
| `test_game.py` | 40 | Port of JS tests + draws, both-win rule, value encoding |
| `test_encoding.py` | 17 | State↔tensor, action↔index, masks, completeness |
| `test_net.py` | 10 | Shapes, value range, masking, save/load |
| `test_mcts.py` | 9 | Visit counts, terminal handling, tree reuse, temperature |
| `test_selfplay_smoke.py` | 9 | Replay buffer + self-play sample validity |
| `test_arena.py` | 12 | Baselines, arena matches, Elo |
| `test_train.py` | 3 | Full iteration smoke, resume, Gate-C check |
| `test_webui.py` | 12 | FastAPI server: /api/health, /api/move, static files, validation |

JavaScript tests for the web UI live in `ui/tests/*.test.js` (logic) and `ui/tests/ui.smoke.test.js` (jsdom integration; covers both manual and model-mode wiring).

## Entry points

```bash
python -m gobblet.train --run-dir runs/gobblet-v1 --max-iters 20   # train
python -m gobblet.train --resume runs/gobblet-v1                     # continue
python -m gobblet.arena --ckpt runs/gobblet-v1/best.pt              # evaluate
python -m gobblet.play --ckpt runs/gobblet-v1/best.pt               # play (CLI)
python -m gobblet.webui --ckpt runs/gobblet-v1/best.pt              # play (browser)
```

See `docs/train.md` for the full command-line guide and `docs/ui.md` for the web UI.
