"""
AI Trading Bot — Main Entry Point
==================================
Orchestrates the full pipeline:
1. Init DB
2. Connect to exchange
3. Start dashboard server (background)
4. Run main trading loop

Usage:
    python main.py                # Live trading mode
    python main.py --backtest     # Backtest mode
    python main.py --scan         # Market scan only
    python main.py --dashboard    # Dashboard only
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import uvicorn
from loguru import logger

# ── Setup logging ─────────────────────────────────────────────────────────────
Path("logs").mkdir(exist_ok=True)
logger.remove()
logger.add(sys.stderr, level="INFO", colorize=True,
           format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")
logger.add("logs/trading_bot.log", rotation="10 MB", retention="30 days",
           level="DEBUG", encoding="utf-8")

# ── Local imports ─────────────────────────────────────────────────────────────
from config import settings
from database.db import init_db, get_recent_trades, get_win_rate
from exchange.connector import ExchangeConnector
from indicators.calculator import calculate, IndicatorResult
from ai.reasoning_engine import get_ai_decision
from strategies.multi_timeframe import confirm_multi_timeframe
from strategies.trade_executor import execute_trade, build_trade_history_summary
from tools.sentiment_analyzer import analyze_sentiment
from tools.market_scanner import scan_market
from tools.whale_tracker import get_funding_rates
from tools.news_filter import is_news_blackout, refresh_events
from alerts.telegram_bot import send_daily_summary, send_error_alert
from dashboard.app import app as dashboard_app


# ── Main trading loop ─────────────────────────────────────────────────────────

async def analyse_symbol(
    symbol: str,
    exchange: ExchangeConnector,
    balance: float,
) -> None:
    """Full analysis pipeline for a single symbol."""
    logger.info(f"Analysing {symbol}...")

    # 1. Fetch multi-timeframe OHLCV
    ohlcv_map = await exchange.fetch_multi_timeframe(symbol, settings.timeframe_list)
    if not ohlcv_map:
        logger.warning(f"No OHLCV data for {symbol}")
        return

    # 2. Compute indicators per timeframe
    indicators: Dict[str, IndicatorResult] = {}
    for tf, df in ohlcv_map.items():
        ind = calculate(df, symbol, tf)
        indicators[tf] = ind
        logger.debug(f"  {tf}: RSI={ind.rsi} EMA50={ind.ema50:.2f} Signal={ind.signal}")

    # 3. Multi-timeframe confluence check
    mtf = confirm_multi_timeframe(indicators)
    logger.info(f"{symbol} MTF: {mtf.signal} ({mtf.confirmed_tfs}/{mtf.total_tfs} TFs, {mtf.strength:.1f}%)")

    if mtf.signal == "WAIT":
        logger.info(f"No MTF confirmation for {symbol} — skipping")
        return

    # 4. News blackout check
    if is_news_blackout():
        logger.warning("News blackout active — skipping trade")
        return

    # 5. Sentiment check
    sentiment = await analyze_sentiment(symbol)
    if sentiment.high_impact_news:
        logger.warning(f"High-impact news detected for {symbol} — skipping")
        return

    # 6. Funding rate check (for crypto)
    if "/" in symbol:
        base = symbol.split("/")[0]
        funding = await get_funding_rates([symbol])
        if funding:
            fr = funding[0]
            logger.info(f"Funding rate {symbol}: {fr.rate:.2f}% ({fr.sentiment})")
            # Avoid heavily-lopsided positions
            if fr.sentiment == "LONG_HEAVY" and mtf.signal == "BUY":
                logger.warning("Funding heavily long — reducing conviction")
            if fr.sentiment == "SHORT_HEAVY" and mtf.signal == "SELL":
                logger.warning("Funding heavily short — reducing conviction")

    # 7. Build historical trade context for AI
    history_summary = await build_trade_history_summary(symbol)

    # 8. AI decision
    primary_ind = indicators.get(settings.timeframe_list[-2], next(iter(indicators.values())))
    decision = await get_ai_decision(
        symbol=symbol,
        indicators=indicators,
        balance=balance,
        recent_trades_summary=history_summary,
    )

    if not decision:
        logger.warning(f"AI decision failed for {symbol}")
        return

    logger.info(
        f"AI: {decision.direction} | Confidence: {decision.confidence:.1f}% | "
        f"Risk: {decision.risk_level} | Provider: {decision.provider}"
    )
    logger.info(f"Reasoning: {decision.reasoning}")

    # 9. Execute trade
    market_conditions = {
        "price": primary_ind.current_price,
        "rsi": primary_ind.rsi,
        "trend": primary_ind.trend,
        "sentiment": sentiment.label,
    }

    await execute_trade(
        decision=decision,
        symbol=symbol,
        exchange=exchange,
        balance=balance,
        atr=primary_ind.atr,
        market_conditions=market_conditions,
    )


async def trading_loop() -> None:
    """Main perpetual trading loop."""
    await init_db()
    await refresh_events()

    async with ExchangeConnector() as exchange:
        logger.info(f"Connected to {settings.active_exchange} ({'TESTNET' if settings.use_testnet else 'LIVE'})")

        loop_count = 0
        while True:
            try:
                loop_count += 1
                balance = await exchange.get_balance()
                logger.info(f"Balance: ${balance:.2f} USDT | Loop #{loop_count}")

                for symbol in settings.pair_list:
                    await analyse_symbol(symbol, exchange, balance)
                    await asyncio.sleep(1)  # short pause between symbols

                # Every 24 loops (~2h at 5m intervals), send daily summary
                if loop_count % 24 == 0:
                    trades = await get_recent_trades(100)
                    closed = [t for t in trades if t.status == "closed"]
                    wins = sum(1 for t in closed if t.is_win)
                    pnl = sum(t.pnl or 0 for t in closed)
                    await send_daily_summary(len(closed), wins, len(closed) - wins, pnl)

                logger.info(f"Loop complete. Sleeping 5 minutes...")
                await asyncio.sleep(300)  # 5-minute main cycle

            except asyncio.CancelledError:
                logger.info("Trading loop cancelled.")
                break
            except Exception as e:
                logger.exception(f"Loop error: {e}")
                await send_error_alert(str(e))
                await asyncio.sleep(30)


async def backtest_mode() -> None:
    """Run backtests on all pairs."""
    from backtesting.engine import run_backtest

    await init_db()
    async with ExchangeConnector() as exchange:
        for symbol in settings.pair_list:
            for tf in ["1h", "4h"]:
                df = await exchange.fetch_ohlcv(symbol, tf, limit=1000)
                if df.empty:
                    continue
                result = run_backtest(df, symbol, tf)
                print(f"\n{'='*50}")
                print(f"Symbol: {result.symbol} | TF: {result.timeframe}")
                print(f"Trades: {result.total_trades} | Win Rate: {result.win_rate}%")
                print(f"Return: {result.total_return_pct:.2f}% | Max DD: {result.max_drawdown_pct:.2f}%")
                print(f"Profit Factor: {result.profit_factor} | Sharpe: {result.sharpe_ratio}")


async def scan_mode() -> None:
    """One-shot market scan."""
    async with ExchangeConnector() as exchange:
        results = await scan_market(exchange)
        print(f"\n{'Symbol':<15} {'Signal':<8} {'Confidence':<12} {'Trend':<12} {'RSI'}")
        print("-" * 60)
        for r in results:
            print(f"{r.symbol:<15} {r.signal:<8} {r.confidence:<12.1f} {r.trend:<12} {r.rsi:.1f}")


def start_dashboard() -> None:
    uvicorn.run(
        dashboard_app,
        host=settings.dashboard_host,
        port=settings.dashboard_port,
        log_level="warning",
    )


# ── Entry point ───────────────────────────────────────────────────────────────

async def main_async(args: argparse.Namespace) -> None:
    if args.backtest:
        await backtest_mode()
    elif args.scan:
        await scan_mode()
    elif args.dashboard:
        # Dashboard only
        import threading
        t = threading.Thread(target=start_dashboard, daemon=True)
        t.start()
        await asyncio.Event().wait()
    else:
        # Full bot: dashboard in background thread + trading loop
        import threading
        t = threading.Thread(target=start_dashboard, daemon=True)
        t.start()
        logger.info(f"Dashboard: http://{settings.dashboard_host}:{settings.dashboard_port}")
        await trading_loop()


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Trading Bot")
    parser.add_argument("--backtest", action="store_true", help="Run backtests")
    parser.add_argument("--scan", action="store_true", help="Market scan only")
    parser.add_argument("--dashboard", action="store_true", help="Dashboard only")
    args = parser.parse_args()

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")


if __name__ == "__main__":
    main()
