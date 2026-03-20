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
                centers=[([0.1], [10])],
                names=['A', 'B'],
                austal=[1, 2],
            )
        self.assertIn('mutually exclusive', str(context.exception))

    def test_init_bounds_must_be_list_or_tuple(self):
        """Test StabiltyClass raises for invalid bounds type."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(bounds="invalid", names=['A'], austal=[1])

    def test_init_centers_must_be_list_or_tuple(self):
        """Test StabiltyClass raises for invalid centers type."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(centers="invalid", names=['A'], austal=[1])

    def test_init_bounds_elements_must_be_pairs(self):
        """Test StabiltyClass raises when bounds elements not 2-element."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(
                bounds=[([0.1], [10], [20])],
                names=['A', 'B'],
                austal=[1, 2],
            )

    def test_init_centers_elements_must_be_pairs(self):
        """Test StabiltyClass raises when centers elements not 2-element."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(
                centers=[([0.1],)],
                names=['A'],
                austal=[1],
            )

    def test_init_bounds_lists_same_length(self):
        """Test StabiltyClass raises when bounds sublists different length."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(
                bounds=[([0.1, 0.2], [10])],
                names=['A', 'B'],
                austal=[1, 2],
            )

    def test_init_centers_lists_same_length(self):
        """Test StabiltyClass raises when centers sublists different length."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(
                centers=[([0.1, 0.2], [10])],
                names=['A'],
                austal=[1],
            )

    def test_init_bounds_sorted_z0(self):
        """Test StabiltyClass raises when z0 values not sorted."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(
                bounds=[([0.2, 0.1], [10, 20])],
                names=['A', 'B'],
                austal=[1, 2],
            )

    def test_init_centers_sorted_z0(self):
        """Test StabiltyClass raises when z0 values not sorted."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(
                centers=[([0.2, 0.1], [10, 20])],
                names=['A'],
                austal=[1],
            )

    def test_init_names_missing_raises(self):
        """Test StabiltyClass raises when names key is missing."""
        with self.assertRaises(ValueError) as context:
            _dispersion.StabiltyClass(
                centers=[([0.1], [10])],
                austal=[1],
            )
        self.assertIn('names', str(context.exception))

    def test_init_names_must_be_list_or_tuple(self):
        """Test StabiltyClass raises for invalid names type."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(
                centers=[([0.1], [10])],
                names="invalid",
                austal=[1],
            )

    def test_init_names_must_be_strings(self):
        """Test StabiltyClass raises when names are not strings."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(
                centers=[([0.1], [10])],
                names=[1, 2],
                austal=[1],
            )

    def test_init_names_count_must_match(self):
        """Test StabiltyClass raises when names count doesn't match classes."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(
                centers=[([0.1], [10]), ([0.1], [20])],
                names=['A'],  # Only 1 name for 2 classes
                austal=[1, 2],
            )

    def test_init_austal_missing_raises(self):
        """Test StabiltyClass raises when austal key is missing."""
        with self.assertRaises(ValueError) as context:
            _dispersion.StabiltyClass(
                centers=[([0.1], [10])],
                names=['A'],
            )
        self.assertIn('austal', str(context.exception))

    def test_init_austal_must_be_list_or_tuple(self):
        """Test StabiltyClass raises for invalid austal type."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(
                centers=[([0.1], [10])],
                names=['A'],
                austal="invalid",
            )

    def test_init_austal_must_be_integers(self):
        """Test StabiltyClass raises when austal values are not integers."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(
                centers=[([0.1], [10])],
                names=['A'],
                austal=[1.5],
            )

    def test_init_austal_count_must_match(self):
        """Test StabiltyClass raises when austal count doesn't match classes."""
        with self.assertRaises(ValueError):
            _dispersion.StabiltyClass(
                centers=[([0.1], [10]), ([0.1], [20])],
                names=['A', 'B'],
                austal=[1],  # Only 1 value for 2 classes
            )

    def test_init_valid_bounds(self):
        """Test StabiltyClass initializes correctly with valid bounds."""
        sc = _dispersion.StabiltyClass(
            bounds=[
                ([0.01, 0.1, 1.0], [10, 20, 30]),
                ([0.01, 0.1, 1.0], [50, 60, 70]),
            ],
            names=['A', 'B', 'C'],
            austal=[1, 2, 3],
        )
        self.assertEqual(sc.count, 3)

    def test_init_valid_centers(self):
        """Test StabiltyClass initializes correctly with valid centers."""
        sc = _dispersion.StabiltyClass(
            centers=[
                ([0.01, 0.1, 1.0], [10, 20, 30]),
                ([0.01, 0.1, 1.0], [50, 60, 70]),
            ],
            names=['A', 'B'],
            austal=[1, 2],
        )
        self.assertEqual(sc.count, 2)

    def test_init_austal_stored_correctly(self):
        """Test austal values are stored on the instance."""
        sc = _dispersion.StabiltyClass(
            centers=[
                ([0.01, 0.1], [10, 20]),
                ([0.01, 0.1], [50, 60]),
            ],
            names=['A', 'B'],
            austal=[3, 7],
            reverse_index=False,
        )
        self.assertEqual(sc.austal, [3, 7])

    def test_init_tabbed_is_inverse_parameter_accepted(self):
        """Test new parameter name tabbed_is_inverse is accepted."""
        # renamed from tabbed_values_inverted to tabbed_is_inverse
        sc = _dispersion.StabiltyClass(
            centers=[
                ([0.01, 0.1], [0.1, 0.05]),
                ([0.01, 0.1], [0.02, 0.01]),
            ],
            tabbed_is_inverse=True,
            reverse_index=False,
            names=['A', 'B'],
            austal=[1, 2],
        )
        self.assertEqual(sc.count, 2)

    def test_init_no_tabbed_values_inverted_parameter(self):
        """Test old parameter name tabbed_values_inverted is no longer accepted."""
        import inspect
        sig = inspect.signature(_dispersion.StabiltyClass.__init__)
        self.assertNotIn('tabbed_values_inverted', sig.parameters)
        self.assertIn('tabbed_is_inverse', sig.parameters)


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
            austal=[1, 2],
            reverse_index=False,
        )

    # --- class_center (renamed from get_center) ---

    def test_class_center_returns_float(self):
        """Test class_center returns a float."""
        result = self.sc.class_center(1, 0.1)
        self.assertIsInstance(result, float)

    def test_class_center_invalid_num(self):
        """Test class_center raises for invalid class number."""
        with self.assertRaises(ValueError):
            self.sc.class_center(99, 0.1)

    def test_class_center_inverse_parameter(self):
        """Test class_center accepts inverse parameter (renamed from inverted)."""
        result_L = self.sc.class_center(1, 0.1, inverse=False)
        result_inv = self.sc.class_center(1, 0.1, inverse=True)
        self.assertAlmostEqual(result_L, 1.0 / result_inv, places=10)

    def test_class_center_no_inverted_parameter(self):
        """Test class_center no longer accepts old 'inverted' parameter name."""
        import inspect
        sig = inspect.signature(self.sc.class_center)
        self.assertNotIn('inverted', sig.parameters)
        self.assertIn('inverse', sig.parameters)

    # --- class_bound (renamed from get_bound) ---

    def test_class_bound_returns_float(self):
        """Test class_bound returns a float for a valid intermediate class."""
        result = self.sc.class_bound(1, 0.1)
        self.assertIsInstance(result, float)

    def test_class_bound_invalid_num_zero(self):
        """Test class_bound raises for class number 0 (below valid range)."""
        with self.assertRaises(ValueError):
            self.sc.class_bound(0, 0.1)

    def test_class_bound_invalid_num_too_high(self):
        """Test class_bound raises for class number above count."""
        with self.assertRaises(ValueError):
            self.sc.class_bound(self.sc.count + 1, 0.1)

    def test_class_bound_highest_class_raises(self):
        """Test class_bound raises for the highest class number by design.

        class_bound(n) separates class n from n+1, so the highest class
        has no upper boundary — _bounds has count-1 entries, not count.
        """
        with self.assertRaises(ValueError):
            self.sc.class_bound(self.sc.count, 0.1)

    def test_class_bound_inverse_parameter(self):
        """Test class_bound accepts inverse parameter (renamed from inverted)."""
        result_L = self.sc.class_bound(1, 0.1, inverse=False)
        result_inv = self.sc.class_bound(1, 0.1, inverse=True)
        self.assertAlmostEqual(result_L, 1.0 / result_inv, places=10)

    def test_class_bound_no_inverted_parameter(self):
        """Test class_bound no longer accepts old 'inverted' parameter name."""
        import inspect
        sig = inspect.signature(self.sc.class_bound)
        self.assertNotIn('inverted', sig.parameters)
        self.assertIn('inverse', sig.parameters)

    # --- lookup_num (renamed from lookup_index, originally get_index) ---

    def test_lookup_num_returns_series(self):
        """Test lookup_num returns a pd.Series."""
        result = self.sc.lookup_num(
            pd.Series([0.1]), pd.Series([50.0])
        )
        self.assertIsInstance(result, pd.Series)

    def test_lookup_num_scalar_inputs_coerced(self):
        """Test lookup_num accepts scalar inputs (coerces to Series)."""
        result = self.sc.lookup_num(0.1, 50.0)
        self.assertIsInstance(result, pd.Series)

    def test_lookup_num_inverse_parameter(self):
        """Test lookup_num accepts inverse parameter (renamed from inverted)."""
        import inspect
        sig = inspect.signature(self.sc.lookup_num)
        self.assertNotIn('inverted', sig.parameters)
        self.assertIn('inverse', sig.parameters)

    def test_lookup_num_impossible_z0_returns_minus1(self):
        """Test lookup_num returns -1 for impossible z0 values."""
        # fixed: was not robust against impossible z0 values
        result = self.sc.lookup_num(
            pd.Series([-999.0]), pd.Series([50.0])
        )
        self.assertEqual(result.iloc[0], -1)

    def test_lookup_num_zero_z0_returns_minus1(self):
        """Test lookup_num returns -1 for zero z0 (impossible value)."""
        result = self.sc.lookup_num(
            pd.Series([0.0]), pd.Series([50.0])
        )
        self.assertEqual(result.iloc[0], -1)

    def test_lookup_num_nan_z0_returns_minus1(self):
        """Test lookup_num returns -1 for NaN z0."""
        result = self.sc.lookup_num(
            pd.Series([float('nan')]), pd.Series([50.0])
        )
        self.assertEqual(result.iloc[0], -1)

    # --- lookup_name ---

    def test_lookup_name_returns_series(self):
        """Test lookup_name returns a pd.Series."""
        result = self.sc.lookup_name(
            pd.Series([0.1]), pd.Series([50.0])
        )
        self.assertIsInstance(result, pd.Series)

    # --- lookup_austal ---

    def test_lookup_austal_returns_series(self):
        """Test lookup_austal returns a pd.Series."""
        result = self.sc.lookup_austal(
            pd.Series([0.1]), pd.Series([50.0])
        )
        self.assertIsInstance(result, pd.Series)

    # --- num2name (renamed from index2name, originally name()) ---

    def test_num2name_returns_string(self):
        """Test num2name returns a string."""
        result = self.sc.num2name(1)
        self.assertIsInstance(result, str)
        self.assertEqual(result, 'Stable')

    def test_num2name_invalid_num(self):
        """Test num2name raises for invalid class number."""
        with self.assertRaises(ValueError):
            self.sc.num2name(99)

    # --- num2austal (renamed from index2austal) ---

    def test_num2austal_returns_int_for_scalar(self):
        """Test num2austal returns int for scalar valid input."""
        result = self.sc.num2austal(1)
        self.assertIsInstance(result, int)

    def test_num2austal_returns_9_for_invalid_num(self):
        """Test num2austal returns 9 (nan sentinel) instead of raising."""
        # fixed: was raising instead of returning nan value "9"
        result = self.sc.num2austal(-1)
        self.assertEqual(result, 9)

    def test_num2austal_series_input_invalid_returns_9(self):
        """Test num2austal returns 9 for out-of-range values in a Series."""
        result = self.sc.num2austal(pd.Series([-1, 1, 99]))
        self.assertIsInstance(result, pd.Series)
        self.assertEqual(result.iloc[0], 9)
        self.assertEqual(result.iloc[2], 9)

    # --- name2num (renamed from name2index, originally index()) ---

    def test_name2num_returns_int(self):
        """Test name2num returns an integer for valid name."""
        result = self.sc.name2num('Stable')
        self.assertEqual(result, 1)

    def test_name2num_invalid_name(self):
        """Test name2num raises for invalid class name."""
        with self.assertRaises(ValueError):
            self.sc.name2num('NonexistentClass')

    # --- name2austal ---

    def test_name2austal_returns_int(self):
        """Test name2austal returns int for valid name."""
        result = self.sc.name2austal('Stable')
        self.assertIsInstance(result, int)

    def test_name2austal_value_matches_austal_list(self):
        """Test name2austal value corresponds to austal attribute."""
        num = self.sc.name2num('Stable')
        expected_austal = self.sc.austal[num - 1]
        self.assertEqual(self.sc.name2austal('Stable'), expected_austal)

    # --- old method names must not exist ---

    def test_old_method_get_bound_does_not_exist(self):
        """Test old (2.10.0) method get_bound no longer exists."""
        self.assertFalse(hasattr(self.sc, 'get_bound'))

    def test_old_method_get_center_does_not_exist(self):
        """Test old (2.10.0) method get_center no longer exists."""
        self.assertFalse(hasattr(self.sc, 'get_center'))

    def test_old_method_get_index_does_not_exist(self):
        """Test old (2.10.0) method get_index no longer exists."""
        self.assertFalse(hasattr(self.sc, 'get_index'))

    def test_old_method_get_name_does_not_exist(self):
        """Test old (2.10.0) method get_name no longer exists."""
        self.assertFalse(hasattr(self.sc, 'get_name'))

    def test_old_method_name_does_not_exist(self):
        """Test old (2.10.0) method name() no longer exists."""
        self.assertFalse(callable(getattr(self.sc, 'name', None)))

    def test_old_method_index_does_not_exist(self):
        """Test old (2.10.0) method index() no longer exists."""
        self.assertFalse(callable(getattr(self.sc, 'index', None)))

    def test_old_method_lookup_index_does_not_exist(self):
        """Test intermediate name lookup_index no longer exists."""
        self.assertFalse(hasattr(self.sc, 'lookup_index'))

    def test_old_method_index2name_does_not_exist(self):
        """Test intermediate name index2name no longer exists."""
        self.assertFalse(hasattr(self.sc, 'index2name'))

    def test_old_method_index2austal_does_not_exist(self):
        """Test intermediate name index2austal no longer exists."""
        self.assertFalse(hasattr(self.sc, 'index2austal'))

    def test_old_method_name2index_does_not_exist(self):
        """Test intermediate name name2index no longer exists."""
        self.assertFalse(hasattr(self.sc, 'name2index'))


