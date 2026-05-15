"""
Central configuration management using pydantic-settings.
All settings loaded from environment variables / .env file.
"""
from __future__ import annotations
from functools import lru_cache
from typing import List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Exchange ──────────────────────────────────────────────────────────────
    active_exchange: str = "binance"
    binance_api_key: str = ""
    binance_secret: str = ""
    bybit_api_key: str = ""
    bybit_secret: str = ""
    use_testnet: bool = True

    # ── Trading pairs ─────────────────────────────────────────────────────────
    trading_pairs: str = "BTC/USDT,ETH/USDT"
    timeframes: str = "5m,15m,1h,4h"

    @property
    def pair_list(self) -> List[str]:
        return [p.strip() for p in self.trading_pairs.split(",")]

    @property
    def timeframe_list(self) -> List[str]:
        return [t.strip() for t in self.timeframes.split(",")]

    # ── Risk management ───────────────────────────────────────────────────────
    risk_percent: float = 1.0          # % of balance per trade
    max_daily_loss_percent: float = 5.0
    leverage: int = 1
    trade_cooldown_seconds: int = 300  # 5 min between trades per pair
    max_open_trades: int = 5

    # ── AI providers ──────────────────────────────────────────────────────────
    openai_api_key: str = ""
    groq_api_key: str = ""
    gemini_api_key: str = ""
    deepseek_api_key: str = ""
    primary_ai_provider: str = "openai"  # openai | groq | gemini | deepseek
    ai_model: str = "gpt-4o"
    enable_ai_reasoning: bool = True

    # ── Telegram ──────────────────────────────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./trading_bot.db"

    # ── Dashboard ─────────────────────────────────────────────────────────────
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8000
    secret_key: str = "change_me"

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_file: str = "logs/trading_bot.log"

    # ── Strategy thresholds ───────────────────────────────────────────────────
    rsi_buy_threshold: float = 55.0
    rsi_sell_threshold: float = 45.0
    min_confidence: float = 65.0       # minimum AI confidence % to trade
    min_volume_multiplier: float = 1.5  # volume spike detection


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
