"""
Risk Management module.
Position sizing, max daily loss guard, ATR-based SL/TP, cooldown tracking.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from loguru import logger
from config import settings
from database.db import get_daily_pnl, get_open_trades


# Cooldown tracker: symbol -> last_trade_time
_cooldown_map: Dict[str, datetime] = {}


def calculate_position_size(
    balance: float,
    entry: float,
    stop_loss: float,
    risk_pct: float = settings.risk_percent,
    leverage: int = settings.leverage,
) -> float:
    """
    Kelly-inspired fixed-fractional position sizing.
    Returns quantity (in base asset units).
    """
    if entry <= 0 or abs(entry - stop_loss) < 1e-10:
        return 0.0
    risk_amount = balance * (risk_pct / 100)
    price_risk = abs(entry - stop_loss)
    qty = (risk_amount / price_risk) * leverage
    return round(qty, 6)


def atr_based_sl_tp(
    entry: float,
    atr: float,
    direction: str,
    sl_atr_mult: float = 2.0,
    tp_atr_mult: float = 4.0,
) -> Tuple[float, float]:
    """Returns (stop_loss, take_profit) based on ATR."""
    if direction == "BUY":
        sl = round(entry - atr * sl_atr_mult, 6)
        tp = round(entry + atr * tp_atr_mult, 6)
    else:
        sl = round(entry + atr * sl_atr_mult, 6)
        tp = round(entry - atr * tp_atr_mult, 6)
    return sl, tp


async def check_daily_loss_limit(balance: float) -> bool:
    """Returns True if trading is allowed (daily loss within limits)."""
    daily_pnl = await get_daily_pnl()
    max_loss = balance * (settings.max_daily_loss_percent / 100)
    if daily_pnl < -max_loss:
        logger.warning(f"Daily loss limit hit: ${daily_pnl:.2f}. Max: ${-max_loss:.2f}")
        return False
    return True


async def check_max_open_trades() -> bool:
    open_trades = await get_open_trades()
    if len(open_trades) >= settings.max_open_trades:
        logger.info(f"Max open trades reached ({settings.max_open_trades})")
        return False
    return True


def is_in_cooldown(symbol: str) -> bool:
    last = _cooldown_map.get(symbol)
    if last is None:
        return False
    elapsed = (datetime.utcnow() - last).total_seconds()
    return elapsed < settings.trade_cooldown_seconds


def set_cooldown(symbol: str) -> None:
    _cooldown_map[symbol] = datetime.utcnow()
    logger.debug(f"Cooldown set for {symbol}")


async def is_safe_to_trade(symbol: str, balance: float) -> Tuple[bool, str]:
    """Master safety check before any trade execution."""
    if is_in_cooldown(symbol):
        return False, f"Cooldown active for {symbol}"
    if not await check_daily_loss_limit(balance):
        return False, "Daily loss limit reached"
    if not await check_max_open_trades():
        return False, "Max open trades reached"
    return True, "OK"
