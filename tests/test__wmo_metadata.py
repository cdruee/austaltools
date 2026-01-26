#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive test suite for austaltools._wmo_metadata module.

This module tests WMO (World Meteorological Organization) station
metadata retrieval and processing functionality.
"""
import json
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock, mock_open

import pytest

import austaltools._wmo_metadata
from austaltools import _wmo_metadata


class TestModuleConstants(unittest.TestCase):
    """Tests for module-level constants."""

    def test_oscarfile_is_string(self):
        """Test OSCARFILE is a string path."""
        self.assertIsInstance(_wmo_metadata.OSCARFILE, (str, os.PathLike))

    def test_oscarfile_ends_with_json(self):
        """Test OSCARFILE has .json extension."""
        self.assertTrue(str(_wmo_metadata.OSCARFILE).endswith('.json'))

    def test_oscarfile_contains_wmo(self):
        """Test OSCARFILE path contains 'wmo'."""
        self.assertIn('wmo', str(_wmo_metadata.OSCARFILE).lower())

    def test_stationlist_is_dict(self):
        """Test STATIONLIST is initialized as dict."""
        # Note: May be empty dict or filled depending on prior calls
        self.assertIsInstance(_wmo_metadata.STATIONLIST, (dict, list))


class TestGetFloat(unittest.TestCase):
    """Tests for the _get_float function."""

    def test_get_float_valid_float(self):
        """Test _get_float with valid float value."""
        station = {'latitude': 51.5}
        result = _wmo_metadata._get_float(station, 'latitude')
        self.assertEqual(result, 51.5)

    def test_get_float_valid_int(self):
        """Test _get_float with integer value (converts to float)."""
        station = {'elevation': 100}
        result = _wmo_metadata._get_float(station, 'elevation')
        self.assertEqual(result, 100.0)
        self.assertIsInstance(result, float)

    def test_get_float_string_number(self):
        """Test _get_float with string number value."""
        station = {'latitude': '51.5'}
        result = _wmo_metadata._get_float(station, 'latitude')
        self.assertEqual(result, 51.5)

    def test_get_float_missing_field(self):
        """Test _get_float returns None for missing field."""
        station = {'latitude': 51.5}
        result = _wmo_metadata._get_float(station, 'nonexistent')
        self.assertIsNone(result)

    def test_get_float_invalid_value(self):
        """Test _get_float returns None for non-convertible value."""
        station = {'latitude': 'not a number'}
        result = _wmo_metadata._get_float(station, 'latitude')
        self.assertIsNone(result)

    def test_get_float_empty_string(self):
        """Test _get_float returns None for empty string."""
        station = {'latitude': ''}
        result = _wmo_metadata._get_float(station, 'latitude')
        self.assertIsNone(result)

    def test_get_float_none_value(self):
        """Test _get_float with None value in dict."""
        station = {'latitude': None}
        result = _wmo_metadata._get_float(station, 'latitude')
        self.assertIsNone(result)


class TestWigosFromWmo(unittest.TestCase):
    """Tests for the _wigos_from_wmo function."""

    def test_wigos_from_wmo_integer(self):
        """Test _wigos_from_wmo with integer input."""
        result = _wmo_metadata._wigos_from_wmo(10384)
        self.assertEqual(result, '0-20000-0-10384')

    def test_wigos_from_wmo_string(self):
        """Test _wigos_from_wmo with string input."""
        result = _wmo_metadata._wigos_from_wmo('10384')
        self.assertEqual(result, '0-20000-0-10384')

    def test_wigos_from_wmo_zero_padding(self):
        """Test _wigos_from_wmo zero-pads to 5 digits."""
        result = _wmo_metadata._wigos_from_wmo(123)
        self.assertEqual(result, '0-20000-0-00123')

    def test_wigos_from_wmo_single_digit(self):
        """Test _wigos_from_wmo with single digit."""
        result = _wmo_metadata._wigos_from_wmo(1)
        self.assertEqual(result, '0-20000-0-00001')

    def test_wigos_from_wmo_five_digits(self):
        """Test _wigos_from_wmo with exactly 5 digits."""
        result = _wmo_metadata._wigos_from_wmo(12345)
        self.assertEqual(result, '0-20000-0-12345')

    def test_wigos_from_wmo_format(self):
        """Test _wigos_from_wmo returns correct WIGOS format."""
        result = _wmo_metadata._wigos_from_wmo(10000)
        # WIGOS format: 0-20000-0-NNNNN
        parts = result.split('-')
        self.assertEqual(len(parts), 4)
        self.assertEqual(parts[0], '0')
        self.assertEqual(parts[1], '20000')
        self.assertEqual(parts[2], '0')
        self.assertEqual(len(parts[3]), 5)


class TestWigosIds(unittest.TestCase):
    """Tests for the wigos_ids function."""

    def test_wigos_ids_single_primary(self):
        """Test wigos_ids with single primary ID."""
        station = {
            'wigosStationIdentifiers': [
                {'wigosStationIdentifier': '0-20000-0-10384', 'primary': True}
            ]
        }
        result = _wmo_metadata.wigos_ids(station)
        self.assertEqual(result, ['0-20000-0-10384'])

    def test_wigos_ids_multiple_ids(self):
        """Test wigos_ids with multiple IDs."""
        station = {
            'wigosStationIdentifiers': [
                {'wigosStationIdentifier': '0-20000-0-10384', 'primary': True},
                {'wigosStationIdentifier': '0-20001-0-10384', 'primary': False}
            ]
        }
        result = _wmo_metadata.wigos_ids(station)
        self.assertEqual(len(result), 2)
        # Primary should be first
        self.assertEqual(result[0], '0-20000-0-10384')

    def test_wigos_ids_primary_first(self):
        """Test wigos_ids puts primary ID first."""
        station = {
            'wigosStationIdentifiers': [
                {'wigosStationIdentifier': 'secondary-id', 'primary': False},
                {'wigosStationIdentifier': 'primary-id', 'primary': True}
            ]
        }
        result = _wmo_metadata.wigos_ids(station)
        self.assertEqual(result[0], 'primary-id')

    def test_wigos_ids_no_identifiers(self):
        """Test wigos_ids with no identifiers."""
        station = {'wigosStationIdentifiers': []}
        result = _wmo_metadata.wigos_ids(station)
        self.assertEqual(result, [])

    def test_wigos_ids_missing_key(self):
        """Test wigos_ids with missing wigosStationIdentifiers key."""
        station = {}
        result = _wmo_metadata.wigos_ids(station)
        self.assertEqual(result, [])

    def test_wigos_ids_all_secondary(self):
        """Test wigos_ids with all secondary IDs."""
        station = {
            'wigosStationIdentifiers': [
                {'wigosStationIdentifier': 'id1', 'primary': False},
                {'wigosStationIdentifier': 'id2', 'primary': False}
            ]
        }
        result = _wmo_metadata.wigos_ids(station)
        self.assertEqual(len(result), 2)
        self.assertIn('id1', result)
        self.assertIn('id2', result)


class TestPosition(unittest.TestCase):
    """Tests for the position function."""

    def test_position_complete_data(self):
        """Test position with complete data."""
        station = {
            'latitude': 51.5,
            'longitude': -0.1,
            'elevation': 100
        }
        lat, lon, ele = _wmo_metadata.position(station)
        self.assertEqual(lat, 51.5)
        self.assertEqual(lon, -0.1)
        self.assertEqual(ele, 100.0)

    def test_position_missing_latitude(self):
        """Test position with missing latitude."""
        station = {'longitude': -0.1, 'elevation': 100}
        lat, lon, ele = _wmo_metadata.position(station)
        self.assertIsNone(lat)
        self.assertEqual(lon, -0.1)
        self.assertEqual(ele, 100.0)

    def test_position_missing_longitude(self):
        """Test position with missing longitude."""
        station = {'latitude': 51.5, 'elevation': 100}
        lat, lon, ele = _wmo_metadata.position(station)
        self.assertEqual(lat, 51.5)
        self.assertIsNone(lon)
        self.assertEqual(ele, 100.0)

    def test_position_missing_elevation(self):
        """Test position with missing elevation."""
        station = {'latitude': 51.5, 'longitude': -0.1}
        lat, lon, ele = _wmo_metadata.position(station)
        self.assertEqual(lat, 51.5)
        self.assertEqual(lon, -0.1)
        self.assertIsNone(ele)

    def test_position_all_missing(self):
        """Test position with all fields missing."""
        station = {}
        lat, lon, ele = _wmo_metadata.position(station)
        self.assertIsNone(lat)
        self.assertIsNone(lon)
        self.assertIsNone(ele)

    def test_position_string_values(self):
        """Test position with string number values."""
        station = {
            'latitude': '51.5',
            'longitude': '-0.1',
            'elevation': '100'
        }
        lat, lon, ele = _wmo_metadata.position(station)
        self.assertEqual(lat, 51.5)
        self.assertEqual(lon, -0.1)
        self.assertEqual(ele, 100.0)

    def test_position_returns_tuple(self):
        """Test position returns a tuple."""
        station = {'latitude': 51.5, 'longitude': -0.1, 'elevation': 100}
        result = _wmo_metadata.position(station)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)


class TestLazyLoadList(unittest.TestCase):
    """Tests for the _lazy_load_list function."""

    def setUp(self):
        """Reset STATIONLIST before each test."""
        _wmo_metadata.STATIONLIST = {}

    def test_lazy_load_list_loads_json(self):
        """Test _lazy_load_list loads JSON file."""
        test_data = [
            {'name': 'Station 1', 'latitude': 51.0},
            {'name': 'Station 2', 'latitude': 52.0}
        ]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                          delete=False) as f:
            json.dump(test_data, f)
            temp_file = f.name

        try:
            _wmo_metadata._lazy_load_list(temp_file)
            self.assertEqual(_wmo_metadata.STATIONLIST, test_data)
        finally:
            os.unlink(temp_file)

    def test_lazy_load_list_only_loads_once(self):
        """Test _lazy_load_list doesn't reload if already loaded."""
        _wmo_metadata.STATIONLIST = [{'name': 'Already loaded'}]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                          delete=False) as f:
            json.dump([{'name': 'New data'}], f)
            temp_file = f.name

        try:
            _wmo_metadata._lazy_load_list(temp_file)
            # Should still have old data
            self.assertEqual(_wmo_metadata.STATIONLIST[0]['name'],
                             'Already loaded')
        finally:
            os.unlink(temp_file)

    def test_lazy_load_list_empty_dict_triggers_load(self):
        """Test _lazy_load_list loads when STATIONLIST is empty dict."""
        _wmo_metadata.STATIONLIST = {}
        test_data = [{'name': 'Test Station'}]

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                          delete=False) as f:
            json.dump(test_data, f)
            temp_file = f.name

        try:
            _wmo_metadata._lazy_load_list(temp_file)
            self.assertEqual(_wmo_metadata.STATIONLIST, test_data)
        finally:
            os.unlink(temp_file)


