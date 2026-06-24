(function (root, factory) {
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = factory();
  } else {
    root.GobbletGame = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  const SIZES = ['S', 'M', 'L'];
  const SIZE_ORDER = { S: 0, M: 1, L: 2 };
  const COLORS = ['red', 'blue'];

  function makePieces(color) {
    const pieces = [];
    let id = 0;
    for (const size of SIZES) {
      for (let i = 0; i < 2; i++) {
        pieces.push({ id: `${color}-${size}-${id++}`, color, size });
      }
    }
    return pieces;
  }

  function create() {
    const state = {
      board: Array.from({ length: 9 }, () => []),
      trays: { red: makePieces('red'), blue: makePieces('blue') },
      currentPlayer: 'red',
      winner: null,
      history: [],
    };

    function other(color) { return color === 'red' ? 'blue' : 'red'; }

    const LINES = [
      [0, 1, 2], [3, 4, 5], [6, 7, 8],   // rows
      [0, 3, 6], [1, 4, 7], [2, 5, 8],   // cols
      [0, 4, 8], [2, 4, 6],              // diagonals
    ];

    function findWinningLines() {
      const result = { red: [], blue: [] };
      for (const line of LINES) {
        const tops = line.map(cell => {
          const stack = state.board[cell];
          return stack.length ? stack[stack.length - 1] : null;
        });
        if (!tops.every(Boolean)) continue;
        const color = tops[0].color;
        if (!tops.every(p => p.color === color)) continue;
        result[color].push({ cells: line.slice(), color });
      }
      return result;
    }

    function snapshot() {
      return {
        board: state.board.map(stack => stack.slice()),
        trays: { red: state.trays.red.slice(), blue: state.trays.blue.slice() },
        currentPlayer: state.currentPlayer,
        winner: state.winner,
      };
    }

    function pushHistory() { state.history.push(snapshot()); }

    function restoreSnapshot(snap) {
      state.board = snap.board.map(s => s.slice());
      state.trays = { red: snap.trays.red.slice(), blue: snap.trays.blue.slice() };
      state.currentPlayer = snap.currentPlayer;
      state.winner = snap.winner;
    }

    function canPlaceOn(piece, cell) {
      const stack = state.board[cell];
      if (!stack.length) return true;
      const top = stack[stack.length - 1];
      return SIZE_ORDER[piece.size] > SIZE_ORDER[top.size];
    }

    function legalActions() {
      if (state.winner) return [];
      const color = state.currentPlayer;
      const actions = [];
      for (const piece of state.trays[color]) {
        for (let cell = 0; cell < 9; cell++) {
          if (canPlaceOn(piece, cell)) actions.push({ type: 'place', pieceId: piece.id, to: cell });
        }
      }
      for (let from = 0; from < 9; from++) {
        const stack = state.board[from];
        if (!stack.length) continue;
        const piece = stack[stack.length - 1];
        if (piece.color !== color) continue;
        for (let to = 0; to < 9; to++) {
          if (to === from) continue;
          if (canPlaceOn(piece, to)) actions.push({ type: 'move', from, to });
        }
      }
      return actions;
    }

    function legalDestinationsForBoardCell(cell) {
      if (state.winner) return [];
      const stack = state.board[cell];
      if (!stack.length) return [];
      const piece = stack[stack.length - 1];
      if (piece.color !== state.currentPlayer) return [];
      const dests = [];
      for (let to = 0; to < 9; to++) {
        if (to === cell) continue;
        if (canPlaceOn(piece, to)) dests.push(to);
      }
      return dests;
    }

    function legalDestinationsForTrayPiece(pieceId) {
      if (state.winner) return [];
      const color = state.currentPlayer;
      const piece = state.trays[color].find(p => p.id === pieceId);
      if (!piece) return [];
      const dests = [];
      for (let to = 0; to < 9; to++) {
        if (canPlaceOn(piece, to)) dests.push(to);
      }
      return dests;
    }

    function applyPlace(pieceId, cell) {
      const color = state.currentPlayer;
      const tray = state.trays[color];
      const idx = tray.findIndex(p => p.id === pieceId);
      if (idx < 0) return { ok: false, reason: 'piece not in tray' };
      const piece = tray[idx];
      const stack = state.board[cell];
      if (stack.length) {
        const top = stack[stack.length - 1];
        if (SIZE_ORDER[piece.size] <= SIZE_ORDER[top.size]) {
          return { ok: false, reason: 'cannot cover same-size or larger piece' };
        }
      }
      pushHistory();
      tray.splice(idx, 1);
      stack.push(piece);
      return { ok: true };
    }

    function applyMove(fromCell, toCell) {
      if (fromCell === toCell) return { ok: false, reason: 'cannot move to the same source cell (no-op)' };
      const stack = state.board[fromCell];
      if (!stack.length) return { ok: false, reason: 'no piece at source cell' };
      const piece = stack[stack.length - 1];
      if (piece.color !== state.currentPlayer) return { ok: false, reason: 'can only move your own top piece' };
      const dest = state.board[toCell];
      if (dest.length) {
        const destTop = dest[dest.length - 1];
        if (SIZE_ORDER[piece.size] <= SIZE_ORDER[destTop.size]) {
          return { ok: false, reason: 'cannot cover same-size or larger piece' };
        }
      }
      pushHistory();
      stack.pop();
      dest.push(piece);
      return { ok: true };
    }

    function resolveAfterAction(mover) {
      const wins = findWinningLines();
      const moverWins = wins[mover].length > 0;
      const opponentWins = wins[other(mover)].length > 0;
      if (moverWins && opponentWins) state.winner = other(mover);
      else if (moverWins) state.winner = mover;
      else if (opponentWins) state.winner = other(mover);
    }

    return {
      get currentPlayer() { return state.currentPlayer; },
      get winner() { return state.winner; },
      isGameOver() { return state.winner !== null; },
      topAt(cell) { const stack = state.board[cell]; return stack.length ? stack[stack.length - 1] : null; },
      stackAt(cell) { return state.board[cell].slice(); },
      tray(color) { return state.trays[color].slice(); },

      findWinningLines() { return findWinningLines(); },

      winningCells() {
        if (!state.winner) return [];
        const lines = findWinningLines();
        const w = state.winner;
        if (lines[w].length) return lines[w][0].cells.slice();
        return [];
      },

      canUndo() { return state.history.length > 0; },

      undo() {
        if (!state.history.length) return { ok: false, reason: 'no history to undo' };
        restoreSnapshot(state.history.pop());
        return { ok: true };
      },

      legalActions() { return legalActions(); },
      legalDestinationsForBoardCell(cell) { return legalDestinationsForBoardCell(cell); },
      legalDestinationsForTrayPiece(pieceId) { return legalDestinationsForTrayPiece(pieceId); },

      serializeState() {
        const COLOR_INT = { red: 0, blue: 1 };
        const SIZE_INT = { S: 0, M: 1, L: 2 };
        const board = state.board.map(stack => stack.map(p => [COLOR_INT[p.color], SIZE_INT[p.size]]));
        const trayCounts = [0, 0, 0, 0, 0, 0];
        for (const color of COLORS) {
          for (const p of state.trays[color]) {
            trayCounts[COLOR_INT[color] * 3 + SIZE_INT[p.size]] += 1;
          }
        }
        return {
          board,
          trays: trayCounts,
          player: COLOR_INT[state.currentPlayer],
          ply: state.history.length,
          winner: state.winner === null ? null : COLOR_INT[state.winner],
          is_draw: false,
        };
      },

      place(pieceId, cell) {
        if (state.winner) return { ok: false, reason: 'game is over' };
        if (cell < 0 || cell > 8) return { ok: false, reason: 'cell out of range' };
        const mover = state.currentPlayer;
        const res = applyPlace(pieceId, cell);
        if (!res.ok) return res;
        resolveAfterAction(mover);
        if (!state.winner) state.currentPlayer = other(mover);
        return { ok: true };
      },

      move(fromCell, toCell) {
        if (state.winner) return { ok: false, reason: 'game is over' };
        if (fromCell < 0 || fromCell > 8) return { ok: false, reason: 'source cell out of range' };
        if (toCell < 0 || toCell > 8) return { ok: false, reason: 'destination cell out of range' };
        const mover = state.currentPlayer;
        const res = applyMove(fromCell, toCell);
        if (!res.ok) return res;
        resolveAfterAction(mover);
        if (!state.winner) state.currentPlayer = other(mover);
        return { ok: true };
      },
    };
  }

  return { create };
});
