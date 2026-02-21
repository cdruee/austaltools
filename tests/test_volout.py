#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for austaltools.volout

Run with:
    pytest tests/test_volout.py -v
"""
import logging
import subprocess
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from austaltools import command_line
from austaltools.volout import is_valid_color, contrasting_shade, plot_voxels

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
SUBCMD = 'volout'

class TestCliParserSubcommand(unittest.TestCase):
    """Tests for subcommand availability in cli_parser."""

    def setUp(self):
        """Set up parser for tests."""
        self.parser = command_line.cli_parser()

    def test_has_volout_subcommand(self):
        """Test 'volout' subcommand is available."""
        args = self.parser.parse_args(['volout'])
        self.assertEqual(args.command, 'volout')

class TestMain(unittest.TestCase):
    """Tests for the main function."""

    @patch('austaltools.command_line.volout.main')
    def test_main_calls_volout(self, mock_volout_main):
        """Test main dispatches to volout.main for 'volout' command."""
        args = {
            'command': 'volout',
            'working_dir': '/tmp',
            'verb': None,
            'temp_dir': None
        }
        command_line.main(args)
        mock_volout_main.assert_called_once_with(args)

    def test_main_no_working_dir_raises(self):
        """Test main raises when working_dir is None."""
        args = {
            'command': 'volout',
            'working_dir': None,
            'verb': None,
            'temp_dir': None
        }
        with self.assertRaises(ValueError) as context:
            command_line.main(args)
        self.assertIn('PATH not given', str(context.exception))

    @patch('austaltools.command_line._storage')
    @patch('austaltools.command_line.volout.main')
    def test_main_sets_temp_dir(self, mock_volout_main, mock_storage):
        """Test main sets _storage.TEMP when temp_dir provided."""
        args = {
            'command': 'volout',
            'working_dir': '/tmp',
            'verb': None,
            'temp_dir': '/custom/temp'
        }
        command_line.main(args)
        self.assertEqual(mock_storage.TEMP, '/custom/temp')

class TestPytestStyle:
    """Pytest-style tests with parametrization."""

    @pytest.mark.parametrize("subcommand", [
        'volout',
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
        args = parser.parse_args([verbosity_flag, 'volout'])
        assert args.verb == expected_level


class TestIsValidColor:
    def test_named_color(self):
        assert is_valid_color('steelblue')

    def test_hex_color(self):
        assert is_valid_color('#aabbcc')

    def test_hex_color_with_alpha(self):
        assert is_valid_color('#aabbccff')

    def test_rgb_tuple(self):
        assert is_valid_color((0.1, 0.5, 0.9))

    def test_rgba_tuple(self):
        assert is_valid_color((0.1, 0.5, 0.9, 0.5))

    def test_invalid_string(self):
        assert not is_valid_color('notacolor')

    def test_invalid_tuple_out_of_range(self):
        assert not is_valid_color((1.5, 0.0, 0.0))

    def test_empty_string(self):
        assert not is_valid_color('')


# ===========================================================================
# contrasting_shade
# ===========================================================================

class TestContrastingShade:
    def test_returns_rgba_tuple(self):
        result = contrasting_shade('white')
        assert len(result) == 4

    def test_light_color_becomes_darker(self):
        r, g, b, a = contrasting_shade('white')
        # white has luminance 1.0 → should darken
        assert r < 1.0
        assert g < 1.0
        assert b < 1.0

    def test_dark_color_becomes_lighter(self):
        r, g, b, a = contrasting_shade('black')
        # black has luminance 0.0 → should lighten
        assert r > 0.0
        assert g > 0.0
        assert b > 0.0

    def test_alpha_preserved(self):
        _, _, _, a = contrasting_shade('steelblue')
        _, _, _, a_orig = __import__('matplotlib.colors', fromlist=['to_rgba']).to_rgba('steelblue')
        assert a == pytest.approx(a_orig)

    def test_factor_zero_unchanged(self):
        import matplotlib.colors as mcolors
        orig = mcolors.to_rgba('steelblue')
        result = contrasting_shade('steelblue', factor=0.0)
        assert result == pytest.approx(orig, abs=1e-6)

    def test_factor_clamps_to_valid_range(self):
        r, g, b, a = contrasting_shade('white', factor=2.0)
        assert 0.0 <= r <= 1.0
        assert 0.0 <= g <= 1.0
        assert 0.0 <= b <= 1.0


# ===========================================================================
# angle / camera parsing  (tested via the logic in main(), extracted here)
# ===========================================================================

def parse_angle(angle):
    """
    Replicate the angle-parsing logic from volout.main() so we can test it
    independently without needing a full args dict or file I/O.
    Returns (azi_from, ele_from, zoom).
    """
    if isinstance(angle, str):
        cardinals = {'N': 0, 'E': 90, 'S': 180, 'W': 270}
        intercardinals = {'NE': 45, 'SE': 135, 'SW': 225, 'NW': 315}
        up = angle.upper()
        if up in cardinals:
            return float(cardinals[up]), 0.0, None
        elif up in intercardinals:
            return float(intercardinals[up]), 40.0, None
        else:
            angle = angle.strip('()')
            try:
                parts = [float(v) for v in angle.replace(',', ' ').split()]
            except ValueError:
                raise ValueError(f"Unrecognised angle value: {angle!r}")
            if len(parts) == 1:
                return parts[0], 40.0, 1.0
            elif len(parts) == 2:
                return parts[0], parts[1], 1.0
            elif len(parts) == 3:
                return parts[0], parts[1], parts[2]
            else:
                raise ValueError(f"Angle string must have 1–3 values, got: {angle!r}")
    elif isinstance(angle, (int, float)):
        return float(angle), 40.0, 1.0
    elif isinstance(angle, (list, tuple)):
        if len(angle) == 2:
            return float(angle[0]), float(angle[1]), 1.0
        elif len(angle) == 3:
            return float(angle[0]), float(angle[1]), float(angle[2])
        else:
            raise ValueError(f"Tuple angle must have 2 or 3 elements")
    else:
        raise ValueError(f"Angle must be string, float, or tuple, not {type(angle)}")


class TestParseAngle:
    # cardinal directions
    @pytest.mark.parametrize("direction,expected_azi", [
        ('N', 0), ('E', 90), ('S', 180), ('W', 270),
        ('n', 0), ('s', 180),
    ])
    def test_cardinal(self, direction, expected_azi):
        azi, ele, zoom = parse_angle(direction)
        assert azi == expected_azi
        assert ele == 0.0
        assert zoom is None

    # intercardinal directions
    @pytest.mark.parametrize("direction,expected_azi", [
        ('NE', 45), ('SE', 135), ('SW', 225), ('NW', 315),
        ('sw', 225), ('Ne', 45),
    ])
    def test_intercardinal(self, direction, expected_azi):
        azi, ele, zoom = parse_angle(direction)
        assert azi == expected_azi
        assert ele == 40.0
        assert zoom is None

    # numeric strings
    def test_numeric_string_single(self):
        azi, ele, zoom = parse_angle('225')
        assert azi == 225.0
        assert ele == 40.0
        assert zoom == 1.0

    def test_numeric_string_two_values_comma(self):
        azi, ele, zoom = parse_angle('225,30')
        assert azi == 225.0
        assert ele == 30.0

    def test_numeric_string_two_values_space(self):
        azi, ele, zoom = parse_angle('225 30')
        assert azi == 225.0
        assert ele == 30.0

    def test_numeric_string_three_values(self):
        azi, ele, zoom = parse_angle('225,30,0.5')
        assert azi == 225.0
        assert ele == 30.0
        assert zoom == 0.5

    def test_numeric_string_with_parentheses(self):
        azi, ele, zoom = parse_angle('(225,30,0.5)')
        assert azi == 225.0
        assert zoom == 0.5

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError):
            parse_angle('diagonal')

    def test_too_many_values_raises(self):
        with pytest.raises(ValueError):
            parse_angle('1,2,3,4')

    # float / int
    def test_float(self):
        azi, ele, zoom = parse_angle(135.0)
        assert azi == 135.0
        assert ele == 40.0
        assert zoom == 1.0

    def test_int(self):
        azi, ele, zoom = parse_angle(270)
        assert azi == 270.0

    # tuple / list
    def test_tuple_two(self):
        azi, ele, zoom = parse_angle((180, 25))
        assert azi == 180.0
        assert ele == 25.0
        assert zoom == 1.0

    def test_list_three(self):
        azi, ele, zoom = parse_angle([90, 20, 0.5])
        assert zoom == 0.5

    def test_bad_type_raises(self):
        with pytest.raises(ValueError):
            parse_angle({'azi': 45})


# ===========================================================================
# plot_voxels  (smoke tests — check it runs without error)
# ===========================================================================

@pytest.fixture
def simple_grid():
    """Small grid with a few filled cells."""
    grid = np.zeros((10, 10, 5), dtype=int)
    grid[2:5, 2:5, 0:3] = 1
    grid[6, 6, 0:4] = 1
    return grid


@pytest.fixture
def hh():
    return [0.0, 3.0, 6.0, 10.0, 15.0, 20.0]  # nk+1 = 6 entries for nk=5


class TestPlotVoxels:
    def test_runs_default(self, simple_grid, hh):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        plot_voxels(simple_grid, 0.0, 0.0, 10.0, hh)
        plt.close('all')

    def test_runs_clip_fit(self, simple_grid, hh):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        plot_voxels(simple_grid, 0.0, 0.0, 10.0, hh, clip='fit')
        plt.close('all')

    def test_runs_clip_center(self, simple_grid, hh):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        plot_voxels(simple_grid, 0.0, 0.0, 10.0, hh, clip='center')
        plt.close('all')

    def test_runs_perspective(self, simple_grid, hh):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        plot_voxels(simple_grid, 0.0, 0.0, 10.0, hh, zoom=0.5)
        plt.close('all')

    def test_runs_custom_color_single(self, simple_grid, hh):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        plot_voxels(simple_grid, 0.0, 0.0, 10.0, hh, color='tomato')
        plt.close('all')

    def test_runs_custom_color_two(self, simple_grid, hh):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        plot_voxels(simple_grid, 0.0, 0.0, 10.0, hh, color=('tomato', 'darkred'))
        plt.close('all')

    def test_invalid_color_raises(self, simple_grid, hh):
        with pytest.raises(ValueError):
            plot_voxels(simple_grid, 0.0, 0.0, 10.0, hh, color='notacolor')

    def test_empty_grid_returns_none(self, hh):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        empty = np.zeros((5, 5, 5), dtype=int)
        result = plot_voxels(empty, 0.0, 0.0, 10.0, hh)
        assert result is None
        plt.close('all')

    def test_hh_wrong_length_raises(self, simple_grid):
        bad_hh = [0.0, 1.0]  # clearly wrong for nk=5
        with pytest.raises(ValueError):
            plot_voxels(simple_grid, 0.0, 0.0, 10.0, bad_hh)

    def test_nk_entries_hh(self, simple_grid):
        """hh with exactly nk entries (lower edges only) should also work."""
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        hh_nk = [0.0, 3.0, 6.0, 10.0, 15.0]  # 5 entries for nk=5
        plot_voxels(simple_grid, 0.0, 0.0, 10.0, hh_nk)
        plt.close('all')
