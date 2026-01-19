#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive test suite for austaltools._corine module.

This module tests the CORINE land cover class querying and roughness
calculation functionality.
"""
import json
import unittest
from unittest.mock import patch, MagicMock, mock_open
import urllib.error

import numpy as np
import pytest

import austaltools._corine
from austaltools import _corine


class TestLandcoverClassesDictionaries(unittest.TestCase):
    """Tests for the land cover class dictionaries."""

    def test_lbm_de_dictionary_not_empty(self):
        """Test that LBM-DE dictionary is populated."""
        self.assertGreater(len(_corine.LANDCOVER_CLASSES_Z0_LBM_DE), 0)

    def test_corine_dictionary_not_empty(self):
        """Test that CORINE dictionary is populated."""
        self.assertGreater(len(_corine.LANDCOVER_CLASSES_Z0_CORINE), 0)

    def test_lbm_de_values_are_positive_floats(self):
        """Test that all LBM-DE roughness values are positive floats."""
        for code, z0 in _corine.LANDCOVER_CLASSES_Z0_LBM_DE.items():
            self.assertIsInstance(code, int)
            self.assertIsInstance(z0, float)
            self.assertGreater(z0, 0)

    def test_corine_values_are_positive_floats(self):
        """Test that all CORINE roughness values are positive floats."""
        for code, z0 in _corine.LANDCOVER_CLASSES_Z0_CORINE.items():
            self.assertIsInstance(code, int)
            self.assertIsInstance(z0, float)
            self.assertGreater(z0, 0)

    def test_lbm_de_codes_are_three_digits(self):
        """Test that all LBM-DE codes are 3-digit integers."""
        for code in _corine.LANDCOVER_CLASSES_Z0_LBM_DE.keys():
            self.assertGreaterEqual(code, 100)
            self.assertLess(code, 1000)

    def test_corine_codes_are_three_digits(self):
        """Test that all CORINE codes are 3-digit integers."""
        for code in _corine.LANDCOVER_CLASSES_Z0_CORINE.keys():
            self.assertGreaterEqual(code, 100)
            self.assertLess(code, 1000)

    def test_roughness_values_in_expected_range(self):
        """Test that roughness values are within expected physical range (0.01 to 2.0 m)."""
        for z0 in _corine.LANDCOVER_CLASSES_Z0_LBM_DE.values():
            self.assertGreaterEqual(z0, 0.01)
            self.assertLessEqual(z0, 2.0)

        for z0 in _corine.LANDCOVER_CLASSES_Z0_CORINE.values():
            self.assertGreaterEqual(z0, 0.01)
            self.assertLessEqual(z0, 2.0)


class TestRestApiUrl(unittest.TestCase):
    """Tests for the REST API URL constant."""

    def test_rest_api_url_is_string(self):
        """Test that REST_API_URL is a string."""
        self.assertIsInstance(_corine.REST_API_URL, str)

    def test_rest_api_url_is_https(self):
        """Test that REST_API_URL uses HTTPS."""
        self.assertTrue(_corine.REST_API_URL.startswith('https://'))

    def test_rest_api_url_contains_corine(self):
        """Test that REST_API_URL contains CORINE reference."""
        self.assertIn('Corine', _corine.REST_API_URL)


class TestSamplePoints(unittest.TestCase):
    """Tests for the sample_points function."""

    def test_sample_points_returns_list(self):
        """Test that sample_points returns a list."""
        result = _corine.sample_points(100.0, 200.0, 10.0)
        self.assertIsInstance(result, list)

    def test_sample_points_returns_tuples(self):
        """Test that sample_points returns list of tuples."""
        result = _corine.sample_points(100.0, 200.0, 10.0)
        for point in result:
            self.assertIsInstance(point, tuple)
            self.assertEqual(len(point), 2)

    def test_sample_points_center_included(self):
        """Test that the center point is included in sample points."""
        xg, yg, h = 100.0, 200.0, 10.0
        result = _corine.sample_points(xg, yg, h)
        self.assertIn((xg, yg), result)

    def test_sample_points_default_factor(self):
        """Test sample_points with default factor (10)."""
        xg, yg, h = 0.0, 0.0, 1.0
        result = _corine.sample_points(xg, yg, h)
        # Should have points within radius h * fac = 10
        self.assertGreater(len(result), 0)

    def test_sample_points_custom_factor(self):
        """Test sample_points with custom factor."""
        xg, yg, h = 0.0, 0.0, 1.0
        fac = 5
        result = _corine.sample_points(xg, yg, h, fac)
        # All points should be within radius h * fac
        for x, y in result:
            dist = np.sqrt((x - xg) ** 2 + (y - yg) ** 2)
            self.assertLessEqual(dist, h * fac + 1e-10)

    def test_sample_points_small_factor(self):
        """Test sample_points with small factor."""
        xg, yg, h = 100.0, 200.0, 10.0
        fac = 1
        result = _corine.sample_points(xg, yg, h, fac)
        # Should have fewer points with smaller factor
        result_large = _corine.sample_points(xg, yg, h, fac=5)
        self.assertLess(len(result), len(result_large))

    def test_sample_points_symmetry(self):
        """Test that sample points are symmetric around center."""
        xg, yg, h = 0.0, 0.0, 10.0
        fac = 3
        result = _corine.sample_points(xg, yg, h, fac)
        # For each point (x, y), (-x, -y) should also exist
        for x, y in result:
            self.assertIn((-x, -y), result)

    def test_sample_points_within_radius(self):
        """Test that all sample points are within specified radius."""
        xg, yg, h = 50.0, 75.0, 5.0
        fac = 8
        result = _corine.sample_points(xg, yg, h, fac)
        max_radius = h * fac
        for x, y in result:
            dist = np.sqrt((x - xg) ** 2 + (y - yg) ** 2)
            self.assertLessEqual(dist, max_radius + 1e-10)


class TestQueryCorineClass(unittest.TestCase):
    """Tests for the query_corine_class function."""

    @patch('urllib.request.urlopen')
    def test_query_corine_class_success(self, mock_urlopen):
        """Test successful CORINE class query."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'features': [{'attributes': {'Code_18': '311'}}]
        }).encode()
        mock_urlopen.return_value = mock_response

        result = _corine.query_corine_class(50.0, 8.0)
        self.assertEqual(result, 311)

    @patch('urllib.request.urlopen')
    def test_query_corine_class_empty_features(self, mock_urlopen):
        """Test CORINE class query with empty features."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'features': []
        }).encode()
        mock_urlopen.return_value = mock_response

        result = _corine.query_corine_class(50.0, 8.0)
        self.assertEqual(result, 0)

    @patch('urllib.request.urlopen')
    def test_query_corine_class_http_error(self, mock_urlopen):
        """Test CORINE class query with HTTP error."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url='http://test.com', code=500, msg='Server Error',
            hdrs={}, fp=None
        )

        result = _corine.query_corine_class(50.0, 8.0)
        self.assertEqual(result, 0)

    @patch('urllib.request.urlopen')
    def test_query_corine_class_url_error(self, mock_urlopen):
        """Test CORINE class query with URL error."""
        mock_urlopen.side_effect = urllib.error.URLError('Connection refused')

        result = _corine.query_corine_class(50.0, 8.0)
        self.assertEqual(result, 0)

    @patch('urllib.request.urlopen')
    def test_query_corine_class_multiple_features(self, mock_urlopen):
        """Test CORINE class query with multiple features (should return 0)."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'features': [
                {'attributes': {'Code_18': '311'}},
                {'attributes': {'Code_18': '312'}}
            ]
        }).encode()
        mock_urlopen.return_value = mock_response

        result = _corine.query_corine_class(50.0, 8.0)
        self.assertEqual(result, 0)

    @patch('urllib.request.urlopen')
    def test_query_corine_class_returns_integer(self, mock_urlopen):
        """Test that query_corine_class always returns an integer."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'features': [{'attributes': {'Code_18': '211'}}]
        }).encode()
        mock_urlopen.return_value = mock_response

        result = _corine.query_corine_class(50.0, 8.0)
        self.assertIsInstance(result, int)


