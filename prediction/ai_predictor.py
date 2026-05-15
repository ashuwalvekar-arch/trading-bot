"""
AI model predictor — loads a pre-trained sklearn model and returns
BUY / SELL signals with confidence scores.
"""

from __future__ import annotations

from pathlib import Path
import joblib
import pandas as pd

# Resolve model path properly
_MODEL_PATH = Path(__file__).resolve().parent.parent / "ai_model.pkl"

_model = None


def _load_model():
    """
    Load AI model safely.
    Prevents scanner crashes if model file is missing.
    """
    global _model

    if _model is None:

        if not _MODEL_PATH.exists():
            print(
                f"WARNING: AI model not found at {_MODEL_PATH}. "
                "AI predictions disabled."
            )
            return None

        try:
            _model = joblib.load(_MODEL_PATH)
            print(f"AI model loaded successfully from {_MODEL_PATH}")

        except Exception as e:
            print(f"ERROR loading AI model: {e}")
            return None

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
    dict with keys:
        signal: BULLISH | BEARISH | NO_MODEL | ERROR
        confidence: 0-100
    """

    model = _load_model()

    # If model unavailable
    if model is None:
        return {
            "signal": "NO_MODEL",
            "confidence": 0.0,
        }

    try:

        features = pd.DataFrame([{
            "ema20": ema20,
            "ema50": ema50,
            "rsi": rsi,
            "returns": returns,
            "tick_volume": volume,
        }])

        prediction = model.predict(features)[0]

        # Handle models without predict_proba
        confidence = 50.0

        if hasattr(model, "predict_proba"):
            probability = model.predict_proba(features)[0]
            confidence = round(float(max(probability)) * 100, 2)

        return {
            "signal": "BULLISH" if prediction == 1 else "BEARISH",
            "confidence": confidence,
        }

    except Exception as e:

        print(f"Prediction error: {e}")

        return {
            "signal": "ERROR",
            "confidence": 0.0,
        }
