import os

class SecretMissingError(RuntimeError):
    pass

def required_secret(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SecretMissingError(f"Required secret is not configured: {name}")
    return value

def live_trading_enabled() -> bool:
    return os.getenv("GMAI_LIVE_TRADING", "false").lower() in {"1", "true", "yes"}

def assert_live_enabled() -> None:
    if not live_trading_enabled():
        raise RuntimeError("Live trading is disabled. Set GMAI_LIVE_TRADING=true only after validation.")
