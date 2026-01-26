#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive test suite for austaltools._fetch_dwd_obs module.

This module tests DWD (German Weather Service) observation data
fetching, parsing, and processing functionality.
"""
import datetime
import io
import os
import tempfile
import unittest
import zipfile
from unittest.mock import patch, MagicMock, mock_open

import numpy as np
import pandas as pd
import pytest

import austaltools._fetch_dwd_obs
from austaltools import _fetch_dwd_obs


class TestModuleConstants(unittest.TestCase):
    """Tests for module-level constants."""

    def test_oldest_is_timestamp(self):
        """Test OLDEST is a pandas Timestamp."""
        self.assertIsInstance(_fetch_dwd_obs.OLDEST, pd.Timestamp)

    def test_oldest_is_1970(self):
        """Test OLDEST is set to 1970-01-01."""
        self.assertEqual(_fetch_dwd_obs.OLDEST.year, 1970)
        self.assertEqual(_fetch_dwd_obs.OLDEST.month, 1)
        self.assertEqual(_fetch_dwd_obs.OLDEST.day, 1)

    def test_obsfile_dwd_format(self):
        """Test OBSFILE_DWD is a format string with station placeholder."""
        self.assertIsInstance(_fetch_dwd_obs.OBSFILE_DWD, str)
        self.assertIn('%05i', _fetch_dwd_obs.OBSFILE_DWD)
        # Test formatting works
        result = _fetch_dwd_obs.OBSFILE_DWD % 1234
        self.assertIn('01234', result)

    def test_metafile_dwd_format(self):
        """Test METAFILE_DWD is a format string with station placeholder."""
        self.assertIsInstance(_fetch_dwd_obs.METAFILE_DWD, str)
        self.assertIn('%05i', _fetch_dwd_obs.METAFILE_DWD)
        # Test formatting works
        result = _fetch_dwd_obs.METAFILE_DWD % 5678
        self.assertIn('05678', result)

    def test_to_collect_is_list(self):
        """Test TO_COLLECT is a non-empty list."""
        self.assertIsInstance(_fetch_dwd_obs.TO_COLLECT, list)
        self.assertGreater(len(_fetch_dwd_obs.TO_COLLECT), 0)

    def test_to_collect_structure(self):
        """Test TO_COLLECT entries have correct structure."""
        for entry in _fetch_dwd_obs.TO_COLLECT:
            self.assertIsInstance(entry, list)
            self.assertEqual(len(entry), 3)
            # [name, gtl, abbr] - all strings
            self.assertIsInstance(entry[0], str)  # name
            self.assertIsInstance(entry[1], str)  # gtl (group two-letter)
            self.assertIsInstance(entry[2], str)  # abbr

    def test_to_collect_contains_required_groups(self):
        """Test TO_COLLECT contains essential parameter groups."""
        group_names = [entry[0] for entry in _fetch_dwd_obs.TO_COLLECT]
        # Check for essential weather parameters
        self.assertIn('air_temperature', group_names)
        self.assertIn('wind', group_names)
        self.assertIn('precipitation', group_names)
        self.assertIn('pressure', group_names)

    def test_to_collect_gtl_codes(self):
        """Test TO_COLLECT has valid two-letter group codes."""
        gtl_codes = [entry[1] for entry in _fetch_dwd_obs.TO_COLLECT]
        expected_codes = ['TU', 'CS', 'FX', 'RR', 'P0', 'EB', 'VV', 'FF']
        for code in expected_codes:
            self.assertIn(code, gtl_codes)


class TestFetchDirlist(unittest.TestCase):
    """Tests for the fetch_dirlist function."""

    @patch('requests.get')
    def test_fetch_dirlist_returns_list(self, mock_get):
        """Test fetch_dirlist returns a list."""
        mock_response = MagicMock()
        mock_response.content = b'<a href="file1.zip">file1</a><a href="file2.zip">file2</a>'
        mock_get.return_value.__enter__ = MagicMock(return_value=mock_response)
        mock_get.return_value.__exit__ = MagicMock(return_value=False)

        result = _fetch_dwd_obs.fetch_dirlist('https://example.com')
        self.assertIsInstance(result, list)

    @patch('requests.get')
    def test_fetch_dirlist_extracts_links(self, mock_get):
        """Test fetch_dirlist extracts href links."""
        mock_response = MagicMock()
        mock_response.content = b'''
            <a href="file1.zip">File 1</a>
            <a href="file2.txt">File 2</a>
            <a href="data.csv">Data</a>
        '''
        mock_get.return_value.__enter__ = MagicMock(return_value=mock_response)
        mock_get.return_value.__exit__ = MagicMock(return_value=False)

        result = _fetch_dwd_obs.fetch_dirlist('https://example.com')
        self.assertIn('file1.zip', result)
        self.assertIn('file2.txt', result)
        self.assertIn('data.csv', result)

    @patch('requests.get')
    def test_fetch_dirlist_with_pattern(self, mock_get):
        """Test fetch_dirlist filters by pattern."""
        mock_response = MagicMock()
        mock_response.content = b'''
            <a href="file1.zip">File 1</a>
            <a href="file2.txt">File 2</a>
            <a href="data.zip">Data</a>
        '''
        mock_get.return_value.__enter__ = MagicMock(return_value=mock_response)
        mock_get.return_value.__exit__ = MagicMock(return_value=False)

        result = _fetch_dwd_obs.fetch_dirlist('https://example.com', pattern=r'.*\.zip')
        self.assertIn('file1.zip', result)
        self.assertIn('data.zip', result)
        self.assertNotIn('file2.txt', result)

    @patch('requests.get')
    def test_fetch_dirlist_empty_response(self, mock_get):
        """Test fetch_dirlist with empty response."""
        mock_response = MagicMock()
        mock_response.content = b'<html><body>No files</body></html>'
        mock_get.return_value.__enter__ = MagicMock(return_value=mock_response)
        mock_get.return_value.__exit__ = MagicMock(return_value=False)

        result = _fetch_dwd_obs.fetch_dirlist('https://example.com')
        self.assertEqual(result, [])

    @patch('requests.get')
    def test_fetch_dirlist_complex_pattern(self, mock_get):
        """Test fetch_dirlist with complex regex pattern."""
        mock_response = MagicMock()
        mock_response.content = b'''
            <a href="stundenwerte_TU_00001_hist.zip">Station 1</a>
            <a href="stundenwerte_TU_00002_hist.zip">Station 2</a>
            <a href="stundenwerte_FF_00001_hist.zip">Wind Station 1</a>
            <a href="readme.txt">Readme</a>
        '''
        mock_get.return_value.__enter__ = MagicMock(return_value=mock_response)
        mock_get.return_value.__exit__ = MagicMock(return_value=False)

        result = _fetch_dwd_obs.fetch_dirlist(
            'https://example.com',
            pattern=r'stundenwerte_TU_.*\.zip'
        )
        self.assertEqual(len(result), 2)
        self.assertIn('stundenwerte_TU_00001_hist.zip', result)
        self.assertIn('stundenwerte_TU_00002_hist.zip', result)


class TestFetchFile(unittest.TestCase):
    """Tests for the fetch_file function."""

    def test_fetch_file_invalid_era(self):
        """Test fetch_file raises for invalid era."""
        with self.assertRaises(ValueError) as context:
            _fetch_dwd_obs.fetch_file('TU', 12345, era='invalid')
        self.assertIn('era', str(context.exception).lower())

    def test_fetch_file_invalid_group(self):
        """Test fetch_file raises for unknown group."""
        with self.assertRaises(ValueError) as context:
            _fetch_dwd_obs.fetch_file('XX', 12345)
        self.assertIn('group', str(context.exception).lower())

    @patch('austaltools._fetch_dwd_obs._tools.download')
    @patch('austaltools._fetch_dwd_obs.fetch_dirlist')
    def test_fetch_file_valid_group(self, mock_dirlist, mock_download):
        """Test fetch_file with valid group code."""
        mock_dirlist.return_value = ['stundenwerte_TU_12345_hist.zip']
        mock_download.return_value = 'stundenwerte_TU_12345_hist.zip'

        result = _fetch_dwd_obs.fetch_file('TU', 12345)
        mock_download.assert_called_once()

    @patch('austaltools._fetch_dwd_obs._tools.download')
    def test_fetch_file_stations_list(self, mock_download):
        """Test fetch_file for stations list file."""
        mock_download.return_value = 'TU_Stundenwerte_Beschreibung_Stationen.txt'

        result = _fetch_dwd_obs.fetch_file('TU', 'stations')
        self.assertIn('Stationen', mock_download.call_args[0][0])

    @patch('austaltools._fetch_dwd_obs._tools.download')
    def test_fetch_file_stationen_alias(self, mock_download):
        """Test fetch_file accepts 'stationen' as alias for stations."""
        mock_download.return_value = 'TU_Stundenwerte_Beschreibung_Stationen.txt'

        result = _fetch_dwd_obs.fetch_file('TU', 'stationen')
        self.assertIn('Stationen', mock_download.call_args[0][0])

    def test_fetch_file_all_groups_valid(self):
        """Test all groups in TO_COLLECT are recognized."""
        for name, gtl, abbr in _fetch_dwd_obs.TO_COLLECT:
            # Should not raise ValueError for group
            try:
                with patch('austaltools._fetch_dwd_obs.fetch_dirlist') as mock_dirlist:
                    with patch('austaltools._fetch_dwd_obs._tools.download') as mock_download:
                        mock_dirlist.return_value = [f'stundenwerte_{gtl}_00001_hist.zip']
                        mock_download.return_value = f'stundenwerte_{gtl}_00001_hist.zip'
                        _fetch_dwd_obs.fetch_file(gtl, 1)
            except ValueError as e:
                if 'group' in str(e).lower():
                    self.fail(f"Group {gtl} should be recognized")


class TestFetchStationlist(unittest.TestCase):
    """Tests for the fetch_stationlist function."""

    @patch('austaltools._fetch_dwd_obs.fetch_file')
    def test_fetch_stationlist_returns_dict(self, mock_fetch_file):
        """Test fetch_stationlist returns a dictionary."""
        # Create mock station list file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Header line 1\n")
            f.write("Header line 2\n")
            f.write("00003 19370101 20110331            202     50.7827    6.0941 Station Name\n")
            temp_file = f.name

        mock_fetch_file.return_value = temp_file

        try:
            result = _fetch_dwd_obs.fetch_stationlist(years=None)
            self.assertIsInstance(result, dict)
        finally:
            os.unlink(temp_file)

    @patch('austaltools._fetch_dwd_obs.fetch_file')
    def test_fetch_stationlist_with_years_list(self, mock_fetch_file):
        """Test fetch_stationlist accepts years as list."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Header line 1\n")
            f.write("Header line 2\n")
            f.write("00003 19370101 20110331            202     50.7827    6.0941 Station Name\n")
            temp_file = f.name

        mock_fetch_file.return_value = temp_file

        try:
            result = _fetch_dwd_obs.fetch_stationlist(years=[2020, 2021, 2022])
            self.assertIsInstance(result, dict)
        finally:
            os.unlink(temp_file)

    @patch('austaltools._fetch_dwd_obs.fetch_file')
    def test_fetch_stationlist_with_single_year(self, mock_fetch_file):
        """Test fetch_stationlist converts single year to list."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Header line 1\n")
            f.write("Header line 2\n")
            f.write("00003 19370101 20110331            202     50.7827    6.0941 Station Name\n")
            temp_file = f.name

        mock_fetch_file.return_value = temp_file

        try:
            result = _fetch_dwd_obs.fetch_stationlist(years=2020)
            self.assertIsInstance(result, dict)
        finally:
            os.unlink(temp_file)


class TestGetMetaValue(unittest.TestCase):
    """Tests for the get_meta_value function."""

    def test_get_meta_value_file_not_found(self):
        """Test get_meta_value raises for non-existent file."""
        with self.assertRaises(ValueError) as context:
            _fetch_dwd_obs.get_meta_value(
                '/nonexistent/file.csv',
                '2020-01-01', '2020-12-31', 'param'
            )
        self.assertIn('not found', str(context.exception))

    def test_get_meta_value_invalid_metadata_type(self):
        """Test get_meta_value raises for invalid metadata type."""
        with self.assertRaises(ValueError):
            _fetch_dwd_obs.get_meta_value(
                12345,  # Invalid type
                '2020-01-01', '2020-12-31', 'param'
            )

    def test_get_meta_value_time_order(self):
        """Test get_meta_value raises when time_end before time_begin."""
        df = pd.DataFrame({
            'time': pd.to_datetime(['2020-01-01', '2020-06-01']),
            'param': [1.0, 2.0]
        })
        df.set_index('time', inplace=True)
        df.index = df.index.tz_localize('UTC')

        with self.assertRaises(ValueError) as context:
            _fetch_dwd_obs.get_meta_value(
                df, '2020-12-31', '2020-01-01', 'param'
            )
        self.assertIn('time_end', str(context.exception))

    def test_get_meta_value_parameter_not_found(self):
        """Test get_meta_value raises for missing parameter."""
        df = pd.DataFrame({
            'time': pd.to_datetime(['2020-01-01', '2020-06-01']),
            'existing_param': [1.0, 2.0]
        })
        df.set_index('time', inplace=True)
        df.index = df.index.tz_localize('UTC')

        with self.assertRaises(ValueError) as context:
            _fetch_dwd_obs.get_meta_value(
                df, '2020-01-01', '2020-12-31', 'missing_param'
            )
        self.assertIn('not found', str(context.exception))

    def test_get_meta_value_with_dataframe(self):
        """Test get_meta_value with DataFrame input."""
        df = pd.DataFrame({
            'time': pd.to_datetime(['2020-01-01', '2020-06-01', '2020-12-01']),
            'elevation': [100.0, 100.0, 105.0]
        })
        df.set_index('time', inplace=True)
        df.index = df.index.tz_localize('UTC')

        result = _fetch_dwd_obs.get_meta_value(
            df, '2020-01-01', '2020-12-31', 'elevation'
        )
        self.assertIsInstance(result, pd.Series)

    def test_get_meta_value_from_file(self):
        """Test get_meta_value reads from CSV file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("time,elevation,name\n")
            f.write("2020-01-01,100.0,Station A\n")
            f.write("2020-06-01,100.0,Station A\n")
            f.write("2020-12-01,105.0,Station A\n")
            temp_file = f.name

        try:
            result = _fetch_dwd_obs.get_meta_value(
                temp_file, '2020-01-01', '2020-12-31', 'elevation'
            )
            self.assertIsInstance(result, pd.Series)
        finally:
            os.unlink(temp_file)


