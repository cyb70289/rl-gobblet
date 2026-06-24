"""Batched self-play runner: 64 concurrent games, batched MCTS, tree reuse.

Produces (state_tensor, policy_target, value_target) samples for training.
Temperature tau=1 for first `temperature_plies` plies (exploration), then 0.
"""
from __future__ import annotations

import numpy as np
import torch
from tqdm import tqdm

from .config import Config
from .encoding import state_to_tensor, action_to_index
from .game import Game
from .mcts import batched_mcts_search, choose_action


class SelfPlayRunner:
    def __init__(self, cfg: Config, net):
        self.cfg = cfg
        self.net = net
        self.rng = np.random.default_rng()

    def run(self, num_games: int | None = None, show_progress: bool = False) -> list:
        """Run num_games self-play games; return list of (state_t, policy_t, value)."""
        if num_games is None:
            num_games = self.cfg.selfplay.games_per_iter

        concurrent = self.cfg.selfplay.concurrent_games
        temp_plies = self.cfg.mcts.temperature_plies
        all_samples: list = []

        games: list[Game] = []
        trees: list = []
        recordings: list[list] = []
        active: list[int] = []
        started = 0

        pbar = tqdm(total=num_games, desc="self-play", disable=not show_progress)

        def fill_slots():
            nonlocal started
            while len(active) < concurrent and started < num_games:
                idx = len(games)
                games.append(Game())
                trees.append(None)
                recordings.append([])
                active.append(idx)
                started += 1

        fill_slots()

        while active:
            # --- batched MCTS on all active games ---
            active_states = [games[i].state for i in active]
            active_roots = [trees[i] for i in active]
            counts_list, new_roots = batched_mcts_search(
                active_states, self.cfg.mcts, self.net,
                add_noise=True, roots=active_roots, rng=self.rng,
            )
            for j, i in enumerate(active):
                trees[i] = new_roots[j]

            # --- choose + apply actions, record samples ---
            for j, i in enumerate(active):
                st = games[i].state
                ply = st.ply
                tau = 1.0 if ply < temp_plies else 0.0
                action = choose_action(counts_list[j], temperature=tau, rng=self.rng)
                if action is None:
                    continue

                # record (state_tensor, policy_target, player_to_move)
                state_t = state_to_tensor(st)
                counts = counts_list[j]
                total = counts.sum().item()
                policy_t = counts / total if total > 0 else counts
                recordings[i].append((state_t, policy_t, st.player))

                # apply action
                games[i].apply(action)

                # tree reuse: descend to child
                root = trees[i]
                idx_a = action_to_index(action)
                if root is not None and not root.is_terminal and idx_a in root.children:
                    trees[i] = root.children[idx_a]
                    trees[i].parent = None
                else:
                    trees[i] = None

            # --- collect finished games ---
            still_active = []
            for i in active:
                g = games[i]
                if g.is_terminal():
                    ts = g.state
                    for state_t, policy_t, player in recordings[i]:
                        if ts.winner is not None:
                            value = 1.0 if ts.winner == player else -1.0
                        else:
                            value = 0.0  # draw
                        all_samples.append((state_t, policy_t, value))
                    pbar.update(1)
                else:
                    still_active.append(i)
            active = still_active
            fill_slots()

        pbar.close()
        return all_samples
