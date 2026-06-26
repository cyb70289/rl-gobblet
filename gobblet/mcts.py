"""AlphaZero MCTS with batched leaf evaluation and tree reuse.

PUCT selection, Dirichlet noise at root, virtual-loss-free synchronous batching.
Each simulation round: select one leaf per concurrent root, batch-evaluate all
non-terminal leaves with one forward pass, expand + backup. 3-fold repetition
is detected along the search path (per-game); ply-cap draws come from State.
"""
from __future__ import annotations

import math

import numpy as np
import torch

from .config import MCTSConfig
from .encoding import (
    states_to_batch, legal_mask_batch,
    action_to_index, index_to_action, NUM_ACTIONS,
)


class _Node:
    """A single MCTS node with lazy state creation.

    Child states are only materialized when the child is actually traversed
    (selected via PUCT), not when the child is first created during expansion.
    This avoids ~45x redundant State.apply() calls per expansion.
    """

    __slots__ = (
        "_state", "_action", "parent", "action_idx", "prior", "original_prior",
        "children", "visit_count", "value_sum", "is_expanded",
        "_terminal", "_terminal_value", "_state_created",
    )

    def __init__(self, state=None, action=None, parent=None, action_idx=None, prior=0.0):
        self._state = state
        self._action = action
        self.parent = parent
        self.action_idx = action_idx
        self.prior = prior
        self.original_prior = prior
        self.children: dict[int, _Node] = {}
        self.visit_count = 0
        self.value_sum = 0.0
        self.is_expanded = False
        self._state_created = state is not None
        if state is not None:
            self._terminal = state.is_terminal()
            self._terminal_value = state.value_for_current() if self._terminal else 0.0
        else:
            self._terminal = None
            self._terminal_value = None

    def _ensure_state(self):
        if not self._state_created:
            self._state = self.parent.state.apply(self._action)
            self._state_created = True
            self._terminal = self._state.is_terminal()
            self._terminal_value = (
                self._state.value_for_current() if self._terminal else 0.0
            )

    @property
    def state(self):
        if not self._state_created:
            self._ensure_state()
        return self._state

    @property
    def is_terminal(self) -> bool:
        if self._terminal is None:
            self._ensure_state()
        return self._terminal

    @property
    def terminal_value(self) -> float:
        if self._terminal_value is None:
            self._ensure_state()
        return self._terminal_value


def _select_child(node: _Node, cfg: MCTSConfig) -> _Node:
    """Pick child maximizing PUCT = Q + c_puct * P * sqrt(N_parent) / (1 + N_child)."""
    sqrt_n = math.sqrt(node.visit_count + 1)
    best_score = -float("inf")
    best_child = None
    for child in node.children.values():
        if child.visit_count > 0:
            q = -child.value_sum / child.visit_count
        else:
            q = 0.0
        u = cfg.c_puct * child.prior * sqrt_n / (1 + child.visit_count)
        score = q + u
        if score > best_score:
            best_score = score
            best_child = child
    return best_child


def _expand(leaf: _Node, probs: torch.Tensor, legal_idxs, legal_acts) -> None:
    """Create children for all legal actions (lazy: no state created yet)."""
    for idx, action in zip(legal_idxs, legal_acts):
        p = probs[idx].item()
        child = _Node(action=action, parent=leaf, action_idx=idx, prior=p)
        leaf.children[idx] = child
    leaf.is_expanded = True


def _add_dirichlet_noise(root: _Node, cfg: MCTSConfig) -> None:
    n = len(root.children)
    if n == 0:
        return
    noise = np.random.dirichlet([cfg.dirichlet_alpha] * n)
    for j, child in enumerate(root.children.values()):
        child.prior = (
            (1 - cfg.dirichlet_weight) * child.original_prior
            + cfg.dirichlet_weight * float(noise[j])
        )


def _backup(path: list, value: float) -> None:
    """Walk from leaf to root, flipping sign at each level."""
    v = value
    for node in reversed(path):
        node.visit_count += 1
        node.value_sum += v
        v = -v