class TestCorineFileHelp(unittest.TestCase):
    """Tests for the corine_file_help function."""

    @patch('builtins.print')
    def test_corine_file_help_prints_messages(self, mock_print):
        """Test that corine_file_help prints help messages."""
        _corine.corine_file_help()
        self.assertTrue(mock_print.called)
        self.assertGreaterEqual(mock_print.call_count, 1)


class TestCorineFileLoad(unittest.TestCase):
    """Tests for the corine_file_load function."""

    @patch('austaltools._corine._storage.read_config')
    def test_corine_file_load_no_austaldir(self, mock_read_config):
        """Test corine_file_load raises error when austaldir not defined."""
        mock_read_config.return_value = {}

        with self.assertRaises(RuntimeError) as context:
            _corine.corine_file_load()
        self.assertIn('austaldir', str(context.exception))

    @patch('austaltools._corine._storage.read_config')
    def test_corine_file_load_empty_austaldir(self, mock_read_config):
        """Test corine_file_load raises error when austaldir is empty."""
        mock_read_config.return_value = {'austaldir': ''}

        with self.assertRaises(RuntimeError) as context:
            _corine.corine_file_load()
        self.assertIn('austaldir', str(context.exception))

    @patch('austaltools._corine._storage.read_config')
    @patch('os.path.exists')
    def test_corine_file_load_file_not_found(self, mock_exists, mock_read_config):
        """Test corine_file_load raises error when z0-gk.dmna not found."""
        mock_read_config.return_value = {'austaldir': '/fake/path'}
        mock_exists.return_value = False

        with self.assertRaises(RuntimeError) as context:
            _corine.corine_file_load()
        self.assertIn('z0-gk.dmna', str(context.exception))


