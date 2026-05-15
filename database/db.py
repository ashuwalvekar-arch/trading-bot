"""
Async database engine, session factory, and helper functions.
"""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, date
from typing import AsyncGenerator, List, Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine
)
from sqlalchemy import select, func, and_

from database.models import Base, Trade, MarketMemory, BotPerformance, SentimentLog
from config import settings
from loguru import logger


engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_db() -> None:
    """Create all tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialised.")


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Trade helpers ─────────────────────────────────────────────────────────────

async def save_trade(trade: Trade) -> Trade:
    async with get_session() as s:
        s.add(trade)
        await s.flush()
        await s.refresh(trade)
        return trade


async def close_trade(trade_id: int, exit_price: float, pnl: float, pnl_pct: float) -> None:
    async with get_session() as s:
        result = await s.execute(select(Trade).where(Trade.id == trade_id))
        trade = result.scalar_one_or_none()
        if trade:
            trade.exit_price = exit_price
            trade.pnl = pnl
            trade.pnl_pct = pnl_pct
            trade.is_win = pnl > 0
            trade.status = "closed"
            trade.closed_at = datetime.utcnow()


async def get_open_trades(symbol: Optional[str] = None) -> List[Trade]:
    async with get_session() as s:
        q = select(Trade).where(Trade.status == "open")
        if symbol:
            q = q.where(Trade.symbol == symbol)
        result = await s.execute(q)
        return list(result.scalars().all())


async def get_daily_pnl() -> float:
    async with get_session() as s:
        today = date.today()
        result = await s.execute(
            select(func.coalesce(func.sum(Trade.pnl), 0.0)).where(
                and_(
                    Trade.status == "closed",
                    func.date(Trade.closed_at) == today,
                )
            )
        )
        return float(result.scalar_one())


async def get_recent_trades(limit: int = 50) -> List[Trade]:
    async with get_session() as s:
        result = await s.execute(
            select(Trade).order_by(Trade.opened_at.desc()).limit(limit)
        )
        return list(result.scalars().all())


async def get_win_rate(symbol: Optional[str] = None, lookback: int = 100) -> float:
    async with get_session() as s:
        q = select(Trade).where(Trade.status == "closed").order_by(
            Trade.closed_at.desc()
        ).limit(lookback)
        if symbol:
            q = q.where(Trade.symbol == symbol)
        result = await s.execute(q)
        trades = list(result.scalars().all())
        if not trades:
            return 0.0
        wins = sum(1 for t in trades if t.is_win)
        return round(wins / len(trades) * 100, 2)


# ── Market memory helpers ─────────────────────────────────────────────────────

async def save_market_memory(memory: MarketMemory) -> None:
    async with get_session() as s:
        s.add(memory)


async def get_market_history(symbol: str, timeframe: str, limit: int = 20) -> List[MarketMemory]:
    async with get_session() as s:
        result = await s.execute(
            select(MarketMemory)
            .where(
                and_(
                    MarketMemory.symbol == symbol,
                    MarketMemory.timeframe == timeframe,
                )
            )
            .order_by(MarketMemory.recorded_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
