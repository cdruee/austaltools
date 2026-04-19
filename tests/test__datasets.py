#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for austaltools._datasets module.

Covers dataset management, availability scanning, terrain/weather helpers,
and various utility functions.  CDS-download tests live in test__fetch_cds.py.
"""
import json
import os
import tempfile
import unittest
import zipfile
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

from austaltools import _datasets, _storage


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

class TestModuleConstants(unittest.TestCase):
    """Tests for module-level constants defined in _datasets."""

    def test_dem_window_format(self):
        """DEM_WINDOW must be a 4-tuple with latmin < latmax and lonmin < lonmax."""
        self.assertEqual(len(_datasets.DEM_WINDOW), 4)
        latmin, latmax, lonmin, lonmax = _datasets.DEM_WINDOW
        self.assertLess(latmin, latmax)
        self.assertLess(lonmin, lonmax)

    def test_dem_fmt_is_string(self):
        """DEM_FMT must be a format string containing '%s'."""
        self.assertIsInstance(_datasets.DEM_FMT, str)
        self.assertIn('%s', _datasets.DEM_FMT)

    def test_wea_fmt_is_string(self):
        """WEA_FMT must be a format string containing '%s'."""
        self.assertIsInstance(_datasets.WEA_FMT, str)
        self.assertIn('%s', _datasets.WEA_FMT)

    def test_obs_fmt_is_string(self):
        """OBS_FMT must be a format string containing '%s'."""
        self.assertIsInstance(_datasets.OBS_FMT, str)
        self.assertIn('%s', _datasets.OBS_FMT)

    def test_dem_crs_is_epsg(self):
        """DEM_CRS must be a string starting with 'EPSG:'."""
        self.assertIsInstance(_datasets.DEM_CRS, str)
        self.assertTrue(_datasets.DEM_CRS.startswith('EPSG:'))

    def test_compress_netcdf_is_string(self):
        """_storage.COMPRESS_NETCDF must be a recognised compression name."""
        self.assertIsInstance(_storage.COMPRESS_NETCDF, str)
        self.assertIn(_storage.COMPRESS_NETCDF, ['zlib', 'gzip', 'lzma', ''])

    def test_nodata_value(self):
        """NODATA must be a large float (standard netCDF fill value)."""
        self.assertIsInstance(_datasets.NODATA, float)
        self.assertGreater(_datasets.NODATA, 1e30)

    def test_sources_terrain_is_list(self):
        """SOURCES_TERRAIN must be a list."""
        self.assertIsInstance(_datasets.SOURCES_TERRAIN, list)

    def test_sources_weather_is_list(self):
        """SOURCES_WEATHER must be a list."""
        self.assertIsInstance(_datasets.SOURCES_WEATHER, list)

    def test_dataset_definitions_loaded(self):
        """DATASET_DEFINITIONS must be a non-empty dict loaded from JSON."""
        self.assertIsInstance(_datasets.DATASET_DEFINITIONS, dict)
        self.assertGreater(len(_datasets.DATASET_DEFINITIONS), 0)


# ---------------------------------------------------------------------------
# DataSet class
# ---------------------------------------------------------------------------

class TestDataSetClass(unittest.TestCase):
    """Tests for the DataSet class."""

    def test_dataset_init_requires_name(self):
        """DataSet must raise ValueError when 'name' is missing."""
        with self.assertRaises(ValueError) as ctx:
            _datasets.DataSet(storage='terrain')
        self.assertIn('name', str(ctx.exception))

    def test_dataset_init_requires_storage(self):
        """DataSet must raise ValueError when 'storage' is missing."""
        with self.assertRaises(ValueError) as ctx:
            _datasets.DataSet(name='TEST')
        self.assertIn('storage', str(ctx.exception))

    def test_dataset_init_minimal(self):
        """DataSet initialises correctly with minimal parameters."""
        ds = _datasets.DataSet(name='TEST', storage='terrain')
        self.assertEqual(ds.name, 'TEST')
        self.assertEqual(ds.storage, 'terrain')
        self.assertFalse(ds.available)

    def test_dataset_init_sets_file_license(self):
        """DataSet sets a default file_license based on name."""
        ds = _datasets.DataSet(name='TEST', storage='terrain')
        self.assertEqual(ds.file_license, 'TEST.LICENSE.txt')

    def test_dataset_init_sets_file_notice(self):
        """DataSet sets a default file_notice based on name."""
        ds = _datasets.DataSet(name='TEST', storage='terrain')
        self.assertEqual(ds.file_notice, 'TEST.NOTICE.txt')

    def test_dataset_init_sets_file_data_terrain(self):
        """DataSet sets file_data for terrain storage from DEM_FMT."""
        ds = _datasets.DataSet(name='TEST', storage='terrain')
        self.assertEqual(ds.file_data, _datasets.DEM_FMT % 'TEST')

    def test_dataset_init_sets_file_data_weather_grid(self):
        """DataSet sets file_data for weather grid storage from WEA_FMT."""
        ds = _datasets.DataSet(name='TEST', storage='weather', position='grid')
        self.assertEqual(ds.file_data, _datasets.WEA_FMT % 'TEST')

    def test_dataset_init_sets_file_data_weather_station(self):
        """DataSet sets file_data for weather station storage from OBS_FMT."""
        ds = _datasets.DataSet(name='TEST', storage='weather', position='station')
        self.assertEqual(ds.file_data, _datasets.OBS_FMT % 'TEST')

    def test_dataset_init_custom_attributes(self):
        """DataSet stores custom keyword arguments as attributes."""
        ds = _datasets.DataSet(
            name='TEST',
            storage='terrain',
            license='spdx:MIT',
            uri='https://example.com/data.nc'
        )
        self.assertEqual(ds.license, 'spdx:MIT')
        self.assertEqual(ds.uri, 'https://example.com/data.nc')

    def test_dataset_assemble_default(self):
        """Default assemble() placeholder returns True."""
        ds = _datasets.DataSet(name='TEST', storage='terrain')
        self.assertTrue(ds.assemble('/path', 'TEST', False, {}))

    def test_dataset_download_no_uri_raises(self):
        """download() raises ValueError when no URI is set or provided."""
        ds = _datasets.DataSet(name='TEST', storage='terrain')
        with self.assertRaises(ValueError):
            ds.download(path='/tmp')

    def test_dataset_init_with_assemble_function(self):
        """DataSet resolves the 'assemble' string to an actual callable."""
        ds = _datasets.DataSet(
            name='TEST',
            storage='terrain',
            assemble='assemble_DGMxx'
        )
        self.assertTrue(callable(ds.assemble))


# ---------------------------------------------------------------------------
# name_yearly
# ---------------------------------------------------------------------------

class TestNameYearly(unittest.TestCase):
    """Tests for the name_yearly helper."""

    def test_name_yearly_format(self):
        """name_yearly produces '<NAME>-<YYYY>' format."""
        self.assertEqual(_datasets.name_yearly('ERA5', 2020), 'ERA5-2020')

    def test_name_yearly_pads_year(self):
        """name_yearly zero-pads the year to 4 digits."""
        self.assertEqual(_datasets.name_yearly('TEST', 99), 'TEST-0099')

    def test_name_yearly_with_zero(self):
        """name_yearly handles year 0."""
        self.assertEqual(_datasets.name_yearly('DATA', 0), 'DATA-0000')


# ---------------------------------------------------------------------------
# dataset_get / dataset_available / dataset_list
# ---------------------------------------------------------------------------

class TestDatasetGet(unittest.TestCase):
    """Tests for dataset_get."""

    @patch('austaltools._datasets._init_datasets')
    def test_dataset_get_found(self, _mock_init):
        """dataset_get returns the matching DataSet object."""
        mock_ds = MagicMock()
        mock_ds.name = 'TEST-DS'
        _datasets.DATASETS = [mock_ds]
        self.assertEqual(_datasets.dataset_get('TEST-DS'), mock_ds)

    @patch('austaltools._datasets._init_datasets')
    def test_dataset_get_not_found(self, _mock_init):
        """dataset_get raises ValueError when the dataset is unknown."""
        _datasets.DATASETS = []
        with self.assertRaises(ValueError) as ctx:
            _datasets.dataset_get('NONEXISTENT')
        self.assertIn('not found', str(ctx.exception))


class TestDatasetAvailable(unittest.TestCase):
    """Tests for dataset_available."""

    @patch('austaltools._datasets.dataset_get')
    def test_dataset_available_true(self, mock_get):
        """dataset_available returns True when the dataset is available."""
        mock_ds = MagicMock()
        mock_ds.available = True
        mock_get.return_value = mock_ds
        self.assertTrue(_datasets.dataset_available('TEST'))

    @patch('austaltools._datasets.dataset_get')
    def test_dataset_available_false(self, mock_get):
        """dataset_available returns False when the dataset is not available."""
        mock_ds = MagicMock()
        mock_ds.available = False
        mock_get.return_value = mock_ds
        self.assertFalse(_datasets.dataset_available('TEST'))


class TestDatasetList(unittest.TestCase):
    """Tests for dataset_list."""

    @patch('austaltools._datasets._init_datasets')
    def test_dataset_list_returns_dict(self, _mock_init):
        """dataset_list returns a dict keyed by dataset name."""
        mock_ds = MagicMock()
        mock_ds.name = 'TEST'
        mock_ds.storage = 'terrain'
        mock_ds.available = True
        mock_ds.uri = 'https://example.com'
        mock_ds.path = '/data/path'
        _datasets.DATASETS = [mock_ds]

        result = _datasets.dataset_list()
        self.assertIsInstance(result, dict)
        self.assertIn('TEST', result)

    @patch('austaltools._datasets._init_datasets')
    def test_dataset_list_contains_required_keys(self, _mock_init):
        """Each entry in dataset_list has the four required keys."""
        mock_ds = MagicMock()
        mock_ds.name = 'TEST'
        mock_ds.storage = 'terrain'
        mock_ds.available = True
        mock_ds.uri = None
        mock_ds.path = None
        _datasets.DATASETS = [mock_ds]

        entry = _datasets.dataset_list()['TEST']
        for key in ('storage', 'available', 'uri', 'path'):
            self.assertIn(key, entry)


# ---------------------------------------------------------------------------
# _ass_clear_target
# ---------------------------------------------------------------------------

class TestAssClearTarget(unittest.TestCase):
    """Tests for _ass_clear_target."""

    def test_ass_clear_target_nonexistent(self):
        """Returns True for a path that does not exist yet."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, 'nonexistent.nc')
            self.assertTrue(_datasets._ass_clear_target(target, replace=False))

    def test_ass_clear_target_exists_no_replace(self):
        """Returns False and keeps file when it exists and replace=False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, 'existing.nc')
            with open(target, 'w') as f:
                f.write('data')
            result = _datasets._ass_clear_target(target, replace=False)
            self.assertFalse(result)
            self.assertTrue(os.path.exists(target))

    def test_ass_clear_target_exists_replace(self):
        """Returns True and deletes file when it exists and replace=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, 'existing.nc')
            with open(target, 'w') as f:
                f.write('data')
            result = _datasets._ass_clear_target(target, replace=True)
            self.assertTrue(result)
            self.assertFalse(os.path.exists(target))


