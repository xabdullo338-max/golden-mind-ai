from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

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

    @abstractmethod
    async def place_order(self, symbol: str, side: str, quantity: float,
                          order_type: str = "MARKET", **kwargs) -> dict[str, Any]: ...

    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]: ...
