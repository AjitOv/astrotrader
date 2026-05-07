"""Feature-group ablation study.

Question this answers:
    Does each feature group (astro / market / regime) contribute Brier-score
    signal, or is it noise riding for free?

Method (no shortcuts):
    For each ablation config (a set of group weights):
      1. Rebuild SimilarityEngine with those weights.
      2. Walk-forward over the TRAINING window → raw probabilities.
      3. Fit a fresh calibrator on the training rows.
      4. Walk-forward over the TEST window with the calibrator attached.
      5. Compute test-window Brier / log loss / ECE / hit rate / strategy.

Comparing different ablations on the SAME test window with EACH using its OWN
fitted calibrator is the only fair comparison. Sharing a calibrator across
configs would mismeasure them.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Iterable

import numpy as np
import pandas as pd

from ..calibration.calibrator import IsotonicCalibrator, PlattCalibrator
from ..pipeline import AstrotradeContext
from ..similarity.engine import SimilarityEngine
from .metrics import (
    brier_score,
    expected_calibration_error,
    log_loss,
    naive_strategy_equity,
    strategy_summary,
)
from .walk_forward import walk_forward

log = logging.getLogger(__name__)


@dataclass
class AblationConfig:
    """One ablation: a label + relative weights for the three feature groups."""

    name: str
    weights: dict[str, float] = field(default_factory=dict)

    def normalized(self) -> dict[str, float]:
        s = float(sum(self.weights.values()))
        if s <= 0:
            raise ValueError(f"all weights are zero in ablation {self.name!r}")
        return {k: v / s for k, v in self.weights.items()}


# The default sweep. Renormalization happens inside SimilarityEngine, so absolute
# magnitudes here are irrelevant; only ratios matter.
STANDARD_ABLATIONS: list[AblationConfig] = [
    AblationConfig("full",        {"astro": 0.40, "market": 0.35, "regime": 0.25}),
    AblationConfig("no_astro",    {"astro": 0.00, "market": 0.58, "regime": 0.42}),
    AblationConfig("no_market",   {"astro": 0.62, "market": 0.00, "regime": 0.38}),
    AblationConfig("no_regime",   {"astro": 0.53, "market": 0.47, "regime": 0.00}),
    AblationConfig("astro_only",  {"astro": 1.0,  "market": 0.0,  "regime": 0.0}),
    AblationConfig("market_only", {"astro": 0.0,  "market": 1.0,  "regime": 0.0}),
    AblationConfig("regime_only", {"astro": 0.0,  "market": 0.0,  "regime": 1.0}),
    AblationConfig("equal",       {"astro": 1.0,  "market": 1.0,  "regime": 1.0}),
]


def _ablation_context(ctx: AstrotradeContext, weights: dict[str, float]) -> AstrotradeContext:
    """Return a copy of ctx with a SimilarityEngine using the given weights and
    a cleared calibrator dict — calibrators must be refit per ablation."""
    engine = SimilarityEngine(ctx.state_matrix, group_weights=weights)
    return replace(ctx, engine=engine, calibrators={})


def _hit_rate(p_up: np.ndarray, actual_up: np.ndarray, conf: np.ndarray, threshold: float):
    decisive = p_up != 0.5
    mask = (conf >= threshold) & decisive
    if not mask.any():
        return float("nan"), 0
    pred_sign = np.sign(p_up[mask] - 0.5)
    actual_sign = np.where(actual_up[mask] > 0, 1, -1)
    return float(np.mean(pred_sign == actual_sign)), int(mask.sum())


def _evaluate(
    test_rows: pd.DataFrame, confidence_threshold: float
) -> dict:
    """Compute the comparison-row metrics for one ablation config."""
    p_up = test_rows["p_up"].to_numpy()
    p_raw = test_rows["p_up_raw"].to_numpy()
    y = test_rows["actual_up"].to_numpy()
    conf = test_rows["confidence"].to_numpy()

    hit30, n30 = _hit_rate(p_up, y, conf, 0.30)
    eq = naive_strategy_equity(test_rows, confidence_threshold=confidence_threshold)
    s = strategy_summary(eq)

    return {
        "n_test": len(test_rows),
        "brier_raw": brier_score(p_raw, y),
        "brier_cal": brier_score(p_up, y),
        "log_loss_cal": log_loss(p_up, y),
        "ece_cal": expected_calibration_error(p_up, y),
        "hit_rate_conf30": hit30,
        "n_conf30": n30,
        "active_share": s["active_share"],
        "sharpe": s["sharpe"],
        "total_logret": s["total_logret"],
    }


def run_ablation(
    ctx: AstrotradeContext,
    train_start: str,
    train_end: str,
    test_start: str,
    test_end: str | None = None,
    horizon: int = 5,
    top_n: int = 50,
    stride: int = 1,
    method: str = "isotonic",
    confidence_threshold: float = 0.20,
    configs: Iterable[AblationConfig] | None = None,
    progress_callback=None,
) -> pd.DataFrame:
    """Run all ablations, return one DataFrame row per config.

    progress_callback receives (config_name, phase, done, total) where phase is
    'train' or 'test'.
    """
    configs = list(configs or STANDARD_ABLATIONS)
    cal_class = IsotonicCalibrator if method == "isotonic" else PlattCalibrator
    rows: list[dict] = []

    for cfg in configs:
        log.info("ablation: %s weights=%s", cfg.name, cfg.weights)
        sub_ctx = _ablation_context(ctx, cfg.normalized())

        train_rows = walk_forward(
            sub_ctx,
            horizon=horizon,
            start=train_start,
            end=train_end,
            top_n=top_n,
            stride=stride,
            progress_callback=lambda d, t, _name=cfg.name: (
                progress_callback(_name, "train", d, t) if progress_callback else None
            ),
        )
        if train_rows.empty:
            raise RuntimeError(f"ablation {cfg.name!r}: empty training rows")

        cal = cal_class.fit(
            train_rows["p_up_raw"].to_numpy(),
            train_rows["actual_up"].to_numpy(),
            horizon=horizon,
            symbol=ctx.symbol,
        )
        sub_ctx = sub_ctx.attach_calibrator(cal)

        test_rows = walk_forward(
            sub_ctx,
            horizon=horizon,
            start=test_start,
            end=test_end,
            top_n=top_n,
            stride=stride,
            progress_callback=lambda d, t, _name=cfg.name: (
                progress_callback(_name, "test", d, t) if progress_callback else None
            ),
        )
        if test_rows.empty:
            raise RuntimeError(f"ablation {cfg.name!r}: empty test rows")

        metrics = _evaluate(test_rows, confidence_threshold)
        metrics.update(
            config=cfg.name,
            **{f"w_{k}": v for k, v in cfg.normalized().items()},
        )
        rows.append(metrics)

    df = pd.DataFrame(rows)

    # Order columns sensibly with config first.
    cols = ["config"] + [c for c in df.columns if c != "config"]
    df = df[cols]

    # Δ vs 'full' for the headline metrics — that's the "did this group help?" signal.
    if "full" in df["config"].values:
        full = df.loc[df["config"] == "full"].iloc[0]
        df["dbrier_vs_full"] = df["brier_cal"] - full["brier_cal"]
        df["dlogloss_vs_full"] = df["log_loss_cal"] - full["log_loss_cal"]
        df["dhit30_vs_full"] = df["hit_rate_conf30"] - full["hit_rate_conf30"]

    return df


def print_comparison(df: pd.DataFrame) -> None:
    """Pretty-print the ablation comparison table."""
    print(f"\n=== ABLATION STUDY :: configs={len(df)} ===")
    show = df.copy()
    fmt_pct = lambda x: f"{x*100:+.2f}pp" if pd.notna(x) else "  n/a"  # noqa: E731
    fmt_4 = lambda x: f"{x:.4f}" if pd.notna(x) else "  n/a"  # noqa: E731
    fmt_3 = lambda x: f"{x:.3f}" if pd.notna(x) else "  n/a"  # noqa: E731
    fmt_2 = lambda x: f"{x:+.2f}" if pd.notna(x) else "  n/a"  # noqa: E731

    for c in ("brier_cal", "log_loss_cal", "ece_cal", "brier_raw"):
        show[c] = show[c].map(fmt_4)
    for c in ("hit_rate_conf30", "active_share"):
        show[c] = show[c].map(fmt_3)
    for c in ("sharpe", "total_logret"):
        show[c] = show[c].map(fmt_2)

    if "dbrier_vs_full" in show.columns:
        show["dbrier_vs_full"] = df["dbrier_vs_full"].map(fmt_4)
        show["dlogloss_vs_full"] = df["dlogloss_vs_full"].map(fmt_4)
        show["dhit30_vs_full"] = df["dhit30_vs_full"].map(fmt_pct)

    cols = [
        "config",
        "w_astro", "w_market", "w_regime",
        "brier_cal", "log_loss_cal", "ece_cal",
        "hit_rate_conf30", "n_conf30",
        "sharpe", "active_share",
    ]
    if "dbrier_vs_full" in show.columns:
        cols += ["dbrier_vs_full", "dhit30_vs_full"]

    show = show[[c for c in cols if c in show.columns]]
    # Format the weight columns
    for c in ("w_astro", "w_market", "w_regime"):
        show[c] = df[c].map(lambda v: f"{v:.2f}")
    print(show.to_string(index=False))

    print(
        "\nreading guide:\n"
        "  dbrier_vs_full > 0  → that ablation is WORSE than the full model → the "
        "removed group HELPED.\n"
        "  dbrier_vs_full < 0  → that ablation is BETTER than the full model → the "
        "removed group HURT (or was noise).\n"
        "  Compare *_only configs to see each group's standalone contribution above "
        "base-rate parity (Brier ≈ 0.235)."
    )
