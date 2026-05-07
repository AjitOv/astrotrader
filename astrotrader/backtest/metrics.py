"""Calibration & performance metrics for backtest runs.

Definitions
-----------
* Brier:       mean((p − y)²). Lower is better. Random guess on a 50/50 task = 0.25.
* Log loss:    −mean(y log p + (1−y) log (1−p)). Random guess = 0.693.
* Reliability: bin predicted p_up into K bins; in each bin compare mean predicted
               to mean realized. A perfectly calibrated model lies on y = x.
* Hit rate:    fraction of days where sign(p − 0.5) matched sign(actual_logret).
* Strategy:    a deliberately unsophisticated rule (long when bullish + above
               confidence threshold, short when bearish, flat else). Compounds
               actual horizon-h log-returns; OVERLAPS unless stride == horizon.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ----------------------------------------------------------------- core scalars


def brier_score(p_up: np.ndarray, actual_up: np.ndarray) -> float:
    return float(np.mean((p_up - actual_up) ** 2))


def log_loss(p_up: np.ndarray, actual_up: np.ndarray, eps: float = 1e-9) -> float:
    p = np.clip(p_up, eps, 1 - eps)
    y = actual_up.astype(float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def expected_calibration_error(
    p_up: np.ndarray, actual_up: np.ndarray, n_bins: int = 10
) -> float:
    """ECE: weighted mean |bin_pred − bin_actual| across non-empty bins.
    Industry-standard summary of a reliability diagram."""
    bins = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(p_up, bins) - 1, 0, n_bins - 1)
    n = len(p_up)
    ece = 0.0
    for b in range(n_bins):
        mask = idx == b
        if not mask.any():
            continue
        bin_pred = float(p_up[mask].mean())
        bin_act = float(actual_up[mask].mean())
        ece += (mask.sum() / n) * abs(bin_pred - bin_act)
    return float(ece)


# --------------------------------------------------------------- diagram tables


def reliability_table(
    p_up: np.ndarray, actual_up: np.ndarray, n_bins: int = 10
) -> pd.DataFrame:
    bins = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(p_up, bins) - 1, 0, n_bins - 1)
    rows = []
    for b in range(n_bins):
        mask = idx == b
        if not mask.any():
            continue
        rows.append(
            {
                "bin_low": float(bins[b]),
                "bin_high": float(bins[b + 1]),
                "n": int(mask.sum()),
                "mean_predicted": float(p_up[mask].mean()),
                "mean_actual": float(actual_up[mask].mean()),
            }
        )
    return pd.DataFrame(rows)


def hit_rate_by_confidence(
    p_up: np.ndarray,
    actual_up: np.ndarray,
    confidence: np.ndarray,
    thresholds: tuple[float, ...] = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5),
) -> pd.DataFrame:
    """Directional hit rate when confidence ≥ threshold.

    "Hit" = sign of (p_up − 0.5) matches sign of (actual_logret). Days with p == 0.5
    or actual == 0 are excluded from the rate."""
    pred_sign = np.sign(p_up - 0.5)
    actual_sign = np.where(actual_up > 0, 1, -1)
    correct = (pred_sign == actual_sign).astype(float)
    decisive = pred_sign != 0
    rows = []
    for t in thresholds:
        mask = (confidence >= t) & decisive
        if not mask.any():
            continue
        rows.append(
            {
                "min_confidence": float(t),
                "n": int(mask.sum()),
                "share_of_days": float(mask.sum() / len(p_up)),
                "hit_rate": float(correct[mask].mean()),
            }
        )
    return pd.DataFrame(rows)


# ------------------------------------------------------------------- strategy


def naive_strategy_equity(
    rows: pd.DataFrame,
    confidence_threshold: float = 0.0,
    bps_per_turn: float = 0.0,
) -> pd.DataFrame:
    """Compounded equity from a naive rule.

    rule: long  +1.0  when bias == 'bullish' and confidence >= threshold
          short −1.0  when bias == 'bearish' and confidence >= threshold
          flat   0.0  otherwise

    Returns dataframe with columns: date, position, pnl, equity, equity_buyhold."""
    df = rows.sort_values("date").reset_index(drop=True).copy()
    pos = np.where(
        (df["bias"] == "bullish") & (df["confidence"] >= confidence_threshold),
        1.0,
        np.where(
            (df["bias"] == "bearish") & (df["confidence"] >= confidence_threshold),
            -1.0,
            0.0,
        ),
    )
    cost = bps_per_turn * 1e-4 * np.abs(np.diff(np.r_[0.0, pos]))
    pnl = pos * df["actual_logret"].to_numpy() - cost
    out = pd.DataFrame(
        {
            "date": df["date"],
            "position": pos,
            "pnl": pnl,
            "equity": np.exp(np.cumsum(pnl)),
            "equity_buyhold": np.exp(np.cumsum(df["actual_logret"].to_numpy())),
        }
    )
    return out


def strategy_summary(eq: pd.DataFrame, ann_factor: float = 252.0) -> dict:
    """Sharpe / max DD / total return on the strategy's per-period pnl.

    Note: pnl here is per-row over the full *horizon h* trading days; it overlaps
    when stride < h. Treat Sharpe as a relative-comparison number, not an absolute."""
    pnl = eq["pnl"].to_numpy()
    pos = eq["position"].to_numpy() if "position" in eq.columns else np.zeros_like(pnl)
    active_share = float(np.mean(pos != 0)) if len(pos) > 0 else 0.0

    if len(pnl) == 0 or pnl.std() == 0:
        return {
            "sharpe": 0.0,
            "total_logret": 0.0,
            "max_dd": 0.0,
            "win_rate": 0.0,
            "active_share": active_share,
        }
    sharpe = float(pnl.mean() / pnl.std() * np.sqrt(ann_factor))
    log_eq = np.log(eq["equity"].to_numpy())
    running_max = np.maximum.accumulate(log_eq)
    max_dd = float(np.min(log_eq - running_max))
    return {
        "sharpe": sharpe,
        "total_logret": float(log_eq[-1]),
        "max_dd": max_dd,
        "win_rate": float(np.mean(pnl > 0)),
        "active_share": active_share,
    }
