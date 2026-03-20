#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for austaltools.select_year

Run with:
    pytest tests/test_select_year.py -v
"""
import unittest
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

from austaltools.select_year import (
    _classify_direction,
    _classify_speed,
    _classify_km,
    _freq_abs,
    _chi2_term,
    _sigma_hits,
    method_A,
    method_B,
    method_T,
    selected_year_plot,
)


# ===========================================================================
# Fixtures / shared helpers
# ===========================================================================

def _make_hourly_index(years):
    """Return a full-year hourly DatetimeIndex for the given list of years."""
    parts = [pd.date_range(f"{y}-01-01", f"{y}-12-31 23:00", freq="h")
             for y in years]
    return parts[0].append(parts[1:]) if len(parts) > 1 else parts[0]


def _make_wind_df(years, seed=42):
    """
    Create a synthetic hourly wind + stability DataFrame suitable for
    method_A and method_B.

    Columns: FF (m/s), DD (°), KM (Klug/Manier 1–6).
    """
    rng = np.random.default_rng(seed)
    idx = _make_hourly_index(years)
    n = len(idx)
    df = pd.DataFrame({
        "FF": rng.uniform(0.5, 10.0, n),
        "DD": rng.uniform(0.0, 360.0, n),
        "KM": rng.integers(1, 7, n),
    }, index=idx)
    return df


def _make_temp_df(years, seed=42):
    """
    Create a synthetic hourly temperature DataFrame suitable for method_T.

    Column: T (°C) with a realistic annual cycle plus noise.
    """
    rng = np.random.default_rng(seed)
    idx = _make_hourly_index(years)
    n = len(idx)
    doy = idx.day_of_year
    # seasonal cycle + diurnal cycle + noise
    T = (10 * np.sin(2 * np.pi * (doy - 80) / 365)
         + 3  * np.sin(2 * np.pi * idx.hour / 24)
         + rng.normal(0, 1.5, n))
    return pd.DataFrame({"T": T}, index=idx)


# ===========================================================================
# _classify_direction
# ===========================================================================

class TestClassifyDirection:
    def test_north_maps_to_sector_0(self):
        dd = pd.Series([0.0, 360.0, 359.9, 0.1])
        result = _classify_direction(dd)
        assert (result == 0).all()

    def test_east_maps_to_sector_3(self):
        # sector 3 covers 75°–105° with 12 sectors (30° each)
        dd = pd.Series([90.0])
        result = _classify_direction(dd)
        assert result.iloc[0] == 3

    def test_south_maps_to_sector_6(self):
        dd = pd.Series([180.0])
        result = _classify_direction(dd)
        assert result.iloc[0] == 6

    def test_all_sectors_covered(self):
        # one value per sector centre
        centres = np.arange(0, 360, 30).astype(float)
        dd = pd.Series(centres)
        result = _classify_direction(dd)
        assert set(result) == set(range(12))

    def test_nan_maps_to_minus_one(self):
        dd = pd.Series([np.nan, 90.0, np.nan])
        result = _classify_direction(dd)
        assert result.iloc[0] == -1
        assert result.iloc[2] == -1
        assert result.iloc[1] != -1

    def test_output_dtype_is_int(self):
        dd = pd.Series([45.0, np.nan])
        result = _classify_direction(dd)
        assert result.dtype == int

    def test_custom_n_sectors(self):
        dd = pd.Series([90.0])
        result = _classify_direction(dd, n_sectors=4)
        # 4 sectors of 90° each; 90° → sector 1
        assert result.iloc[0] == 1

    def test_all_nan(self):
        dd = pd.Series([np.nan, np.nan])
        result = _classify_direction(dd)
        assert (result == -1).all()

    def test_index_preserved(self):
        idx = pd.date_range("2020-01-01", periods=3, freq="h")
        dd = pd.Series([0.0, 90.0, 180.0], index=idx)
        result = _classify_direction(dd)
        assert list(result.index) == list(idx)


# ===========================================================================
# _classify_speed
# ===========================================================================

class TestClassifySpeed:
    @pytest.fixture
    def edges(self):
        return np.array([0.0, 2.0, 5.0, 10.0, 20.0])

    def test_first_bin(self, edges):
        ff = pd.Series([0.0, 1.9])
        result = _classify_speed(ff, edges)
        assert (result == 0).all()

    def test_last_bin(self, edges):
        # edges = [0, 2, 5, 10, 20] → last defined bin is index 3 (10–20)
        ff = pd.Series([10.1, 19.9])
        result = _classify_speed(ff, edges)
        assert (result == 3).all()

    def test_overflow_beyond_last_edge(self, edges):
        # searchsorted returns len(edges[1:]) = 4 for values above last edge
        ff = pd.Series([25.0, 100.0])
        result = _classify_speed(ff, edges)
        assert (result == 4).all()

    def test_boundary_goes_to_higher_bin(self, edges):
        # side="right" → exact boundary belongs to next bin
        ff = pd.Series([2.0])
        result = _classify_speed(ff, edges)
        assert result.iloc[0] == 1

    def test_nan_maps_to_minus_one(self, edges):
        ff = pd.Series([np.nan, 3.0, np.nan])
        result = _classify_speed(ff, edges)
        assert result.iloc[0] == -1
        assert result.iloc[2] == -1
        assert result.iloc[1] != -1

    def test_output_dtype_is_int(self, edges):
        ff = pd.Series([1.0, np.nan])
        result = _classify_speed(ff, edges)
        assert result.dtype == int

    def test_index_preserved(self, edges):
        idx = pd.date_range("2020-01-01", periods=3, freq="h")
        ff = pd.Series([1.0, 3.0, 7.0], index=idx)
        result = _classify_speed(ff, edges)
        assert list(result.index) == list(idx)

    def test_all_nan(self, edges):
        ff = pd.Series([np.nan, np.nan])
        result = _classify_speed(ff, edges)
        assert (result == -1).all()


# ===========================================================================
# _classify_km
# ===========================================================================

class TestClassifyKm:
    def test_valid_classes_pass_through(self):
        km = pd.Series([1, 2, 3, 4, 5, 6], dtype=float)
        result = _classify_km(km)
        assert list(result) == [1, 2, 3, 4, 5, 6]

    def test_nan_maps_to_minus_one(self):
        km = pd.Series([1.0, np.nan, 3.0])
        result = _classify_km(km)
        assert result.iloc[1] == -1

    def test_output_dtype_is_int(self):
        km = pd.Series([2.0, np.nan])
        result = _classify_km(km)
        assert result.dtype == int

    def test_all_nan(self):
        km = pd.Series([np.nan, np.nan])
        result = _classify_km(km)
        assert (result == -1).all()


# ===========================================================================
# _freq_abs
# ===========================================================================

class TestFreqAbs:
    def test_counts_match(self):
        s = pd.Series([0, 0, 1, 2, 2, 2])
        result = _freq_abs(s, range(3))
        assert result[0] == 2
        assert result[1] == 1
        assert result[2] == 3

    def test_missing_class_filled_with_zero(self):
        s = pd.Series([0, 0])
        result = _freq_abs(s, range(3))
        assert result[1] == 0
        assert result[2] == 0

    def test_sentinel_minus_one_excluded(self):
        s = pd.Series([-1, -1, 0, 1])
        result = _freq_abs(s, range(3))
        # -1 must not appear in output
        assert -1 not in result.index
        assert result[0] == 1
        assert result[1] == 1

    def test_output_dtype_float(self):
        s = pd.Series([0, 1])
        result = _freq_abs(s, range(2))
        assert result.dtype == float

    def test_empty_series_all_zeros(self):
        s = pd.Series([], dtype=int)
        result = _freq_abs(s, range(3))
        assert (result == 0).all()


# ===========================================================================
# _chi2_term
# ===========================================================================

class TestChi2Term:
    def test_identical_distributions_give_zero(self):
        Mx_abs = pd.Series([10.0, 20.0, 30.0])
        Mx_rel = Mx_abs / Mx_abs.sum()
        result = _chi2_term(Mx_abs, Mx_abs, Mx_rel)
        assert result == pytest.approx(0.0)

    def test_returns_float(self):
        Mx_abs = pd.Series([10.0, 20.0])
        Mx_rel = Mx_abs / Mx_abs.sum()
        x_abs  = pd.Series([12.0, 18.0])
        result = _chi2_term(x_abs, Mx_abs, Mx_rel)
        assert isinstance(result, float)

    def test_nonzero_deviation(self):
        Mx_abs = pd.Series([10.0, 10.0])
        Mx_rel = Mx_abs / Mx_abs.sum()
        x_abs  = pd.Series([20.0, 0.0])
        result = _chi2_term(x_abs, Mx_abs, Mx_rel)
        assert result > 0.0

    def test_zero_mx_class_skipped(self):
        # class 1 has Mx_abs == 0 → should not cause division by zero
        Mx_abs = pd.Series([10.0, 0.0, 10.0])
        Mx_rel = pd.Series([0.5, 0.0, 0.5])
        x_abs  = pd.Series([12.0, 5.0, 8.0])
        result = _chi2_term(x_abs, Mx_abs, Mx_rel)
        assert np.isfinite(result)

    def test_result_is_nonnegative(self):
        rng = np.random.default_rng(0)
        Mx_abs = pd.Series(rng.uniform(1, 100, 12))
        Mx_rel = Mx_abs / Mx_abs.sum()
        x_abs  = pd.Series(rng.uniform(1, 100, 12))
        assert _chi2_term(x_abs, Mx_abs, Mx_rel) >= 0.0


# ===========================================================================
# _sigma_hits
# ===========================================================================

class TestSigmaHits:
    def test_all_inside_returns_full_count(self):
        Mx    = pd.Series([10.0, 20.0, 30.0])
        sigma = pd.Series([ 5.0, 10.0, 15.0])
        x     = Mx.copy()   # exactly at mean → strictly inside
        assert _sigma_hits(x, Mx, sigma) == 3

    def test_all_outside_returns_zero(self):
        Mx    = pd.Series([10.0, 20.0])
        sigma = pd.Series([ 1.0,  1.0])
        x     = pd.Series([50.0, 50.0])
        assert _sigma_hits(x, Mx, sigma) == 0

    def test_boundary_is_excluded(self):
        # strictly less / greater than → boundary value is NOT a hit
        Mx    = pd.Series([10.0])
        sigma = pd.Series([ 5.0])
        x_boundary = pd.Series([15.0])   # exactly Mx + sigma → not inside
        assert _sigma_hits(x_boundary, Mx, sigma) == 0

    def test_returns_int(self):
        Mx    = pd.Series([5.0])
        sigma = pd.Series([2.0])
        x     = pd.Series([5.0])
        assert isinstance(_sigma_hits(x, Mx, sigma), int)

    def test_partial_hits(self):
        Mx    = pd.Series([10.0, 10.0, 10.0])
        sigma = pd.Series([ 1.0,  1.0,  1.0])
        x     = pd.Series([10.0, 20.0, 10.0])   # 2 inside, 1 outside
        assert _sigma_hits(x, Mx, sigma) == 2


# ===========================================================================
# method_B
# ===========================================================================

class TestMethodB:

    @pytest.fixture
    def wind_df(self):
        return _make_wind_df(range(2015, 2021))

    def test_returns_tuple_of_two(self, wind_df):
        result = method_B(wind_df)
        assert isinstance(result, tuple) and len(result) == 2

    def test_representative_year_in_input_years(self, wind_df):
        yr, _ = method_B(wind_df)
        assert yr in range(2015, 2021)

    def test_ranking_indexed_by_year(self, wind_df):
        _, ranking = method_B(wind_df)
        assert ranking.index.name == "year" or set(ranking.index).issubset(
            range(2015, 2021))

    def test_ranking_has_score_column(self, wind_df):
        _, ranking = method_B(wind_df)
        assert "BG_n" in ranking.columns

    def test_ranking_sorted_ascending(self, wind_df):
        _, ranking = method_B(wind_df)
        scores = ranking["BG_n"].values
        assert list(scores) == sorted(scores)

    def test_all_years_present_in_ranking(self, wind_df):
        _, ranking = method_B(wind_df)
        assert set(ranking.index) == set(range(2015, 2021))

    def test_scores_are_nonnegative(self, wind_df):
        _, ranking = method_B(wind_df)
        assert (ranking["BG_n"] >= 0).all()

    def test_nan_in_ff_handled(self, wind_df):
        wind_df = wind_df.copy()
        wind_df.loc[wind_df.index[:200], "FF"] = np.nan
        yr, ranking = method_B(wind_df)
        assert yr in set(ranking.index)

    def test_nan_in_dd_handled(self, wind_df):
        wind_df = wind_df.copy()
        wind_df.loc[wind_df.index[:200], "DD"] = np.nan
        yr, ranking = method_B(wind_df)
        assert yr in set(ranking.index)

    def test_custom_weight_changes_score(self, wind_df):
        _, r_default = method_B(wind_df, weight_dir=3.0, weight_speed=1.0)
        _, r_equal   = method_B(wind_df, weight_dir=1.0, weight_speed=1.0)
        # scores need not be identical when weights differ
        assert not r_default["BG_n"].equals(r_equal["BG_n"])

    def test_single_year_runs(self):
        df = _make_wind_df([2020])
        yr, ranking = method_B(df)
        assert yr == 2020


# ===========================================================================
# method_A
# ===========================================================================

class TestMethodA:

    @pytest.fixture
    def wind_df(self):
        return _make_wind_df(range(2015, 2021))

    def test_returns_triple(self, wind_df):
        result = method_A(wind_df)
        assert isinstance(result, tuple) and len(result) == 3

    def test_representative_year_in_input(self, wind_df):
        yr, _, _ = method_A(wind_df)
        assert yr in range(2015, 2021)

    def test_chi2_ranking_sorted_ascending(self, wind_df):
        _, r_chi2, _ = method_A(wind_df)
        scores = r_chi2["chi2_total"].values
        assert list(scores) == sorted(scores)

    def test_sigma_ranking_sorted_descending(self, wind_df):
        _, _, r_sigma = method_A(wind_df)
        scores = r_sigma["TQ_total"].values
        assert list(scores) == sorted(scores, reverse=True)

    def test_chi2_columns_present(self, wind_df):
        _, r_chi2, _ = method_A(wind_df)
        for col in ["chi2_dir", "chi2_noc", "chi2_spd", "chi2_km",
                    "chi2_total"]:
            assert col in r_chi2.columns

    def test_sigma_columns_present(self, wind_df):
        _, _, r_sigma = method_A(wind_df)
        for col in ["TQ_dir", "TQ_noc", "TQ_spd", "TQ_km", "TQ_total"]:
            assert col in r_sigma.columns

    def test_chi2_total_equals_weighted_sum(self, wind_df):
        """chi2_total must equal G1*c1 + G2*c2 + G3*c3 + G4*c4.

        The individual component columns are stored rounded to 4 decimal
        places, so the reconstructed sum may differ from chi2_total by up
        to the accumulated rounding error (~1e-3).
        """
        G1, G2, G3, G4 = 0.36, 0.15, 0.24, 0.25
        _, r_chi2, _ = method_A(wind_df, G1_dir=G1, G2_noc=G2,
                                 G3_spd=G3, G4_ak=G4)
        expected = (G1 * r_chi2["chi2_dir"]
                    + G2 * r_chi2["chi2_noc"]
                    + G3 * r_chi2["chi2_spd"]
                    + G4 * r_chi2["chi2_km"])
        pd.testing.assert_series_equal(
            r_chi2["chi2_total"], expected,
            check_names=False,
            atol=1e-3,   # tolerate rounding from .round(4) on components
            rtol=0,
        )

    def test_all_years_in_both_rankings(self, wind_df):
        _, r_chi2, r_sigma = method_A(wind_df)
        assert set(r_chi2.index) == set(range(2015, 2021))
        assert set(r_sigma.index) == set(range(2015, 2021))

    def test_nan_in_km_handled(self, wind_df):
        wind_df = wind_df.copy()
        wind_df.loc[wind_df.index[:300], "KM"] = np.nan
        yr, _, _ = method_A(wind_df)
        assert yr in range(2015, 2021)

    def test_chi2_scores_nonnegative(self, wind_df):
        _, r_chi2, _ = method_A(wind_df)
        assert (r_chi2["chi2_total"] >= 0).all()

    def test_single_year_runs(self):
        df = _make_wind_df([2020])
        yr, r_chi2, r_sigma = method_A(df)
        assert yr == 2020


# ===========================================================================
# method_T
# ===========================================================================

class TestMethodT:

    @pytest.fixture
    def temp_df(self):
        return _make_temp_df(range(2015, 2021))

    def test_returns_tuple_of_two(self, temp_df):
        result = method_T(temp_df)
        assert isinstance(result, tuple) and len(result) == 2

    def test_representative_year_in_input(self, temp_df):
        yr, _ = method_T(temp_df)
        assert yr in range(2015, 2021)

    def test_ranking_has_required_columns(self, temp_df):
        _, ranking = method_T(temp_df)
        for col in ["bias", "rms_daily", "rms_monthly", "score"]:
            assert col in ranking.columns

    def test_ranking_sorted_ascending(self, temp_df):
        _, ranking = method_T(temp_df)
        scores = ranking["score"].values
        assert list(scores) == sorted(scores)

    def test_all_years_present(self, temp_df):
        _, ranking = method_T(temp_df)
        assert set(ranking.index) == set(range(2015, 2021))

    def test_scores_nonnegative(self, temp_df):
        _, ranking = method_T(temp_df)
        assert (ranking["score"] >= 0).all()

    def test_missing_column_raises_key_error(self, temp_df):
        with pytest.raises(KeyError):
            method_T(temp_df, temp_col="NOTEXIST")

    def test_custom_temp_col(self):
        df = _make_temp_df(range(2015, 2018))
        df = df.rename(columns={"T": "temp"})
        yr, ranking = method_T(df, temp_col="temp")
        assert yr in range(2015, 2018)

    def test_nan_rows_dropped_gracefully(self, temp_df):
        temp_df = temp_df.copy()
        # set one full day to NaN
        temp_df.loc["2017-07-15", "T"] = np.nan
        yr, ranking = method_T(temp_df)
        assert yr in range(2015, 2021)

    def test_bias_close_to_zero_for_uniform_data(self):
        """A year identical to the MAC should have near-zero bias."""
        years = range(2015, 2021)
        idx   = _make_hourly_index(years)
        doy   = idx.day_of_year
        # purely deterministic annual cycle, same every year → all biases ≈ 0
        T = 10 * np.sin(2 * np.pi * (doy - 80) / 365).astype(float)
        df = pd.DataFrame({"T": T}, index=idx)
        _, ranking = method_T(df)
        assert ranking["bias"].abs().max() < 1e-6

    def test_single_year_runs(self):
        df = _make_temp_df([2020])
        yr, ranking = method_T(df)
        assert yr == 2020


# ===========================================================================
# selected_year_plot
# ===========================================================================

class TestSelectedYearPlot:
    """Smoke tests – verify the function runs without error."""

    @pytest.fixture(autouse=True)
    def use_agg_backend(self):
        import matplotlib
        matplotlib.use("Agg")

    @pytest.fixture
    def ranking_B(self):
        df = _make_wind_df(range(2015, 2021))
        yr, ranking = method_B(df)
        return yr, {"ranking": ranking}

    @pytest.fixture
    def ranking_A(self):
        df = _make_wind_df(range(2015, 2021))
        yr, r_chi2, r_sigma = method_A(df)
        return yr, {"chi2 ranking": r_chi2, "sigma ranking": r_sigma}

    def test_no_plot_arg_returns_early(self, ranking_B, tmp_path):
        yr, rankings = ranking_B
        # no 'plot' key → must return without error
        selected_year_plot({}, rankings, yr)

    def test_none_plot_returns_early(self, ranking_B, tmp_path):
        yr, rankings = ranking_B
        selected_year_plot({"plot": None}, rankings, yr)

    def test_empty_plot_name_raises(self, ranking_B):
        yr, rankings = ranking_B
        with pytest.raises(ValueError):
            selected_year_plot({"plot": ""}, rankings, yr)

    def test_saves_png_single_ranking(self, ranking_B, tmp_path):
        yr, rankings = ranking_B
        outfile = str(tmp_path / "test.png")
        selected_year_plot({"plot": outfile}, rankings, yr)
        assert (tmp_path / "test.png").exists()

    def test_saves_png_two_rankings(self, ranking_A, tmp_path):
        yr, rankings = ranking_A
        outfile = str(tmp_path / "test_A.png")
        selected_year_plot({"plot": outfile}, rankings, yr)
        assert (tmp_path / "test_A.png").exists()

    def test_saves_pdf(self, ranking_B, tmp_path):
        yr, rankings = ranking_B
        outfile = str(tmp_path / "test.pdf")
        selected_year_plot({"plot": outfile}, rankings, yr)
        assert (tmp_path / "test.pdf").exists()

    def test_selected_year_not_in_rankings_does_not_crash(
            self, ranking_B, tmp_path):
        yr, rankings = ranking_B
        outfile = str(tmp_path / "test_missing.png")
        selected_year_plot({"plot": outfile}, rankings, 9999)
        assert (tmp_path / "test_missing.png").exists()


# ===========================================================================
# Integration: method_B result feeds selected_year_plot
# ===========================================================================

class TestIntegration:
    @pytest.fixture(autouse=True)
    def use_agg_backend(self):
        import matplotlib
        matplotlib.use("Agg")

    def test_method_b_to_plot(self, tmp_path):
        df = _make_wind_df(range(2015, 2021))
        yr, ranking = method_B(df)
        outfile = str(tmp_path / "b.png")
        selected_year_plot({"plot": outfile}, {"ranking": ranking}, yr)
        assert (tmp_path / "b.png").exists()

    def test_method_a_to_plot(self, tmp_path):
        df = _make_wind_df(range(2015, 2021))
        yr, r_chi2, r_sigma = method_A(df)
        outfile = str(tmp_path / "a.png")
        selected_year_plot(
            {"plot": outfile},
            {"chi2 ranking": r_chi2, "sigma ranking": r_sigma},
            yr,
        )
        assert (tmp_path / "a.png").exists()

    def test_method_t_to_plot(self, tmp_path):
        df = _make_temp_df(range(2015, 2021))
        yr, ranking = method_T(df)
        outfile = str(tmp_path / "t.png")
        selected_year_plot({"plot": outfile}, {"ranking": ranking}, yr)
        assert (tmp_path / "t.png").exists()
