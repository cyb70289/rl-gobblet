const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

function loadDom(opts = {}) {
  const root = path.join(__dirname, '..');
  const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8')
    .replace(/<script src="game\.js"><\/script>\s*/, '')
    .replace(/<script src="app\.js"><\/script>\s*/, '');
  const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true });
  const { window } = dom;
  // expose config to app.js before app.js loads
  window.__gobbletAnim = opts.anim || { shineMs: 0 };
  if (opts.fetch) window.fetch = opts.fetch;
  for (const file of ['game.js', 'app.js']) {
    const s = window.document.createElement('script');
    s.textContent = fs.readFileSync(path.join(root, file), 'utf8');
    window.document.body.appendChild(s);
  }
  return window;
}

async function flush() {
  // The new async action pipeline (source-shine, state, dest-shine,
  // model fetch, model-apply) can take up to ~6 macrotasks when
  // shineMs=0. Flush generously.
  for (let i = 0; i < 12; i++) {
    await new Promise(r => setTimeout(r, 0));
  }
}

function defaultHealth() {
  return { ok: true, status: 200, json: async () => ({ ok: true, model_loaded: true, sims: 4, device: 'cpu', model_path: 'test' }) };
}

function makeFetchMock({ health = defaultHealth(), move = defaultMove() } = {}) {
  const requests = [];
  const fn = async (url, opts) => {
    requests.push({ url, opts });
    if (url === '/api/health') return health;
    if (url === '/api/move') return move;
    return { ok: false, status: 404, text: async () => 'not found' };
  };
  return { requests, fn };
}

function defaultMove() {
  return { ok: true, status: 200, json: async () => ({ action: { kind: 'place', to: 4, size: 1 } }) };
}

const R_TO_SIZE = { '20': 'S', '32': 'M', '44': 'L' };

function traySlots(window, color) {
  const trayEl = window.document.getElementById(color === 'red' ? 'red-tray' : 'blue-tray');
  return Array.from(trayEl.querySelectorAll('.tray-slot'));
}

function slotSize(slot) {
  const r = slot.querySelector('circle').getAttribute('r');
  return R_TO_SIZE[r];
}

function findSlot(window, color, size) {
  return traySlots(window, color).find(s => slotSize(s) === size);
}

function cellEl(window, cell) {
  return window.document.querySelector(`.cell[data-cell="${cell}"]`);
}

function cellTopColor(window, cell) {
  const c = cellEl(window, cell).querySelector('circle');
  if (!c) return null;
  // shade() produces hsl(...); we identify color by hue
  const fill = c.getAttribute('fill');
  if (fill.startsWith('hsl(8')) return 'red';
  if (fill.startsWith('hsl(205')) return 'blue';
  return null;
}

function modeControlsOrder(window) {
  const mc = window.document.querySelector('.mode-controls');
  const out = [];
  for (const c of mc.children) {
    if (c.id) {
      out.push(c.id);
    } else {
      // wrapping <label> for a <select>; pick the select's id
      const sel = c.querySelector('select');
      out.push(sel ? sel.id : c.tagName.toLowerCase());
    }
  }
  return out;
}

test('UI initial render: Red to move, empty board, 6 slots per tray, undo disabled, banner hidden', () => {
  const w = loadDom();
  assert.match(w.document.getElementById('turn-label').textContent, /Red/);
  assert.ok(w.document.getElementById('turn-label').classList.contains('red'));
  assert.strictEqual(w.document.querySelectorAll('.cell').length, 9);
  for (let c = 0; c < 9; c++) {
    assert.strictEqual(cellEl(w, c).querySelector('circle'), null, `cell ${c} should be empty`);
  }
  assert.strictEqual(traySlots(w, 'red').length, 6);
  assert.strictEqual(traySlots(w, 'blue').length, 6);
  assert.strictEqual(w.document.getElementById('undo-btn').disabled, true);
  assert.strictEqual(w.document.getElementById('banner').classList.contains('hidden'), true);
  // red tray is the active one
  assert.ok(w.document.getElementById('red-tray').classList.contains('active'));
});

test('UI: clicking a red S tray slot selects it; clicking cell 0 places it and passes turn to blue', () => {
  const w = loadDom();
  const slot = findSlot(w, 'red', 'S');
  slot.click();
  const selectedSlot = w.document.querySelector('.tray-slot.selected');
  assert.ok(selectedSlot, 'a tray slot should be selected after click');
  assert.strictEqual(slotSize(selectedSlot), 'S');
  // valid destinations highlighted (all 9 cells are valid for an S on an empty board)
  assert.ok(cellEl(w, 0).classList.contains('valid'));

  cellEl(w, 0).click();
  assert.strictEqual(cellTopColor(w, 0), 'red');
  assert.strictEqual(traySlots(w, 'red').length, 5, 'red tray should drop to 5');
  assert.match(w.document.getElementById('turn-label').textContent, /Blue/);
  assert.ok(w.document.getElementById('blue-tray').classList.contains('active'));
  assert.strictEqual(w.document.getElementById('undo-btn').disabled, false);
});

