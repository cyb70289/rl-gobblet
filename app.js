(function () {
  'use strict';

  const GobbleGame = window.GobbleGame;
  let game = GobbleGame.create();
  let selected = null; // {kind:'tray', pieceId} | {kind:'board', cell} | null

  const RADII = { S: 20, M: 32, L: 44 };
  const SIZE_ORDER = ['S', 'M', 'L'];
  const BRIGHT = { red: [8, 78, 55], blue: [205, 70, 55] };
  const DARK = { red: [8, 55, 28], blue: [205, 55, 26] };

  function shade(color, depthFromTop) {
    const b = BRIGHT[color], d = DARK[color];
    const t = Math.min(depthFromTop, 2) / 2;
    const h = b[0] + (d[0] - b[0]) * t;
    const s = b[1] + (d[1] - b[1]) * t;
    const l = b[2] + (d[2] - b[2]) * t;
    return `hsl(${h.toFixed(1)}, ${s.toFixed(1)}%, ${l.toFixed(1)}%)`;
  }

  function buildPieceSvg(piecesOuterFirst) {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 100 100');
    svg.setAttribute('width', '100%');
    svg.setAttribute('height', '100%');
    piecesOuterFirst.forEach((p, idx) => {
      const c = document.createElementNS(ns, 'circle');
      c.setAttribute('cx', '50');
      c.setAttribute('cy', '50');
      c.setAttribute('r', String(RADII[p.size]));
      c.setAttribute('fill', shade(p.color, idx));
      svg.appendChild(c);
    });
    return svg;
  }

  const el = (id) => document.getElementById(id);
  const boardEl = el('board');
  const blueTrayEl = el('blue-tray');
  const redTrayEl = el('red-tray');
  const turnLabelEl = el('turn-label');
  const bannerEl = el('banner');
  const undoBtn = el('undo-btn');
  const restartBtn = el('restart-btn');

  function sortedTray(color) {
    return game.tray(color).slice().sort((a, b) => SIZE_ORDER.indexOf(a.size) - SIZE_ORDER.indexOf(b.size));
  }

  function validDestinations() {
    if (!selected) return new Set();
    if (selected.kind === 'tray') return new Set(game.legalDestinationsForTrayPiece(selected.pieceId));
    return new Set(game.legalDestinationsForBoardCell(selected.cell));
  }

  function clearNode(node) { while (node.firstChild) node.removeChild(node.firstChild); }

  function renderTray(node, color) {
    clearNode(node);
    node.classList.remove('active', 'red', 'blue');
    if (!game.winner && game.currentPlayer === color) node.classList.add('active', color);

    const pieces = sortedTray(color);
    pieces.forEach((p) => {
      const slot = document.createElement('div');
      slot.className = 'tray-slot';
      slot.dataset.color = color;
      slot.dataset.pieceId = p.id;
      slot.appendChild(buildPieceSvg([p]));
      if (selected && selected.kind === 'tray' && selected.pieceId === p.id) {
        slot.classList.add('selected');
      }
      slot.addEventListener('click', () => onTrayPieceClick(color, p.id));
      node.appendChild(slot);
    });
  }

  function renderBoard(validSet, winningSet) {
    clearNode(boardEl);
    for (let cell = 0; cell < 9; cell++) {
      const cellDiv = document.createElement('div');
      cellDiv.className = 'cell';
      cellDiv.dataset.cell = String(cell);

      if (validSet.has(cell)) cellDiv.classList.add('valid');
      if (selected && selected.kind === 'board' && selected.cell === cell) cellDiv.classList.add('selected');
      if (winningSet.has(cell)) cellDiv.classList.add('winning');

      const stack = game.stackAt(cell); // bottom -> top
      if (stack.length) {
        const outerFirst = stack.slice().reverse(); // top (largest) first
        cellDiv.appendChild(buildPieceSvg(outerFirst));
      }
      cellDiv.addEventListener('click', () => onCellClick(cell));
      boardEl.appendChild(cellDiv);
    }
  }

  function render() {
    const validSet = validDestinations();
    const winningSet = new Set(game.winningCells());

    if (game.winner) {
      turnLabelEl.textContent = `${capitalize(game.winner)} wins`;
      turnLabelEl.className = `turn-label ${game.winner}`;
      bannerEl.textContent = `${capitalize(game.winner)} wins!`;
      bannerEl.className = `banner ${game.winner}`;
    } else {
      turnLabelEl.textContent = `${capitalize(game.currentPlayer)}'s turn`;
      turnLabelEl.className = `turn-label ${game.currentPlayer}`;
      bannerEl.className = 'banner hidden';
      bannerEl.textContent = '';
    }

    renderTray(blueTrayEl, 'blue');
    renderTray(redTrayEl, 'red');
    renderBoard(validSet, winningSet);

    undoBtn.disabled = !game.canUndo();
  }

  function capitalize(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

  function isOwnTopPiece(cell) {
    const top = game.topAt(cell);
    return top && top.color === game.currentPlayer;
  }

  function onTrayPieceClick(color, pieceId) {
    if (game.winner) return;
    if (color !== game.currentPlayer) return;
    if (selected && selected.kind === 'tray' && selected.pieceId === pieceId) {
      selected = null;
    } else {
      selected = { kind: 'tray', pieceId };
    }
    render();
  }

  function onCellClick(cell) {
    if (game.winner) return;

    if (!selected) {
      if (isOwnTopPiece(cell)) {
        selected = { kind: 'board', cell };
        render();
      }
      return;
    }

    const validSet = validDestinations();
    if (validSet.has(cell)) {
      executeAction(cell);
      return;
    }

    if (selected.kind === 'board' && selected.cell === cell) {
      selected = null;
      render();
      return;
    }

    if (isOwnTopPiece(cell)) {
      selected = { kind: 'board', cell };
      render();
      return;
    }

    flashCell(cell);
  }

  function executeAction(cell) {
    let res;
    if (selected.kind === 'tray') {
      res = game.place(selected.pieceId, cell);
    } else {
      res = game.move(selected.cell, cell);
    }
    if (res.ok) {
      selected = null;
      render();
    } else {
      flashCell(cell);
    }
  }

  function flashCell(cell) {
    const node = boardEl.querySelector(`.cell[data-cell="${cell}"]`);
    if (!node) return;
    node.classList.remove('flash');
    void node.offsetWidth; // reflow to restart animation
    node.classList.add('flash');
  }

  undoBtn.addEventListener('click', () => {
    if (!game.canUndo()) return;
    game.undo();
    selected = null;
    render();
  });

  restartBtn.addEventListener('click', () => {
    game = GobbleGame.create();
    selected = null;
    render();
  });

  render();
})();
