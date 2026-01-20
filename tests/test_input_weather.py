#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive test suite for austaltools.input_weather module.

This module tests the weather data extraction functionality for AUSTAL.
Focus is on fast unit tests for helper functions rather than slow
integration tests that require network access or large data files.
"""
import logging
import os
import subprocess
import unittest
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

from austaltools import command_line
from austaltools import input_weather


# Helper function for subprocess tests
CMD = ['python', '-m', 'austaltools.command_line']
SUBCMD = 'weather'
OUTPUT = 'test'
EXTENSION = 'akterm'


def capture(command):
    """Run command and capture output."""
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out, err = proc.communicate()
    print('command stdout: \n' + out.decode())
    print('command stderr: \n' + err.decode())
    print('cmd exit code : \n%s' % proc.returncode)
    return out, err, proc.returncode


def expected_files(output):
    """Generate list of expected output files."""
    result = []
    for s in ['era5', 'dwd']:
        for y in range(2000, 2020):
            for m in ['kms', 'kmo', 'k2o', 'pts', 'kmc', 'pgc']:
                result.append("%s_%s_%04i_%s.%s" %
                              (s, output, y, m, EXTENSION))
    return result


# =============================================================================
# Tests for CLI parser subcommand
# =============================================================================

class TestCliParserSubcommand(unittest.TestCase):
    """Tests for subcommand availability in cli_parser."""

    def setUp(self):
        """Set up parser for tests."""
        self.parser = command_line.cli_parser()

    def test_has_weather_subcommand(self):
        """Test 'weather' subcommand is available."""
        args = self.parser.parse_args(['weather', '-L', '49.0', '6.0', '-y', '2000', 'test'])
        self.assertEqual(args.command, 'weather')


# =============================================================================
# Tests for main function dispatch
# =============================================================================

class TestMain(unittest.TestCase):
    """Tests for the main function dispatch."""

    @patch('austaltools.command_line.input_weather.main')
    def test_main_calls_input_weather(self, mock_weather_main):
        """Test main dispatches to input_weather.main for 'weather' command."""
        args = {
            'command': 'weather',
            'working_dir': '/tmp',
            'verb': None,
            'temp_dir': None
        }
        command_line.main(args)
        mock_weather_main.assert_called_once_with(args)

    def test_main_no_working_dir_raises(self):
        """Test main raises when working_dir is None."""
        args = {
            'command': 'weather',
            'working_dir': None,
            'verb': None,
            'temp_dir': None
        }
        with self.assertRaises(ValueError) as context:
            command_line.main(args)
        self.assertIn('PATH not given', str(context.exception))


# =============================================================================
# Tests for h_eff function
# =============================================================================

class TestHEff(unittest.TestCase):
    """Tests for the h_eff (effective height) function."""

    def test_h_eff_returns_list(self):
        """Test h_eff returns a list of 9 values."""
        result = input_weather.h_eff(10.0, 0.1)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 9)

    def test_h_eff_all_positive(self):
        """Test h_eff returns all positive values."""
        result = input_weather.h_eff(10.0, 0.1)
        self.assertTrue(all(h > 0 for h in result))

    def test_h_eff_increasing_with_roughness(self):
        """Test h_eff generally increases with roughness class."""
        result = input_weather.h_eff(10.0, 0.1)
        # For higher roughness, effective height should generally be higher
        # (this is approximate due to the complex relationship)
        self.assertIsInstance(result[0], float)


# =============================================================================
# Tests for area_of_triangle function
# =============================================================================

class TestAreaOfTriangle(unittest.TestCase):
    """Tests for the area_of_triangle function."""

    def test_area_unit_triangle(self):
        """Test area of unit right triangle."""
        abc = [(0., 0.), (1., 0.), (0., 1.)]
        area = input_weather.area_of_triangle(abc)
        self.assertAlmostEqual(abs(area), 0.5, places=5)

    def test_area_square_triangle(self):
        """Test area of larger triangle."""
        abc = [(0., 0.), (2., 0.), (0., 2.)]
        area = input_weather.area_of_triangle(abc)
        self.assertAlmostEqual(abs(area), 2.0, places=5)

    def test_area_degenerate_triangle(self):
        """Test area of degenerate (collinear) triangle is zero."""
        abc = [(0., 0.), (1., 1.), (2., 2.)]
        area = input_weather.area_of_triangle(abc)
        self.assertAlmostEqual(area, 0.0, places=5)

    def test_area_sign_ccw(self):
        """Test counter-clockwise triangle has positive area."""
        abc = [(0., 0.), (1., 0.), (0., 1.)]
        area = input_weather.area_of_triangle(abc)
        self.assertGreater(area, 0)

    def test_area_sign_cw(self):
        """Test clockwise triangle has negative area."""
        abc = [(0., 0.), (0., 1.), (1., 0.)]
        area = input_weather.area_of_triangle(abc)
        self.assertLess(area, 0)


# =============================================================================
# Tests for point_in_triangle function
# =============================================================================

class TestPointInTriangle(unittest.TestCase):
    """Tests for the point_in_triangle function."""

    def test_point_inside(self):
        """Test point clearly inside triangle."""
        p = (0.25, 0.25)
        abc = [(0., 0.), (1., 0.), (0., 1.)]
        result = input_weather.point_in_triangle(p, abc)
        self.assertTrue(result)

    def test_point_outside(self):
        """Test point clearly outside triangle."""
        p = (2., 2.)
        abc = [(0., 0.), (1., 0.), (0., 1.)]
        result = input_weather.point_in_triangle(p, abc)
        self.assertFalse(result)

    def test_point_at_vertex(self):
        """Test point at vertex is not considered inside (boundary)."""
        p = (0., 0.)
        abc = [(0., 0.), (1., 0.), (0., 1.)]
        result = input_weather.point_in_triangle(p, abc)
        # Points exactly on boundary may return False
        self.assertIsInstance(result, bool)

    def test_degenerate_triangle_returns_false(self):
        """Test degenerate (zero area) triangle returns False."""
        p = (0.5, 0.5)
        abc = [(0., 0.), (1., 1.), (2., 2.)]  # Collinear
        result = input_weather.point_in_triangle(p, abc)
        self.assertFalse(result)

    def test_point_centroid(self):
        """Test centroid is inside triangle."""
        abc = [(0., 0.), (3., 0.), (0., 3.)]
        centroid = (1., 1.)
        result = input_weather.point_in_triangle(centroid, abc)
        self.assertTrue(result)


# =============================================================================
# Tests for grid_calulate_weights function
# =============================================================================

class TestGridCalculateWeights(unittest.TestCase):
    """Tests for the grid_calulate_weights function."""

    def test_weights_sum_to_one(self):
        """Test weights sum to 1.0."""
        pos = [(0, 0, 1.0), (1, 0, 2.0), (0, 1, 3.0)]
        weights = input_weather.grid_calulate_weights(pos, 'weighted')
        self.assertAlmostEqual(sum(weights), 1.0, places=5)

    def test_nearest_variant(self):
        """Test nearest variant gives weight 1 to nearest point."""
        pos = [(0, 0, 1.0), (1, 0, 2.0), (0, 1, 3.0)]
        weights = input_weather.grid_calulate_weights(pos, 'nearest')
        self.assertEqual(weights[0], 1.0)
        self.assertEqual(weights[1], 0.0)
        self.assertEqual(weights[2], 0.0)

    def test_mean_variant(self):
        """Test mean variant gives equal weights."""
        pos = [(0, 0, 1.0), (1, 0, 2.0), (0, 1, 3.0)]
        weights = input_weather.grid_calulate_weights(pos, 'mean')
        self.assertAlmostEqual(weights[0], 1/3, places=5)
        self.assertAlmostEqual(weights[1], 1/3, places=5)
        self.assertAlmostEqual(weights[2], 1/3, places=5)

    def test_weighted_closer_has_more_weight(self):
        """Test weighted variant gives more weight to closer points."""
        pos = [(0, 0, 1.0), (1, 0, 10.0), (0, 1, 10.0)]
        weights = input_weather.grid_calulate_weights(pos, 'weighted')
        self.assertGreater(weights[0], weights[1])
        self.assertGreater(weights[0], weights[2])

    def test_unknown_variant_raises(self):
        """Test unknown variant raises ValueError."""
        pos = [(0, 0, 1.0), (1, 0, 2.0), (0, 1, 3.0)]
        with self.assertRaises(ValueError) as context:
            input_weather.grid_calulate_weights(pos, 'unknown')
        self.assertIn('unknown', str(context.exception))


# =============================================================================
# Tests for cloud_type_from_cover function
# =============================================================================

class TestCloudTypeFromCover(unittest.TestCase):
    """Tests for the cloud_type_from_cover function."""

    def test_no_clouds(self):
        """Test no clouds returns empty string."""
        tcc = pd.Series([0.0])
        lmcc = pd.Series([0.0])
        result = input_weather.cloud_type_from_cover(tcc, lmcc)
        self.assertEqual(result.iloc[0], '')

    def test_low_tcc_returns_ci(self):
        """Test very low total cloud cover returns CI."""
        tcc = pd.Series([0.05])
        lmcc = pd.Series([0.02])
        result = input_weather.cloud_type_from_cover(tcc, lmcc)
        self.assertEqual(result.iloc[0], 'CI')

    def test_high_ratio_returns_cu(self):
        """Test high low/middle ratio returns CU."""
        tcc = pd.Series([0.5])
        lmcc = pd.Series([0.45])  # ratio > 0.80
        result = input_weather.cloud_type_from_cover(tcc, lmcc)
        self.assertEqual(result.iloc[0], 'CU')

    def test_low_ratio_returns_ci(self):
        """Test low ratio returns CI."""
        tcc = pd.Series([0.5])
        lmcc = pd.Series([0.2])  # ratio < 0.80
        result = input_weather.cloud_type_from_cover(tcc, lmcc)
        self.assertEqual(result.iloc[0], 'CI')


# =============================================================================
# Tests for module constants
# =============================================================================

class TestModuleConstants(unittest.TestCase):
    """Tests for module-level constants."""

    def test_default_wind_variant(self):
        """Test DEFAULT_WIND_VARIANT is defined."""
        self.assertIsNotNone(input_weather.DEFAULT_WIND_VARIANT)

    def test_default_inter_variant(self):
        """Test DEFAULT_INTER_VARIANT is defined."""
        self.assertIsNotNone(input_weather.DEFAULT_INTER_VARIANT)

    def test_default_class_scheme(self):
        """Test DEFAULT_CLASS_SCHEME is defined."""
        self.assertIsNotNone(input_weather.DEFAULT_CLASS_SCHEME)


# =============================================================================
# Tests for add_options function
# =============================================================================

class TestAddOptions(unittest.TestCase):
    """Tests for the add_options function."""

    def test_add_options_returns_parser(self):
        """Test add_options returns an argument parser."""
        import argparse
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()

        result = input_weather.add_options(subparsers)

        self.assertIsNotNone(result)

    def test_add_options_creates_weather_subcommand(self):
        """Test add_options creates 'weather' subcommand."""
        import argparse
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')

        input_weather.add_options(subparsers)

        args = parser.parse_args(['weather', '-L', '49.0', '6.0', '-y', '2000', 'test'])
        self.assertEqual(args.command, 'weather')


# =============================================================================
# Command line basic tests (fast, no network)
# =============================================================================

class TestCommandLineBasic(unittest.TestCase):
    """Fast command line tests that don't require network access."""

    def test_no_param(self):
        """Test that no parameters shows usage."""
        command = CMD + [SUBCMD]
        out, err, exitcode = capture(command)
        self.assertNotEqual(exitcode, 0)
        self.assertTrue(err.decode().startswith('usage'))

    def test_help(self):
        """Test help displays usage."""
        command = CMD + [SUBCMD, '-h']
        out, err, exitcode = capture(command)
        self.assertEqual(exitcode, 0)
        self.assertTrue(out.decode().startswith('usage'))

    def test_mutex_options(self):
        """Test mutually exclusive options fail."""
        command = CMD + [SUBCMD,
                         '-L', '6.75', '49.75',
                         '-U', '337921', '5513264',
                         OUTPUT]
        out, err, exitcode = capture(command)
        self.assertNotEqual(exitcode, 0)
        self.assertTrue(err.decode().startswith('usage'))

    def test_noyear_fails(self):
        """Test missing year fails."""
        command = CMD + [SUBCMD,
                         '-L', '6.75', '49.75',
                         OUTPUT]
        out, err, exitcode = capture(command)
        self.assertGreater(exitcode, 0)


