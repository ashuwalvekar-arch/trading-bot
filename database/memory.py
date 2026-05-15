"""
database/memory.py — Persistent AI memory: stores trades, patterns, market conditions.
The AI engine queries this to learn from history and adapt its strategy.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    LearningPattern,
    MarketMemory,
    PerformanceStats,
    Signal,
    Trade,
    TradeResult,
    TradeStatus,
)
from logs.logger import get_logger

logger = get_logger(__name__)


class TradingMemory:
    """
    Central memory hub. All reads/writes go through this class so the AI
    engine can request context-rich history summaries in one call.
    """

    def __init__(self, session: AsyncSession):
        self.db = session

    # ── Trade CRUD ────────────────────────────────────────────────────────────

    async def save_trade(self, trade: Trade) -> Trade:
        self.db.add(trade)
        await self.db.commit()
        await self.db.refresh(trade)
        logger.info(f"Trade saved: {trade.symbol} {trade.direction} @ {trade.entry_price}")
        return trade

    async def update_trade(self, trade: Trade) -> Trade:
        await self.db.commit()
        await self.db.refresh(trade)
        return trade

    async def get_trade_by_id(self, trade_id: int) -> Optional[Trade]:
        result = await self.db.execute(select(Trade).where(Trade.id == trade_id))
        return result.scalar_one_or_none()

    async def get_open_trades(self, symbol: Optional[str] = None) -> List[Trade]:
        q = select(Trade).where(Trade.status == TradeStatus.OPEN)
        if symbol:
            q = q.where(Trade.symbol == symbol)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def get_recent_trades(
        self, symbol: Optional[str] = None, limit: int = 50
    ) -> List[Trade]:
        q = (
            select(Trade)
            .order_by(desc(Trade.opened_at))
            .limit(limit)
        )
        if symbol:
            q = q.where(Trade.symbol == symbol)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def get_today_trades(self) -> List[Trade]:
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self.db.execute(
            select(Trade).where(Trade.opened_at >= today)
        )
        return list(result.scalars().all())

    # ── Performance ───────────────────────────────────────────────────────────

    async def get_win_rate(
        self, symbol: Optional[str] = None, days: int = 30
    ) -> Dict[str, Any]:
        since = datetime.utcnow() - timedelta(days=days)
        q = select(Trade).where(
            Trade.status == TradeStatus.CLOSED, Trade.opened_at >= since
        )
        if symbol:
            q = q.where(Trade.symbol == symbol)
        result = await self.db.execute(q)
        trades = list(result.scalars().all())

        if not trades:
            return {"win_rate": 0.0, "total": 0, "wins": 0, "losses": 0, "total_pnl": 0.0}

        wins = sum(1 for t in trades if t.result == TradeResult.WIN)
        losses = sum(1 for t in trades if t.result == TradeResult.LOSS)
        total_pnl = sum((t.pnl or 0) for t in trades)

        return {
            "win_rate": wins / len(trades) * 100,
            "total": len(trades),
            "wins": wins,
            "losses": losses,
            "total_pnl": total_pnl,
            "avg_pnl": total_pnl / len(trades),
        }

    async def get_daily_pnl(self) -> float:
        today_trades = await self.get_today_trades()
        return sum((t.pnl or 0) for t in today_trades if t.status == TradeStatus.CLOSED)

    # ── Memory Context (fed to AI) ────────────────────────────────────────────

    async def get_ai_memory_context(
        self, symbol: str, limit: int = 10
    ) -> str:
        """
        Summarise recent trade history for the AI prompt so it can learn
        from past wins/losses and adapt its reasoning.
        """
        recent = await self.get_recent_trades(symbol=symbol, limit=limit)
        stats = await self.get_win_rate(symbol=symbol, days=30)
        patterns = await self.get_learning_patterns()

        lines = [
            f"=== MEMORY CONTEXT for {symbol} ===",
            f"Last 30d: Win Rate={stats['win_rate']:.1f}% | Total={stats['total']} | PnL={stats['total_pnl']:.2f}",
            "",
            "Recent trades:",
        ]
        for t in recent[:5]:
            lines.append(
                f"  [{t.direction}] Entry={t.entry_price} Exit={t.exit_price} "
                f"Result={t.result} PnL={t.pnl} Confidence={t.confidence}%"
            )

        if patterns:
            lines.append("")
            lines.append("Learned patterns:")
            for p in patterns[:3]:
                lines.append(
                    f"  {p.pattern_name}: success_rate={p.success_rate:.1f}% (n={p.sample_count})"
                )

        return "\n".join(lines)

    # ── Signals ───────────────────────────────────────────────────────────────

    async def save_signal(self, signal: Signal) -> Signal:
        self.db.add(signal)
        await self.db.commit()
        await self.db.refresh(signal)
        return signal

    # ── Market Memory ─────────────────────────────────────────────────────────

    async def save_market_condition(
        self,
        symbol: str,
        timeframe: str,
        condition_type: str,
        condition_data: Dict,
        outcome: Optional[str] = None,
    ) -> None:
        mem = MarketMemory(
            symbol=symbol,
            timeframe=timeframe,
            condition_type=condition_type,
            condition_data=condition_data,
            outcome=outcome,
        )
        self.db.add(mem)
        await self.db.commit()

    # ── Learning Patterns ─────────────────────────────────────────────────────

    async def update_learning_pattern(
        self, pattern_name: str, pattern_data: Dict, success: bool
    ) -> None:
        result = await self.db.execute(
            select(LearningPattern).where(LearningPattern.pattern_name == pattern_name)
        )
        pattern = result.scalar_one_or_none()

        if pattern is None:
            pattern = LearningPattern(
                pattern_name=pattern_name,
                pattern_data=pattern_data,
                success_rate=100.0 if success else 0.0,
                sample_count=1,
            )
            self.db.add(pattern)
        else:
            # Incremental running average
            n = pattern.sample_count
            new_rate = (pattern.success_rate * n + (100.0 if success else 0.0)) / (n + 1)
            pattern.success_rate = new_rate
            pattern.sample_count = n + 1
            pattern.pattern_data = pattern_data

        await self.db.commit()

    async def get_learning_patterns(self) -> List[LearningPattern]:
        result = await self.db.execute(
            select(LearningPattern).order_by(desc(LearningPattern.success_rate))
        )
        return list(result.scalars().all())

    # ── Performance Stats Snapshot ─────────────────────────────────────────────

    async def snapshot_daily_performance(self) -> None:
        stats = await self.get_win_rate(days=1)
        snap = PerformanceStats(
            date=datetime.utcnow(),
            total_trades=stats["total"],
            winning_trades=stats["wins"],
            losing_trades=stats["losses"],
            win_rate=stats["win_rate"],
            total_pnl=stats["total_pnl"],
        )
        self.db.add(snap)
        await self.db.commit()
        logger.info("Daily performance snapshot saved.")
