"""Ablation harness tests.

These run on the session-scoped SPY ctx. We use a tiny train/test window and
stride to keep test time bounded.
"""
from __future__ import annotations

import pandas as pd

from astrotrader.backtest.ablation import (
    AblationConfig,
    STANDARD_ABLATIONS,
    _ablation_context,
    run_ablation,
)


def test_ablation_config_normalizes() -> None:
    cfg = AblationConfig("x", {"astro": 2.0, "market": 1.0, "regime": 1.0})
    n = cfg.normalized()
    assert abs(sum(n.values()) - 1.0) < 1e-9
    assert n["astro"] == 0.5


def test_ablation_context_swaps_engine_and_clears_calibrators(ctx) -> None:
    sub = _ablation_context(ctx, {"astro": 0.0, "market": 1.0, "regime": 0.0})
    assert sub.engine is not ctx.engine
    assert sub.calibrators == {}
    # Original ctx must be untouched
    assert ctx.calibrators == {}  # ctx had none anyway, but the swap mustn't have leaked


def test_run_ablation_small_window(ctx) -> None:
    """End-to-end on a small training+test window with stride to stay fast."""
    configs = [
        AblationConfig("full",       {"astro": 0.40, "market": 0.35, "regime": 0.25}),
        AblationConfig("market_only", {"astro": 0.0, "market": 1.0, "regime": 0.0}),
    ]
    df = run_ablation(
        ctx,
        train_start="2014-01-01",
        train_end="2018-12-31",
        test_start="2019-01-01",
        test_end="2019-12-31",
        horizon=5,
        top_n=20,
        stride=10,
        method="platt",
        configs=configs,
    )
    assert len(df) == 2
    assert {"config", "brier_cal", "log_loss_cal", "ece_cal", "hit_rate_conf30"}.issubset(df.columns)
    assert (df["brier_cal"] >= 0).all() and (df["brier_cal"] <= 1).all()
    # Δ vs full computed
    assert "dbrier_vs_full" in df.columns
    assert df.loc[df["config"] == "full", "dbrier_vs_full"].iloc[0] == 0.0


def test_standard_ablations_have_distinct_weights() -> None:
    seen = set()
    for cfg in STANDARD_ABLATIONS:
        # Each named config must produce a unique weight vector
        normed = tuple(round(v, 4) for v in cfg.normalized().values())
        assert normed not in seen, f"duplicate weights in {cfg.name}"
        seen.add(normed)
