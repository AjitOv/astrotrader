"""Astro feature encoder.

Encodes raw planetary longitudes into a numeric feature vector:

  position features    sin(λ), cos(λ)              — wrap-safe; 0° == 360°
  retrograde features  sign(speed)                  — −1 / +1
  speed magnitude      |speed|                      — captures stations
  aspect features      cos(λ_a − λ_b − target)      — orb-aware via cos
  lunar phase          sin(φ), cos(φ) where φ = λ_moon − λ_sun
  fast cycles          phase position 0..1 for moon-mercury / moon-venus / etc.

The cos-of-aspect-deviation trick is important: for any aspect angle α,
cos(λ_a − λ_b − α) is +1 at exact aspect, −1 at opposite, smoothly weighted
in between — equivalent to a continuous orb function.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..data.ephemeris import BODIES

# Bodies we form aspects between. Outers move slowly; their aspects matter.
ASPECT_BODIES = ["sun", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto"]

# Major aspects in degrees. Conjunction, sextile, square, trine, opposition.
MAJOR_ASPECTS = {"conj": 0.0, "sex": 60.0, "sq": 90.0, "tri": 120.0, "opp": 180.0}


@dataclass(frozen=True)
class AstroFeatureSpec:
    use_minor_aspects: bool = False
    include_speed: bool = True


def _angle_diff(a: pd.Series, b: pd.Series) -> pd.Series:
    """Signed angular difference in [-180, 180]."""
    d = (a - b + 180.0) % 360.0 - 180.0
    return d


def encode_astro(positions: pd.DataFrame, spec: AstroFeatureSpec | None = None) -> pd.DataFrame:
    """Take ephemeris positions DataFrame, return a wide feature DataFrame."""
    spec = spec or AstroFeatureSpec()
    out = {}

    # 1. Position sin/cos and retrograde flags + speed magnitudes.
    for body in BODIES:
        lon = np.deg2rad(positions[f"{body}_lon"].values)
        out[f"astro_{body}_sin"] = np.sin(lon)
        out[f"astro_{body}_cos"] = np.cos(lon)

        if spec.include_speed:
            speed = positions[f"{body}_speed"].values
            # Sun and Moon never retrograde, so their sign carries no information; skip.
            if body not in ("sun", "moon"):
                out[f"astro_{body}_retro"] = np.sign(speed)
            out[f"astro_{body}_speed_mag"] = np.abs(speed)

    # 2. Aspects between slow/medium bodies. For each pair × aspect, encode cos-deviation.
    for i, a in enumerate(ASPECT_BODIES):
        for b in ASPECT_BODIES[i + 1 :]:
            diff = _angle_diff(positions[f"{a}_lon"], positions[f"{b}_lon"])
            for name, ang in MAJOR_ASPECTS.items():
                # cos of (diff − ang) peaks at +1 when exact, −1 when opposed-aspect.
                # Use 2× to give the function symmetry around the target.
                rad = np.deg2rad(diff - ang)
                out[f"asp_{a}_{b}_{name}"] = np.cos(rad).values

    # 3. Lunar phase from sun-moon separation.
    moon_phase = _angle_diff(positions["moon_lon"], positions["sun_lon"])
    phase_rad = np.deg2rad(moon_phase)
    out["astro_lunar_sin"] = np.sin(phase_rad).values
    out["astro_lunar_cos"] = np.cos(phase_rad).values
    out["astro_lunar_phase01"] = ((moon_phase % 360.0) / 360.0).values  # 0..1 cycle position

    # 4. Mercury–Sun synodic position (informative for fast cycles).
    merc_sun = _angle_diff(positions["mercury_lon"], positions["sun_lon"])
    out["astro_merc_sun_sin"] = np.sin(np.deg2rad(merc_sun)).values
    out["astro_merc_sun_cos"] = np.cos(np.deg2rad(merc_sun)).values

    df = pd.DataFrame(out, index=positions.index)
    return df
