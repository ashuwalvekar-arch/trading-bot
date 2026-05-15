"""
Telegram alert helper.
Sends messages via the python-telegram-bot library.
Token and chat_id are loaded from settings (env / .env file).
"""
from telegram import Bot
from config import settings


async def send_alert(message: str) -> None:
    """Send a plain-text alert to the configured Telegram chat."""
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id

    if not token or not chat_id:
        # Telegram not configured — log and skip silently
        return

    bot = Bot(token=token)
    await bot.send_message(chat_id=chat_id, text=message)
