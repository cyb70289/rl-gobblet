const test = require('node:test');
const assert = require('node:assert/strict');
const { create } = require('../game.js');

function place(game, color, size, cell) {
  const p = game.tray(color).find(x => x.size === size);
  const res = game.place(p.id, cell);
  assert.strictEqual(res.ok, true, `setup place ${color} ${size} -> ${cell} failed: ${res.reason}`);
}

test('legalActions: initial state — 54 place actions (6 pieces x 9 cells), zero move actions', () => {
  const game = create();
  const actions = game.legalActions();
  assert.strictEqual(actions.length, 54);
  assert.strictEqual(actions.filter(a => a.type === 'place').length, 54);
  assert.strictEqual(actions.filter(a => a.type === 'move').length, 0);
  // every place action targets a distinct cell for each piece
  const redS = game.tray('red').filter(p => p.size === 'S').map(p => p.id);
  const sTargets = new Set(actions.filter(a => redS.includes(a.pieceId)).map(a => a.to));
  assert.strictEqual(sTargets.size, 9, 'each S piece can target all 9 cells');
});

test('legalActions: after red S@0, blue has 52 actions (S:2x8, M:2x9, L:2x9), zero moves', () => {
  const game = create();
  place(game, 'red', 'S', 0);
  const actions = game.legalActions();
  assert.strictEqual(actions.length, 52);
  assert.strictEqual(actions.filter(a => a.type === 'move').length, 0);
  // blue S pieces cannot target cell 0 (would cover same size)
  const blueS = game.tray('blue').filter(p => p.size === 'S').map(p => p.id);
  const sTargets = actions.filter(a => blueS.includes(a.pieceId)).map(a => a.to);
  assert.ok(!sTargets.includes(0), 'blue S must not be allowed to cover red S at cell 0');
  // blue M and L CAN target cell 0
  const bigger = actions.filter(a => !blueS.includes(a.pieceId)).map(a => a.to);
  assert.ok(bigger.includes(0), 'blue M/L must be allowed to cover red S at cell 0');
});

test('legalActions: includes move actions for own top pieces; excludes same-cell and same-size-cover', () => {
  const game = create();
  place(game, 'red', 'S', 0);
  place(game, 'blue', 'S', 4);
  const actions = game.legalActions();
  const moves = actions.filter(a => a.type === 'move');
  assert.ok(moves.length > 0, 'red should have move actions for its top piece at cell 0');
  assert.ok(moves.some(a => a.from === 0 && a.to === 1), 'move 0->1 (empty) should be legal');
  assert.ok(!moves.some(a => a.from === 0 && a.to === 0), 'move 0->0 (same cell) must be excluded');
  assert.ok(!moves.some(a => a.from === 0 && a.to === 4), 'move 0->4 (cover same-size blue S) must be excluded');
});

test('legalActions: every listed action is actually playable (apply then undo each)', () => {
  const game = create();
  place(game, 'red', 'S', 0);
  place(game, 'blue', 'M', 4);   // blue M covers... cell 4 was empty; now blue M@4
  place(game, 'red', 'M', 1);
  // blue's turn
  const actions = game.legalActions();
  assert.ok(actions.length > 0);
  for (const a of actions) {
    let res;
    if (a.type === 'place') res = game.place(a.pieceId, a.to);
    else res = game.move(a.from, a.to);
    assert.strictEqual(res.ok, true, `action ${JSON.stringify(a)} not actually playable: ${res.reason}`);
    assert.strictEqual(game.undo().ok, true);
  }
});

test('legalActions: empty when the game is over', () => {
  const game = create();
  place(game, 'red', 'S', 0);
  place(game, 'blue', 'S', 3);
  place(game, 'red', 'M', 1);
  place(game, 'blue', 'S', 5);
  place(game, 'red', 'L', 2);
  assert.strictEqual(game.winner, 'red');
  assert.deepStrictEqual(game.legalActions(), []);
});

test('legalDestinationsForBoardCell: returns valid targets for an own top piece; empty for opponent/empty/covered', () => {
  const game = create();
  place(game, 'red', 'S', 0);
  place(game, 'blue', 'S', 4);
  // red's turn; red top piece at cell 0
  const dests = game.legalDestinationsForBoardCell(0);
  assert.ok(dests.includes(1), 'can move to empty cell 1');
  assert.ok(!dests.includes(0), 'cannot move to same cell');
  assert.ok(!dests.includes(4), 'cannot cover same-size blue S at 4');
  // cell 4 is opponent's top — no destinations (not your piece)
  assert.deepStrictEqual(game.legalDestinationsForBoardCell(4), []);
  // cell 2 is empty — no destinations
  assert.deepStrictEqual(game.legalDestinationsForBoardCell(2), []);
});

test('legalDestinationsForTrayPiece: returns valid cells for a tray piece of the current player', () => {
  const game = create();
  place(game, 'red', 'S', 0);     // red S@0
  place(game, 'blue', 'M', 0);    // blue M covers red S@0
  // red's turn; red L in tray should be able to cover blue M@0 and go to 8 empty cells
  const redL = game.tray('red').find(p => p.size === 'L');
  const dests = game.legalDestinationsForTrayPiece(redL.id);
  assert.ok(dests.includes(0), 'red L can cover blue M at cell 0');
  // empty cells are 1..8
  for (let c = 1; c <= 8; c++) assert.ok(dests.includes(c), `red L can go to empty cell ${c}`);
  assert.strictEqual(dests.length, 9);
  // red S in tray cannot cover blue M@0
  const redS = game.tray('red').find(p => p.size === 'S');
  const sDests = game.legalDestinationsForTrayPiece(redS.id);
  assert.ok(!sDests.includes(0), 'red S cannot cover blue M at cell 0');
  assert.strictEqual(sDests.length, 8);
});
