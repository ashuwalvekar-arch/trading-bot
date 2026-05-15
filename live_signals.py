import random

def get_live_signal():

    signal_type = random.choice(["BUY", "SELL"])

    entry = 4690.0

    if signal_type == "BUY":

        sl = entry - 10
        tp = entry + 25

        reason = (
            "Bullish liquidity sweep + "
            "AI bullish momentum"
        )

    else:

        sl = entry + 10
        tp = entry - 25

        reason = (
            "Bearish liquidity grab + "
            "AI bearish confirmation"
        )

    return {

        "symbol": "GOLD.i#",

        "signal": signal_type,

        "entry": round(entry,2),

        "sl": round(sl,2),

        "tp": round(tp,2),

        "confidence": random.randint(82,97),

        "reason": reason
    }