test('UI: full game via clicks — red wins row 0 S-M-L; banner shows, board locks, winning cells pulse', () => {
  const w = loadDom();
  // red S@0, blue S@3, red M@1, blue S@5, red L@2 -> red wins
  findSlot(w, 'red', 'S').click();   cellEl(w, 0).click();
  findSlot(w, 'blue', 'S').click();  cellEl(w, 3).click();
  findSlot(w, 'red', 'M').click();   cellEl(w, 1).click();
  findSlot(w, 'blue', 'S').click();  cellEl(w, 5).click();
  findSlot(w, 'red', 'L').click();   cellEl(w, 2).click();

  const banner = w.document.getElementById('banner');
  assert.ok(!banner.classList.contains('hidden'));
  assert.match(banner.textContent, /Red wins/);
  assert.strictEqual(w.document.getElementById('turn-label').textContent, "Red wins!");

  // winning cells 0,1,2 have 'winning' class
  for (const c of [0, 1, 2]) assert.ok(cellEl(w, c).classList.contains('winning'), `cell ${c} should be winning`);
  assert.ok(!cellEl(w, 3).classList.contains('winning'));

  // board locked: clicking a blue tray piece does nothing
  const blueSlotsBefore = traySlots(w, 'blue').length;
  findSlot(w, 'blue', 'L').click();
  assert.strictEqual(traySlots(w, 'blue').length, blueSlotsBefore, 'no action after win');
});

test('UI: undo reverts the winning move (banner hidden, game unlocked, turn back to red)', () => {
  const w = loadDom();
  findSlot(w, 'red', 'S').click();   cellEl(w, 0).click();
  findSlot(w, 'blue', 'S').click();  cellEl(w, 3).click();
  findSlot(w, 'red', 'M').click();   cellEl(w, 1).click();
  findSlot(w, 'blue', 'S').click();  cellEl(w, 5).click();
  findSlot(w, 'red', 'L').click();   cellEl(w, 2).click();
  assert.ok(!w.document.getElementById('banner').classList.contains('hidden'));

  w.document.getElementById('undo-btn').click();
  assert.strictEqual(w.document.getElementById('banner').classList.contains('hidden'), true, 'banner hidden after undo');
  assert.strictEqual(w.document.getElementById('turn-label').textContent, "Red's turn");
  assert.strictEqual(cellEl(w, 2).querySelector('circle'), null, 'red L removed from cell 2');
  assert.ok(w.document.getElementById('undo-btn').disabled === false, 'still more history to undo');
});

test('UI: restart resets to the initial state', () => {
  const w = loadDom();
  findSlot(w, 'red', 'S').click();   cellEl(w, 0).click();
  findSlot(w, 'blue', 'S').click();  cellEl(w, 3).click();
  w.document.getElementById('restart-btn').click();

  assert.strictEqual(traySlots(w, 'red').length, 6);
  assert.strictEqual(traySlots(w, 'blue').length, 6);
  for (let c = 0; c < 9; c++) assert.strictEqual(cellEl(w, c).querySelector('circle'), null);
  assert.strictEqual(w.document.getElementById('turn-label').textContent, "Red's turn");
  assert.strictEqual(w.document.getElementById('undo-btn').disabled, true);
  assert.strictEqual(w.document.getElementById('banner').classList.contains('hidden'), true);
});

test('UI: move flow — place red S@0, blue S@4, then red moves 0->1; cell 0 empties, cell 1 red S', () => {
  const w = loadDom();
  findSlot(w, 'red', 'S').click();   cellEl(w, 0).click();
  findSlot(w, 'blue', 'S').click();  cellEl(w, 4).click();
  // red's turn: click own top piece at cell 0 to select for moving
  cellEl(w, 0).click();
  assert.ok(cellEl(w, 0).classList.contains('selected'));
  assert.ok(cellEl(w, 1).classList.contains('valid'), 'cell 1 should be a valid move destination');
  assert.ok(!cellEl(w, 4).classList.contains('valid'), 'cell 4 (same-size blue S) should NOT be valid');
  cellEl(w, 1).click();
  assert.strictEqual(cellEl(w, 0).querySelector('circle'), null, 'cell 0 now empty');
  assert.strictEqual(cellTopColor(w, 1), 'red');
  assert.match(w.document.getElementById('turn-label').textContent, /Blue/);
});

