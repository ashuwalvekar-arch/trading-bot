"""
Async multi-timeframe trend helper.
Uses the project-wide async ExchangeConnector instead of raw synchronous ccxt.
"""
from __future__ import annotations

import pandas as pd


def _ema(series: pd.Series, span: int) -> float:
    return series.ewm(span=span).mean().iloc[-1]


def get_trend_from_df(df: pd.DataFrame) -> str:
    """Return 'BUY' or 'SELL' based on price vs EMA-20."""
    ema20 = _ema(df["close"], 20)
    price = df["close"].iloc[-1]
    return "BUY" if price > ema20 else "SELL"


async def multi_timeframe_signal(symbol: str, exchange) -> str:
    """
    Fetch 5m, 15m, 1h data via the async ExchangeConnector and return
    a consensus signal ('BUY', 'SELL', or 'WAIT').

    Parameters
    ----------
    symbol   : e.g. 'BTC/USDT'
    exchange : an already-connected ExchangeConnector instance
    """
    signals: list[str] = []

    for tf in ("5m", "15m", "1h"):
        df = await exchange.fetch_ohlcv(symbol, tf, limit=50)
        if df is None or df.empty:
            return "WAIT"
        signals.append(get_trend_from_df(df))

    if len(set(signals)) == 1:
        return signals[0]

    return "WAIT"
