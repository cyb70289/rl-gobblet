# Gobblet

A 3×3 board game with an AlphaZero-style self-play implementation:
a ResNet + MCTS learns to play from scratch, then serves as the
opponent in a browser-based UI.

## Game

Two players (red, blue) take turns placing or moving buckets on a
3×3 board. Each player has 6 pieces — 2 each of small, medium, and
large. Larger pieces cover smaller ones, and only the top piece of
each cell counts. Win by forming a line of 3 same-color tops whose
sizes are in S→M→L or L→M→S order. Red moves first. See
[docs/game-rules.md](docs/game-rules.md) for the full rules.

## Model

AlphaZero-style. A small ResNet (6 blocks, 64 filters) outputs a
99-dim policy (27 place + 72 move) and a tanh-bounded value. MCTS
with PUCT selection, Dirichlet root noise, and batched leaf
evaluation generates self-play training data. Iterations of self-play
→ SGD → arena-eval → checkpoint continue until the network beats
random ≥ 99% and a 1-ply greedy baseline ≥ 70%. See
[docs/model.md](docs/model.md) for the architecture and
[docs/train.md](docs/train.md) for the command-line recipes.

## Play in the browser

Start the server (uses the trained checkpoint at `model/gobblet.pt`):

```bash
.venv/bin/python -m gobblet.webui --ckpt model/gobblet.pt
# open http://127.0.0.1:8000/
```

The topbar lets you choose **Human vs Human** (manual) or **Human
vs Model** (against the network). When you pick the model, you also
choose your color; the model auto-plays its side, the turn label
flashes "thinking…" during MCTS, and the response is applied to the
board. See [docs/ui.md](docs/ui.md) for the full UI guide, including
the wire format used between the browser and the server.

## Run the tests

```bash
# Python (112 tests)
.venv/bin/python -m pytest

# JS (62 tests, requires Node 18+)
cd ui && npm install && npm test
```

## Layout

```
gobblet/           Python package (engine, MCTS, training, webui)
  tests/             Python tests (pytest)
ui/               Browser-side code
  index.html, app.js, game.js, styles.css
  package.json, package-lock.json
  tests/             JS tests (node --test)
docs/             Game rules, model architecture, training guide, UI guide
model/            Trained checkpoints
```
