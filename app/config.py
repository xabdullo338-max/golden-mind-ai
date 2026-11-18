from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    trading_mode: str = "PAPER"
    initial_balance_usdt: float = Field(default=300.0, gt=0)
    max_risk_per_trade_pct: float = Field(default=0.25, gt=0, le=2.0)
    max_daily_loss_pct: float = Field(default=3.0, gt=0, le=10.0)
    max_open_positions: int = Field(default=3, ge=1, le=20)
    allowed_symbols: str = "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT"
    scalping_enabled: bool = False
    scalping_target_trades_per_hour: int = Field(default=100, ge=1, le=1000)
    scalping_max_trades_per_hour: int = Field(default=100, ge=1, le=1000)
    scalping_cooldown_seconds: float = Field(default=0.5, ge=0, le=60)
    scalping_max_spread_pct: float = Field(default=0.08, gt=0, le=5)
    scalping_min_move_pct: float = Field(default=0.03, gt=0, le=10)

    @property
    def symbols(self) -> set[str]:
        return {s.strip().upper() for s in self.allowed_symbols.split(",") if s.strip()}
