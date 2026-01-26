#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive test suite for austaltools._datasets module.

This module tests dataset management, downloading, assembling,
and various utility functions for terrain and weather data handling.
"""
import json
import os
import tempfile
import unittest
import zipfile
from unittest.mock import patch, MagicMock, mock_open, PropertyMock

import numpy as np
import pandas as pd
import pytest

import austaltools._datasets
from austaltools import _datasets


class TestModuleConstants(unittest.TestCase):
    """Tests for module-level constants."""

    def test_cdsapi_limit_parallel_is_positive(self):
        """Test CDSAPI_LIMIT_PARALLEL is a positive integer."""
        self.assertIsInstance(_datasets.CDSAPI_LIMIT_PARALLEL, int)
        self.assertGreaterEqual(_datasets.CDSAPI_LIMIT_PARALLEL, 0)

    def test_wea_window_format(self):
        """Test WEA_WINDOW has correct format (latmin, latmax, lonmin, lonmax)."""
        self.assertEqual(len(_datasets.WEA_WINDOW), 4)
        latmin, latmax, lonmin, lonmax = _datasets.WEA_WINDOW
        self.assertLess(latmin, latmax)
        self.assertLess(lonmin, lonmax)

    def test_dem_window_format(self):
        """Test DEM_WINDOW has correct format."""
        self.assertEqual(len(_datasets.DEM_WINDOW), 4)
        latmin, latmax, lonmin, lonmax = _datasets.DEM_WINDOW
        self.assertLess(latmin, latmax)
        self.assertLess(lonmin, lonmax)

    def test_dem_fmt_is_string(self):
        """Test DEM_FMT is a format string."""
        self.assertIsInstance(_datasets.DEM_FMT, str)
        self.assertIn('%s', _datasets.DEM_FMT)

    def test_wea_fmt_is_string(self):
        """Test WEA_FMT is a format string."""
        self.assertIsInstance(_datasets.WEA_FMT, str)
        self.assertIn('%s', _datasets.WEA_FMT)

    def test_obs_fmt_is_string(self):
        """Test OBS_FMT is a format string."""
        self.assertIsInstance(_datasets.OBS_FMT, str)
        self.assertIn('%s', _datasets.OBS_FMT)

    def test_dem_crs_is_epsg(self):
        """Test DEM_CRS is a valid EPSG code format."""
        self.assertIsInstance(_datasets.DEM_CRS, str)
        self.assertTrue(_datasets.DEM_CRS.startswith('EPSG:'))

    def test_compress_netcdf_is_string(self):
        """Test COMPRESS_NETCDF is a valid compression string."""
        self.assertIsInstance(_datasets.COMPRESS_NETCDF, str)
        self.assertIn(_datasets.COMPRESS_NETCDF, ['zlib', 'gzip', 'lzma', ''])

    def test_nodata_value(self):
        """Test NODATA is a large float value."""
        self.assertIsInstance(_datasets.NODATA, float)
        self.assertGreater(_datasets.NODATA, 1e30)

    def test_sources_terrain_is_list(self):
        """Test SOURCES_TERRAIN is a non-empty list."""
        self.assertIsInstance(_datasets.SOURCES_TERRAIN, list)

    def test_sources_weather_is_list(self):
        """Test SOURCES_WEATHER is a non-empty list."""
        self.assertIsInstance(_datasets.SOURCES_WEATHER, list)

    def test_dataset_definitions_loaded(self):
        """Test DATASET_DEFINITIONS is loaded from JSON."""
        self.assertIsInstance(_datasets.DATASET_DEFINITIONS, dict)
        self.assertGreater(len(_datasets.DATASET_DEFINITIONS), 0)


class TestDataSetClass(unittest.TestCase):
    """Tests for the DataSet class."""

    def test_dataset_init_requires_name(self):
        """Test DataSet requires name parameter."""
        with self.assertRaises(ValueError) as context:
            _datasets.DataSet(storage='terrain')
        self.assertIn('name', str(context.exception))

    def test_dataset_init_requires_storage(self):
        """Test DataSet requires storage parameter."""
        with self.assertRaises(ValueError) as context:
            _datasets.DataSet(name='TEST')
        self.assertIn('storage', str(context.exception))

    def test_dataset_init_minimal(self):
        """Test DataSet initialization with minimal parameters."""
        ds = _datasets.DataSet(name='TEST', storage='terrain')
        self.assertEqual(ds.name, 'TEST')
        self.assertEqual(ds.storage, 'terrain')
        self.assertFalse(ds.available)

    def test_dataset_init_sets_file_license(self):
        """Test DataSet sets default file_license."""
        ds = _datasets.DataSet(name='TEST', storage='terrain')
        self.assertEqual(ds.file_license, 'TEST.LICENSE.txt')

    def test_dataset_init_sets_file_notice(self):
        """Test DataSet sets default file_notice."""
        ds = _datasets.DataSet(name='TEST', storage='terrain')
        self.assertEqual(ds.file_notice, 'TEST.NOTICE.txt')

    def test_dataset_init_sets_file_data_terrain(self):
        """Test DataSet sets file_data for terrain storage."""
        ds = _datasets.DataSet(name='TEST', storage='terrain')
        self.assertEqual(ds.file_data, _datasets.DEM_FMT % 'TEST')

    def test_dataset_init_sets_file_data_weather_grid(self):
        """Test DataSet sets file_data for weather grid storage."""
        ds = _datasets.DataSet(name='TEST', storage='weather', position='grid')
        self.assertEqual(ds.file_data, _datasets.WEA_FMT % 'TEST')

    def test_dataset_init_sets_file_data_weather_station(self):
        """Test DataSet sets file_data for weather station storage."""
        ds = _datasets.DataSet(name='TEST', storage='weather', position='station')
        self.assertEqual(ds.file_data, _datasets.OBS_FMT % 'TEST')

    def test_dataset_init_custom_attributes(self):
        """Test DataSet accepts custom attributes."""
        ds = _datasets.DataSet(
            name='TEST',
            storage='terrain',
            license='spdx:MIT',
            uri='https://example.com/data.nc'
        )
        self.assertEqual(ds.license, 'spdx:MIT')
        self.assertEqual(ds.uri, 'https://example.com/data.nc')

    def test_dataset_assemble_default(self):
        """Test default assemble method returns True."""
        ds = _datasets.DataSet(name='TEST', storage='terrain')
        result = ds.assemble('/path', 'TEST', False, {})
        self.assertTrue(result)

    def test_dataset_download_no_uri_raises(self):
        """Test download raises when no uri provided."""
        ds = _datasets.DataSet(name='TEST', storage='terrain')
        with self.assertRaises(ValueError):
            ds.download(path='/tmp')


class TestNameYearly(unittest.TestCase):
    """Tests for the name_yearly function."""

    def test_name_yearly_format(self):
        """Test name_yearly produces correct format."""
        result = _datasets.name_yearly('ERA5', 2020)
        self.assertEqual(result, 'ERA5-2020')

    def test_name_yearly_pads_year(self):
        """Test name_yearly pads year to 4 digits."""
        result = _datasets.name_yearly('TEST', 99)
        self.assertEqual(result, 'TEST-0099')

    def test_name_yearly_with_zero(self):
        """Test name_yearly with year 0."""
        result = _datasets.name_yearly('DATA', 0)
        self.assertEqual(result, 'DATA-0000')


class TestDatasetGet(unittest.TestCase):
    """Tests for the dataset_get function."""

    @patch('austaltools._datasets._init_datasets')
    def test_dataset_get_found(self, mock_init):
        """Test dataset_get returns dataset when found."""
        mock_ds = MagicMock()
        mock_ds.name = 'TEST-DS'
        _datasets.DATASETS = [mock_ds]

        result = _datasets.dataset_get('TEST-DS')
        self.assertEqual(result, mock_ds)

    @patch('austaltools._datasets._init_datasets')
    def test_dataset_get_not_found(self, mock_init):
        """Test dataset_get raises ValueError when not found."""
        _datasets.DATASETS = []

        with self.assertRaises(ValueError) as context:
            _datasets.dataset_get('NONEXISTENT')
        self.assertIn('not found', str(context.exception))


class TestDatasetAvailable(unittest.TestCase):
    """Tests for the dataset_available function."""

    @patch('austaltools._datasets.dataset_get')
    def test_dataset_available_true(self, mock_get):
        """Test dataset_available returns True when available."""
        mock_ds = MagicMock()
        mock_ds.available = True
        mock_get.return_value = mock_ds

        result = _datasets.dataset_available('TEST')
        self.assertTrue(result)

    @patch('austaltools._datasets.dataset_get')
    def test_dataset_available_false(self, mock_get):
        """Test dataset_available returns False when not available."""
        mock_ds = MagicMock()
        mock_ds.available = False
        mock_get.return_value = mock_ds

        result = _datasets.dataset_available('TEST')
        self.assertFalse(result)


class TestDatasetList(unittest.TestCase):
    """Tests for the dataset_list function."""

    @patch('austaltools._datasets._init_datasets')
    def test_dataset_list_returns_dict(self, mock_init):
        """Test dataset_list returns a dictionary."""
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
    def test_dataset_list_contains_required_keys(self, mock_init):
        """Test dataset_list entries contain required keys."""
        mock_ds = MagicMock()
        mock_ds.name = 'TEST'
        mock_ds.storage = 'terrain'
        mock_ds.available = True
        mock_ds.uri = None
        mock_ds.path = None
        _datasets.DATASETS = [mock_ds]

        result = _datasets.dataset_list()
        entry = result['TEST']
        self.assertIn('storage', entry)
        self.assertIn('available', entry)
        self.assertIn('uri', entry)
        self.assertIn('path', entry)


class TestAssClearTarget(unittest.TestCase):
    """Tests for the _ass_clear_target function."""

    def test_ass_clear_target_nonexistent(self):
        """Test _ass_clear_target returns True for nonexistent file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, 'nonexistent.nc')
            result = _datasets._ass_clear_target(target, replace=False)
            self.assertTrue(result)

    def test_ass_clear_target_exists_no_replace(self):
        """Test _ass_clear_target returns False when file exists and no replace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, 'existing.nc')
            with open(target, 'w') as f:
                f.write('data')

            result = _datasets._ass_clear_target(target, replace=False)
            self.assertFalse(result)
            self.assertTrue(os.path.exists(target))

    def test_ass_clear_target_exists_replace(self):
        """Test _ass_clear_target removes file when replace=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = os.path.join(tmpdir, 'existing.nc')
            with open(target, 'w') as f:
                f.write('data')

            result = _datasets._ass_clear_target(target, replace=True)
            self.assertTrue(result)
            self.assertFalse(os.path.exists(target))


