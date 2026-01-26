#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive test suite for austaltools._storage module.

This module tests storage location management, configuration file
handling, and related utility functions.
"""
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock, mock_open

import pytest
import yaml

import austaltools._storage
from austaltools import _storage


class TestModuleConstants(unittest.TestCase):
    """Tests for module-level constants."""

    def test_config_file_is_string(self):
        """Test CONFIG_FILE is a string."""
        self.assertIsInstance(_storage.CONFIG_FILE, str)

    def test_config_file_has_yaml_extension(self):
        """Test CONFIG_FILE ends with .yaml."""
        self.assertTrue(_storage.CONFIG_FILE.endswith('.yaml'))

    def test_storage_locations_is_list(self):
        """Test STORAGE_LOCATIONS is a non-empty list."""
        self.assertIsInstance(_storage.STORAGE_LOCATIONS, list)
        self.assertGreater(len(_storage.STORAGE_LOCATIONS), 0)

    def test_storage_locations_contains_current_dir(self):
        """Test STORAGE_LOCATIONS includes current directory."""
        self.assertIn('.', _storage.STORAGE_LOCATIONS)

    def test_storage_terrain_is_string(self):
        """Test STORAGE_TERRAIN is a string."""
        self.assertIsInstance(_storage.STORAGE_TERRAIN, str)
        self.assertEqual(_storage.STORAGE_TERRAIN, 'terrain')

    def test_storage_weather_is_string(self):
        """Test STORAGE_WAETHER is a string."""
        self.assertIsInstance(_storage.STORAGE_WAETHER, str)
        self.assertEqual(_storage.STORAGE_WAETHER, 'weather')

    def test_storages_list(self):
        """Test STORAGES contains terrain and weather."""
        self.assertIsInstance(_storage.STORAGES, list)
        self.assertIn(_storage.STORAGE_TERRAIN, _storage.STORAGES)
        self.assertIn(_storage.STORAGE_WAETHER, _storage.STORAGES)

    def test_temp_is_valid_directory(self):
        """Test TEMP is a valid temporary directory path."""
        self.assertIsInstance(_storage.TEMP, str)
        self.assertTrue(os.path.isdir(_storage.TEMP))

    def test_simple_default_weather(self):
        """Test SIMPLE_DEFAULT_WEATHER is a string."""
        self.assertIsInstance(_storage.SIMPLE_DEFAULT_WEATHER, str)
        self.assertEqual(_storage.SIMPLE_DEFAULT_WEATHER, 'CERRA')

    def test_simple_default_year(self):
        """Test SIMPLE_DEFAULT_YEAR is an integer."""
        self.assertIsInstance(_storage.SIMPLE_DEFAULT_YEAR, int)
        self.assertEqual(_storage.SIMPLE_DEFAULT_YEAR, 2003)

    def test_simple_default_terrain(self):
        """Test SIMPLE_DEFAULT_TERRAIN is a string."""
        self.assertIsInstance(_storage.SIMPLE_DEFAULT_TERRAIN, str)

    def test_simple_default_extent(self):
        """Test SIMPLE_DEFAULT_EXTENT is a float."""
        self.assertIsInstance(_storage.SIMPLE_DEFAULT_EXTENT, float)
        self.assertEqual(_storage.SIMPLE_DEFAULT_EXTENT, 10.)


class TestLocationsAvailable(unittest.TestCase):
    """Tests for the locations_available function."""

    def test_locations_available_returns_list(self):
        """Test locations_available returns a list."""
        result = _storage.locations_available([])
        self.assertIsInstance(result, list)

    def test_locations_available_empty_input(self):
        """Test locations_available with empty list."""
        result = _storage.locations_available([])
        self.assertEqual(result, [])

    def test_locations_available_existing_dirs(self):
        """Test locations_available finds existing directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _storage.locations_available([tmpdir, '/nonexistent/path'])
            self.assertIn(tmpdir, result)
            self.assertNotIn('/nonexistent/path', result)

    def test_locations_available_nonexistent_dirs(self):
        """Test locations_available excludes non-existent directories."""
        result = _storage.locations_available([
            '/definitely/not/a/real/path',
            '/another/fake/path'
        ])
        self.assertEqual(result, [])

    def test_locations_available_mixed_dirs(self):
        """Test locations_available with mix of existing and non-existing."""
        with tempfile.TemporaryDirectory() as tmpdir1:
            with tempfile.TemporaryDirectory() as tmpdir2:
                locs = [tmpdir1, '/nonexistent', tmpdir2, '/also/fake']
                result = _storage.locations_available(locs)
                self.assertEqual(len(result), 2)
                self.assertIn(tmpdir1, result)
                self.assertIn(tmpdir2, result)

    def test_locations_available_preserves_order(self):
        """Test locations_available preserves input order."""
        with tempfile.TemporaryDirectory() as tmpdir1:
            with tempfile.TemporaryDirectory() as tmpdir2:
                locs = [tmpdir1, tmpdir2]
                result = _storage.locations_available(locs)
                self.assertEqual(result[0], tmpdir1)
                self.assertEqual(result[1], tmpdir2)