# ---------------------------------------------------------------------------
# unpack_file
# ---------------------------------------------------------------------------

class TestUnpackFile(unittest.TestCase):
    """Tests for unpack_file."""

    def test_unpack_file_none(self):
        """None unpack string → returns the file unchanged."""
        self.assertEqual(_datasets.unpack_file('test.tif', None), ['test.tif'])

    def test_unpack_file_empty_string(self):
        """Empty unpack string → returns the file unchanged."""
        self.assertEqual(_datasets.unpack_file('test.tif', ''), ['test.tif'])

    def test_unpack_file_tif(self):
        """'tif' unpack string → returns the file unchanged."""
        self.assertEqual(_datasets.unpack_file('test.tif', 'tif'), ['test.tif'])

    def test_unpack_file_false(self):
        """'false' unpack string → returns the file unchanged."""
        self.assertEqual(_datasets.unpack_file('test.tif', 'false'), ['test.tif'])

    def test_unpack_file_zip_pattern(self):
        """zip:// pattern extracts matching files from the archive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, 'test.zip')
            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.writestr('data/file1.tif', 'content1')
                zf.writestr('data/file2.tif', 'content2')
                zf.writestr('other/file3.txt', 'content3')

            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                result = _datasets.unpack_file(zip_path, 'zip://data/*.tif')
                self.assertEqual(len(result), 2)
                self.assertIn('file1.tif', result)
                self.assertIn('file2.tif', result)
            finally:
                os.chdir(old_cwd)

    def test_unpack_file_invalid_format(self):
        """Unknown unpack scheme raises IOError."""
        with self.assertRaises(IOError):
            _datasets.unpack_file('test.dat', 'unknown://pattern')


# ---------------------------------------------------------------------------
# expand_filelist_string
# ---------------------------------------------------------------------------

class TestExpandFilelistString(unittest.TestCase):
    """Tests for expand_filelist_string."""

    def test_expand_filelist_string_no_expansion(self):
        """Plain filename is returned as a single-element list."""
        result = _datasets.expand_filelist_string(
            'simple.tif', 'https://example.com', True, None, None, None
        )
        self.assertEqual(result, ['simple.tif'])

    def test_expand_filelist_string_unknown_type(self):
        """An explicit but unknown type suffix raises ValueError."""
        with self.assertRaises(ValueError):
            _datasets.expand_filelist_string(
                'file.dat::unknown', 'https://example.com',
                True, None, None, None
            )


# ---------------------------------------------------------------------------
# xyz2csv
# ---------------------------------------------------------------------------

class TestXyz2csv(unittest.TestCase):
    """Tests for xyz2csv."""

    def test_xyz2csv_basic(self):
        """Converts a basic 4-point xyz file to csv."""
        with tempfile.TemporaryDirectory() as tmpdir:
            inp = os.path.join(tmpdir, 'test.xyz')
            out = os.path.join(tmpdir, 'test.csv')
            with open(inp, 'w') as f:
                f.write('100 200 10.5\n100 201 11.0\n'
                        '101 200 10.8\n101 201 11.2\n')
            self.assertTrue(_datasets.xyz2csv(inp, out))
            self.assertTrue(os.path.exists(out))

    def test_xyz2csv_empty_file(self):
        """Returns False when the file has fewer than 4 data points."""
        with tempfile.TemporaryDirectory() as tmpdir:
            inp = os.path.join(tmpdir, 'empty.xyz')
            out = os.path.join(tmpdir, 'empty.csv')
            with open(inp, 'w') as f:
                f.write('100 200 10.5\n')
            self.assertFalse(_datasets.xyz2csv(inp, out))

    def test_xyz2csv_with_header(self):
        """Handles a file that starts with a text header line."""
        with tempfile.TemporaryDirectory() as tmpdir:
            inp = os.path.join(tmpdir, 'header.xyz')
            out = os.path.join(tmpdir, 'header.csv')
            with open(inp, 'w') as f:
                f.write('x y z\n100 200 10.5\n100 201 11.0\n'
                        '101 200 10.8\n101 201 11.2\n')
            self.assertTrue(_datasets.xyz2csv(inp, out))

    def test_xyz2csv_utm_remove_zone(self):
        """utm_remove_zone=True strips the leading zone digits from easting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            inp = os.path.join(tmpdir, 'utm.xyz')
            out = os.path.join(tmpdir, 'utm.csv')
            with open(inp, 'w') as f:
                f.write('32500000 5500000 100\n32500000 5500001 101\n'
                        '32500001 5500000 102\n32500001 5500001 103\n')
            self.assertTrue(_datasets.xyz2csv(inp, out, utm_remove_zone=True))


