import asyncio
import random
from datetime import datetime, timedelta

from database.db import AsyncSessionLocal, Trade

symbols = [
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "BNB/USDT",
    "XRP/USDT"
]

signals = ["BUY", "SELL"]

strategies = [
    "AI Momentum",
    "Breakout",
    "Scalping",
    "Trend Following"
]

async def seed():
    async with AsyncSessionLocal() as session:
        for i in range(25):

            entry = random.uniform(100, 50000)
            pnl = random.uniform(-150, 300)

            trade = Trade(
                exchange="Binance",
                symbol=random.choice(symbols),
                direction=random.choice(signals),
                entry_price=entry,
                exit_price=entry + random.uniform(-500, 500),
                stop_loss=entry - random.uniform(10, 100),
                take_profit=entry + random.uniform(10, 300),
                quantity=random.uniform(0.01, 2),
                leverage=random.randint(1, 20),
                ai_signal=random.choice(signals),
                ai_confidence=random.uniform(70, 99),
                ai_reasoning="AI detected momentum breakout",
                ai_provider="OpenAI",
                risk_level=random.choice(["LOW", "MEDIUM", "HIGH"]),
                strategy=random.choice(strategies),
                timeframe="15m",
                market_conditions="Bullish",
                order_id=f"ORD-{i}",
                status="CLOSED",
                pnl=pnl,
                pnl_pct=random.uniform(-5, 10),
                is_win=pnl > 0,
                opened_at=datetime.utcnow() - timedelta(hours=i),
                closed_at=datetime.utcnow()
            )

            session.add(trade)

        await session.commit()

    print("Demo trades inserted successfully.")

asyncio.run(seed())