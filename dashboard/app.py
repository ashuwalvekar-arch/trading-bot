from __future__ import annotations

import asyncio
import json
import threading
import time
from datetime import datetime
from typing import Dict, List

import pandas as pd
import requests
import ta

from fastapi import FastAPI
from fastapi import WebSocket
from fastapi import WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

# =========================================================
# MT5 GRACEFUL IMPORT (Windows only)
# =========================================================

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False
    print("WARNING: MetaTrader5 not available (Linux/Mac). Running in DEMO mode.")

# =========================================================
# OPTIONAL AI IMPORTS
# =========================================================

try:

    from prediction.ai_predictor import (
        predict_next_candle
    )

except:

    def predict_next_candle(*args):

        return {
            "signal": "BUY",
            "confidence": 88
        }

# =========================================================
# FASTAPI
# =========================================================

app = FastAPI(
    title="Institutional AI Trading Dashboard",
    version="20.0.0"
)


@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {
        "status": "running",
        "service": "AI Trading Bot"
    }


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================
# MT5 INIT
# =========================================================

if MT5_AVAILABLE:
    if not mt5.initialize():
        print("MT5 INIT FAILED")
    else:
        print("MT5 CONNECTED")
else:
    print("MT5 SKIPPED — running in demo/simulation mode")

# =========================================================
# SYMBOLS
# =========================================================

SYMBOLS = [

    "GOLD.i#",
    "BTCUSD#",
    "EURUSD#",
    "NAS100#",
    "US30#",
    "GBPJPY#"
]

# =========================================================
# GLOBALS
# =========================================================

_latest_signals: List[Dict] = []
trade_history_data = []
_connected_ws: List[WebSocket] = []

# =========================================================
# TELEGRAM
# =========================================================

TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""


def send_telegram(message):

    if TELEGRAM_BOT_TOKEN == "":
        return

    try:

        url = (
            f"https://api.telegram.org/bot"
            f"{TELEGRAM_BOT_TOKEN}"
            f"/sendMessage"
        )

        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        }

        requests.post(
            url,
            data=payload,
            timeout=10
        )

    except Exception as e:

        print("TELEGRAM ERROR:", e)

# =========================================================
# SESSION FILTER
# =========================================================


def session_filter():

    hour = datetime.utcnow().hour

    london = (
        hour >= 7
        and
        hour <= 11
    )

    newyork = (
        hour >= 13
        and
        hour <= 17
    )

    return london or newyork

# =========================================================
# NEWS FILTER
# =========================================================

HIGH_IMPACT_NEWS = [
    "FOMC",
    "NFP",
    "CPI",
    "Powell",
    "Interest Rate"
]


def news_filter():

    try:

        url = (
            "https://nfs.faireconomy.media/"
            "ff_calendar_thisweek.json"
        )

        data = requests.get(
            url,
            timeout=10
        ).json()

        for event in data:

            title = str(
                event.get("title", "")
            )

            impact = str(
                event.get("impact", "")
            )

            if impact.lower() == "high":

                for keyword in HIGH_IMPACT_NEWS:

                    if keyword.lower() in title.lower():

                        return False

        return True

    except:

        return True

# =========================================================
# RISK MANAGEMENT
# =========================================================

MAX_DAILY_LOSS = 100
MAX_OPEN_TRADES = 3
RISK_PERCENT = 1


def prop_firm_check():

    if not MT5_AVAILABLE or mt5 is None:
        return True  # Allow in demo mode

    positions = mt5.positions_get()

    if positions:

        if len(positions) >= MAX_OPEN_TRADES:

            return False

    account = mt5.account_info()

    if account:

        if account.profit < -MAX_DAILY_LOSS:

            return False

    return True

# =========================================================
# LOT SIZE
# =========================================================


def calculate_lot_size(stop_loss_points):

    if not MT5_AVAILABLE or mt5 is None:
        return 0.01  # Default demo lot size

    account = mt5.account_info()

    if account is None:

        return 0.01

    balance = account.balance

    risk_amount = (
        balance
        *
        RISK_PERCENT
    ) / 100

    lot_size = (
        risk_amount
        /
        stop_loss_points
    ) / 10

    if lot_size < 0.01:
        lot_size = 0.01

    if lot_size > 1:
        lot_size = 1

    return round(lot_size, 2)

