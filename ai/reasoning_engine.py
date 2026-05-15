"""
AI Reasoning Engine — supports OpenAI, Groq, Gemini, DeepSeek.
Produces structured trading decisions with direction, confidence,
risk level, and reasoning text.
"""
from __future__ import annotations
import json
import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from loguru import logger
from config import settings
from indicators.calculator import IndicatorResult


@dataclass
class AIDecision:
    direction: str      # BUY | SELL | WAIT
    confidence: float   # 0–100
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_level: str     # LOW | MEDIUM | HIGH
    market_bias: str
    reasoning: str
    provider: str


SYSTEM_PROMPT = """You are an elite institutional quantitative trader with 20+ years of experience
in crypto, forex, and commodities markets. You have deep expertise in technical analysis,
risk management, and market microstructure.

Your role is to analyze market conditions and provide PRECISE, ACTIONABLE trading setups.
Always be conservative — capital preservation is the #1 priority.

When analyzing, consider:
1. Primary trend direction (EMA 50/200 relationship)
2. Momentum (RSI, MACD histogram)
3. Volume confirmation
4. Candlestick patterns
5. Multi-timeframe confluence
6. Support/resistance levels
7. Risk-reward ratio (minimum 1:2)

Return a valid JSON object ONLY (no markdown, no explanation outside JSON):
{
  "direction": "BUY|SELL|WAIT",
  "confidence": <0-100>,
  "entry_price": <float>,
  "stop_loss": <float>,
  "take_profit": <float>,
  "risk_level": "LOW|MEDIUM|HIGH",
  "market_bias": "<one sentence>",
  "reasoning": "<2-3 sentences explaining the setup>"
}"""


def _build_analysis_prompt(
    symbol: str,
    indicators: Dict[str, IndicatorResult],
    recent_trades_summary: str,
    balance: float,
) -> str:
    lines = [f"=== TRADING ANALYSIS REQUEST: {symbol} ===\n", f"Account balance: ${balance:.2f} USDT\n"]

    for tf, ind in indicators.items():
        lines.append(f"\n--- Timeframe: {tf} ---")
        lines.append(f"Price: {ind.current_price}")
        lines.append(f"RSI(14): {ind.rsi}")
        lines.append(f"EMA50: {ind.ema50}  EMA200: {ind.ema200}")
        lines.append(f"MACD: {ind.macd:.6f}  Signal: {ind.macd_signal:.6f}  Hist: {ind.macd_hist:.6f}")
        lines.append(f"ATR(14): {ind.atr}")
        lines.append(f"Volume: {ind.volume:.2f}  Vol SMA20: {ind.volume_sma:.2f}  Spike: {ind.volume_spike}")
        lines.append(f"Trend: {ind.trend}  Strength: {ind.trend_strength:.1f}%")
        lines.append(f"Support: {ind.support}  Resistance: {ind.resistance}")
        lines.append(f"Patterns: {', '.join(ind.patterns) if ind.patterns else 'None'}")
        lines.append(f"Rule-based signal: {ind.signal} ({ind.signal_strength}%)")

    if recent_trades_summary:
        lines.append(f"\n=== RECENT TRADE HISTORY ===\n{recent_trades_summary}")

    lines.append(
        "\nBased on ALL timeframes combined, provide the best trading setup or WAIT. "
        "Respond with JSON only."
    )
    return "\n".join(lines)


# ── Provider implementations ─────────────────────────────────────────────────

async def _call_openai(prompt: str) -> str:
    import openai
    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    resp = await client.chat.completions.create(
        model=settings.ai_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=600,
    )
    return resp.choices[0].message.content.strip()


async def _call_groq(prompt: str) -> str:
    from groq import AsyncGroq
    client = AsyncGroq(api_key=settings.groq_api_key)
    resp = await client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=600,
    )
    return resp.choices[0].message.content.strip()


async def _call_gemini(prompt: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-1.5-pro")
    full = f"{SYSTEM_PROMPT}\n\n{prompt}"
    resp = await asyncio.to_thread(model.generate_content, full)
    return resp.text.strip()


async def _call_deepseek(prompt: str) -> str:
    import openai
    client = openai.AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url="https://api.deepseek.com/v1",
    )
    resp = await client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=600,
    )
    return resp.choices[0].message.content.strip()


_PROVIDERS = {
    "openai": _call_openai,
    "groq": _call_groq,
    "gemini": _call_gemini,
    "deepseek": _call_deepseek,
}


async def get_ai_decision(
    symbol: str,
    indicators: Dict[str, IndicatorResult],
    balance: float = 1000.0,
    recent_trades_summary: str = "",
    provider: Optional[str] = None,
) -> Optional[AIDecision]:
    """
    Main entry point.  Returns AIDecision or None on failure.
    Falls back to secondary providers if primary fails.
    """
    if not settings.enable_ai_reasoning:
        # Fallback to rule-based only
        primary_tf = next(iter(indicators))
        ind = indicators[primary_tf]
        current = ind.current_price
        atr = ind.atr or current * 0.01
        direction = ind.signal
        return AIDecision(
            direction=direction,
            confidence=ind.signal_strength,
            entry_price=current,
            stop_loss=current - atr * 2 if direction == "BUY" else current + atr * 2,
            take_profit=current + atr * 4 if direction == "BUY" else current - atr * 4,
            risk_level="MEDIUM",
            market_bias=ind.trend,
            reasoning="Rule-based signal (AI disabled).",
            provider="rule-based",
        )

    provider = provider or settings.primary_ai_provider
    prompt = _build_analysis_prompt(symbol, indicators, recent_trades_summary, balance)

    provider_order = [provider] + [p for p in _PROVIDERS if p != provider]

    for prov in provider_order:
        fn = _PROVIDERS.get(prov)
        if fn is None:
            continue
        api_key = getattr(settings, f"{prov}_api_key", "")
        if not api_key:
            continue
        try:
            raw = await fn(prompt)
            raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            data: Dict[str, Any] = json.loads(raw)
            return AIDecision(
                direction=data.get("direction", "WAIT").upper(),
                confidence=float(data.get("confidence", 0)),
                entry_price=float(data.get("entry_price", 0)),
                stop_loss=float(data.get("stop_loss", 0)),
                take_profit=float(data.get("take_profit", 0)),
                risk_level=data.get("risk_level", "HIGH").upper(),
                market_bias=data.get("market_bias", ""),
                reasoning=data.get("reasoning", ""),
                provider=prov,
            )
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error from {prov}: {e}")
        except Exception as e:
            logger.warning(f"AI provider {prov} failed: {e}")

    logger.error("All AI providers failed.")
    return None
