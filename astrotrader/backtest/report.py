"""Pretty-print backtest summaries and bundle metrics into one object."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .metrics import (
    brier_score,
    expected_calibration_error,
    hit_rate_by_confidence,
    log_loss,
    naive_strategy_equity,
    reliability_table,
    strategy_summary,
)


@dataclass
class BacktestSummary:
    n: int
    horizon: int
    base_rate_up: float
    mean_p_up: float
    brier: float
    log_loss: float
    ece: float
    reliability: pd.DataFrame
    hit_rates: pd.DataFrame
    equity: pd.DataFrame
    strategy: dict
    rows: pd.DataFrame


def summarize(rows: pd.DataFrame, horizon: int, confidence_threshold: float = 0.2) -> BacktestSummary:
    p_up = rows["p_up"].to_numpy()
    actual_up = rows["actual_up"].to_numpy()
    confidence = rows["confidence"].to_numpy()

    eq = naive_strategy_equity(rows, confidence_threshold=confidence_threshold)
    return BacktestSummary(
        n=len(rows),
        horizon=horizon,
        base_rate_up=float(actual_up.mean()),
        mean_p_up=float(p_up.mean()),
        brier=brier_score(p_up, actual_up),
        log_loss=log_loss(p_up, actual_up),
        ece=expected_calibration_error(p_up, actual_up),
        reliability=reliability_table(p_up, actual_up),
        hit_rates=hit_rate_by_confidence(p_up, actual_up, confidence),
        equity=eq,
        strategy=strategy_summary(eq),
        rows=rows,
    )


def print_summary(summary: BacktestSummary) -> None:
    print(f"\n=== ASTROTRADE BACKTEST :: horizon={summary.horizon}d :: N={summary.n} ===")
    print(f"base rate (actual P up):  {summary.base_rate_up:.3f}")
    print(f"mean predicted P(up):     {summary.mean_p_up:.3f}")
    print(f"Brier score:              {summary.brier:.4f}   (random=0.25; lower better)")
    print(f"Log loss:                 {summary.log_loss:.4f}   (random=0.693; lower better)")
    print(f"ECE (calibration error):  {summary.ece:.4f}   (perfect=0)")

    # Improvement over a constant predictor at base rate
    base = summary.base_rate_up
    brier_base = base * (1 - base)
    print(f"Brier vs base-rate baseline ({brier_base:.4f}): "
          f"{'BETTER' if summary.brier < brier_base else 'WORSE'} "
          f"by {brier_base - summary.brier:+.4f}")

    print("\nreliability (predicted bin → mean realized P(up)):")
    if not summary.reliability.empty:
        rel = summary.reliability.copy()
        for c in ("bin_low", "bin_high", "mean_predicted", "mean_actual"):
            rel[c] = rel[c].map(lambda x: f"{x:.3f}")
        print(rel.to_string(index=False))
    else:
        print("  (no rows)")

    print("\nhit rate by minimum confidence:")
    if not summary.hit_rates.empty:
        hr = summary.hit_rates.copy()
        for c in ("min_confidence", "share_of_days", "hit_rate"):
            hr[c] = hr[c].map(lambda x: f"{x:.3f}")
        print(hr.to_string(index=False))
    else:
        print("  (no decisive predictions)")

    s = summary.strategy
    print(
        "\nnaive strategy (overlap-aware; treat as comparative):"
        f"\n  total log-return:    {s['total_logret']:+.3f}"
        f"\n  Sharpe (annualized): {s['sharpe']:+.2f}"
        f"\n  max drawdown:        {s['max_dd']:.3f}"
        f"\n  win rate:            {s['win_rate']:.3f}"
        f"\n  active share:        {s['active_share']:.3f}"
    )
    bh_logret = float(np.log(summary.equity['equity_buyhold'].iloc[-1]))
    print(f"  buy-and-hold logret: {bh_logret:+.3f}")
