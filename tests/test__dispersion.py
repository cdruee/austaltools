#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive test suite for austaltools._dispersion module.

This module tests atmospheric stability class determination
and related dispersion modeling functions.
"""
import unittest
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

import austaltools._dispersion
from austaltools import _dispersion


class TestStabilityClassInit(unittest.TestCase):
    """Tests for StabiltyClass initialization."""

    def test_init_bounds_and_centers_mutually_exclusive(self):
        """Test StabiltyClass raises when both bounds and centers given."""
        with self.assertRaises(ValueError) as context:
            _dispersion.StabiltyClass(
                bounds=[([0.1], [10])],
                centers=[([0.1], [10])]
            )
        self.assertIn('mutually exclusive', str(context.exception))

    def test_init_bounds_must_be_list_or_tuple(self):
        """Test StabiltyClass raises for invalid bounds type."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(bounds="invalid")

    def test_init_centers_must_be_list_or_tuple(self):
        """Test StabiltyClass raises for invalid centers type."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(centers="invalid")

    def test_init_bounds_elements_must_be_pairs(self):
        """Test StabiltyClass raises when bounds elements not 2-element."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(bounds=[([0.1], [10], [20])])

    def test_init_centers_elements_must_be_pairs(self):
        """Test StabiltyClass raises when centers elements not 2-element."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(centers=[([0.1],)])

    def test_init_bounds_lists_same_length(self):
        """Test StabiltyClass raises when bounds sublists different length."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(bounds=[([0.1, 0.2], [10])])

    def test_init_centers_lists_same_length(self):
        """Test StabiltyClass raises when centers sublists different length."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(centers=[([0.1, 0.2], [10])])

    def test_init_bounds_sorted_z0(self):
        """Test StabiltyClass raises when z0 values not sorted."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(bounds=[([0.2, 0.1], [10, 20])])

    def test_init_centers_sorted_z0(self):
        """Test StabiltyClass raises when z0 values not sorted."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(centers=[([0.2, 0.1], [10, 20])])

    def test_init_names_must_be_list_or_tuple(self):
        """Test StabiltyClass raises for invalid names type."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(
                centers=[([0.1], [10])],
                names="invalid"
            )

    def test_init_names_must_be_strings(self):
        """Test StabiltyClass raises when names are not strings."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(
                centers=[([0.1], [10])],
                names=[1, 2]
            )

    def test_init_names_count_must_match(self):
        """Test StabiltyClass raises when names count doesn't match classes."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(
                centers=[([0.1], [10]), ([0.1], [20])],
                names=['A']  # Only 1 name for 2 classes
            )

    def test_init_valid_bounds(self):
        """Test StabiltyClass initializes correctly with valid bounds."""
        sc = _dispersion.StabiltyClass(
            bounds=[
                ([0.01, 0.1, 1.0], [10, 20, 30]),
                ([0.01, 0.1, 1.0], [50, 60, 70]),
            ],
            names=['A', 'B', 'C']
        )
        self.assertEqual(sc.count, 3)

    def test_init_valid_centers(self):
        """Test StabiltyClass initializes correctly with valid centers."""
        sc = _dispersion.StabiltyClass(
            centers=[
                ([0.01, 0.1, 1.0], [10, 20, 30]),
                ([0.01, 0.1, 1.0], [50, 60, 70]),
            ],
            names=['A', 'B']
        )
        self.assertEqual(sc.count, 2)


