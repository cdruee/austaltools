#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive test suite for austaltools._geo module.

This module tests geo-position related functionality including
coordinate transformations and station information retrieval.
"""
import json
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

import austaltools._geo
from austaltools import _geo


class TestCoordinateTransformations(unittest.TestCase):
    """Tests for coordinate transformation functions."""

    def test_gk2ll_returns_tuple(self):
        """Test gk2ll returns a tuple of two floats."""
        result = _geo.gk2ll(3500000, 5500000)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_ll2gk_returns_tuple(self):
        """Test ll2gk returns a tuple of two floats."""
        result = _geo.ll2gk(50.0, 8.0)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_ut2ll_returns_tuple(self):
        """Test ut2ll returns a tuple of two floats."""
        result = _geo.ut2ll(500000, 5500000)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_ll2ut_returns_tuple(self):
        """Test ll2ut returns a tuple of two floats."""
        result = _geo.ll2ut(50.0, 8.0)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_ut2gk_returns_tuple(self):
        """Test ut2gk returns a tuple of two floats."""
        result = _geo.ut2gk(500000, 5500000)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_gk2ut_returns_tuple(self):
        """Test gk2ut returns a tuple of two floats."""
        result = _geo.gk2ut(3500000, 5500000)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_gk2ll_roundtrip(self):
        """Test GK to LL and back gives original values."""
        rechts_orig, hoch_orig = 3500000, 5500000
        lat, lon = _geo.gk2ll(rechts_orig, hoch_orig)
        rechts_back, hoch_back = _geo.ll2gk(lat, lon)
        self.assertAlmostEqual(rechts_orig, rechts_back, delta=1.0)
        self.assertAlmostEqual(hoch_orig, hoch_back, delta=1.0)

    def test_ll2gk_roundtrip(self):
        """Test LL to GK and back gives original values."""
        lat_orig, lon_orig = 50.0, 9.0
        rechts, hoch = _geo.ll2gk(lat_orig, lon_orig)
        lat_back, lon_back = _geo.gk2ll(rechts, hoch)
        self.assertAlmostEqual(lat_orig, lat_back, places=5)
        self.assertAlmostEqual(lon_orig, lon_back, places=5)

    def test_ut2ll_roundtrip(self):
        """Test UTM to LL and back gives original values."""
        east_orig, north_orig = 500000, 5500000
        lat, lon = _geo.ut2ll(east_orig, north_orig)
        east_back, north_back = _geo.ll2ut(lat, lon)
        self.assertAlmostEqual(east_orig, east_back, delta=1.0)
        self.assertAlmostEqual(north_orig, north_back, delta=1.0)

    def test_ll2ut_roundtrip(self):
        """Test LL to UTM and back gives original values."""
        lat_orig, lon_orig = 50.0, 9.0
        east, north = _geo.ll2ut(lat_orig, lon_orig)
        lat_back, lon_back = _geo.ut2ll(east, north)
        self.assertAlmostEqual(lat_orig, lat_back, places=5)
        self.assertAlmostEqual(lon_orig, lon_back, places=5)

    def test_ut2gk_roundtrip(self):
        """Test UTM to GK and back gives original values."""
        east_orig, north_orig = 500000, 5500000
        rechts, hoch = _geo.ut2gk(east_orig, north_orig)
        east_back, north_back = _geo.gk2ut(rechts, hoch)
        self.assertAlmostEqual(east_orig, east_back, delta=1.0)
        self.assertAlmostEqual(north_orig, north_back, delta=1.0)

    def test_gk2ut_roundtrip(self):
        """Test GK to UTM and back gives original values."""
        rechts_orig, hoch_orig = 3500000, 5500000
        east, north = _geo.gk2ut(rechts_orig, hoch_orig)
        rechts_back, hoch_back = _geo.ut2gk(east, north)
        self.assertAlmostEqual(rechts_orig, rechts_back, delta=1.0)
        self.assertAlmostEqual(hoch_orig, hoch_back, delta=1.0)


class TestSphericDistance(unittest.TestCase):
    """Tests for the spheric_distance function."""

    def test_spheric_distance_same_point(self):
        """Test spheric_distance returns 0 for same point."""
        result = _geo.spheric_distance(50.0, 8.0, 50.0, 8.0)
        self.assertAlmostEqual(result, 0.0, places=5)

    def test_spheric_distance_returns_float(self):
        """Test spheric_distance returns a float."""
        result = _geo.spheric_distance(50.0, 8.0, 51.0, 9.0)
        self.assertIsInstance(result, (float, np.floating))

    def test_spheric_distance_positive(self):
        """Test spheric_distance returns positive value."""
        result = _geo.spheric_distance(50.0, 8.0, 51.0, 9.0)
        self.assertGreater(result, 0)

    def test_spheric_distance_symmetric(self):
        """Test spheric_distance is symmetric."""
        dist1 = _geo.spheric_distance(50.0, 8.0, 51.0, 9.0)
        dist2 = _geo.spheric_distance(51.0, 9.0, 50.0, 8.0)
        self.assertAlmostEqual(dist1, dist2, places=5)

    def test_spheric_distance_known_value(self):
        """Test spheric_distance against known distance."""
        # Frankfurt (50.1, 8.7) to Berlin (52.5, 13.4) ~ 424 km
        result = _geo.spheric_distance(50.1, 8.7, 52.5, 13.4)
        self.assertAlmostEqual(result, 424, delta=10)

    def test_spheric_distance_equator(self):
        """Test spheric_distance along equator."""
        # 1 degree longitude at equator ~ 111 km
        result = _geo.spheric_distance(0.0, 0.0, 0.0, 1.0)
        self.assertAlmostEqual(result, 111, delta=2)

    def test_spheric_distance_meridian(self):
        """Test spheric_distance along meridian."""
        # 1 degree latitude ~ 111 km
        result = _geo.spheric_distance(0.0, 0.0, 1.0, 0.0)
        self.assertAlmostEqual(result, 111, delta=2)

    def test_spheric_distance_antipodal(self):
        """Test spheric_distance for antipodal points."""
        # North pole to south pole ~ 20,000 km (half earth circumference)
        result = _geo.spheric_distance(90.0, 0.0, -90.0, 0.0)
        self.assertAlmostEqual(result, 20015, delta=100)

    def test_spheric_distance_with_arrays(self):
        """Test spheric_distance works with numpy arrays."""
        lat1 = np.array([50.0, 51.0])
        lon1 = np.array([8.0, 9.0])
        result = _geo.spheric_distance(lat1, lon1, 52.0, 10.0)
        self.assertEqual(len(result), 2)


class TestReadDwdStationinfo(unittest.TestCase):
    """Tests for the read_dwd_stationinfo function."""

    def test_read_dwd_stationinfo_station_and_coords_error(self):
        """Test read_dwd_stationinfo raises when both station and coords given."""
        with self.assertRaises(ValueError) as context:
            _geo.read_dwd_stationinfo(
                station=12345,
                pos_lat=50.0,
                pos_lon=8.0
            )
        self.assertIn('None', str(context.exception))

    def test_read_dwd_stationinfo_with_station(self):
        """Test read_dwd_stationinfo with station number."""
        # Create mock data file
        test_data = {
            "12345": {
                "latitude": 50.5,
                "longitude": 8.5,
                "elevation": 150,
                "name": "Test Station"
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                          delete=False) as f:
            json.dump(test_data, f)
            temp_file = f.name

        try:
            lat, lon, ele, nam = _geo.read_dwd_stationinfo(
                station=12345,
                datafile=temp_file
            )
            self.assertEqual(lat, 50.5)
            self.assertEqual(lon, 8.5)
            self.assertEqual(ele, 150)
            self.assertEqual(nam, "Test Station")
        finally:
            os.unlink(temp_file)

    def test_read_dwd_stationinfo_station_not_found(self):
        """Test read_dwd_stationinfo raises for non-existent station."""
        test_data = {
            "12345": {
                "latitude": 50.5,
                "longitude": 8.5,
                "elevation": 150,
                "name": "Test Station"
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                          delete=False) as f:
            json.dump(test_data, f)
            temp_file = f.name

        try:
            with self.assertRaises(ValueError) as context:
                _geo.read_dwd_stationinfo(station=99999, datafile=temp_file)
            self.assertIn('not in datafile', str(context.exception))
        finally:
            os.unlink(temp_file)

    def test_read_dwd_stationinfo_nearest_station(self):
        """Test read_dwd_stationinfo finds nearest station by coords."""
        test_data = {
            "1": {
                "latitude": 50.0,
                "longitude": 8.0,
                "elevation": 100,
                "name": "Station 1"
            },
            "2": {
                "latitude": 52.0,
                "longitude": 10.0,
                "elevation": 200,
                "name": "Station 2"
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                          delete=False) as f:
            json.dump(test_data, f)
            temp_file = f.name

        try:
            # Search near station 1
            lat, lon, ele, nam, idx = _geo.read_dwd_stationinfo(
                station=None,
                pos_lat=50.1,
                pos_lon=8.1,
                datafile=temp_file
            )
            self.assertEqual(nam, "Station 1")
        finally:
            os.unlink(temp_file)


class TestEvaluateLocationOpts(unittest.TestCase):
    """Tests for the evaluate_location_opts function."""

    def test_evaluate_location_opts_ll(self):
        """Test evaluate_location_opts with lat/lon."""
        args = {'ll': ['50.0', '8.0']}
        lat, lon, ele, station, nam = _geo.evaluate_location_opts(args)
        self.assertEqual(lat, 50.0)
        self.assertEqual(lon, 8.0)
        self.assertIsNone(ele)
        self.assertIsNone(nam)

    def test_evaluate_location_opts_gk(self):
        """Test evaluate_location_opts with Gauss-Kruger coords."""
        args = {'gk': ['3500000', '5500000']}
        lat, lon, ele, station, nam = _geo.evaluate_location_opts(args)
        self.assertIsNotNone(lat)
        self.assertIsNotNone(lon)

    def test_evaluate_location_opts_ut(self):
        """Test evaluate_location_opts with UTM coords."""
        args = {'ut': ['500000', '5500000']}
        lat, lon, ele, station, nam = _geo.evaluate_location_opts(args)
        self.assertIsNotNone(lat)
        self.assertIsNotNone(lon)

    def test_evaluate_location_opts_empty(self):
        """Test evaluate_location_opts with no location args."""
        args = {}
        lat, lon, ele, station, nam = _geo.evaluate_location_opts(args)
        self.assertIsNone(lat)
        self.assertIsNone(lon)

    @patch('austaltools._geo._wmo_metadata.wmo_stationinfo')
    def test_evaluate_location_opts_wmo(self, mock_wmo):
        """Test evaluate_location_opts with WMO station."""
        mock_wmo.return_value = (50.0, 8.0, 100, 'Test Station')
        args = {'wmo': '10637'}
        lat, lon, ele, station, nam = _geo.evaluate_location_opts(args)
        self.assertEqual(lat, 50.0)
        self.assertEqual(lon, 8.0)
        self.assertEqual(ele, 100)
        self.assertEqual(nam, 'Test Station')

    @patch('austaltools._geo.read_dwd_stationinfo')
    def test_evaluate_location_opts_dwd(self, mock_dwd):
        """Test evaluate_location_opts with DWD station."""
        mock_dwd.return_value = (50.0, 8.0, 100, 'Test Station')
        args = {'dwd': '12345'}
        lat, lon, ele, station, nam = _geo.evaluate_location_opts(args)
        self.assertEqual(lat, 50.0)
        self.assertEqual(lon, 8.0)
        self.assertEqual(station, 12345)


class TestModuleGlobals(unittest.TestCase):
    """Tests for module-level spatial reference objects."""

    def test_ll_spatial_reference_exists(self):
        """Test LL (WGS84) spatial reference is defined."""
        self.assertIsNotNone(_geo.LL)

    def test_gk_spatial_reference_exists(self):
        """Test GK (Gauss-Kruger) spatial reference is defined."""
        self.assertIsNotNone(_geo.GK)

    def test_ut_spatial_reference_exists(self):
        """Test UT (UTM) spatial reference is defined."""
        self.assertIsNotNone(_geo.UT)


# Pytest-style parametrized tests

class TestPytestStyle:
    """Pytest-style tests for additional patterns."""

    @pytest.mark.parametrize("lat,lon", [
        (50.0, 8.0),
        (52.5, 13.4),
        (48.1, 11.6),
        (53.5, 10.0),
        (47.4, 8.5),
    ])
    def test_ll2gk2ll_roundtrip_various(self, lat, lon):
        """Test LL to GK roundtrip for various German cities."""
        rechts, hoch = _geo.ll2gk(lat, lon)
        lat_back, lon_back = _geo.gk2ll(rechts, hoch)
        assert abs(lat - lat_back) < 0.0001
        assert abs(lon - lon_back) < 0.0001

    @pytest.mark.parametrize("lat,lon", [
        (50.0, 8.0),
        (52.5, 13.4),
        (48.1, 11.6),
    ])
    def test_ll2ut2ll_roundtrip_various(self, lat, lon):
        """Test LL to UTM roundtrip for various locations."""
        east, north = _geo.ll2ut(lat, lon)
        lat_back, lon_back = _geo.ut2ll(east, north)
        assert abs(lat - lat_back) < 0.0001
        assert abs(lon - lon_back) < 0.0001

    @pytest.mark.parametrize("lat1,lon1,lat2,lon2,expected_km", [
        (50.0, 8.0, 50.0, 8.0, 0),  # Same point
        (0.0, 0.0, 0.0, 1.0, 111),  # 1 degree at equator
        (0.0, 0.0, 1.0, 0.0, 111),  # 1 degree latitude
    ])
    def test_spheric_distance_known_values(self, lat1, lon1, lat2, lon2,
                                            expected_km):
        """Test spheric_distance against known values."""
        result = _geo.spheric_distance(lat1, lon1, lat2, lon2)
        assert abs(result - expected_km) < 2  # 2 km tolerance

    @pytest.mark.parametrize("args,expected_keys", [
        ({'ll': ['50', '8']}, ('lat', 'lon')),
        ({'gk': ['3500000', '5500000']}, ('lat', 'lon')),
        ({'ut': ['500000', '5500000']}, ('lat', 'lon')),
        ({}, ('none', 'none')),
    ])
    def test_evaluate_location_opts_various(self, args, expected_keys):
        """Test evaluate_location_opts with various input types."""
        lat, lon, ele, station, nam = _geo.evaluate_location_opts(args)
        if expected_keys == ('none', 'none'):
            assert lat is None
            assert lon is None
        else:
            assert lat is not None
            assert lon is not None


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and boundary conditions."""

    def test_spheric_distance_negative_coords(self):
        """Test spheric_distance with negative coordinates."""
        # Southern hemisphere
        result = _geo.spheric_distance(-33.9, 18.4, -34.0, 18.5)
        self.assertGreater(result, 0)

    def test_spheric_distance_date_line(self):
        """Test spheric_distance across date line."""
        result = _geo.spheric_distance(0.0, 179.0, 0.0, -179.0)
        # Should be about 222 km (2 degrees at equator)
        self.assertAlmostEqual(result, 222, delta=5)

    def test_coordinate_transform_extreme_north(self):
        """Test coordinate transforms for extreme northern Germany."""
        lat, lon = 55.0, 8.5  # Northern Germany
        rechts, hoch = _geo.ll2gk(lat, lon)
        lat_back, lon_back = _geo.gk2ll(rechts, hoch)
        self.assertAlmostEqual(lat, lat_back, places=4)
        self.assertAlmostEqual(lon, lon_back, places=4)

    def test_coordinate_transform_extreme_south(self):
        """Test coordinate transforms for extreme southern Germany."""
        lat, lon = 47.3, 10.9  # Bavaria/Alps
        rechts, hoch = _geo.ll2gk(lat, lon)
        lat_back, lon_back = _geo.gk2ll(rechts, hoch)
        self.assertAlmostEqual(lat, lat_back, places=4)
        self.assertAlmostEqual(lon, lon_back, places=4)


if __name__ == '__main__':
    unittest.main()