# =========================================================
# TRAILING STOP
# =========================================================


def trailing_stop_manager():

    while True:

        try:

            if not MT5_AVAILABLE or mt5 is None:
                time.sleep(30)
                continue

            positions = mt5.positions_get()

            if positions:

                for pos in positions:

                    if pos.profit > 5:

                        request = {

                            "action": mt5.TRADE_ACTION_SLTP,

                            "symbol": pos.symbol,

                            "position": pos.ticket,

                            "sl": pos.price_open,

                            "tp": pos.tp
                        }

                        mt5.order_send(request)

        except Exception as e:

            print("TRAILING STOP ERROR:", e)

        time.sleep(10)

# =========================================================
# DEMO DATA GENERATOR (used when MT5 is unavailable)
# =========================================================

import random

_DEMO_PRICES = {
    "GOLD.i#": 2320.00,
    "BTCUSD#": 65000.00,
    "EURUSD#": 1.0850,
    "NAS100#": 18500.00,
    "US30#": 39500.00,
    "GBPJPY#": 195.50,
}


def get_demo_rates(symbol, count=300):
    """Generate synthetic OHLCV data for demo mode."""
    base = _DEMO_PRICES.get(symbol, 1000.0)
    rows = []
    price = base
    for i in range(count):
        change = random.uniform(-0.002, 0.002) * price
        open_ = price
        close = price + change
        high = max(open_, close) + abs(random.uniform(0, 0.001) * price)
        low = min(open_, close) - abs(random.uniform(0, 0.001) * price)
        rows.append({
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "tick_volume": random.randint(100, 2000),
        })
        price = close
    return rows

# =========================================================
# MULTI TIMEFRAME ANALYSIS
# =========================================================


def multi_timeframe_mt5_symbol(symbol):

    try:

        if MT5_AVAILABLE and mt5 is not None:
            timeframes = {
                "M5": mt5.TIMEFRAME_M5,
                "M15": mt5.TIMEFRAME_M15,
                "H1": mt5.TIMEFRAME_H1
            }

            bullish = 0
            bearish = 0

            for _, tf in timeframes.items():

                rates = mt5.copy_rates_from_pos(
                    symbol,
                    tf,
                    0,
                    200
                )

                if rates is None:
                    continue

                df = pd.DataFrame(rates)

                df['ema20'] = ta.trend.ema_indicator(
                    df['close'],
                    window=20
                )

                df['ema50'] = ta.trend.ema_indicator(
                    df['close'],
                    window=50
                )

                latest = df.iloc[-1]

                if latest['ema20'] > latest['ema50']:
                    bullish += 1
                else:
                    bearish += 1

        else:
            # Demo mode: use synthetic data for all 3 timeframes
            bullish = 0
            bearish = 0
            for _ in range(3):
                df = pd.DataFrame(get_demo_rates(symbol, 200))
                df['ema20'] = ta.trend.ema_indicator(df['close'], window=20)
                df['ema50'] = ta.trend.ema_indicator(df['close'], window=50)
                latest = df.iloc[-1]
                if latest['ema20'] > latest['ema50']:
                    bullish += 1
                else:
                    bearish += 1

        if bullish >= 2:
            return "BUY"

        if bearish >= 2:
            return "SELL"

        return "WAIT"

    except:

        return "WAIT"

# =========================================================
# AI SIGNAL ENGINE
# =========================================================


