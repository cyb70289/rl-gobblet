const test = require('node:test');
const assert = require('node:assert/strict');
const { create } = require('../game.js');

function place(game, color, size, cell) {
  const p = game.tray(color).find(x => x.size === size);
  const res = game.place(p.id, cell);
  assert.strictEqual(res.ok, true, `setup place ${color} ${size} -> ${cell} failed: ${res.reason}`);
}

test('undo: canUndo is false at start, true after a move, false again after undoing to start', () => {
  const game = create();
  assert.strictEqual(game.canUndo(), false);
  place(game, 'red', 'S', 0);
  assert.strictEqual(game.canUndo(), true);
  assert.strictEqual(game.undo().ok, true);
  assert.strictEqual(game.canUndo(), false);
});

test('undo: reverts a PLACE — piece returns to tray, cell empties, turn restores', () => {
  const game = create();
  const redS = game.tray('red').find(p => p.size === 'S');
  place(game, 'red', 'S', 0);
  assert.strictEqual(game.tray('red').length, 5);
  assert.strictEqual(game.topAt(0).id, redS.id);
  assert.strictEqual(game.currentPlayer, 'blue');

  assert.strictEqual(game.undo().ok, true);
  assert.strictEqual(game.tray('red').length, 6);
  assert.ok(game.tray('red').find(p => p.id === redS.id), 'red S back in tray');
  assert.strictEqual(game.topAt(0), null);
  assert.strictEqual(game.currentPlayer, 'red');
});

test('undo: reverts a MOVE — moved piece returns to source, destination restores, turn restores', () => {
  const game = create();
  const redS = game.tray('red').find(p => p.size === 'S');
  place(game, 'red', 'S', 0);
  place(game, 'blue', 'S', 4);
  // red moves S 0 -> 1
  assert.strictEqual(game.move(0, 1).ok, true);
  assert.strictEqual(game.topAt(0), null);
  assert.strictEqual(game.topAt(1).id, redS.id);
  assert.strictEqual(game.currentPlayer, 'blue');

  assert.strictEqual(game.undo().ok, true);
  assert.strictEqual(game.topAt(0).id, redS.id, 'red S back at source cell 0');
  assert.strictEqual(game.topAt(1), null, 'destination cell 1 empty again');
  assert.strictEqual(game.currentPlayer, 'red');
});

test('undo: reverts a covering MOVE — exact stack order restored at both cells', () => {
  // cell 0: red S (bottom), red M moved on top of it from cell 1.
  const game = create();
  const redS = game.tray('red').find(p => p.size === 'S');
  const redM = game.tray('red').find(p => p.size === 'M');
  place(game, 'red', 'S', 0);
  place(game, 'blue', 'S', 4);
  place(game, 'red', 'M', 1);
  place(game, 'blue', 'S', 5);
  // red moves M from 1 -> 0 (covers red S)
  assert.strictEqual(game.move(1, 0).ok, true);
  assert.strictEqual(game.stackAt(0).map(p => p.id).join(','), [redS.id, redM.id].join(','));
  assert.strictEqual(game.topAt(1), null);

  assert.strictEqual(game.undo().ok, true);
  assert.strictEqual(game.stackAt(0).map(p => p.id).join(','), [redS.id].join(','), 'cell 0 back to just red S');
  assert.strictEqual(game.topAt(1).id, redM.id, 'red M back at cell 1');
});

test('undo: reverts a winning move — winner cleared, game unlocked, board restored', () => {
  const game = create();
  place(game, 'red', 'S', 0);
  place(game, 'blue', 'S', 3);
  place(game, 'red', 'M', 1);
  place(game, 'blue', 'S', 5);
  place(game, 'red', 'L', 2);   // red wins
  assert.strictEqual(game.winner, 'red');
  assert.strictEqual(game.isGameOver(), true);

  assert.strictEqual(game.undo().ok, true);
  assert.strictEqual(game.winner, null);
  assert.strictEqual(game.isGameOver(), false);
  assert.strictEqual(game.topAt(2), null, 'red L removed from cell 2');
  assert.strictEqual(game.currentPlayer, 'red', 'turn restored to red');
  // red L back in tray
  assert.ok(game.tray('red').find(p => p.size === 'L'));
});

test('undo: with no history returns ok=false', () => {
  const game = create();
  const res = game.undo();
  assert.strictEqual(res.ok, false);
  assert.match(res.reason, /nothing|no history|empty/i);
});

test('undo: multiple undos walk back to initial state', () => {
  const game = create();
  place(game, 'red', 'S', 0);
  place(game, 'blue', 'S', 4);
  place(game, 'red', 'M', 1);
  assert.strictEqual(game.undo().ok, true);
  assert.strictEqual(game.undo().ok, true);
  assert.strictEqual(game.undo().ok, true);
  assert.strictEqual(game.canUndo(), false);
  assert.strictEqual(game.currentPlayer, 'red');
  assert.strictEqual(game.tray('red').length, 6);
  assert.strictEqual(game.tray('blue').length, 6);
  for (let c = 0; c < 9; c++) assert.strictEqual(game.topAt(c), null);
});
