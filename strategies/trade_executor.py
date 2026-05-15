"""
Trade Executor — bridges AI decision → risk checks → exchange orders → DB logging.
"""
from __future__ import annotations
import asyncio
from datetime import datetime
from typing import Optional
from loguru import logger

from ai.reasoning_engine import AIDecision
from database.models import Trade
from database.db import save_trade, get_win_rate, get_recent_trades
from exchange.connector import ExchangeConnector
from tools.risk_manager import (
    calculate_position_size, atr_based_sl_tp,
    is_safe_to_trade, set_cooldown
)
from alerts.telegram_bot import send_trade_opened, send_signal_alert
from config import settings


async def build_trade_history_summary(symbol: str) -> str:
    trades = await get_recent_trades(20)
    sym_trades = [t for t in trades if t.symbol == symbol]
    if not sym_trades:
        return ""
    win_rate = await get_win_rate(symbol, 20)
    lines = [f"Recent {symbol} trades (last {len(sym_trades)}): Win rate={win_rate}%"]
    for t in sym_trades[-5:]:
        lines.append(
            f"  {t.direction} @ {t.entry_price} → PnL: ${t.pnl or 0:.2f} ({t.status})"
        )
    return "\n".join(lines)


async def execute_trade(
    decision: AIDecision,
    symbol: str,
    exchange: ExchangeConnector,
    balance: float,
    atr: float,
    market_conditions: dict,
) -> Optional[Trade]:
    """
    Full trade execution pipeline.
    1. Safety checks
    2. Position sizing
    3. Place order
    4. Persist to DB
    5. Send Telegram alert
    """
    if decision.direction == "WAIT":
        logger.info(f"AI says WAIT for {symbol}")
        return None

    if decision.confidence < settings.min_confidence:
        logger.info(f"Confidence too low: {decision.confidence:.1f}% < {settings.min_confidence}%")
        return None

    # Safety checks
    safe, reason = await is_safe_to_trade(symbol, balance)
    if not safe:
        logger.warning(f"Trade blocked: {reason}")
        return None

    entry = decision.entry_price or market_conditions.get("price", 0)
    sl = decision.stop_loss
    tp = decision.take_profit

    # Fall back to ATR-based SL/TP if AI values missing
    if not sl or not tp:
        sl, tp = atr_based_sl_tp(entry, atr, decision.direction)

    qty = calculate_position_size(balance, entry, sl)
    if qty <= 0:
        logger.warning("Position size calculation resulted in 0.")
        return None

    # Notify signal BEFORE order
    await send_signal_alert(
        symbol, decision.direction, entry, sl, tp,
        decision.confidence, decision.reasoning, decision.risk_level
    )

    # Set leverage
    await exchange.set_leverage(symbol, settings.leverage)

    # Place market order
    side = "buy" if decision.direction == "BUY" else "sell"
    order = await exchange.place_market_order(symbol, side, qty)
    if not order:
        logger.error("Order placement failed.")
        return None

    actual_entry = float(order.get("average", entry))

    # Persist trade
    trade = Trade(
        exchange=settings.active_exchange,
        symbol=symbol,
        direction=decision.direction,
        entry_price=actual_entry,
        stop_loss=sl,
        take_profit=tp,
        quantity=qty,
        leverage=settings.leverage,
        ai_signal=decision.direction,
        ai_confidence=decision.confidence,
        ai_reasoning=decision.reasoning,
        ai_provider=decision.provider,
        risk_level=decision.risk_level,
        strategy="MTF_AI",
        timeframe="multi",
        market_conditions=market_conditions,
        order_id=str(order.get("id", "")),
        status="open",
        opened_at=datetime.utcnow(),
    )
    saved = await save_trade(trade)

    # Cooldown
    set_cooldown(symbol)

    await send_trade_opened(symbol, decision.direction, qty, actual_entry)
    logger.success(f"Trade opened: {decision.direction} {qty} {symbol} @ {actual_entry}")
    return saved
