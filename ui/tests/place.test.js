const test = require('node:test');
const assert = require('node:assert/strict');
const { create } = require('../game.js');

test('place: red places S on empty cell 0 → top becomes red S, red tray has 5, turn passes to blue, no winner', () => {
  const game = create();
  const redS = game.tray('red').find(p => p.size === 'S');
  const res = game.place(redS.id, 0);

  assert.strictEqual(res.ok, true);
  const top = game.topAt(0);
  assert.strictEqual(top.color, 'red');
  assert.strictEqual(top.size, 'S');
  assert.strictEqual(top.id, redS.id);
  assert.strictEqual(game.tray('red').length, 5);
  assert.strictEqual(game.tray('blue').length, 6);
  assert.strictEqual(game.currentPlayer, 'blue');
  assert.strictEqual(game.winner, null);
});

test('place: placing removes the exact piece from the tray (by id), not just any same-size piece', () => {
  const game = create();
  const redSPieces = game.tray('red').filter(p => p.size === 'S');
  assert.strictEqual(redSPieces.length, 2);
  const target = redSPieces[0];
  game.place(target.id, 0);
  const remaining = game.tray('red');
  assert.ok(!remaining.find(p => p.id === target.id), 'placed piece must be removed from tray');
  assert.strictEqual(remaining.filter(p => p.size === 'S').length, 1);
});