class TestByWigosId(unittest.TestCase):
    """Tests for the by_wigos_id function."""

    def setUp(self):
        """Set up test station list."""
        _wmo_metadata.STATIONLIST = [
            {
                'name': 'Test Station 1',
                'wigosStationIdentifiers': [
                    {'wigosStationIdentifier': '0-20000-0-10384',
                     'primary': True}
                ]
            },
            {
                'name': 'Test Station 2',
                'wigosStationIdentifiers': [
                    {'wigosStationIdentifier': '0-20000-0-10385',
                     'primary': True}
                ]
            }
        ]

    def test_by_wigos_id_found(self):
        """Test by_wigos_id finds matching station."""
        result = _wmo_metadata.by_wigos_id('0-20000-0-10384')
        self.assertIsNotNone(result)
        self.assertEqual(result['name'], 'Test Station 1')

    def test_by_wigos_id_not_found(self):
        """Test by_wigos_id returns None for non-existent ID."""
        result = _wmo_metadata.by_wigos_id('0-20000-0-99999')
        self.assertIsNone(result)

    def test_by_wigos_id_calls_lazy_load(self):
        """Test by_wigos_id triggers lazy load."""
        _wmo_metadata.STATIONLIST = {}

        with patch.object(_wmo_metadata, '_lazy_load_list') as mock_load:
            _wmo_metadata.by_wigos_id('0-20000-0-10384')
            mock_load.assert_called_once()


