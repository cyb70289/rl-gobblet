# Gobblet — UI Guide

A web UI for the Gobblet game. Two modes:

- **Human vs Human** — manual play. Pure browser, no server.
- **Human vs Model** — play against the trained model from
  `model/gobblet.pt`. Served by `gobblet/webui.py` (a small FastAPI
  process that also hosts the static files).

## Files

UI code lives under `ui/`:

- `ui/index.html` — markup; loads `game.js` then `app.js` as plain `<script>` tags.
- `ui/styles.css` — all styling. Visual constants (cell size, piece radii, colors)
  are CSS variables in `:root` — change visuals there, not in JS.
- `ui/game.js` — **pure game logic**, no DOM. Exposes `window.GobbletGame` (UMD:
  also works under Node `require`). Reusable by the trainer and the server.
- `ui/app.js` — UI controller; imports nothing, calls `GobbletGame` directly.
- `ui/package.json` — JS package config (jsdom is the only dev dep; `npm test`
  runs the JS test suite).

Server code lives under `gobblet/`:

- `gobblet/webui.py` — FastAPI server (entry point `python -m gobblet.webui`).
  Exposes `GET /api/health` and `POST /api/move` and serves the static files
  from `ui/` by default.

> Architecture rule: keep `ui/game.js` DOM-free and framework-agnostic. All UI
> concerns live in `ui/app.js` + `ui/styles.css` + `ui/index.html`. The server
> in `gobblet/webui.py` reuses the same `State`/`Action`/`MCTS` types the
> trainer uses; it does **not** depend on the DOM.

## GobbletGame API (used by app.js)

`GobbletGame.create()` returns a game instance. Key methods:

- `currentPlayer` / `winner` — getters (`'red'` | `'blue'` | `null`).
- `isGameOver()`, `canUndo()`.
- `topAt(cell)`, `stackAt(cell)`, `tray(color)` — board/tray reads.
- `place(pieceId, cell)`, `move(fromCell, toCell)` — return `{ok, reason}`;
  advance turn and resolve wins internally.
- `undo()` — snapshot-based revert (one step).
- `winningCells()` — the 3 cells of the winning line (empty if no winner).
- `legalDestinationsForTrayPiece(pieceId)`, `legalDestinationsForBoardCell(cell)`
  — used by the UI to highlight valid destinations.
- `legalActions()` — full move list (used by tests; used by the server too).
- `serializeState()` — returns the wire-format JSON the server consumes.
  See [Wire format](#wire-format) below.

Cell indexing: 0-8, row-major (0=top-left, 8=bottom-right).

## app.js structure

Single IIFE. Key points:

- **Game state**: `game` (the `GobbletGame` instance) + `selected` (currently
  selected piece or cell, or `null`).
- **UI state**: `mode` (`'manual'` | `'model'`), `humanColor` (`'red'` | `'blue'`,
  only relevant in model mode), `modelAvailable` (boolean from health check),
  `modelThinking` (request in flight), `lastError` (current banner message,
  if any), `requestSeq` (counter to discard stale model responses).
- **Selection model**: click a tray piece or an own top piece on the board to
  select; click a valid destination to place/move; click the selected item
  again to deselect; click an invalid destination to flash + keep selection.
  Clicks are ignored while `modelThinking` is true.
- **Rendering**: `render()` is the single full re-render. Called after every
  state change. Cheap on a 3×3 board; no virtual DOM needed.
- **Piece visuals**: `buildPieceSvg(piecesOuterFirst)` draws a stack as
  concentric circles. Input order is **outer-first** (top of stack = largest =
  outermost ring). `shade(color, depthFromTop)` darkens covered pieces.
- **Tray order**: `sortedTray(color)` sorts by size S→M→L for stable layout.

## Model mode

The topbar adds three new controls (in the middle of the bar):

- **Mode select** — `Human vs Human` (default) or `Human vs Model`.
- **Color picker** — visible only in model mode. `You are: Red (first)` or
  `You are: Blue (second)`. The model plays the other color.
- **Model status** — a small pill showing `model: ready`, `model: thinking…`,
  `model: not available`, or `checking…`.

When the page loads it fetches `GET /api/health`. If the server is down or
the model isn't loaded, the `Human vs Model` option is disabled (shown as
`Human vs Model (offline)`) and a tooltip-equivalent label tells the user.
Manual mode still works fully.

Switching the mode or color always **restarts the game**. There is no
"continue the existing game" path — a fresh state avoids any ambiguity
about which color the human is.

Every **model** move plays a short "shine" animation: the originating
element pulses once with a gold glow (0.5s), the state changes
instantly, then the destination cell pulses once more (0.5s). Human
moves are applied instantly with no animation — the player already
knows what they did. Clicks, undo, and mode switches are ignored
while the animation is in progress. `Restart` is never disabled and cancels
any in-flight animation.

In model mode, when it's the model's turn, the page fires
`POST /api/move`, the turn label changes to `<Color> is thinking…`, and
the cells get a `.locked` class (no clicks register). When the response
arrives, the action is applied to `game.js` via `place()` or `move()`:

