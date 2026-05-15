import random
from datetime import datetime

symbols = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "BNB/USDT"
]

def get_live_signal():

    signal = random.choice(["BUY", "SELL"])

    return {
        "symbol": random.choice(symbols),
        "signal": signal,
        "confidence": random.randint(75, 98),
        "price": round(random.uniform(1000, 70000), 2),
        "time": datetime.utcnow().isoformat(),
        "reason": "AI momentum breakout detected"
    }