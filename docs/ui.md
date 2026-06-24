# Gobblet — UI Guide

A static, manually-playable web page for the Gobblet game. Opens directly via
`file://` (no server). Future steps will extend this UI (e.g. show the model's
best moves); this doc is the entry point for those changes.

## Files

- `index.html` — markup; loads `game.js` then `app.js` as plain `<script>` tags.
- `styles.css` — all styling. Visual constants (cell size, piece radii, colors)
  are CSS variables in `:root` — change visuals there, not in JS.
- `game.js` — **pure game logic**, no DOM. Exposes `window.GobbletGame` (UMD:
  also works under Node `require`). Reusable by the future RL trainer.
- `app.js` — UI controller; imports nothing, calls `GobbletGame` directly.

> Architecture rule: keep `game.js` DOM-free and framework-agnostic. All UI
> concerns live in `app.js` + `styles.css` + `index.html`. The RL trainer in
> later steps will reuse `game.js` verbatim — do not couple it to the DOM.

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
- `legalActions()` — full move list (used by tests; will be used by RL).

Cell indexing: 0-8, row-major (0=top-left, 8=bottom-right).

## app.js structure

Single IIFE, ~150 lines. Straightforward read; key points:

- **State**: `game` (the `GobbletGame` instance) + `selected` (currently selected
  piece or cell, or `null`). No other UI state — everything else is derived
  from `game` on each `render()`.
- **Selection model**: click a tray piece or an own top piece on the board to
  select; click a valid destination to place/move; click the selected item
  again to deselect; click an invalid destination to flash + keep selection.
- **Rendering**: `render()` is the single full re-render. Called after every
  state change. Cheap on a 3×3 board; no virtual DOM needed.
- **Piece visuals**: `buildPieceSvg(piecesOuterFirst)` draws a stack as
  concentric circles. Input order is **outer-first** (top of stack = largest =
  outermost ring). `shade(color, depthFromTop)` darkens covered pieces.
- **Tray order**: `sortedTray(color)` sorts by size S→M→L for stable layout.

## Tests

`npm test` runs all. Two kinds:

- `test/*.test.js` (44 tests) — pure logic tests of `game.js` via `node:test`,
  zero external deps. These are the contract for `game.js`.
- `test/ui.smoke.test.js` (7 tests) — loads the real `index.html` + `game.js` +
  `app.js` into jsdom and simulates clicks. Verifies the wiring (place, move,
  win display, undo, restart, invalid-click flash). **Requires jsdom**
  (`npm install` once); skip with `node --test test/*.test.js` if unavailable.

## Adding features (typical paths)

- **New visual cue** → `styles.css` + a class toggle in `app.js`'s `render()`.
- **New control button** → markup in `index.html`, handler in `app.js`, state
  stays in `game` if it touches game state.
- **Show model-suggested moves** (future RL step) → compute suggestions
  outside `app.js`, pass into `render()`; add a `.suggested` CSS class. Keep
  `game.js` pure — don't add UI hooks there.
- **New game rule** → add a failing logic test in `test/`, implement in
  `game.js`, then update `app.js` only if the UI surface changes.

See `docs/game-rules.md` for the rules themselves.