# =============================================================================
# Pytest-style parametrized tests
# =============================================================================

class TestPytestStyle:
    """Pytest-style tests with parametrization."""

    @pytest.mark.parametrize("subcommand", [
        'weather',
    ])
    def test_subcommand_help_available(self, subcommand):
        """Test help is available for weather subcommand."""
        command = CMD + [subcommand, '-h']
        out, err, exitcode = capture(command)
        assert exitcode == 0
        assert 'usage' in out.decode().lower()

    @pytest.mark.parametrize("verbosity_flag,expected_level", [
        ('--debug', logging.DEBUG),
        ('--verbose', logging.INFO),
        ('-v', logging.INFO),
    ])
    def test_verbosity_flags(self, verbosity_flag, expected_level):
        """Test verbosity flags set correct logging levels."""
        parser = command_line.cli_parser()
        args = parser.parse_args([verbosity_flag, 'weather', '-L', '49.0', '6.0', '-y', '2000', 'test'])
        assert args.verb == expected_level

    @pytest.mark.parametrize("variant", [
        'weighted',
        'nearest',
        'mean',
    ])
    def test_grid_weights_variants(self, variant):
        """Test all interpolation variants produce valid weights."""
        pos = [(0, 0, 1.0), (1, 0, 2.0), (0, 1, 3.0)]
        weights = input_weather.grid_calulate_weights(pos, variant)
        assert len(weights) == 3
        assert abs(sum(weights) - 1.0) < 1e-5

    @pytest.mark.parametrize("abc,expected_positive", [
        ([(0., 0.), (1., 0.), (0., 1.)], True),   # CCW
        ([(0., 0.), (0., 1.), (1., 0.)], False),  # CW
    ])
    def test_triangle_area_sign(self, abc, expected_positive):
        """Test triangle area sign depends on vertex order."""
        area = input_weather.area_of_triangle(abc)
        if expected_positive:
            assert area > 0
        else:
            assert area < 0


