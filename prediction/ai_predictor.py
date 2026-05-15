"""
AI model predictor — loads a pre-trained sklearn model and returns
BUY / SELL signals with confidence scores.
"""
from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd

# Resolve the model path relative to this file so it works regardless
# of the current working directory.
_MODEL_PATH = Path(__file__).resolve().parent.parent / "ai_model.pkl"

_model = None


def _load_model():
    global _model
    if _model is None:
        if not _MODEL_PATH.exists():
            raise FileNotFoundError(
                f"AI model not found at {_MODEL_PATH}. "
                "Run train_ai.py to generate it first."
            )
        _model = joblib.load(_MODEL_PATH)
    return _model


def predict_next_candle(
    ema20: float,
    ema50: float,
    rsi: float,
    returns: float,
    volume: float,
) -> dict:
    """
    Predict the next candle direction.

    Returns
    -------
    dict with keys 'signal' ('BULLISH' | 'BEARISH') and 'confidence' (0-100).
    """
    model = _load_model()

    features = pd.DataFrame([{
        "ema20": ema20,
        "ema50": ema50,
        "rsi": rsi,
        "returns": returns,
        "tick_volume": volume,
    }])

    prediction = model.predict(features)[0]
    probability = model.predict_proba(features)[0]
    confidence = round(float(max(probability)) * 100, 2)

    return {
        "signal": "BULLISH" if prediction == 1 else "BEARISH",
        "confidence": confidence,
    }
