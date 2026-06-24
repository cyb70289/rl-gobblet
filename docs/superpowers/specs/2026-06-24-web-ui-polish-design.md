# Web UI Polish — Design Spec

**Date:** 2026-06-24
**Scope:** `ui/` only (HTML, CSS, app.js, tests). `gobblet/webui.py` and `ui/game.js` are not touched.

## Background

Four small but visible issues in the current web UI:

1. The turn label in the topbar (e.g. `Model wins!`) wraps to two lines when the
   bar is narrow.
2. The `model: ready` status sits at the end of the mode-controls block, far
   from the mode select it describes.
3. In model mode, `Undo` pops one ply and the model immediately re-fires the
   same move — there is no way to take back your own last move.
4. There is no visual indication of a move; the board just snaps to the new
   state.

This spec covers all four.

## Decisions (recap of grill answers)

| # | Decision |
|---|---|
| 1 | `white-space: nowrap` on the topbar; width grows dynamically past the board. |
| 2 | Order: `Mode | Model Status | Color`. |
| 3 | Model-mode undo: pop up to **two plies** per click (model's + human's preceding); model **never** auto-fires after undo. Manual-mode undo unchanged. Undo disabled while `modelThinking`. |
| 4 | **Shine effect** (scale + glow pulse), 1.0s source-shine → instant state change → 1.0s dest-shine. Model moves animate the same way. Undo has no animation. Clicks ignored during animation. Win banner appears after dest-shine completes. |

---

## 1. Turn label width

**File:** `ui/styles.css`

The current `.topbar` is pinned to `width: calc(var(--cell-size) * 3 + var(--board-gap) * 2)`
(= board width, ~372px). When `.mode-controls` grows (model mode with color
picker + model status), `.turn-label` is squeezed and wraps.

**Change:**

- Remove the fixed `width` on `.topbar`.
- Add `white-space: nowrap` to `.topbar` (prevents any of the three
  top-level children from wrapping to a new line).
- Add `white-space: nowrap` to `.turn-label` (defensive — it should never
  wrap even if a future change makes its parent narrower).
- Add `white-space: nowrap` to `.mode-controls` and `.controls` to keep
  their internal rows on one line.
- The topbar's `justify-content: space-between` continues to work; the
  whole bar simply becomes as wide as it needs to be, which is ≥ board
  width.

**No HTML changes.**

## 2. Reorder model-status

**File:** `ui/index.html`

Current order inside `.mode-controls`:

```
Mode | Color (hidden in manual) | Model Status
```

Target order:

```
Mode | Model Status | Color (hidden in manual)
```

**Change:** move the `<span id="model-status">` element to sit between the
Mode `<label>` and the Color `<label>`. No changes to IDs, classes, or
attributes — pure DOM reorder.

## 3. Undo behavior in model mode

**File:** `ui/app.js`

**Current behavior** (`undoBtn` click handler, ~line 383):

```javascript
undoBtn.addEventListener('click', () => {
  if (modelThinking) return;
  if (!game.canUndo()) return;
  game.undo();
  selected = null;
  render();
  if (isModelTurn()) maybeFireModelMove();
});
```

**New behavior:**

- **Manual mode:** unchanged. One click → one ply popped.
- **Model mode:** one click pops up to **two plies** — first the model's
  most recent move, then the human's preceding move (if it exists). After
  the pop, the model is **never** auto-fired.
- The `Undo` button stays disabled while `modelThinking` is true.
- The `Undo` button stays enabled as long as there is at least one ply to
  pop. If the game is at the very start (history empty), the button is
  disabled — same as today.
- The human's selection (`selected`) is cleared on any undo, same as today.

**Pseudocode:**

```javascript
undoBtn.addEventListener('click', () => {
  if (modelThinking) return;
  if (!game.canUndo()) return;
  if (mode === 'model') {
    // pop the model's most recent move
    if (game.canUndo()) game.undo();
    // pop the human's preceding move (if any)
    if (game.canUndo() && !game.winner) game.undo();
    // intentional: do NOT call maybeFireModelMove() here.
  } else {
    game.undo();
  }
  selected = null;
  render();
});
```

