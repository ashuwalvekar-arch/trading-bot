"""
Whale Tracker — monitors large on-chain transactions and funding rates.
Uses public APIs (no auth required for basic data).
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import List, Optional
import httpx
from loguru import logger


@dataclass
class FundingRate:
    symbol: str
    rate: float        # annualised %
    next_funding: str
    sentiment: str     # LONG_HEAVY | SHORT_HEAVY | NEUTRAL


async def get_funding_rates(symbols: List[str]) -> List[FundingRate]:
    """Fetch perpetual funding rates from Binance public API."""
    results = []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://fapi.binance.com/fapi/v1/premiumIndex")
            if resp.status_code != 200:
                return results
            data = resp.json()
            symbol_map = {d["symbol"]: d for d in data}

            for sym in symbols:
                clean = sym.replace("/", "")
                if clean not in symbol_map:
                    continue
                item = symbol_map[clean]
                rate = float(item.get("lastFundingRate", 0)) * 100 * 3 * 365  # annualised
                sentiment = "LONG_HEAVY" if rate > 50 else ("SHORT_HEAVY" if rate < -50 else "NEUTRAL")
                results.append(FundingRate(
                    symbol=sym,
                    rate=round(rate, 4),
                    next_funding=item.get("nextFundingTime", ""),
                    sentiment=sentiment,
                ))
    except Exception as e:
        logger.warning(f"Funding rate fetch failed: {e}")
    return results


async def get_large_transactions(symbol: str, threshold_usd: float = 1_000_000) -> List[dict]:
    """
    Placeholder for whale transaction monitoring.
    In production: connect to Whale Alert API, Glassnode, or Nansen.
    """
    logger.debug(f"Whale tracker: monitoring {symbol} (threshold=${threshold_usd:,.0f})")
    return []  # Implement with paid API in production
