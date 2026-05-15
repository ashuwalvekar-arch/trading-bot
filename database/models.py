"""
SQLAlchemy ORM models for persistent trade memory and bot state.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, Float, String, Boolean,
    DateTime, Text, JSON, ForeignKey, Index
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    exchange = Column(String(50), nullable=False)
    symbol = Column(String(30), nullable=False)
    direction = Column(String(10), nullable=False)   # BUY / SELL
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    leverage = Column(Integer, default=1)

    # AI metadata
    ai_signal = Column(String(10))                   # BUY / SELL / WAIT
    ai_confidence = Column(Float)
    ai_reasoning = Column(Text)
    ai_provider = Column(String(30))
    risk_level = Column(String(20))                  # LOW / MEDIUM / HIGH

    # Strategy metadata
    strategy = Column(String(100))
    timeframe = Column(String(10))
    market_conditions = Column(JSON)                 # snapshot of indicators

    # Execution
    order_id = Column(String(100))
    status = Column(String(20), default="open")      # open / closed / cancelled
    pnl = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    is_win = Column(Boolean, nullable=True)

    # Timestamps
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_trades_symbol_status", "symbol", "status"),
        Index("ix_trades_opened_at", "opened_at"),
    )

    def __repr__(self) -> str:
        return f"<Trade {self.id} {self.symbol} {self.direction} @ {self.entry_price}>"


class MarketMemory(Base):
    """Stores market condition snapshots the AI can learn from."""
    __tablename__ = "market_memory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(30), nullable=False)
    timeframe = Column(String(10), nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow)

    rsi = Column(Float)
    ema50 = Column(Float)
    ema200 = Column(Float)
    macd = Column(Float)
    macd_signal = Column(Float)
    atr = Column(Float)
    volume = Column(Float)
    volume_sma = Column(Float)
    trend = Column(String(20))            # BULLISH / BEARISH / SIDEWAYS
    pattern = Column(String(50))          # detected candlestick pattern
    support = Column(Float)
    resistance = Column(Float)
    outcome = Column(String(10))          # WIN / LOSS / NEUTRAL (filled later)

    __table_args__ = (
        Index("ix_market_memory_symbol", "symbol", "timeframe"),
    )


class BotPerformance(Base):
    """Daily performance snapshot."""
    __tablename__ = "bot_performance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, default=datetime.utcnow)
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    total_pnl = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0)
    best_trade_pnl = Column(Float, default=0.0)
    worst_trade_pnl = Column(Float, default=0.0)
    sharpe_ratio = Column(Float, nullable=True)


class SentimentLog(Base):
    __tablename__ = "sentiment_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(30))
    source = Column(String(50))         # twitter / reddit / news
    sentiment_score = Column(Float)     # -1 to +1
    raw_text = Column(Text)
    recorded_at = Column(DateTime, default=datetime.utcnow)