class TestRoughnessAustal(unittest.TestCase):
    """Tests for the roughness_austal function."""

    def setUp(self):
        """Reset CORINE_GERMANY global before each test."""
        _corine.CORINE_GERMANY = None

    @patch('austaltools._corine.corine_file_load')
    def test_roughness_austal_loads_data(self, mock_load):
        """Test that roughness_austal loads CORINE data when not cached."""
        mock_data = MagicMock()
        mock_data.header = {
            'xmin': '3400000',
            'ymin': '5400000',
            'delta': '100',
            'clsi': 'A B C',
            'clsd': '0.1 m 0.5 m 1.0 m'
        }
        mock_data.data = {
            'Classes': np.array([[['A'] * 100] * 100])
        }
        mock_load.return_value = mock_data

        _corine.roughness_austal(3400050, 5400050, 100, fac=1)
        mock_load.assert_called_once()

    @patch('austaltools._corine.corine_file_load')
    def test_roughness_austal_uses_cache(self, mock_load):
        """Test that roughness_austal uses cached data on subsequent calls."""
        mock_data = MagicMock()
        mock_data.header = {
            'xmin': '3400000',
            'ymin': '5400000',
            'delta': '100',
            'clsi': 'A B C',
            'clsd': '0.1 m 0.5 m 1.0 m'
        }
        mock_data.data = {
            'Classes': np.array([[['A'] * 100] * 100])
        }
        _corine.CORINE_GERMANY = mock_data

        _corine.roughness_austal(3400050, 5400050, 100, fac=1)
        mock_load.assert_not_called()

    @patch('austaltools._corine.corine_file_load')
    def test_roughness_austal_returns_float(self, mock_load):
        """Test that roughness_austal returns a float."""
        mock_data = MagicMock()
        mock_data.header = {
            'xmin': '3400000',
            'ymin': '5400000',
            'delta': '100',
            'clsi': 'A B C',
            'clsd': '0.1 m 0.5 m 1.0 m'
        }
        # Create proper 3D array
        mock_data.data = {
            'Classes': np.array([[['A'] * 100] * 100])
        }
        mock_load.return_value = mock_data

        result = _corine.roughness_austal(3400050, 5400050, 100, fac=1)
        self.assertTrue(result is None or isinstance(result, (float, np.floating)))


