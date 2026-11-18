from dataclasses import dataclass

@dataclass
class KillSwitch:
    global_enabled: bool = False
    account_disabled: set[str] = None

    def __post_init__(self):
        if self.account_disabled is None:
            self.account_disabled = set()

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