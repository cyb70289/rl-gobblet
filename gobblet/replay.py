"""FIFO replay buffer with persist/load."""
from __future__ import annotations

from collections import deque
from pathlib import Path

import numpy as np
import torch


class ReplayBuffer:
    def __init__(self, max_size: int = 50_000):
        self.max_size = max_size
        self.samples: deque = deque(maxlen=max_size)

    def __len__(self) -> int:
        return len(self.samples)

    def add(self, sample) -> None:
        """sample = (state_tensor(21,3,3), policy_tensor(99,), value: float)."""
        self.samples.append(sample)

    def add_many(self, samples) -> None:
        for s in samples:
            self.samples.append(s)

    def sample(self, batch_size: int):
        n = len(self.samples)
        if n == 0:
            raise ValueError("buffer is empty")
        idxs = np.random.randint(0, n, size=batch_size)
        states = torch.stack([self.samples[i][0] for i in idxs])
        policies = torch.stack([self.samples[i][1] for i in idxs])
        values = torch.tensor([self.samples[i][2] for i in idxs], dtype=torch.float32)
        return states, policies, values

    def save(self, path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        n = len(self.samples)
        if n == 0:
            torch.save({"states": torch.empty(0), "policies": torch.empty(0),
                        "values": torch.empty(0), "max_size": self.max_size}, path)
            return
        states = torch.stack([s[0] for s in self.samples])
        policies = torch.stack([s[1] for s in self.samples])
        values = torch.tensor([s[2] for s in self.samples], dtype=torch.float32)
        torch.save({"states": states, "policies": policies,
                    "values": values, "max_size": self.max_size}, path)

    @classmethod
    def load(cls, path) -> "ReplayBuffer":
        data = torch.load(path, map_location="cpu", weights_only=False)
        buf = cls(max_size=data["max_size"])
        for i in range(len(data["states"])):
            buf.add((data["states"][i], data["policies"][i], data["values"][i].item()))
        return buf