test('UI: invalid destination click flashes and keeps selection (no state change)', () => {
  const w = loadDom();
  findSlot(w, 'red', 'S').click();   cellEl(w, 0).click();
  findSlot(w, 'blue', 'S').click();  cellEl(w, 4).click();
  // red selects S from tray again, tries to place on cell 4 (blue S same size -> invalid)
  findSlot(w, 'red', 'S').click();
  const cell4 = cellEl(w, 4);
  cell4.click();
  assert.ok(cell4.classList.contains('flash'), 'invalid destination should flash');
  // selection should still be active (red tray still has a selected slot)
  assert.ok(w.document.querySelector('.tray-slot.selected'), 'selection retained after invalid click');
  // turn unchanged
  assert.match(w.document.getElementById('turn-label').textContent, /Red/);
});

// ============== model mode ==============

test('UI: mode toggle exists, defaults to manual, color picker is hidden', () => {
  const w = loadDom();
  const modeSelect = w.document.getElementById('mode-select');
  assert.ok(modeSelect, 'mode-select should exist');
  assert.strictEqual(modeSelect.value, 'manual');
  const modelOpt = modeSelect.querySelector('option[value="model"]');
  assert.ok(modelOpt);
  // without a successful health check, model option is disabled
  assert.ok(modelOpt.disabled, 'model option disabled until health check');
  const colorPicker = w.document.getElementById('color-picker');
  assert.ok(colorPicker);
  assert.ok(colorPicker.classList.contains('hidden'), 'color picker hidden in manual mode');
});

test('UI: health check enables the model option; switching to model mode reveals the color picker and restarts', async () => {
  const mock = makeFetchMock();
  const w = loadDom({ fetch: mock.fn });
  await flush();

  const modeSelect = w.document.getElementById('mode-select');
  const modelOpt = modeSelect.querySelector('option[value="model"]');
  assert.ok(!modelOpt.disabled, 'model option should be enabled after health check');

  // make a move in manual mode first, to verify it gets reset
  findSlot(w, 'red', 'S').click();
  cellEl(w, 0).click();
  assert.strictEqual(traySlots(w, 'red').length, 5);

  // switch to model mode
  modeSelect.value = 'model';
  modeSelect.dispatchEvent(new w.Event('change'));
  await flush();

  const colorPicker = w.document.getElementById('color-picker');
  assert.ok(!colorPicker.classList.contains('hidden'), 'color picker visible after switching to model mode');
  assert.strictEqual(traySlots(w, 'red').length, 6, 'red tray reset on mode switch');
  assert.strictEqual(cellEl(w, 0).querySelector('circle'), null, 'cell 0 reset on mode switch');
});

test('UI: in model mode (you=red), after your move the model fetches and applies the response', async () => {
  const mock = makeFetchMock();
  const w = loadDom({ fetch: mock.fn });
  await flush();

  // switch to model mode (you=red, so model=blue, blue moves second)
  const modeSelect = w.document.getElementById('mode-select');
  modeSelect.value = 'model';
  modeSelect.dispatchEvent(new w.Event('change'));
  await flush();

  // human (red) makes a move
  findSlot(w, 'red', 'S').click();
  cellEl(w, 0).click();
  await flush();

  // /api/move should have been called
  const moveReqs = mock.requests.filter(r => r.url === '/api/move');
  assert.strictEqual(moveReqs.length, 1, 'one /api/move call after human move');
  // verify the request body includes state and modelColor
  const body = JSON.parse(moveReqs[0].opts.body);
  assert.strictEqual(body.modelColor, 1, 'modelColor=1 (blue)');
  assert.strictEqual(body.state.player, 1, 'state.player=1 (blue)');

  // the mock returns place M at cell 4 — verify the board reflects that
  assert.strictEqual(cellTopColor(w, 4), 'blue', 'model placed M at cell 4');
  assert.match(w.document.getElementById('turn-label').textContent, /Red/);
});

test('UI: in model mode (you=blue), the model moves first', async () => {
  const mock = makeFetchMock();
  const w = loadDom({ fetch: mock.fn });
  await flush();

  // switch to model mode and pick blue
  const modeSelect = w.document.getElementById('mode-select');
  modeSelect.value = 'model';
  modeSelect.dispatchEvent(new w.Event('change'));
  await flush();

  const colorSelect = w.document.getElementById('color-select');
  colorSelect.value = 'blue';
  colorSelect.dispatchEvent(new w.Event('change'));
  await flush();

  const moveReqs = mock.requests.filter(r => r.url === '/api/move');
  assert.strictEqual(moveReqs.length, 1, 'model moved first (you=blue)');
  const body = JSON.parse(moveReqs[0].opts.body);
  assert.strictEqual(body.modelColor, 0, 'modelColor=0 (red)');
  assert.strictEqual(cellTopColor(w, 4), 'red', 'red M placed at cell 4');
});

