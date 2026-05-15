import pandas as pd

def detect_liquidity_sweep(df):

    last = df.iloc[-1]

    previous = df.iloc[-2]

    # BUY SIDE LIQUIDITY SWEEP
    if (
        last["low"] < previous["low"]
        and last["close"] > previous["low"]
    ):

        return {
            "type": "BUY",
            "reason": "Sell-side liquidity sweep"
        }

    # SELL SIDE LIQUIDITY SWEEP
    if (
        last["high"] > previous["high"]
        and last["close"] < previous["high"]
    ):

        return {
            "type": "SELL",
            "reason": "Buy-side liquidity sweep"
        }

    return None