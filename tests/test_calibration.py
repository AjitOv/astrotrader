"""Calibration tests."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from astrotrader.backtest.metrics import brier_score, expected_calibration_error
from astrotrader.calibration.calibrator import (
    IsotonicCalibrator,
    PlattCalibrator,
    default_path,
    load_calibrator,
    save_calibrator,
)


@pytest.fixture
def biased_predictions():
    """Synthesize a miscalibrated source: predicted = true / 2 + noise.
    Truly perfect calibration is impossible, but a fitted calibrator should beat raw."""
    rng = np.random.default_rng(0)
    n = 5000
    true_p = rng.uniform(0.2, 0.8, size=n)
    actual = (rng.uniform(size=n) < true_p).astype(int)
    # Bias the predictions strongly: shrink toward 0.5
    p_raw = 0.5 + (true_p - 0.5) * 0.4 + rng.normal(0, 0.02, size=n)
    p_raw = np.clip(p_raw, 0.01, 0.99)
    return p_raw, actual


def test_isotonic_improves_brier(biased_predictions):
    p_raw, actual = biased_predictions
    cal = IsotonicCalibrator.fit(p_raw, actual, horizon=5, symbol="TEST")
    p_cal = cal.transform(p_raw)
    assert brier_score(p_cal, actual) < brier_score(p_raw, actual)
    assert expected_calibration_error(p_cal, actual) < expected_calibration_error(p_raw, actual)


def test_platt_improves_brier(biased_predictions):
    p_raw, actual = biased_predictions
    cal = PlattCalibrator.fit(p_raw, actual, horizon=5, symbol="TEST")
    p_cal = cal.transform(p_raw)
    assert brier_score(p_cal, actual) < brier_score(p_raw, actual)


def test_calibrator_output_bounds(biased_predictions):
    p_raw, actual = biased_predictions
    iso = IsotonicCalibrator.fit(p_raw, actual, horizon=5, symbol="TEST")
    platt = PlattCalibrator.fit(p_raw, actual, horizon=5, symbol="TEST")
    for cal in (iso, platt):
        out = cal.transform(np.array([0.0, 0.1, 0.5, 0.9, 1.0]))
        assert (out >= 0).all() and (out <= 1).all()


def test_save_load_roundtrip(tmp_path, biased_predictions):
    p_raw, actual = biased_predictions
    cal = IsotonicCalibrator.fit(p_raw, actual, horizon=5, symbol="TEST")
    path = save_calibrator(cal, tmp_path / "cal.joblib")
    loaded = load_calibrator(path)
    assert loaded.method == "isotonic"
    assert loaded.horizon == 5
    assert loaded.symbol == "TEST"
    np.testing.assert_allclose(loaded.transform(p_raw[:50]), cal.transform(p_raw[:50]))


def test_default_path_format():
    p = default_path("SPY", 5, "isotonic")
    assert p.name == "calibrator_SPY_h5_isotonic.joblib"


def test_score_carries_raw_and_calibrated(ctx):
    """Decide() with a calibrator must populate p_up, p_up_raw, calibrated correctly."""
    from astrotrader.pipeline import decide
    # Build a fake but valid calibrator (identity-ish, fit on a few points).
    rng = np.random.default_rng(0)
    n = 200
    p = rng.uniform(0.3, 0.7, size=n)
    y = (rng.uniform(size=n) < p).astype(int)
    cal = IsotonicCalibrator.fit(p, y, horizon=5, symbol="SPY")

    ctx_cal = ctx.attach_calibrator(cal)
    d_raw = decide(ctx, primary_horizon=5, top_n=30)
    d_cal = decide(ctx_cal, primary_horizon=5, top_n=30)

    assert d_raw.score.calibrated is False
    assert d_cal.score.calibrated is True
    assert d_raw.score.p_up == d_raw.score.p_up_raw
    # Calibration should not move p_up_raw between the two runs.
    assert d_cal.score.p_up_raw == d_raw.score.p_up_raw
    # And the calibrated probability is bounded
    assert 0.0 <= d_cal.score.p_up <= 1.0
    # p_down = 1 - p_up after calibration
    assert abs(d_cal.score.p_up + d_cal.score.p_down - 1.0) < 1e-9