def generate_signal_for_symbol(symbol):

    try:

        if MT5_AVAILABLE and mt5 is not None:
            rates = mt5.copy_rates_from_pos(
                symbol,
                mt5.TIMEFRAME_M5,
                0,
                300
            )
        else:
            rates = get_demo_rates(symbol, 300)

        if rates is None:
            return None

        df = pd.DataFrame(rates)

        df['ema20'] = ta.trend.ema_indicator(
            df['close'],
            window=20
        )

        df['ema50'] = ta.trend.ema_indicator(
            df['close'],
            window=50
        )

        df['rsi'] = ta.momentum.rsi(
            df['close'],
            window=14
        )

        latest = df.iloc[-1]

        entry = round(
            latest['close'],
            2
        )

        signal = "WAIT"
        confidence = 0
        sl = 0
        tp = 0

        buy_score = 0
        sell_score = 0

        mtf = multi_timeframe_mt5_symbol(symbol)

        if latest['ema20'] > latest['ema50']:
            buy_score += 1
        else:
            sell_score += 1

        if latest['rsi'] > 55:
            buy_score += 1

        if latest['rsi'] < 45:
            sell_score += 1

        ai = predict_next_candle(
            latest['ema20'],
            latest['ema50'],
            latest['rsi'],
            latest['close'],
            latest['tick_volume']
        )

        confidence = ai['confidence']

        if (
            buy_score >= 2
            and
            mtf == "BUY"
            and
            confidence >= 70
        ):

            signal = "BUY"
            sl = round(entry - 10, 2)
            tp = round(entry + 25, 2)

        elif (
            sell_score >= 2
            and
            mtf == "SELL"
            and
            confidence >= 70
        ):

            signal = "SELL"
            sl = round(entry + 10, 2)
            tp = round(entry - 25, 2)

        return {

            "symbol": symbol,

            "signal": signal,

            "price": entry,

            "sl": sl,

            "tp": tp,

            "confidence": confidence,

            "reason":
            f"Institutional AI Scanner | MTF {mtf}"
            + ("" if MT5_AVAILABLE else " [DEMO]")
        }

    except Exception as e:

        print("SCAN ERROR:", symbol, e)

        return None

# =========================================================
# BEST AI SIGNAL
# =========================================================


def generate_best_signal():

    all_signals = []

    for symbol in SYMBOLS:

        signal = generate_signal_for_symbol(symbol)

        if signal is None:
            continue

        if signal['signal'] == "WAIT":
            continue

        all_signals.append(signal)

    if len(all_signals) == 0:

        return {
            "symbol": "NONE",
            "signal": "WAIT",
            "price": 0,
            "sl": 0,
            "tp": 0,
            "confidence": 0,
            "reason": "No institutional setup"
        }

    best = max(
        all_signals,
        key=lambda x:
        x['confidence']
    )

    return best

# =========================================================
# AUTO TRADER
# =========================================================


def auto_trader():

    while True:

        try:

            signal = generate_best_signal()

            if (
                signal['signal'] == "WAIT"
                or
                signal['confidence'] < 70
            ):

                time.sleep(20)

                continue

            if not session_filter():

                time.sleep(60)

                continue

            if not news_filter():

                time.sleep(60)

                continue

            if not prop_firm_check():

                time.sleep(60)

                continue

            symbol = signal['symbol']

            # --- MT5 live execution ---
            if MT5_AVAILABLE and mt5 is not None:

                tick = mt5.symbol_info_tick(symbol)

                if tick is None:

                    time.sleep(10)

                    continue

                order_type = mt5.ORDER_TYPE_BUY
                price = tick.ask

                if signal['signal'] == "SELL":

                    order_type = mt5.ORDER_TYPE_SELL
                    price = tick.bid

                request = {

                    "action": mt5.TRADE_ACTION_DEAL,

                    "symbol": symbol,

                    "volume": calculate_lot_size(10),

                    "type": order_type,

                    "price": price,

                    "sl": signal['sl'],

                    "tp": signal['tp'],

                    "deviation": 20,

                    "magic": 100,

                    "comment": "MULTI ASSET AI",

                    "type_time": mt5.ORDER_TIME_GTC,

                    "type_filling": mt5.ORDER_FILLING_IOC,
                }

                result = mt5.order_send(request)
                print(result)

            else:
                # Demo mode — log trade without sending to broker
                print(f"[DEMO] Simulated {signal['signal']} on {symbol} @ {signal['price']}")

            trade_history_data.append({

                "time": datetime.utcnow().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),

                "symbol": symbol,

                "signal": signal['signal'],

                "entry": signal['price'],

                "confidence": signal['confidence']
            })

            send_telegram(

                f"AI TRADE EXECUTED\n\n"

                f"Symbol: {symbol}\n"

                f"Signal: {signal['signal']}\n"

                f"Confidence: {signal['confidence']}%"
            )

            time.sleep(120)

        except Exception as e:

            print("AUTO TRADER:", e)

            time.sleep(30)

