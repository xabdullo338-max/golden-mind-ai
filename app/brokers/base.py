from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from ..market_data import MarketTick

@dataclass(frozen=True)
class BrokerAccount:
    account_id: str
    broker: str
    # PAPER = local simulation, TESTNET/DEMO = broker sandbox, LIVE = real money.
    mode: str = "PAPER"

    def __post_init__(self):
        mode = self.mode.upper()
        if mode not in {"PAPER", "TESTNET", "DEMO", "LIVE"}:
            raise ValueError(f"Unsupported account mode: {self.mode}")
        object.__setattr__(self, "mode", mode)

    @property
    def is_live(self) -> bool:
        return self.mode == "LIVE"

    @property
    def is_simulated(self) -> bool:
        return self.mode == "PAPER"

class BrokerAdapter(ABC):
    account: BrokerAccount

    @abstractmethod
    async def get_balance(self) -> dict[str, float]: ...

    @abstractmethod
    async def get_positions(self) -> list[dict[str, Any]]: ...

    async def get_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Return currently open orders; adapters may override when supported."""
        return []

    async def get_market_tick(self, symbol: str) -> MarketTick | None:
        """Return the latest market tick; adapters may override when supported."""
        return None

    async def get_trade_history(self, symbol: str, limit: int = 1000) -> list[dict[str, Any]]:
        """Return recent account trades; adapters may override when supported."""
        return []

    async def get_order_by_client_id(self, symbol: str, client_order_id: str) -> dict[str, Any] | None:
        """Return broker truth for an order identified by client order ID."""
        return None

    async def get_account_trades(self) -> list[dict[str, Any]] | None:
        """Return recent account-level executions for reconciliation, or None if unsupported."""
        return None

    async def hydrate_positions(self, position_engine: Any, account_id: str,
                                positions: list[dict[str, Any]]) -> bool:
        """Optionally hydrate positions directly from broker-authoritative state.

        Adapters that cannot reconstruct positions from trade history may override
        this method. Returning False preserves the fail-closed recovery behavior.
        """
        return False

    @abstractmethod
    async def place_order(self, symbol: str, side: str, quantity: float,
                          order_type: str = "MARKET", **kwargs) -> dict[str, Any]: ...

    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]: ...