class TestStabilityClassMethods(unittest.TestCase):
    """Tests for StabiltyClass methods."""

    def setUp(self):
        """Set up test stability class."""
        self.sc = _dispersion.StabiltyClass(
            centers=[
                ([0.01, 0.1, 1.0], [10, 20, 30]),
                ([0.01, 0.1, 1.0], [100, 200, 300]),
            ],
            names=['Stable', 'Unstable'],
            reverse_index=False
        )

    def test_get_center_returns_float(self):
        """Test get_center returns a float."""
        result = self.sc.get_center(0, 0.1)
        self.assertIsInstance(result, float)

    def test_get_center_invalid_num(self):
        """Test get_center raises for invalid class number."""
        with self.assertRaises(ValueError):
            self.sc.get_center(99, 0.1)

    def test_get_bound_returns_float(self):
        """Test get_bound returns a float."""
        result = self.sc.get_bound(0, 0.1)
        self.assertIsInstance(result, float)

    def test_get_bound_invalid_num(self):
        """Test get_bound raises for invalid boundary number."""
        with self.assertRaises(ValueError):
            self.sc.get_bound(99, 0.1)

    def test_get_index_returns_int(self):
        """Test get_index returns an integer."""
        result = self.sc.get_index(0.1, 50)
        self.assertIsInstance(result, int)

    def test_name_returns_string(self):
        """Test name returns a string."""
        result = self.sc.name(1)
        self.assertIsInstance(result, str)
        self.assertEqual(result, 'Stable')

    def test_name_invalid_num(self):
        """Test name raises for invalid class number."""
        with self.assertRaises(ValueError):
            self.sc.name(99)

    def test_index_returns_int(self):
        """Test index returns an integer for valid name."""
        result = self.sc.index('Stable')
        self.assertEqual(result, 1)

    def test_index_invalid_name(self):
        """Test index raises for invalid class name."""
        with self.assertRaises(ValueError):
            self.sc.index('NonexistentClass')


class TestPredefinedStabilityClasses(unittest.TestCase):
    """Tests for predefined stability class objects."""

    def test_km2021_exists(self):
        """Test KM2021 stability class is defined."""
        self.assertIsNotNone(_dispersion.KM2021)
        self.assertIsInstance(_dispersion.KM2021, _dispersion.StabiltyClass)

    def test_km2021_has_6_classes(self):
        """Test KM2021 has 6 stability classes."""
        self.assertEqual(_dispersion.KM2021.count, 6)

    def test_km2021_class_names(self):
        """Test KM2021 has correct class names."""
        expected_names = ['I', 'II', 'III1', 'III2', 'IV', 'V']
        self.assertEqual(_dispersion.KM2021.names, expected_names)

    def test_km2002_exists(self):
        """Test KM2002 stability class is defined."""
        self.assertIsNotNone(_dispersion.KM2002)
        self.assertIsInstance(_dispersion.KM2002, _dispersion.StabiltyClass)

    def test_km2002_has_6_classes(self):
        """Test KM2002 has 6 stability classes."""
        self.assertEqual(_dispersion.KM2002.count, 6)

    def test_pg1972_exists(self):
        """Test PG1972 stability class is defined."""
        self.assertIsNotNone(_dispersion.PG1972)
        self.assertIsInstance(_dispersion.PG1972, _dispersion.StabiltyClass)

    def test_pg1972_has_7_classes(self):
        """Test PG1972 has 7 stability classes (A-G)."""
        self.assertEqual(_dispersion.PG1972.count, 7)

    def test_pg1972_class_names(self):
        """Test PG1972 has correct class names."""
        expected_names = ['A', 'B', 'C', 'D', 'E', 'F', 'G']
        self.assertEqual(_dispersion.PG1972.names, expected_names)