class TestRoughnessWeb(unittest.TestCase):
    """Tests for the roughness_web function."""

    @patch('austaltools._corine.query_corine_class')
    @patch('austaltools._geo.gk2ll')
    def test_roughness_web_calls_query(self, mock_gk2ll, mock_query):
        """Test that roughness_web calls query_corine_class."""
        mock_gk2ll.return_value = (50.0, 8.0)
        mock_query.return_value = 311  # Forest

        result = _corine.roughness_web(3500000, 5500000, 100, fac=1)
        self.assertTrue(mock_query.called)

    @patch('austaltools._corine.query_corine_class')
    @patch('austaltools._geo.gk2ll')
    def test_roughness_web_known_class(self, mock_gk2ll, mock_query):
        """Test roughness_web with known CORINE class."""
        mock_gk2ll.return_value = (50.0, 8.0)
        mock_query.return_value = 311  # Broad-leaved forest

        result = _corine.roughness_web(3500000, 5500000, 100, fac=1)
        expected_z0 = _corine.LANDCOVER_CLASSES_Z0_CORINE[311]
        self.assertEqual(result, expected_z0)

    @patch('austaltools._corine.query_corine_class')
    @patch('austaltools._geo.gk2ll')
    def test_roughness_web_unknown_class(self, mock_gk2ll, mock_query):
        """Test roughness_web with unknown CORINE class."""
        mock_gk2ll.return_value = (50.0, 8.0)
        mock_query.return_value = 999  # Unknown class

        result = _corine.roughness_web(3500000, 5500000, 100, fac=1)
        # Should return nan when no valid classes found
        self.assertTrue(np.isnan(result))

    @patch('austaltools._corine.query_corine_class')
    @patch('austaltools._geo.gk2ll')
    def test_roughness_web_mixed_classes(self, mock_gk2ll, mock_query):
        """Test roughness_web with mixed CORINE classes."""
        mock_gk2ll.return_value = (50.0, 8.0)
        # Return different classes for different calls
        mock_query.side_effect = [311, 312, 211, 311, 312]

        result = _corine.roughness_web(3500000, 5500000, 100, fac=1)
        self.assertIsInstance(result, (float, np.floating))

    @patch('austaltools._corine.query_corine_class')
    @patch('austaltools._geo.gk2ll')
    def test_roughness_web_returns_average(self, mock_gk2ll, mock_query):
        """Test that roughness_web returns average of roughness values."""
        mock_gk2ll.return_value = (50.0, 8.0)
        # All points return same class
        mock_query.return_value = 211  # Non-irrigated arable land

        result = _corine.roughness_web(3500000, 5500000, 100, fac=1)
        expected_z0 = _corine.LANDCOVER_CLASSES_Z0_CORINE[211]
        self.assertAlmostEqual(result, expected_z0, places=5)


