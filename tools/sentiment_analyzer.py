"""
Sentiment & News analyzer.
Pulls from RSS/news feeds and scores sentiment with VADER.
Blocks trading during major news events (FOMC, NFP, CPI).
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
import feedparser
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from loguru import logger


HIGH_IMPACT_KEYWORDS = [
    "fomc", "fed rate", "federal reserve", "interest rate decision",
    "nfp", "non-farm payroll", "cpi", "inflation data",
    "emergency", "crash", "halt", "ban", "regulation",
]

NEWS_FEEDS = {
    "crypto": [
        "https://cointelegraph.com/rss",
        "https://decrypt.co/feed",
        "https://coindesk.com/arc/outboundfeeds/rss/",
    ],
    "forex": [
        "https://www.forexlive.com/feed/",
        "https://www.fxstreet.com/rss",
    ],
    "general": [
        "https://feeds.finance.yahoo.com/rss/2.0/headline",
    ],
}

_vader = SentimentIntensityAnalyzer()


@dataclass
class SentimentResult:
    symbol: str
    score: float            # -1.0 (very bearish) to +1.0 (very bullish)
    label: str              # BEARISH | NEUTRAL | BULLISH
    high_impact_news: bool
    news_titles: List[str]


async def analyze_sentiment(symbol: str) -> SentimentResult:
    """Fetch recent news and compute sentiment score."""
    category = "crypto" if any(c in symbol for c in ["BTC", "ETH", "XRP"]) else "forex"
    feeds = NEWS_FEEDS.get(category, []) + NEWS_FEEDS["general"]

    titles: List[str] = []
    scores: List[float] = []
    high_impact = False

    for feed_url in feeds:
        try:
            feed = await asyncio.to_thread(feedparser.parse, feed_url)
            for entry in feed.entries[:10]:
                title = entry.get("title", "")
                if not title:
                    continue

                # Check high-impact keywords
                lower = title.lower()
                if any(kw in lower for kw in HIGH_IMPACT_KEYWORDS):
                    high_impact = True

                vs = _vader.polarity_scores(title)
                scores.append(vs["compound"])
                titles.append(title)
        except Exception as e:
            logger.debug(f"Feed error ({feed_url}): {e}")

    avg_score = sum(scores) / len(scores) if scores else 0.0
    label = "BULLISH" if avg_score > 0.05 else ("BEARISH" if avg_score < -0.05 else "NEUTRAL")

    return SentimentResult(
        symbol=symbol,
        score=round(avg_score, 4),
        label=label,
        high_impact_news=high_impact,
        news_titles=titles[:5],
    )