class TestStabilityClassFunction(unittest.TestCase):
    """Tests for the stabilty_class function."""

    def test_stabilty_class_returns_list(self):
        """Test stabilty_class returns a list."""
        time = pd.DatetimeIndex(['2024-01-01 12:00:00'])
        z0 = pd.Series([0.1], index=time)
        L = pd.Series([-100], index=time)

        result = _dispersion.stabilty_class('KM2021', time, z0, L)
        self.assertIsInstance(result, list)

    def test_stabilty_class_shape_mismatch(self):
        """Test stabilty_class raises for shape mismatch."""
        time = pd.DatetimeIndex(['2024-01-01 12:00:00'])
        z0 = pd.Series([0.1, 0.2])  # Wrong shape
        L = pd.Series([-100])

        with self.assertRaises(ValueError):
            _dispersion.stabilty_class('KM2021', time, z0, L)

    def test_stabilty_class_km2021(self):
        """Test stabilty_class with KM2021 classifier."""
        time = pd.DatetimeIndex(['2024-01-01 12:00:00'])
        z0 = pd.Series([0.1], index=time)
        L = pd.Series([-100], index=time)

        result = _dispersion.stabilty_class('KM2021', time, z0, L)
        self.assertIn(result[0], range(1, 10))  # Valid class or 9 (missing)

    def test_stabilty_class_km2002(self):
        """Test stabilty_class with KM2002 classifier."""
        time = pd.DatetimeIndex(['2024-01-01 12:00:00'])
        z0 = pd.Series([0.1], index=time)
        L = pd.Series([-100], index=time)

        result = _dispersion.stabilty_class('KM2002', time, z0, L)
        self.assertIn(result[0], range(1, 10))

    def test_stabilty_class_pg1972(self):
        """Test stabilty_class with PG1972 classifier."""
        time = pd.DatetimeIndex(['2024-01-01 12:00:00'])
        z0 = pd.Series([0.1], index=time)
        L = pd.Series([-100], index=time)

        result = _dispersion.stabilty_class('PG1972', time, z0, L)
        self.assertIn(result[0], range(1, 10))

    def test_stabilty_class_scalar_inputs(self):
        """Test stabilty_class with scalar inputs."""
        time = pd.Timestamp('2024-01-01 12:00:00')
        z0 = 0.1
        L = -100

        result = _dispersion.stabilty_class('KM2021', time, z0, L)
        self.assertIsInstance(result, list)

    def test_stabilty_class_with_datetime64(self):
        """Test stabilty_class with np.datetime64 input."""
        time = np.datetime64('2024-01-01T12:00:00')
        z0 = 0.1
        L = -100

        result = _dispersion.stabilty_class('KM2021', time, z0, L)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)

    def test_stabilty_class_with_string_list(self):
        """Test stabilty_class with list of string timestamps."""
        time = ['2024-01-01 12:00:00', '2024-01-01 13:00:00']
        z0 = [0.1, 0.1]
        L = [-100, -150]

        result = _dispersion.stabilty_class('KM2021', time, z0, L)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)

    def test_stabilty_class_shape_mismatch(self):
        """Test stabilty_class raises for shape mismatch."""
        time = pd.DatetimeIndex(['2024-01-01 12:00:00'])
        z0 = pd.Series([0.1, 0.2])  # Wrong shape
        L = pd.Series([-100])

        with self.assertRaises(ValueError):
            _dispersion.stabilty_class('KM2021', time, z0, L)

    def test_stabilty_class_km2021(self):
        """Test stabilty_class with KM2021 classifier."""
        time = pd.DatetimeIndex(['2024-01-01 12:00:00'])
        z0 = pd.Series([0.1], index=time)
        L = pd.Series([-100], index=time)

        result = _dispersion.stabilty_class('KM2021', time, z0, L)
        self.assertIn(result[0], range(1, 10))  # Valid class or 9 (missing)

    def test_stabilty_class_km2002(self):
        """Test stabilty_class with KM2002 classifier."""
        time = pd.DatetimeIndex(['2024-01-01 12:00:00'])
        z0 = pd.Series([0.1], index=time)
        L = pd.Series([-100], index=time)

        result = _dispersion.stabilty_class('KM2002', time, z0, L)
        self.assertIn(result[0], range(1, 10))

    def test_stabilty_class_pg1972(self):
        """Test stabilty_class with PG1972 classifier."""
        time = pd.DatetimeIndex(['2024-01-01 12:00:00'])
        z0 = pd.Series([0.1], index=time)
        L = pd.Series([-100], index=time)

        result = _dispersion.stabilty_class('PG1972', time, z0, L)
        self.assertIn(result[0], range(1, 10))

    def test_stabilty_class_scalar_inputs(self):
        """Test stabilty_class with scalar inputs."""
        time = pd.Timestamp('2024-01-01 12:00:00')
        z0 = 0.1
        L = -100

        result = _dispersion.stabilty_class('KM2021', time, z0, L)
        self.assertIsInstance(result, list)