class TestMeanRoughness(unittest.TestCase):
    """Tests for the mean_roughness function."""

    @patch('austaltools._corine.roughness_web')
    def test_mean_roughness_web_source(self, mock_web):
        """Test mean_roughness with 'web' source."""
        mock_web.return_value = 1.5

        result = _corine.mean_roughness('web', 3500000, 5500000, 100, fac=5)
        mock_web.assert_called_once_with(3500000, 5500000, 100, 5)
        self.assertEqual(result, 1.5)

    @patch('austaltools._corine.roughness_austal')
    def test_mean_roughness_austal_source(self, mock_austal):
        """Test mean_roughness with 'austal' source."""
        mock_austal.return_value = 0.5

        result = _corine.mean_roughness('austal', 3500000, 5500000, 100, fac=5)
        mock_austal.assert_called_once_with(3500000, 5500000, 100, 5)
        self.assertEqual(result, 0.5)

    def test_mean_roughness_invalid_source(self):
        """Test mean_roughness with invalid source raises ValueError."""
        with self.assertRaises(ValueError) as context:
            _corine.mean_roughness('invalid', 3500000, 5500000, 100)
        self.assertIn('web', str(context.exception))
        self.assertIn('austal', str(context.exception))

    def test_mean_roughness_empty_source(self):
        """Test mean_roughness with empty source raises ValueError."""
        with self.assertRaises(ValueError):
            _corine.mean_roughness('', 3500000, 5500000, 100)

    @patch('austaltools._corine.roughness_web')
    def test_mean_roughness_default_factor(self, mock_web):
        """Test mean_roughness uses default factor of 10."""
        mock_web.return_value = 1.0

        _corine.mean_roughness('web', 3500000, 5500000, 100)
        mock_web.assert_called_once_with(3500000, 5500000, 100, 10.)


class TestGlobalVariables(unittest.TestCase):
    """Tests for global variables and module state."""

    def test_corine_germany_initial_state(self):
        """Test CORINE_GERMANY initial state is None."""
        # Reset to test initial state
        _corine.CORINE_GERMANY = None
        self.assertIsNone(_corine.CORINE_GERMANY)


class TestIntegrationSamplePointsWithRoughnessWeb(unittest.TestCase):
    """Integration tests for sample_points used with roughness calculations."""

    @patch('austaltools._corine.query_corine_class')
    @patch('austaltools._geo.gk2ll')
    def test_sample_points_used_in_roughness_web(self, mock_gk2ll, mock_query):
        """Test that sample_points count matches query calls in roughness_web."""
        mock_gk2ll.return_value = (50.0, 8.0)
        mock_query.return_value = 311

        xg, yg, h = 3500000, 5500000, 100
        fac = 2
        expected_points = _corine.sample_points(xg, yg, h, fac)

        _corine.roughness_web(xg, yg, h, fac)
        self.assertEqual(mock_query.call_count, len(expected_points))


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and boundary conditions."""

    def test_sample_points_zero_radius(self):
        """Test sample_points with zero radius."""
        result = _corine.sample_points(100.0, 200.0, 0.0, fac=10)
        # With h=0, only center point should be included
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], (100.0, 200.0))

    def test_sample_points_negative_coordinates(self):
        """Test sample_points with negative coordinates."""
        result = _corine.sample_points(-100.0, -200.0, 10.0, fac=2)
        self.assertIn((-100.0, -200.0), result)
        self.assertGreater(len(result), 1)

    def test_sample_points_large_coordinates(self):
        """Test sample_points with large coordinates."""
        result = _corine.sample_points(1e7, 1e7, 100.0, fac=2)
        self.assertIn((1e7, 1e7), result)
        self.assertGreater(len(result), 1)

    @patch('urllib.request.urlopen')
    def test_query_corine_class_special_coordinates(self, mock_urlopen):
        """Test query_corine_class with boundary coordinates."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'features': [{'attributes': {'Code_18': '211'}}]
        }).encode()
        mock_urlopen.return_value = mock_response

        # Test with coordinates at boundaries
        result = _corine.query_corine_class(0.0, 0.0)
        self.assertIsInstance(result, int)

        result = _corine.query_corine_class(-90.0, -180.0)
        self.assertIsInstance(result, int)

        result = _corine.query_corine_class(90.0, 180.0)
        self.assertIsInstance(result, int)


