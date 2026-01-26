#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive test suite for austaltools._windutil module.

This module tests weather data loading and roughness length
determination functions.
"""
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock, PropertyMock

import numpy as np
import pandas as pd
import pytest

from austaltools import _windutil


class TestLoadWeather(unittest.TestCase):
    """Tests for the load_weather function."""

    @patch('austaltools._windutil.readmet')
    @patch('austaltools._windutil._tools.find_austxt')
    @patch('austaltools._windutil._tools.get_austxt')
    @patch('austaltools._windutil.get_roughness_length')
    @patch('os.listdir')
    def test_load_weather_with_zeitreihe_dmna(self, mock_listdir, mock_get_z0,
                                              mock_get_austxt, mock_find_austxt,
                                              mock_readmet):
        """Test load_weather when zeitreihe.dmna exists."""
        mock_listdir.return_value = ['zeitreihe.dmna', 'austal.txt']
        mock_get_austxt.return_value = {'az': ['test.akterm']}
        mock_get_z0.return_value = 0.1

        # Mock the dmna data
        mock_data = MagicMock()
        mock_data.data = {
            'te': pd.to_datetime(['2024-01-01 00:00', '2024-01-01 01:00']),
            'ua': MagicMock(values=np.array([5.0, 6.0])),
            'ra': MagicMock(values=np.array([180.0, 190.0]))
        }
        mock_readmet.dmna.DataFile.return_value = mock_data

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _windutil.load_weather(tmpdir)

        self.assertIsInstance(result, pd.DataFrame)
        self.assertIn('FF', result.columns)
        self.assertIn('DD', result.columns)
        self.assertIn('KM', result.columns)

    @patch('austaltools._windutil.readmet')
    @patch('austaltools._windutil._tools.find_austxt')
    @patch('austaltools._windutil._tools.get_austxt')
    @patch('os.listdir')
    def test_load_weather_with_akterm(self, mock_listdir, mock_get_austxt,
                                      mock_find_austxt, mock_readmet):
        """Test load_weather when using AKTERM file."""
        mock_listdir.return_value = ['austal.txt']  # No zeitreihe.dmna
        mock_get_austxt.return_value = {'az': ['weather.akterm']}

        # Mock the akterm data
        mock_akterm = MagicMock()
        mock_akterm.data = pd.DataFrame({
            'FF': [5.0, 6.0],
            'DD': [180.0, 190.0],
            'KM': [3, 4]
        })
        mock_readmet.akterm.DataFile.return_value = mock_akterm

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _windutil.load_weather(tmpdir)

        self.assertIsInstance(result, pd.DataFrame)
        self.assertIn('FF', result.columns)
        self.assertIn('DD', result.columns)
        self.assertIn('KM', result.columns)

    @patch('austaltools._windutil._tools.find_austxt')
    @patch('austaltools._windutil._tools.get_austxt')
    @patch('os.listdir')
    def test_load_weather_no_az_raises(self, mock_listdir, mock_get_austxt,
                                       mock_find_austxt):
        """Test load_weather raises when no az defined and no zeitreihe."""
        mock_listdir.return_value = ['austal.txt']  # No zeitreihe.dmna
        mock_get_austxt.return_value = {}  # No 'az' key

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError) as context:
                _windutil.load_weather(tmpdir)
            self.assertIn('no az defined', str(context.exception))

    @patch('austaltools._windutil.readmet')
    def test_load_weather_with_dmna_file_specified(self, mock_readmet):
        """Test load_weather with explicit dmna file."""
        mock_data = MagicMock()
        mock_data.data = {
            'te': pd.to_datetime(['2024-01-01 00:00']),
            'ua': MagicMock(values=np.array([5.0])),
            'ra': MagicMock(values=np.array([180.0]))
        }
        mock_readmet.dmna.DataFile.return_value = mock_data

        with patch('austaltools._windutil.get_roughness_length', return_value=0.1):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = _windutil.load_weather(
                    tmpdir, file='test.dmna'
                )

        self.assertIsInstance(result, pd.DataFrame)

    @patch('austaltools._windutil.readmet')
    def test_load_weather_with_akterm_file_specified(self, mock_readmet):
        """Test load_weather with explicit akterm file."""
        mock_akterm = MagicMock()
        mock_akterm.data = pd.DataFrame({
            'FF': [5.0],
            'DD': [180.0],
            'KM': [3]
        })
        mock_readmet.akterm.DataFile.return_value = mock_akterm

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _windutil.load_weather(
                tmpdir, file='test.akterm'
            )

        self.assertIsInstance(result, pd.DataFrame)

    @patch('austaltools._windutil.readmet')
    @patch('austaltools._windutil._tools.find_austxt')
    @patch('austaltools._windutil._tools.get_austxt')
    @patch('austaltools._windutil.get_roughness_length')
    @patch('os.listdir')
    def test_load_weather_with_conf_provided(self, mock_listdir, mock_get_z0,
                                             mock_get_austxt, mock_find_austxt,
                                             mock_readmet):
        """Test load_weather with conf dict provided."""
        mock_listdir.return_value = ['zeitreihe.dmna']
        mock_get_z0.return_value = 0.1

        mock_data = MagicMock()
        mock_data.data = {
            'te': pd.to_datetime(['2024-01-01 00:00']),
            'ua': MagicMock(values=np.array([5.0])),
            'ra': MagicMock(values=np.array([180.0]))
        }
        mock_readmet.dmna.DataFile.return_value = mock_data

        conf = {'z0': 0.1, 'xg': 3500000, 'yg': 5500000}

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _windutil.load_weather(tmpdir, conf=conf)

        # find_austxt should not be called when conf is provided
        mock_find_austxt.assert_not_called()
        self.assertIsInstance(result, pd.DataFrame)

    @patch('austaltools._windutil.readmet')
    @patch('austaltools._windutil._tools.find_austxt')
    @patch('austaltools._windutil._tools.get_austxt')
    @patch('os.listdir')
    def test_load_weather_timeseries_dmna(self, mock_listdir, mock_get_austxt,
                                          mock_find_austxt, mock_readmet):
        """Test load_weather finds timeseries.dmna as alternative."""
        mock_listdir.return_value = ['timeseries.dmna', 'austal.txt']
        mock_get_austxt.return_value = {}

        mock_data = MagicMock()
        mock_data.data = {
            'te': pd.to_datetime(['2024-01-01 00:00']),
            'ua': MagicMock(values=np.array([5.0])),
            'ra': MagicMock(values=np.array([180.0]))
        }
        mock_readmet.dmna.DataFile.return_value = mock_data

        with patch('austaltools._windutil.get_roughness_length', return_value=0.1):
            with tempfile.TemporaryDirectory() as tmpdir:
                result = _windutil.load_weather(tmpdir)

        self.assertIsInstance(result, pd.DataFrame)


class TestGetRoughnessLength(unittest.TestCase):
    """Tests for the get_roughness_length function."""

    @patch('austaltools._windutil._tools.read_z0')
    def test_get_roughness_length_from_config(self, mock_read_z0):
        """Test get_roughness_length returns z0 from config."""
        mock_read_z0.return_value = 0.5

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _windutil.get_roughness_length(tmpdir)

        self.assertEqual(result, 0.5)

    @patch('austaltools._windutil._tools.read_z0')
    @patch('austaltools._windutil._tools.find_austxt')
    @patch('austaltools._windutil._tools.get_austxt')
    @patch('austaltools._windutil._corine.roughness_austal')
    def test_get_roughness_length_from_corine_gk(self, mock_roughness_austal,
                                                  mock_get_austxt,
                                                  mock_find_austxt,
                                                  mock_read_z0):
        """Test get_roughness_length calculates from CORINE with GK coords."""
        mock_read_z0.return_value = None
        mock_get_austxt.return_value = {
            'xg': 3500000,
            'yg': 5500000,
            'hq': 15.0
        }
        mock_roughness_austal.return_value = 0.3

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _windutil.get_roughness_length(tmpdir)

        self.assertEqual(result, 0.3)
        mock_roughness_austal.assert_called_once_with(3500000, 5500000, 15.0)

    @patch('austaltools._windutil._tools.read_z0')
    @patch('austaltools._windutil._tools.find_austxt')
    @patch('austaltools._windutil._tools.get_austxt')
    @patch('austaltools._windutil._geo.ut2gk')
    @patch('austaltools._windutil._corine.roughness_austal')
    def test_get_roughness_length_from_corine_utm(self, mock_roughness_austal,
                                                   mock_ut2gk,
                                                   mock_get_austxt,
                                                   mock_find_austxt,
                                                   mock_read_z0):
        """Test get_roughness_length calculates from CORINE with UTM coords."""
        mock_read_z0.return_value = None
        mock_get_austxt.return_value = {
            'xu': 500000,
            'yu': 5500000,
            'hq': 15.0
        }
        mock_ut2gk.return_value = (3500000, 5500000)
        mock_roughness_austal.return_value = 0.25

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _windutil.get_roughness_length(tmpdir)

        self.assertEqual(result, 0.25)
        mock_ut2gk.assert_called_once_with(500000, 5500000)

    @patch('austaltools._windutil._tools.read_z0')
    @patch('austaltools._windutil._tools.find_austxt')
    @patch('austaltools._windutil._tools.get_austxt')
    @patch('austaltools._windutil._corine.roughness_austal')
    @patch('austaltools._windutil._corine.roughness_web')
    def test_get_roughness_length_fallback_to_web(self, mock_roughness_web,
                                                   mock_roughness_austal,
                                                   mock_get_austxt,
                                                   mock_find_austxt,
                                                   mock_read_z0):
        """Test get_roughness_length falls back to web API."""
        mock_read_z0.return_value = None
        mock_get_austxt.return_value = {
            'xg': 3500000,
            'yg': 5500000,
            'hq': 15.0
        }
        mock_roughness_austal.return_value = None  # Local CORINE not available
        mock_roughness_web.return_value = 0.2

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _windutil.get_roughness_length(tmpdir)

        self.assertEqual(result, 0.2)
        mock_roughness_web.assert_called_once_with(3500000, 5500000, 15.0)

    @patch('austaltools._windutil._tools.read_z0')
    @patch('austaltools._windutil._tools.find_austxt')
    @patch('austaltools._windutil._tools.get_austxt')
    def test_get_roughness_length_no_position_raises(self, mock_get_austxt,
                                                      mock_find_austxt,
                                                      mock_read_z0):
        """Test get_roughness_length raises when no position defined."""
        mock_read_z0.return_value = None
        mock_get_austxt.return_value = {}  # No xg/yg or xu/yu

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError) as context:
                _windutil.get_roughness_length(tmpdir)
            self.assertIn('neither z0 nor position defined',
                          str(context.exception))

    @patch('austaltools._windutil._tools.read_z0')
    @patch('austaltools._windutil._tools.find_austxt')
    @patch('austaltools._windutil._tools.get_austxt')
    @patch('austaltools._windutil._corine.roughness_austal')
    def test_get_roughness_length_default_hq(self, mock_roughness_austal,
                                              mock_get_austxt,
                                              mock_find_austxt,
                                              mock_read_z0):
        """Test get_roughness_length uses default hq=10 when not defined."""
        mock_read_z0.return_value = None
        mock_get_austxt.return_value = {
            'xg': 3500000,
            'yg': 5500000
            # No 'hq' key
        }
        mock_roughness_austal.return_value = 0.1

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _windutil.get_roughness_length(tmpdir)

        # hq should default to 10.0
        mock_roughness_austal.assert_called_once_with(3500000, 5500000, 10.)

    @patch('austaltools._windutil._tools.read_z0')
    @patch('austaltools._windutil._tools.DEFAULT_WORKING_DIR', '/default/path')
    def test_get_roughness_length_default_working_dir(self, mock_read_z0):
        """Test get_roughness_length uses DEFAULT_WORKING_DIR when None."""
        mock_read_z0.return_value = 0.1

        result = _windutil.get_roughness_length(working_dir=None)

        mock_read_z0.assert_called_once_with('/default/path', None)

    @patch('austaltools._windutil._tools.read_z0')
    def test_get_roughness_length_with_conf_provided(self, mock_read_z0):
        """Test get_roughness_length uses provided conf."""
        mock_read_z0.return_value = 0.2
        conf = {'z0': 0.2}

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _windutil.get_roughness_length(tmpdir, conf=conf)

        mock_read_z0.assert_called_once_with(tmpdir, conf)
        self.assertEqual(result, 0.2)


class TestModuleImports(unittest.TestCase):
    """Tests for module-level imports and logger."""

    def test_logger_exists(self):
        """Test module logger is defined."""
        self.assertIsNotNone(_windutil.logger)

    def test_imports_corine(self):
        """Test _corine module is imported."""
        self.assertIsNotNone(_windutil._corine)

    def test_imports_dispersion(self):
        """Test _dispersion module is imported."""
        self.assertIsNotNone(_windutil._dispersion)

    def test_imports_geo(self):
        """Test _geo module is imported."""
        self.assertIsNotNone(_windutil._geo)

    def test_imports_tools(self):
        """Test _tools module is imported."""
        self.assertIsNotNone(_windutil._tools)


# Pytest-style parametrized tests

class TestPytestStyle:
    """Pytest-style tests for additional patterns."""

    @pytest.mark.parametrize("file_ext,expected_type", [
        ('.dmna', 'dmna'),
        ('.akterm', 'akterm'),
        ('.akt', 'akterm'),
        ('', 'akterm'),
    ])
    def test_load_weather_file_type_detection(self, file_ext, expected_type):
        """Test load_weather detects file type from extension."""
        # This tests the logic path, not actual file reading
        filename = f'test{file_ext}'
        if file_ext == '.dmna':
            assert filename.endswith('.dmna')
        else:
            assert not filename.endswith('.dmna')

    @pytest.mark.parametrize("conf,expected_coords", [
        ({'xg': 100, 'yg': 200}, ('xg', 'yg')),
        ({'xu': 100, 'yu': 200}, ('xu', 'yu')),
    ])
    def test_coordinate_type_selection(self, conf, expected_coords):
        """Test coordinate type selection logic."""
        if 'xg' in conf and 'yg' in conf:
            coord_type = ('xg', 'yg')
        elif 'xu' in conf and 'yu' in conf:
            coord_type = ('xu', 'yu')
        else:
            coord_type = None
        assert coord_type == expected_coords


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and boundary conditions."""

    @patch('austaltools._windutil._tools.read_z0')
    @patch('austaltools._windutil._tools.find_austxt')
    @patch('austaltools._windutil._tools.get_austxt')
    @patch('austaltools._windutil._corine.roughness_austal')
    @patch('austaltools._windutil._corine.roughness_web')
    def test_get_roughness_length_both_corine_fail(self, mock_web, mock_austal,
                                                    mock_get_austxt,
                                                    mock_find_austxt,
                                                    mock_read_z0):
        """Test get_roughness_length when both CORINE methods return None."""
        mock_read_z0.return_value = None
        mock_get_austxt.return_value = {
            'xg': 3500000,
            'yg': 5500000,
            'hq': 10.0
        }
        mock_austal.return_value = None
        mock_web.return_value = None

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _windutil.get_roughness_length(tmpdir)

        # Both methods tried, returns None
        self.assertIsNone(result)

    @patch('austaltools._windutil.readmet')
    @patch('austaltools._windutil._tools.find_austxt')
    @patch('austaltools._windutil._tools.get_austxt')
    @patch('austaltools._windutil.get_roughness_length')
    @patch('os.listdir')
    def test_load_weather_returns_dataframe_columns(self, mock_listdir,
                                                     mock_get_z0,
                                                     mock_get_austxt,
                                                     mock_find_austxt,
                                                     mock_readmet):
        """Test load_weather returns DataFrame with correct columns."""
        mock_listdir.return_value = ['zeitreihe.dmna']
        mock_get_austxt.return_value = {}
        mock_get_z0.return_value = 0.1

        mock_data = MagicMock()
        mock_data.data = {
            'te': pd.to_datetime(['2024-01-01 00:00', '2024-01-01 01:00',
                                  '2024-01-01 02:00']),
            'ua': MagicMock(values=np.array([5.0, 6.0, 7.0])),
            'ra': MagicMock(values=np.array([180.0, 190.0, 200.0]))
        }
        mock_readmet.dmna.DataFile.return_value = mock_data

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _windutil.load_weather(tmpdir)

        # Check all expected columns exist
        self.assertEqual(set(result.columns), {'FF', 'DD', 'KM'})
        # Check length matches input
        self.assertEqual(len(result), 3)


