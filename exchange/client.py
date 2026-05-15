"""
exchange/client.py — Unified exchange client wrapping CCXT.
Supports Binance and Bybit with automatic retry + rate-limit handling.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import ccxt.async_support as ccxt
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from logs.logger import get_logger

logger = get_logger(__name__)


# ─── Factory ──────────────────────────────────────────────────────────────────

def create_exchange(name: str) -> ccxt.Exchange:
    cfg = settings.exchange
    kwargs: Dict[str, Any] = {
        "enableRateLimit": True,
        "rateLimit": 50,
        "options": {"defaultType": "future"},
    }

    if name == "binance":
        kwargs["apiKey"] = cfg.binance_api_key.get_secret_value()
        kwargs["secret"] = cfg.binance_secret.get_secret_value()
        ex = ccxt.binance(kwargs)
        if cfg.binance_testnet:
            ex.set_sandbox_mode(True)

    elif name == "bybit":
        kwargs["apiKey"] = cfg.bybit_api_key.get_secret_value()
        kwargs["secret"] = cfg.bybit_secret.get_secret_value()
        ex = ccxt.bybit(kwargs)
        if cfg.bybit_testnet:
            ex.set_sandbox_mode(True)

    else:
        raise ValueError(f"Unsupported exchange: {name}")

    return ex


# ─── Unified Client ───────────────────────────────────────────────────────────

class ExchangeClient:
    """
    Wraps a CCXT exchange instance with:
      - OHLCV fetching (returns DataFrames)
      - Balance queries
      - Order placement
      - Rate-limit retries via tenacity
    """

    def __init__(self, exchange_name: Optional[str] = None):
        self.name = exchange_name or settings.exchange.default_exchange
        self._exchange = create_exchange(self.name)
        self._initialized = False

    async def initialize(self) -> None:
        if not self._initialized:
            await self._exchange.load_markets()
            self._initialized = True
            logger.info(f"Exchange '{self.name}' initialized.")

    async def close(self) -> None:
        await self._exchange.close()

    # ── OHLCV ─────────────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "15m",
        limit: int = 300,
    ) -> pd.DataFrame:
        """Fetch OHLCV candles and return as a DataFrame."""
        raw = await self._exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        if not raw:
            raise ValueError(f"No OHLCV data returned for {symbol}/{timeframe}")

        df = pd.DataFrame(
            raw, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        df = df.astype(float)
        return df

    async def fetch_multi_timeframe(
        self,
        symbol: str,
        timeframes: Optional[List[str]] = None,
    ) -> Dict[str, pd.DataFrame]:
        """Fetch multiple timeframes concurrently."""
        tfs = timeframes or settings.trading.timeframes
        tasks = {tf: self.fetch_ohlcv(symbol, tf) for tf in tfs}
        results: Dict[str, pd.DataFrame] = {}
        for tf, coro in tasks.items():
            try:
                results[tf] = await coro
            except Exception as e:
                logger.warning(f"Failed to fetch {symbol}/{tf}: {e}")
        return results

    # ── Balances ──────────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
    async def fetch_balance(self) -> Dict[str, Any]:
        balance = await self._exchange.fetch_balance()
        return {
            "total": balance.get("total", {}),
            "free": balance.get("free", {}),
            "used": balance.get("used", {}),
        }

    async def get_usdt_balance(self) -> float:
        bal = await self.fetch_balance()
        return float(bal["free"].get("USDT", 0.0))

    # ── Ticker ────────────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
    async def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        return await self._exchange.fetch_ticker(symbol)

    async def get_current_price(self, symbol: str) -> float:
        ticker = await self.fetch_ticker(symbol)
        return float(ticker["last"])

    # ── Orders ────────────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=3))
    async def place_market_order(
        self,
        symbol: str,
        side: str,  # "buy" | "sell"
        amount: float,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        if settings.trading.paper_trading:
            price = await self.get_current_price(symbol)
            logger.info(
                f"[PAPER] {side.upper()} {amount} {symbol} @ ~{price}"
            )
            return {
                "id": f"paper_{datetime.utcnow().timestamp()}",
                "symbol": symbol,
                "side": side,
                "amount": amount,
                "price": price,
                "status": "closed",
                "paper": True,
            }

        order = await self._exchange.create_market_order(
            symbol, side, amount, params=params or {}
        )
        logger.info(f"Order placed: {order}")
        return order

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=3))
    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        if settings.trading.paper_trading:
            logger.info(f"[PAPER] LIMIT {side.upper()} {amount} {symbol} @ {price}")
            return {
                "id": f"paper_limit_{datetime.utcnow().timestamp()}",
                "symbol": symbol,
                "side": side,
                "amount": amount,
                "price": price,
                "status": "open",
                "paper": True,
            }
        return await self._exchange.create_limit_order(
            symbol, side, amount, price, params=params or {}
        )

    async def cancel_order(self, order_id: str, symbol: str) -> Dict:
        return await self._exchange.cancel_order(order_id, symbol)

    async def fetch_order(self, order_id: str, symbol: str) -> Dict:
        return await self._exchange.fetch_order(order_id, symbol)

    # ── Leverage ──────────────────────────────────────────────────────────────

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        try:
            await self._exchange.set_leverage(leverage, symbol)
            logger.info(f"Leverage set to {leverage}x for {symbol}")
        except Exception as e:
            logger.warning(f"Could not set leverage: {e}")

    # ── Funding Rate ──────────────────────────────────────────────────────────

    async def fetch_funding_rate(self, symbol: str) -> Optional[float]:
        try:
            data = await self._exchange.fetch_funding_rate(symbol)
            return float(data.get("fundingRate", 0.0))
        except Exception:
            return None


# ─── Multi-Exchange Router ────────────────────────────────────────────────────

class MultiExchangeRouter:
    """
    Manages multiple exchange clients and routes requests to the best exchange
    (best price, lowest fees, available liquidity).
    """

    def __init__(self, exchanges: Optional[List[str]] = None):
        self._clients: Dict[str, ExchangeClient] = {}
        for name in (exchanges or [settings.exchange.default_exchange]):
            self._clients[name] = ExchangeClient(name)

    async def initialize_all(self) -> None:
        for client in self._clients.values():
            await client.initialize()

    async def close_all(self) -> None:
        for client in self._clients.values():
            await client.close()

    def get(self, name: str) -> ExchangeClient:
        return self._clients[name]

    def default(self) -> ExchangeClient:
        return self._clients[settings.exchange.default_exchange]

    async def best_price(self, symbol: str, side: str) -> Tuple[str, float]:
        """Return (exchange_name, best_price) for a given side (buy/sell)."""
        prices = {}
        for name, client in self._clients.items():
            try:
                prices[name] = await client.get_current_price(symbol)
            except Exception:
                pass
        if not prices:
            raise RuntimeError("No exchange returned a price.")
        if side == "buy":
            return min(prices, key=prices.get), min(prices.values())
        return max(prices, key=prices.get), max(prices.values())