class TestBuildTable(unittest.TestCase):
    """Tests for the build_table function."""

    def test_build_table_non_contiguous_years(self):
        """Test build_table raises for non-contiguous years."""
        dat_df = pd.DataFrame()
        meta_df = pd.DataFrame()

        with self.assertRaises(ValueError) as context:
            _fetch_dwd_obs.build_table(dat_df, meta_df, [2020, 2022])
        self.assertIn('contiguous', str(context.exception))

    def test_build_table_contiguous_years(self):
        """Test build_table accepts contiguous years."""
        # Create minimal test data
        idx = pd.date_range('2020-01-01', '2021-12-31 23:00', freq='h', tz='UTC')
        dat_df = pd.DataFrame(
            {'temp': np.random.randn(len(idx))},
            index=idx
        )
        meta_df = pd.DataFrame(
            {'elevation': [100.0] * len(idx)},
            index=idx
        )

        result = _fetch_dwd_obs.build_table(dat_df, meta_df, [2020, 2021])
        self.assertIsInstance(result, pd.DataFrame)

    def test_build_table_single_year(self):
        """Test build_table with single year."""
        idx = pd.date_range('2020-01-01', '2020-12-31 23:00', freq='h', tz='UTC')
        dat_df = pd.DataFrame(
            {'temp': np.random.randn(len(idx))},
            index=idx
        )
        meta_df = pd.DataFrame(
            {'elevation': [100.0] * len(idx)},
            index=idx
        )

        result = _fetch_dwd_obs.build_table(dat_df, meta_df, [2020])
        self.assertIsInstance(result, pd.DataFrame)

    def test_build_table_output_index(self):
        """Test build_table creates hourly index for full period."""
        idx = pd.date_range('2020-01-01', '2020-12-31 23:00', freq='h', tz='UTC')
        dat_df = pd.DataFrame({'temp': [20.0] * len(idx)}, index=idx)
        meta_df = pd.DataFrame({'elevation': [100.0] * len(idx)}, index=idx)

        result = _fetch_dwd_obs.build_table(dat_df, meta_df, [2020])

        # Check index spans full year
        self.assertEqual(result.index[0].year, 2020)
        self.assertEqual(result.index[0].month, 1)
        self.assertEqual(result.index[0].day, 1)
        self.assertEqual(result.index[-1].year, 2020)
        self.assertEqual(result.index[-1].month, 12)
        self.assertEqual(result.index[-1].day, 31)


