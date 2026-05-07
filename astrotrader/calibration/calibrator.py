"""Probability calibration.

Two methods:
  isotonic — non-parametric monotonic mapping. Default. Uses sklearn.IsotonicRegression.
             Flexible enough to correct non-monotonic biases in the raw output.
  platt    — sigmoid(a · logit(p) + b). Two parameters, robust on small samples.

Calibrators are fit on a *training-window* DataFrame of (p_up_raw, actual_up) and
evaluated on a *disjoint* test window. Anything else is in-sample fitting and is
not informative about real performance.

Persistence: joblib pickle. Carries metadata so we can verify a saved calibrator
matches the symbol/horizon at load time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

import joblib
import numpy as np

from ..config import SETTINGS


@runtime_checkable
class Calibrator(Protocol):
    method: str
    horizon: int
    n_train: int
    symbol: str

    def transform(self, p: np.ndarray) -> np.ndarray: ...


@dataclass
class IsotonicCalibrator:
    horizon: int
    symbol: str
    n_train: int
    iso: object = None  # sklearn IsotonicRegression
    method: str = "isotonic"
    metadata: dict = field(default_factory=dict)

    def transform(self, p: np.ndarray) -> np.ndarray:
        p = np.asarray(p, dtype=float)
        return np.clip(self.iso.transform(p), 0.0, 1.0)

    @classmethod
    def fit(
        cls,
        p_raw: np.ndarray,
        actual_up: np.ndarray,
        horizon: int,
        symbol: str,
    ) -> "IsotonicCalibrator":
        from sklearn.isotonic import IsotonicRegression

        p_raw = np.asarray(p_raw, dtype=float)
        actual_up = np.asarray(actual_up, dtype=float)
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        iso.fit(p_raw, actual_up)
        return cls(
            horizon=horizon,
            symbol=symbol,
            n_train=len(p_raw),
            iso=iso,
        )


@dataclass
class PlattCalibrator:
    horizon: int
    symbol: str
    n_train: int
    a: float = 1.0
    b: float = 0.0
    method: str = "platt"
    metadata: dict = field(default_factory=dict)

    def transform(self, p: np.ndarray) -> np.ndarray:
        p = np.asarray(p, dtype=float)
        eps = 1e-9
        x = np.log(np.clip(p, eps, 1 - eps) / np.clip(1 - p, eps, 1 - eps))
        return 1.0 / (1.0 + np.exp(-(self.a * x + self.b)))

    @classmethod
    def fit(
        cls,
        p_raw: np.ndarray,
        actual_up: np.ndarray,
        horizon: int,
        symbol: str,
    ) -> "PlattCalibrator":
        from sklearn.linear_model import LogisticRegression

        p_raw = np.asarray(p_raw, dtype=float)
        actual_up = np.asarray(actual_up, dtype=int)
        eps = 1e-9
        x = np.log(np.clip(p_raw, eps, 1 - eps) / np.clip(1 - p_raw, eps, 1 - eps)).reshape(-1, 1)
        lr = LogisticRegression(C=1e6)  # near-unregularized; pure max-likelihood
        lr.fit(x, actual_up)
        return cls(
            horizon=horizon,
            symbol=symbol,
            n_train=len(p_raw),
            a=float(lr.coef_[0, 0]),
            b=float(lr.intercept_[0]),
        )


# ----------------------------------------------------------------- persistence


def default_path(symbol: str, horizon: int, method: str = "isotonic") -> Path:
    return SETTINGS.cache_dir / f"calibrator_{symbol.upper()}_h{horizon}_{method}.joblib"


def save_calibrator(cal: Calibrator, path: Path | None = None) -> Path:
    path = Path(path) if path else default_path(cal.symbol, cal.horizon, cal.method)
    joblib.dump(cal, path)
    return path


def load_calibrator(path: Path | str) -> Calibrator:
    cal = joblib.load(Path(path))
    if not isinstance(cal, (IsotonicCalibrator, PlattCalibrator)):
        raise ValueError(f"loaded object at {path} is not a Calibrator: {type(cal)}")
    return cal


def auto_load(
    symbol: str,
    horizon: int,
    method: str | None = None,
    methods_priority: tuple[str, ...] = ("platt", "isotonic"),
) -> Calibrator | None:
    """Return the best-available calibrator for (symbol, horizon).

    If `method` is given, only that one is tried. Otherwise we try the priority
    list in order — Platt first because the ablation showed it generalizes
    better than isotonic on weak-signal time-series data.
    """
    candidates = (method,) if method else methods_priority
    for m in candidates:
        path = default_path(symbol, horizon, m)
        if path.exists():
            return load_calibrator(path)
    return None
