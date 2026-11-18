from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass
class ExecutionLedger:
    """Tracks cumulative broker execution per order and returns only new fill delta."""

    _executed: dict[tuple[str, str, str], float]

    def __init__(self):
        self._executed = {}

    def delta(self, order_id: str, cumulative_executed: float,
              account_id: str | None = None, broker: str | None = None) -> float:
        if cumulative_executed < 0:
            raise ValueError("cumulative_executed cannot be negative")
        key = (broker.upper(), account_id, order_id) if account_id is not None and broker is not None else ("", "", order_id)
        previous = self._executed.get(key, 0.0)
        if cumulative_executed < previous:
            raise ValueError("broker execution quantity moved backwards")
        delta = cumulative_executed - previous
        self._executed[key] = cumulative_executed
        return delta

    def clear(self, order_id: str, account_id: str | None = None,
              broker: str | None = None) -> None:
        key = (broker.upper(), account_id, order_id) if account_id is not None and broker is not None else ("", "", order_id)
        self._executed.pop(key, None)