class TestTaylorInsolationClass(unittest.TestCase):
    """Tests for the taylor_insolation_class function."""

    def test_taylor_insolation_weak(self):
        """Test taylor_insolation_class returns 1 for weak (<=15 deg)."""
        result = _dispersion.taylor_insolation_class(10)
        self.assertEqual(result, 1)

    def test_taylor_insolation_slight(self):
        """Test taylor_insolation_class returns 2 for slight (15-35 deg)."""
        result = _dispersion.taylor_insolation_class(25)
        self.assertEqual(result, 2)

    def test_taylor_insolation_moderate(self):
        """Test taylor_insolation_class returns 3 for moderate (35-60 deg)."""
        result = _dispersion.taylor_insolation_class(45)
        self.assertEqual(result, 3)

    def test_taylor_insolation_strong(self):
        """Test taylor_insolation_class returns 4 for strong (>60 deg)."""
        result = _dispersion.taylor_insolation_class(70)
        self.assertEqual(result, 4)

    def test_taylor_insolation_boundary_15(self):
        """Test taylor_insolation_class at boundary 15 degrees."""
        result = _dispersion.taylor_insolation_class(15)
        self.assertEqual(result, 1)

    def test_taylor_insolation_boundary_35(self):
        """Test taylor_insolation_class at boundary 35 degrees."""
        result = _dispersion.taylor_insolation_class(35)
        self.assertEqual(result, 2)

    def test_taylor_insolation_boundary_60(self):
        """Test taylor_insolation_class at boundary 60 degrees."""
        result = _dispersion.taylor_insolation_class(60)
        self.assertEqual(result, 3)


class TestTurnersKey(unittest.TestCase):
    """Tests for the turners_key function."""

    def test_turners_key_returns_int(self):
        """Test turners_key returns an integer."""
        result = _dispersion.turners_key(3.0, 2)
        self.assertIsInstance(result, int)

    def test_turners_key_valid_range(self):
        """Test turners_key returns value in valid range (1-7)."""
        result = _dispersion.turners_key(3.0, 2)
        self.assertIn(result, range(1, 8))

    def test_turners_key_low_wind_high_nri(self):
        """Test turners_key for low wind, high radiation."""
        result = _dispersion.turners_key(0.5, 4)
        self.assertEqual(result, 1)  # Class A (very unstable)

    def test_turners_key_high_wind_neutral(self):
        """Test turners_key for high wind, neutral."""
        result = _dispersion.turners_key(6.0, 0)
        self.assertEqual(result, 4)  # Class D (neutral)

    def test_turners_key_invalid_nri(self):
        """Test turners_key raises for invalid NRI."""
        with self.assertRaises(ValueError):
            _dispersion.turners_key(3.0, 10)

    def test_turners_key_negative_wind(self):
        """Test turners_key raises for negative wind speed."""
        with self.assertRaises(ValueError):
            _dispersion.turners_key(-1.0, 2)


class TestObukhovLength(unittest.TestCase):
    """Tests for the obukhov_length function."""

    def test_obukhov_length_returns_numeric(self):
        """Test obukhov_length returns numeric value."""
        result = _dispersion.obukhov_length(
            ust=0.3,
            rho=1.2,
            Tv=288,
            H=100,
            E=50,
            Kelvin=True
        )
        self.assertIsInstance(result, (float, np.floating, np.ndarray))

    def test_obukhov_length_positive_H_negative_L(self):
        """Test obukhov_length is negative for positive H (unstable)."""
        result = _dispersion.obukhov_length(
            ust=0.3,
            rho=1.2,
            Tv=288,
            H=100,  # Positive sensible heat flux
            E=50,
            Kelvin=True
        )
        self.assertLess(result, 0)

    def test_obukhov_length_negative_H_positive_L(self):
        """Test obukhov_length is positive for negative H (stable)."""
        result = _dispersion.obukhov_length(
            ust=0.3,
            rho=1.2,
            Tv=288,
            H=-100,  # Negative sensible heat flux
            E=-50,
            Kelvin=True
        )
        self.assertGreater(result, 0)


