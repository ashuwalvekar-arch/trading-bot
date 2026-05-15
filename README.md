# 🤖 AI Trading Bot — Institutional Grade

A fully autonomous AI-powered trading bot supporting **Crypto**, **Forex**, **XAUUSD**, and **BTCUSD** across multiple exchanges.

## ✨ Features

| Feature | Status |
|---------|--------|
| Multi-exchange (Binance, Bybit) | ✅ |
| Multi-timeframe analysis (5m/15m/1h/4h) | ✅ |
| AI reasoning (OpenAI/Groq/Gemini/DeepSeek) | ✅ |
| Technical indicators (RSI/EMA/MACD/ATR) | ✅ |
| Candlestick pattern detection | ✅ |
| Risk management & position sizing | ✅ |
| Persistent SQLite/PostgreSQL memory | ✅ |
| Telegram alerts | ✅ |
| Web dashboard (FastAPI) | ✅ |
| TradingView webhook | ✅ |
| Backtesting engine | ✅ |
| Sentiment & news analysis | ✅ |
| Funding rate monitoring | ✅ |
| ML scaffolding (LSTM/Transformer) | ✅ |
| Docker deployment | ✅ |

## 🚀 Quick Start

```bash
# 1. Clone and setup
git clone <repo> && cd trading_bot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your API keys

# 3. Run (testnet by default)
python main.py

# Dashboard: http://localhost:8000
```

## 🎛️ Modes

```bash
python main.py                # Full bot + dashboard
python main.py --backtest     # Backtest all pairs
python main.py --scan         # Market scan only
python main.py --dashboard    # Dashboard only
```

## 📁 Project Structure

```
trading_bot/
├── main.py                    # Entry point
├── config.py                  # All settings via .env
├── requirements.txt
├── Dockerfile / docker-compose.yml
│
├── ai/
│   └── reasoning_engine.py    # OpenAI/Groq/Gemini/DeepSeek
│
├── exchange/
│   └── connector.py           # CCXT multi-exchange
│
├── indicators/
│   └── calculator.py          # RSI/EMA/MACD/ATR/patterns
│
├── strategies/
│   ├── multi_timeframe.py     # MTF confluence engine
│   └── trade_executor.py      # Order execution pipeline
│
├── tools/
│   ├── risk_manager.py        # Position sizing, daily limits
│   ├── sentiment_analyzer.py  # VADER + RSS feeds
│   ├── market_scanner.py      # Pair scanner
│   ├── whale_tracker.py       # Funding rates, whale alerts
│   └── news_filter.py         # News blackout system
│
├── database/
│   ├── models.py              # SQLAlchemy ORM
│   └── db.py                  # Async session + helpers
│
├── alerts/
│   └── telegram_bot.py        # Telegram notifications
│
├── backtesting/
│   └── engine.py              # Walk-forward backtest
│
├── dashboard/
│   └── app.py                 # FastAPI + live dashboard
│
└── machine_learning/
    ├── feature_engineering.py  # Feature extraction
    └── lstm_model.py           # LSTM PyTorch scaffold
```

## ⚙️ Key Configuration (.env)

```env
ACTIVE_EXCHANGE=binance
TRADING_PAIRS=BTC/USDT,ETH/USDT,XAU/USDT
USE_TESTNET=true           # Set false for live trading
RISK_PERCENT=1.0           # 1% per trade
MAX_DAILY_LOSS_PERCENT=5.0
LEVERAGE=1

PRIMARY_AI_PROVIDER=openai
AI_MODEL=gpt-4o
MIN_CONFIDENCE=65          # AI confidence threshold

TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## 🛡️ Risk Warnings

- **ALWAYS test on testnet first**
- This bot is educational/research software
- Past performance does not guarantee future results
- Crypto and forex trading involves substantial risk of loss
- Never trade with money you cannot afford to lose

## 🐳 Docker

```bash
docker-compose up -d
```

## 📊 Dashboard

Access at `http://localhost:8000` after starting the bot.
- Live signals panel
- Trade history
- Performance stats
- TradingView webhook: `POST /webhook/tradingview`

## 🔒 Security

- All credentials via environment variables
- Use IP whitelisting on exchange API keys
- Enable withdrawal restrictions on exchange
- Rotate API keys regularly
