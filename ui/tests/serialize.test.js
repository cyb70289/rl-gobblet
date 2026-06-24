const test = require('node:test');
const assert = require('node:assert/strict');
const { create } = require('../game.js');

const SIZE_TO_INT = { S: 0, M: 1, L: 2 };
const COLOR_TO_INT = { red: 0, blue: 1 };

function firstPieceId(game, color, size) {
  return game.tray(color).find(p => p.size === size).id;
}

test('serializeState: initial state — empty board, full trays, red to move, ply 0, no winner', () => {
  const game = create();
  const s = game.serializeState();
  assert.deepStrictEqual(s.board, [[], [], [], [], [], [], [], [], []]);
  assert.deepStrictEqual(s.trays, [2, 2, 2, 2, 2, 2]);
  assert.strictEqual(s.player, 0);
  assert.strictEqual(s.ply, 0);
  assert.strictEqual(s.winner, null);
  assert.strictEqual(s.is_draw, false);
});

test('serializeState: trays index is color*3+size, player is 0=red,1=blue, ply is history.length', () => {
  const game = create();
  game.place(firstPieceId(game, 'red', 'S'), 0);
  const s = game.serializeState();
  assert.deepStrictEqual(s.board[0], [[0, 0]]);
  assert.strictEqual(s.trays[0], 1);
  assert.strictEqual(s.trays[1], 2);
  assert.strictEqual(s.trays[2], 2);
  assert.strictEqual(s.trays[3], 2);
  assert.strictEqual(s.trays[4], 2);
  assert.strictEqual(s.trays[5], 2);
  assert.strictEqual(s.player, 1);
  assert.strictEqual(s.ply, 1);
});

test('serializeState: cell stack is bottom-to-top in the wire format', () => {
  const game = create();
  game.place(firstPieceId(game, 'red', 'S'), 0);
  game.place(firstPieceId(game, 'blue', 'L'), 0);
  const s = game.serializeState();
  assert.deepStrictEqual(s.board[0], [[0, 0], [1, 2]]);
  assert.strictEqual(s.trays[0], 1);
  assert.strictEqual(s.trays[5], 1);
  assert.strictEqual(s.player, 0);
  assert.strictEqual(s.ply, 2);
});

test('serializeState: winner is encoded as 0 or 1 when the game ends', () => {
  const game = create();
  game.place(firstPieceId(game, 'red', 'S'), 0);
  game.place(firstPieceId(game, 'blue', 'S'), 3);
  game.place(firstPieceId(game, 'red', 'M'), 1);
  game.place(firstPieceId(game, 'blue', 'S'), 5);
  game.place(firstPieceId(game, 'red', 'L'), 2);
  const s = game.serializeState();
  assert.strictEqual(s.winner, 0);
  assert.strictEqual(s.ply, 5);
});
