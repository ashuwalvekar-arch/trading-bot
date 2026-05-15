"""
CCXT-based exchange connector supporting Binance, Bybit, and any CCXT exchange.
Provides: OHLCV fetching, balance, order placement, rate-limit handling.
"""
from __future__ import annotations
import asyncio
from typing import Dict, List, Optional, Any
import ccxt.async_support as ccxt
import pandas as pd
from loguru import logger
from config import settings


EXCHANGE_CONFIGS: Dict[str, Dict] = {
    "binance": {
        "class": ccxt.binance,
        "options": {"defaultType": "spot"},
    },
    "bybit": {
        "class": ccxt.bybit,
        "options": {"defaultType": "linear"},
    },
}


class ExchangeConnector:
    def __init__(self, exchange_id: str = settings.active_exchange):
        self.exchange_id = exchange_id
        cfg = EXCHANGE_CONFIGS.get(exchange_id)
        if cfg is None:
            raise ValueError(f"Unsupported exchange: {exchange_id}")

        api_key = getattr(settings, f"{exchange_id}_api_key", "")
        secret = getattr(settings, f"{exchange_id}_secret", "")

        self._exchange: ccxt.Exchange = cfg["class"]({
            "apiKey": api_key,
            "secret": secret,
            "enableRateLimit": True,
            "options": cfg.get("options", {}),
        })

        if settings.use_testnet:
            self._exchange.set_sandbox_mode(True)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def close(self) -> None:
        await self._exchange.close()

    # ── OHLCV ─────────────────────────────────────────────────────────────────

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 500
    ) -> pd.DataFrame:
        try:
            raw = await self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df.set_index("timestamp", inplace=True)
            return df
        except ccxt.NetworkError as e:
            logger.warning(f"Network error fetching OHLCV {symbol}: {e}")
            await asyncio.sleep(5)
            return pd.DataFrame()
        except ccxt.BaseError as e:
            logger.error(f"Exchange error fetching OHLCV {symbol}: {e}")
            return pd.DataFrame()

    async def fetch_multi_timeframe(
        self, symbol: str, timeframes: List[str], limit: int = 300
    ) -> Dict[str, pd.DataFrame]:
        results = {}
        for tf in timeframes:
            df = await self.fetch_ohlcv(symbol, tf, limit)
            if not df.empty:
                results[tf] = df
            await asyncio.sleep(0.2)   # gentle rate limit
        return results

    # ── Account ───────────────────────────────────────────────────────────────

    async def get_balance(self, currency: str = "USDT") -> float:
        try:
            bal = await self._exchange.fetch_balance()
            return float(bal.get("free", {}).get(currency, 0.0))
        except Exception as e:
            logger.error(f"Balance fetch error: {e}")
            return 0.0

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        try:
            return await self._exchange.fetch_ticker(symbol)
        except Exception as e:
            logger.error(f"Ticker fetch error {symbol}: {e}")
            return {}

    # ── Orders ────────────────────────────────────────────────────────────────

    async def place_market_order(
        self,
        symbol: str,
        side: str,          # "buy" | "sell"
        amount: float,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        try:
            order = await self._exchange.create_market_order(
                symbol, side, amount, params=params or {}
            )
            logger.info(f"Order placed: {side.upper()} {amount} {symbol} | ID: {order['id']}")
            return order
        except ccxt.InsufficientFunds:
            logger.error("Insufficient funds for order.")
            return {}
        except ccxt.BaseError as e:
            logger.error(f"Order error: {e}")
            return {}

    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        try:
            await self._exchange.set_leverage(leverage, symbol)
            return True
        except Exception as e:
            logger.warning(f"Leverage set failed ({symbol}): {e}")
            return False

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        try:
            await self._exchange.cancel_order(order_id, symbol)
            return True
        except Exception as e:
            logger.error(f"Cancel order failed: {e}")
            return False

    async def fetch_open_orders(self, symbol: str) -> List[Dict]:
        try:
            return await self._exchange.fetch_open_orders(symbol)
        except Exception as e:
            logger.error(f"Fetch open orders failed: {e}")
            return []