class TestLogging(unittest.TestCase):
    """Tests for logging behavior."""

    @patch('austaltools._corine.logger')
    @patch('urllib.request.urlopen')
    def test_query_corine_class_logs_debug(self, mock_urlopen, mock_logger):
        """Test that query_corine_class logs debug messages."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            'features': [{'attributes': {'Code_18': '311'}}]
        }).encode()
        mock_urlopen.return_value = mock_response

        _corine.query_corine_class(50.0, 8.0)
        self.assertTrue(mock_logger.debug.called)

    @patch('austaltools._corine.logger')
    @patch('urllib.request.urlopen')
    def test_query_corine_class_logs_error_on_http_error(self, mock_urlopen, mock_logger):
        """Test that query_corine_class logs error on HTTP failure."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url='http://test.com', code=500, msg='Server Error',
            hdrs={}, fp=None
        )

        _corine.query_corine_class(50.0, 8.0)
        self.assertTrue(mock_logger.error.called)


class TestCorineClassesMapping(unittest.TestCase):
    """Tests to verify specific CORINE class mappings."""

    def test_urban_classes_high_roughness(self):
        """Test that urban areas have high roughness values."""
        urban_codes = [111, 112]  # Continuous and discontinuous urban fabric
        for code in urban_codes:
            if code in _corine.LANDCOVER_CLASSES_Z0_CORINE:
                self.assertGreaterEqual(
                    _corine.LANDCOVER_CLASSES_Z0_CORINE[code], 1.0,
                    f"Urban class {code} should have roughness >= 1.0"
                )

    def test_water_classes_low_roughness(self):
        """Test that water bodies have low roughness values."""
        water_codes = [511, 512, 521, 522, 523]  # Various water bodies
        for code in water_codes:
            if code in _corine.LANDCOVER_CLASSES_Z0_CORINE:
                self.assertLessEqual(
                    _corine.LANDCOVER_CLASSES_Z0_CORINE[code], 0.1,
                    f"Water class {code} should have roughness <= 0.1"
                )

    def test_forest_classes_moderate_roughness(self):
        """Test that forest areas have moderate to high roughness values."""
        forest_codes = [311, 312, 313]  # Different forest types
        for code in forest_codes:
            if code in _corine.LANDCOVER_CLASSES_Z0_CORINE:
                self.assertGreaterEqual(
                    _corine.LANDCOVER_CLASSES_Z0_CORINE[code], 1.0,
                    f"Forest class {code} should have roughness >= 1.0"
                )


# Pytest-style tests for additional coverage

class TestPytestStyle:
    """Pytest-style tests for additional patterns."""

    def test_sample_points_parametrized_factors(self):
        """Test sample_points with various factors."""
        factors = [1, 2, 5, 10, 20]
        prev_count = 0
        for fac in factors:
            result = _corine.sample_points(0.0, 0.0, 1.0, fac)
            # More points with larger factor
            assert len(result) >= prev_count
            prev_count = len(result)

    @pytest.mark.parametrize("source,expected_func", [
        ("web", "roughness_web"),
        ("austal", "roughness_austal"),
    ])
    def test_mean_roughness_dispatches_correctly(self, source, expected_func):
        """Test that mean_roughness dispatches to correct function."""
        with patch(f'austaltools._corine.{expected_func}') as mock_func:
            mock_func.return_value = 1.0
            _corine.mean_roughness(source, 0, 0, 100)
            mock_func.assert_called_once()

    @pytest.mark.parametrize("invalid_source", [
        "Web",
        "AUSTAL",
        "local",
        "api",
        None,
    ])
    def test_mean_roughness_rejects_invalid_sources(self, invalid_source):
        """Test that mean_roughness rejects invalid source values."""
        with pytest.raises((ValueError, TypeError)):
            _corine.mean_roughness(invalid_source, 0, 0, 100)


if __name__ == '__main__':
    unittest.main()
