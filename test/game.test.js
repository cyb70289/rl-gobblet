const test = require('node:test');
const assert = require('node:assert/strict');
const { create } = require('../game.js');

test('initial state: empty 3x3 board, 6 pieces per tray (2S/2M/2L), red to move, no winner', () => {
  const game = create();

  assert.strictEqual(game.currentPlayer, 'red');
  assert.strictEqual(game.winner, null);
  assert.strictEqual(game.isGameOver(), false);

  for (let cell = 0; cell < 9; cell++) {
    assert.strictEqual(game.topAt(cell), null, `cell ${cell} should be empty`);
  }

  assert.strictEqual(game.tray('red').length, 6);
  assert.strictEqual(game.tray('blue').length, 6);

  const redSizes = game.tray('red').map(p => p.size).sort();
  assert.deepStrictEqual(redSizes, ['L', 'L', 'M', 'M', 'S', 'S']);
  const blueSizes = game.tray('blue').map(p => p.size).sort();
  assert.deepStrictEqual(blueSizes, ['L', 'L', 'M', 'M', 'S', 'S']);

  for (const p of game.tray('red')) assert.strictEqual(p.color, 'red');
  for (const p of game.tray('blue')) assert.strictEqual(p.color, 'blue');

  const redIds = game.tray('red').map(p => p.id);
  assert.strictEqual(new Set(redIds).size, 6, 'red piece ids must be unique');
  const blueIds = game.tray('blue').map(p => p.id);
  assert.strictEqual(new Set(blueIds).size, 6, 'blue piece ids must be unique');
});