class TestByWmoId(unittest.TestCase):
    """Tests for the by_wmo_id function."""

    def setUp(self):
        """Set up test station list."""
        _wmo_metadata.STATIONLIST = [
            {
                'name': 'Frankfurt',
                'wigosStationIdentifiers': [
                    {'wigosStationIdentifier': '0-20000-0-10637',
                     'primary': True}
                ]
            }
        ]

    def test_by_wmo_id_integer(self):
        """Test by_wmo_id with integer WMO ID."""
        result = _wmo_metadata.by_wmo_id(10637)
        self.assertIsNotNone(result)
        self.assertEqual(result['name'], 'Frankfurt')

    def test_by_wmo_id_string(self):
        """Test by_wmo_id with string WMO ID."""
        result = _wmo_metadata.by_wmo_id('10637')
        self.assertIsNotNone(result)
        self.assertEqual(result['name'], 'Frankfurt')

    def test_by_wmo_id_not_found(self):
        """Test by_wmo_id returns None for non-existent station."""
        result = _wmo_metadata.by_wmo_id(99999)
        self.assertIsNone(result)

    def test_by_wmo_id_converts_to_wigos(self):
        """Test by_wmo_id converts WMO ID to WIGOS format."""
        with patch.object(_wmo_metadata, 'by_wigos_id') as mock_by_wigos:
            with patch.object(_wmo_metadata, '_lazy_load_list'):
                mock_by_wigos.return_value = {'name': 'Test'}
                _wmo_metadata.by_wmo_id(10637)
                mock_by_wigos.assert_called_with('0-20000-0-10637')