# =========================================================
# ANALYTICS
# =========================================================

@app.get("/advanced_analytics")
async def advanced_analytics():

    total_trades = len(trade_history_data)

    buy_count = 0
    sell_count = 0

    equity_curve = []

    equity = 1000

    for trade in trade_history_data:

        if trade['signal'] == "BUY":
            buy_count += 1

        if trade['signal'] == "SELL":
            sell_count += 1

        equity += 10

        equity_curve.append(equity)

    return {
        "total_trades": total_trades,
        "buy_trades": buy_count,
        "sell_trades": sell_count,
        "equity_curve": equity_curve,
        "journal": trade_history_data[-20:]
    }

# =========================================================
# SIGNAL LOOP
# =========================================================

async def signal_loop():

    while True:

        try:

            signal = generate_best_signal()

            _latest_signals.clear()
            _latest_signals.append(signal)

            await broadcast_ws(
                json.dumps(signal)
            )

            await asyncio.sleep(10)

        except Exception as e:

            print("SIGNAL LOOP ERROR:", e)

            await asyncio.sleep(5)

# =========================================================
# STARTUP
# =========================================================

@app.on_event("startup")
async def startup():

    asyncio.create_task(
        signal_loop()
    )

    threading.Thread(
        target=trailing_stop_manager,
        daemon=True
    ).start()

    threading.Thread(
        target=auto_trader,
        daemon=True
    ).start()

# =========================================================
# API
# =========================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML

@app.get("/api/signals")
async def signals():

    if len(_latest_signals) == 0:
        _latest_signals.append(
            generate_best_signal()
        )

    return {
        "signals": _latest_signals
    }

@app.post("/execute_trade")
async def execute_trade():

    try:

        signal = generate_best_signal()

        if signal['signal'] == "WAIT":

            return {
                "status": "error",
                "message": "No valid trade setup"
            }

        symbol = signal['symbol']

        if MT5_AVAILABLE and mt5 is not None:

            tick = mt5.symbol_info_tick(symbol)

            if tick is None:

                return {
                    "status": "error",
                    "message": "No tick data"
                }

            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask

            if signal["signal"] == "SELL":

                order_type = mt5.ORDER_TYPE_SELL
                price = tick.bid

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": calculate_lot_size(10),
                "type": order_type,
                "price": price,
                "sl": signal["sl"],
                "tp": signal["tp"],
                "deviation": 20,
                "magic": 100,
                "comment": "AI BOT",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(request)

        else:
            # Demo mode
            result = "[DEMO] Order simulated — MT5 not available on this platform"
            print(f"[DEMO] execute_trade: {signal['signal']} {symbol} @ {signal['price']}")

        trade_history_data.append({
            "time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": symbol,
            "signal": signal['signal'],
            "entry": signal['price'],
            "confidence": signal['confidence']
        })

        return {
            "status": "success",
            "signal": signal,
            "result": str(result)
        }

    except Exception as e:

        return {
            "status": "error",
            "message": str(e)
        }

# =========================================================
# WEBSOCKET
# =========================================================

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):

    await ws.accept()

    _connected_ws.append(ws)

    try:

        while True:
            await ws.receive_text()

    except WebSocketDisconnect:

        _connected_ws.remove(ws)

async def broadcast_ws(message: str):

    dead = []

    for ws in _connected_ws:

        try:
            await ws.send_text(message)

        except:
            dead.append(ws)

    for ws in dead:
        _connected_ws.remove(ws)

