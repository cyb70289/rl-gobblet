const test = require('node:test');
const assert = require('node:assert/strict');
const { create } = require('../game.js');

function placeBoth(game, color, size, cell) {
  const p = game.tray(color).find(x => x.size === size);
  return game.place(p.id, cell);
}

test('move: relocates own top piece to an empty cell; source becomes empty, turn passes', () => {
  const game = create();
  const redS = game.tray('red').find(p => p.size === 'S');
  game.place(redS.id, 0);          // red S at cell 0
  const blueS = game.tray('blue').find(p => p.size === 'S');
  game.place(blueS.id, 4);         // blue S at cell 4 (center)
  // red's turn again: move red S from cell 0 to cell 1
  const res = game.move(0, 1);
  assert.strictEqual(res.ok, true);
  assert.strictEqual(game.topAt(0), null);
  assert.strictEqual(game.topAt(1).id, redS.id);
  assert.strictEqual(game.currentPlayer, 'blue');
});

test('move: can cover a smaller top piece at destination', () => {
  const game = create();
  const redS = game.tray('red').find(p => p.size === 'S');
  game.place(redS.id, 0);          // red S at 0
  const blueS = game.tray('blue').find(p => p.size === 'S');
  game.place(blueS.id, 4);         // blue S at 4
  // red moves S 0->4? S cannot cover S. Instead set up: red M at 1, then move it over red S at 0.
  const redM = game.tray('red').find(p => p.size === 'M');
  game.place(redM.id, 1);          // red M at 1
  const blueX = game.tray('blue').find(p => p.size === 'M');
  game.place(blueX.id, 4);         // blue M at 4
  // red's turn: move red M from 1 to 0, covering red S
  const res = game.move(1, 0);
  assert.strictEqual(res.ok, true);
  assert.strictEqual(game.topAt(0).id, redM.id);
  assert.strictEqual(game.topAt(0).size, 'M');
  // red S is now covered underneath
  const stack = game.stackAt(0);
  assert.strictEqual(stack.length, 2);
  assert.strictEqual(stack[0].id, redS.id);
  assert.strictEqual(stack[1].id, redM.id);
});

test('move: cannot move from an empty cell', () => {
  const game = create();
  const res = game.move(0, 1);
  assert.strictEqual(res.ok, false);
  assert.match(res.reason, /empty|source|no piece/i);
  assert.strictEqual(game.currentPlayer, 'red');
});

test('move: cannot move opponent top piece', () => {
  const game = create();
  const redS = game.tray('red').find(p => p.size === 'S');
  game.place(redS.id, 0);          // red S at 0 (red's piece)
  const blueS = game.tray('blue').find(p => p.size === 'S');
  game.place(blueS.id, 4);         // blue's turn: blue S at 4
  // red's turn: try to move blue's piece at cell 4
  const res = game.move(4, 1);
  assert.strictEqual(res.ok, false);
  assert.match(res.reason, /own|color|opponent/i);
  assert.strictEqual(game.currentPlayer, 'red');
});

test('move: cannot move to the same source cell (no-op)', () => {
  const game = create();
  const redS = game.tray('red').find(p => p.size === 'S');
  game.place(redS.id, 0);
  const blueS = game.tray('blue').find(p => p.size === 'S');
  game.place(blueS.id, 4);
  const res = game.move(0, 0);
  assert.strictEqual(res.ok, false);
  assert.match(res.reason, /same|no-op|source/i);
  assert.strictEqual(game.currentPlayer, 'red');
  assert.strictEqual(game.topAt(0).id, redS.id);
});

test('move: cannot cover same-size or larger at destination', () => {
  const game = create();
  const redS = game.tray('red').find(p => p.size === 'S');
  game.place(redS.id, 0);          // red S at 0
  const blueS = game.tray('blue').find(p => p.size === 'S');
  game.place(blueS.id, 4);         // blue S at 4
  // red's turn: move red S (cell 0) onto blue S (cell 4) -> same size, invalid
  const res = game.move(0, 4);
  assert.strictEqual(res.ok, false);
  assert.match(res.reason, /cover/);
  assert.strictEqual(game.currentPlayer, 'red');
});

test('move: can only move the TOP piece, not a covered piece', () => {
  // covered pieces are not accessible via move(); move() always operates on top.
  // Setting up: red S at 0, red M over it at 0. The S is covered.
  const game = create();
  const redS = game.tray('red').find(p => p.size === 'S');
  game.place(redS.id, 0);
  const blueS = game.tray('blue').find(p => p.size === 'S');
  game.place(blueS.id, 4);
  const redM = game.tray('red').find(p => p.size === 'M');
  game.place(redM.id, 0);          // red M covers red S at 0
  const blueX = game.tray('blue').find(p => p.size === 'M');
  game.place(blueX.id, 4);
  // red's turn: moving cell 0 moves the TOP (red M), not red S
  const res = game.move(0, 1);
  assert.strictEqual(res.ok, true);
  assert.strictEqual(game.topAt(0).id, redS.id, 'red S is now exposed as top at cell 0');
  assert.strictEqual(game.topAt(1).id, redM.id);
});

test('move: is allowed even when the player still has unplaced pieces in tray', () => {
  const game = create();
  const redS = game.tray('red').find(p => p.size === 'S');
  game.place(redS.id, 0);
  const blueS = game.tray('blue').find(p => p.size === 'S');
  game.place(blueS.id, 4);
  // red still has 5 pieces in tray, but chooses to move
  assert.strictEqual(game.tray('red').length, 5);
  const res = game.move(0, 1);
  assert.strictEqual(res.ok, true);
  assert.strictEqual(game.tray('red').length, 5, 'move does not change tray count');
});
