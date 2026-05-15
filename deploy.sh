#!/bin/bash
# ================================================
# AI Trading Bot — Deployment Script
# Supports: Ubuntu VPS, Railway, Render, AWS
# ================================================
set -e

echo "🤖 AI Trading Bot Deployment"
echo "============================="

# 1. System dependencies
apt-get update -qq && apt-get install -y python3.11 python3.11-pip python3.11-venv git -qq

# 2. Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install --upgrade pip -q
pip install -r requirements.txt -q

# 4. Copy env file
if [ ! -f .env ]; then
  cp .env.example .env
  echo "⚠️  Edit .env with your API keys before starting!"
fi

# 5. Create directories
mkdir -p logs

# 6. Start bot with PM2 (optional) or systemd
if command -v pm2 &> /dev/null; then
  pm2 start main.py --name trading-bot --interpreter python3.11
  pm2 save
  echo "✅ Bot started with PM2"
else
  echo "Run: python main.py"
fi