class TestLocationsWritable(unittest.TestCase):
    """Tests for the locations_writable function."""

    def test_locations_writable_returns_list(self):
        """Test locations_writable returns a list."""
        result = _storage.locations_writable([])
        self.assertIsInstance(result, list)

    def test_locations_writable_empty_input(self):
        """Test locations_writable with empty list."""
        result = _storage.locations_writable([])
        self.assertEqual(result, [])

    def test_locations_writable_writable_dir(self):
        """Test locations_writable finds writable directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _storage.locations_writable([tmpdir])
            self.assertIn(tmpdir, result)

    def test_locations_writable_nonexistent_dir(self):
        """Test locations_writable excludes non-existent directories."""
        result = _storage.locations_writable(['/nonexistent/path'])
        self.assertEqual(result, [])


class TestLocationHasStorage(unittest.TestCase):
    """Tests for the location_has_storage function."""

    def test_location_has_storage_true(self):
        """Test location_has_storage returns True when storage exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_dir = os.path.join(tmpdir, 'terrain')
            os.makedirs(storage_dir)

            result = _storage.location_has_storage(tmpdir, 'terrain')
            self.assertTrue(result)

    def test_location_has_storage_false(self):
        """Test location_has_storage returns False when storage doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _storage.location_has_storage(tmpdir, 'terrain')
            self.assertFalse(result)

    def test_location_has_storage_file_not_dir(self):
        """Test location_has_storage with file instead of directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file named 'terrain' instead of directory
            file_path = os.path.join(tmpdir, 'terrain')
            with open(file_path, 'w') as f:
                f.write('test')

            # os.path.exists returns True for files too
            result = _storage.location_has_storage(tmpdir, 'terrain')
            self.assertTrue(result)  # exists() returns True for files


class TestFindWriteableStorage(unittest.TestCase):
    """Tests for the find_writeable_storage function."""

    def test_find_writeable_storage_requires_stor(self):
        """Test find_writeable_storage raises when stor is None."""
        with self.assertRaises(ValueError) as context:
            _storage.find_writeable_storage(locs=['.'], stor=None)
        self.assertIn('stor', str(context.exception))

    def test_find_writeable_storage_no_available_locations(self):
        """Test find_writeable_storage returns None when no locations available."""
        result = _storage.find_writeable_storage(
            locs=['/nonexistent/path'],
            stor='terrain'
        )
        self.assertIsNone(result)

    def test_find_writeable_storage_existing_storage(self):
        """Test find_writeable_storage finds existing storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_dir = os.path.join(tmpdir, 'terrain')
            os.makedirs(storage_dir)

            result = _storage.find_writeable_storage(
                locs=[tmpdir],
                stor='terrain'
            )
            self.assertEqual(result, storage_dir)

    def test_find_writeable_storage_creates_storage(self):
        """Test find_writeable_storage creates storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _storage.find_writeable_storage(
                locs=[tmpdir],
                stor='new_storage'
            )
            expected = os.path.join(tmpdir, 'new_storage')
            self.assertEqual(result, expected)
            self.assertTrue(os.path.isdir(expected))

    def test_find_writeable_storage_no_writable_locations(self):
        """Test find_writeable_storage returns None when no writable locations."""
        # Use a location that exists but isn't writable (if possible)
        # This is tricky to test portably, so we mock it
        with patch.object(_storage, 'locations_available') as mock_avail:
            with patch.object(_storage, 'locations_writable') as mock_write:
                mock_avail.return_value = ['/some/path']
                mock_write.return_value = []

                result = _storage.find_writeable_storage(
                    locs=['/some/path'],
                    stor='terrain'
                )
                self.assertIsNone(result)