class TestDataFromDownload(unittest.TestCase):
    """Tests for the data_from_download function."""

    def test_data_from_download_returns_dataframe(self):
        """Test data_from_download returns DataFrame."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create mock product file
            product_file = 'produkt_tu_stunde_test.txt'
            with open(os.path.join(tmpdir, product_file), 'w') as f:
                f.write("STATIONS_ID;MESS_DATUM;TT_TU;RF_TU;eor\n")
                f.write("00001;2020010100;5.5;80;eor\n")
                f.write("00001;2020010101;5.2;82;eor\n")
                f.write("00001;2020010102;4.8;85;eor\n")

            result = _fetch_dwd_obs.data_from_download([product_file], tmpdir)
            self.assertIsInstance(result, pd.DataFrame)

    def test_data_from_download_converts_time(self):
        """Test data_from_download converts MESS_DATUM to datetime index."""
        with tempfile.TemporaryDirectory() as tmpdir:
            product_file = 'produkt_tu_stunde_test.txt'
            with open(os.path.join(tmpdir, product_file), 'w') as f:
                f.write("STATIONS_ID;MESS_DATUM;TT_TU;RF_TU;eor\n")
                f.write("00001;2020010100;5.5;80;eor\n")
                f.write("00001;2020010101;5.2;82;eor\n")

            result = _fetch_dwd_obs.data_from_download([product_file], tmpdir)
            self.assertEqual(result.index.name, 'time')
            self.assertTrue(pd.api.types.is_datetime64_any_dtype(result.index))

    def test_data_from_download_drops_columns(self):
        """Test data_from_download drops STATIONS_ID, MESS_DATUM, eor."""
        with tempfile.TemporaryDirectory() as tmpdir:
            product_file = 'produkt_tu_stunde_test.txt'
            with open(os.path.join(tmpdir, product_file), 'w') as f:
                f.write("STATIONS_ID;MESS_DATUM;TT_TU;RF_TU;eor\n")
                f.write("00001;2020010100;5.5;80;eor\n")

            result = _fetch_dwd_obs.data_from_download([product_file], tmpdir)
            self.assertNotIn('STATIONS_ID', result.columns)
            self.assertNotIn('MESS_DATUM', result.columns)
            self.assertNotIn('eor', result.columns)

    def test_data_from_download_replaces_missing_values(self):
        """Test data_from_download replaces -999 with NaN."""
        with tempfile.TemporaryDirectory() as tmpdir:
            product_file = 'produkt_tu_stunde_test.txt'
            with open(os.path.join(tmpdir, product_file), 'w') as f:
                f.write("STATIONS_ID;MESS_DATUM;TT_TU;RF_TU;eor\n")
                f.write("00001;2020010100;-999;80;eor\n")
                f.write("00001;2020010101;5.2;-999;eor\n")

            result = _fetch_dwd_obs.data_from_download([product_file], tmpdir)
            # Check -999 values are replaced with NaN
            self.assertTrue(pd.isna(result['TT_TU'].iloc[0]))
            self.assertTrue(pd.isna(result['RF_TU'].iloc[1]))

    def test_data_from_download_merges_multiple_files(self):
        """Test data_from_download merges multiple product files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two product files with different columns
            product_file1 = 'produkt_tu_stunde_test.txt'
            with open(os.path.join(tmpdir, product_file1), 'w') as f:
                f.write("STATIONS_ID;MESS_DATUM;TT_TU;eor\n")
                f.write("00001;2020010100;5.5;eor\n")

            product_file2 = 'produkt_ff_stunde_test.txt'
            with open(os.path.join(tmpdir, product_file2), 'w') as f:
                f.write("STATIONS_ID;MESS_DATUM;F;eor\n")
                f.write("00001;2020010100;3.2;eor\n")

            result = _fetch_dwd_obs.data_from_download(
                [product_file1, product_file2], tmpdir
            )
            self.assertIn('TT_TU', result.columns)
            self.assertIn('F', result.columns)

    def test_data_from_download_integer_mess_datum(self):
        """Test data_from_download handles integer MESS_DATUM."""
        with tempfile.TemporaryDirectory() as tmpdir:
            product_file = 'produkt_tu_stunde_test.txt'
            with open(os.path.join(tmpdir, product_file), 'w') as f:
                f.write("STATIONS_ID;MESS_DATUM;TT_TU;eor\n")
                f.write("00001;2020010100;5.5;eor\n")

            result = _fetch_dwd_obs.data_from_download([product_file], tmpdir)
            self.assertEqual(result.index[0].year, 2020)
            self.assertEqual(result.index[0].month, 1)
            self.assertEqual(result.index[0].day, 1)
            self.assertEqual(result.index[0].hour, 0)

    def test_data_from_download_filters_old_data(self):
        """Test data_from_download removes data before OLDEST."""
        with tempfile.TemporaryDirectory() as tmpdir:
            product_file = 'produkt_tu_stunde_test.txt'
            with open(os.path.join(tmpdir, product_file), 'w') as f:
                f.write("STATIONS_ID;MESS_DATUM;TT_TU;eor\n")
                f.write("00001;1960010100;5.5;eor\n")  # Before OLDEST
                f.write("00001;2020010100;6.0;eor\n")  # After OLDEST

            result = _fetch_dwd_obs.data_from_download([product_file], tmpdir)
            # Should only contain data from 2020
            self.assertTrue(all(result.index >= _fetch_dwd_obs.OLDEST))


