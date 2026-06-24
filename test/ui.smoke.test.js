const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

function loadDom() {
  const root = path.join(__dirname, '..');
  const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8')
    .replace(/<script src="game\.js"><\/script>\s*/, '')
    .replace(/<script src="app\.js"><\/script>\s*/, '');
  const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true });
  const { window } = dom;
  for (const file of ['game.js', 'app.js']) {
    const s = window.document.createElement('script');
    s.textContent = fs.readFileSync(path.join(root, file), 'utf8');
    window.document.body.appendChild(s);
  }
  return window;
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
  assert.strictEqual(w.document.getElementById('turn-label').textContent, 'Red wins');

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