class TestHEff(unittest.TestCase):
    """Tests for the h_eff function."""

    def test_h_eff_returns_list(self):
        """Test h_eff returns a list."""
        result = _dispersion.h_eff(has=10, z0s=0.1)
        self.assertIsInstance(result, list)

    def test_h_eff_nine_values(self):
        """Test h_eff returns 9 values (for 9 z0 classes)."""
        result = _dispersion.h_eff(has=10, z0s=0.1)
        self.assertEqual(len(result), 9)

    def test_h_eff_all_positive(self):
        """Test h_eff returns all positive values."""
        result = _dispersion.h_eff(has=10, z0s=0.1)
        for val in result:
            self.assertGreater(val, 0)

    def test_h_eff_increases_with_z0(self):
        """Test h_eff values generally increase with z0."""
        result = _dispersion.h_eff(has=10, z0s=0.1)
        # Heights should generally increase for higher z0
        # (rougher terrain = higher effective height)
        self.assertLess(result[0], result[-1])


class TestVdi38726SunRiseSet(unittest.TestCase):
    """Tests for the vdi_3872_6_sun_rise_set function."""

    def test_sun_rise_set_returns_tuple(self):
        """Test vdi_3872_6_sun_rise_set returns tuple of two values."""
        result = _dispersion.vdi_3872_6_sun_rise_set(
            time='2024-06-21 12:00:00',
            lat=50.0,
            lon=8.0
        )
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_sun_rise_set_sunrise_before_sunset(self):
        """Test sunrise is before sunset."""
        sunrise, sunset = _dispersion.vdi_3872_6_sun_rise_set(
            time='2024-06-21 12:00:00',
            lat=50.0,
            lon=8.0
        )
        self.assertLess(sunrise, sunset)

    def test_sun_rise_set_summer_day_longer(self):
        """Test summer day is longer than winter day."""
        summer_rise, summer_set = _dispersion.vdi_3872_6_sun_rise_set(
            time='2024-06-21 12:00:00',
            lat=50.0,
            lon=8.0
        )
        winter_rise, winter_set = _dispersion.vdi_3872_6_sun_rise_set(
            time='2024-12-21 12:00:00',
            lat=50.0,
            lon=8.0
        )
        summer_length = summer_set - summer_rise
        winter_length = winter_set - winter_rise
        self.assertGreater(summer_length, winter_length)

    def test_sun_rise_set_invalid_longitude(self):
        """Test vdi_3872_6_sun_rise_set raises for invalid longitude."""
        with self.assertRaises(ValueError):
            _dispersion.vdi_3872_6_sun_rise_set(
                time='2024-06-21 12:00:00',
                lat=50.0,
                lon=100.0  # Outside CET zone
            )

    def test_sun_rise_set_with_datetime64(self):
        """Test vdi_3872_6_sun_rise_set with np.datetime64 input."""
        result = _dispersion.vdi_3872_6_sun_rise_set(
            time=np.datetime64('2024-06-21T12:00:00'),
            lat=50.0,
            lon=8.0
        )
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_sun_rise_set_with_timestamp(self):
        """Test vdi_3872_6_sun_rise_set with pd.Timestamp input."""
        result = _dispersion.vdi_3872_6_sun_rise_set(
            time=pd.Timestamp('2024-06-21 12:00:00'),
            lat=50.0,
            lon=8.0
        )
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_sun_rise_set_with_string_list(self):
        """Test vdi_3872_6_sun_rise_set with list of string timestamps."""
        result = _dispersion.vdi_3872_6_sun_rise_set(
            time=['2024-06-21 12:00:00', '2024-12-21 12:00:00'],
            lat=50.0,
            lon=8.0
        )
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        # Each element should be a Series with 2 values
        self.assertEqual(len(result[0]), 2)
        self.assertEqual(len(result[1]), 2)

    def test_sun_rise_set_with_datetimeindex(self):
        """Test vdi_3872_6_sun_rise_set with pd.DatetimeIndex input."""
        result = _dispersion.vdi_3872_6_sun_rise_set(
            time=pd.DatetimeIndex(['2024-06-21 12:00:00', '2024-12-21 12:00:00']),
            lat=50.0,
            lon=8.0
        )
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result[0]), 2)


