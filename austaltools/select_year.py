#!/bin/env python3
# -*- coding: utf-8 -*-
"""
Selection of a representative year from a multi-year meteorological
time series, following VDI 3783 Part 20 [VDI3783p20]_.

A *representative year* is a twelve-month period
(typically a calendar year) that best represents the
mean meteorological conditions of a
multi-year period at a measuring station.

Three methods are provided:

* :func:`method_A` – AKJahr
  (:math:`\\chi^2` and :math:`\\sigma`-environment,
  VDI 3783 Part 20, Annex A3.1).
  For Details see see :func:`austaltools.select_year.method_A`
* :func:`method_B` – selection from meteorological time series
  (VDI 3783 Part 20, Annex A3.2).
  For Details see see :func:`austaltools.select_year.method_B`
* :func:`method_T` – selection based on temperature
  annual cycle.
  This is an extra method to find years that were not
  exeptionally warm or cold in parst or as a whole.

"""
import logging
import os
import sys

import numpy as np
import pandas as pd

from . import _datasets
from . import _tools
from ._metadata import __version__
from . import _windutil
from . import input_weather

logger = logging.getLogger(__name__)

SELECT_YEAR_PICKLE = 'select_year.pkl'


# ---------------------------------------------------------------------------
# helpers

def _classify_direction(dd: pd.Series, n_sectors: int = 12) -> pd.Series:
    """
    Classify wind direction into equidistant sectors (0-based).

    Each sector has width :math:`360° / n_{\\text{sectors}}`.  Sector 0 is
    centred on North (0°).  ``NaN`` values are mapped to ``-1`` and are
    therefore absent from any ``range(n_sectors)`` reindex.

    :param dd: Wind direction in degrees (0–360).
    :type dd: pandas.Series
    :param n_sectors: Number of sectors (default 12 → 30° each).
    :type n_sectors: int
    :returns: Integer sector indices; ``-1`` for missing values.
    :rtype: pandas.Series
    """
    sector_width = 360.0 / n_sectors
    class_no = (((dd + sector_width / 2.0) % 360) // sector_width)
    return class_no.mask(np.isnan(class_no), -1).astype(int)

# ---------------------------------------------------------------------------

def _classify_speed(ff: pd.Series, edges: np.ndarray) -> pd.Series:
    """
    Classify wind speed into bins defined by *edges*.

    Bin *k* covers :math:`\\text{edges}[k] \\le u < \\text{edges}[k+1]`.
    The last bin is right-open (catches all values above the last edge).
    ``NaN`` values are mapped to ``-1``.

    :param ff: Wind speed in m/s.
    :type ff: pandas.Series
    :param edges: Monotonically increasing bin boundaries including 0 as
        the first element.
    :type edges: numpy.ndarray
    :returns: Integer bin indices (0-based); ``-1`` for missing values.
    :rtype: pandas.Series
    """
    nan_mask = ff.isna()
    raw = np.searchsorted(edges[1:], ff.fillna(0).values, side="right")
    class_no = pd.Series(raw, index=ff.index, dtype=int)
    class_no[nan_mask] = -1
    return class_no

# ---------------------------------------------------------------------------

def _classify_km(km: pd.Series) -> pd.Series:
    """
    Pass through Klug/Manier stability classes (integer 1–6) unchanged.

    ``NaN`` values are mapped to ``-1`` and are therefore absent from any
    ``range(1, 7)`` reindex.

    :param km: Klug/Manier stability class (1–6).
    :type km: pandas.Series
    :returns: Integer stability classes; ``-1`` for missing values.
    :rtype: pandas.Series
    """
    nan_mask = km.isna()
    class_no = km.fillna(-1).astype(int)
    return class_no

# ---------------------------------------------------------------------------

def _freq_abs(series: pd.Series, classes: range) -> pd.Series:
    """
    Absolute frequency (hours) per class.

    Values not in *classes* (e.g. the sentinel ``-1``) are silently
    ignored because :pymeth:`pandas.Series.reindex` fills missing keys
    with zero.

    :param series: Classified integer time series.
    :type series: pandas.Series
    :param classes: Expected class labels to include in the output.
    :type classes: range
    :returns: Absolute counts indexed by class label.
    :rtype: pandas.Series
    """
    return series.value_counts().reindex(classes, fill_value=0).astype(float)


# ---------------------------------------------------------------------------

def _chi2_term(
    x_abs: pd.Series,      # absolute freq of individual year
    Mx_abs: pd.Series,     # multi-year mean absolute freq
    Mx_rel: pd.Series,     # multi-year mean relative freq
) -> float:
    """
    Weighted :math:`\\chi^2` deviation term for one parameter (Eq. A1).

    .. math::

        \\chi^2_i = \\sum_{j=1}^{m}
            \\frac{(x_{i,j,\\mathrm{abs}} - Mx_{i,j,\\mathrm{abs}})^2}
                  {Mx_{i,j,\\mathrm{abs}}}
            \\cdot Mx_{i,j,\\mathrm{rel}}

    Classes where :math:`Mx_{i,j,\\mathrm{abs}} = 0` are skipped
    (undefined denominator).

    :param x_abs: Absolute frequency per class for the individual year.
    :type x_abs: pandas.Series
    :param Mx_abs: Multi-year mean absolute frequency per class.
    :type Mx_abs: pandas.Series
    :param Mx_rel: Relative share of *Mx_abs* in the total annual hours.
    :type Mx_rel: pandas.Series
    :returns: Scalar :math:`\\chi^2_i` value.
    :rtype: float
    """
    mask = Mx_abs > 0
    diff = x_abs[mask] - Mx_abs[mask]
    return float(np.sum((diff ** 2 / Mx_abs[mask]) * Mx_rel[mask]))


# ---------------------------------------------------------------------------

def _sigma_hits(
    x: pd.Series,          # value for individual year (abs or rel)
    Mx: pd.Series,         # multi-year mean
    sigma: pd.Series,      # multi-year std dev
) -> int:
    """
    Count classes inside the :math:`\\sigma`-environment (Eq. A3).

    A class *j* is a *hit* when the individual-year value lies strictly
    within one standard deviation of the multi-year mean:

    .. math::

        (Mx_{i,j} - \\sigma_{i,j}) < x_{i,j} < (Mx_{i,j} + \\sigma_{i,j})

    :param x: Per-class value for the individual year (absolute or
        relative frequency).
    :type x: pandas.Series
    :param Mx: Multi-year mean per class.
    :type Mx: pandas.Series
    :param sigma: Multi-year standard deviation per class.
    :type sigma: pandas.Series
    :returns: Number of classes that satisfy Eq. A3.
    :rtype: int
    """
    inside = (x > (Mx - sigma)) & (x < (Mx + sigma))
    return int(inside.sum())


# ---------------------------------------------------------------------------
# main functions

def method_A(
    df: pd.DataFrame,
    n_dir_sectors: int = 12,
    speed_edges: np.ndarray | None = None,
    n_speed_classes: int = 10,
    # Weightings G_i (Eq. A2)
    G1_dir: float = 0.36,      # wind direction distribution
    G2_noc: float = 0.15,      # nocturnal & weak wind distribution
    G3_spd: float = 0.24,      # wind speed
    G4_ak:  float = 0.25,      # dispersion class (AK / Klug-Manier)
    # Nocturnal / weak-wind filter
    nocturnal_hours: tuple[int, int] = (18, 6),   # UTC: 18:00 – 06:00
    weak_wind_threshold: float = 2.0,             # m/s  (≤ threshold)
) -> tuple[int, pd.DataFrame, pd.DataFrame]:
    """
    Select a representative year using Method A – AKJahr.

    Implements VDI 3783 Part 20, Annex A3.1.  For each candidate year
    the method evaluates four parameters against their multi-year means:

    * :math:`i=1` – wind-direction distribution (30° sectors)
    * :math:`i=2` – nocturnal and weak-wind direction distribution
      (18:00–06:00 UTC, :math:`u \\le u_{\\text{weak}}`)
    * :math:`i=3` – wind-speed distribution
    * :math:`i=4` – dispersion-class (Klug/Manier) distribution

    **Weighted** :math:`\\chi^2` **term** (Eq. A1)

    .. math::

        \\chi^2_i = \\sum_{j=1}^{m}
            \\frac{(x_{i,j,\\mathrm{abs}} - Mx_{i,j,\\mathrm{abs}})^2}
                  {Mx_{i,j,\\mathrm{abs}}}
            \\cdot Mx_{i,j,\\mathrm{rel}}

    **Total** :math:`\\chi^2` **(Eq. A2)**

    .. math::

        \\chi^2 = \\sum_{i=1}^{4} \\chi^2_i \\cdot G_i

    with default weightings
    :math:`G_1 = 0.36,\\; G_2 = 0.15,\\; G_3 = 0.24,\\; G_4 = 0.25`.

    **Sigma-environment hit ratio (Eq. A3 / A4)**

    A class *j* of parameter *i* is a *hit* if

    .. math::

        Mx_{i,j} - \\sigma_{i,j} < x_{i,j} < Mx_{i,j} + \\sigma_{i,j}

    The total hit ratio is

    .. math::

        TQ = \\sum_{i=1}^{4} TQ_i \\cdot G_i

    **Selection criteria (applied in order)**

    a. Rank 1 in :math:`\\chi^2` **and** rank 1 in :math:`TQ`.
    b. Rank 1 in :math:`\\chi^2` and rank 2 or 3 in :math:`TQ`.
    c. Rank 2 or 3 in :math:`\\chi^2` and in the top-3 of :math:`TQ`.
    d. Fallback: best :math:`\\chi^2` among the top-3 :math:`TQ` years.

    :param df: Hourly time series with a :class:`pandas.DatetimeIndex`
        and columns ``FF`` (wind speed, m/s), ``DD`` (wind direction, °),
        ``KM`` (Klug/Manier stability class, integer 1–6).
    :type df: pandas.DataFrame
    :param n_dir_sectors: Number of equidistant wind-direction sectors.
        Default 12 (→ 30° each).
    :type n_dir_sectors: int
    :param speed_edges: Right bin edges for wind-speed classes (m/s).
        ``None`` → *n_speed_classes* equidistant classes up to the
        overall maximum.
    :type speed_edges: numpy.ndarray or None
    :param n_speed_classes: Number of auto-generated speed classes;
        used only when *speed_edges* is ``None``.
    :type n_speed_classes: int
    :param G1_dir: Weighting for the wind-direction parameter
        (:math:`G_1`, default 0.36).
    :type G1_dir: float
    :param G2_noc: Weighting for the nocturnal/weak-wind parameter
        (:math:`G_2`, default 0.15).
    :type G2_noc: float
    :param G3_spd: Weighting for the wind-speed parameter
        (:math:`G_3`, default 0.24).
    :type G3_spd: float
    :param G4_ak: Weighting for the dispersion-class parameter
        (:math:`G_4`, default 0.25).
    :type G4_ak: float
    :param nocturnal_hours: ``(start_hour, end_hour)`` UTC defining the
        nocturnal period (default ``(18, 6)`` → 18:00–06:00 UTC).
    :type nocturnal_hours: tuple[int, int]
    :param weak_wind_threshold: Upper wind-speed limit (m/s, inclusive)
        for the nocturnal/weak-wind filter (default 2.0 m/s).
    :type weak_wind_threshold: float
    :returns: A 3-tuple ``(representative_year, ranking_chi2,
        ranking_sigma)`` where

        * *representative_year* – selected calendar year (int)
        * *ranking_chi2* – :class:`pandas.DataFrame` indexed by year,
          sorted ascending by ``chi2_total`` (lower is better), with
          per-parameter and total :math:`\\chi^2` columns
        * *ranking_sigma* – :class:`pandas.DataFrame` indexed by year,
          sorted descending by ``TQ_total`` (higher is better), with
          per-parameter and total :math:`TQ` columns

    :rtype: tuple[int, pandas.DataFrame, pandas.DataFrame]
    """
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    years = sorted(df.index.year.unique())

    # ------------------------------------------------------------------
    # 0. Build speed bins
    # ------------------------------------------------------------------
    if speed_edges is None:
        ff_max = df["FF"].max()
        speed_edges = np.linspace(0, ff_max, n_speed_classes + 1)
    else:
        speed_edges = np.asarray(speed_edges)
        if speed_edges[0] != 0:
            speed_edges = np.r_[0.0, speed_edges]

    n_spd_cls = len(speed_edges) - 1
    dir_classes   = range(n_dir_sectors)
    speed_classes = range(n_spd_cls)
    km_classes    = range(1, 7)   # Klug/Manier: 1…6

    # ------------------------------------------------------------------
    # 1. Classify all data
    # ------------------------------------------------------------------
    dir_sec   = _classify_direction(df["DD"], n_dir_sectors)
    spd_sec   = _classify_speed(df["FF"], speed_edges)
    km_sec    = _classify_km(df["KM"])

    # Nocturnal & weak-wind mask: 18:00–06:00 UTC AND FF ≤ threshold
    hour = df.index.hour
    noc_mask = (
        ((hour >= nocturnal_hours[0]) | (hour < nocturnal_hours[1]))
        & (df["FF"] <= weak_wind_threshold)
    )
    dir_sec_noc = dir_sec[noc_mask & (dir_sec >= 0)]

    # ------------------------------------------------------------------
    # 2. Multi-year MEAN absolute and relative frequencies per class
    # ------------------------------------------------------------------
    n_years = len(years)

    def _multiyear_stats(series: pd.Series, classes) -> tuple[pd.Series, pd.Series, pd.Series]:
        """
        Compute multi-year mean, relative frequency, and standard deviation.

        Values equal to ``-1`` (NaN sentinel) are excluded because they
        are absent from *classes*.

        :returns: ``(Mx_abs, Mx_rel, sigma)`` where

            * *Mx_abs* – mean absolute frequency (h/yr) per class
            * *Mx_rel* – :math:`Mx_{\\mathrm{abs}} / \\sum Mx_{\\mathrm{abs}}`
            * *sigma*  – sample standard deviation across years (ddof=1)
        """
        yearly = pd.DataFrame(
            {yr: _freq_abs(series[df.index.year == yr] if series is not dir_sec_noc
                           else series[series.index.year == yr], classes)
             for yr in years}
        ).T  # shape (n_years, n_classes)

        Mx_abs   = yearly.mean()
        sigma    = yearly.std(ddof=1)
        total_h  = Mx_abs.sum()
        Mx_rel   = Mx_abs / total_h if total_h > 0 else Mx_abs * 0
        return Mx_abs, Mx_rel, sigma

    # helper for nocturnal series (its own year-mask)
    def _multiyear_stats_noc(classes) -> tuple[pd.Series, pd.Series, pd.Series]:
        yearly = pd.DataFrame(
            {yr: _freq_abs(dir_sec_noc[dir_sec_noc.index.year == yr], classes)
             for yr in years}
        ).T
        Mx_abs  = yearly.mean()
        sigma   = yearly.std(ddof=1)
        total_h = Mx_abs.sum()
        Mx_rel  = Mx_abs / total_h if total_h > 0 else Mx_abs * 0
        return Mx_abs, Mx_rel, sigma

    # values in the classification timeseries that are -1
    # are disregarded since -1 is not included in *_classes
    Mx_dir_abs,   Mx_dir_rel,   sigma_dir   = _multiyear_stats(dir_sec,     dir_classes)
    Mx_noc_abs,   Mx_noc_rel,   sigma_noc   = _multiyear_stats_noc(dir_classes)
    Mx_spd_abs,   Mx_spd_rel,   sigma_spd   = _multiyear_stats(spd_sec,     speed_classes)
    Mx_km_abs,    Mx_km_rel,    sigma_km    = _multiyear_stats(km_sec,      km_classes)

    # ------------------------------------------------------------------
    # 3. Per-year χ² terms and sigma hits  (Eq. A1 – A4)
    # ------------------------------------------------------------------
    chi2_dir_yr  = {}
    chi2_noc_yr  = {}
    chi2_spd_yr  = {}
    chi2_km_yr   = {}
    chi2_total   = {}

    TQ_dir_yr    = {}
    TQ_noc_yr    = {}
    TQ_spd_yr    = {}
    TQ_km_yr     = {}
    TQ_total     = {}

    for yr in years:
        mask_yr = df.index.year == yr

        # values in the classification timeseries that are -1
        # are disregarded since -1 is not included in *_classes
        x_dir = _freq_abs(dir_sec[mask_yr],                            dir_classes)
        x_noc = _freq_abs(dir_sec_noc[dir_sec_noc.index.year == yr],   dir_classes)
        x_spd = _freq_abs(spd_sec[mask_yr],                            speed_classes)
        x_km  = _freq_abs(km_sec[mask_yr],                             km_classes)

        # --- χ² (Eq. A1) ---
        c1 = _chi2_term(x_dir, Mx_dir_abs, Mx_dir_rel)
        c2 = _chi2_term(x_noc, Mx_noc_abs, Mx_noc_rel)
        c3 = _chi2_term(x_spd, Mx_spd_abs, Mx_spd_rel)
        c4 = _chi2_term(x_km,  Mx_km_abs,  Mx_km_rel)

        chi2_dir_yr[yr] = c1
        chi2_noc_yr[yr] = c2
        chi2_spd_yr[yr] = c3
        chi2_km_yr[yr]  = c4

        # Eq. A2: total χ²
        chi2_total[yr] = G1_dir * c1 + G2_noc * c2 + G3_spd * c3 + G4_ak * c4

        # --- sigma hits (Eq. A3) ---
        h1 = _sigma_hits(x_dir, Mx_dir_abs, sigma_dir)
        h2 = _sigma_hits(x_noc, Mx_noc_abs, sigma_noc)
        h3 = _sigma_hits(x_spd, Mx_spd_abs, sigma_spd)
        h4 = _sigma_hits(x_km,  Mx_km_abs,  sigma_km)

        TQ_dir_yr[yr] = h1
        TQ_noc_yr[yr] = h2
        TQ_spd_yr[yr] = h3
        TQ_km_yr[yr]  = h4

        # Eq. A4: total hit ratio
        TQ_total[yr] = G1_dir * h1 + G2_noc * h2 + G3_spd * h3 + G4_ak * h4

    chi2_s = pd.Series(chi2_total, name="chi2_total")
    TQ_s   = pd.Series(TQ_total,   name="TQ_total")

    # ------------------------------------------------------------------
    # 4. Build ranking tables
    # ------------------------------------------------------------------
    ranking_chi2 = pd.DataFrame({
        "chi2_dir":   pd.Series(chi2_dir_yr),
        "chi2_noc":   pd.Series(chi2_noc_yr),
        "chi2_spd":   pd.Series(chi2_spd_yr),
        "chi2_km":    pd.Series(chi2_km_yr),
        "chi2_total": chi2_s,
    }).sort_values("chi2_total").round(4)

    ranking_sigma = pd.DataFrame({
        "TQ_dir":   pd.Series(TQ_dir_yr),
        "TQ_noc":   pd.Series(TQ_noc_yr),
        "TQ_spd":   pd.Series(TQ_spd_yr),
        "TQ_km":    pd.Series(TQ_km_yr),
        "TQ_total": TQ_s,
    }).sort_values("TQ_total", ascending=False).round(4)

    # ------------------------------------------------------------------
    # 5. Selection logic (criteria a → b → c → fallback)
    # ------------------------------------------------------------------
    chi2_rank  = {yr: r + 1 for r, yr in enumerate(ranking_chi2.index)}
    sigma_rank = {yr: r + 1 for r, yr in enumerate(ranking_sigma.index)}
    # top-3 in sigma environment
    top3_sigma = set(list(ranking_sigma.index)[:3])

    rep_year = None

    # criterion a: rank 1 in both χ² and sigma
    yr_chi2_1 = ranking_chi2.index[0]
    if sigma_rank[yr_chi2_1] == 1:
        rep_year = yr_chi2_1
        logger.info(f"Criterion (a): year {rep_year} is rank 1 in χ² AND rank 1 in sigma → selected.")

    # criterion b: rank 1 in χ², rank 2 or 3 in sigma
    if rep_year is None:
        if yr_chi2_1 in top3_sigma:
            rep_year = yr_chi2_1
            logger.info(
                f"Criterion (b): year {rep_year} is rank 1 in χ², "
                f"rank {sigma_rank[yr_chi2_1]} in sigma → selected."
            )

    # criterion c: rank 2 or 3 in χ² AND in top-3 sigma
    if rep_year is None:
        for yr in list(ranking_chi2.index)[1:3]:
            if yr in top3_sigma:
                rep_year = yr
                logger.info(
                    f"Criterion (c): year {rep_year} is rank {chi2_rank[yr]} in χ², "
                    f"rank {sigma_rank[yr]} in sigma → selected."
                )
                break

    # fallback: best χ² among top-3 sigma (best wind-direction + AK agreement)
    if rep_year is None:
        candidates = [yr for yr in ranking_chi2.index if yr in top3_sigma]
        if candidates:
            rep_year = candidates[0]
            logger.info(
                f"Fallback: no year met criteria a-c; "
                f"year {rep_year} chosen from top-3 sigma with best χ²."
            )
        else:
            rep_year = int(ranking_chi2.index[0])
            logger.info(
                f"Fallback (last resort): year {rep_year} chosen as rank-1 χ² "
                f"(no overlap between top-3 χ² and top-3 sigma)."
            )

    return rep_year, ranking_chi2, ranking_sigma

# -------------------------------------------------------------------------

def method_B(
    df: pd.DataFrame,
    n_dir_sectors: int = 12,          # 30° sectors  → 360/30 = 12
    speed_classes: list[float] | None = None,  # right edges in m/s; None → equidistant auto
    n_speed_classes: int = 10,         # used only when speed_classes is None
    weight_dir: float = 3.0,
    weight_speed: float = 1.0,
) -> tuple[int, pd.DataFrame]:
    """
    Select a representative year using Method B – time-series comparison.

    Implements VDI 3783 Part 20, Annex A3.2.  The method compares the
    wind-direction and wind-speed frequency distributions of each
    individual year against the multi-year total, then ranks years by a
    weighted deviation score.

    **Deviation measure (Eq. A5)**

    For parameter :math:`i` (1 = wind direction, 2 = wind speed) and
    individual year :math:`n`:

    .. math::

        A_{i,n} = \\sum_{j=1}^{m}
            \\left( x_{i,j,\\mathrm{rel}} - x_{i,j,n,\\mathrm{rel}} \\right)^2

    where :math:`x_{i,j,\\mathrm{rel}}` is the relative frequency of
    class *j* over the entire multi-year period and
    :math:`x_{i,j,n,\\mathrm{rel}}` is the corresponding value for
    year *n*.  Only valid (non-NaN) hours enter both denominators.

    Each :math:`A_{i,n}` is then normalised so that the minimum across
    all years equals 100.

    **Assessment variable (Eq. A6)**

    .. math::

        BG_n = \\frac{w_{\\mathrm{dir}}}{w_{\\mathrm{dir}}+w_{\\mathrm{spd}}}
               \\cdot A_{1,n}^{\\mathrm{norm}}
             + \\frac{w_{\\mathrm{spd}}}{w_{\\mathrm{dir}}+w_{\\mathrm{spd}}}
               \\cdot A_{2,n}^{\\mathrm{norm}}

    The year with the smallest :math:`BG_n` is the representative year.

    :param df: Hourly time series with a :class:`pandas.DatetimeIndex`
        and columns ``FF`` (wind speed, m/s), ``DD`` (wind direction, °).
        Column ``KM`` is accepted but not used by this method.
    :type df: pandas.DataFrame
    :param n_dir_sectors: Number of equidistant wind-direction sectors.
        Default 12 (→ 30° each).
    :type n_dir_sectors: int
    :param speed_classes: Right bin edges for wind-speed classes (m/s).
        ``None`` → *n_speed_classes* equidistant classes up to the
        overall maximum.
    :type speed_classes: list[float] or None
    :param n_speed_classes: Number of auto-generated speed classes;
        used only when *speed_classes* is ``None``.
    :type n_speed_classes: int
    :param weight_dir: Weight :math:`w_{\\mathrm{dir}}` for the
        wind-direction deviation (default 3.0).
    :type weight_dir: float
    :param weight_speed: Weight :math:`w_{\\mathrm{spd}}` for the
        wind-speed deviation (default 1.0).
    :type weight_speed: float
    :returns: A 2-tuple ``(representative_year, ranking)`` where

        * *representative_year* – selected calendar year (int)
        * *ranking* – :class:`pandas.DataFrame` indexed by year, sorted
          ascending by ``BG_n`` (lower is better), with columns
          ``A_dir_norm (→100)``, ``A_speed_norm (→100)``, ``BG_n``,
          and ``mean_FF_ms`` (annual mean wind speed, plausibility check)
    :rtype: tuple[int, pandas.DataFrame]
    """
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    years = sorted(df.index.year.unique())

    # ------------------------------------------------------------------
    # 1.  Build classification bins
    # ------------------------------------------------------------------
    # Wind direction: 12 sectors of 30° each, centred so that sector 1
    # covers 345°–15° (i.e. "North"), consistent with meteorological practice.
    # We shift DD by half a sector width before flooring.

    # Wind speed: equidistant or user-supplied classes
    if speed_classes is None:
        ff_max = df["FF"].max()
        edges = np.linspace(0, ff_max, n_speed_classes + 1)
    else:
        edges = np.array([0.0] + list(speed_classes))

    # keep full index, -1 values are simply absent from the valid classes range
    dir_sector = _classify_direction(df["DD"], n_dir_sectors)
    speed_sector = _classify_speed(df["FF"], edges)

    n_dir_classes = n_dir_sectors
    n_spd_classes = len(edges) - 1

    # ------------------------------------------------------------------
    # 2.  Multi-year (total) relative frequencies  x_{i,j,rel}
    # ------------------------------------------------------------------
    freq_dir_total = (
            dir_sector.value_counts()
            .reindex(range(n_dir_classes), fill_value=0)
            / (dir_sector >= 0).sum()  # denominator = valid hours only
    )
    freq_spd_total = (
            speed_sector.value_counts()
            .reindex(range(n_spd_classes), fill_value=0)
            / (speed_sector >= 0).sum()
    )

    # ------------------------------------------------------------------
    # 3.  Per-year relative frequencies and deviation measures  (Eq. A5)
    # ------------------------------------------------------------------
    A_dir   = {}
    A_speed = {}
    mean_speed_by_year = {}

    for yr in years:
        mask = df.index.year == yr
        n_yr_valid_dir = (dir_sector[mask] >= 0).sum()
        n_yr_valid_spd = (speed_sector[mask] >= 0).sum()

        freq_dir_yr = (
                dir_sector[mask].value_counts()
                .reindex(range(n_dir_classes), fill_value=0)
                / n_yr_valid_dir
        )
        freq_spd_yr = (
                speed_sector[mask].value_counts()
                .reindex(range(n_spd_classes), fill_value=0)
                / n_yr_valid_spd
        )

        # Eq. A5:  A_{i,n} = Σ_j ( x_{i,j,rel} − x_{i,j,n,rel} )²
        A_dir[yr]   = float(np.sum((freq_dir_total.values - freq_dir_yr.values) ** 2))
        A_speed[yr] = float(np.sum((freq_spd_total.values - freq_spd_yr.values) ** 2))

        mean_speed_by_year[yr] = float(df.loc[mask, "FF"].mean())

    A_dir   = pd.Series(A_dir,   name="A_dir_raw")
    A_speed = pd.Series(A_speed, name="A_speed_raw")

    # ------------------------------------------------------------------
    # 4.  Normalise each parameter independently to 100 for the minimum
    # ------------------------------------------------------------------
    A_dir_norm   = A_dir   / A_dir.min()   * 100.0
    A_speed_norm = A_speed / A_speed.min() * 100.0

    # ------------------------------------------------------------------
    # 5.  Weighted assessment variable BG_n  (Eq. A6)
    # ------------------------------------------------------------------
    w_total = weight_dir + weight_speed
    BG = (weight_dir / w_total) * A_dir_norm + (weight_speed / w_total) * A_speed_norm

    # ------------------------------------------------------------------
    # 6.  Rank and output
    # ------------------------------------------------------------------
    mean_speed_by_year = pd.Series(mean_speed_by_year, name="mean_FF_ms")
    mean_speed_total   = float(df["FF"].mean())

    ranking = pd.DataFrame({
        "A_dir_norm (→100)":   A_dir_norm.round(1),
        "A_speed_norm (→100)": A_speed_norm.round(1),
        "BG_n":                BG.round(1),
        "mean_FF_ms":          mean_speed_by_year.round(2),
    }).sort_values("BG_n")

    representative_year = int(ranking.index[0])

    return representative_year, ranking


# -------------------------------------------------------------------------

def method_T(
        df: pd.DataFrame,
        temp_col: str = "T",
) -> tuple[int, pd.DataFrame]:
    """
    Select a representative year using Method T – temperature annual cycle.

    The method compares the temperature annual cycle of each individual
    year against the multi-year mean annual cycle (MAC) using three
    complementary scores.

    **Step 1 – Daily means**

    Sub-daily values are aggregated to daily means
    :math:`T_{d,n}` for day *d* of year *n*.  Days where all values are
    missing are excluded.

    **Step 2 – Mean annual cycle (MAC)**

    .. math::

        \\overline{T}_{\\mathrm{doy}}
        = \\frac{1}{N_{\\mathrm{doy}}}
          \\sum_{n} T_{d(\\mathrm{doy}),n}

    where the average runs over all years that contain day-of-year
    *doy*.  Leap-day (DOY 366) is averaged only over leap years.

    **Step 3 – Per-year bias**

    .. math::

        b_n = \\frac{1}{D_n} \\sum_{d \\in n}
              \\left( T_{d,n} - \\overline{T}_{\\mathrm{doy}(d)} \\right)

    **Step 4 – RMS of bias-corrected daily anomalies**

    .. math::

        \\sigma_{\\mathrm{daily},n} = \\sqrt{
            \\frac{1}{D_n} \\sum_{d \\in n}
            \\left[
                \\left( T_{d,n} - \\overline{T}_{\\mathrm{doy}(d)} \\right)
                - b_n
            \\right]^2
        }

    **Step 5 – RMS of bias-corrected monthly-mean anomalies**

    Let :math:`\\bar{T}_{m,n}` be the mean of daily means in calendar
    month *m* of year *n*, and :math:`\\bar{T}_{m,n}^{\\mathrm{MAC}}`
    the corresponding mean of MAC values for the same days.  Then:

    .. math::

        \\sigma_{\\mathrm{monthly},n} = \\sqrt{
            \\frac{1}{12} \\sum_{m=1}^{12}
            \\left( \\bar{T}_{m,n} - \\bar{T}_{m,n}^{\\mathrm{MAC}} - b_n
            \\right)^2
        }

    **Step 6 – Ranking score**

    .. math::

        S_n = |b_n|
            + \\left| \\sigma_{\\mathrm{daily},n}
                      - \\min_n \\sigma_{\\mathrm{daily},n} \\right|
            + \\left| \\sigma_{\\mathrm{monthly},n}
                      - \\min_n \\sigma_{\\mathrm{monthly},n} \\right|

    The year with the smallest :math:`S_n` is the representative year.

    :param df: Time series with a :class:`pandas.DatetimeIndex` (hourly
        or finer) and a temperature column.
    :type df: pandas.DataFrame
    :param temp_col: Name of the temperature column (default ``'T'``).
        The unit (°C or K) does not affect the result.
    :type temp_col: str
    :returns: A 2-tuple ``(representative_year, ranking)`` where

        * *representative_year* – selected calendar year (int)
        * *ranking* – :class:`pandas.DataFrame` indexed by year, sorted
          ascending by ``score`` (:math:`S_n`), with columns ``bias``
          (:math:`b_n`), ``rms_daily`` (:math:`\\sigma_{\\mathrm{daily}}`),
          ``rms_monthly`` (:math:`\\sigma_{\\mathrm{monthly}}`), and
          ``score`` (:math:`S_n`)

    :rtype: tuple[int, pandas.DataFrame]
    :raises KeyError: If *temp_col* is not present in *df*.
    """
    df = df.copy()
    df.index = pd.to_datetime(df.index)

    if temp_col not in df.columns:
        raise KeyError(
            f"Temperature column '{temp_col}' not found in DataFrame. "
            f"Available columns: {list(df.columns)}")

    # ------------------------------------------------------------------
    # 1. Daily means
    # ------------------------------------------------------------------
    daily = (
        df[temp_col]
        .resample("D")
        .mean()  # NaN days if all values were NaN → handled below
    )
    daily = daily.dropna()

    daily_df = pd.DataFrame({
        "T": daily,
        "year": daily.index.year,
        "doy": daily.index.day_of_year,
        "month": daily.index.month,
    })

    years = sorted(daily_df["year"].unique())

    # ------------------------------------------------------------------
    # 2. Mean annual cycle  (average over all years per DOY)
    # ------------------------------------------------------------------
    mac = daily_df.groupby("doy")[
        "T"].mean()  # Series indexed by DOY 1-366

    # ------------------------------------------------------------------
    # 3 & 4. Per-year scores
    # ------------------------------------------------------------------
    records = {}
    for yr in years:
        yr_df = daily_df[daily_df["year"] == yr].copy()
        yr_df["mac"] = yr_df["doy"].map(mac)

        diff = yr_df["T"] - yr_df["mac"]

        # (2) mean bias
        bias = float(diff.mean())

        # (3) RMS of daily residuals
        rms_daily = float(np.sqrt(((diff - bias) ** 2).mean()))

        # (4) RMS of monthly-mean residuals
        monthly_T = yr_df.groupby("month")["T"].mean()
        # MAC monthly mean: average MAC values for days that fall in each
        # month of *this* year (accounts for leap-year Feb correctly)
        monthly_mac = yr_df.groupby("month")["mac"].mean()
        monthly_diff = monthly_T - monthly_mac - bias
        rms_monthly = float(np.sqrt((monthly_diff ** 2).mean()))


        records[yr] = {
            "bias": round(bias, 4),
            "rms_daily": round(rms_daily, 4),
            "rms_monthly": round(rms_monthly, 4),
        }

    ranking = pd.DataFrame.from_dict(records, orient="index")
    ranking["score"] = (
            abs(ranking['bias']) +
            abs(ranking['rms_daily'] - ranking['rms_daily'].min()) +
            abs(ranking['rms_monthly'] - ranking['rms_monthly'].min()))

    ranking = ranking.sort_values("score")
    ranking.index.name = "year"

    representative_year = int(ranking.index[0])
    return representative_year, ranking


# -------------------------------------------------------------------------

def main(args, return_only: bool = False):
    """
    Main entry point for the ``select-year`` sub-command.

    Loads or builds a multi-year meteorological DataFrame, dispatches to
    the requested method, and prints the selected year together with the
    ranking table(s).

    :param args: Command-line arguments as a dictionary.  Recognised keys:

        * ``working_dir`` *(str, default* ``'.'`` *)* – directory used
          for the intermediate pickle cache ``select_year.pkl``.
        * ``year`` *(str or None)* – year range such as ``'2010-2020'``;
          ``None`` uses the last 10 calendar years.
        * ``source`` *(str, required)* – weather-data source identifier.
        * ``method`` *(str, required)* – one of ``'a'``/``'akjahr'``,
          ``'b'``/``'timeseries'``, or ``'t'``/``'temperature'``.
        * ``prec`` *(bool, default* ``False`` *)* – precipitation flag
          passed to :func:`input_weather.austal_weather`.

    :type args: dict
    :raises ValueError: If ``source`` or ``method`` is missing or
        ``method`` is not a recognised value.
    :raises EnvironmentError: If no weather data can be located.
    """
    logger.debug(format(args))


    working_dir = args.get('working_dir', '.')

    yearstring = args.get('year', None)
    if yearstring is not None:
        years = _tools.expand_sequence(yearstring)
    else:
        years = [pd.Timestamp.now().year - x for x in reversed(range(1,11))]
    logger.info(f"using years: {format(years)}")

    source = args.get('source', None)
    if source is None:
        raise ValueError("argument `source` missing or empty")
    logger.info(f"using source: {source}")

    method = args.get('method', None)
    if method is None:
        raise ValueError("argument `method` missing or empty")
    if method.lower() in ['a', 'akjahr']:
        method = 'a'
    elif method.lower() in ['b', 'timeseries']:
        method = 'b'
    elif method.lower() in ['t', 'temperature']:
        method = 't'
    else:
        raise ValueError(f"unknown method: {str(method)}")

    if args.get('prec', None) is None:
        args['prec'] = False

    available_weather = _datasets.find_weather_data()
    if available_weather is None or len(available_weather) == 0:
        logger.warning("No available weather data in config file,"
                       "trying to search weather data. \n"
                       "Run configure_autaltools to collect the "
                       "available weather data infomation once.")
        available_weather = _datasets.find_weather_data()
        if len(available_weather) == 0:
            raise EnvironmentError("No available weather data found.")

    # load cache file if it exists and test if it matches
    if os.path.exists(SELECT_YEAR_PICKLE):
        logger.debug(f"cache file found: {SELECT_YEAR_PICKLE}")
        df = pd.read_pickle(SELECT_YEAR_PICKLE)
        test_attrs = []
        for x in ["dwd", "wmo", "gk", "ut", "ll", "years", "source",
                  "class-scheme", "wind-variant"]:
            test_attrs.append(df.attrs.get(x, None) == args.get(x, None))
        if all(test_attrs):
            logger.info(f"using data in cache file: {SELECT_YEAR_PICKLE}")
        else:
            logger.debug("chache file does not match")
            df = None
    else:
        df = None

    # if cache did not exist rd does not match: extract data
    if df is None:
        df_list = []
        n=0
        for year in years:
            n += 1
            logger.info(f"processing year: {year} ({n}/{len(years)})")
            ar = args.copy()
            ar['year'] = year
            df_list.append(
                input_weather.austal_weather(ar, return_data_frame=True)
            )
            del ar
        df = pd.concat(df_list)
        del df_list

        # save cache to file
        for x in ["dwd", "wmo", "gk", "ut", "ll", "years", "source",
                  "class-scheme", "wind-variant"]:
            df.attrs[x] = args.get(x,None)
        df.to_pickle(SELECT_YEAR_PICKLE)
        logger.info(f"saved data to cache file: {SELECT_YEAR_PICKLE}")

    if method == 'a':
        selected_year, ranking_chi2, ranking_sigma = method_A(df)
        rankings = {'chi2 ranking': ranking_chi2,
                    'sigma ranking': ranking_sigma}
    elif method == 'b':
        selected_year, ranking = method_B(df)
        rankings = {'ranking': ranking}
    elif method == 't':
        selected_year, ranking = method_T(df)
        rankings = {'ranking': ranking}
    else:
        raise RuntimeError(f"unknown method: {str(method)}")

    if not return_only:
        print("---------------------")

        for k, v in rankings.items():
            print(k)
            print()
            print(format(v))
            print("---------------------")

        print(f"selected year: {selected_year}")
        print("---------------------")

    return selected_year

# ----------------------------------------------------

def add_options(subparsers):

    known_sources = _datasets.SOURCES_WEATHER

    pars_syr = subparsers.add_parser(
        name='select-year',
        help='Select representative year according to '
             'VDI 3783 Part 20, Appendix A3',
        formatter_class=_tools.SmartFormatter,
    )
    pars_syr = _tools.add_location_opts(pars_syr, stations=True)
    pars_syr.add_argument('-m', '--method',
                          dest='method',
                          choices=['a', 'akjahr', 'b', 'timeseries',
                                   't', 'temperature'],
                          default='b',
                          help="Method for selecting a representative"
                               "year:\n"
                               "``a``/``akjahr``: method A"
                               " (chi^2 and sigma environment)\n"
                               "``b``/``timeseries``: method B"
                               " (from meteorological timesries)\n"
                               "``t``/``temperature``: method T"
                               " (representative by temperature)\n"
                               "For Details see the API description of "
                               "the module" + __name__ + ". "
                               "Defaults to %(default)s")
    pars_syr.add_argument('-s', '--source',
                        metavar="CODE",
                        nargs=None,
                        choices=known_sources,
                        default=known_sources[0],
                        help='select the source for the weather data. ' +
                             'Known ``CODE`` values are ' +
                             ' '.join(known_sources) +
                             ' Defaults to ' +
                             known_sources[0])
    pars_syr.add_argument('-y', '--year',
                         default=None,
                         help="range of years to select the representative"
                              " year from. Specify a range like "
                              " `1990-2000`."
                              " If not given, the last 10 years will be"
                              " used.")
    pars_syr.add_argument('-c', '--cache',
                          default=SELECT_YEAR_PICKLE,
                          help="Name for cache file. "
                               "This file stores the extraxted data "
                               "for all years, which allows to re-run "
                               "this program quicker if only -m/--method "
                               "or the output is changed. "
                               "The default is %(default)s.")
    input_weather.DEFAULT_CLASS_SCHEME = 'kms'
    pars_syr = input_weather.add_advanced_option_group(pars_syr)
    return subparsers