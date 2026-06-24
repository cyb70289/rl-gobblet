(function () {
  'use strict';

  const GobbletGame = window.GobbletGame;
  let game = GobbletGame.create();
  let selected = null; // {kind:'tray', pieceId} | {kind:'board', cell} | null

  // ---- model-mode state ----
  let mode = 'manual';            // 'manual' | 'model'
  let humanColor = 'red';         // 'red' | 'blue' (which color the human plays in model mode)
  let modelAvailable = false;     // /api/health result
  let modelThinking = false;      // /api/move request in flight
  let animating = false;          // shine animation in progress
  let lastError = null;           // most recent model error message (banner)
  let requestSeq = 0;             // discard stale /api/move responses

  const RADII = { S: 20, M: 32, L: 44 };
  const SIZE_ORDER = ['S', 'M', 'L'];
  const BRIGHT = { red: [8, 78, 55], blue: [205, 70, 55] };
  const DARK = { red: [8, 55, 28], blue: [205, 55, 26] };
  const COLOR_INT = { red: 0, blue: 1 };
  const INT_COLOR = ['red', 'blue'];

  const ANIM = (typeof window !== 'undefined' && window.__gobbletAnim) || { shineMs: 1000 };

  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

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
  const modeSelect = el('mode-select');
  const colorSelect = el('color-select');
  const colorPicker = el('color-picker');
  const modelStatus = el('model-status');

  function otherColor(c) { return c === 'red' ? 'blue' : 'red'; }
  function modelColor() { return mode === 'model' ? otherColor(humanColor) : null; }
  function isHumanTurn() {
    return mode === 'manual' || game.currentPlayer === humanColor;
  }
  function isModelTurn() {
    return mode === 'model' && modelAvailable && !game.winner && game.currentPlayer === modelColor();
  }

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
    const interactive = !game.winner && isHumanTurn() && !modelThinking;
    if (interactive) node.classList.add('active', color);

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
      if (modelThinking) cellDiv.classList.add('locked');

      const stack = game.stackAt(cell);
      if (stack.length) {
        const outerFirst = stack.slice().reverse();
        cellDiv.appendChild(buildPieceSvg(outerFirst));
      }
      cellDiv.addEventListener('click', () => onCellClick(cell));
      boardEl.appendChild(cellDiv);
    }
  }

  function endText() {
    if (mode === 'model') {
      return game.winner === humanColor ? 'You win!' : 'Model wins!';
    }
    return `${capitalize(game.winner)} wins!`;
  }

  function modelStatusText() {
    if (mode === 'manual') return '';
    if (modelThinking) return 'model: thinking…';
    if (!modelAvailable) return 'model: not available';
    return 'model: ready';
  }

  function modelStatusState() {
    if (mode === 'manual') return 'off';
    if (modelThinking) return 'thinking';
    if (!modelAvailable) return 'down';
    return 'ready';
  }

  function render() {
    const validSet = validDestinations();
    const winningSet = new Set(game.winningCells());

    if (lastError && !game.winner) {
      turnLabelEl.textContent = lastError;
      turnLabelEl.className = 'turn-label error';
      bannerEl.textContent = lastError;
      bannerEl.className = 'banner error';
    } else if (game.winner) {
      const txt = endText();
      turnLabelEl.textContent = txt;
      turnLabelEl.className = `turn-label ${game.winner}`;
      bannerEl.textContent = txt;
      bannerEl.className = `banner ${game.winner}`;
    } else if (modelThinking) {
      const c = capitalize(game.currentPlayer);
      turnLabelEl.textContent = `${c} is thinking…`;
      turnLabelEl.className = `turn-label ${game.currentPlayer} thinking`;
      bannerEl.className = 'banner hidden';
      bannerEl.textContent = '';
    } else {
      turnLabelEl.textContent = `${capitalize(game.currentPlayer)}'s turn`;
      turnLabelEl.className = `turn-label ${game.currentPlayer}`;
      bannerEl.className = 'banner hidden';
      bannerEl.textContent = '';
    }

    renderTray(blueTrayEl, 'blue');
    renderTray(redTrayEl, 'red');
    renderBoard(validSet, winningSet);

    undoBtn.disabled = !game.canUndo() || modelThinking || animating;

    // mode controls
    colorPicker.classList.toggle('hidden', mode !== 'model');
    const modeSelectDisabled = modelThinking || animating;
    modeSelect.disabled = modeSelectDisabled;
    colorSelect.disabled = modeSelectDisabled || mode !== 'model';
    modelStatus.textContent = modelStatusText();
    modelStatus.dataset.state = modelStatusState();

    // disable the "model" option in the mode select if model is unavailable
    const modelOpt = modeSelect.querySelector('option[value="model"]');
    if (modelOpt) {
      modelOpt.disabled = !modelAvailable;
      modelOpt.textContent = modelAvailable ? 'Human vs Model' : 'Human vs Model (offline)';
    }
    if (mode === 'model' && !modelAvailable && !modelThinking) {
      // force back to manual if model became unavailable
      mode = 'manual';
      modeSelect.value = 'manual';
      colorPicker.classList.add('hidden');
    }
  }

  function capitalize(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

  function isOwnTopPiece(cell) {
    const top = game.topAt(cell);
    return top && top.color === game.currentPlayer;
  }

  function onTrayPieceClick(color, pieceId) {
    if (game.winner || modelThinking || animating) return;
    if (!isHumanTurn()) return;
    if (color !== game.currentPlayer) return;
    if (selected && selected.kind === 'tray' && selected.pieceId === pieceId) {
      selected = null;
    } else {
      selected = { kind: 'tray', pieceId };
    }
    render();
  }

  function onCellClick(cell) {
    if (game.winner || modelThinking || animating) return;

    if (!selected) {
      if (isOwnTopPiece(cell) && isHumanTurn()) {
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

    if (isOwnTopPiece(cell) && isHumanTurn()) {
      selected = { kind: 'board', cell };
      render();
      return;
    }

    flashCell(cell);
  }

  function resolveSourceElement(sel) {
    if (!sel) return null;
    if (sel.kind === 'tray') {
      return document.querySelector(
        `.tray-slot[data-color="${game.currentPlayer}"][data-piece-id="${sel.pieceId}"]`
      );
    }
    if (sel.kind === 'board') {
      return boardEl.querySelector(`.cell[data-cell="${sel.cell}"]`);
    }
    return null;
  }

  async function executeAction(cell) {
    const startSeq = requestSeq;
    animating = true;
    render();

    const sourceEl = resolveSourceElement(selected);
    if (!sourceEl) {
      animating = false;
      render();
      flashCell(cell);
      return;
    }

    sourceEl.classList.add('shine');
    await sleep(ANIM.shineMs);
    // On requestSeq mismatch, restartGame() is the only caller that bumps
    // requestSeq during an action; it always resets animating=false too,
    // so we don't need to do it here.
    if (startSeq !== requestSeq) return;
    sourceEl.classList.remove('shine');

    let res;
    if (selected.kind === 'tray') {
      res = game.place(selected.pieceId, cell);
    } else {
      res = game.move(selected.cell, cell);
    }
    selected = null;

    if (!res.ok) {
      animating = false;
      render();
      flashCell(cell);
      return;
    }

    render();
    if (startSeq !== requestSeq) return;

    const destEl = boardEl.querySelector(`.cell[data-cell="${cell}"]`);
    if (destEl) {
      destEl.classList.add('shine');
      await sleep(ANIM.shineMs);
      if (startSeq !== requestSeq) return;
      destEl.classList.remove('shine');
    }

    animating = false;

    if (game.winner) {
      render();
    } else if (isModelTurn()) {
      maybeFireModelMove();
    } else {
      render();
    }
  }

  function flashCell(cell) {
    const node = boardEl.querySelector(`.cell[data-cell="${cell}"]`);
    if (!node) return;
    node.classList.remove('flash');
    void node.offsetWidth;
    node.classList.add('flash');
  }

  // ---- model-mode network calls ----

  function applyServerAction(action) {
    if (action.kind === 'place') {
      const sizeName = SIZE_ORDER[action.size];
      const piece = game.tray(game.currentPlayer).find(p => p.size === sizeName);
      if (!piece) {
        showError('Model returned a place action with no available piece');
        return false;
      }
      const res = game.place(piece.id, action.to);
      if (!res.ok) {
        showError(`Model move rejected: ${res.reason}`);
        return false;
      }
    } else if (action.kind === 'move') {
      const res = game.move(action.from_, action.to);
      if (!res.ok) {
        showError(`Model move rejected: ${res.reason}`);
        return false;
      }
    } else {
      showError(`Unknown action kind: ${action.kind}`);
      return false;
    }
    return true;
  }

  async function applyServerActionAnimated(action) {
    const startSeq = requestSeq;

    modelThinking = false;
    animating = true;
    render();

    let sourceEl;
    if (action.kind === 'place') {
      const sizeName = SIZE_ORDER[action.size];
      const piece = game.tray(game.currentPlayer).find(p => p.size === sizeName);
      if (!piece) {
        showError('Model returned a place action with no available piece');
        animating = false;
        return;
      }
      sourceEl = document.querySelector(
        `.tray-slot[data-color="${game.currentPlayer}"][data-piece-id="${piece.id}"]`
      );
    } else if (action.kind === 'move') {
      sourceEl = boardEl.querySelector(`.cell[data-cell="${action.from_}"]`);
    } else {
      showError(`Unknown action kind: ${action.kind}`);
      animating = false;
      return;
    }

    if (sourceEl) {
      sourceEl.classList.add('shine');
      await sleep(ANIM.shineMs);
      if (startSeq !== requestSeq) {
        animating = false;
        return;
      }
      sourceEl.classList.remove('shine');
    }

    const ok = applyServerAction(action);
    if (!ok) {
      animating = false;
      render();
      return;
    }
    render();
    if (startSeq !== requestSeq) {
      animating = false;
      return;
    }

    const destEl = boardEl.querySelector(`.cell[data-cell="${action.to}"]`);
    if (destEl) {
      destEl.classList.add('shine');
      await sleep(ANIM.shineMs);
      if (startSeq !== requestSeq) {
        animating = false;
        return;
      }
      destEl.classList.remove('shine');
    }

    animating = false;

    if (game.winner) {
      render();
    } else if (isModelTurn()) {
      maybeFireModelMove();
    } else {
      render();
    }
  }

  function showError(msg) {
    lastError = msg;
    modelAvailable = false;  // disable model mode for the rest of the session
    setTimeout(() => { if (lastError === msg) { lastError = null; render(); } }, 6000);
    render();
  }

  async function checkHealth() {
    try {
      const r = await fetch('/api/health');
      if (!r.ok) throw new Error(`status ${r.status}`);
      const body = await r.json();
      modelAvailable = !!body.model_loaded;
    } catch (e) {
      modelAvailable = false;
    }
    render();
    if (isModelTurn()) maybeFireModelMove();
  }

  async function maybeFireModelMove() {
    if (!isModelTurn()) return;
    if (modelThinking) return;
    if (animating) return;
    modelThinking = true;
    const seq = ++requestSeq;
    render();
    try {
      const r = await fetch('/api/move', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          state: game.serializeState(),
          modelColor: COLOR_INT[game.currentPlayer],
        }),
      });
      if (seq !== requestSeq) return;
      if (!r.ok) {
        const txt = await r.text();
        throw new Error(`status ${r.status}: ${txt.slice(0, 100)}`);
      }
      const body = await r.json();
      if (seq !== requestSeq) return;
      await applyServerActionAnimated(body.action);
    } catch (e) {
      if (seq !== requestSeq) return;
      showError(`Model error: ${e.message}`);
      modelThinking = false;
      animating = false;
      render();
    }
  }

  function restartGame() {
    game = GobbletGame.create();
    selected = null;
    lastError = null;
    animating = false;
    modelThinking = false;
    requestSeq++;
    render();
    if (isModelTurn()) maybeFireModelMove();
  }

  // ---- event wiring ----

  modeSelect.addEventListener('change', () => {
    if (modeSelect.value === mode) return;
    mode = modeSelect.value;
    restartGame();
  });

  colorSelect.addEventListener('change', () => {
    if (colorSelect.value === humanColor) return;
    humanColor = colorSelect.value;
    restartGame();
  });

  undoBtn.addEventListener('click', () => {
    if (modelThinking) return;
    if (animating) return;
    if (!game.canUndo()) return;
    if (mode === 'model') {
      if (game.canUndo()) game.undo();
      if (game.canUndo() && !game.winner) game.undo();
    } else {
      game.undo();
    }
    selected = null;
    render();
  });

  restartBtn.addEventListener('click', () => {
    restartGame();
  });

  // initial render + health check
  render();
  checkHealth();
})();
