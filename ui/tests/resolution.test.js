const test = require('node:test');
const assert = require('node:assert/strict');
const { create } = require('../game.js');

function place(game, color, size, cell) {
  const p = game.tray(color).find(x => x.size === size);
  const res = game.place(p.id, cell);
  assert.strictEqual(res.ok, true, `setup place ${color} ${size} -> ${cell} failed: ${res.reason}`);
}

test('resolution: a MOVE that completes the mover own line -> mover wins', () => {
  const game = create();
  place(game, 'red', 'S', 0);
  place(game, 'blue', 'S', 5);
  place(game, 'red', 'M', 1);
  place(game, 'blue', 'M', 7);
  place(game, 'red', 'L', 4);   // red L sits on cell 4 (not part of row 0)
  place(game, 'blue', 'M', 6);  // blue: S@5, M@7, M@6 — no line
  // red's turn: move red L from 4 -> 2 completing row 0 S-M-L
  const res = game.move(4, 2);
  assert.strictEqual(res.ok, true);
  assert.strictEqual(game.winner, 'red');
  assert.deepStrictEqual(game.winningCells().sort((a,b)=>a-b), [0, 1, 2]);
});

test('resolution: a MOVE that uncovers the opponent winning line (mover has no win) -> opponent wins', () => {
  // blue has S@3, M@4, L@5 (row 1) but blue M@4 is hidden under red L@4.
  // red moves its L off cell 4 -> uncovers blue M -> blue row 1 S-M-L completes.
  const game = create();
  place(game, 'red', 'S', 0);
  place(game, 'blue', 'S', 3);
  place(game, 'red', 'M', 1);
  place(game, 'blue', 'M', 4);
  place(game, 'red', 'L', 4);   // red L covers blue M at cell 4
  place(game, 'blue', 'L', 5);  // blue L at 5; row 1 tops: blue S, red L, blue L — not a blue win
  // red's turn: move red L from 4 -> 8 (uncovers blue M at 4)
  const res = game.move(4, 8);
  assert.strictEqual(res.ok, true);
  assert.strictEqual(game.winner, 'blue');
  assert.deepStrictEqual(game.winningCells().sort((a,b)=>a-b), [3, 4, 5]);
});

test('resolution: a MOVE that creates mover win AND uncovers opponent win (both) -> opponent (non-mover) wins', () => {
  // red mover: moving L from 4 -> 2 completes red row 0 (S@0,M@1,L@2)
  //   AND uncovers blue M@4 completing blue row 1 (S@3,M@4,L@5).
  //   Both win -> opponent (blue) wins.
  const game = create();
  place(game, 'red', 'S', 0);
  place(game, 'blue', 'S', 3);
  place(game, 'red', 'M', 1);
  place(game, 'blue', 'M', 4);
  place(game, 'red', 'L', 4);   // red L covers blue M at cell 4
  place(game, 'blue', 'L', 5);  // blue row 1 not yet winning (cell 4 is red L)
  // red's turn: move red L from 4 -> 2
  const res = game.move(4, 2);
  assert.strictEqual(res.ok, true);
  // both have a winning line -> opponent of mover (blue) wins
  assert.strictEqual(game.winner, 'blue');
  const lines = game.findWinningLines();
  assert.ok(lines.red.length >= 1, 'red should also have a winning line');
  assert.ok(lines.blue.length >= 1, 'blue should have a winning line');
});
