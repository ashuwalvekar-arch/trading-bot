"""
Feature Engineering for ML models.
Converts indicator snapshots into feature vectors suitable for
LSTM, Transformer, or RL agents.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import List, Tuple
from indicators.calculator import calculate


FEATURE_COLS = [
    "rsi", "ema50", "ema200", "ema_ratio",
    "macd", "macd_signal", "macd_hist",
    "atr_pct", "volume_ratio", "trend_strength",
    "close_normalized",
]


def build_features(df: pd.DataFrame, symbol: str, timeframe: str) -> pd.DataFrame:
    """
    Returns a DataFrame of normalised features derived from OHLCV data.
    Suitable for feeding into any sklearn / PyTorch model.
    """
    from ta.momentum import RSIIndicator
    from ta.trend import EMAIndicator, MACD
    from ta.volatility import AverageTrueRange
    import ta

    close = df["close"]
    high, low, volume = df["high"], df["low"], df["volume"]

    features = pd.DataFrame(index=df.index)
    features["rsi"] = RSIIndicator(close, window=14).rsi() / 100
    ema50 = EMAIndicator(close, window=50).ema_indicator()
    ema200 = EMAIndicator(close, window=200).ema_indicator()
    features["ema50"] = ema50 / close
    features["ema200"] = ema200 / close
    features["ema_ratio"] = ema50 / ema200

    macd_obj = MACD(close)
    features["macd"] = macd_obj.macd() / close
    features["macd_signal"] = macd_obj.macd_signal() / close
    features["macd_hist"] = macd_obj.macd_diff() / close

    atr = AverageTrueRange(high, low, close, window=14).average_true_range()
    features["atr_pct"] = atr / close

    vol_sma = volume.rolling(20).mean()
    features["volume_ratio"] = volume / vol_sma

    # Normalised close (rolling z-score over 50 periods)
    roll_mean = close.rolling(50).mean()
    roll_std = close.rolling(50).std()
    features["close_normalized"] = (close - roll_mean) / (roll_std + 1e-9)

    # Trend strength proxy
    features["trend_strength"] = ((ema50 - ema200) / ema200).abs() * 100

    return features.dropna()


def create_sequences(
    features: pd.DataFrame,
    labels: pd.Series,
    lookback: int = 60,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Creates (X, y) sequences for LSTM input.
    X shape: (samples, lookback, n_features)
    y shape: (samples,)
    """
    X, y = [], []
    arr = features.values
    lab = labels.values
    for i in range(lookback, len(arr)):
        X.append(arr[i - lookback : i])
        y.append(lab[i])
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.int64)