class TestMetaFromDownload(unittest.TestCase):
    """Tests for the meta_from_download function."""

    def test_meta_from_download_geographie_file(self):
        """Test meta_from_download parses Geographie metadata file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_file = 'Metadaten_Geographie_00001.txt'
            with open(os.path.join(tmpdir, meta_file), 'w',
                      encoding='iso-8859-1') as f:
                f.write("Stations_id;Stationshoehe;Geogr. Breite;Geogr. Laenge;"
                        "von_datum;bis_datum;Stationsname;eor\n")
                f.write("00001;100;51.0;7.0;19500101;20231231;TestStation;eor\n")

            result = _fetch_dwd_obs.meta_from_download(
                [meta_file], 1, tmpdir
            )
            self.assertIsInstance(result, pd.DataFrame)

    def test_meta_from_download_deduplicates_files(self):
        """Test meta_from_download deduplicates file list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_file = 'Metadaten_Geographie_00001.txt'
            with open(os.path.join(tmpdir, meta_file), 'w',
                      encoding='iso-8859-1') as f:
                f.write("Stations_id;Stationshoehe;Geogr. Breite;Geogr. Laenge;"
                        "von_datum;bis_datum;Stationsname;eor\n")
                f.write("00001;100;51.0;7.0;19500101;20231231;TestStation;eor\n")

            # Pass same file twice
            result = _fetch_dwd_obs.meta_from_download(
                [meta_file, meta_file], 1, tmpdir
            )
            self.assertIsInstance(result, pd.DataFrame)

    def test_meta_from_download_unknown_file_type(self):
        """Test meta_from_download raises for unknown metadata file type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            meta_file = 'Metadaten_Unknown_00001.txt'
            with open(os.path.join(tmpdir, meta_file), 'w',
                      encoding='iso-8859-1') as f:
                f.write("Stations_id;von_datum;bis_datum;eor\n")
                f.write("00001;19500101;20231231;eor\n")

            with self.assertRaises(ValueError) as context:
                _fetch_dwd_obs.meta_from_download([meta_file], 1, tmpdir)
            self.assertIn('unknown', str(context.exception).lower())


class TestFetchStation(unittest.TestCase):
    """Tests for the fetch_station function."""

    @patch('austaltools._fetch_dwd_obs.meta_from_download')
    @patch('austaltools._fetch_dwd_obs.data_from_download')
    @patch('austaltools._fetch_dwd_obs.fetch_file')
    @patch('shutil.rmtree')
    @patch('os.chdir')
    @patch('os.mkdir')
    def test_fetch_station_creates_temp_dir(self, mock_mkdir, mock_chdir,
                                             mock_rmtree, mock_fetch_file,
                                             mock_data, mock_meta):
        """Test fetch_station creates temporary directory for station."""
        mock_fetch_file.return_value = 'test.zip'
        mock_data.return_value = pd.DataFrame()
        mock_meta.return_value = pd.DataFrame()

        # Mock zipfile
        with patch('zipfile.ZipFile') as mock_zip:
            mock_zip_instance = MagicMock()
            mock_zip_instance.namelist.return_value = []
            mock_zip.return_value.__enter__ = MagicMock(
                return_value=mock_zip_instance
            )
            mock_zip.return_value.__exit__ = MagicMock(return_value=False)

            _fetch_dwd_obs.fetch_station(12345, store=False)

        mock_mkdir.assert_called_with('12345')

    @patch('austaltools._fetch_dwd_obs.meta_from_download')
    @patch('austaltools._fetch_dwd_obs.data_from_download')
    @patch('austaltools._fetch_dwd_obs.fetch_file')
    @patch('shutil.rmtree')
    @patch('os.chdir')
    @patch('os.mkdir')
    def test_fetch_station_store_false_returns_dataframes(
            self, mock_mkdir, mock_chdir, mock_rmtree,
            mock_fetch_file, mock_data, mock_meta):
        """Test fetch_station returns DataFrames when store=False."""
        mock_fetch_file.return_value = 'test.zip'
        expected_data = pd.DataFrame({'col': [1, 2, 3]})
        expected_meta = pd.DataFrame({'meta': ['a', 'b', 'c']})
        mock_data.return_value = expected_data
        mock_meta.return_value = expected_meta

        with patch('zipfile.ZipFile') as mock_zip:
            mock_zip_instance = MagicMock()
            mock_zip_instance.namelist.return_value = []
            mock_zip.return_value.__enter__ = MagicMock(
                return_value=mock_zip_instance
            )
            mock_zip.return_value.__exit__ = MagicMock(return_value=False)

            dat, meta = _fetch_dwd_obs.fetch_station(12345, store=False)

        self.assertIsInstance(dat, pd.DataFrame)
        self.assertIsInstance(meta, pd.DataFrame)


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and boundary conditions."""

    def test_obsfile_format_zero_padding(self):
        """Test OBSFILE_DWD correctly zero-pads station numbers."""
        result = _fetch_dwd_obs.OBSFILE_DWD % 1
        self.assertIn('00001', result)

        result = _fetch_dwd_obs.OBSFILE_DWD % 99999
        self.assertIn('99999', result)

    def test_metafile_format_zero_padding(self):
        """Test METAFILE_DWD correctly zero-pads station numbers."""
        result = _fetch_dwd_obs.METAFILE_DWD % 1
        self.assertIn('00001', result)

        result = _fetch_dwd_obs.METAFILE_DWD % 99999
        self.assertIn('99999', result)

    def test_oldest_is_utc(self):
        """Test OLDEST timestamp is UTC."""
        self.assertIsNotNone(_fetch_dwd_obs.OLDEST.tzinfo)


