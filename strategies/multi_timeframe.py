"""
Multi-timeframe confluence checker.
Works entirely from pre-computed IndicatorResult objects passed in from main.py,
so no extra exchange calls are needed here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class MTFResult:
    signal: str          # BUY | SELL | WAIT
    confirmed_tfs: int   # number of timeframes agreeing
    total_tfs: int       # total timeframes evaluated
    strength: float      # agreement percentage (0-100)


def confirm_multi_timeframe(indicators: Dict) -> MTFResult:
    """
    Evaluate confluence across all timeframes in *indicators*.

    Parameters
    ----------
    indicators : dict mapping timeframe str -> IndicatorResult
                 (as built in main.py's analyse_symbol)

    Returns
    -------
    MTFResult with the consensus signal and strength metrics.
    """
    if not indicators:
        return MTFResult(signal="WAIT", confirmed_tfs=0, total_tfs=0, strength=0.0)

    votes: list[str] = []
    for ind in indicators.values():
        sig = getattr(ind, "signal", "WAIT")
        votes.append(sig)

    total = len(votes)
    buy_count  = votes.count("BUY")
    sell_count = votes.count("SELL")

    if buy_count > sell_count and buy_count / total >= 0.5:
        return MTFResult(
            signal="BUY",
            confirmed_tfs=buy_count,
            total_tfs=total,
            strength=round(buy_count / total * 100, 1),
        )

    if sell_count > buy_count and sell_count / total >= 0.5:
        return MTFResult(
            signal="SELL",
            confirmed_tfs=sell_count,
            total_tfs=total,
            strength=round(sell_count / total * 100, 1),
        )

    return MTFResult(signal="WAIT", confirmed_tfs=0, total_tfs=total, strength=0.0)