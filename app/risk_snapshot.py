from __future__ import annotations

from dataclasses import dataclass

from .portfolio import AccountSnapshot
from .portfolio_state import BrokerState


@dataclass(frozen=True)
class RiskSnapshotProvider:
    """Builds an AccountSnapshot from broker-authoritative reconciled state.

    Prices are supplied by the market-data layer; this class never invents
    prices. Missing prices therefore make the valuation incomplete.
    """

    daily_start_equity: dict[str, float] | None = None

    def build(
        self,
        state: BrokerState,
        *,
        prices: dict[str, float] | None = None,
    ) -> AccountSnapshot | None:
        if not state.confirmed:
            return None

        prices = {str(k).upper(): float(v) for k, v in (prices or {}).items()}
        cash = 0.0
        equity = 0.0
        for asset, quantity in state.balances.items():
            asset = asset.upper()
            quantity = float(quantity)
            if quantity <= 0:
                continue
            if asset in {"USDT", "USDC", "BUSD"}:
                cash += quantity
                equity += quantity
            else:
                price = prices.get(asset) or prices.get(f"{asset}USDT")
                if price is None or price <= 0:
                    return None
                equity += quantity * price

        for position in state.positions.values():
            quantity = float(position)
            if quantity <= 0:
                continue
            asset = next(
                (a for a, q in state.positions.items() if q == position),
                None,
            )
            if asset is None or asset.upper() in state.balances:
                continue
            price = prices.get(asset.upper()) or prices.get(f"{asset.upper()}USDT")
            if price is None or price <= 0:
                return None
            equity += quantity * price

        start = (self.daily_start_equity or {}).get(state.account_id, equity)
        if start <= 0:
            return None

        open_positions = sum(1 for q in state.positions.values() if float(q) > 0)
        return AccountSnapshot(
            account_id=state.account_id,
            equity=equity,
            cash=cash,
            realized_pnl=0.0,
            unrealized_pnl=equity - cash,
            daily_start_equity=start,
            open_positions=open_positions,
        )
