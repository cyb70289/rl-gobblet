"""State <-> tensor and action <-> index encoding.

21-channel (3,3) input tensor (plan Q5):
  ch  0..5  : stack presence of (color,size) per cell  (R,S),(R,M),(R,L),(B,S),(B,M),(B,L)
  ch  6..11 : top piece of (color,size) per cell       (same order)
  ch 12     : turn (1 if red to move, 0 if blue) broadcast
  ch 13     : own-top (1 at cells whose top belongs to player to move)
  ch 14     : ply / 100 broadcast
  ch 15..20 : tray counts per (color,size), broadcast (value 0/1/2)

Action -> 99-dim index (plan Q6):
  [0..26]   Place(size, to)        idx = size*9 + to
  [27..98]  Move(from, to)         idx = 27 + from*8 + dest_slot
            where dest_slot = to if to<from else to-1  (0..7 over non-source cells)
"""
from __future__ import annotations

import torch

from .game import State, Action, RED, BLUE, S, M, L, SIZES, COLORS

NUM_PLANES = 21
NUM_ACTIONS = 99
PLACE_BASE = 0   # 27 slots
MOVE_BASE = 27   # 72 slots
_TRAY_CHANNELS = {c * 3 + s: 15 + c * 3 + s for c in COLORS for s in SIZES}
_PRESENCE_BASE = 0
_TOP_BASE = 6


def _pair_channel(color: int, size: int) -> int:
    return color * 3 + size


def state_to_tensor(state: State) -> torch.Tensor:
    t = torch.zeros(NUM_PLANES, 3, 3, dtype=torch.float32)
    for cell in range(9):
        r, c = divmod(cell, 3)
        stack = state.board[cell]
        for (color, size) in stack:
            ch = _PRESENCE_BASE + _pair_channel(color, size)
            t[ch, r, c] = 1.0
        if stack:
            top_color, top_size = stack[-1]
            t[_TOP_BASE + _pair_channel(top_color, top_size), r, c] = 1.0
            if top_color == state.player:
                t[13, r, c] = 1.0  # own-top
    # turn plane (12)
    if state.player == RED:
        t[12, :, :] = 1.0
    # ply plane (14)
    t[14, :, :] = state.ply / 100.0
    # tray planes (15..20), broadcast
    for color in COLORS:
        for size in SIZES:
            ch = 15 + _pair_channel(color, size)
            t[ch, :, :] = float(state.tray_count(color, size))
    return t


def states_to_batch(states) -> torch.Tensor:
    if not states:
        return torch.zeros(0, NUM_PLANES, 3, 3, dtype=torch.float32)
    return torch.stack([state_to_tensor(s) for s in states], dim=0)


# ---------------- action <-> index ----------------
def action_to_index(action: Action) -> int:
    if action.kind == "place":
        return PLACE_BASE + action.size * 9 + action.to
    else:
        frm, to = action.from_, action.to
        dest_slot = to if to < frm else to - 1
        return MOVE_BASE + frm * 8 + dest_slot


def index_to_action(idx: int) -> Action:
    if idx < MOVE_BASE:
        size, to = divmod(idx, 9)
        return Action.place(size, to)
    m = idx - MOVE_BASE
    frm, dest_slot = divmod(m, 8)
    to = dest_slot if dest_slot < frm else dest_slot + 1
    return Action.move(frm, to)


def apply_index(state: State, idx: int) -> State:
    return state.apply(index_to_action(idx))


# ---------------- legal masks ----------------
def legal_mask(state: State) -> torch.Tensor:
    mask = torch.zeros(NUM_ACTIONS, dtype=torch.bool)
    for a in state.legal_actions():
        mask[action_to_index(a)] = True
    return mask


def legal_mask_batch(states) -> torch.Tensor:
    if not states:
        return torch.zeros(0, NUM_ACTIONS, dtype=torch.bool)
    return torch.stack([legal_mask(s) for s in states], dim=0)


def legal_indices(state: State):
    """Return (indices, actions) for legal actions — handy for MCTS."""
    acts = state.legal_actions()
    idxs = [action_to_index(a) for a in acts]
    return idxs, acts