test('UI: a 5xx from /api/move shows an error and disables the model option', async () => {
  const mock = makeFetchMock({
    move: { ok: false, status: 500, text: async () => 'server error' },
  });
  const w = loadDom({ fetch: mock.fn });
  await flush();

  const modeSelect = w.document.getElementById('mode-select');
  modeSelect.value = 'model';
  modeSelect.dispatchEvent(new w.Event('change'));
  await flush();

  findSlot(w, 'red', 'S').click();
  cellEl(w, 0).click();
  await flush();

  // banner shows the error
  const banner = w.document.getElementById('banner');
  assert.ok(!banner.classList.contains('hidden'), 'banner visible on error');
  assert.match(banner.textContent, /Model error/);

  // model option is disabled
  const modelOpt = modeSelect.querySelector('option[value="model"]');
  assert.ok(modelOpt.disabled, 'model option disabled after error');
});

test('UI: server down on initial load disables the model option', async () => {
  const mock = makeFetchMock({ health: { ok: false, status: 500 } });
  const w = loadDom({ fetch: mock.fn });
  await flush();

  const modeSelect = w.document.getElementById('mode-select');
  const modelOpt = modeSelect.querySelector('option[value="model"]');
  assert.ok(modelOpt.disabled, 'model option disabled when health fails');
});

test('UI: mode-controls order is Mode, Model Status, Color', () => {
  const w = loadDom();
  const order = modeControlsOrder(w);
  assert.deepStrictEqual(
    order,
    ['mode-select', 'model-status', 'color-picker'],
    `expected [mode-select, model-status, color-picker] got ${JSON.stringify(order)}`
  );
});

test('UI: undo in model mode pops two plies and does not fire the model', async () => {
  const mock = makeFetchMock();
  const w = loadDom({ fetch: mock.fn });
  await flush();

  const modeSelect = w.document.getElementById('mode-select');
  modeSelect.value = 'model';
  modeSelect.dispatchEvent(new w.Event('change'));
  await flush();

  // human (red) plays
  findSlot(w, 'red', 'S').click();
  cellEl(w, 0).click();
  await flush();
  // model (blue) has placed M at 4
  assert.strictEqual(cellTopColor(w, 4), 'blue');

  const moveReqsBefore = mock.requests.filter(r => r.url === '/api/move').length;
  assert.strictEqual(moveReqsBefore, 1);

  // undo: should pop both the model's and the human's moves
  w.document.getElementById('undo-btn').click();
  await flush();

  // state is back to start (cell 0 empty, cell 4 empty, red tray full)
  assert.strictEqual(cellEl(w, 0).querySelector('circle'), null, 'cell 0 should be empty after undo');
  assert.strictEqual(cellEl(w, 4).querySelector('circle'), null, 'cell 4 should be empty after undo');
  assert.strictEqual(traySlots(w, 'red').length, 6, 'red tray should be full after undo');
  assert.strictEqual(w.document.getElementById('turn-label').textContent, "Red's turn");

  // model must NOT have re-fired
  const moveReqsAfter = mock.requests.filter(r => r.url === '/api/move').length;
  assert.strictEqual(moveReqsAfter, 1, 'model should not re-fire after undo');
});

test('UI: undo in manual mode still pops one ply', async () => {
  const w = loadDom();
  // red S@0, blue S@3
  findSlot(w, 'red', 'S').click();   cellEl(w, 0).click();
  findSlot(w, 'blue', 'S').click();  cellEl(w, 3).click();
  // undo: should pop the blue S@3 move only
  w.document.getElementById('undo-btn').click();
  await flush();
  // cell 0 has red S; cell 3 empty; blue tray back to 6
  assert.strictEqual(cellTopColor(w, 0), 'red');
  assert.strictEqual(cellEl(w, 3).querySelector('circle'), null, 'cell 3 should be empty');
  assert.strictEqual(traySlots(w, 'blue').length, 6, 'blue tray should be full after one undo');
  assert.match(w.document.getElementById('turn-label').textContent, /Red/);
});

test('UI: source element receives the .shine class during a click', async () => {
  // Use a non-zero shineMs so we can observe the class mid-animation
  const w = loadDom({ anim: { shineMs: 50 } });
  // red selects S and starts a click on cell 0
  findSlot(w, 'red', 'S').click();
  cellEl(w, 0).click();
  // The render() inside executeAction creates a fresh DOM. Query by class.
  const shiningSlot = w.document.querySelector('.tray-slot.shine');
  assert.ok(shiningSlot, 'a tray slot should have .shine class right after click');
  // wait for the animation to complete
  await flush();
  assert.strictEqual(
    w.document.querySelector('.tray-slot.shine'),
    null,
    'tray slot .shine should be removed after animation'
  );
});