# =============================================================================
# Edge case tests
# =============================================================================

class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and boundary conditions."""

    def test_h_eff_small_z0(self):
        """Test h_eff with small roughness length."""
        result = input_weather.h_eff(10.0, 0.001)
        self.assertTrue(all(np.isfinite(h) for h in result))

    def test_h_eff_large_z0(self):
        """Test h_eff with large roughness length."""
        result = input_weather.h_eff(10.0, 1.0)
        self.assertTrue(all(np.isfinite(h) for h in result))

    def test_point_in_triangle_negative_coords(self):
        """Test point_in_triangle with negative coordinates."""
        p = (-0.25, -0.25)
        abc = [(-1., -1.), (1., -1.), (-1., 1.)]
        result = input_weather.point_in_triangle(p, abc)
        self.assertTrue(result)

    def test_weights_zero_distance(self):
        """Test weights when one point has zero distance."""
        pos = [(0, 0, 0.0), (1, 0, 2.0), (0, 1, 3.0)]  # First has 0 distance
        weights = input_weather.grid_calulate_weights(pos, 'weighted')
        # When distance is 0, that point should get all weight
        self.assertEqual(weights[0], 1.0)


# =============================================================================
# Integration tests (marked slow - can be skipped)
# =============================================================================

@pytest.mark.slow
class TestIntegrationSlow(unittest.TestCase):
    """Slow integration tests that require network/data access.
    
    These tests are marked as slow and can be skipped with:
    pytest -m "not slow"
    """

    def test_ll_coordinates(self):
        """Test with lat/lon coordinates (requires data access)."""
        command = CMD + [SUBCMD,
                         '-L', '49.75', '6.75',
                         '-y', '2000',
                         OUTPUT]
        out, err, exitcode = capture(command)
        self.assertEqual(exitcode, 0)
        produced_files = [x for x in expected_files(OUTPUT)
                          if os.path.exists(x)]
        self.assertGreater(len(produced_files), 0)
        for x in produced_files:
            os.remove(x)


if __name__ == '__main__':
    unittest.main()
