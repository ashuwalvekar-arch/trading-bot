"""
webhooks/tradingview.py — FastAPI router for TradingView webhook alerts.
Mount this on the main FastAPI app at /webhook/tradingview.
"""
from __future__ import annotations

import hmac
import hashlib
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from config import settings
from logs.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhooks"])

# TradingView alert payload schema
class TVAlert(BaseModel):
    symbol: str
    action: str             # buy | sell | close
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    timeframe: Optional[str] = None
    strategy: Optional[str] = None
    message: Optional[str] = None
    secret: Optional[str] = None   # shared secret for auth


def verify_secret(secret: Optional[str]) -> bool:
    """Simple shared-secret verification for TradingView alerts."""
    expected = settings.dashboard.dashboard_secret_key.get_secret_value()
    if expected == "change-me-in-production":
        # Dev mode — skip verification
        return True
    if not secret:
        return False
    return hmac.compare_digest(secret, expected)


@router.post("/tradingview")
async def tradingview_webhook(
    alert: TVAlert,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """
    Receive TradingView strategy alerts and forward to the trading engine.

    TradingView alert message JSON example:
    {
        "symbol": "BTCUSDT",
        "action": "buy",
        "price": {{close}},
        "stop_loss": {{strategy.order.sl}},
        "take_profit": {{strategy.order.tp}},
        "secret": "your-secret-here"
    }
    """
    if not verify_secret(alert.secret):
        logger.warning(f"Unauthorized TradingView webhook from {request.client.host}")
        raise HTTPException(status_code=401, detail="Invalid webhook secret.")

    logger.info(
        f"TradingView alert received: {alert.symbol} {alert.action} @ {alert.price}"
    )

    # Normalise symbol format (BTCUSDT → BTC/USDT)
    symbol = _normalise_symbol(alert.symbol)
    action = alert.action.upper()

    if action not in ("BUY", "SELL", "CLOSE"):
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

    # Store webhook signal for the main trading loop to pick up
    background_tasks.add_task(
        _process_tv_alert,
        symbol=symbol,
        action=action,
        price=alert.price,
        sl=alert.stop_loss,
        tp=alert.take_profit,
        timeframe=alert.timeframe,
        strategy=alert.strategy,
    )

    return {"status": "received", "symbol": symbol, "action": action}


async def _process_tv_alert(
    symbol: str,
    action: str,
    price: Optional[float],
    sl: Optional[float],
    tp: Optional[float],
    timeframe: Optional[str],
    strategy: Optional[str],
) -> None:
    """Background task: process the TradingView alert."""
    from ai.reasoning_engine import TradeDecision
    from database.models import AsyncSessionLocal
    from database.memory import TradingMemory
    from exchange.client import ExchangeClient
    from tools.risk_manager import RiskManager
    from tools.trade_executor import TradeExecutor

    decision = TradeDecision(
        symbol=symbol,
        direction=action if action != "CLOSE" else "WAIT",
        confidence=70.0,   # TV alerts get baseline confidence
        entry_price=price,
        stop_loss=sl,
        take_profit=tp,
        risk_level="MEDIUM",
        reasoning=f"TradingView webhook: {strategy or 'manual'}",
        provider="tradingview",
    )

    async with AsyncSessionLocal() as session:
        memory = TradingMemory(session)
        exchange = ExchangeClient()
        await exchange.initialize()
        executor = TradeExecutor(exchange, memory, RiskManager())

        if action == "CLOSE":
            open_trades = await memory.get_open_trades(symbol=symbol)
            for trade in open_trades:
                current_price = await exchange.get_current_price(symbol)
                await executor.close_trade(trade, current_price, reason="tv_webhook_close")
        else:
            await executor.execute_signal(decision)

        await exchange.close()


def _normalise_symbol(raw: str) -> str:
    """Convert BTCUSDT → BTC/USDT, XAU/USD → XAU/USDT etc."""
    raw = raw.upper().replace("-", "").replace("_", "")
    # Common quote currencies
    for quote in ("USDT", "USD", "BUSD", "BTC", "ETH"):
        if raw.endswith(quote) and "/" not in raw:
            base = raw[: -len(quote)]
            return f"{base}/{quote}"
    return raw
