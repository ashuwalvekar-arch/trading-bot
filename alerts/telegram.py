"""
alerts/telegram.py — Sends formatted trade alerts to Telegram.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from config import settings
from logs.logger import get_logger

logger = get_logger(__name__)

_bot = None


def _get_bot():
    global _bot
    if _bot is None:
        from telegram import Bot
        _bot = Bot(token=settings.telegram.telegram_bot_token.get_secret_value())
    return _bot


async def send_message(text: str, parse_mode: str = "HTML") -> None:
    if not settings.telegram.telegram_enabled:
        logger.debug(f"[Telegram disabled] {text}")
        return
    try:
        bot = _get_bot()
        await bot.send_message(
            chat_id=settings.telegram.telegram_chat_id,
            text=text,
            parse_mode=parse_mode,
        )
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")


async def send_signal_alert(
    symbol: str,
    direction: str,
    entry: Optional[float],
    sl: Optional[float],
    tp: Optional[float],
    confidence: float,
    risk_level: str,
    reasoning: str,
    provider: str = "",
) -> None:
    emoji = "🟢" if direction == "BUY" else "🔴" if direction == "SELL" else "⚪"
    risk_emoji = {"LOW": "🟩", "MEDIUM": "🟨", "HIGH": "🟧", "EXTREME": "🟥"}.get(risk_level, "⬜")

    msg = f"""
{emoji} <b>TRADE SIGNAL — {symbol}</b>

<b>Direction :</b> {direction}
<b>Entry     :</b> {entry or 'market'}
<b>Stop Loss :</b> {sl}
<b>Take Profit:</b> {tp}
<b>Confidence:</b> {confidence:.1f}%
<b>Risk Level:</b> {risk_emoji} {risk_level}

<i>{reasoning}</i>

<code>AI: {provider}</code>
""".strip()
    await send_message(msg)


async def send_trade_result(
    symbol: str,
    direction: str,
    entry: float,
    exit_price: float,
    pnl: float,
    pnl_pct: float,
    result: str,
) -> None:
    emoji = "✅" if result == "WIN" else "❌" if result == "LOSS" else "➖"
    msg = f"""
{emoji} <b>TRADE CLOSED — {symbol}</b>

<b>Direction :</b> {direction}
<b>Entry     :</b> {entry}
<b>Exit      :</b> {exit_price}
<b>PnL       :</b> {pnl:+.2f} USDT ({pnl_pct:+.2f}%)
<b>Result    :</b> {result}
""".strip()
    await send_message(msg)


async def send_error_alert(message: str) -> None:
    msg = f"⚠️ <b>BOT ERROR</b>\n\n<code>{message[:500]}</code>"
    await send_message(msg)


async def send_daily_summary(stats: Dict[str, Any]) -> None:
    msg = f"""
📊 <b>DAILY SUMMARY</b>

<b>Trades   :</b> {stats.get('total', 0)}
<b>Win Rate :</b> {stats.get('win_rate', 0):.1f}%
<b>PnL      :</b> {stats.get('total_pnl', 0):+.2f} USDT
<b>Wins     :</b> {stats.get('wins', 0)}
<b>Losses   :</b> {stats.get('losses', 0)}
""".strip()
    await send_message(msg)