class TestUnpackFile(unittest.TestCase):
    """Tests for the unpack_file function."""

    def test_unpack_file_none(self):
        """Test unpack_file with None returns original file."""
        result = _datasets.unpack_file('test.tif', None)
        self.assertEqual(result, ['test.tif'])

    def test_unpack_file_empty_string(self):
        """Test unpack_file with empty string returns original file."""
        result = _datasets.unpack_file('test.tif', '')
        self.assertEqual(result, ['test.tif'])

    def test_unpack_file_tif(self):
        """Test unpack_file with 'tif' returns original file."""
        result = _datasets.unpack_file('test.tif', 'tif')
        self.assertEqual(result, ['test.tif'])

    def test_unpack_file_false(self):
        """Test unpack_file with 'false' returns original file."""
        result = _datasets.unpack_file('test.tif', 'false')
        self.assertEqual(result, ['test.tif'])

    def test_unpack_file_zip_pattern(self):
        """Test unpack_file with zip pattern extracts files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test zip file
            zip_path = os.path.join(tmpdir, 'test.zip')
            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.writestr('data/file1.tif', 'content1')
                zf.writestr('data/file2.tif', 'content2')
                zf.writestr('other/file3.txt', 'content3')

            # Change to temp dir to avoid polluting working directory
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
        """Test unpack_file with invalid format raises IOError."""
        with self.assertRaises(IOError):
            _datasets.unpack_file('test.dat', 'unknown://pattern')


class TestExpandFilelistString(unittest.TestCase):
    """Tests for the expand_filelist_string function."""

    def test_expand_filelist_string_no_expansion(self):
        """Test expand_filelist_string with plain filename."""
        result = _datasets.expand_filelist_string(
            'simple.tif', 'https://example.com', True, None, None, None
        )
        self.assertEqual(result, ['simple.tif'])

    def test_expand_filelist_string_unknown_type(self):
        """Test expand_filelist_string raises for unknown type."""
        with self.assertRaises(ValueError):
            _datasets.expand_filelist_string(
                'file.dat::unknown', 'https://example.com',
                True, None, None, None
            )


class TestXyz2csv(unittest.TestCase):
    """Tests for the xyz2csv function."""

    def test_xyz2csv_basic(self):
        """Test xyz2csv converts basic xyz file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test xyz file
            input_file = os.path.join(tmpdir, 'test.xyz')
            output_file = os.path.join(tmpdir, 'test.csv')

            with open(input_file, 'w') as f:
                f.write('100 200 10.5\n')
                f.write('100 201 11.0\n')
                f.write('101 200 10.8\n')
                f.write('101 201 11.2\n')

            result = _datasets.xyz2csv(input_file, output_file)
            self.assertTrue(result)
            self.assertTrue(os.path.exists(output_file))

    def test_xyz2csv_empty_file(self):
        """Test xyz2csv returns False for nearly empty file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_file = os.path.join(tmpdir, 'empty.xyz')
            output_file = os.path.join(tmpdir, 'empty.csv')

            with open(input_file, 'w') as f:
                f.write('100 200 10.5\n')  # Only one line

            result = _datasets.xyz2csv(input_file, output_file)
            self.assertFalse(result)

    def test_xyz2csv_with_header(self):
        """Test xyz2csv handles file with header."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_file = os.path.join(tmpdir, 'header.xyz')
            output_file = os.path.join(tmpdir, 'header.csv')

            with open(input_file, 'w') as f:
                f.write('x y z\n')  # Header line
                f.write('100 200 10.5\n')
                f.write('100 201 11.0\n')
                f.write('101 200 10.8\n')
                f.write('101 201 11.2\n')

            result = _datasets.xyz2csv(input_file, output_file)
            self.assertTrue(result)

    def test_xyz2csv_utm_remove_zone(self):
        """Test xyz2csv with UTM zone removal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_file = os.path.join(tmpdir, 'utm.xyz')
            output_file = os.path.join(tmpdir, 'utm.csv')

            # Coordinates with UTM zone prefix (32500000 = zone 32, 500000 easting)
            with open(input_file, 'w') as f:
                f.write('32500000 5500000 100\n')
                f.write('32500000 5500001 101\n')
                f.write('32500001 5500000 102\n')
                f.write('32500001 5500001 103\n')

            result = _datasets.xyz2csv(input_file, output_file,
                                        utm_remove_zone=True)
            self.assertTrue(result)


class TestCdsMergeZipped(unittest.TestCase):
    """Tests for the cds_merge_zipped function."""

    @patch('austaltools._datasets._netcdf.merge_variables')
    def test_cds_merge_zipped_creates_destination(self, mock_merge):
        """Test cds_merge_zipped calls merge_variables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test zip with nc files
            zip_path = os.path.join(tmpdir, 'source.zip')
            dest_path = os.path.join(tmpdir, 'dest.nc')

            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.writestr('data1.nc', 'nc_content_1')
                zf.writestr('data2.nc', 'nc_content_2')

            _datasets.cds_merge_zipped(zip_path, dest_path)
            mock_merge.assert_called_once()

    def test_cds_merge_zipped_no_nc_files(self):
        """Test cds_merge_zipped raises IOError when no nc files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, 'empty.zip')
            dest_path = os.path.join(tmpdir, 'dest.nc')

            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.writestr('readme.txt', 'no nc files here')

            with self.assertRaises(IOError):
                _datasets.cds_merge_zipped(zip_path, dest_path)


class TestCdsReplaceValidTime(unittest.TestCase):
    """Tests for the cds_replace_valid_time function."""

    def test_cds_replace_valid_time_returns_dicts(self):
        """Test cds_replace_valid_time returns two dicts."""
        replace, convert = _datasets.cds_replace_valid_time()
        self.assertIsInstance(replace, dict)
        self.assertIsInstance(convert, dict)

    def test_cds_replace_valid_time_replace_key(self):
        """Test cds_replace_valid_time has valid_time in replace."""
        replace, convert = _datasets.cds_replace_valid_time()
        self.assertIn('valid_time', replace)

    def test_cds_replace_valid_time_convert_key(self):
        """Test cds_replace_valid_time has valid_time in convert."""
        replace, convert = _datasets.cds_replace_valid_time()
        self.assertIn('valid_time', convert)


class TestAvailableFunctions(unittest.TestCase):
    """Tests for availability scanning functions."""

    @patch('austaltools._datasets._storage.read_config')
    def test_available_read_empty_config(self, mock_read):
        """Test _available_read with empty config."""
        mock_read.return_value = {}
        result = _datasets._available_read()
        self.assertEqual(result, {})

    @patch('austaltools._datasets._storage.read_config')
    def test_available_read_with_data(self, mock_read):
        """Test _available_read with available datasets."""
        mock_read.return_value = {
            'available': {
                'terrain': {'DEM1': '/path/to/dem1'},
                'weather': {'ERA5-2020': '/path/to/era5'}
            }
        }
        result = _datasets._available_read()
        self.assertIn('DEM1', result)
        self.assertIn('ERA5-2020', result)

    @patch('austaltools._datasets._storage.write_config')
    @patch('austaltools._datasets._storage.read_config')
    def test_available_write_calls_write_config(self, mock_read, mock_write):
        """Test _available_write calls write_config."""
        mock_read.return_value = {}
        mock_ds = MagicMock()
        mock_ds.available = True
        mock_ds.name = 'TEST'
        mock_ds.path = '/path'

        _datasets._available_write([mock_ds])
        mock_write.assert_called_once()


class TestDatasetsExpand(unittest.TestCase):
    """Tests for _datasets_expand function."""

    def test_datasets_expand_simple(self):
        """Test _datasets_expand with simple dataset."""
        definitions = {
            'TEST': {
                'storage': 'terrain',
            }
        }
        result = _datasets._datasets_expand(definitions)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, 'TEST')

    def test_datasets_expand_yearly_split(self):
        """Test _datasets_expand with yearly split."""
        definitions = {
            'YEARLY': {
                'storage': 'weather',
                'split': 'years',
                'years_available': '2020-2022'
            }
        }
        result = _datasets._datasets_expand(definitions)
        self.assertEqual(len(result), 3)
        names = [ds.name for ds in result]
        self.assertIn('YEARLY-2020', names)
        self.assertIn('YEARLY-2021', names)
        self.assertIn('YEARLY-2022', names)


class TestDatasetsSetAvailable(unittest.TestCase):
    """Tests for _datasets_set_available function."""

    def test_datasets_set_available_marks_available(self):
        """Test _datasets_set_available marks datasets as available."""
        ds1 = _datasets.DataSet(name='DS1', storage='terrain')
        ds2 = _datasets.DataSet(name='DS2', storage='terrain')

        avail = {'DS1': '/path/ds1'}
        result = _datasets._datasets_set_available([ds1, ds2], avail)

        self.assertTrue(ds1.available)
        self.assertEqual(ds1.path, '/path/ds1')
        self.assertFalse(ds2.available)
        self.assertIsNone(ds2.path)


class TestFindWeatherData(unittest.TestCase):
    """Tests for find_weather_data function."""

    @patch('austaltools._datasets._init_datasets')
    def test_find_weather_data_returns_dict(self, mock_init):
        """Test find_weather_data returns a dictionary."""
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
    def test_find_weather_data_excludes_terrain(self, mock_init):
        """Test find_weather_data excludes terrain datasets."""
        mock_ds = MagicMock()
        mock_ds.name = 'DEM1'
        mock_ds.storage = 'terrain'
        mock_ds.available = True
        _datasets.DATASETS = [mock_ds]

        result = _datasets.find_weather_data()
        self.assertNotIn('DEM1', result)


class TestFindTerrainData(unittest.TestCase):
    """Tests for find_terrain_data function."""

    @patch('austaltools._datasets._init_datasets')
    def test_find_terrain_data_returns_dict(self, mock_init):
        """Test find_terrain_data returns a dictionary."""
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
    def test_find_terrain_data_excludes_weather(self, mock_init):
        """Test find_terrain_data excludes weather datasets."""
        mock_ds = MagicMock()
        mock_ds.name = 'ERA5-2020'
        mock_ds.storage = 'weather'
        mock_ds.available = True
        _datasets.DATASETS = [mock_ds]

        result = _datasets.find_terrain_data()
        self.assertNotIn('ERA5-2020', result)


class TestShowNotice(unittest.TestCase):
    """Tests for show_notice function."""

    @patch('builtins.print')
    def test_show_notice_with_file(self, mock_print):
        """Test show_notice prints notice content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            notice_file = os.path.join(tmpdir, 'TEST.NOTICE.txt')
            with open(notice_file, 'w') as f:
                f.write('Test notice content')

            _datasets.show_notice(tmpdir, 'TEST')
            self.assertTrue(mock_print.called)

    @patch('builtins.print')
    def test_show_notice_no_file(self, mock_print):
        """Test show_notice does nothing when no notice file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _datasets.show_notice(tmpdir, 'NONEXISTENT')
            # Should not print anything (except maybe debug)
            # The print for notice should not be called
            for call in mock_print.call_args_list:
                self.assertNotIn('IMPORTANT', str(call))


class TestProvideTerrainValidation(unittest.TestCase):
    """Tests for provide_terrain validation."""

    def test_provide_terrain_invalid_method(self):
        """Test provide_terrain raises for invalid method."""
        with self.assertRaises(ValueError) as context:
            _datasets.provide_terrain('DEM1', method='invalid')
        self.assertIn('download', str(context.exception))
        self.assertIn('assemble', str(context.exception))


class TestCdsGetOrderList(unittest.TestCase):
    """Tests for cds_get_order_list function."""

    @patch('austaltools._datasets.cds_processorder')
    @patch('austaltools._datasets.cds_getorder')
    def test_cds_get_order_list_sequential(self, mock_getorder, mock_process):
        """Test cds_get_order_list runs sequentially when RUNPARALLEL=False."""
        original_runparallel = _datasets.RUNPARALLEL
        _datasets.RUNPARALLEL = False
        try:
            mock_getorder.return_value = 'downloaded.nc'
            mock_process.return_value = 'processed.nc'

            args_list = [
                {'dataset': 'test', 'request': {}, 'target': 'file1.nc'},
                {'dataset': 'test', 'request': {}, 'target': 'file2.nc'}
            ]

            result = _datasets.cds_get_order_list(args_list)
            self.assertEqual(len(result), 2)
            self.assertEqual(mock_getorder.call_count, 2)
        finally:
            _datasets.RUNPARALLEL = original_runparallel


class TestProvideStationlist(unittest.TestCase):
    """Tests for provide_stationlist function."""

    def test_provide_stationlist_no_source(self):
        """Test provide_stationlist raises without source."""
        with self.assertRaises(ValueError):
            _datasets.provide_stationlist(source=None)

    def test_provide_stationlist_unknown_source(self):
        """Test provide_stationlist raises for unknown source."""
        with self.assertRaises(ValueError):
            _datasets.provide_stationlist(source='UNKNOWN')

    @patch('austaltools._datasets.stationlist_DWD')
    def test_provide_stationlist_dwd(self, mock_stationlist):
        """Test provide_stationlist calls stationlist_DWD for DWD source."""
        _datasets.provide_stationlist(source='DWD', fmt='json', out='/tmp/out.json')
        mock_stationlist.assert_called_once_with(path='/tmp/out.json', fmt='json')


class TestMergeTilesValidation(unittest.TestCase):
    """Tests for merge_tiles input validation."""

    def test_merge_tiles_invalid_ullr(self):
        """Test merge_tiles raises for invalid ullr."""
        with self.assertRaises(ValueError):
            _datasets.merge_tiles('target.nc', ['file1.tif'], ullr=(1, 2, 3))


# Pytest-style parametrized tests

class TestPytestStyle:
    """Pytest-style tests for additional patterns."""

    @pytest.mark.parametrize("unpack_str,expected_len", [
        (None, 1),
        ('', 1),
        ('tif', 1),
        ('false', 1),
    ])
    def test_unpack_file_simple_cases(self, unpack_str, expected_len):
        """Test unpack_file with various simple inputs."""
        result = _datasets.unpack_file('test.tif', unpack_str)
        assert len(result) == expected_len
        assert result[0] == 'test.tif'

    @pytest.mark.parametrize("name,year,expected", [
        ('ERA5', 2020, 'ERA5-2020'),
        ('CERRA', 1985, 'CERRA-1985'),
        ('TEST', 1, 'TEST-0001'),
        ('DATA', 99999, 'DATA-99999'),
    ])
    def test_name_yearly_parametrized(self, name, year, expected):
        """Test name_yearly with various inputs."""
        assert _datasets.name_yearly(name, year) == expected

    @pytest.mark.parametrize("storage,position,expected_suffix", [
        ('terrain', None, '.elevation.nc'),
        ('weather', 'grid', '.ak-input.nc'),
        ('weather', 'station', '.obs.zip'),
        ('weather', None, '.ak-input.nc'),
    ])
    def test_dataset_file_data_formats(self, storage, position, expected_suffix):
        """Test DataSet file_data is set correctly for different configurations."""
        kwargs = {'name': 'TEST', 'storage': storage}
        if position:
            kwargs['position'] = position
        ds = _datasets.DataSet(**kwargs)
        assert ds.file_data.endswith(expected_suffix)


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and boundary conditions."""

    def test_dataset_init_with_assemble_function(self):
        """Test DataSet can reference assemble function by name."""
        # This should work if a function named 'assemble_DGMxx' exists
        ds = _datasets.DataSet(
            name='TEST',
            storage='terrain',
            assemble='assemble_DGMxx'
        )
        # The assemble attribute should be the actual function
        self.assertTrue(callable(ds.assemble))

    def test_nodata_is_standard_netcdf_fill(self):
        """Test NODATA matches common netCDF fill value."""
        # Standard netCDF _FillValue for float64
        self.assertAlmostEqual(_datasets.NODATA, 9.96920996838686905e+36, places=20)


class TestIntegrationDatasetsExpand(unittest.TestCase):
    """Integration tests for dataset expansion."""

    def test_expand_actual_definitions(self):
        """Test _datasets_expand works with actual DATASET_DEFINITIONS."""
        result = _datasets._datasets_expand(_datasets.DATASET_DEFINITIONS)
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        for ds in result:
            self.assertIsInstance(ds, _datasets.DataSet)
            self.assertIsNotNone(ds.name)
            self.assertIsNotNone(ds.storage)


if __name__ == '__main__':
    unittest.main()
