"""
News Event Filter — prevents trading during high-impact macro events.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import List
import asyncio
import httpx
from loguru import logger


# Hardcoded upcoming high-impact events (in production, pull from ForexFactory API or Investing.com)
HIGH_IMPACT_EVENTS: List[dict] = []


async def refresh_events() -> None:
    """
    Refresh high-impact event calendar.
    In production: integrate with ForexFactory RSS or economic calendar API.
    """
    global HIGH_IMPACT_EVENTS
    # Placeholder — replace with real calendar fetch
    HIGH_IMPACT_EVENTS = []
    logger.debug("News event calendar refreshed (placeholder)")


def is_news_blackout(buffer_minutes: int = 30) -> bool:
    """Returns True if we are within buffer_minutes of a high-impact event."""
    now = datetime.utcnow()
    for event in HIGH_IMPACT_EVENTS:
        event_time = event.get("time")
        if not event_time:
            continue
        diff = abs((event_time - now).total_seconds() / 60)
        if diff <= buffer_minutes:
            logger.warning(f"News blackout: {event.get('name')} in {diff:.0f} min")
            return True
    return False
