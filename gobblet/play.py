"""Interactive CLI play mode: human vs trained model."""
from __future__ import annotations

import argparse

import numpy as np
import torch

from .config import Config
from .game import Game, State, Action, RED, BLUE, S, M, L
from .mcts import MCTS
from .net import GobbletNet
from .encoding import action_to_index

SIZE_NAMES = {S: "S", M: "M", L: "L"}
COLOR_NAMES = {RED: "Red", BLUE: "Blue"}


def _render_board(state: State) -> str:
    """Render the 3x3 board as text."""
    lines = []
    for r in range(3):
        cells = []
        for c in range(3):
            cell = r * 3 + c
            top = state.top_at(cell)
            if top is None:
                cells.append("  .  ")
            else:
                color, size = top
                cn = "R" if color == RED else "B"
                sn = SIZE_NAMES[size]
                cells.append(f" {cn}{sn}  ")
        lines.append("|".join(cells))
        if r < 2:
            lines.append("-" * 17)
    return "\n".join(lines)


def _render_trays(state: State) -> str:
    parts = []
    for color in (RED, BLUE):
        cn = COLOR_NAMES[color]
        counts = [f"{SIZE_NAMES[s]}={state.tray_count(color, s)}" for s in (S, M, L)]
        parts.append(f"{cn} tray: {' '.join(counts)}")
    return "\n".join(parts)


def _parse_human_input(text: str) -> Action | None:
    """Parse human input like 'p s 0' (place S at cell 0) or 'm 0 1' (move 0->1)."""
    parts = text.strip().lower().split()
    if not parts:
        return None
    try:
        if parts[0] in ("p", "place"):
            size = {"s": S, "m": M, "l": L}[parts[1]]
            to = int(parts[2])
            return Action.place(size, to)
        elif parts[0] in ("m", "move"):
            frm = int(parts[1])
            to = int(parts[2])
            return Action.move(frm, to)
    except (IndexError, KeyError, ValueError):
        pass
    return None


def play(ckpt_path: str, human_color: int = BLUE, sims: int = 200,
         smoke: bool = False) -> None:
    """Play a game against the model."""
    cfg = Config.for_smoke() if smoke else Config()
    cfg.mcts.simulations = sims if not smoke else 4

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    net = GobbletNet(cfg.net).to(device)
    net.load(ckpt_path)
    net.eval()

    mcts = MCTS(cfg.mcts, net)
    game = Game()
    print(f"\n=== Gobblet — You are {COLOR_NAMES[human_color]}, "
          f"model is {COLOR_NAMES[1 - human_color]} ===")
    print("Commands: 'p <S|M|L> <cell>' to place, 'm <from> <to>' to move")
    print("Cells are 0-8 (row-major: 0,1,2 / 3,4,5 / 6,7,8)\n")

    while not game.is_terminal():
        st = game.state
        print(f"\n{COLOR_NAMES[st.player]}'s turn (ply {st.ply}):")
        print(_render_board(st))
        print(_render_trays(st))

        if st.player == human_color:
            while True:
                text = input("\nYour move: ").strip()
                if text.lower() in ("q", "quit", "exit"):
                    print("Goodbye!")
                    return
                action = _parse_human_input(text)
                if action is not None and action in st.legal_actions():
                    break
                print("Invalid move. Try again. Format: 'p S 0' or 'm 0 1'")
        else:
            print("\nModel thinking...")
            counts = mcts.search(st, add_noise=False)
            action = mcts.choose_action(counts, temperature=0.0)
            print(f"Model plays: {action}")

        game.apply(action)
        if game.state.player == human_color:
            mcts.update_root(action)

    # Game over
    print(f"\n{'=' * 30}")
    print(_render_board(game.state))
    if game.state.winner is not None:
        winner_name = COLOR_NAMES[game.state.winner]
        if game.state.winner == human_color:
            print(f"\n{winner_name} wins! You win!")
        else:
            print(f"\n{winner_name} wins! Model wins!")
    else:
        print("\nDraw!")


def main():
    parser = argparse.ArgumentParser(description="Play Gobblet against trained model")
    parser.add_argument("--ckpt", required=True, help="checkpoint path (best.pt)")
    parser.add_argument("--color", default="blue", choices=["red", "blue"],
                        help="your color (red moves first)")
    parser.add_argument("--sims", type=int, default=200, help="MCTS simulations per move")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    human_color = RED if args.color == "red" else BLUE
    play(args.ckpt, human_color=human_color, sims=args.sims, smoke=args.smoke)


if __name__ == "__main__":
    main()
