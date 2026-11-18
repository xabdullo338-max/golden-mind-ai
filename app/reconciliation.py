from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class ReconciliationResult:
    account_id: str
    ok: bool
    discrepancies: list[str]

class ReconciliationEngine:
    """Compares normalized internal and broker snapshots before further execution."""

    def compare(self, account_id: str, internal_positions: dict[str, float],
                broker_positions: list[dict[str, Any]], tolerance: float = 1e-8) -> ReconciliationResult:
        broker = {str(p["asset"]).upper(): float(p["quantity"]) for p in broker_positions}
        keys = set(internal_positions) | set(broker)
        discrepancies = []
        for asset in sorted(keys):
            internal_qty = float(internal_positions.get(asset, 0.0))
            broker_qty = float(broker.get(asset, 0.0))
            if abs(internal_qty - broker_qty) > tolerance:
                discrepancies.append(f"{asset}: internal={internal_qty}, broker={broker_qty}")
        return ReconciliationResult(account_id, not discrepancies, discrepancies)