class TestVdi38726StandardWind(unittest.TestCase):
    """Tests for the vdi_3872_6_standard_wind function."""

    def test_standard_wind_returns_numeric(self):
        """Test vdi_3872_6_standard_wind returns numeric value."""
        result = _dispersion.vdi_3872_6_standard_wind(
            va=5.0,
            hap=10.0,
            z0p=0.1
        )
        self.assertIsInstance(result, (float, np.floating, np.ndarray))

    def test_standard_wind_same_conditions_unchanged(self):
        """Test wind unchanged when already at standard conditions."""
        # Standard: 10m height, z0=0.1m
        result = _dispersion.vdi_3872_6_standard_wind(
            va=5.0,
            hap=10.0,
            z0p=0.1
        )
        # Should be close to input value
        self.assertAlmostEqual(result, 5.0, delta=0.5)

    def test_standard_wind_array_input(self):
        """Test vdi_3872_6_standard_wind with array input."""
        va = np.array([3.0, 5.0, 7.0])
        result = _dispersion.vdi_3872_6_standard_wind(
            va=va,
            hap=10.0,
            z0p=0.1
        )
        self.assertEqual(len(result), 3)


class TestZ0Verkaik(unittest.TestCase):
    """Tests for the z0_verkaik function."""

    def test_z0_verkaik_returns_float(self):
        """Test z0_verkaik returns a float when rose=False."""
        speed = pd.Series([6.0, 7.0, 8.0])
        gust = pd.Series([9.0, 10.0, 11.0])
        dirct = pd.Series([0.0, 90.0, 180.0])

        result = _dispersion.z0_verkaik(
            z=10.0,
            speed=speed,
            gust=gust,
            dirct=dirct,
            rose=False
        )
        self.assertIsInstance(result, (float, np.floating))

    def test_z0_verkaik_rose_returns_tuple(self):
        """Test z0_verkaik returns tuple when rose=True."""
        speed = pd.Series([6.0, 7.0, 8.0])
        gust = pd.Series([9.0, 10.0, 11.0])
        dirct = pd.Series([0.0, 90.0, 180.0])

        result = _dispersion.z0_verkaik(
            z=10.0,
            speed=speed,
            gust=gust,
            dirct=dirct,
            rose=True
        )
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_z0_verkaik_positive_result(self):
        """Test z0_verkaik returns positive roughness length."""
        speed = pd.Series([6.0, 7.0, 8.0, 9.0, 10.0])
        gust = pd.Series([9.0, 10.0, 11.0, 12.0, 13.0])
        dirct = pd.Series([0.0, 90.0, 180.0, 270.0, 45.0])

        result = _dispersion.z0_verkaik(
            z=10.0,
            speed=speed,
            gust=gust,
            dirct=dirct,
            rose=False
        )
        self.assertGreater(result, 0)

    def test_z0_verkaik_with_list_inputs(self):
        """Test z0_verkaik with list inputs instead of pd.Series."""
        speed = [6.0, 7.0, 8.0, 9.0, 10.0]
        gust = [9.0, 10.0, 11.0, 12.0, 13.0]
        dirct = [0.0, 90.0, 180.0, 270.0, 45.0]

        result = _dispersion.z0_verkaik(
            z=10.0,
            speed=speed,
            gust=gust,
            dirct=dirct,
            rose=False
        )
        self.assertIsInstance(result, (float, np.floating))
        self.assertGreater(result, 0)


# Pytest-style parametrized tests

