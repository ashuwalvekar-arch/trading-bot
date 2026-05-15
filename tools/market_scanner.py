"""
Market Scanner — checks all configured pairs and returns ranked signals.
"""
from __future__ import annotations
import asyncio
from typing import Dict, List
from dataclasses import dataclass
from loguru import logger

from exchange.connector import ExchangeConnector
from indicators.calculator import calculate, IndicatorResult
from config import settings


@dataclass
class ScanResult:
    symbol: str
    signal: str
    confidence: float
    trend: str
    rsi: float
    primary_timeframe: str


async def scan_market(exchange: ExchangeConnector) -> List[ScanResult]:
    results: List[ScanResult] = []
    primary_tf = settings.timeframe_list[-2] if len(settings.timeframe_list) >= 2 else "1h"

    for symbol in settings.pair_list:
        try:
            df = await exchange.fetch_ohlcv(symbol, primary_tf, limit=300)
            if df.empty:
                continue
            ind = calculate(df, symbol, primary_tf)
            results.append(ScanResult(
                symbol=symbol,
                signal=ind.signal,
                confidence=ind.signal_strength,
                trend=ind.trend,
                rsi=ind.rsi,
                primary_timeframe=primary_tf,
            ))
        except Exception as e:
            logger.error(f"Scan error {symbol}: {e}")

    # Sort by confidence descending
    results.sort(key=lambda r: r.confidence, reverse=True)
    return results
