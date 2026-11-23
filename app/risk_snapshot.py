from __future__ import annotations

from dataclasses import dataclass

from .portfolio import AccountSnapshot
from .portfolio_state import BrokerState
from .daily_risk_state import DailyRiskStateStore
from .position_engine import PositionEngine


@dataclass(frozen=True)
class RiskSnapshotProvider:
    """Builds an AccountSnapshot from broker-authoritative reconciled state.

    Prices are supplied by the market-data layer; this class never invents
    prices. Missing prices therefore make the valuation incomplete.
    """

    daily_start_equity: dict[str, float] | None = None
    daily_risk_store: DailyRiskStateStore | None = None
    positions: PositionEngine | None = None

    def exposures(
        self,
        state: BrokerState,
        *,
        prices: dict[str, float],
    ) -> tuple[float, dict[str, float]]:
        if not state.confirmed:
            return 0.0, {}
        total = 0.0
        by_symbol: dict[str, float] = {}
        for asset, quantity in state.positions.items():
            asset = str(asset).upper()
            quantity = float(quantity)
            if quantity <= 0:
                continue
            price = prices.get(asset) or prices.get(f"{asset}USDT")
            if price is None or price <= 0:
                raise ValueError(f"price unavailable for {asset}")
            notional = quantity * price
            total += notional
            by_symbol[f"{asset}USDT"] = notional
        return total, by_symbol

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

        for asset, quantity in state.positions.items():
            quantity = float(quantity)
            asset = str(asset).upper()
            if quantity <= 0 or asset in state.balances:
                continue
            price = prices.get(asset) or prices.get(f"{asset}USDT")
            if price is None or price <= 0:
                return None
            equity += quantity * price

        if self.daily_risk_store is not None:
            from .portfolio import utc_date
            daily_state = self.daily_risk_store.establish_if_missing(
                state.account_id, utc_date(), equity
            )
            start = daily_state.start_equity
        else:
            start = (self.daily_start_equity or {}).get(state.account_id)
            # Standalone snapshot providers used by PAPER/TESTNET callers may
            # not have a durable daily-risk store. In that case, establish the
            # current reconciled equity as the initial baseline. The production
            # API supplies DailyRiskStateStore, so LIVE risk checks keep a
            # durable day-start equity instead of resetting it on each call.
            if start is None:
                start = equity

        if start <= 0:
            return None

        open_positions = sum(1 for q in state.positions.values() if float(q) > 0)
        realized_pnl = 0.0
        unrealized_pnl = equity - cash

        if self.positions is not None:
            local_positions = self.positions.snapshot(state.account_id)
            realized_pnl = sum(p.realized_pnl for p in local_positions)
            unrealized_pnl = 0.0
            for position in local_positions:
                symbol = position.symbol.upper()
                mark = prices.get(symbol)
                if mark is None and symbol.endswith("USDT"):
                    mark = prices.get(symbol.removesuffix("USDT"))
                if mark is None or mark <= 0:
                    return None
                unrealized_pnl += position.unrealized_pnl(mark)

        return AccountSnapshot(
            account_id=state.account_id,
            equity=equity,
            cash=cash,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            daily_start_equity=start,
            open_positions=open_positions,
        )
