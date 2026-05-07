"""Ephemeris access via skyfield. Geocentric ecliptic longitudes for the classical bodies.

We compute heliocentric-style geocentric apparent longitude in degrees [0, 360) for:
Sun, Moon, Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune, Pluto.

Speeds (degrees/day) are derived numerically; sign of speed indicates retrograde.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from skyfield.api import Loader

from ..config import SETTINGS

log = logging.getLogger(__name__)

# de440s.bsp covers 1849–2150 in <40MB. Plenty for any back-test we care about.
EPHEMERIS_FILE = "de440s.bsp"

# de440s.bsp ships only barycenter entries for Mars and outward.
# Mercury/Venus/Moon are available as direct bodies; Earth-Moon barycenter
# is implicit. The mass-difference between a planet and its barycenter is
# astrologically negligible for our purposes.
BODIES: dict[str, str] = {
    "sun": "sun",
    "moon": "moon",
    "mercury": "mercury",
    "venus": "venus",
    "mars": "mars barycenter",
    "jupiter": "jupiter barycenter",
    "saturn": "saturn barycenter",
    "uranus": "uranus barycenter",
    "neptune": "neptune barycenter",
    "pluto": "pluto barycenter",
}


@lru_cache(maxsize=1)
def _loader_and_kernel():
    loader = Loader(str(SETTINGS.cache_dir))
    eph = loader(EPHEMERIS_FILE)
    ts = loader.timescale()
    earth = eph["earth"]
    return loader, eph, ts, earth


def _ecliptic_longitude(eph, earth, body_key: str, t) -> np.ndarray:
    body = eph[body_key]
    astrometric = earth.at(t).observe(body).apparent()
    # Ecliptic of date is the standard convention for Western astrology.
    _lat, lon, _dist = astrometric.ecliptic_latlon(epoch="date")
    return np.asarray(lon.degrees) % 360.0


def compute_positions(dates: Iterable[pd.Timestamp]) -> pd.DataFrame:
    """Return geocentric ecliptic longitude (deg) for each body at 21:00 UTC of each date.

    21:00 UTC ≈ US market close. Single sample per day is sufficient for daily-bar work.
    """
    _, eph, ts, earth = _loader_and_kernel()
    dates = pd.DatetimeIndex(dates)
    t = ts.utc(dates.year.values, dates.month.values, dates.day.values, 21)

    out = {}
    for name, key in BODIES.items():
        out[f"{name}_lon"] = _ecliptic_longitude(eph, earth, key, t)

    df = pd.DataFrame(out, index=dates)
    df.index.name = "date"
    # Speeds: numerical derivative in deg/day. Wrap-aware (handle 360→0 jumps).
    for name in BODIES:
        col = f"{name}_lon"
        diff = df[col].diff()
        # Unwrap the ±180 jumps caused by 0/360 boundary
        diff = ((diff + 180) % 360) - 180
        df[f"{name}_speed"] = diff
    df.iloc[0, df.columns.get_indexer([f"{n}_speed" for n in BODIES])] = 0.0
    return df


def cached_positions(dates: Iterable[pd.Timestamp], symbol_tag: str = "default") -> pd.DataFrame:
    """Disk-cached wrapper around compute_positions, keyed by (start, end, count)."""
    dates = pd.DatetimeIndex(dates)
    key = f"eph_{symbol_tag}_{dates.min().date()}_{dates.max().date()}_{len(dates)}.parquet"
    path: Path = SETTINGS.cache_dir / key
    if path.exists():
        return pd.read_parquet(path)
    df = compute_positions(dates)
    df.to_parquet(path)
    return df