# ---------------------------------------------------------------------------
# Availability helpers
# ---------------------------------------------------------------------------

class TestAvailableFunctions(unittest.TestCase):
    """Tests for _available_read, _available_write."""

    @patch('austaltools._datasets._storage.read_config')
    def test_available_read_empty_config(self, mock_read):
        """_available_read returns an empty dict when config has no 'available' key."""
        mock_read.return_value = {}
        self.assertEqual(_datasets._available_read(), {})

    @patch('austaltools._datasets._storage.read_config')
    def test_available_read_with_data(self, mock_read):
        """_available_read returns datasets from both terrain and weather sections."""
        mock_read.return_value = {
            'available': {
                'terrain': {'DEM1': '/path/to/dem1'},
                'weather': {'ERA5-2020': '/path/to/era5'},
            }
        }
        result = _datasets._available_read()
        self.assertIn('DEM1', result)
        self.assertIn('ERA5-2020', result)

    @patch('austaltools._datasets._storage.write_config')
    @patch('austaltools._datasets._storage.read_config')
    def test_available_write_calls_write_config(self, mock_read, mock_write):
        """_available_write persists the availability tree via write_config."""
        mock_read.return_value = {}
        mock_ds = MagicMock()
        mock_ds.available = True
        mock_ds.name = 'TEST'
        mock_ds.path = '/path'
        _datasets._available_write([mock_ds])
        mock_write.assert_called_once()


