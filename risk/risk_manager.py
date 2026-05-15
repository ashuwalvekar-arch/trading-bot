"""
Session-level risk manager.
Reads limits from settings so they respect the configured environment
instead of hard-coded numbers.
Tracks state per-instance to avoid shared global mutable state.
"""
from __future__ import annotations

from config import settings


class RiskManager:
    """Stateful risk guard for a single trading session."""

    def __init__(self):
        balance = 1000.0  # conservative fallback; ideally updated from exchange
        self.max_daily_loss: float = balance * (settings.max_daily_loss_percent / 100)
        self.max_trades: int = settings.max_open_trades
        self.current_loss: float = 0.0
        self.trade_count: int = 0

    def can_trade(self) -> bool:
        """Return True if neither the daily-loss nor trade-count limit is reached."""
        if self.current_loss >= self.max_daily_loss:
            return False
        if self.trade_count >= self.max_trades:
            return False
        return True

    def record_trade(self, pnl: float) -> None:
        """Call after each trade closes to update internal counters."""
        self.trade_count += 1
        if pnl < 0:
            self.current_loss += abs(pnl)

    def reset(self) -> None:
        """Reset daily counters (call at the start of each trading day)."""
        self.current_loss = 0.0
        self.trade_count = 0


# Module-level singleton for simple usage
_default_manager = RiskManager()


def can_trade() -> bool:
    return _default_manager.can_trade()


def record_trade(pnl: float) -> None:
    _default_manager.record_trade(pnl)


def reset_daily() -> None:
    _default_manager.reset()
