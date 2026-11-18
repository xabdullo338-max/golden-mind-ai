from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    trading_mode: str = "PAPER"
    initial_balance_usdt: float = Field(default=300.0, gt=0)
    max_risk_per_trade_pct: float = Field(default=1.0, gt=0, le=2.0)
    max_daily_loss_pct: float = Field(default=3.0, gt=0, le=10.0)
    max_open_positions: int = Field(default=3, ge=1, le=20)
    allowed_symbols: str = "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT"

    @property
    def symbols(self) -> set[str]:
        return {s.strip().upper() for s in self.allowed_symbols.split(",") if s.strip()}

settings = Settings()
