#!/bin/env python3
# -*- coding: utf-8 -*-
"""
This module implements the selection of a
representative year according to
VDI 3783 Part 20 [VDI3783p20]_ .

``representative year`` is defined as
twelve-month period (typically a calendar year)
which represents optimally the mean wind conditions
of a multiyear period at a measuring station.
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


# ---------------------------------------------------------------------------
# helpers

def _classify_direction(dd: pd.Series, n_sectors: int = 12) -> pd.Series:
    """Classify wind direction into n_sectors equidistant 30° sectors (0-based)."""
    sector_width = 360.0 / n_sectors
    class_no = (((dd + sector_width / 2.0) % 360) // sector_width)
    return class_no.mask(np.isnan(class_no), -1).astype(int)

# ---------------------------------------------------------------------------

def _classify_speed(ff: pd.Series, edges: np.ndarray) -> pd.Series:
    nan_mask = ff.isna()
    raw = np.searchsorted(edges[1:], ff.fillna(0).values, side="right")
    class_no = pd.Series(raw, index=ff.index, dtype=int)
    class_no[nan_mask] = -1
    return class_no

# ---------------------------------------------------------------------------

def _classify_km(km: pd.Series) -> pd.Series:
    nan_mask = km.isna()
    class_no = km.fillna(-1).astype(int)
    return class_no

# ---------------------------------------------------------------------------

def _freq_abs(series: pd.Series, classes: range) -> pd.Series:
    """Absolute frequency (hours) per class."""
    return series.value_counts().reindex(classes, fill_value=0).astype(float)


# ---------------------------------------------------------------------------

def _chi2_term(
    x_abs: pd.Series,      # absolute freq of individual year
    Mx_abs: pd.Series,     # multi-year mean absolute freq
    Mx_rel: pd.Series,     # multi-year mean relative freq
) -> float:
    """
    chi² term  (Eq. A1)
    
    χ²_i = Σ_j  [(x_{i,j,abs} - Mx_{i,j,abs})² / Mx_{i,j,abs}]  ·  Mx_{i,j,rel}

    Classes where Mx_abs == 0 are skipped (undefined).
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
    sigma-environment hit ratio  (Eq. A3 / A4)

    Number of classes j where  Mx_j - σ_j < x_j < Mx_j + σ_j  (Eq. A3).
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
    Select a representative year from a multi-year hourly meteorological
    time series following VDI 3783 Part 20, Annex A3.1, Method A (AKJahr).

    Parameters
    ----------
    df : pd.DataFrame
        Hourly DatetimeIndex, columns: 'FF' (m/s), 'DD' (°), 'KM' (int 1-6).
    n_dir_sectors : int
        Wind-direction sectors (default 12 → 30° each).
    speed_edges : array-like or None
        Right bin edges for wind speed classes (m/s).  None → auto.
    n_speed_classes : int
        Number of auto speed classes (used only when speed_edges is None).
    G1_dir, G2_noc, G3_spd, G4_ak : float
        Parameter weightings for Eq. A2.
    nocturnal_hours : (int, int)
        Start and end hour (UTC) of the nocturnal period (default 18–06).
    weak_wind_threshold : float
        Wind speed threshold for nocturnal/weak-wind filter (default 2.0 m/s).

    Returns
    -------
    dict with keys
        'representative_year'  – int
        'ranking_chi2'         – DataFrame sorted by χ² (ascending = best)
        'ranking_sigma'        – DataFrame sorted by TQ (descending = best)
        'chi2_by_year'         – Series of total χ² per year
        'TQ_by_year'           – Series of total hit ratio TQ per year
        'selection_log'        – list of strings explaining the selection logic
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
        Returns (Mx_abs, Mx_rel, sigma_abs) over all years.
        Mx_abs  = mean absolute frequency (h/yr) per class
        Mx_rel  = relative share of Mx_abs in total annual hours
        sigma   = std dev of absolute freq across years
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
    Select a representative year from a multi-year hourly meteorological time
    series following VDI 3783 Part 20, Annex A3.2, Method B (Eq. A5 + A6).

    Parameters
    ----------
    df : pd.DataFrame
        DatetimeIndex (hourly), columns: 'FF' (wind speed m/s), 'DD' (wind
        direction °), 'KM' (Klug/Manier stability class – not used in Method B
        but kept for completeness).
    n_dir_sectors : int
        Number of equidistant wind-direction sectors (default 12 → 30° each).
    speed_classes : list of float or None
        Upper class boundaries for wind speed (m/s).  If None, n_speed_classes
        equidistant classes between 0 and the overall maximum are created.
    n_speed_classes : int
        Number of auto-generated speed classes (used only when speed_classes is
        None).
    weight_dir : float
        Weight for the wind-direction deviation (default 3, giving ratio 3:1).
    weight_speed : float
        Weight for the wind-speed deviation (default 1).

    Returns
    -------
    dict with keys
        'ranking'          – DataFrame sorted by BG_n (best year first)
        'representative_year' – int, the best year
        'A_dir'            – Series of raw deviation measures for direction
        'A_speed'          – Series of raw deviation measures for speed
        'BG'               – Series of weighted assessment variable BG_n
        'mean_speed_total' – long-term mean wind speed (plausibility check)
        'mean_speed_by_year' – Series of annual mean wind speeds
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

def main(args):
    """
    This is the main working function

    :param args: the command line arguments as dictionary
    :type args: dict
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

    SELECT_YEAR_PICKLE = os.path.join(working_dir, 'select_year.pkl')
    if os.path.exists(SELECT_YEAR_PICKLE):
        df = pd.read_pickle(SELECT_YEAR_PICKLE)
    else:
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

        df.to_pickle(SELECT_YEAR_PICKLE)

    if method == 'a':
        selected_year, ranking_chi2, ranking_sigma = method_A(df)
        rankings=[ranking_chi2, ranking_sigma]
    else:
        selected_year, ranking = method_B(df)
        rankings=[ranking]


    print("---------------------")
    print(f"selected year: {selected_year}")
    print("---------------------")

    for r in rankings:
        print(format(r))
        print("---------------------")



# ----------------------------------------------------

def add_options(subparsers):

    known_sources = _datasets.SOURCES_WEATHER

    pars_syr = subparsers.add_parser(
        name='select-year',
        help='Select representative year according to '
             'VDI 3783 Part 20, Appendix A3 [VDI3783p20]_',
        formatter_class=_tools.SmartFormatter,
    )
    pars_syr = _tools.add_location_opts(pars_syr, stations=True)
    pars_syr.add_argument('-m', '--method',
                          dest='method',
                          choices=['a', 'akjahr', 'b', 'timeseries'],
                          default='b',
                          help="Method for selecting a representative"
                               "year:\n"
                               "`a`/`akjahr`: method ``A``"
                               " ($\Chi^2$ and $\sigma$ environment)\n"
                               "`b`/`timeseries`: method ``B``"
                               " (from meteorological timesries)\n"
                               "Defaults to [%(default)]")
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
    input_weather.DEFAULT_CLASS_SCHEME = 'kms'
    pars_syr = input_weather.add_advanced_option_group(pars_syr)
    return subparsers