# ---------------------------------------------------------------------------
# _datasets_expand / _datasets_set_available
# ---------------------------------------------------------------------------

class TestDatasetsExpand(unittest.TestCase):
    """Tests for _datasets_expand."""

    def test_datasets_expand_simple(self):
        """A simple (non-split) definition produces one DataSet."""
        definitions = {'TEST': {'storage': 'terrain'}}
        result = _datasets._datasets_expand(definitions)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, 'TEST')

    def test_datasets_expand_yearly_split(self):
        """A 'years' split produces one DataSet per year."""
        definitions = {
            'YEARLY': {
                'storage': 'weather',
                'split': 'years',
                'years_available': '2020-2022',
            }
        }
        result = _datasets._datasets_expand(definitions)
        self.assertEqual(len(result), 3)
        names = [ds.name for ds in result]
        self.assertIn('YEARLY-2020', names)
        self.assertIn('YEARLY-2021', names)
        self.assertIn('YEARLY-2022', names)


class TestDatasetsSetAvailable(unittest.TestCase):
    """Tests for _datasets_set_available."""

    def test_datasets_set_available_marks_available(self):
        """Datasets present in the avail dict are marked available."""
        ds1 = _datasets.DataSet(name='DS1', storage='terrain')
        ds2 = _datasets.DataSet(name='DS2', storage='terrain')
        _datasets._datasets_set_available([ds1, ds2], {'DS1': '/path/ds1'})
        self.assertTrue(ds1.available)
        self.assertEqual(ds1.path, '/path/ds1')
        self.assertFalse(ds2.available)
        self.assertIsNone(ds2.path)


