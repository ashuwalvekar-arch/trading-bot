"""
indicators/technical.py — All technical indicator calculations using pandas-ta.
Returns structured dicts so the AI engine can consume them easily.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd
import pandas_ta as ta

from logs.logger import get_logger

logger = get_logger(__name__)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _safe(val: Any, decimals: int = 6) -> Optional[float]:
    """Return rounded float or None if NaN/None."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if np.isnan(f) else round(f, decimals)
    except (TypeError, ValueError):
        return None


# ─── Main Calculator ─────────────────────────────────────────────────────────

class TechnicalIndicators:
    """
    Calculates all indicators needed by the trading strategies.
    Accepts a DataFrame with OHLCV columns (open, high, low, close, volume).
    """

    def __init__(self, df: pd.DataFrame):
        if df is None or len(df) < 50:
            raise ValueError("Need at least 50 candles for indicator calculation.")
        self.df = df.copy()
        self._ensure_columns()

    def _ensure_columns(self) -> None:
        rename_map = {c.lower(): c.lower() for c in self.df.columns}
        self.df.columns = [c.lower() for c in self.df.columns]
        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(self.df.columns)
        if missing:
            raise ValueError(f"OHLCV columns missing: {missing}")

    # ── RSI ───────────────────────────────────────────────────────────────────

    def rsi(self, period: int = 14) -> Optional[float]:
        result = ta.rsi(self.df["close"], length=period)
        if result is None or result.empty:
            return None
        return _safe(result.iloc[-1])

    # ── EMA ───────────────────────────────────────────────────────────────────

    def ema(self, period: int) -> Optional[float]:
        result = ta.ema(self.df["close"], length=period)
        if result is None or result.empty:
            return None
        return _safe(result.iloc[-1])

    def ema_series(self, period: int) -> pd.Series:
        return ta.ema(self.df["close"], length=period)

    # ── MACD ──────────────────────────────────────────────────────────────────

    def macd(
        self, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> Dict[str, Optional[float]]:
        result = ta.macd(self.df["close"], fast=fast, slow=slow, signal=signal)
        if result is None or result.empty:
            return {"macd": None, "signal": None, "histogram": None, "crossover": None}

        macd_val = _safe(result.iloc[-1, 0])
        signal_val = _safe(result.iloc[-1, 2])
        hist = _safe(result.iloc[-1, 1])

        # Detect crossover (last 2 bars)
        if len(result) >= 2:
            prev_hist = _safe(result.iloc[-2, 1])
            crossover: Optional[str] = None
            if prev_hist is not None and hist is not None:
                if prev_hist < 0 and hist > 0:
                    crossover = "bullish"
                elif prev_hist > 0 and hist < 0:
                    crossover = "bearish"
        else:
            crossover = None

        return {
            "macd": macd_val,
            "signal": signal_val,
            "histogram": hist,
            "crossover": crossover,
        }

    # ── ATR ───────────────────────────────────────────────────────────────────

    def atr(self, period: int = 14) -> Optional[float]:
        result = ta.atr(self.df["high"], self.df["low"], self.df["close"], length=period)
        if result is None or result.empty:
            return None
        return _safe(result.iloc[-1])

    # ── Volume Analysis ───────────────────────────────────────────────────────

    def volume_analysis(self, period: int = 20) -> Dict[str, Any]:
        vol = self.df["volume"]
        avg_vol = vol.rolling(period).mean().iloc[-1]
        current_vol = vol.iloc[-1]
        ratio = current_vol / avg_vol if avg_vol > 0 else 1.0

        return {
            "current": _safe(current_vol),
            "average": _safe(avg_vol),
            "ratio": _safe(ratio, 2),
            "spike": ratio > 1.5,
            "strong_spike": ratio > 2.0,
        }

    # ── Bollinger Bands ───────────────────────────────────────────────────────

    def bollinger_bands(self, period: int = 20, std: float = 2.0) -> Dict[str, Any]:
        result = ta.bbands(self.df["close"], length=period, std=std)
        if result is None or result.empty:
            return {"upper": None, "middle": None, "lower": None, "width": None}
        row = result.iloc[-1]
        upper = _safe(row.get(f"BBU_{period}_{std}", row.iloc[2]))
        middle = _safe(row.get(f"BBM_{period}_{std}", row.iloc[1]))
        lower = _safe(row.get(f"BBL_{period}_{std}", row.iloc[0]))
        width = _safe((upper - lower) / middle * 100) if (upper and lower and middle) else None
        close = self.df["close"].iloc[-1]
        return {
            "upper": upper,
            "middle": middle,
            "lower": lower,
            "width": width,
            "squeeze": width < 2.0 if width else False,
            "price_position": (
                "above_upper" if close > upper
                else "below_lower" if close < lower
                else "inside"
            ) if upper and lower else "unknown",
        }

    # ── Trend Strength (ADX) ──────────────────────────────────────────────────

    def adx(self, period: int = 14) -> Dict[str, Any]:
        result = ta.adx(self.df["high"], self.df["low"], self.df["close"], length=period)
        if result is None or result.empty:
            return {"adx": None, "plus_di": None, "minus_di": None, "trend_strength": "unknown"}

        adx_val = _safe(result.iloc[-1, 0])
        plus_di = _safe(result.iloc[-1, 1])
        minus_di = _safe(result.iloc[-1, 2])

        strength = "weak"
        if adx_val:
            if adx_val > 50:
                strength = "very_strong"
            elif adx_val > 35:
                strength = "strong"
            elif adx_val > 25:
                strength = "moderate"

        return {
            "adx": adx_val,
            "plus_di": plus_di,
            "minus_di": minus_di,
            "trend_strength": strength,
            "trending": adx_val > 25 if adx_val else False,
        }

    # ── Support & Resistance ──────────────────────────────────────────────────

    def support_resistance(self, lookback: int = 50) -> Dict[str, Any]:
        recent = self.df.tail(lookback)
        highs = recent["high"].values
        lows = recent["low"].values
        close = self.df["close"].iloc[-1]

        resistance_levels = self._find_pivot_highs(highs)
        support_levels = self._find_pivot_lows(lows)

        nearest_resistance = min(
            (r for r in resistance_levels if r > close), default=None
        )
        nearest_support = max(
            (s for s in support_levels if s < close), default=None
        )

        return {
            "resistance_levels": [_safe(r) for r in resistance_levels[-3:]],
            "support_levels": [_safe(s) for s in support_levels[-3:]],
            "nearest_resistance": _safe(nearest_resistance),
            "nearest_support": _safe(nearest_support),
            "near_resistance": (
                abs(close - nearest_resistance) / close < 0.005
                if nearest_resistance else False
            ),
            "near_support": (
                abs(close - nearest_support) / close < 0.005
                if nearest_support else False
            ),
        }

    def _find_pivot_highs(self, data: np.ndarray, window: int = 5) -> list:
        pivots = []
        for i in range(window, len(data) - window):
            if data[i] == max(data[i - window : i + window + 1]):
                pivots.append(data[i])
        return pivots

    def _find_pivot_lows(self, data: np.ndarray, window: int = 5) -> list:
        pivots = []
        for i in range(window, len(data) - window):
            if data[i] == min(data[i - window : i + window + 1]):
                pivots.append(data[i])
        return pivots

    # ── Candlestick Patterns ──────────────────────────────────────────────────

    def candlestick_patterns(self) -> Dict[str, bool]:
        """Detect common candlestick patterns on the last 3 candles."""
        df = self.df.tail(5).copy()
        o, h, l, c = df["open"], df["high"], df["low"], df["close"]

        last_o, last_h, last_l, last_c = o.iloc[-1], h.iloc[-1], l.iloc[-1], c.iloc[-1]
        prev_o, prev_h, prev_l, prev_c = o.iloc[-2], h.iloc[-2], l.iloc[-2], c.iloc[-2]

        body = abs(last_c - last_o)
        upper_wick = last_h - max(last_c, last_o)
        lower_wick = min(last_c, last_o) - last_l
        total_range = last_h - last_l or 0.0001

        prev_body = abs(prev_c - prev_o)

        patterns = {
            "hammer": (
                lower_wick >= 2 * body
                and upper_wick <= 0.1 * total_range
                and last_c > last_o
            ),
            "inverted_hammer": (
                upper_wick >= 2 * body
                and lower_wick <= 0.1 * total_range
                and last_c > last_o
            ),
            "shooting_star": (
                upper_wick >= 2 * body
                and lower_wick <= 0.1 * total_range
                and last_c < last_o
            ),
            "doji": body <= total_range * 0.05,
            "bullish_engulfing": (
                prev_c < prev_o  # prev bearish
                and last_c > last_o  # current bullish
                and last_o < prev_c
                and last_c > prev_o
            ),
            "bearish_engulfing": (
                prev_c > prev_o  # prev bullish
                and last_c < last_o  # current bearish
                and last_o > prev_c
                and last_c < prev_o
            ),
            "morning_star": self._morning_star(df),
            "evening_star": self._evening_star(df),
        }
        return patterns

    def _morning_star(self, df: pd.DataFrame) -> bool:
        if len(df) < 3:
            return False
        o, c = df["open"].values, df["close"].values
        return (
            c[-3] < o[-3]  # bearish candle
            and abs(c[-2] - o[-2]) < abs(c[-3] - o[-3]) * 0.3  # small body
            and c[-1] > o[-1]  # bullish candle
            and c[-1] > (o[-3] + c[-3]) / 2
        )

    def _evening_star(self, df: pd.DataFrame) -> bool:
        if len(df) < 3:
            return False
        o, c = df["open"].values, df["close"].values
        return (
            c[-3] > o[-3]  # bullish candle
            and abs(c[-2] - o[-2]) < abs(c[-3] - o[-3]) * 0.3  # small body
            and c[-1] < o[-1]  # bearish candle
            and c[-1] < (o[-3] + c[-3]) / 2
        )

    # ── Full Snapshot ─────────────────────────────────────────────────────────

    def full_snapshot(self) -> Dict[str, Any]:
        """Return all indicators in one dict for the AI engine."""
        close = self.df["close"].iloc[-1]
        ema50 = self.ema(50)
        ema200 = self.ema(200)
        rsi_val = self.rsi()
        macd_data = self.macd()
        atr_val = self.atr()
        vol = self.volume_analysis()
        adx_data = self.adx()
        sr = self.support_resistance()
        patterns = self.candlestick_patterns()
        bb = self.bollinger_bands()

        trend = "bullish" if (ema50 and ema200 and ema50 > ema200) else "bearish"

        return {
            "close": _safe(close),
            "ema_50": ema50,
            "ema_200": ema200,
            "trend": trend,
            "rsi": rsi_val,
            "macd": macd_data,
            "atr": atr_val,
            "volume": vol,
            "adx": adx_data,
            "support_resistance": sr,
            "candlestick_patterns": patterns,
            "bollinger_bands": bb,
            "active_patterns": [k for k, v in patterns.items() if v],
        }
