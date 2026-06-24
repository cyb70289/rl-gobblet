const test = require('node:test');
const assert = require('node:assert/strict');
const { create } = require('../game.js');

test('place cover rules: L can cover S, L can cover M, M can cover S (any color)', () => {
  const game = create();
  const redS = game.tray('red').find(p => p.size === 'S');
  assert.strictEqual(game.place(redS.id, 0).ok, true);

  // blue's turn now; blue L covers red S at cell 0
  const blueL = game.tray('blue').find(p => p.size === 'L');
  assert.strictEqual(game.place(blueL.id, 0).ok, true);
  assert.strictEqual(game.topAt(0).id, blueL.id);
  assert.strictEqual(game.topAt(0).color, 'blue');
  assert.strictEqual(game.topAt(0).size, 'L');
});

test('place cover rules: cannot cover same-size piece (S on S, M on M, L on L)', () => {
  const game = create();
  const redS = game.tray('red').find(p => p.size === 'S');
  game.place(redS.id, 0);
  const blueS = game.tray('blue').find(p => p.size === 'S');
  const res = game.place(blueS.id, 0);
  assert.strictEqual(res.ok, false);
  assert.match(res.reason, /cover/);
  // turn did NOT pass
  assert.strictEqual(game.currentPlayer, 'blue');
  assert.strictEqual(game.topAt(0).id, redS.id);
});

test('place cover rules: cannot cover larger piece (S on M, S on L, M on L)', () => {
  const game = create();
  const redM = game.tray('red').find(p => p.size === 'M');
  game.place(redM.id, 0);
  const blueS = game.tray('blue').find(p => p.size === 'S');
  const res = game.place(blueS.id, 0);
  assert.strictEqual(res.ok, false);
  assert.match(res.reason, /cover/);
  assert.strictEqual(game.currentPlayer, 'blue');
});

test('place: cannot place a piece that is not in the current player tray (opponent piece)', () => {
  const game = create();
  const blueS = game.tray('blue').find(p => p.size === 'S');
  // red's turn; trying to place blue's piece
  const res = game.place(blueS.id, 0);
  assert.strictEqual(res.ok, false);
  assert.match(res.reason, /tray/);
  assert.strictEqual(game.currentPlayer, 'red');
});

test('place: cannot place from a piece id that does not exist', () => {
  const game = create();
  const res = game.place('no-such-id', 0);
  assert.strictEqual(res.ok, false);
  assert.match(res.reason, /tray/);
});

test('place: cell out of range is invalid', () => {
  const game = create();
  const redS = game.tray('red').find(p => p.size === 'S');
  assert.strictEqual(game.place(redS.id, -1).ok, false);
  assert.strictEqual(game.place(redS.id, 9).ok, false);
  assert.strictEqual(game.currentPlayer, 'red');
});
