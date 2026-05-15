import pandas as pd

# =========================================================
# SWING HIGHS / LOWS
# =========================================================

def detect_swings(df, lookback=5):

    swing_highs = []
    swing_lows = []

    for i in range(lookback, len(df)-lookback):

        high = df['high'].iloc[i]

        low = df['low'].iloc[i]

        if high == max(
            df['high'].iloc[
                i-lookback:i+lookback
            ]
        ):

            swing_highs.append(i)

        if low == min(
            df['low'].iloc[
                i-lookback:i+lookback
            ]
        ):

            swing_lows.append(i)

    return swing_highs, swing_lows

# =========================================================
# BOS / CHOCH
# =========================================================

def detect_bos_choch(df):

    highs, lows = detect_swings(df)

    if len(highs) < 2 or len(lows) < 2:

        return None

    last_high = df['high'].iloc[highs[-1]]
    prev_high = df['high'].iloc[highs[-2]]

    last_low = df['low'].iloc[lows[-1]]
    prev_low = df['low'].iloc[lows[-2]]

    if last_high > prev_high:

        return {

            "type": "BOS_BULLISH",

            "reason":
            "Bullish break of structure"
        }

    if last_low < prev_low:

        return {

            "type": "BOS_BEARISH",

            "reason":
            "Bearish break of structure"
        }

    return None

# =========================================================
# LIQUIDITY SWEEP
# =========================================================

def detect_liquidity_sweep(df):

    latest = df.iloc[-1]

    prev_high = df['high'].rolling(
        20
    ).max().iloc[-2]

    prev_low = df['low'].rolling(
        20
    ).min().iloc[-2]

    if (

        latest['high'] > prev_high

        and

        latest['close'] < prev_high

    ):

        return {

            "type": "SELL",

            "reason":
            "Bearish liquidity sweep detected"
        }

    if (

        latest['low'] < prev_low

        and

        latest['close'] > prev_low

    ):

        return {

            "type": "BUY",

            "reason":
            "Bullish liquidity sweep detected"
        }

    return None

# =========================================================
# FAIR VALUE GAPS
# =========================================================

def detect_fvg(df):

    if len(df) < 5:

        return None

    c1 = df.iloc[-3]
    c2 = df.iloc[-2]
    c3 = df.iloc[-1]

    # Bullish FVG

    if c1['high'] < c3['low']:

        return {

            "type": "BULLISH_FVG",

            "reason":
            "Bullish fair value gap"
        }

    # Bearish FVG

    if c1['low'] > c3['high']:

        return {

            "type": "BEARISH_FVG",

            "reason":
            "Bearish fair value gap"
        }

    return None

# =========================================================
# ORDER BLOCK
# =========================================================

def detect_order_block(df):

    latest = df.iloc[-1]

    prev = df.iloc[-2]

    # Bullish OB

    if (

        prev['close'] < prev['open']

        and

        latest['close'] > latest['open']

    ):

        return {

            "type": "BULLISH_OB",

            "reason":
            "Bullish order block detected"
        }

    # Bearish OB

    if (

        prev['close'] > prev['open']

        and

        latest['close'] < latest['open']

    ):

        return {

            "type": "BEARISH_OB",

            "reason":
            "Bearish order block detected"
        }

    return None