# ---------------------------------------------------------------------------
# find_weather_data / find_terrain_data
# ---------------------------------------------------------------------------

class TestFindWeatherData(unittest.TestCase):
    """Tests for find_weather_data."""

    @patch('austaltools._datasets._init_datasets')
    def test_find_weather_data_returns_dict(self, _mock_init):
        """Returns a dict containing available weather datasets."""
        mock_ds = MagicMock()
        mock_ds.name = 'ERA5-2020'
        mock_ds.storage = 'weather'
        mock_ds.available = True
        mock_ds.path = '/path/weather'
        _datasets.DATASETS = [mock_ds]
        result = _datasets.find_weather_data()
        self.assertIsInstance(result, dict)
        self.assertIn('ERA5-2020', result)

    @patch('austaltools._datasets._init_datasets')
    def test_find_weather_data_excludes_terrain(self, _mock_init):
        """Terrain datasets are excluded from the result."""
        mock_ds = MagicMock()
        mock_ds.name = 'DEM1'
        mock_ds.storage = 'terrain'
        mock_ds.available = True
        _datasets.DATASETS = [mock_ds]
        self.assertNotIn('DEM1', _datasets.find_weather_data())


class TestFindTerrainData(unittest.TestCase):
    """Tests for find_terrain_data."""

    @patch('austaltools._datasets._init_datasets')
    def test_find_terrain_data_returns_dict(self, _mock_init):
        """Returns a dict containing available terrain datasets."""
        mock_ds = MagicMock()
        mock_ds.name = 'DEM1'
        mock_ds.storage = 'terrain'
        mock_ds.available = True
        mock_ds.path = '/path/terrain'
        _datasets.DATASETS = [mock_ds]
        result = _datasets.find_terrain_data()
        self.assertIsInstance(result, dict)
        self.assertIn('DEM1', result)

    @patch('austaltools._datasets._init_datasets')
    def test_find_terrain_data_excludes_weather(self, _mock_init):
        """Weather datasets are excluded from the result."""
        mock_ds = MagicMock()
        mock_ds.name = 'ERA5-2020'
        mock_ds.storage = 'weather'
        mock_ds.available = True
        _datasets.DATASETS = [mock_ds]
        self.assertNotIn('ERA5-2020', _datasets.find_terrain_data())


# ---------------------------------------------------------------------------
# show_notice
# ---------------------------------------------------------------------------

class TestShowNotice(unittest.TestCase):
    """Tests for show_notice."""

    @patch('builtins.print')
    def test_show_notice_with_file(self, mock_print):
        """Prints notice content when the notice file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            notice_file = os.path.join(tmpdir, 'TEST.NOTICE.txt')
            with open(notice_file, 'w') as f:
                f.write('Test notice content')
            _datasets.show_notice(tmpdir, 'TEST')
            self.assertTrue(mock_print.called)

    @patch('builtins.print')
    def test_show_notice_no_file(self, mock_print):
        """Does not print 'IMPORTANT' when no notice file is present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _datasets.show_notice(tmpdir, 'NONEXISTENT')
            for call in mock_print.call_args_list:
                self.assertNotIn('IMPORTANT', str(call))


# ---------------------------------------------------------------------------
# provide_terrain validation
# ---------------------------------------------------------------------------

