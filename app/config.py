from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    trading_mode: str = "PAPER"
    # Explicit server-side feature flag. LIVE stays OFF unless deliberately enabled.
    live_trading_enabled: bool = False
    # Independent hard ceilings for LIVE, tighter than normal risk settings.
    live_max_order_notional_usdt: float = Field(default=20.0, gt=0, le=1000)
    live_max_daily_loss_pct: float = Field(default=1.0, gt=0, le=5.0)

    initial_balance_usdt: float = Field(default=300.0, gt=0)
    max_risk_per_trade_pct: float = Field(default=0.25, gt=0, le=2.0)
    max_daily_loss_pct: float = Field(default=3.0, gt=0, le=10.0)
    max_open_positions: int = Field(default=3, ge=1, le=20)
    max_total_exposure_pct: float = Field(default=100.0, gt=0, le=1000)
    max_symbol_exposure_pct: float = Field(default=100.0, gt=0, le=1000)
    max_consecutive_losses: int = Field(default=0, ge=0, le=100)

    allowed_symbols: str = "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT"

    scalping_enabled: bool = False
    scalping_target_trades_per_hour: int = Field(default=100, ge=1, le=1000)
    scalping_max_trades_per_hour: int = Field(default=100, ge=1, le=1000)
    scalping_cooldown_seconds: float = Field(default=0.5, ge=0, le=60)
    scalping_max_spread_pct: float = Field(default=0.08, gt=0, le=5)
    scalping_min_move_pct: float = Field(default=0.03, gt=0, le=10)
    max_market_data_age_seconds: float = Field(default=2.0, gt=0, le=60)
    risk_cooldown_seconds: float = Field(default=0.0, ge=0, le=60)

    # Safe runtime bootstrap. LIVE is never enabled by configuration alone.
    auto_register_accounts: bool = True
    binance_account_id: str = "BINANCE-01"
    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_base_url: str = "https://testnet.binance.vision"

    @property
    def symbols(self) -> set[str]:
        return {s.strip().upper() for s in self.allowed_symbols.split(",") if s.strip()}
