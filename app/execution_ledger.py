from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass
class ExecutionLedger:
    """Tracks cumulative broker execution per order and returns only new fill delta."""

    _executed: dict[str, float]

    def __init__(self):
        self._executed = {}

    def delta(self, order_id: str, cumulative_executed: float) -> float:
        if cumulative_executed < 0:
            raise ValueError("cumulative_executed cannot be negative")
        previous = self._executed.get(order_id, 0.0)
        if cumulative_executed < previous:
            raise ValueError("broker execution quantity moved backwards")
        delta = cumulative_executed - previous
        self._executed[order_id] = cumulative_executed
        return delta

    def clear(self, order_id: str) -> None:
        self._executed.pop(order_id, None)