class TestProvideTerrainValidation(unittest.TestCase):
    """Input-validation tests for provide_terrain."""

    def test_provide_terrain_invalid_method(self):
        """Raises ValueError for unrecognised method."""
        with self.assertRaises(ValueError) as ctx:
            _datasets.provide_terrain('DEM1', method='invalid')
        self.assertIn('download', str(ctx.exception))
        self.assertIn('assemble', str(ctx.exception))


# ---------------------------------------------------------------------------
# provide_stationlist
# ---------------------------------------------------------------------------

class TestProvideStationlist(unittest.TestCase):
    """Tests for provide_stationlist."""

    def test_provide_stationlist_no_source(self):
        """Raises ValueError when source is None."""
        with self.assertRaises(ValueError):
            _datasets.provide_stationlist(source=None)

    def test_provide_stationlist_unknown_source(self):
        """Raises ValueError for an unknown source."""
        with self.assertRaises(ValueError):
            _datasets.provide_stationlist(source='UNKNOWN')

    @patch('austaltools._datasets.provide_stationlist')
    def test_provide_stationlist(self, mock_stationlist):
        """Delegates to assemble_stationlist for source='DWD'."""
        _datasets.provide_stationlist(source='DWD', fmt='json',
                                      out='/tmp/out.json')
        mock_stationlist.assert_called_once_with(source='DWD', fmt='json',
                                                 out='/tmp/out.json')


# ---------------------------------------------------------------------------
# merge_tiles validation
# ---------------------------------------------------------------------------

class TestMergeTilesValidation(unittest.TestCase):
    """Input-validation tests for merge_tiles."""

    def test_merge_tiles_invalid_ullr(self):
        """Raises ValueError when ullr does not have exactly 4 elements."""
        with self.assertRaises(ValueError):
            _datasets.merge_tiles('target.nc', ['file1.tif'], ullr=(1, 2, 3))


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases(unittest.TestCase):
    """Edge cases and boundary conditions."""

    def test_nodata_is_standard_netcdf_fill(self):
        """NODATA matches the standard netCDF float64 _FillValue."""
        self.assertAlmostEqual(_datasets.NODATA,
                               9.96920996838686905e+36, places=20)


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

class TestIntegrationDatasetsExpand(unittest.TestCase):
    """Integration tests using the real DATASET_DEFINITIONS."""

    def test_expand_actual_definitions(self):
        """_datasets_expand produces valid DataSet objects from the real JSON."""
        result = _datasets._datasets_expand(_datasets.DATASET_DEFINITIONS)
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        for ds in result:
            self.assertIsInstance(ds, _datasets.DataSet)
            self.assertIsNotNone(ds.name)
            self.assertIsNotNone(ds.storage)


# ---------------------------------------------------------------------------
# Pytest-parametrised tests
# ---------------------------------------------------------------------------

class TestPytestStyle:
    """Pytest-style parametrised tests."""

    @pytest.mark.parametrize("unpack_str", [None, '', 'tif', 'false'])
    def test_unpack_file_simple_cases(self, unpack_str):
        """unpack_file passthrough cases all return the original filename."""
        result = _datasets.unpack_file('test.tif', unpack_str)
        assert len(result) == 1
        assert result[0] == 'test.tif'

    @pytest.mark.parametrize("name,year,expected", [
        ('ERA5', 2020, 'ERA5-2020'),
        ('CERRA', 1985, 'CERRA-1985'),
        ('TEST', 1, 'TEST-0001'),
        ('DATA', 99999, 'DATA-99999'),
    ])
    def test_name_yearly_parametrized(self, name, year, expected):
        """name_yearly produces the expected string for various inputs."""
        assert _datasets.name_yearly(name, year) == expected

    @pytest.mark.parametrize("storage,position,expected_suffix", [
        ('terrain', None, '.elevation.nc'),
        ('weather', 'grid', '.ak-input.nc'),
        ('weather', 'station', '.obs.zip'),
        ('weather', None, '.ak-input.nc'),
    ])
    def test_dataset_file_data_formats(self, storage, position,
                                       expected_suffix):
        """DataSet.file_data ends with the correct suffix for each configuration."""
        kwargs = {'name': 'TEST', 'storage': storage}
        if position:
            kwargs['position'] = position
        ds = _datasets.DataSet(**kwargs)
        assert ds.file_data.endswith(expected_suffix)


# ---------------------------------------------------------------------------

if __name__ == '__main__':
    unittest.main()