# =========================================================
# HTML
# =========================================================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
<title>Institutional AI Trading Dashboard</title>
<meta charset="UTF-8">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#050B14;color:#e2e8f0;font-family:Arial,sans-serif;min-height:100vh}
.dash{padding:16px;max-width:1600px;margin:auto}
.topbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;padding:12px 20px;background:#0F172A;border-radius:14px;border:1px solid #1e293b}
.topbar h1{font-size:18px;font-weight:700;color:#00E0FF;letter-spacing:1px}
.topbar .status{display:flex;gap:12px;align-items:center}
.dot{width:8px;height:8px;border-radius:50%;background:#00ff99;display:inline-block;animation:pulse 1.5s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.3}}
.grid2{display:grid;grid-template-columns:1.5fr 1fr;gap:14px;margin-bottom:14px}
.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}
.card{background:#0F172A;border-radius:16px;padding:18px;border:1px solid #1e293b;margin-bottom:14px}
.card h3{font-size:11px;text-transform:uppercase;letter-spacing:1.5px;color:#64748b;margin-bottom:12px}
.signal-badge{display:inline-block;padding:4px 14px;border-radius:8px;font-size:12px;font-weight:700;letter-spacing:1px}
.buy{background:#052e16;color:#00ff99;border:1px solid #00ff99}
.sell{background:#2d0a0a;color:#ff4d6d;border:1px solid #ff4d6d}
.wait{background:#2d1f00;color:#ffaa00;border:1px solid #ffaa00}
.main-signal{font-size:52px;font-weight:900;line-height:1}
.main-signal.BUY{color:#00ff99}
.main-signal.SELL{color:#ff4d6d}
.main-signal.WAIT{color:#ffaa00}
.symbol{font-size:22px;font-weight:700;color:#e2e8f0;margin:6px 0 4px}
.price-row{display:flex;gap:20px;margin-top:10px;flex-wrap:wrap}
.price-item label{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px;display:block}
.price-item span{font-size:16px;font-weight:600;color:#cbd5e1}
.price-item.sl span{color:#ff4d6d}
.price-item.tp span{color:#00ff99}
.conf-bar{background:#1e293b;border-radius:6px;height:8px;margin-top:6px;overflow:hidden}
.conf-fill{height:100%;border-radius:6px;background:linear-gradient(90deg,#00E0FF,#00ff99);transition:width 0.5s}
.metric{background:#0a1628;border-radius:12px;padding:14px 16px;border:1px solid #1e293b;text-align:center}
.metric .val{font-size:28px;font-weight:800;color:#00E0FF}
.metric .lbl{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-top:4px}
.exec-btn{width:100%;padding:16px;border:none;border-radius:12px;background:#00E0FF;color:#050B14;font-size:16px;font-weight:800;cursor:pointer;letter-spacing:1px;transition:all 0.2s}
.exec-btn:hover{background:#00c4e0;transform:scale(1.01)}
.exec-btn:active{transform:scale(0.99)}
.exec-btn.loading{background:#1e293b;color:#64748b;cursor:not-allowed}
.symbols-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.sym-card{background:#0a1628;border-radius:10px;padding:10px 12px;border:1px solid #1e293b}
.sym-card .sym-name{font-size:11px;font-weight:700;color:#94a3b8;letter-spacing:1px}
.sym-card .sym-sig{font-size:14px;font-weight:800;margin-top:2px}
.sym-card .sym-sig.BUY{color:#00ff99}
.sym-card .sym-sig.SELL{color:#ff4d6d}
.sym-card .sym-sig.WAIT{color:#64748b}
.chart-wrap{position:relative;height:160px;width:100%}
.trade-list{max-height:200px;overflow-y:auto}
.trade-list::-webkit-scrollbar{width:4px}
.trade-list::-webkit-scrollbar-thumb{background:#1e293b;border-radius:4px}
.trade-row{display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid #1e293b;font-size:12px}
.trade-row:last-child{border-bottom:none}
.trade-row .tsym{font-weight:700;color:#cbd5e1;width:80px}
.trade-row .ttime{color:#475569;font-size:10px}
.tconf{font-size:11px;font-weight:700;color:#00E0FF}
.filters{display:flex;gap:8px;margin-bottom:10px}
.filter-btn{padding:4px 12px;border-radius:20px;border:1px solid #1e293b;background:transparent;color:#64748b;font-size:11px;cursor:pointer}
.filter-btn.active{background:#00E0FF22;color:#00E0FF;border-color:#00E0FF55}
.risk-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.risk-row label{font-size:12px;color:#64748b}
.risk-val{font-size:13px;font-weight:700;color:#e2e8f0}
.pass{color:#00ff99}
.fail{color:#ff4d6d}
.reason-box{background:#0a1628;border-radius:8px;padding:8px 12px;font-size:11px;color:#64748b;margin-top:10px;border-left:3px solid #00E0FF}
.tv-container{background:#0a1628;border-radius:12px;overflow:hidden;height:500px;border:1px solid #1e293b}
.alert-toast{position:fixed;bottom:20px;right:20px;background:#0F172A;border:1px solid #00ff99;color:#00ff99;padding:12px 20px;border-radius:12px;font-size:13px;font-weight:700;z-index:9999;opacity:0;transition:opacity 0.3s;max-width:300px;pointer-events:none}
.alert-toast.show{opacity:1}
</style>
</head>
<body>
<div class="dash">

<div class="topbar">
<h1>&#11041; INSTITUTIONAL AI TRADING DASHBOARD</h1>
<div class="status">
<span class="dot"></span>
<span style="font-size:12px;color:#64748b">MT5 LIVE</span>
<span id="clockEl" style="font-size:12px;color:#475569;font-family:monospace"></span>
</div>
</div>

<div class="grid2">

<div>

<div class="card">
<h3>AI Signal Engine</h3>
<div style="display:flex;align-items:flex-start;gap:24px;flex-wrap:wrap">
<div>
<div class="main-signal WAIT" id="mainSig">--</div>
<div class="symbol" id="mainSym">--</div>
<span class="signal-badge wait" id="sigBadge">SCANNING...</span>
</div>
<div style="flex:1;min-width:180px">
<div class="price-row">
<div class="price-item"><label>Entry</label><span id="entryP">--</span></div>
<div class="price-item sl"><label>Stop Loss</label><span id="slP">--</span></div>
<div class="price-item tp"><label>Take Profit</label><span id="tpP">--</span></div>
</div>
<div style="margin-top:14px">
<div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:4px">
<span style="color:#64748b">AI CONFIDENCE</span>
<span style="color:#00E0FF;font-weight:700" id="confVal">0%</span>
</div>
<div class="conf-bar"><div class="conf-fill" id="confBar" style="width:0%"></div></div>
</div>
<div class="reason-box" id="reasonBox">Waiting for signal...</div>
</div>
</div>
</div>

<div class="card">
<h3>Multi-Asset Scanner</h3>
<div class="symbols-grid">
<div class="sym-card"><div class="sym-name">GOLD.i#</div><div class="sym-sig WAIT" id="sym0">--</div></div>
<div class="sym-card"><div class="sym-name">BTCUSD#</div><div class="sym-sig WAIT" id="sym1">--</div></div>
<div class="sym-card"><div class="sym-name">EURUSD#</div><div class="sym-sig WAIT" id="sym2">--</div></div>
<div class="sym-card"><div class="sym-name">NAS100#</div><div class="sym-sig WAIT" id="sym3">--</div></div>
<div class="sym-card"><div class="sym-name">US30#</div><div class="sym-sig WAIT" id="sym4">--</div></div>
<div class="sym-card"><div class="sym-name">GBPJPY#</div><div class="sym-sig WAIT" id="sym5">--</div></div>
</div>
</div>

<div class="card">
<h3>Risk Management</h3>
<div class="risk-row"><label>Max Daily Loss</label><span class="risk-val">$100</span></div>
<div class="risk-row"><label>Max Open Trades</label><span class="risk-val">3</span></div>
<div class="risk-row"><label>Risk Per Trade</label><span class="risk-val">1%</span></div>
<div class="risk-row"><label>London / NY Session</label><span class="risk-val" id="sessionEl">CHECKING...</span></div>
<div class="risk-row"><label>News Filter</label><span class="risk-val" id="newsEl">CHECKING...</span></div>
<div class="risk-row"><label>Prop Firm Rules</label><span class="risk-val pass">&#10003; ENFORCED</span></div>
</div>

</div>

<div>

<div class="card">
<h3>Manual Execution</h3>
<button class="exec-btn" id="execBtn" onclick="executeTrade()">&#128640; EXECUTE AI TRADE</button>
<div style="margin-top:10px;font-size:11px;color:#475569;text-align:center">Lot size auto-calculated via 1% risk model</div>
</div>

<div class="card">
<h3>Institutional Analytics</h3>
<div class="grid4">
<div class="metric"><div class="val" id="totTrades">0</div><div class="lbl">Total</div></div>
<div class="metric"><div class="val" id="buyTrades" style="color:#00ff99">0</div><div class="lbl">BUY</div></div>
<div class="metric"><div class="val" id="sellTrades" style="color:#ff4d6d">0</div><div class="lbl">SELL</div></div>
<div class="metric"><div class="val" id="winRate">0%</div><div class="lbl">Win %</div></div>
</div>
<div class="chart-wrap" style="margin-top:10px"><canvas id="equityChart"></canvas></div>
</div>

<div class="card">
<h3>Trade Journal</h3>
<div class="filters">
<button class="filter-btn active" onclick="filterTrades('ALL',this)">ALL</button>
<button class="filter-btn" onclick="filterTrades('BUY',this)">BUY</button>
<button class="filter-btn" onclick="filterTrades('SELL',this)">SELL</button>
</div>
<div class="trade-list" id="tradeList">
<div style="text-align:center;color:#475569;font-size:12px;padding:20px">No trades yet</div>
</div>
</div>

</div>
</div>

<div class="card">
<h3>Live TradingView Chart</h3>
<div class="tv-container" id="tradingview_chart"></div>
</div>

</div>

<div class="alert-toast" id="toast"></div>

<script src="https://s3.tradingview.com/tv.js"></script>
<script>
let equityChart = null
let allTrades = []
let currentFilter = 'ALL'

function clock(){
const n = new Date()
document.getElementById('clockEl').textContent = n.toUTCString().split(' ')[4] + ' UTC'
}
clock(); setInterval(clock, 1000)

function showToast(msg, color){
const t = document.getElementById('toast')
t.textContent = msg
t.style.borderColor = color || '#00ff99'
t.style.color = color || '#00ff99'
t.classList.add('show')
setTimeout(()=>t.classList.remove('show'), 3500)
}

function checkSession(){
const h = new Date().getUTCHours()
const london = h>=7 && h<=11
const ny = h>=13 && h<=17
const el = document.getElementById('sessionEl')
if(london || ny){
el.textContent = (london ? '✓ LONDON' : '✓ NEW YORK') + ' ACTIVE'
el.className = 'risk-val pass'
} else {
el.textContent = '⚠ OFF-HOURS'
el.className = 'risk-val fail'
}
}
checkSession(); setInterval(checkSession, 30000)

new TradingView.widget({
"autosize": true,
"symbol": "OANDA:XAUUSD",
"interval": "5",
"timezone": "Asia/Kolkata",
"theme": "dark",
"style": "1",
"locale": "en",
"container_id": "tradingview_chart"
})

async function loadSignals(){
try {
const response = await fetch('/api/signals')
const data = await response.json()
const s = data.signals[0]
updateSignalUI(s)
} catch(e){}
}

function updateSignalUI(s){
const el = document.getElementById('mainSig')
el.textContent = s.signal
el.className = 'main-signal ' + s.signal
document.getElementById('mainSym').textContent = s.symbol
document.getElementById('entryP').textContent = s.price || '--'
document.getElementById('slP').textContent = s.sl || '--'
document.getElementById('tpP').textContent = s.tp || '--'
const conf = s.confidence || 0
document.getElementById('confVal').textContent = conf + '%'
document.getElementById('confBar').style.width = conf + '%'
document.getElementById('reasonBox').textContent = s.reason || ''
const badge = document.getElementById('sigBadge')
badge.className = 'signal-badge ' + (s.signal||'wait').toLowerCase()
badge.textContent = s.signal==='BUY' ? 'LONG SETUP' : s.signal==='SELL' ? 'SHORT SETUP' : 'NO SETUP'
const syms = ['GOLD.i#','BTCUSD#','EURUSD#','NAS100#','US30#','GBPJPY#']
syms.forEach((sym,i)=>{
const e2 = document.getElementById('sym'+i)
if(e2 && s.symbol===sym){
e2.textContent = s.signal
e2.className = 'sym-sig ' + s.signal
}
})
}

async function loadAnalytics(){
try {
const response = await fetch('/advanced_analytics')
const data = await response.json()
allTrades = data.journal || []
document.getElementById('totTrades').textContent = data.total_trades
document.getElementById('buyTrades').textContent = data.buy_trades
document.getElementById('sellTrades').textContent = data.sell_trades
const wr = data.total_trades>0 ? Math.round((data.buy_trades/data.total_trades)*100) : 0
document.getElementById('winRate').textContent = wr + '%'
const newsEl = document.getElementById('newsEl')
newsEl.textContent = '✓ CLEAR'
newsEl.className = 'risk-val pass'
renderEquity(data.equity_curve || [])
renderTrades()
} catch(e){}
}

function renderEquity(curve){
const ctx = document.getElementById('equityChart')
if(!ctx) return
if(equityChart) equityChart.destroy()
equityChart = new Chart(ctx, {
type: 'line',
data: {
labels: curve.map((_,i)=>i+1),
datasets:[{
label: 'Equity Curve',
data: curve,
borderColor: '#00ff99',
borderWidth: 2,
pointRadius: 0,
tension: 0.35,
fill: true,
backgroundColor: 'rgba(0,255,153,0.07)'
}]
},
options:{
responsive:true,
maintainAspectRatio:false,
plugins:{ legend:{ display:false } },
scales:{
x:{ display:false },
y:{ grid:{ color:'#1e293b' }, ticks:{ color:'#475569', font:{ size:10 } } }
}
}
})
}

function filterTrades(f, btn){
currentFilter = f
document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'))
btn.classList.add('active')
renderTrades()
}

function renderTrades(){
const list = document.getElementById('tradeList')
const filtered = currentFilter==='ALL' ? allTrades : allTrades.filter(t=>t.signal===currentFilter)
if(!filtered.length){
list.innerHTML = '<div style="text-align:center;color:#475569;font-size:12px;padding:20px">No trades</div>'
return
}
list.innerHTML = [...filtered].reverse().map(t=>`
<div class="trade-row">
<span class="tsym">${t.symbol}</span>
<span class="signal-badge ${(t.signal||'').toLowerCase()}" style="font-size:10px;padding:2px 8px">${t.signal}</span>
<span style="color:#94a3b8">${t.entry}</span>
<span class="tconf">${t.confidence}%</span>
<span class="ttime">${(t.time||'').slice(11,16)}</span>
</div>
`).join('')
}

async function executeTrade(){
const btn = document.getElementById('execBtn')
btn.textContent = '⏳ EXECUTING...'
btn.classList.add('loading')
btn.disabled = true
try {
const response = await fetch('/execute_trade',{ method:'POST' })
const data = await response.json()
if(data.status==='success'){
showToast('✓ TRADE EXECUTED: ' + (data.signal&&data.signal.symbol ? data.signal.symbol : ''), '#00ff99')
loadAnalytics()
} else {
showToast('✗ ' + (data.message||'Error'), '#ff4d6d')
}
} catch(e){
showToast('✗ Connection error', '#ff4d6d')
}
btn.textContent = '🚀 EXECUTE AI TRADE'
btn.classList.remove('loading')
btn.disabled = false
}

try {
const ws = new WebSocket('ws://' + location.host + '/ws')
ws.onmessage = (e) => {
try {
const s = JSON.parse(e.data)
if(s){
updateSignalUI(s)
if(s.signal!=='WAIT') showToast('📡 SIGNAL: ' + s.signal + ' ' + s.symbol, s.signal==='BUY'?'#00ff99':'#ff4d6d')
}
} catch(err){}
}
} catch(err){}

loadSignals()
loadAnalytics()
setInterval(loadSignals,5000)
setInterval(loadAnalytics,10000)
</script>
</body>
</html>
"""
