"""
Technical indicator calculator — pure pandas/numpy, no TA-Lib dependency.
Supports: RSI, EMA, MACD, ATR, Volume analysis, Trend detection,
          Support/Resistance, Candlestick patterns.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from loguru import logger


@dataclass
class IndicatorResult:
    symbol: str
    timeframe: str
    rsi: float = 0.0
    ema50: float = 0.0
    ema200: float = 0.0
    macd: float = 0.0
    macd_signal: float = 0.0
    macd_hist: float = 0.0
    atr: float = 0.0
    volume: float = 0.0
    volume_sma: float = 0.0
    volume_spike: bool = False
    trend: str = "SIDEWAYS"           # BULLISH | BEARISH | SIDEWAYS
    trend_strength: float = 0.0       # 0-100
    support: float = 0.0
    resistance: float = 0.0
    patterns: List[str] = field(default_factory=list)
    current_price: float = 0.0
    signal: str = "WAIT"              # BUY | SELL | WAIT
    signal_strength: float = 0.0     # 0-100


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _macd(close: pd.Series, fast=12, slow=26, signal=9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _support_resistance(df: pd.DataFrame, lookback: int = 50) -> Tuple[float, float]:
    window = df.tail(lookback)
    support = float(window["low"].min())
    resistance = float(window["high"].max())
    return support, resistance


# ── Candlestick Pattern Detection ────────────────────────────────────────────

def _detect_patterns(df: pd.DataFrame) -> List[str]:
    patterns = []
    if len(df) < 3:
        return patterns

    o, h, l, c = (
        df["open"].values,
        df["high"].values,
        df["low"].values,
        df["close"].values,
    )
    body_size = abs(c - o)
    candle_range = h - l

    # Last 3 candles (indices -3, -2, -1)
    i = -1

    # Doji
    if candle_range[i] > 0 and body_size[i] / candle_range[i] < 0.1:
        patterns.append("DOJI")

    # Hammer (bullish reversal)
    if (
        body_size[i] > 0
        and (l[i] - min(o[i], c[i])) >= 2 * body_size[i]
        and (h[i] - max(o[i], c[i])) < body_size[i]
    ):
        patterns.append("HAMMER")

    # Shooting Star (bearish reversal)
    if (
        body_size[i] > 0
        and (h[i] - max(o[i], c[i])) >= 2 * body_size[i]
        and (min(o[i], c[i]) - l[i]) < body_size[i]
    ):
        patterns.append("SHOOTING_STAR")

    # Bullish Engulfing
    if (
        c[-2] < o[-2]                     # prev bearish
        and c[i] > o[i]                   # curr bullish
        and o[i] < c[-2]                  # opens below prev close
        and c[i] > o[-2]                  # closes above prev open
    ):
        patterns.append("BULLISH_ENGULFING")

    # Bearish Engulfing
    if (
        c[-2] > o[-2]
        and c[i] < o[i]
        and o[i] > c[-2]
        and c[i] < o[-2]
    ):
        patterns.append("BEARISH_ENGULFING")

    # Morning Star (3-candle bullish)
    if len(df) >= 3:
        if (
            c[-3] < o[-3]                 # first: bearish
            and body_size[-2] < body_size[-3] * 0.3  # middle: small body
            and c[i] > o[i]               # third: bullish
            and c[i] > (o[-3] + c[-3]) / 2  # closes above midpoint of first
        ):
            patterns.append("MORNING_STAR")

        # Evening Star (3-candle bearish)
        if (
            c[-3] > o[-3]
            and body_size[-2] < body_size[-3] * 0.3
            and c[i] < o[i]
            and c[i] < (o[-3] + c[-3]) / 2
        ):
            patterns.append("EVENING_STAR")

    return patterns


def calculate(df: pd.DataFrame, symbol: str, timeframe: str,
              volume_multiplier: float = 1.5) -> IndicatorResult:
    """
    Main entry point.  `df` must have columns: open, high, low, close, volume
    indexed by datetime (oldest first).
    """
    result = IndicatorResult(symbol=symbol, timeframe=timeframe)

    if len(df) < 50:
        logger.warning(f"Insufficient candles for {symbol} {timeframe}: {len(df)}")
        return result

    close = df["close"]
    result.current_price = float(close.iloc[-1])

    # RSI
    rsi_series = _rsi(close)
    result.rsi = round(float(rsi_series.iloc[-1]), 2)

    # EMA
    result.ema50 = round(float(_ema(close, min(50, len(close))).iloc[-1]), 6)
    result.ema200 = round(float(_ema(close, min(200, len(close))).iloc[-1]), 6)

    # MACD
    macd_line, sig_line, histogram = _macd(close)
    result.macd = round(float(macd_line.iloc[-1]), 6)
    result.macd_signal = round(float(sig_line.iloc[-1]), 6)
    result.macd_hist = round(float(histogram.iloc[-1]), 6)

    # ATR
    result.atr = round(float(_atr(df).iloc[-1]), 6)

    # Volume
    vol = df["volume"]
    result.volume = float(vol.iloc[-1])
    result.volume_sma = float(vol.rolling(20).mean().iloc[-1])
    result.volume_spike = result.volume > result.volume_sma * volume_multiplier

    # Trend
    if result.ema50 > result.ema200:
        result.trend = "BULLISH"
        ema_gap_pct = (result.ema50 - result.ema200) / result.ema200 * 100
        result.trend_strength = min(100, ema_gap_pct * 10)
    elif result.ema50 < result.ema200:
        result.trend = "BEARISH"
        ema_gap_pct = (result.ema200 - result.ema50) / result.ema200 * 100
        result.trend_strength = min(100, ema_gap_pct * 10)
    else:
        result.trend = "SIDEWAYS"
        result.trend_strength = 0.0

    # Support / Resistance
    result.support, result.resistance = _support_resistance(df)

    # Candlestick patterns
    result.patterns = _detect_patterns(df)

    # Raw signal logic
    result.signal, result.signal_strength = _generate_signal(result)

    return result


def _generate_signal(r: IndicatorResult) -> Tuple[str, float]:
    """Rule-based signal engine (pre-AI)."""
    buy_score = 0.0
    sell_score = 0.0

    # EMA cross
    if r.ema50 > r.ema200:
        buy_score += 25
    else:
        sell_score += 25

    # RSI
    if r.rsi > 55:
        buy_score += 20
    elif r.rsi < 45:
        sell_score += 20

    # MACD
    if r.macd > r.macd_signal and r.macd_hist > 0:
        buy_score += 25
    elif r.macd < r.macd_signal and r.macd_hist < 0:
        sell_score += 25

    # Volume spike
    if r.volume_spike:
        if r.trend == "BULLISH":
            buy_score += 15
        elif r.trend == "BEARISH":
            sell_score += 15

    # Candlestick patterns
    bullish_patterns = {"HAMMER", "BULLISH_ENGULFING", "MORNING_STAR"}
    bearish_patterns = {"SHOOTING_STAR", "BEARISH_ENGULFING", "EVENING_STAR"}
    for p in r.patterns:
        if p in bullish_patterns:
            buy_score += 10
        elif p in bearish_patterns:
            sell_score += 10

    total = max(buy_score + sell_score, 1)
    if buy_score > sell_score and buy_score >= 60:
        return "BUY", round(buy_score / total * 100, 1)
    elif sell_score > buy_score and sell_score >= 60:
        return "SELL", round(sell_score / total * 100, 1)
    return "WAIT", 0.0
