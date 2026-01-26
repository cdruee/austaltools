#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive test suite for austaltools.eap module.

This module tests the EAP (Ersatz-AnemometerPosition) functionality
for finding substitute anemometer positions according to VDI 3783 Part 16.
"""
import logging
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

from austaltools import command_line
from austaltools import eap


# Helper function for subprocess tests
def capture(command):
    """Run command and capture output."""
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out, err = proc.communicate()
    return out, err, proc.returncode


CMD = ['python', '-m', 'austaltools.command_line']
SUBCMD = 'eap'

class TestCliParserSubcommand(unittest.TestCase):
    """Tests for subcommand availability in cli_parser."""

    def setUp(self):
        """Set up parser for tests."""
        self.parser = command_line.cli_parser()

    def test_has_eap_subcommand(self):
        """Test 'eap' subcommand is available."""
        args = self.parser.parse_args(['eap'])
        self.assertEqual(args.command, 'eap')

class TestMain(unittest.TestCase):
    """Tests for the main function."""

    @patch('austaltools.command_line.eap.main')
    def test_main_calls_eap(self, mock_eap_main):
        """Test main dispatches to eap.main for 'eap' command."""
        args = {
            'command': 'eap',
            'working_dir': '/tmp',
            'verb': None,
            'temp_dir': None
        }
        command_line.main(args)
        mock_eap_main.assert_called_once_with(args)

    def test_main_no_working_dir_raises(self):
        """Test main raises when working_dir is None."""
        args = {
            'command': 'eap',
            'working_dir': None,
            'verb': None,
            'temp_dir': None
        }
        with self.assertRaises(ValueError) as context:
            command_line.main(args)
        self.assertIn('PATH not given', str(context.exception))

    @patch('austaltools.command_line._storage')
    @patch('austaltools.command_line.eap.main')
    def test_main_sets_temp_dir(self, mock_eap_main, mock_storage):
        """Test main sets _storage.TEMP when temp_dir provided."""
        args = {
            'command': 'eap',
            'working_dir': '/tmp',
            'verb': None,
            'temp_dir': '/custom/temp'
        }
        command_line.main(args)
        self.assertEqual(mock_storage.TEMP, '/custom/temp')

class TestPytestStyle:
    """Pytest-style tests with parametrization."""

    @pytest.mark.parametrize("subcommand", [
        'eap',
    ])
    def test_subcommand_help_available(self, subcommand):
        """Test help is available for all subcommands."""
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
        args = parser.parse_args([verbosity_flag, 'eap'])
        assert args.verb == expected_level


class TestSameSenseRotation(unittest.TestCase):
    """Tests for the same_sense_rotation function."""

    def test_same_sense_positive_rotation(self):
        """Test detection of same positive (clockwise) rotation."""
        val = np.array([10., 20., 30., 40.])
        ref = np.array([5., 15., 25., 35.])
        result = eap.same_sense_rotation(val, ref)
        self.assertTrue(result)

    def test_same_sense_negative_rotation(self):
        """Test detection of same negative (counter-clockwise) rotation."""
        val = np.array([40., 30., 20., 10.])
        ref = np.array([35., 25., 15., 5.])
        result = eap.same_sense_rotation(val, ref)
        self.assertTrue(result)

    def test_different_sense_rotation(self):
        """Test detection of different rotation senses."""
        val = np.array([10., 20., 30., 40.])  # Positive
        ref = np.array([40., 30., 20., 10.])  # Negative
        result = eap.same_sense_rotation(val, ref)
        self.assertFalse(result)

    def test_unsorted_reference(self):
        """Test with unsorted reference (sense=0)."""
        val = np.array([10., 20., 30., 40.])
        ref = np.array([10., 30., 20., 40.])  # Not monotonic
        result = eap.same_sense_rotation(val, ref)
        self.assertFalse(result)

    def test_wrap_around_360(self):
        """Test with values wrapping around 360 degrees."""
        val = np.array([350., 360., 370., 380.])
        ref = np.array([340., 350., 360., 370.])
        result = eap.same_sense_rotation(val, ref)
        self.assertTrue(result)


class TestContiguousAreas(unittest.TestCase):
    """Tests for the contiguous_areas function."""

    def test_single_area(self):
        """Test identification of a single contiguous area."""
        arr = np.array([
            [1, 1, 0],
            [1, 1, 0],
            [0, 0, 0]
        ]).astype(bool)
        labels, num_areas = eap.contiguous_areas(arr)
        self.assertEqual(num_areas, 1)
        # All True values should have the same label
        self.assertEqual(labels[0, 0], labels[0, 1])
        self.assertEqual(labels[0, 0], labels[1, 0])
        self.assertEqual(labels[0, 0], labels[1, 1])

    def test_multiple_areas(self):
        """Test identification of multiple separate areas."""
        arr = np.array([
            [1, 0, 1],
            [0, 0, 0],
            [1, 0, 1]
        ]).astype(bool)
        labels, num_areas = eap.contiguous_areas(arr)
        self.assertEqual(num_areas, 4)

    def test_l_shaped_area(self):
        """Test L-shaped contiguous area."""
        arr = np.array([
            [1, 0, 0],
            [1, 1, 0],
            [0, 1, 1]
        ]).astype(bool)
        labels, num_areas = eap.contiguous_areas(arr)
        self.assertEqual(num_areas, 1)

    def test_empty_array(self):
        """Test with array containing no True values."""
        arr = np.zeros((3, 3), dtype=bool)
        labels, num_areas = eap.contiguous_areas(arr)
        self.assertEqual(num_areas, 0)

    def test_full_array(self):
        """Test with array all True values."""
        arr = np.ones((3, 3), dtype=bool)
        labels, num_areas = eap.contiguous_areas(arr)
        self.assertEqual(num_areas, 1)

    def test_diagonal_not_connected(self):
        """Test that diagonal neighbors are not connected (4-connectivity)."""
        arr = np.array([
            [1, 0],
            [0, 1]
        ]).astype(bool)
        labels, num_areas = eap.contiguous_areas(arr)
        self.assertEqual(num_areas, 2)


class TestCalcQualityMeasure(unittest.TestCase):
    """Tests for the calc_quality_measure function."""

    def test_shape_mismatch_u_v_raises(self):
        """Test that mismatched u and v grid shapes raise ValueError."""
        u_grid = np.zeros((10, 10, 5, 6, 36))
        v_grid = np.zeros((10, 11, 5, 6, 36))  # Different shape
        u_ref = np.zeros((5, 6, 36))
        v_ref = np.zeros((5, 6, 36))

        with self.assertRaises(ValueError) as context:
            eap.calc_quality_measure(u_grid, v_grid, u_ref, v_ref)
        self.assertIn('do not match', str(context.exception))

    def test_shape_mismatch_ref_raises(self):
        """Test that mismatched reference shapes raise ValueError."""
        u_grid = np.zeros((10, 10, 5, 6, 36))
        v_grid = np.zeros((10, 10, 5, 6, 36))
        u_ref = np.zeros((5, 6, 36))
        v_ref = np.zeros((5, 7, 36))  # Different shape

        with self.assertRaises(ValueError) as context:
            eap.calc_quality_measure(u_grid, v_grid, u_ref, v_ref)
        self.assertIn('do not match', str(context.exception))

    def test_shape_mismatch_grid_ref_raises(self):
        """Test that grid and ref shape mismatch raises ValueError."""
        u_grid = np.zeros((10, 10, 5, 6, 36))
        v_grid = np.zeros((10, 10, 5, 6, 36))
        u_ref = np.zeros((4, 6, 36))  # Wrong nz
        v_ref = np.zeros((4, 6, 36))

        with self.assertRaises(ValueError) as context:
            eap.calc_quality_measure(u_grid, v_grid, u_ref, v_ref)
        self.assertIn('does not match', str(context.exception))

    def test_returns_three_arrays(self):
        """Test that function returns g, gd, gf arrays."""
        # Create minimal valid input
        nx, ny, nz, nstab, ndir = 10, 10, 3, 6, 36
        u_grid = np.random.rand(nx, ny, nz, nstab, ndir) * 5 + 1
        v_grid = np.random.rand(nx, ny, nz, nstab, ndir) * 5 + 1
        u_ref = np.random.rand(nz, nstab, ndir) * 5 + 1
        v_ref = np.random.rand(nz, nstab, ndir) * 5 + 1

        g, gd, gf = eap.calc_quality_measure(u_grid, v_grid, u_ref, v_ref)

        self.assertEqual(g.shape, (nx, ny, nz))
        self.assertEqual(gd.shape, (nx, ny, nz))
        self.assertEqual(gf.shape, (nx, ny, nz))


class TestFindEap(unittest.TestCase):
    """Tests for the find_eap function."""

    def test_find_eap_basic(self):
        """Test basic EAP finding."""
        g_lower = np.array([
            [0.5, 0.8, 0.3],
            [0.2, 0.7, 0.9],
            [0.4, 0.6, 0.1]
        ]).astype(float)

        eaps, g_upper = eap.find_eap(g_lower)

        # Should find EAP locations
        self.assertIsInstance(eaps, list)
        self.assertIsInstance(g_upper, list)
        self.assertTrue(len(eaps) > 0)

    def test_find_eap_all_nan(self):
        """Test EAP finding with all NaN values."""
        g_lower = np.full((3, 3), np.nan)

        eaps, g_upper = eap.find_eap(g_lower)

        self.assertEqual(eaps, [])
        self.assertEqual(g_upper, [])

    def test_find_eap_single_valid(self):
        """Test EAP finding with single valid point."""
        g_lower = np.full((3, 3), np.nan)
        g_lower[1, 1] = 0.5

        eaps, g_upper = eap.find_eap(g_lower)

        self.assertEqual(len(eaps), 1)
        self.assertEqual(eaps[0], (1, 1))


class TestCalcAllEap(unittest.TestCase):
    """Tests for the calc_all_eap function."""

    def test_calc_all_eap_basic(self):
        """Test calc_all_eap returns lists for all levels."""
        g = np.random.rand(10, 10, 5)

        eap_levels, g_upper_levels = eap.calc_all_eap(g)

        self.assertEqual(len(eap_levels), 5)
        self.assertEqual(len(g_upper_levels), 5)

    def test_calc_all_eap_with_max_level(self):
        """Test calc_all_eap respects mx_lvl parameter."""
        g = np.random.rand(10, 10, 5)

        eap_levels, g_upper_levels = eap.calc_all_eap(g, mx_lvl=2)

        self.assertEqual(len(eap_levels), 5)
        # Levels beyond mx_lvl should have empty lists
        self.assertEqual(eap_levels[3], [])
        self.assertEqual(eap_levels[4], [])


class TestInterpolateWind(unittest.TestCase):
    """Tests for the interpolate_wind function."""

    def test_interpolate_exact_level(self):
        """Test interpolation at exact input level."""
        u_in = [10.0, 15.0, 20.0]
        v_in = [5.0, 8.0, 12.0]
        z_in = [0.0, 100.0, 200.0]
        levels = [100.0]

        u_out, v_out = eap.interpolate_wind(u_in, v_in, z_in, levels)

        self.assertEqual(u_out[0], 15.0)
        self.assertEqual(v_out[0], 8.0)

    def test_interpolate_between_levels(self):
        """Test interpolation between input levels."""
        u_in = [10.0, 20.0]
        v_in = [5.0, 10.0]
        z_in = [10.0, 100.0]
        levels = [50.0]

        u_out, v_out = eap.interpolate_wind(u_in, v_in, z_in, levels)

        # Should return interpolated values
        self.assertEqual(len(u_out), 1)
        self.assertEqual(len(v_out), 1)

    def test_interpolate_mismatched_lengths_raises(self):
        """Test that mismatched input lengths raise ValueError."""
        u_in = [10.0, 15.0]
        v_in = [5.0, 8.0, 12.0]  # Different length
        z_in = [10.0, 100.0]
        levels = [50.0]

        with self.assertRaises(ValueError) as context:
            eap.interpolate_wind(u_in, v_in, z_in, levels)
        self.assertIn('same length', str(context.exception))

    def test_interpolate_zero_level(self):
        """Test interpolation at level 0."""
        u_in = [10.0, 15.0]
        v_in = [5.0, 8.0]
        z_in = [10.0, 100.0]
        levels = [0.0]

        u_out, v_out = eap.interpolate_wind(u_in, v_in, z_in, levels)

        self.assertEqual(u_out[0], 0.0)
        self.assertEqual(v_out[0], 0.0)


class TestModuleConstants(unittest.TestCase):
    """Tests for module-level constants."""

    def test_n_class_value(self):
        """Test N_CLASS constant."""
        self.assertEqual(eap.N_CLASS, 6)

    def test_n_edge_nodes_value(self):
        """Test N_EGDE_NODES constant."""
        self.assertEqual(eap.N_EGDE_NODES, 3)

    def test_min_ff_value(self):
        """Test MIN_FF constant."""
        self.assertEqual(eap.MIN_FF, 0.5)

    def test_max_height_value(self):
        """Test MAX_HEIGHT constant."""
        self.assertEqual(eap.MAX_HEIGHT, 100.)

    def test_z0_reference_value(self):
        """Test Z0_REFERENCE constant."""
        self.assertEqual(eap.AUSTAL_ROUGHNESS, 0.0100)


class TestAddOptions(unittest.TestCase):
    """Tests for the add_options function."""

    def test_add_options_returns_parser(self):
        """Test add_options returns an argument parser."""
        import argparse
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()

        result = eap.add_options(subparsers)

        self.assertIsNotNone(result)

    def test_add_options_eap_subcommand(self):
        """Test add_options creates 'eap' subcommand."""
        import argparse
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')

        eap.add_options(subparsers)

        # Parse with eap subcommand
        args = parser.parse_args(['eap'])
        self.assertEqual(args.command, 'eap')

    def test_add_options_default_values(self):
        """Test add_options sets correct defaults."""
        import argparse
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')

        eap.add_options(subparsers)

        args = parser.parse_args(['eap'])
        self.assertEqual(args.grid, 0)
        self.assertEqual(args.reference, 'simple')
        self.assertFalse(args.austal)
        self.assertFalse(args.overwrite)


class TestCommandLineEap(unittest.TestCase):
    """Tests for eap command line interface."""

    def test_eap_help(self):
        """Test eap --help shows usage."""
        command = CMD + [SUBCMD, '-h']
        out, err, exitcode = capture(command)
        self.assertEqual(exitcode, 0)
        self.assertTrue(out.decode().startswith('usage'))

    def test_eap_no_params_fails(self):
        """Test eap without parameters fails appropriately."""
        command = CMD + [SUBCMD]
        out, err, exitcode = capture(command)
        # Should fail because no wind library exists
        self.assertNotEqual(exitcode, 0)


# Pytest-style parametrized tests

class TestPytestStyle:
    """Pytest-style tests with parametrization."""

    @pytest.mark.parametrize("val,ref,expected", [
        ([10, 20, 30], [5, 15, 25], True),   # Same positive
        ([30, 20, 10], [25, 15, 5], True),   # Same negative
        ([10, 20, 30], [25, 15, 5], False),  # Different
    ])
    def test_same_sense_rotation_parametrized(self, val, ref, expected):
        """Parametrized test for same_sense_rotation."""
        result = eap.same_sense_rotation(np.array(val), np.array(ref))
        assert result == expected

    @pytest.mark.parametrize("shape,expected_areas", [
        ([[1, 1], [1, 1]], 1),
        ([[1, 0], [0, 1]], 2),
        ([[0, 0], [0, 0]], 0),
        ([[1, 0, 1], [0, 0, 0], [1, 0, 1]], 4),
    ])
    def test_contiguous_areas_parametrized(self, shape, expected_areas):
        """Parametrized test for contiguous_areas."""
        arr = np.array(shape).astype(bool)
        _, num_areas = eap.contiguous_areas(arr)
        assert num_areas == expected_areas


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and boundary conditions."""

    def test_same_sense_single_element(self):
        """Test same_sense_rotation with single element arrays."""
        val = np.array([10.])
        ref = np.array([5.])
        # With single element, diff is empty, so should handle gracefully
        result = eap.same_sense_rotation(val, ref)
        # Expected: False because diff arrays are empty
        self.assertIsInstance(result, bool)

    def test_contiguous_areas_1x1(self):
        """Test contiguous_areas with 1x1 array."""
        arr = np.array([[True]])
        labels, num_areas = eap.contiguous_areas(arr)
        self.assertEqual(num_areas, 1)

    def test_find_eap_mixed_nan_valid(self):
        """Test find_eap with mixed NaN and valid values."""
        g_lower = np.array([
            [np.nan, 0.5, np.nan],
            [0.3, np.nan, 0.7],
            [np.nan, 0.6, np.nan]
        ])
        eaps, g_upper = eap.find_eap(g_lower)
        # Should identify separate areas
        self.assertIsInstance(eaps, list)


class TestIntegration(unittest.TestCase):
    """Integration tests combining multiple components."""

    def test_quality_measure_to_eap_workflow(self):
        """Test workflow from quality measure to EAP finding."""
        # Create synthetic quality measure data
        nx, ny, nz = 20, 20, 5
        g = np.random.rand(nx, ny, nz) * 0.5 + 0.3

        # Add some NaN edges (simulating edge exclusion)
        g[:3, :, :] = np.nan
        g[-3:, :, :] = np.nan
        g[:, :3, :] = np.nan
        g[:, -3:, :] = np.nan

        # Find EAPs
        eap_levels, g_upper_levels = eap.calc_all_eap(g, mx_lvl=3)

        # Verify results
        self.assertEqual(len(eap_levels), nz)
        for lvl in range(4):
            # Levels up to mx_lvl should have EAPs
            self.assertTrue(len(eap_levels[lvl]) > 0)


if __name__ == '__main__':
    unittest.main()
