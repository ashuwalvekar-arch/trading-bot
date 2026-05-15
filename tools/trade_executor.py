"""
tools/trade_executor.py — Orchestrates full trade lifecycle:
  signal → risk check → order placement → DB record → alert.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from ai.reasoning_engine import TradeDecision
from alerts.telegram import send_signal_alert, send_trade_result
from config import settings
from database.memory import TradingMemory
from database.models import Signal, SignalDirection, Trade, TradeResult, TradeStatus
from exchange.client import ExchangeClient
from logs.logger import get_logger
from tools.risk_manager import RiskManager

logger = get_logger(__name__)


class TradeExecutor:
    """
    Executes the full trade lifecycle end-to-end.
    """

    def __init__(
        self,
        exchange: ExchangeClient,
        memory: TradingMemory,
        risk_manager: RiskManager,
    ):
        self.exchange = exchange
        self.memory = memory
        self.risk = risk_manager

    # ── Open Trade ────────────────────────────────────────────────────────────

    async def execute_signal(self, decision: TradeDecision) -> Optional[Trade]:
        """
        Validate, size, and place a trade based on an AI decision.
        Returns the Trade ORM object if executed, else None.
        """
        if decision.direction == "WAIT":
            logger.info(f"Signal is WAIT for {decision.symbol} — no action.")
            return None

        # ── Gather pre-trade context
        balance = await self.exchange.get_usdt_balance()
        open_trades = await self.memory.get_open_trades()
        daily_pnl = await self.memory.get_daily_pnl()

        approved, reason = self.risk.pre_trade_checks(
            symbol=decision.symbol,
            confidence=decision.confidence,
            risk_level=decision.risk_level,
            daily_pnl=daily_pnl,
            balance=balance,
            open_count=len(open_trades),
        )

        if not approved:
            logger.warning(f"Trade blocked for {decision.symbol}: {reason}")
            return None

        # ── Entry price
        entry = decision.entry_price or await self.exchange.get_current_price(
            decision.symbol
        )
        atr = decision.indicators_used.get("atr", entry * 0.01)

        # ── SL / TP
        sl, tp = self.risk.calculate_sl_tp(
            entry, atr, decision.direction
        )
        if decision.stop_loss:
            sl = decision.stop_loss
        if decision.take_profit:
            tp = decision.take_profit

        # ── Position size
        qty = self.risk.calculate_position_size(
            balance, entry, sl, settings.risk.default_leverage
        )
        if qty <= 0:
            logger.warning(f"Calculated quantity is 0 for {decision.symbol}.")
            return None

        # ── Place order
        side = "buy" if decision.direction == "BUY" else "sell"
        try:
            order = await self.exchange.place_market_order(
                decision.symbol, side, qty
            )
        except Exception as e:
            logger.error(f"Order placement failed: {e}")
            return None

        # ── Record to DB
        trade = Trade(
            symbol=decision.symbol,
            exchange=self.exchange.name,
            direction=SignalDirection(decision.direction),
            status=TradeStatus.OPEN,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            quantity=qty,
            confidence=decision.confidence,
            risk_level=decision.risk_level,
            ai_reasoning=decision.reasoning,
            indicators_snapshot=decision.indicators_used,
            exchange_order_id=order.get("id"),
            opened_at=datetime.utcnow(),
        )
        trade = await self.memory.save_trade(trade)
        self.risk.record_trade(decision.symbol)

        # ── Save signal record
        signal = Signal(
            trade_id=trade.id,
            symbol=decision.symbol,
            direction=SignalDirection(decision.direction),
            confidence=decision.confidence,
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            risk_level=decision.risk_level,
            reasoning=decision.reasoning,
            indicators=decision.indicators_used,
            executed=True,
        )
        await self.memory.save_signal(signal)

        # ── Telegram alert
        await send_signal_alert(
            symbol=decision.symbol,
            direction=decision.direction,
            entry=entry,
            sl=sl,
            tp=tp,
            confidence=decision.confidence,
            risk_level=decision.risk_level,
            reasoning=decision.reasoning,
            provider=decision.provider,
        )

        logger.info(
            f"Trade OPENED: {decision.symbol} {decision.direction} "
            f"entry={entry} sl={sl} tp={tp} qty={qty}"
        )
        return trade

    # ── Close Trade ───────────────────────────────────────────────────────────

    async def close_trade(
        self, trade: Trade, exit_price: float, reason: str = "manual"
    ) -> Trade:
        side = "sell" if trade.direction == SignalDirection.BUY else "buy"
        try:
            await self.exchange.place_market_order(
                trade.symbol, side, trade.quantity
            )
        except Exception as e:
            logger.error(f"Close order failed: {e}")

        pnl_raw = (
            (exit_price - trade.entry_price) * trade.quantity
            if trade.direction == SignalDirection.BUY
            else (trade.entry_price - exit_price) * trade.quantity
        )
        pnl_pct = (exit_price - trade.entry_price) / trade.entry_price * 100 * (
            1 if trade.direction == SignalDirection.BUY else -1
        )

        trade.exit_price = exit_price
        trade.pnl = round(pnl_raw, 4)
        trade.pnl_pct = round(pnl_pct, 4)
        trade.status = TradeStatus.CLOSED
        trade.closed_at = datetime.utcnow()
        trade.result = (
            TradeResult.WIN
            if pnl_raw > 0
            else TradeResult.LOSS
            if pnl_raw < 0
            else TradeResult.BREAKEVEN
        )

        await self.memory.update_trade(trade)

        # Update learning pattern
        pattern_name = f"{trade.symbol}_{trade.direction.value}_{trade.strategy_used or 'default'}"
        await self.memory.update_learning_pattern(
            pattern_name=pattern_name,
            pattern_data={
                "symbol": trade.symbol,
                "direction": trade.direction.value,
                "confidence": trade.confidence,
            },
            success=trade.result == TradeResult.WIN,
        )

        await send_trade_result(
            symbol=trade.symbol,
            direction=trade.direction.value,
            entry=trade.entry_price,
            exit_price=exit_price,
            pnl=trade.pnl,
            pnl_pct=trade.pnl_pct,
            result=trade.result.value,
        )

        logger.info(
            f"Trade CLOSED: {trade.symbol} pnl={trade.pnl} ({trade.pnl_pct:.2f}%) "
            f"result={trade.result.value}"
        )
        return trade

    # ── Monitor Open Trades ───────────────────────────────────────────────────

    async def monitor_open_trades(self) -> None:
        """Check if any open trade has hit SL or TP and close it."""
        open_trades = await self.memory.get_open_trades()
        for trade in open_trades:
            try:
                price = await self.exchange.get_current_price(trade.symbol)
                hit_tp = (
                    (trade.direction == SignalDirection.BUY and price >= trade.take_profit)
                    or (trade.direction == SignalDirection.SELL and price <= trade.take_profit)
                )
                hit_sl = (
                    (trade.direction == SignalDirection.BUY and price <= trade.stop_loss)
                    or (trade.direction == SignalDirection.SELL and price >= trade.stop_loss)
                )
                if hit_tp:
                    await self.close_trade(trade, price, reason="take_profit")
                elif hit_sl:
                    await self.close_trade(trade, price, reason="stop_loss")
            except Exception as e:
                logger.error(f"Monitor error for trade {trade.id}: {e}")
