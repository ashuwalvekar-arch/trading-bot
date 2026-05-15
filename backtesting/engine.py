"""
Backtesting Engine.
Simulates the multi-timeframe strategy on historical OHLCV data.
Outputs: win rate, profit factor, max drawdown, Sharpe ratio, trade log.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
from loguru import logger
from indicators.calculator import calculate, IndicatorResult


@dataclass
class BacktestTrade:
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    entry_idx: int
    exit_price: float = 0.0
    exit_idx: int = 0
    pnl_pct: float = 0.0
    result: str = "OPEN"   # WIN | LOSS | OPEN


@dataclass
class BacktestResult:
    symbol: str
    timeframe: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    trades: List[BacktestTrade] = field(default_factory=list)


def _simulate_trade(
    df: pd.DataFrame,
    trade: BacktestTrade,
) -> BacktestTrade:
    """Walk forward from entry and check SL/TP hits."""
    for i in range(trade.entry_idx + 1, len(df)):
        h = df["high"].iloc[i]
        l = df["low"].iloc[i]

        if trade.direction == "BUY":
            if l <= trade.stop_loss:
                trade.exit_price = trade.stop_loss
                trade.pnl_pct = (trade.stop_loss - trade.entry_price) / trade.entry_price * 100
                trade.result = "LOSS"
                trade.exit_idx = i
                break
            if h >= trade.take_profit:
                trade.exit_price = trade.take_profit
                trade.pnl_pct = (trade.take_profit - trade.entry_price) / trade.entry_price * 100
                trade.result = "WIN"
                trade.exit_idx = i
                break
        else:  # SELL
            if h >= trade.stop_loss:
                trade.exit_price = trade.stop_loss
                trade.pnl_pct = (trade.entry_price - trade.stop_loss) / trade.entry_price * 100
                trade.result = "LOSS"
                trade.exit_idx = i
                break
            if l <= trade.take_profit:
                trade.exit_price = trade.take_profit
                trade.pnl_pct = (trade.entry_price - trade.take_profit) / trade.entry_price * 100
                trade.result = "WIN"
                trade.exit_idx = i
                break
    return trade


def run_backtest(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    sl_atr_mult: float = 2.0,
    tp_atr_mult: float = 4.0,
    min_signal_strength: float = 60.0,
) -> BacktestResult:
    result = BacktestResult(symbol=symbol, timeframe=timeframe)
    trades: List[BacktestTrade] = []
    in_trade = False

    # We need a rolling window — iterate with expanding window minimum 210 candles
    for i in range(210, len(df)):
        if in_trade:
            continue

        window = df.iloc[: i + 1]
        ind = calculate(window, symbol, timeframe)

        if ind.signal == "WAIT" or ind.signal_strength < min_signal_strength:
            continue
        if ind.atr == 0:
            continue

        entry = ind.current_price
        if ind.signal == "BUY":
            sl = entry - ind.atr * sl_atr_mult
            tp = entry + ind.atr * tp_atr_mult
        else:
            sl = entry + ind.atr * sl_atr_mult
            tp = entry - ind.atr * tp_atr_mult

        trade = BacktestTrade(
            symbol=symbol,
            direction=ind.signal,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            entry_idx=i,
        )
        trade = _simulate_trade(df, trade)
        trades.append(trade)

        if trade.result != "OPEN":
            in_trade = False  # allow next trade

    result.trades = trades
    result.total_trades = len(trades)

    closed = [t for t in trades if t.result != "OPEN"]
    result.wins = sum(1 for t in closed if t.result == "WIN")
    result.losses = sum(1 for t in closed if t.result == "LOSS")

    if result.total_trades > 0:
        result.win_rate = round(result.wins / len(closed) * 100, 2) if closed else 0.0

        pnls = [t.pnl_pct for t in closed]
        result.total_return_pct = round(sum(pnls), 2)

        # Max drawdown
        cumulative = np.cumsum(pnls)
        rolling_max = np.maximum.accumulate(cumulative)
        drawdowns = cumulative - rolling_max
        result.max_drawdown_pct = round(float(drawdowns.min()), 2) if len(drawdowns) else 0.0

        # Profit factor
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        result.profit_factor = round(gross_profit / gross_loss, 3) if gross_loss else float("inf")

        # Sharpe (annualised, assumes daily returns approximation)
        if len(pnls) > 1:
            mean_r = np.mean(pnls)
            std_r = np.std(pnls)
            result.sharpe_ratio = round(mean_r / std_r * math.sqrt(252), 3) if std_r else 0.0

    logger.info(
        f"Backtest {symbol} {timeframe}: {result.total_trades} trades, "
        f"WR={result.win_rate}%, PF={result.profit_factor}, DD={result.max_drawdown_pct}%"
    )
    return result