def batched_mcts_search(
    states, cfg: MCTSConfig, net, add_noise: bool = True,
    roots=None, rng: np.random.Generator | None = None,
):
    """Run MCTS on multiple roots with batched NN evaluation.

    Returns (counts_list, roots). counts_list[i] is a (NUM_ACTIONS,) tensor
    of visit counts for states[i]. roots can be passed back on the next call
    for tree reuse.
    """
    device = next(net.parameters()).device
    rng = rng if rng is not None else np.random.default_rng()

    # --- init / reuse roots ---
    if roots is None:
        roots = [None] * len(states)
    new_roots = []
    for st, root in zip(states, roots):
        if root is not None and root.state.position_key == st.position_key:
            new_roots.append(root)
        else:
            new_roots.append(_Node(st))
    roots = new_roots

    n_sims = cfg.simulations

    # --- pre-expand non-terminal roots (batched) ---
    # This ensures every simulation visits at least one root child,
    # so children visit counts sum to exactly n_sims.
    need_root_expand = [
        i for i, r in enumerate(roots)
        if not r.is_terminal and not r.is_expanded
    ]
    # Re-add noise to already-expanded roots (from tree reuse)
    if add_noise:
        for r in roots:
            if not r.is_terminal and r.is_expanded:
                _add_dirichlet_noise(r, cfg)

    if need_root_expand:
        eval_states = [roots[i].state for i in need_root_expand]
        batch = states_to_batch(eval_states).to(device)
        masks = legal_mask_batch(eval_states).to(device)
        net.eval()
        with torch.no_grad():
            logits, _values = net(batch)
            probs = net.policy_probs(logits, masks)
        probs_cpu = probs.cpu()
        for j, i in enumerate(need_root_expand):
            root = roots[i]
            acts = root.state.legal_actions()
            idxs = [action_to_index(a) for a in acts]
            _expand(root, probs_cpu[j], idxs, acts)
            if add_noise:
                _add_dirichlet_noise(root, cfg)

    for _sim in range(n_sims):
        # --- selection ---
        paths: list[list] = []
        need_eval_idx: list[int] = []
        need_eval_states: list = []
        terminal_backups: list[tuple[int, float]] = []

        for i, root in enumerate(roots):
            path = [root]
            node = root
            while not node.is_terminal and node.is_expanded:
                child = _select_child(node, cfg)
                if child is None:
                    break
                path.append(child)
                node = child
            paths.append(path)

            if node.is_terminal:
                terminal_backups.append((i, node.terminal_value))
            else:
                need_eval_idx.append(i)
                need_eval_states.append(node.state)

        # --- batched NN eval ---
        if need_eval_states:
            batch = states_to_batch(need_eval_states).to(device)
            masks = legal_mask_batch(need_eval_states).to(device)
            net.eval()
            with torch.no_grad():
                logits, values = net(batch)
                probs = net.policy_probs(logits, masks)
            values_cpu = values.squeeze(-1).cpu()
            probs_cpu = probs.cpu()

            for j, gi in enumerate(need_eval_idx):
                leaf = paths[gi][-1]
                st = leaf.state
                acts = st.legal_actions()
                idxs = [action_to_index(a) for a in acts]
                _expand(leaf, probs_cpu[j], idxs, acts)
                if leaf is roots[gi] and add_noise:
                    _add_dirichlet_noise(leaf, cfg)
                v = values_cpu[j].item()
                _backup(paths[gi], v)

        # --- terminal/path-draw backup ---
        for gi, v in terminal_backups:
            _backup(paths[gi], v)

    # --- collect visit counts ---
    results = []
    for root in roots:
        counts = torch.zeros(NUM_ACTIONS, dtype=torch.float32)
        if not root.is_terminal:
            for idx, child in root.children.items():
                counts[idx] = child.visit_count
        results.append(counts)
    return results, roots


def choose_action(counts: torch.Tensor, temperature: float = 0.0,
                  rng: np.random.Generator | None = None):
    """Pick an action from visit counts. tau=0 -> argmax; tau>0 -> sample."""
    if counts.sum().item() == 0:
        return None
    if temperature <= 1e-9:
        idx = counts.argmax().item()
    else:
        scaled = counts.float().pow(1.0 / temperature)
        total = scaled.sum().item()
        if total <= 0:
            idx = counts.argmax().item()
        else:
            probs = scaled / total
            idx = torch.multinomial(probs, 1).item()
    return index_to_action(idx)


class MCTS:
    """Single-tree MCTS wrapper for arena / interactive play."""

    def __init__(self, cfg: MCTSConfig, net):
        self.cfg = cfg
        self.net = net
        self.root: _Node | None = None
        self.rng = np.random.default_rng()

    def search(self, state, add_noise: bool = True) -> torch.Tensor:
        counts, roots = batched_mcts_search(
            [state], self.cfg, self.net,
            add_noise=add_noise, roots=[self.root], rng=self.rng,
        )
        self.root = roots[0]
        return counts[0]

    def choose_action(self, counts: torch.Tensor, temperature: float = 0.0):
        return choose_action(counts, temperature, rng=self.rng)

    def update_root(self, action) -> None:
        """After making a move, reuse the child subtree."""
        if self.root is None:
            return
        idx = action_to_index(action)
        if idx in self.root.children:
            self.root = self.root.children[idx]
            self.root.parent = None
        else:
            self.root = None