# Pytest-style parametrized tests

class TestPytestStyle:
    """Pytest-style tests for additional patterns."""

    @pytest.mark.parametrize("era", [None, 'recent', 'historical'])
    def test_fetch_file_valid_eras(self, era):
        """Test fetch_file accepts valid era values."""
        with patch('austaltools._fetch_dwd_obs.fetch_dirlist') as mock_dirlist:
            with patch('austaltools._fetch_dwd_obs._tools.download') as mock_dl:
                mock_dirlist.return_value = ['stundenwerte_TU_00001_hist.zip']
                mock_dl.return_value = 'file.zip'
                # Should not raise
                _fetch_dwd_obs.fetch_file('TU', 1, era=era)

    @pytest.mark.parametrize("invalid_era", ['future', 'past', 'current', ''])
    def test_fetch_file_invalid_eras(self, invalid_era):
        """Test fetch_file rejects invalid era values."""
        with pytest.raises(ValueError):
            _fetch_dwd_obs.fetch_file('TU', 1, era=invalid_era)

    @pytest.mark.parametrize("group_code", ['TU', 'CS', 'FX', 'RR', 'P0', 'EB', 'VV', 'FF'])
    def test_fetch_file_all_group_codes(self, group_code):
        """Test fetch_file recognizes all TO_COLLECT group codes."""
        with patch('austaltools._fetch_dwd_obs.fetch_dirlist') as mock_dirlist:
            with patch('austaltools._fetch_dwd_obs._tools.download') as mock_dl:
                mock_dirlist.return_value = [f'stundenwerte_{group_code}_00001_hist.zip']
                mock_dl.return_value = 'file.zip'
                # Should not raise ValueError for group
                _fetch_dwd_obs.fetch_file(group_code, 1)

    @pytest.mark.parametrize("station_alias", ['stations', 'stationen'])
    def test_fetch_file_station_aliases(self, station_alias):
        """Test fetch_file accepts both station list aliases."""
        with patch('austaltools._fetch_dwd_obs._tools.download') as mock_dl:
            mock_dl.return_value = 'stations.txt'
            result = _fetch_dwd_obs.fetch_file('TU', station_alias)
            assert 'Stationen' in mock_dl.call_args[0][0]

    @pytest.mark.parametrize("years", [
        [2020],
        [2020, 2021],
        [2020, 2021, 2022],
        [2000, 2001, 2002, 2003, 2004],
    ])
    def test_build_table_various_year_ranges(self, years):
        """Test build_table with various contiguous year ranges."""
        start = f'{years[0]}-01-01'
        end = f'{years[-1]}-12-31 23:00'
        idx = pd.date_range(start, end, freq='h', tz='UTC')
        dat_df = pd.DataFrame({'temp': np.random.randn(len(idx))}, index=idx)
        meta_df = pd.DataFrame({'elevation': [100.0] * len(idx)}, index=idx)

        result = _fetch_dwd_obs.build_table(dat_df, meta_df, years)
        assert isinstance(result, pd.DataFrame)
        assert result.index[0].year == years[0]
        assert result.index[-1].year == years[-1]


