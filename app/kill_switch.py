from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .account_manager import AccountManager
from .event_bus import EventBus, TradingEvent


@dataclass
class KillSwitch:
    global_enabled: bool = False
    account_disabled: set[str] = field(default_factory=set)

    def stop_all(self) -> None:
        self.global_enabled = True

    def resume(self) -> None:
        self.global_enabled = False

    def disable_account(self, account_id: str) -> None:
        self.account_disabled.add(account_id)

    def enable_account(self, account_id: str) -> None:
        self.account_disabled.discard(account_id)

    def assert_allowed(self, account_id: str) -> None:
        if self.global_enabled:
            raise RuntimeError("Global kill switch is active")
        if account_id in self.account_disabled:
            raise RuntimeError(f"Kill switch is active for account {account_id}")


class EmergencySafetySystem:
    """Emergency stop, open-order cancellation and broker-reject circuit breaker."""

    def __init__(
        self,
        accounts: AccountManager,
        kill_switch: KillSwitch,
        event_bus: EventBus | None = None,
        rejection_threshold: int = 3,
        rejection_window_seconds: float = 60.0,
    ) -> None:
        self.accounts = accounts
        self.kill_switch = kill_switch
        self.event_bus = event_bus
        self.rejection_threshold = max(1, int(rejection_threshold))
        self.rejection_window_seconds = max(1.0, float(rejection_window_seconds))
        self._rejects: dict[str, deque[float]] = defaultdict(deque)

    async def _audit(
        self,
        event_type: str,
        *,
        account_id: str | None = None,
        reason: str = "",
        payload: dict[str, Any] | None = None,
    ) -> None:
        if self.event_bus is None:
            return
        await self.event_bus.publish(
            TradingEvent.create(
                event_type,
                account_id,
                reason=reason,
                payload=payload or {},
            )
        )

    async def cancel_all_open_orders(self, account_id: str) -> list[dict[str, Any]]:
        managed = self.accounts.accounts.get(account_id)
        if managed is None:
            return []

        try:
            open_orders = await managed.adapter.get_open_orders()
        except Exception as exc:
            await self._audit(
                "EMERGENCY_CANCEL_FAILED",
                account_id=account_id,
                reason=str(exc),
            )
            return [{"status": "ERROR", "error": str(exc)}]

        results: list[dict[str, Any]] = []
        for order in open_orders:
            symbol = str(order.get("symbol", ""))
            order_id = order.get("orderId") or order.get("order_id")
            if not symbol or order_id is None:
                continue
            try:
                results.append(
                    await managed.adapter.cancel_order(symbol, str(order_id))
                )
            except Exception as exc:
                results.append({
                    "status": "ERROR",
                    "symbol": symbol,
                    "order_id": str(order_id),
                    "error": str(exc),
                })
                await self._audit(
                    "EMERGENCY_CANCEL_FAILED",
                    account_id=account_id,
                    reason=str(exc),
                    payload={"symbol": symbol, "order_id": str(order_id)},
                )

        await self._audit(
            "EMERGENCY_CANCEL_ALL",
            account_id=account_id,
            payload={"attempted": len(open_orders), "results": len(results)},
        )
        return results

    async def freeze_account(self, account_id: str, reason: str) -> None:
        self.kill_switch.disable_account(account_id)
        await self.cancel_all_open_orders(account_id)
        await self._audit(
            "EMERGENCY_ACCOUNT_FROZEN",
            account_id=account_id,
            reason=reason,
        )

    async def freeze_global(self, reason: str) -> None:
        self.kill_switch.stop_all()
        account_ids = list(self.accounts.accounts)
        for account_id in account_ids:
            await self.cancel_all_open_orders(account_id)
        await self._audit(
            "EMERGENCY_GLOBAL_FROZEN",
            reason=reason,
            payload={"accounts": account_ids},
        )

    async def recover_account(
        self,
        account_id: str,
        reason: str = "broker recovery confirmed",
    ) -> None:
        self.kill_switch.enable_account(account_id)
        self._rejects.pop(account_id, None)
        await self._audit(
            "EMERGENCY_ACCOUNT_RECOVERED",
            account_id=account_id,
            reason=reason,
        )

    def is_frozen(self, account_id: str) -> bool:
        return (
            self.kill_switch.global_enabled
            or account_id in self.kill_switch.account_disabled
        )

    async def record_rejection(self, account_id: str, reason: str) -> bool:
        now = datetime.now(UTC).timestamp()
        bucket = self._rejects[account_id]
        bucket.append(now)
        cutoff = now - self.rejection_window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= self.rejection_threshold:
            await self.freeze_account(
                account_id,
                f"circuit breaker: {len(bucket)} broker rejects in "
                f"{self.rejection_window_seconds:.0f}s; last={reason}",
            )
            return True

        await self._audit(
            "BROKER_ORDER_REJECTED",
            account_id=account_id,
            reason=reason,
            payload={"count": len(bucket)},
        )
        return False