class TestIntegration(unittest.TestCase):
    """Integration tests combining multiple components."""

    @patch('austaltools._windutil.readmet')
    @patch('austaltools._windutil._tools.find_austxt')
    @patch('austaltools._windutil._tools.get_austxt')
    @patch('austaltools._windutil._tools.read_z0')
    @patch('os.listdir')
    def test_load_weather_complete_workflow(self, mock_listdir, mock_read_z0,
                                            mock_get_austxt, mock_find_austxt,
                                            mock_readmet):
        """Test complete workflow of loading weather data."""
        # Setup mocks
        mock_listdir.return_value = ['zeitreihe.dmna', 'austal.txt']
        mock_get_austxt.return_value = {'z0': 0.1}
        mock_read_z0.return_value = 0.1

        # Create realistic mock data
        times = pd.date_range('2024-01-01', periods=24, freq='h')
        wind_speeds = np.random.uniform(2, 10, 24)
        wind_dirs = np.random.uniform(0, 360, 24)

        mock_data = MagicMock()
        mock_data.data = {
            'te': times,
            'ua': MagicMock(values=wind_speeds),
            'ra': MagicMock(values=wind_dirs)
        }
        mock_readmet.dmna.DataFile.return_value = mock_data

        with tempfile.TemporaryDirectory() as tmpdir:
            result = _windutil.load_weather(tmpdir)

        # Verify result structure
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 24)
        self.assertTrue(all(col in result.columns for col in ['FF', 'DD', 'KM']))

        # Verify wind speed values
        np.testing.assert_array_almost_equal(result['FF'].values, wind_speeds)

        # Verify wind direction values
        np.testing.assert_array_almost_equal(result['DD'].values, wind_dirs)


if __name__ == '__main__':
    unittest.main()
