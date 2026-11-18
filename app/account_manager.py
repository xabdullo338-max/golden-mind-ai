from dataclasses import dataclass
from typing import Any
from .brokers.base import BrokerAdapter
from .order_models import OrderRequest

@dataclass
class ManagedAccount:
    adapter: BrokerAdapter
    enabled: bool = True

class AccountManager:
    def __init__(self):
        self.accounts: dict[str, ManagedAccount] = {}

    def register(self, adapter: BrokerAdapter):
        account_id = adapter.account.account_id
        if account_id in self.accounts:
            raise ValueError("Account ID already registered")
        self.accounts[account_id] = ManagedAccount(adapter)

    def enable(self, account_id: str):
        self.accounts[account_id].enabled = True

    def disable(self, account_id: str):
        self.accounts[account_id].enabled = False

    def list_accounts(self) -> list[dict[str, Any]]:
        return [
            {"account_id": m.adapter.account.account_id,
             "broker": m.adapter.account.broker,
             "mode": m.adapter.account.mode,
             "enabled": m.enabled}
            for m in self.accounts.values()
        ]

    async def broadcast_order(self, order: OrderRequest) -> list[dict[str, Any]]:
        order.validate()
        results = []
        for managed in self.accounts.values():
            if not managed.enabled:
                continue
            results.append(await managed.adapter.place_order(
                order.symbol, order.side.value, order.quantity,
                order_type=order.order_type.value,
                client_order_id=order.client_order_id,
                limit_price=order.limit_price,
                metadata=order.metadata,
            ))
        return results

    async def order_to(self, account_id: str, order: OrderRequest) -> dict[str, Any]:
        order.validate()
        managed = self.accounts[account_id]
        if not managed.enabled:
            raise RuntimeError(f"Account {account_id} is disabled")
        return await managed.adapter.place_order(
            order.symbol, order.side.value, order.quantity,
            order_type=order.order_type.value,
            client_order_id=order.client_order_id,
            limit_price=order.limit_price,
            metadata=order.metadata,
        )