- For a `place` action, the page picks the first available piece ID of the
  matching color and size from the model's tray (the server doesn't know
  piece IDs).
- For a `move` action, the page calls `game.move(from, to)`.

If the action is rejected by `game.js` (e.g., a state drift bug), or the
server returns a 5xx, an error banner appears, the model is disabled for
the rest of the session, and the page is left in the human's last-moved
state. The user can `Undo` back to their own turn or click `Restart`.

`Undo` in model mode pops up to two plies per click — the model's most
recent move and, if it exists, the human's preceding move. After the
pop, the model is **not** auto-fired; the page waits for the human to
make the next move. In manual mode, `Undo` still pops one ply per
click. The `Undo` button is disabled while a model request is in flight
or while a shine animation is in progress.

The end-game banner says "You win!" / "Model wins!" in model mode
(based on `humanColor` vs `winner`); in manual mode it stays
"Red wins!" / "Blue wins!".

## Wire format

The server is **stateless across requests**. The page sends the full game
state on every model move, the server runs a fresh MCTS, and returns the
chosen action.

**Request** (`POST /api/move`):
```json
{
  "state": {
    "board": [[], [[0,1]], [[1,0],[0,0]], [], [], [], [], [], []],
    "trays": [2, 2, 2, 2, 2, 2],
    "player": 0,
    "ply": 3,
    "winner": null,
    "is_draw": false
  },
  "modelColor": 0
}
```
- `board[i]` is a list of `[color, size]` pairs (color ∈ {0,1}, size ∈ {0,1,2})
  ordered bottom → top.
- `trays[k]` is the count where `k = color*3 + size` (0=RS, 1=RM, 2=RL, 3=BS,
  4=BM, 5=BL).
- `player` ∈ {0, 1}, 0 = red (who moves first per rules).
- `winner` ∈ {0, 1, null}.
- `is_draw` is always `false` from the browser (the manual page doesn't
  implement 3-fold repetition).
- `modelColor` is the color the server should play — must equal
  `state.player` (the server rejects mismatches with 400).

**Response**:
```json
{
  "action": {"kind": "place", "to": 4, "size": 1}
}
```
or
```json
{
  "action": {"kind": "move", "from_": 0, "to": 4}
}
```

## Server (`gobblet/webui.py`)

```bash
python -m gobblet.webui --ckpt model/gobblet.pt [--port 8000] [--host 127.0.0.1] [--sims 200] [--smoke] [--static-dir ui]
```

- `--ckpt` — path to a trained checkpoint. The model architecture is
  `GobbletNet(Config().net)`. Required unless `--smoke` is set.
- `--port` / `--host` — defaults `8000` / `127.0.0.1`.
- `--sims` — MCTS simulations per model move. Default 200, matches `play.py`.
  Ignored with `--smoke` (always 4).
- `--smoke` — use `Config.for_smoke()` (tiny model, 4 sims) and skip loading
  the checkpoint. Useful for development. The server logs
  `SMOKE mode (random init): sims=4, device=...` at startup.
- `--static-dir` — directory containing the static files (default `ui/`).

The server loads the model eagerly at startup and exits with a clear
error if the checkpoint is missing. The first `/api/move` request has
no cold-start penalty.

Static files are served from the `--static-dir` directory (default `ui/`,
relative to the current working directory) by the same FastAPI process.
CORS is not configured (same origin).

## Tests

`cd ui && npm test` runs the JS tests; `.venv/bin/python -m pytest gobblet/tests/`
runs the Python tests.

- `ui/tests/*.test.js` — pure logic tests of `ui/game.js` via `node:test`,
  zero external deps. These are the contract for `ui/game.js`.
- `ui/tests/ui.smoke.test.js` — loads the real `index.html` + `game.js` +
  `app.js` into jsdom and simulates clicks. Verifies both manual play
  (place, move, win display, undo, restart, invalid-click flash) and
  model play (mode toggle, health check, fetch, action application,
  undo re-think, 5xx error handling, server-down handling). Mocks
  `window.fetch` to avoid needing a real server. **Requires jsdom**
  (`npm install` once in `ui/`).
- `gobblet/tests/test_webui.py` — Python tests for the server using
  FastAPI's `TestClient` and a freshly-initialized smoke `GobbletNet`.
  Verifies `/api/health` shape, `/api/move` legality/illegal-state
  coverage, static file serving.

## Adding features (typical paths)

- **New visual cue** → `ui/styles.css` + a class toggle in `ui/app.js`'s `render()`.
- **New control button** → markup in `ui/index.html`, handler in `ui/app.js`,
  state stays in `game` if it touches game state.
- **New server endpoint** → handler in `gobblet/webui.py`'s `create_app`,
  with tests in `gobblet/tests/test_webui.py` using `TestClient`.
- **New game rule** → add a failing logic test in `ui/tests/`, implement in
  `ui/game.js`, then update `ui/app.js` only if the UI surface changes.

See `docs/game-rules.md` for the rules themselves,
`docs/model.md` for the training pipeline, and
`docs/train.md` for command-line recipes.