class TestPredefinedStabilityClasses(unittest.TestCase):
    """Tests for predefined stability class objects."""

    # --- KM2021 ---

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

    def test_km2021_has_austal_attribute(self):
        """Test KM2021 has austal attribute with 6 values."""
        self.assertIsNotNone(_dispersion.KM2021.austal)
        self.assertEqual(len(_dispersion.KM2021.austal), 6)

    # --- KM2002 ---

    def test_km2002_exists(self):
        """Test KM2002 stability class is defined."""
        self.assertIsNotNone(_dispersion.KM2002)
        self.assertIsInstance(_dispersion.KM2002, _dispersion.StabiltyClass)

    def test_km2002_has_6_classes(self):
        """Test KM2002 has 6 stability classes."""
        self.assertEqual(_dispersion.KM2002.count, 6)

    def test_km2002_has_austal_attribute(self):
        """Test KM2002 has austal attribute with 6 values."""
        self.assertIsNotNone(_dispersion.KM2002.austal)
        self.assertEqual(len(_dispersion.KM2002.austal), 6)

    # --- PT1972 (renamed from old PG1972) ---

    def test_pt1972_exists(self):
        """Test PT1972 (Pasquill/Turner) stability class is defined."""
        self.assertIsNotNone(_dispersion.PT1972)
        self.assertIsInstance(_dispersion.PT1972, _dispersion.StabiltyClass)

    def test_pt1972_has_7_classes(self):
        """Test PT1972 has 7 stability classes (A-G)."""
        self.assertEqual(_dispersion.PT1972.count, 7)

    def test_pt1972_class_names(self):
        """Test PT1972 names are stored reversed (reverse_index=True reverses internal storage).

        The data is tabulated least-stable→most-stable, reverse_index=True
        maps class num 1 to the most-stable end, so names are stored as
        ['G','F','E','D','C','B','A'] internally. num2name(1)='G', num2name(7)='A'.
        """
        self.assertEqual(_dispersion.PT1972.names,
                         ['G', 'F', 'E', 'D', 'C', 'B', 'A'])

    def test_pt1972_has_austal_attribute(self):
        """Test PT1972 has austal attribute with 7 values."""
        self.assertIsNotNone(_dispersion.PT1972.austal)
        self.assertEqual(len(_dispersion.PT1972.austal), 7)

    # --- PG1972 (new: Pasquill/Gifford, distinct from old PG1972/now PT1972) ---

    def test_pg1972_exists(self):
        """Test PG1972 (Pasquill/Gifford) stability class is defined."""
        self.assertIsNotNone(_dispersion.PG1972)
        self.assertIsInstance(_dispersion.PG1972, _dispersion.StabiltyClass)

    def test_pg1972_has_7_classes(self):
        """Test PG1972 has 7 stability classes (A-G)."""
        self.assertEqual(_dispersion.PG1972.count, 7)

    def test_pg1972_class_names(self):
        """Test PG1972 names are stored reversed (reverse_index=True reverses internal storage).

        Same convention as PT1972: names stored as ['G','F','E','D','C','B','A'].
        """
        self.assertEqual(_dispersion.PG1972.names,
                         ['G', 'F', 'E', 'D', 'C', 'B', 'A'])

    def test_pg1972_has_austal_attribute(self):
        """Test PG1972 has austal attribute with 7 values."""
        self.assertIsNotNone(_dispersion.PG1972.austal)
        self.assertEqual(len(_dispersion.PG1972.austal), 7)

    def test_pg1972_and_pt1972_are_different_objects(self):
        """Test PG1972 and PT1972 are distinct stability class objects."""
        self.assertIsNot(_dispersion.PG1972, _dispersion.PT1972)

    def test_pg1972_and_pt1972_have_different_bounds(self):
        """Test PG1972 and PT1972 use different boundary data.

        Uses class num 1 (boundary between class 1 and 2), which is valid
        for both 7-class scales (valid range 1..6).
        """
        z0 = 0.05
        bound_pg = _dispersion.PG1972.class_bound(1, z0, inverse=True)
        bound_pt = _dispersion.PT1972.class_bound(1, z0, inverse=True)
        self.assertNotAlmostEqual(bound_pg, bound_pt, places=5)

    # --- austal_class function must not exist ---

    def test_austal_class_function_removed(self):
        """Test obsolete austal_class() function has been removed."""
        self.assertFalse(hasattr(_dispersion, 'austal_class'))