class TestWmoStationinfo(unittest.TestCase):
    """Tests for the wmo_stationinfo function."""

    def setUp(self):
        """Set up test station list."""
        _wmo_metadata.STATIONLIST = [
            {
                'name': 'FRANKFURT/MAIN',
                'latitude': 50.05,
                'longitude': 8.6,
                'elevation': 112,
                'wigosStationIdentifiers': [
                    {'wigosStationIdentifier': '0-20000-0-10637',
                     'primary': True}
                ]
            }
        ]

    def test_wmo_stationinfo_returns_tuple(self):
        """Test wmo_stationinfo returns tuple of 4 elements."""
        result = _wmo_metadata.wmo_stationinfo(10637)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 4)

    def test_wmo_stationinfo_values(self):
        """Test wmo_stationinfo returns correct values."""
        lat, lon, ele, name = _wmo_metadata.wmo_stationinfo(10637)
        self.assertEqual(lat, 50.05)
        self.assertEqual(lon, 8.6)
        self.assertEqual(ele, 112.0)
        self.assertEqual(name, 'Frankfurt/Main')  # Title case

    def test_wmo_stationinfo_title_case_name(self):
        """Test wmo_stationinfo converts name to title case."""
        _wmo_metadata.STATIONLIST = [
            {
                'name': 'BERLIN-TEGEL',
                'latitude': 52.5,
                'longitude': 13.3,
                'elevation': 36,
                'wigosStationIdentifiers': [
                    {'wigosStationIdentifier': '0-20000-0-10382',
                     'primary': True}
                ]
            }
        ]
        lat, lon, ele, name = _wmo_metadata.wmo_stationinfo(10382)
        self.assertEqual(name, 'Berlin-Tegel')

    def test_wmo_stationinfo_with_string_id(self):
        """Test wmo_stationinfo accepts string WMO ID."""
        lat, lon, ele, name = _wmo_metadata.wmo_stationinfo('10637')
        self.assertEqual(lat, 50.05)


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and boundary conditions."""

    def test_get_float_with_zero(self):
        """Test _get_float with zero value."""
        station = {'elevation': 0}
        result = _wmo_metadata._get_float(station, 'elevation')
        self.assertEqual(result, 0.0)

    def test_get_float_with_negative(self):
        """Test _get_float with negative value."""
        station = {'elevation': -10}
        result = _wmo_metadata._get_float(station, 'elevation')
        self.assertEqual(result, -10.0)

    def test_wigos_from_wmo_with_zero(self):
        """Test _wigos_from_wmo with zero."""
        result = _wmo_metadata._wigos_from_wmo(0)
        self.assertEqual(result, '0-20000-0-00000')

    def test_position_with_zero_coordinates(self):
        """Test position with zero coordinates (equator/prime meridian)."""
        station = {'latitude': 0, 'longitude': 0, 'elevation': 0}
        lat, lon, ele = _wmo_metadata.position(station)
        self.assertEqual(lat, 0.0)
        self.assertEqual(lon, 0.0)
        self.assertEqual(ele, 0.0)

    def test_position_with_extreme_coordinates(self):
        """Test position with extreme coordinates."""
        station = {'latitude': -90, 'longitude': 180, 'elevation': 8848}
        lat, lon, ele = _wmo_metadata.position(station)
        self.assertEqual(lat, -90.0)
        self.assertEqual(lon, 180.0)
        self.assertEqual(ele, 8848.0)


# Pytest-style parametrized tests

class TestPytestStyle:
    """Pytest-style tests for additional patterns."""

    @pytest.mark.parametrize("wmo_id,expected_wigos", [
        (1, '0-20000-0-00001'),
        (12, '0-20000-0-00012'),
        (123, '0-20000-0-00123'),
        (1234, '0-20000-0-01234'),
        (12345, '0-20000-0-12345'),
        (99999, '0-20000-0-99999'),
    ])
    def test_wigos_from_wmo_padding(self, wmo_id, expected_wigos):
        """Test _wigos_from_wmo zero-padding for various inputs."""
        result = _wmo_metadata._wigos_from_wmo(wmo_id)
        assert result == expected_wigos

    @pytest.mark.parametrize("value,expected", [
        (51.5, 51.5),
        ('51.5', 51.5),
        (100, 100.0),
        ('100', 100.0),
        (0, 0.0),
        (-10.5, -10.5),
    ])
    def test_get_float_various_values(self, value, expected):
        """Test _get_float with various valid values."""
        station = {'field': value}
        result = _wmo_metadata._get_float(station, 'field')
        assert result == expected

    @pytest.mark.parametrize("invalid_value", [
        'not a number',
        '',
        'abc123',
        '12.34.56',
        None,
    ])
    def test_get_float_invalid_values(self, invalid_value):
        """Test _get_float returns None for invalid values."""
        station = {'field': invalid_value}
        result = _wmo_metadata._get_float(station, 'field')
        assert result is None

    @pytest.mark.parametrize("station_data,expected_count", [
        ({'wigosStationIdentifiers': []}, 0),
        ({'wigosStationIdentifiers': [
            {'wigosStationIdentifier': 'id1', 'primary': True}
        ]}, 1),
        ({'wigosStationIdentifiers': [
            {'wigosStationIdentifier': 'id1', 'primary': True},
            {'wigosStationIdentifier': 'id2', 'primary': False}
        ]}, 2),
        ({}, 0),
    ])
    def test_wigos_ids_count(self, station_data, expected_count):
        """Test wigos_ids returns correct number of IDs."""
        result = _wmo_metadata.wigos_ids(station_data)
        assert len(result) == expected_count


class TestIntegration(unittest.TestCase):
    """Integration tests for WMO metadata module."""

    def test_full_lookup_workflow(self):
        """Test complete workflow from WMO ID to station info."""
        _wmo_metadata.STATIONLIST = [
            {
                'name': 'TEST STATION',
                'latitude': 50.0,
                'longitude': 8.0,
                'elevation': 100,
                'wigosStationIdentifiers': [
                    {'wigosStationIdentifier': '0-20000-0-10001',
                     'primary': True}
                ]
            }
        ]

        # Get station info using WMO ID
        lat, lon, ele, name = _wmo_metadata.wmo_stationinfo(10001)

        self.assertEqual(lat, 50.0)
        self.assertEqual(lon, 8.0)
        self.assertEqual(ele, 100.0)
        self.assertEqual(name, 'Test Station')

    def test_wigos_id_round_trip(self):
        """Test WMO ID to WIGOS and back lookup."""
        wmo_id = 10637
        wigos_id = _wmo_metadata._wigos_from_wmo(wmo_id)

        _wmo_metadata.STATIONLIST = [
            {
                'name': 'Test',
                'wigosStationIdentifiers': [
                    {'wigosStationIdentifier': wigos_id, 'primary': True}
                ]
            }
        ]

        # Look up by WMO ID should find station
        station = _wmo_metadata.by_wmo_id(wmo_id)
        self.assertIsNotNone(station)

        # Look up by WIGOS ID should find same station
        station2 = _wmo_metadata.by_wigos_id(wigos_id)
        self.assertEqual(station, station2)


if __name__ == '__main__':
    unittest.main()
