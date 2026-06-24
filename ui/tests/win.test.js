const test = require('node:test');
const assert = require('node:assert/strict');
const { create } = require('../game.js');

// Helper: place a piece of given color/size to a cell, assuming it is that player's turn.
function place(game, color, size, cell) {
  const p = game.tray(color).find(x => x.size === size);
  const res = game.place(p.id, cell);
  assert.strictEqual(res.ok, true, `setup place ${color} ${size} -> ${cell} failed: ${res.reason}`);
  return res;
}

test('win: red S-M-L along row 0 (cells 0,1,2) -> red wins, winning cells are [0,1,2]', () => {
  const game = create();
  place(game, 'red', 'S', 0);
  place(game, 'blue', 'S', 3);
  place(game, 'red', 'M', 1);
  place(game, 'blue', 'S', 5);
  place(game, 'red', 'L', 2);

  assert.strictEqual(game.winner, 'red');
  assert.strictEqual(game.isGameOver(), true);
  assert.deepStrictEqual(game.winningCells().sort((a,b)=>a-b), [0, 1, 2]);
});

test('win: red L-M-S along row 0 (cells 0,1,2 with sizes L,M,S) -> red wins (reverse direction allowed)', () => {
  const game = create();
  place(game, 'red', 'L', 0);
  place(game, 'blue', 'S', 3);
  place(game, 'red', 'M', 1);
  place(game, 'blue', 'S', 5);
  place(game, 'red', 'S', 2);

  assert.strictEqual(game.winner, 'red');
  assert.deepStrictEqual(game.winningCells().sort((a,b)=>a-b), [0, 1, 2]);
});

test('win: blue S-M-L along column 0 (cells 0,3,6) -> blue wins', () => {
  const game = create();
  place(game, 'red', 'S', 1);     // red tops 1,5,7 — not a line
  place(game, 'blue', 'S', 0);
  place(game, 'red', 'M', 5);
  place(game, 'blue', 'M', 3);
  place(game, 'red', 'M', 7);
  place(game, 'blue', 'L', 6);

  assert.strictEqual(game.winner, 'blue');
  assert.deepStrictEqual(game.winningCells().sort((a,b)=>a-b), [0, 3, 6]);
});

test('win: red S-M-L along main diagonal (cells 0,4,8) -> red wins', () => {
  const game = create();
  place(game, 'red', 'S', 0);
  place(game, 'blue', 'S', 7);
  place(game, 'red', 'M', 4);
  place(game, 'blue', 'M', 6);
  place(game, 'red', 'L', 8);

  assert.strictEqual(game.winner, 'red');
  assert.deepStrictEqual(game.winningCells().sort((a,b)=>a-b), [0, 4, 8]);
});

test('win: blue L-M-S along anti-diagonal (cells 2,4,6 with sizes L,M,S) -> blue wins', () => {
  const game = create();
  place(game, 'red', 'S', 0);
  place(game, 'blue', 'L', 2);
  place(game, 'red', 'S', 1);
  place(game, 'blue', 'M', 4);
  place(game, 'red', 'M', 8);
  place(game, 'blue', 'S', 6);

  assert.strictEqual(game.winner, 'blue');
  assert.deepStrictEqual(game.winningCells().sort((a,b)=>a-b), [2, 4, 6]);
});

test('win: covered pieces do NOT count — red S,M,L in row 0 but red M is covered by blue L -> no win', () => {
  const game = create();
  place(game, 'red', 'S', 0);
  place(game, 'blue', 'S', 3);
  place(game, 'red', 'M', 1);     // red M at cell 1 (top for now)
  place(game, 'blue', 'L', 1);    // blue L covers red M at cell 1 (L > M)
  place(game, 'red', 'L', 2);     // red L at cell 2; row 0 tops: red S, blue L, red L -> NOT a red win

  assert.strictEqual(game.winner, null);
  assert.strictEqual(game.isGameOver(), false);
  assert.deepStrictEqual(game.winningCells(), []);
});

test('win: mixed colors in a line do not win — red S, blue M, red L in row 0 -> no win', () => {
  const game = create();
  place(game, 'red', 'S', 0);
  place(game, 'blue', 'M', 1);
  place(game, 'red', 'L', 2);

  assert.strictEqual(game.winner, null);
  assert.deepStrictEqual(game.winningCells(), []);
});

test('win: red S, red L, red M in row 0 (S-L-M, sizes ignored) -> red wins', () => {
  const game = create();
  place(game, 'red', 'S', 0);
  place(game, 'blue', 'S', 3);
  place(game, 'red', 'L', 1);
  place(game, 'blue', 'S', 5);
  place(game, 'red', 'M', 2);

  assert.strictEqual(game.winner, 'red');
  assert.strictEqual(game.isGameOver(), true);
  assert.deepStrictEqual(game.winningCells().sort((a,b)=>a-b), [0, 1, 2]);
});

test('win: game is locked after a win — further place/move rejected', () => {
  const game = create();
  place(game, 'red', 'S', 0);
  place(game, 'blue', 'S', 3);
  place(game, 'red', 'M', 1);
  place(game, 'blue', 'S', 5);
  place(game, 'red', 'L', 2);
  assert.strictEqual(game.winner, 'red');

  const blueL = game.tray('blue').find(p => p.size === 'L');
  const placeRes = game.place(blueL.id, 4);
  assert.strictEqual(placeRes.ok, false);
  assert.match(placeRes.reason, /over/);

  const moveRes = game.move(3, 4);
  assert.strictEqual(moveRes.ok, false);
  assert.match(moveRes.reason, /over/);
});

test('findWinningLines: reports lines for both colors from the current board state', () => {
  const game = create();
  place(game, 'red', 'S', 0);
  place(game, 'blue', 'S', 3);
  place(game, 'red', 'M', 1);
  place(game, 'blue', 'S', 5);
  place(game, 'red', 'L', 2);

  const lines = game.findWinningLines();
  assert.ok(lines.red.length >= 1, 'red should have a winning line');
  const row = lines.red.find(ln => ln.cells.join(',') === '0,1,2');
  assert.ok(row, 'red winning line should be row 0,1,2');
  assert.strictEqual(row.color, 'red');
  assert.strictEqual(lines.blue.length, 0);
});