class TestStabilityClassIndexOrder(unittest.TestCase):
    """Tests for the fixed index order in StabiltyClass.__init__."""

    def test_km2021_index_order_names_ascending(self):
        """Test KM2021 names are in ascending stability order (I through V)."""
        names = _dispersion.KM2021.names
        self.assertEqual(names[0], 'I')
        self.assertEqual(names[-1], 'V')

    def test_km2021_class_center_increasing_with_index(self):
        """Test KM2021 class centers are ordered: most stable first.

        Class I (num 1) is most stable → large positive L (1/L near 0+).
        Class V (num 6) is most unstable → large negative L (1/L << 0).
        """
        z0 = 0.1
        center_I = _dispersion.KM2021.class_center('I', z0, inverse=True)
        center_V = _dispersion.KM2021.class_center('V', z0, inverse=True)
        # 1/L for class I (stable) > 1/L for class V (unstable)
        self.assertGreater(center_I, center_V)

    def test_pt1972_class_A_most_unstable(self):
        """Test PT1972 class A corresponds to most unstable conditions."""
        z0 = 0.05
        center_A = _dispersion.PT1972.class_center('A', z0, inverse=True)
        center_G = _dispersion.PT1972.class_center('G', z0, inverse=True)
        # 1/L for class A (most unstable) < 1/L for class G (most stable)
        self.assertLess(center_A, center_G)

    def test_pg1972_class_A_most_unstable(self):
        """Test PG1972 class A corresponds to most unstable conditions."""
        z0 = 0.05
        center_A = _dispersion.PG1972.class_center('A', z0, inverse=True)
        center_G = _dispersion.PG1972.class_center('G', z0, inverse=True)
        self.assertLess(center_A, center_G)


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
            ust=0.3, rho=1.2, Tv=288, H=100, E=50, Kelvin=True
        )
        self.assertIsInstance(result, (float, np.floating, np.ndarray))

    def test_obukhov_length_positive_H_negative_L(self):
        """Test obukhov_length is negative for positive H (unstable)."""
        result = _dispersion.obukhov_length(
            ust=0.3, rho=1.2, Tv=288, H=100, E=50, Kelvin=True
        )
        self.assertLess(result, 0)

    def test_obukhov_length_negative_H_positive_L(self):
        """Test obukhov_length is positive for negative H (stable)."""
        result = _dispersion.obukhov_length(
            ust=0.3, rho=1.2, Tv=288, H=-100, E=-50, Kelvin=True
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
        self.assertLess(result[0], result[-1])


class TestVdi38726SunRiseSet(unittest.TestCase):
    """Tests for the vdi_3872_6_sun_rise_set function."""

    def test_sun_rise_set_returns_tuple(self):
        """Test vdi_3872_6_sun_rise_set returns tuple of two values."""
        result = _dispersion.vdi_3872_6_sun_rise_set(
            time='2024-06-21 12:00:00', lat=50.0, lon=8.0
        )
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_sun_rise_set_sunrise_before_sunset(self):
        """Test sunrise is before sunset."""
        sunrise, sunset = _dispersion.vdi_3872_6_sun_rise_set(
            time='2024-06-21 12:00:00', lat=50.0, lon=8.0
        )
        self.assertLess(sunrise, sunset)

    def test_sun_rise_set_summer_day_longer(self):
        """Test summer day is longer than winter day."""
        summer_rise, summer_set = _dispersion.vdi_3872_6_sun_rise_set(
            time='2024-06-21 12:00:00', lat=50.0, lon=8.0
        )
        winter_rise, winter_set = _dispersion.vdi_3872_6_sun_rise_set(
            time='2024-12-21 12:00:00', lat=50.0, lon=8.0
        )
        self.assertGreater(summer_set - summer_rise, winter_set - winter_rise)

    def test_sun_rise_set_invalid_longitude(self):
        """Test vdi_3872_6_sun_rise_set raises for invalid longitude."""
        with self.assertRaises(ValueError):
            _dispersion.vdi_3872_6_sun_rise_set(
                time='2024-06-21 12:00:00', lat=50.0, lon=100.0
            )

    def test_sun_rise_set_with_datetime64(self):
        """Test vdi_3872_6_sun_rise_set with np.datetime64 input."""
        result = _dispersion.vdi_3872_6_sun_rise_set(
            time=np.datetime64('2024-06-21T12:00:00'), lat=50.0, lon=8.0
        )
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_sun_rise_set_with_timestamp(self):
        """Test vdi_3872_6_sun_rise_set with pd.Timestamp input."""
        result = _dispersion.vdi_3872_6_sun_rise_set(
            time=pd.Timestamp('2024-06-21 12:00:00'), lat=50.0, lon=8.0
        )
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_sun_rise_set_with_string_list(self):
        """Test vdi_3872_6_sun_rise_set with list of string timestamps."""
        result = _dispersion.vdi_3872_6_sun_rise_set(
            time=['2024-06-21 12:00:00', '2024-12-21 12:00:00'],
            lat=50.0, lon=8.0
        )
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result[0]), 2)
        self.assertEqual(len(result[1]), 2)

    def test_sun_rise_set_with_datetimeindex(self):
        """Test vdi_3872_6_sun_rise_set with pd.DatetimeIndex input."""
        result = _dispersion.vdi_3872_6_sun_rise_set(
            time=pd.DatetimeIndex(['2024-06-21 12:00:00', '2024-12-21 12:00:00']),
            lat=50.0, lon=8.0
        )
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result[0]), 2)


