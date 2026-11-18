from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class BrokerAccount:
    account_id: str
    broker: str
    mode: str = "PAPER"

class BrokerAdapter(ABC):
    account: BrokerAccount

    @abstractmethod
    async def get_balance(self) -> dict[str, float]: ...

    @abstractmethod
    async def get_positions(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def place_order(self, symbol: str, side: str, quantity: float, order_type: str = "MARKET", **kwargs) -> dict[str, Any]: ...

    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]: ...
