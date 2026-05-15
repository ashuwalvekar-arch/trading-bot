"""
Telegram alert system.
Sends trade signals, execution results, and daily summaries.
"""
from __future__ import annotations
import asyncio
from typing import Optional
import httpx
from loguru import logger
from config import settings


BASE_URL = f"https://api.telegram.org/bot{settings.telegram_bot_token}"


async def _send(text: str, parse_mode: str = "HTML") -> bool:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.debug("Telegram not configured — skipping alert.")
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{BASE_URL}/sendMessage",
                json={
                    "chat_id": settings.telegram_chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                },
            )
            resp.raise_for_status()
            return True
    except Exception as e:
        logger.error(f"Telegram send error: {e}")
        return False


async def send_signal_alert(
    symbol: str,
    direction: str,
    entry: float,
    sl: float,
    tp: float,
    confidence: float,
    reasoning: str,
    risk_level: str,
) -> None:
    emoji = "🟢" if direction == "BUY" else ("🔴" if direction == "SELL" else "⏸️")
    rr = abs(tp - entry) / abs(sl - entry) if abs(sl - entry) > 0 else 0

    msg = (
        f"{emoji} <b>{direction} Signal — {symbol}</b>\n\n"
        f"📌 Entry: <code>{entry:.6f}</code>\n"
        f"🛑 Stop Loss: <code>{sl:.6f}</code>\n"
        f"🎯 Take Profit: <code>{tp:.6f}</code>\n"
        f"⚖️ Risk:Reward: <code>1:{rr:.2f}</code>\n"
        f"🤖 AI Confidence: <b>{confidence:.1f}%</b>\n"
        f"⚠️ Risk Level: <b>{risk_level}</b>\n\n"
        f"💬 <i>{reasoning}</i>"
    )
    await _send(msg)


async def send_trade_opened(symbol: str, direction: str, qty: float, price: float) -> None:
    emoji = "📈" if direction == "BUY" else "📉"
    await _send(
        f"{emoji} <b>Trade Opened</b>\n"
        f"Symbol: {symbol}\n"
        f"Direction: {direction}\n"
        f"Qty: {qty:.6f}\n"
        f"Price: {price:.6f}"
    )


async def send_trade_closed(
    symbol: str, direction: str, pnl: float, pnl_pct: float
) -> None:
    emoji = "✅" if pnl > 0 else "❌"
    await _send(
        f"{emoji} <b>Trade Closed — {'WIN' if pnl > 0 else 'LOSS'}</b>\n"
        f"Symbol: {symbol}\n"
        f"Direction: {direction}\n"
        f"PnL: <code>${pnl:.2f} ({pnl_pct:.2f}%)</code>"
    )


async def send_daily_summary(
    total_trades: int, wins: int, losses: int, total_pnl: float
) -> None:
    wr = wins / total_trades * 100 if total_trades else 0
    await _send(
        f"📊 <b>Daily Performance Summary</b>\n\n"
        f"Trades: {total_trades} | Wins: {wins} | Losses: {losses}\n"
        f"Win Rate: {wr:.1f}%\n"
        f"Total PnL: <code>${total_pnl:.2f}</code>"
    )


async def send_error_alert(message: str) -> None:
    await _send(f"🚨 <b>BOT ERROR</b>\n<code>{message}</code>")
