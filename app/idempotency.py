from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

@dataclass(frozen=True)
class IdempotencyDecision:
    allowed: bool
    reason: str

class OrderIdempotencyGuard:
    """Prevents duplicate client order submissions inside a bounded window."""

    def __init__(self, ttl_seconds: float = 3600.0):
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.ttl_seconds = ttl_seconds
        self._seen: dict[str, float] = {}

    def check_and_mark(self, client_order_id: str) -> IdempotencyDecision:
        if not client_order_id.strip():
            return IdempotencyDecision(False, "client_order_id is required")
        self._prune()
        if client_order_id in self._seen:
            return IdempotencyDecision(False, "duplicate client order id")
        self._seen[client_order_id] = monotonic()
        return IdempotencyDecision(True, "allowed")

    def forget(self, client_order_id: str) -> None:
        self._seen.pop(client_order_id, None)

    def _prune(self) -> None:
        cutoff = monotonic() - self.ttl_seconds
        for key, created in list(self._seen.items()):
            if created < cutoff:
                del self._seen[key]
