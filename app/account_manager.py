from dataclasses import dataclass
from typing import Any
from .brokers.base import BrokerAdapter

@dataclass
class ManagedAccount:
    adapter: BrokerAdapter
    enabled: bool = True

class AccountManager:
    def __init__(self):
        self.accounts: dict[str, ManagedAccount] = {}

    def register(self, adapter: BrokerAdapter):
        if adapter.account.account_id in self.accounts:
            raise ValueError("Account ID already registered")
        self.accounts[adapter.account.account_id] = ManagedAccount(adapter)

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

    async def broadcast_order(self, symbol: str, side: str, quantity: float) -> list[dict[str, Any]]:
        results = []
        for managed in self.accounts.values():
            if not managed.enabled:
                continue
            results.append(await managed.adapter.place_order(symbol, side, quantity))
        return results
