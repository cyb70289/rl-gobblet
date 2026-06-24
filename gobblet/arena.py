"""Arena: baselines (random, greedy-1-ply), MCTS player, match runner, Elo.

Players implement choose_action(state) -> Action and optionally reset().
Arena plays N games with sides swapped; results from player1's perspective.
"""
from __future__ import annotations

import numpy as np
import torch

from .game import Game, State, Action, RED, BLUE
from .mcts import MCTS, choose_action as mcts_choose_action
from .encoding import action_to_index


class RandomPlayer:
    def __init__(self, rng: np.random.Generator | None = None):
        self.rng = rng if rng is not None else np.random.default_rng()

    def choose_action(self, state: State) -> Action | None:
        legal = state.legal_actions()
        if not legal:
            return None
        return legal[int(self.rng.integers(0, len(legal)))]

    def reset(self) -> None:
        pass


class Greedy1PlyPlayer:
    """1-ply lookahead: win if possible, avoid letting opponent win, cover opponent tops."""

    def __init__(self, rng: np.random.Generator | None = None):
        self.rng = rng if rng is not None else np.random.default_rng()

    def choose_action(self, state: State) -> Action | None:
        legal = state.legal_actions()
        if not legal:
            return None
        me = state.player

        # 1. immediate win
        winning = []
        for a in legal:
            ns = state.apply(a)
            if ns is not None and ns.winner == me:
                winning.append(a)
        if winning:
            return winning[int(self.rng.integers(0, len(winning)))]

        # 2. filter out moves that let opponent win next turn
        safe = []
        for a in legal:
            ns = state.apply(a)
            if ns is None or ns.is_terminal():
                safe.append(a)
                continue
            opp = ns.player
            opp_can_win = False
            for oa in ns.legal_actions():
                ns2 = ns.apply(oa)
                if ns2 is not None and ns2.winner == opp:
                    opp_can_win = True
                    break
            if not opp_can_win:
                safe.append(a)
        if not safe:
            safe = list(legal)

        # 3. prefer covering opponent tops
        covering = []
        for a in safe:
            stack = state.stack_at(a.to)
            if stack and stack[-1][0] != me:
                covering.append(a)
        if covering:
            return covering[int(self.rng.integers(0, len(covering)))]

        return safe[int(self.rng.integers(0, len(safe)))]

    def reset(self) -> None:
        pass


class MCTSPlayer:
    """Neural MCTS player for arena / interactive play."""

    def __init__(self, net, mcts_cfg, temperature: float = 0.0):
        self.mcts = MCTS(mcts_cfg, net)
        self.temperature = temperature

    def choose_action(self, state: State) -> Action | None:
        counts = self.mcts.search(state, add_noise=False)
        a = self.mcts.choose_action(counts, self.temperature)
        if a is not None:
            self.mcts.update_root(a)
        return a

    def reset(self) -> None:
        self.mcts.root = None


class Arena:
    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)

    def _play_game(self, red_player, blue_player) -> float:
        """Play one game; return result from red's perspective (1, -1, 0)."""
        red_player.reset()
        blue_player.reset()
        game = Game()
        players = {RED: red_player, BLUE: blue_player}
        while not game.is_terminal():
            p = players[game.state.player]
            a = p.choose_action(game.state)
            if a is None:
                break
            game.apply(a)
        if game.state.winner == RED:
            return 1.0
        elif game.state.winner == BLUE:
            return -1.0
        return 0.0

    def play_match(self, player1, player2, n_games: int = 100) -> list:
        """Play n_games with sides swapped; return results from player1's perspective."""
        results = []
        for i in range(n_games):
            if i % 2 == 0:
                r = self._play_game(player1, player2)   # p1=red
                results.append(r)
            else:
                r = self._play_game(player2, player1)   # p2=red, p1=blue
                results.append(-r)
        return results

    def winrate(self, player1, player2, n_games: int = 100) -> float:
        results = self.play_match(player1, player2, n_games)
        score = sum(r for r in results) / len(results)
        return (score + 1) / 2  # map [-1,1] to [0,1]


def compute_elo(match_results, n_players: int, base_elo: float = 1000,
                k: float = 32, iterations: int = 200) -> list:
    """Compute Elo from match results via iterative update.

    match_results: list of (player_a, player_b, results) where results is a
    list of game outcomes from player_a's perspective
    (1.0 = a wins, -1.0 = b wins, 0.0 = draw).
    """
    elos = [float(base_elo)] * n_players
    for _ in range(iterations):
        for pa, pb, results in match_results:
            for r in results:
                ea = 1.0 / (1.0 + 10 ** ((elos[pb] - elos[pa]) / 400))
                sa = (r + 1) / 2  # map -1,0,1 -> 0,0.5,1
                elos[pa] += k * (sa - ea)
                elos[pb] -= k * (sa - ea)
    return elos


def main():
    import argparse
    from .config import Config
    from .net import GobbletNet
    import sys

    parser = argparse.ArgumentParser(description="Run arena matches")
    parser.add_argument("--ckpt", required=True, help="checkpoint path")
    parser.add_argument("--opponent", default="greedy", choices=["random", "greedy"])
    parser.add_argument("--n-games", type=int, default=100)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    cfg = Config.for_smoke() if args.smoke else Config()
    net = GobbletNet(cfg.net)
    net.load(args.ckpt)
    net.eval()
    device = cfg.device()
    net.to(device)

    mcts_player = MCTSPlayer(net, cfg.mcts, temperature=0.0)
    if args.opponent == "random":
        opp = RandomPlayer()
    else:
        opp = Greedy1PlyPlayer()

    arena = Arena(seed=42)
    results = arena.play_match(mcts_player, opp, n_games=args.n_games)
    wins = sum(1 for r in results if r > 0)
    losses = sum(1 for r in results if r < 0)
    draws = sum(1 for r in results if r == 0)
    print(f"MCTS vs {args.opponent}: {wins}W / {draws}D / {losses}L "
          f"(win rate: {(wins + 0.5*draws)/args.n_games:.1%})")