class TestVdi38726StandardWind(unittest.TestCase):
    """Tests for the vdi_3872_6_standard_wind function."""

    def test_standard_wind_returns_numeric(self):
        """Test vdi_3872_6_standard_wind returns numeric value."""
        result = _dispersion.vdi_3872_6_standard_wind(
            va=5.0, hap=10.0, z0p=0.1
        )
        self.assertIsInstance(result, (float, np.floating, np.ndarray))

    def test_standard_wind_same_conditions_unchanged(self):
        """Test wind unchanged when already at standard conditions."""
        result = _dispersion.vdi_3872_6_standard_wind(
            va=5.0, hap=10.0, z0p=0.1
        )
        self.assertAlmostEqual(result, 5.0, delta=0.5)

    def test_standard_wind_array_input(self):
        """Test vdi_3872_6_standard_wind with array input."""
        va = np.array([3.0, 5.0, 7.0])
        result = _dispersion.vdi_3872_6_standard_wind(
            va=va, hap=10.0, z0p=0.1
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
            z=10.0, speed=speed, gust=gust, dirct=dirct, rose=False
        )
        self.assertIsInstance(result, (float, np.floating))

    def test_z0_verkaik_rose_returns_tuple(self):
        """Test z0_verkaik returns tuple when rose=True."""
        speed = pd.Series([6.0, 7.0, 8.0])
        gust = pd.Series([9.0, 10.0, 11.0])
        dirct = pd.Series([0.0, 90.0, 180.0])
        result = _dispersion.z0_verkaik(
            z=10.0, speed=speed, gust=gust, dirct=dirct, rose=True
        )
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_z0_verkaik_positive_result(self):
        """Test z0_verkaik returns positive roughness length."""
        speed = pd.Series([6.0, 7.0, 8.0, 9.0, 10.0])
        gust = pd.Series([9.0, 10.0, 11.0, 12.0, 13.0])
        dirct = pd.Series([0.0, 90.0, 180.0, 270.0, 45.0])
        result = _dispersion.z0_verkaik(
            z=10.0, speed=speed, gust=gust, dirct=dirct, rose=False
        )
        self.assertGreater(result, 0)

    def test_z0_verkaik_with_list_inputs(self):
        """Test z0_verkaik with list inputs instead of pd.Series."""
        speed = [6.0, 7.0, 8.0, 9.0, 10.0]
        gust = [9.0, 10.0, 11.0, 12.0, 13.0]
        dirct = [0.0, 90.0, 180.0, 270.0, 45.0]
        result = _dispersion.z0_verkaik(
            z=10.0, speed=speed, gust=gust, dirct=dirct, rose=False
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
            time=time_input, lat=50.0, lon=8.0
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
            time=time_input, lat=50.0, lon=8.0
        )
        assert isinstance(result, tuple)
        assert len(result[0]) == 2
        assert len(result[1]) == 2

    @pytest.mark.parametrize("sc_name,expected_count", [
        ('KM2021', 6),
        ('KM2002', 6),
        ('PT1972', 7),
        ('PG1972', 7),
    ])
    def test_predefined_class_counts(self, sc_name, expected_count):
        """Test all predefined stability classes have the expected count."""
        sc = getattr(_dispersion, sc_name)
        assert sc.count == expected_count

    @pytest.mark.parametrize("sc_name", ['KM2021', 'KM2002', 'PT1972', 'PG1972'])
    def test_predefined_classes_have_austal(self, sc_name):
        """Test all predefined stability classes have an austal attribute."""
        sc = getattr(_dispersion, sc_name)
        assert sc.austal is not None
        assert len(sc.austal) == sc.count

    @pytest.mark.parametrize("sc_name", ['PT1972', 'PG1972'])
    def test_pg_pt_austal_fg_combined(self, sc_name):
        """Test EPA convention: F and G both map to austal class 1."""
        sc = getattr(_dispersion, sc_name)
        idx_F = sc.name2num('F')
        idx_G = sc.name2num('G')
        assert sc.num2austal(idx_F) == sc.num2austal(idx_G)

    @pytest.mark.parametrize("z0,lob", [
        (0.01, -50.0),
        (0.1, -100.0),
        (0.5, 200.0),
        (1.0, 50.0),
    ])
    def test_km2021_lookup_num_valid_z0(self, z0, lob):
        """Test KM2021 lookup_num returns a valid class for typical z0/L pairs."""
        result = _dispersion.KM2021.lookup_num(
            pd.Series([z0]), pd.Series([lob])
        )
        assert result.iloc[0] in range(1, 7)

    @pytest.mark.parametrize("impossible_z0", [-1.0, 0.0, 1500.0, float('nan')])
    def test_lookup_num_impossible_z0_values(self, impossible_z0):
        """Test lookup_num returns -1 for all impossible z0 values."""
        result = _dispersion.KM2021.lookup_num(
            pd.Series([impossible_z0]), pd.Series([-100.0])
        )
        assert result.iloc[0] == -1

    @pytest.mark.parametrize("invalid_index", [-1, 0, 99])
    def test_num2austal_invalid_returns_9(self, invalid_index):
        """Test num2austal returns sentinel 9 for out-of-range indices."""
        result = _dispersion.KM2021.num2austal(invalid_index)
        assert result == 9


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and boundary conditions."""

    def test_km2021_lookup_very_unstable(self):
        """Test KM2021 lookup for very unstable conditions."""
        result = _dispersion.KM2021.lookup_num(
            pd.Series([0.1]), pd.Series([-10.0])
        )
        self.assertIn(result.iloc[0], range(1, 10))

    def test_km2021_lookup_very_stable(self):
        """Test KM2021 lookup for very stable conditions."""
        result = _dispersion.KM2021.lookup_num(
            pd.Series([0.1]), pd.Series([10.0])
        )
        self.assertIn(result.iloc[0], range(1, 10))

    def test_km2021_lookup_neutral(self):
        """Test KM2021 lookup for near-neutral conditions (very large |L|)."""
        result = _dispersion.KM2021.lookup_num(
            pd.Series([0.1]), pd.Series([10000.0])
        )
        self.assertIn(result.iloc[0], range(1, 10))

    def test_num2austal_series_preserves_valid_values(self):
        """Test num2austal maps valid indices to their correct austal values."""
        sc = _dispersion.KM2021
        for i in range(1, sc.count + 1):
            result = sc.num2austal(i)
            self.assertEqual(result, sc.austal[i - 1])

    def test_lookup_austal_impossible_z0_returns_9(self):
        """Test lookup_austal returns 9 (via index -1) for impossible z0."""
        result = _dispersion.KM2021.lookup_austal(
            pd.Series([0.0]), pd.Series([-100.0])
        )
        self.assertEqual(result.iloc[0], 9)


if __name__ == '__main__':
    unittest.main()