class TestIntegration(unittest.TestCase):
    """Integration tests for complete workflows."""

    def test_product_file_parsing_workflow(self):
        """Test complete workflow of parsing a product file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create realistic product file
            product_file = 'produkt_tu_stunde_20200101_20201231_00001.txt'
            with open(os.path.join(tmpdir, product_file), 'w') as f:
                f.write("STATIONS_ID;MESS_DATUM;  QN_9;TT_TU;RF_TU;eor\n")
                f.write("         1;2020010100;    3;  5.5;   80;eor\n")
                f.write("         1;2020010101;    3;  5.2;   82;eor\n")
                f.write("         1;2020010102;    3; -999;   85;eor\n")
                f.write("         1;2020010103;    3;  4.5; -999;eor\n")

            result = _fetch_dwd_obs.data_from_download([product_file], tmpdir)

            # Verify structure
            self.assertIn('TT_TU', result.columns)
            self.assertIn('RF_TU', result.columns)
            self.assertEqual(len(result), 4)

            # Verify missing value handling
            self.assertTrue(pd.isna(result.loc[result.index[2], 'TT_TU']))
            self.assertTrue(pd.isna(result.loc[result.index[3], 'RF_TU']))

            # Verify time parsing
            self.assertEqual(result.index[0].hour, 0)
            self.assertEqual(result.index[1].hour, 1)


if __name__ == '__main__':
    unittest.main()