**Edge cases:**

- `you = blue`, model moved first: history has one ply (the model's). One
  click pops it, then `canUndo()` returns false, so the second `undo()` is
  a no-op. After the click, it is the model's turn, but the model is not
  fired. The `Undo` button is now disabled (no history). The user can
  press `Restart` or wait.
- Game over (`game.winner` set): `canUndo()` returns true (history
  contains the winning move). One click pops the winning move, the
  banner hides, and the game unlocks. This is the same as today's
  behavior.
- During `modelThinking`: button is disabled. No change.

**Doc update:** `docs/ui.md` lines 108–110 describe the old behavior. They
will be updated to describe the new behavior (the surrounding paragraph
in `docs/ui.md` "Model mode" section is the right place).

## 4. Move animation

### 4.1 Visual effect — "shine"

**File:** `ui/styles.css`

A new keyframe animation that pulses the element with both a scale and a
gold glow, with two peaks over 1.0s. The color matches the existing
`--select` (gold) for consistency with the selection indicator.

```css
@keyframes shine-pulse {
  0%, 50%, 100% {
    transform: scale(1);
    filter: drop-shadow(0 0 0 transparent);
  }
  25%, 75% {
    transform: scale(1.18);
    filter: drop-shadow(0 0 10px var(--select));
  }
}

.shine {
  animation: shine-pulse 1.0s ease-in-out;
  z-index: 1; /* keep the pulsing piece on top of neighbors */
}
```

A single class `.shine` drives the animation. The animation runs once
(not infinite); we add the class to start, remove it after 1.0s. The
keyframes have two natural peaks at the 25% and 75% marks — two clear
"shines" in 1.0s.

For tray slots, `transform: scale()` is already used for hover
(`tray-slot:hover`). The `.shine` class works alongside the hover, no
conflict.

For cells, we currently set `transform: none` implicitly (cells are
flex-centered). The `transform: scale(1.18)` will center-scale the cell
contents around the cell's center, which is the desired effect.

### 4.2 Timing — three-phase sequence

For every successful action (human or model), the UI runs:

1. **Source shine** (1.0s) — the originating element pulses twice.
   - Place: the chosen tray slot of the current player.
   - Move: the source cell (`from`).
2. **State change** (instant) — `game.place()` / `game.move()` is called,
   `selected` is cleared, `render()` is called to update the DOM to the
   new state.
3. **Destination shine** (1.0s) — the destination cell pulses twice.

Total animation: ~2.0s per action.

If the action is the winning move, the banner (`#banner` + `#turn-label`)
updates to show `Red wins!` / `You win!` / `Model wins!` **after** the
destination-shine completes. The `.winning` class is then added to the
three winning cells and they start their existing `winpulse` animation.

### 4.3 New state flag: `animating`

**File:** `ui/app.js`

A new module-level flag, similar to `modelThinking`:

```javascript
let animating = false;  // true while a shine animation is in progress
```

**UI gating during animation:**

- `undoBtn.disabled` = `!game.canUndo() || modelThinking || animating`
- `modeSelect.disabled` = `modelThinking || animating`
- `colorSelect.disabled` = `modeSelect.disabled || mode !== 'model'`
- `restartBtn.disabled` is always `false` (Restart is never disabled).
  See "Restart cancels in-flight animation" below.
- Cells get `.locked` class when `modelThinking || animating`. Existing
  click handler already checks `if (game.winner || modelThinking) return`;
  extend to `... || animating`.
- Tray slot click handler: same.

**Restart cancels in-flight animation.** `restartGame()` always
increments `requestSeq`. Both `executeAction` and
`applyServerActionAnimated` capture `requestSeq` at the start of each
phase and abort the rest of the sequence if the value has changed. The
animation visibly "snaps" to the new state — acceptable because
Restart is an explicit reset.

### 4.4 Async action execution

**File:** `ui/app.js`

Refactor the synchronous `executeAction(cell)` into an async function:

```javascript
async function executeAction(cell) {
  // Resolve the source DOM element from `selected` BEFORE clearing it.
  const sourceEl = resolveSourceElement(selected);
  if (!sourceEl) {
    // defensive: bail out
    flashCell(cell);
    return;
  }

  const startSeq = requestSeq;  // detect Restart mid-animation
  animating = true;
  render();

  // Phase 1: source shine
  sourceEl.classList.add('shine');
  await sleep(ANIM.shineMs);
  if (startSeq !== requestSeq) return;  // Restart was clicked
  sourceEl.classList.remove('shine');

  // Phase 2: apply state
  let res;
  if (selected.kind === 'tray') {
    res = game.place(selected.pieceId, cell);
  } else {
    res = game.move(selected.cell, cell);
  }
  selected = null;

  if (!res.ok) {
    animating = false;
    render();
    flashCell(cell);
    return;
  }

  render();
  if (startSeq !== requestSeq) return;  // Restart was clicked

  // Phase 3: destination shine
  const destEl = boardEl.querySelector(`.cell[data-cell="${cell}"]`);
  if (destEl) {
    destEl.classList.add('shine');
    await sleep(ANIM.shineMs);
    if (startSeq !== requestSeq) return;  // Restart was clicked
    destEl.classList.remove('shine');
  }

  animating = false;

  if (game.winner) {
    // After the dest-shine, the banner + turn label will pick up the
    // winner in the next render(). Trigger it now.
    render();
  } else if (isModelTurn()) {
    maybeFireModelMove();
  } else {
    render();
  }
}

function resolveSourceElement(sel) {
  if (!sel) return null;
  if (sel.kind === 'tray') {
    return document.querySelector(
      `.tray-slot[data-color="${game.currentPlayer}"][data-piece-id="${sel.pieceId}"]`
    );
  }
  if (sel.kind === 'board') {
    return boardEl.querySelector(`.cell[data-cell="${sel.cell}"]`);
  }
  return null;
}
```

`ANIM` is a small const object:

```javascript
const ANIM = { shineMs: 1000 };
window.__gobbletAnim = ANIM;  // for test override
```

`sleep(ms)` is a small helper:

```javascript
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
```

### 4.5 Model move animation

**File:** `ui/app.js`

Refactor `applyServerAction` so the model move also gets the same
source-shine + state + dest-shine sequence. The current
`applyServerAction` is pure (returns true/false); wrap it.

```javascript
async function applyServerActionAnimated(action) {
  const startSeq = requestSeq;

  // Resolve source element from the action
  let sourceEl;
  if (action.kind === 'place') {
    const sizeName = SIZE_ORDER[action.size];
    const piece = game.tray(game.currentPlayer).find(p => p.size === sizeName);
    if (!piece) {
      showError('Model returned a place action with no available piece');
      return;
    }
    sourceEl = document.querySelector(
      `.tray-slot[data-color="${game.currentPlayer}"][data-piece-id="${piece.id}"]`
    );
  } else if (action.kind === 'move') {
    sourceEl = boardEl.querySelector(`.cell[data-cell="${action.from_}"]`);
  } else {
    showError(`Unknown action kind: ${action.kind}`);
    return;
  }

  animating = true;
  // modelThinking is still true here. render() so the cells are unlocked
  // (locked class) but the model is still flagged.
  render();

  if (sourceEl) {
    sourceEl.classList.add('shine');
    await sleep(ANIM.shineMs);
    if (startSeq !== requestSeq) {
      animating = false;
      modelThinking = false;
      return;
    }
    sourceEl.classList.remove('shine');
  }

  // Apply state
  const ok = applyServerAction(action);
  if (!ok) {
    animating = false;
    modelThinking = false;
    render();
    return;
  }
  render();
  if (startSeq !== requestSeq) {
    animating = false;
    modelThinking = false;
    return;
  }

  // Destination shine
  const destEl = boardEl.querySelector(`.cell[data-cell="${action.to}"]`);
  if (destEl) {
    destEl.classList.add('shine');
    await sleep(ANIM.shineMs);
    if (startSeq !== requestSeq) {
      animating = false;
      modelThinking = false;
      return;
    }
    destEl.classList.remove('shine');
  }

  animating = false;
  modelThinking = false;

  if (game.winner) {
    render();
  } else if (isModelTurn()) {
    // shouldn't happen — model just played — but guard anyway
    maybeFireModelMove();
  } else {
    render();
  }
}
```

`maybeFireModelMove` is updated to call `applyServerActionAnimated`
instead of `applyServerAction` directly. The `finally` block in
`maybeFireModelMove` becomes a no-op (it does not touch
`modelThinking` or call `render()`); `applyServerActionAnimated`
manages both flags at every return point so they are always in sync
with reality.

`restartGame` is updated to also set `animating = false` and
`modelThinking = false`, so the flags are always in sync with reality.
The `requestSeq++` it already does is what causes in-flight animation
phases to abort early.

### 4.6 Win case

When a move causes a win:

- The state change in Phase 2 sets `game.winner`. After Phase 2's
  `render()`, the winning cells are flagged (but the winpulse animation
  is competing with the dest-shine).
- During Phase 3, the dest cell has both `.shine` and `.winning`
  classes. The CSS `.shine` animation runs (transform + filter); the
  `.winning` animation also runs (box-shadow on the cell itself). They
  don't conflict because they animate different properties.
- After Phase 3, `animating = false` and `render()` is called. The
  banner + turn label update with the end-of-game text.

### 4.7 No animation for undo

The undo handler stays synchronous. `game.undo()` is called immediately;
`render()` is called immediately; the user sees the board snap back.

## 5. Tests

**File:** `ui/tests/ui.smoke.test.js`

The existing tests rely on `await flush()` (two `setTimeout(0)`s) after
clicking a cell. With 2.0s of animation per action, those tests will
break.

**Test strategy:** expose `window.__gobbletAnim` (set in `loadDom`'s
options) and have the app read `ANIM.shineMs` lazily. The default is
1000; tests set it to 0.

Update `loadDom` to accept an `anim` option:

```javascript
function loadDom(opts = {}) {
  ...
  // expose config to app.js before app.js loads
  window.__gobbletAnim = opts.anim || { shineMs: 0 };
  ...
}
```

In `app.js`:

```javascript
const ANIM = (typeof window !== 'undefined' && window.__gobbletAnim) || { shineMs: 1000 };
```

Tests that previously used `await flush()` after a click can keep using
`flush()` because the animation is now 0ms. The test that explicitly
checks the dest-shine timing would need real timing — there is no such
test today.

**New tests to add:**

- `UI: after a click, the source element briefly has .shine class`
  — assert that during the first phase, the source element has the
  `.shine` class. (Will require timing; use `shineMs: 0` and a quick
  check before render() settles, or check the class was applied and
  removed at all by spying.)
- `UI: undo in model mode pops two plies and does not fire the model`
- `UI: undo in manual mode still pops one ply`

**Existing test updates:**

- The model-mode undo test (around line 288 of `ui.smoke.test.js`)
  expects the model to re-fire after one undo. That test now expects
  the model NOT to re-fire, and the state to be back to the human's
  turn. The new test (`UI: undo in model mode pops two plies…`) covers
  this.

## 6. Files changed

- `ui/index.html` — reorder model-status (one DOM move)
- `ui/styles.css` — `white-space: nowrap` on topbar + turn label + mode
  controls + controls; new `.shine` class + `@keyframes shine-pulse`
- `ui/app.js` — `animating` flag; `ANIM` config; `sleep()` helper;
  `resolveSourceElement()`; `executeAction()` becomes async; new
  `applyServerActionAnimated()`; updated undo handler
- `ui/tests/ui.smoke.test.js` — `loadDom` accepts `anim` option; updated
  undo test; new tests
- `docs/ui.md` — update the "Undo in model mode" paragraph (line ~108)
  to describe the new behavior

## 7. Out of scope

- No changes to `ui/game.js` (pure game logic is untouched).
- No changes to `gobblet/webui.py` (server-side behavior is unchanged).
- No changes to the manual-mode visual feedback beyond the universal
  topbar fix.
- No settings UI to disable the animation.
- No keyboard shortcuts.
- No reduced-motion accommodation. (Could be added later via
  `@media (prefers-reduced-motion: reduce)`.)