class TestPytestStyle:
    """Pytest-style tests for additional patterns."""

    @pytest.mark.parametrize("solar_altitude,expected_class", [
        (5, 1),
        (15, 1),
        (20, 2),
        (35, 2),
        (40, 3),
        (60, 3),
        (70, 4),
        (90, 4),
    ])
    def test_taylor_insolation_various(self, solar_altitude, expected_class):
        """Test taylor_insolation_class with various altitudes."""
        result = _dispersion.taylor_insolation_class(solar_altitude)
        assert result == expected_class

    @pytest.mark.parametrize("classifier", [
        'Klug/Manier',
        'KM2021',
        'KM',
        'TA Luft 2021',
        'KM2002',
        'TA Luft 2002',
        'Pasquill/Gifford',
        'PG1972',
        'PG',
    ])
    def test_stabilty_class_all_classifiers(self, classifier):
        """Test stabilty_class accepts all valid classifier names."""
        time = pd.DatetimeIndex(['2024-01-01 12:00:00'])
        z0 = pd.Series([0.1], index=time)
        L = pd.Series([-100], index=time)

        result = _dispersion.stabilty_class(classifier, time, z0, L)
        assert isinstance(result, list)
        assert len(result) == 1

    @pytest.mark.parametrize("nri", [-2, -1, 0, 1, 2, 3, 4])
    def test_turners_key_all_nri(self, nri):
        """Test turners_key with all valid NRI values."""
        result = _dispersion.turners_key(3.0, nri)
        assert result in range(1, 8)

    @pytest.mark.parametrize("time_input", [
        '2024-06-21 12:00:00',
        pd.Timestamp('2024-06-21 12:00:00'),
        np.datetime64('2024-06-21T12:00:00'),
    ])
    def test_sun_rise_set_time_input_types(self, time_input):
        """Test vdi_3872_6_sun_rise_set with various time input types."""
        result = _dispersion.vdi_3872_6_sun_rise_set(
            time=time_input,
            lat=50.0,
            lon=8.0
        )
        assert isinstance(result, tuple)
        assert len(result) == 2

    @pytest.mark.parametrize("time_input", [
        pd.DatetimeIndex(['2024-06-21 12:00:00', '2024-12-21 12:00:00']),
        ['2024-06-21 12:00:00', '2024-12-21 12:00:00'],
    ])
    def test_sun_rise_set_array_time_input_types(self, time_input):
        """Test vdi_3872_6_sun_rise_set with array-like time inputs."""
        result = _dispersion.vdi_3872_6_sun_rise_set(
            time=time_input,
            lat=50.0,
            lon=8.0
        )
        assert isinstance(result, tuple)
        assert len(result[0]) == 2
        assert len(result[1]) == 2

    @pytest.mark.parametrize("time_input", [
        pd.Timestamp('2024-01-01 12:00:00'),
        np.datetime64('2024-01-01T12:00:00'),
        '2024-01-01 12:00:00',
    ])
    def test_stabilty_class_time_input_types(self, time_input):
        """Test stabilty_class with various scalar time input types."""
        result = _dispersion.stabilty_class(
            'KM2021',
            time_input,
            0.1,
            -100
        )
        assert isinstance(result, list)
        assert len(result) == 1

    @pytest.mark.parametrize("time_input", [
        pd.DatetimeIndex(['2024-01-01 12:00:00', '2024-01-01 13:00:00']),
        ['2024-01-01 12:00:00', '2024-01-01 13:00:00'],
    ])
    def test_stabilty_class_array_time_input_types(self, time_input):
        """Test stabilty_class with array-like time inputs."""
        result = _dispersion.stabilty_class(
            'KM2021',
            time_input,
            [0.1, 0.1],
            [-100, -150]
        )
        assert isinstance(result, list)
        assert len(result) == 2


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and boundary conditions."""

    def test_stability_class_very_unstable(self):
        """Test stability class for very unstable conditions."""
        time = pd.DatetimeIndex(['2024-06-21 12:00:00'])
        z0 = pd.Series([0.1], index=time)
        L = pd.Series([-10], index=time)  # Very small negative L

        result = _dispersion.stabilty_class('KM2021', time, z0, L)
        # Should return high index (unstable)
        self.assertIn(result[0], range(1, 10))

    def test_stability_class_very_stable(self):
        """Test stability class for very stable conditions."""
        time = pd.DatetimeIndex(['2024-01-01 00:00:00'])
        z0 = pd.Series([0.1], index=time)
        L = pd.Series([10], index=time)  # Small positive L

        result = _dispersion.stabilty_class('KM2021', time, z0, L)
        self.assertIn(result[0], range(1, 10))

    def test_stability_class_neutral(self):
        """Test stability class for neutral conditions."""
        time = pd.DatetimeIndex(['2024-01-01 12:00:00'])
        z0 = pd.Series([0.1], index=time)
        L = pd.Series([10000], index=time)  # Very large L = neutral

        result = _dispersion.stabilty_class('KM2021', time, z0, L)
        self.assertIn(result[0], range(1, 10))


if __name__ == '__main__':
    unittest.main()