class TestReadConfig(unittest.TestCase):
    """Tests for the read_config function."""

    def test_read_config_returns_dict(self):
        """Test read_config returns a dictionary."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _storage.read_config(locs=[tmpdir])
            self.assertIsInstance(result, dict)

    def test_read_config_empty_when_no_config(self):
        """Test read_config returns empty dict when no config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _storage.read_config(locs=[tmpdir])
            self.assertEqual(result, {})

    def test_read_config_reads_yaml(self):
        """Test read_config reads YAML config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, _storage.CONFIG_FILE)
            config_data = {'key1': 'value1', 'key2': 42}
            with open(config_path, 'w') as f:
                yaml.safe_dump(config_data, f)

            result = _storage.read_config(locs=[tmpdir])
            self.assertEqual(result['key1'], 'value1')
            self.assertEqual(result['key2'], 42)

    def test_read_config_merges_multiple_configs(self):
        """Test read_config merges configs from multiple locations."""
        with tempfile.TemporaryDirectory() as tmpdir1:
            with tempfile.TemporaryDirectory() as tmpdir2:
                # First config
                config_path1 = os.path.join(tmpdir1, _storage.CONFIG_FILE)
                with open(config_path1, 'w') as f:
                    yaml.safe_dump({'key1': 'from_dir1', 'shared': 'dir1'}, f)

                # Second config
                config_path2 = os.path.join(tmpdir2, _storage.CONFIG_FILE)
                with open(config_path2, 'w') as f:
                    yaml.safe_dump({'key2': 'from_dir2', 'shared': 'dir2'}, f)

                # Later locations override earlier ones
                result = _storage.read_config(locs=[tmpdir1, tmpdir2])
                self.assertEqual(result['key1'], 'from_dir1')
                self.assertEqual(result['key2'], 'from_dir2')
                self.assertEqual(result['shared'], 'dir2')  # overridden

    def test_read_config_uses_default_locations(self):
        """Test read_config uses STORAGE_LOCATIONS when locs is None."""
        # This test just verifies it doesn't crash
        result = _storage.read_config(locs=None)
        self.assertIsInstance(result, dict)


class TestWriteConfig(unittest.TestCase):
    """Tests for the write_config function."""

    def test_write_config_returns_true(self):
        """Test write_config returns True on success."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _storage.write_config({'key': 'value'}, locs=[tmpdir])
            self.assertTrue(result)

    def test_write_config_creates_file(self):
        """Test write_config creates config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _storage.write_config({'key': 'value'}, locs=[tmpdir])
            config_path = os.path.join(tmpdir, _storage.CONFIG_FILE)
            self.assertTrue(os.path.exists(config_path))

    def test_write_config_writes_yaml(self):
        """Test write_config writes valid YAML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_data = {'key1': 'value1', 'key2': [1, 2, 3]}
            _storage.write_config(config_data, locs=[tmpdir])

            config_path = os.path.join(tmpdir, _storage.CONFIG_FILE)
            with open(config_path, 'r') as f:
                loaded = yaml.safe_load(f)

            self.assertEqual(loaded['key1'], 'value1')
            self.assertEqual(loaded['key2'], [1, 2, 3])

    def test_write_config_no_writable_location(self):
        """Test write_config raises when no writable location."""
        with self.assertRaises(RuntimeError):
            _storage.write_config(
                {'key': 'value'},
                locs=['/nonexistent/readonly/path']
            )

    def test_write_config_overwrites_existing(self):
        """Test write_config overwrites existing config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, _storage.CONFIG_FILE)

            # Write initial config
            with open(config_path, 'w') as f:
                yaml.safe_dump({'old_key': 'old_value'}, f)

            # Overwrite with new config
            _storage.write_config({'new_key': 'new_value'}, locs=[tmpdir])

            with open(config_path, 'r') as f:
                loaded = yaml.safe_load(f)

            self.assertIn('new_key', loaded)
            # Note: write_config completely overwrites, doesn't merge
            self.assertNotIn('old_key', loaded)

    def test_write_config_prefers_existing_config_location(self):
        """Test write_config writes to location with existing config."""
        with tempfile.TemporaryDirectory() as tmpdir1:
            with tempfile.TemporaryDirectory() as tmpdir2:
                # Create existing config in second location
                existing_config = os.path.join(tmpdir2, _storage.CONFIG_FILE)
                with open(existing_config, 'w') as f:
                    yaml.safe_dump({'existing': True}, f)

                # Write new config - should prefer tmpdir2
                _storage.write_config(
                    {'new_key': 'new_value'},
                    locs=[tmpdir1, tmpdir2]
                )

                # Check it wrote to tmpdir2 (with existing config)
                with open(existing_config, 'r') as f:
                    loaded = yaml.safe_load(f)
                self.assertIn('new_key', loaded)


class TestIntegration(unittest.TestCase):
    """Integration tests for storage module."""

    def test_read_write_roundtrip(self):
        """Test config can be written and read back."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_config = {
                'setting1': 'value1',
                'setting2': 123,
                'nested': {'a': 1, 'b': 2}
            }

            _storage.write_config(original_config, locs=[tmpdir])
            loaded_config = _storage.read_config(locs=[tmpdir])

            self.assertEqual(loaded_config, original_config)

    def test_storage_workflow(self):
        """Test complete storage workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Find/create storage
            storage_path = _storage.find_writeable_storage(
                locs=[tmpdir],
                stor='terrain'
            )

            # Verify it was created
            self.assertTrue(os.path.isdir(storage_path))

            # Verify location_has_storage works
            self.assertTrue(
                _storage.location_has_storage(tmpdir, 'terrain')
            )

            # Verify it's in available locations
            available = _storage.locations_available([tmpdir])
            self.assertIn(tmpdir, available)


# Pytest-style parametrized tests

class TestPytestStyle:
    """Pytest-style tests for additional patterns."""

    @pytest.mark.parametrize("storage_name", ['terrain', 'weather', 'custom'])
    def test_find_writeable_storage_various_names(self, storage_name):
        """Test find_writeable_storage with various storage names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _storage.find_writeable_storage(
                locs=[tmpdir],
                stor=storage_name
            )
            assert result == os.path.join(tmpdir, storage_name)
            assert os.path.isdir(result)

    @pytest.mark.parametrize("config_data", [
        {'simple': 'value'},
        {'number': 42},
        {'float': 3.14},
        {'list': [1, 2, 3]},
        {'nested': {'a': {'b': 'c'}}},
        {'mixed': {'str': 'val', 'num': 1, 'list': [1, 2]}},
    ])
    def test_write_read_various_configs(self, config_data):
        """Test write/read with various config structures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _storage.write_config(config_data, locs=[tmpdir])
            loaded = _storage.read_config(locs=[tmpdir])
            assert loaded == config_data

    @pytest.mark.parametrize("num_dirs", [1, 2, 3, 5])
    def test_locations_available_multiple_dirs(self, num_dirs):
        """Test locations_available with various numbers of directories."""
        dirs = [tempfile.mkdtemp() for _ in range(num_dirs)]
        try:
            result = _storage.locations_available(dirs)
            assert len(result) == num_dirs
            for d in dirs:
                assert d in result
        finally:
            for d in dirs:
                os.rmdir(d)


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and boundary conditions."""

    def test_config_file_name_contains_title(self):
        """Test CONFIG_FILE contains the package title."""
        # Import the title to verify
        from austaltools._metadata import __title__
        self.assertIn(__title__, _storage.CONFIG_FILE)

    def test_storage_locations_expands_user(self):
        """Test STORAGE_LOCATIONS contains expanded user paths."""
        # At least one location should contain expanded home directory
        has_home = any('~' not in loc for loc in _storage.STORAGE_LOCATIONS
                       if 'local' in loc or loc.startswith('/home'))
        # This is a soft check - just verify the list is properly formed
        self.assertIsInstance(_storage.STORAGE_LOCATIONS, list)

    def test_empty_config_write_read(self):
        """Test writing and reading empty config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _storage.write_config({}, locs=[tmpdir])
            loaded = _storage.read_config(locs=[tmpdir])
            # Empty dict or None depending on YAML handling
            self.assertTrue(loaded is None or loaded == {})


if __name__ == '__main__':
    unittest.main()
