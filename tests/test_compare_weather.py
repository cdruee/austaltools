#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive test suite for austaltools.compare_weather module.

This module tests the ``compare-weather`` sub-command, which compares
two weather timeseries by running AUSTAL on a synthetic flat-terrain
domain for each of them and computing the overlap of their
above-threshold areas (see ``compare_weather.py``'s own module
docstring for the full picture).

Modelled after ``tests/test_eap.py``: pure/helper functions are tested
directly with synthetic data; ``compute_overlap()`` is tested with
``_read_grid_file()`` monkeypatched to inject known arrays, so its
threshold/overlap/area-fraction math is checked exactly without
needing real AUSTAL output files; ``run_austal()`` and ``main()`` are
tested against a *fake* ``austal`` executable (a small shell script
mimicking just the bits of AUSTAL's behavior this tool relies on --
its progress lines, its "AUSTAL beendet." success marker, and the
per-position result file it produces) so the whole pipeline can be
exercised without a real AUSTAL installation. The command-line
subprocess smoke tests (``TestCommandLineCompareWeather``,
``test_subcommand_help_available``) assume a fully installed
``austaltools`` package, exactly like the equivalent tests in
``test_eap.py`` do.

Two real, full-year hourly weather timeseries are included as fixtures
(``example_obs_2003.akterm``, ``example_mod_2003.akterm``) so that the
file-staging parts of ``run_austal()`` get exercised against genuine,
production-sized AKTERM data rather than only empty dummy files, and
so that ``TestIntegrationRealAustal`` -- skipped unless a real
``austal`` executable is on ``PATH`` -- can run the complete tool
end-to-end on real data.
"""
import argparse
import contextlib
import io
import logging
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from austaltools import command_line
from austaltools import compare_weather as cw


# ---------------------------------------------------------------------
# helpers shared by several test classes
# ---------------------------------------------------------------------

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
SUBCMD = 'compare-weather'

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLE_OBS = os.path.join(HERE, 'example_obs_2003.akterm')
EXAMPLE_MOD = os.path.join(HERE, 'example_mod_2003.akterm')


def _assert_parse_error(testcase, parser, argv):
    """Assert that ``parser.parse_args(argv)`` exits (argparse's way of
    reporting a bad command line), without spamming the test output
    with argparse's own usage/error message on stderr."""
    with contextlib.redirect_stderr(io.StringIO()):
        with testcase.assertRaises(SystemExit):
            parser.parse_args(argv)


# ---------------------------------------------------------------------
# fake `austal` executable, used by run_austal()/main() tests so they
# don't need a real AUSTAL installation
# ---------------------------------------------------------------------

_FAKE_AUSTAL_TEMPLATE = textwrap.dedent("""\
    #!/bin/bash
    mkdir -p lib
    {sleep_line}
    if [ -t 1 ]; then
      echo "Fertig berechnet: 50 %"
      echo "Fertig berechnet: 100 %"
    fi
    {result_line}
    echo "{final_line}"
    exit {exit_code}
    """)


def _write_fake_austal(path, exit_code=0, final_line='AUSTAL beendet.',
                       result_file='xx-y00a.dmna', sleep=0.0):
    """
    Write a fake ``austal`` executable to ``path`` that mimics just
    enough of the real program's behavior for run_austal() to be
    exercised: it optionally emits AUSTAL's own "Fertig berechnet: N %"
    progress lines (only when stdout is a tty, exactly like the real
    thing), touches the requested per-position result file name in its
    (current) working directory, prints a final status line, and exits
    with the given code.
    """
    script = _FAKE_AUSTAL_TEMPLATE.format(
        sleep_line=('sleep %s' % sleep) if sleep else '',
        result_line=('touch "%s"' % result_file) if result_file else '',
        final_line=final_line, exit_code=exit_code)
    with open(path, 'w') as f:
        f.write(script)
    mode = os.stat(path).st_mode
    os.chmod(path, mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def fake_austal(tmp_path, monkeypatch):
    """
    Install a fake ``austal`` executable on ``PATH`` and return a
    factory function to (re)configure its behavior -- see
    :func:`_write_fake_austal`. Starts out configured to succeed.
    """
    bindir = tmp_path / 'fakebin'
    bindir.mkdir()
    exe = bindir / 'austal'

    def _configure(**kwargs):
        _write_fake_austal(str(exe), **kwargs)
        return str(exe)

    _configure()
    monkeypatch.setenv(
        'PATH', str(bindir) + os.pathsep + os.environ.get('PATH', ''))
    return _configure


# ---------------------------------------------------------------------
# CLI wiring (subcommand registration, dispatch, verbosity)
# ---------------------------------------------------------------------

class TestCliParserSubcommand(unittest.TestCase):
    """Tests for subcommand availability in cli_parser."""

    def setUp(self):
        self.parser = command_line.cli_parser()

    def test_has_compare_weather_subcommand(self):
        """Test 'compare-weather' subcommand is available."""
        args = self.parser.parse_args(['compare-weather', 'a.akterm'])
        self.assertEqual(args.command, 'compare-weather')


class TestMain(unittest.TestCase):
    """Tests for command_line.main()'s dispatch to compare_weather."""

    @patch('austaltools.command_line.compare_weather.main')
    def test_main_calls_compare_weather(self, mock_main):
        """Test main dispatches to compare_weather.main for the
        'compare-weather' command."""
        args = {
            'command': 'compare-weather',
            'working_dir': '/tmp',
            'verb': None,
            'temp_dir': None,
        }
        command_line.main(args)
        mock_main.assert_called_once_with(args)

    def test_main_no_working_dir_raises(self):
        """Test main raises when working_dir is None."""
        args = {
            'command': 'compare-weather',
            'working_dir': None,
            'verb': None,
            'temp_dir': None,
        }
        with self.assertRaises(ValueError) as context:
            command_line.main(args)
        self.assertIn('PATH not given', str(context.exception))

    @patch('austaltools.command_line._storage')
    @patch('austaltools.command_line.compare_weather.main')
    def test_main_sets_temp_dir(self, mock_main, mock_storage):
        """Test main sets _storage.TEMP when temp_dir provided."""
        args = {
            'command': 'compare-weather',
            'working_dir': '/tmp',
            'verb': None,
            'temp_dir': '/custom/temp',
        }
        command_line.main(args)
        self.assertEqual(mock_storage.TEMP, '/custom/temp')


class TestPytestStyleCli:
    """Pytest-style tests with parametrization for CLI wiring."""

    @pytest.mark.parametrize("subcommand", [SUBCMD])
    def test_subcommand_help_available(self, subcommand):
        """Test help is available for the compare-weather subcommand."""
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
        args = parser.parse_args([verbosity_flag, SUBCMD, 'a.akterm'])
        assert args.verb == expected_level


# ---------------------------------------------------------------------
# small pure helper functions
# ---------------------------------------------------------------------

class TestPercentage(unittest.TestCase):
    """Tests for the _percentage() argparse type= helper."""

    def test_valid_float(self):
        self.assertEqual(cw._percentage('42.5'), 42.5)

    def test_boundary_zero(self):
        self.assertEqual(cw._percentage('0'), 0.0)

    def test_boundary_hundred(self):
        self.assertEqual(cw._percentage('100'), 100.0)

    def test_below_zero_raises(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            cw._percentage('-0.1')

    def test_above_hundred_raises(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            cw._percentage('100.1')

    def test_not_a_number_raises(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            cw._percentage('abc')


class TestResolveFiles(unittest.TestCase):
    """Tests for the _resolve_files() helper."""

    def test_single_file(self):
        ref, cmp_ = cw._resolve_files(['b.akterm'])
        self.assertIsNone(ref)
        self.assertEqual(cmp_, 'b.akterm')

    def test_two_files(self):
        ref, cmp_ = cw._resolve_files(['a.akterm', 'b.akterm'])
        self.assertEqual(ref, 'a.akterm')
        self.assertEqual(cmp_, 'b.akterm')

    def test_no_files_raises(self):
        with self.assertRaises(ValueError):
            cw._resolve_files([])

    def test_three_files_raises(self):
        with self.assertRaises(ValueError):
            cw._resolve_files(['a', 'b', 'c'])


class TestResolveReferenceFile(unittest.TestCase):
    """Tests for the _resolve_reference_file() helper."""

    def test_explicit_reference_returned_as_is(self):
        result = cw._resolve_reference_file('/some/dir', {}, 'explicit.dmna')
        self.assertEqual(result, 'explicit.dmna')

    def test_zeitreihe_dmna_found(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'zeitreihe.dmna'), 'w').close()
            result = cw._resolve_reference_file(d, {}, None)
        self.assertEqual(result, os.path.join(d, 'zeitreihe.dmna'))

    def test_timeseries_dmna_found(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'timeseries.dmna'), 'w').close()
            result = cw._resolve_reference_file(d, {}, None)
        self.assertEqual(result, os.path.join(d, 'timeseries.dmna'))

    def test_dmna_supersedes_az_with_warning(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'zeitreihe.dmna'), 'w').close()
            conf = {'az': ['weather.aks']}
            with self.assertLogs('austaltools.compare_weather',
                                 level='WARNING') as cm:
                result = cw._resolve_reference_file(d, conf, None)
            self.assertEqual(result, os.path.join(d, 'zeitreihe.dmna'))
            self.assertTrue(any('supersedes' in m for m in cm.output))

    def test_az_used_when_no_dmna_present(self):
        with tempfile.TemporaryDirectory() as d:
            conf = {'az': ['weather.aks']}
            result = cw._resolve_reference_file(d, conf, None)
        self.assertEqual(result, os.path.join(d, 'weather.aks'))

    def test_neither_dmna_nor_az_raises(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                cw._resolve_reference_file(d, {}, None)


class TestFindAustal(unittest.TestCase):
    """Tests for the _find_austal() helper."""

    @patch('austaltools.compare_weather.shutil.which')
    def test_found_on_path(self, mock_which):
        mock_which.return_value = '/usr/bin/austal'
        self.assertEqual(cw._find_austal(), '/usr/bin/austal')

    @patch('austaltools.compare_weather.os.path.exists')
    @patch('austaltools.compare_weather.shutil.which')
    def test_found_in_fallback_location(self, mock_which, mock_exists):
        mock_which.return_value = None
        mock_exists.side_effect = lambda path: path.endswith('/ast/austal')
        result = cw._find_austal()
        self.assertTrue(result.endswith('/ast/austal'))

    @patch('austaltools.compare_weather.os.path.exists', return_value=False)
    @patch('austaltools.compare_weather.shutil.which', return_value=None)
    def test_not_found_raises(self, mock_which, mock_exists):
        with self.assertRaises(OSError):
            cw._find_austal()


class TestExtractResults(unittest.TestCase):
    """Tests for the _extract_results() helper."""

    def test_extracts_matching_files_with_suffix(self):
        with tempfile.TemporaryDirectory() as src, \
             tempfile.TemporaryDirectory() as dst:
            open(os.path.join(src, 'xx-y00a.dmna'), 'w').close()
            open(os.path.join(src, 'other.dmna'), 'w').close()
            extracted = cw._extract_results(src, dst, 'ref')
            self.assertEqual(len(extracted), 1)
            self.assertTrue(os.path.exists(
                os.path.join(dst, 'xx-y00a_ref.dmna')))
            self.assertFalse(os.path.exists(
                os.path.join(dst, 'other_ref.dmna')))

    def test_extracts_german_variant_name(self):
        with tempfile.TemporaryDirectory() as src, \
             tempfile.TemporaryDirectory() as dst:
            open(os.path.join(src, 'xx-j00z.dmna'), 'w').close()
            cw._extract_results(src, dst, 'cmp')
            self.assertTrue(os.path.exists(
                os.path.join(dst, 'xx-j00z_cmp.dmna')))

    def test_creates_destination_dir(self):
        with tempfile.TemporaryDirectory() as src:
            dst = os.path.join(src, 'nested', 'dest')
            open(os.path.join(src, 'xx-y00a.dmna'), 'w').close()
            cw._extract_results(src, dst, 'ref')
            self.assertTrue(os.path.isdir(dst))

    def test_no_matches_logs_warning_and_returns_empty(self):
        with tempfile.TemporaryDirectory() as src, \
             tempfile.TemporaryDirectory() as dst:
            with self.assertLogs('austaltools.compare_weather',
                                 level='WARNING') as cm:
                extracted = cw._extract_results(src, dst, 'ref')
            self.assertEqual(extracted, [])
            self.assertTrue(any('no files matching' in m for m in cm.output))

    def test_searches_recursively(self):
        with tempfile.TemporaryDirectory() as src, \
             tempfile.TemporaryDirectory() as dst:
            sub = os.path.join(src, 'subdir')
            os.makedirs(sub)
            open(os.path.join(sub, 'xx-y00a.dmna'), 'w').close()
            extracted = cw._extract_results(src, dst, 'ref')
            self.assertEqual(len(extracted), 1)


class TestFindExtractedFile(unittest.TestCase):
    """Tests for the _find_extracted_file() helper."""

    def test_finds_single_match(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'xx-y00a_ref.dmna'), 'w').close()
            result = cw._find_extracted_file(d, 'ref')
            self.assertEqual(result, os.path.join(d, 'xx-y00a_ref.dmna'))

    def test_no_match_raises_filenotfound(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                cw._find_extracted_file(d, 'ref')

    def test_both_variants_present_raises(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'xx-y00a_ref.dmna'), 'w').close()
            open(os.path.join(d, 'xx-j00z_ref.dmna'), 'w').close()
            with self.assertRaises(ValueError):
                cw._find_extracted_file(d, 'ref')

    def test_different_suffix_not_matched(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'xx-y00a_cmp.dmna'), 'w').close()
            with self.assertRaises(FileNotFoundError):
                cw._find_extracted_file(d, 'ref')


class TestTouchesBorder(unittest.TestCase):
    """Tests for the _touches_border() helper."""

    def test_interior_only_false(self):
        mask = np.zeros((5, 5), dtype=bool)
        mask[2, 2] = True
        self.assertFalse(cw._touches_border(mask))

    def test_top_row_true(self):
        mask = np.zeros((5, 5), dtype=bool)
        mask[0, 3] = True
        self.assertTrue(cw._touches_border(mask))

    def test_bottom_row_true(self):
        mask = np.zeros((5, 5), dtype=bool)
        mask[-1, 0] = True
        self.assertTrue(cw._touches_border(mask))

    def test_left_column_true(self):
        mask = np.zeros((5, 5), dtype=bool)
        mask[3, 0] = True
        self.assertTrue(cw._touches_border(mask))

    def test_right_column_true(self):
        mask = np.zeros((5, 5), dtype=bool)
        mask[1, -1] = True
        self.assertTrue(cw._touches_border(mask))

    def test_all_false_mask(self):
        mask = np.zeros((5, 5), dtype=bool)
        self.assertFalse(cw._touches_border(mask))

    def test_empty_mask(self):
        mask = np.zeros((0, 0), dtype=bool)
        self.assertFalse(cw._touches_border(mask))

    def test_1x1_mask_true(self):
        mask = np.array([[True]])
        self.assertTrue(cw._touches_border(mask))

    def test_non_2d_mask_false(self):
        mask = np.zeros((3, 3, 3), dtype=bool)
        self.assertFalse(cw._touches_border(mask))


# ---------------------------------------------------------------------
# _read_grid_file(): real readmet round-trip plus mocked error cases
# ---------------------------------------------------------------------

def _write_grid_dmna(path, values, x, y, z=None, name='za'):
    """Write a minimal single-variable grid DMNA file with the real
    readmet.dmna, for _read_grid_file() to read back -- used to test
    against genuine DMNA I/O rather than only a mocked DataFile."""
    import readmet.dmna as dmna
    if z is None:
        z = np.array([0.])
    axs = {'x': np.asarray(x, dtype=float),
           'y': np.asarray(y, dtype=float),
           'z': np.asarray(z, dtype=float)}
    df = dmna.DataFile(values=values, axs=axs, name=name)
    df.write(path)


class TestReadGridFile(unittest.TestCase):
    """Tests for the _read_grid_file() helper."""

    def test_single_level_3d_squeezed_to_2d(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'grid.dmna')
            x = [0., 10., 20., 30.]
            y = [0., 10., 20.]
            values = np.arange(12, dtype=float).reshape(4, 3, 1)
            _write_grid_dmna(path, values, x, y)
            got_values, got_x, got_y = cw._read_grid_file(path)
        self.assertEqual(got_values.shape, (4, 3))
        np.testing.assert_allclose(got_values, values[:, :, 0])
        np.testing.assert_allclose(got_x, x)
        np.testing.assert_allclose(got_y, y)

    def test_multiple_levels_raises(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'grid.dmna')
            x = [0., 10.]
            y = [0., 10.]
            z = [0., 10.]
            values = np.zeros((2, 2, 2))
            _write_grid_dmna(path, values, x, y, z=z)
            with self.assertRaises(ValueError) as context:
                cw._read_grid_file(path)
        self.assertIn('vertical levels', str(context.exception))

    @patch('austaltools.compare_weather.readmet.dmna.DataFile')
    def test_wrong_variable_count_raises(self, mock_datafile_cls):
        instance = MagicMock()
        instance.variables = ['a', 'b']
        mock_datafile_cls.return_value = instance
        with self.assertRaises(ValueError) as context:
            cw._read_grid_file('whatever.dmna')
        self.assertIn('exactly one variable', str(context.exception))

    @patch('austaltools.compare_weather.readmet.dmna.DataFile')
    def test_missing_xy_axes_raises(self, mock_datafile_cls):
        instance = MagicMock()
        instance.variables = ['za']
        instance.data = {'za': np.zeros((2, 2))}
        instance.axes.return_value = {'z': [0.]}
        mock_datafile_cls.return_value = instance
        with self.assertRaises(ValueError) as context:
            cw._read_grid_file('whatever.dmna')
        self.assertIn('x/y grid axes', str(context.exception))

    @patch('austaltools.compare_weather.readmet.dmna.DataFile')
    def test_shape_mismatch_raises(self, mock_datafile_cls):
        instance = MagicMock()
        instance.variables = ['za']
        instance.data = {'za': np.zeros((3, 3))}
        instance.axes.return_value = {'x': [0., 1.], 'y': [0., 1.]}
        mock_datafile_cls.return_value = instance
        with self.assertRaises(ValueError) as context:
            cw._read_grid_file('whatever.dmna')
        self.assertIn('does not match', str(context.exception))

    @patch('austaltools.compare_weather.readmet.dmna.DataFile')
    def test_1d_field_raises(self, mock_datafile_cls):
        instance = MagicMock()
        instance.variables = ['za']
        instance.data = {'za': np.zeros(4)}
        instance.axes.return_value = {'x': [0., 1., 2., 3.], 'y': [0.]}
        mock_datafile_cls.return_value = instance
        with self.assertRaises(ValueError) as context:
            cw._read_grid_file('whatever.dmna')
        self.assertIn('expected a 2D', str(context.exception))


# ---------------------------------------------------------------------
# compute_overlap(): the core threshold / overlap / area-fraction math
# ---------------------------------------------------------------------

class TestComputeOverlap(unittest.TestCase):
    """
    Tests for compute_overlap(), with _read_grid_file() monkeypatched
    to inject known reference/comparison arrays -- this checks the
    threshold resolution and overlap/area-fraction math exactly,
    without needing real AUSTAL output files.
    """

    def setUp(self):
        self.x = np.array([0., 1., 2., 3.])
        self.y = np.array([0., 1., 2., 3.])
        # reference: a single 2x2 "hot" block in the middle
        self.ref = np.array([
            [1., 2., 2., 1.],
            [2., 5., 5., 2.],
            [2., 5., 5., 2.],
            [1., 2., 2., 1.],
        ])
        # comparison: the hot block shifted one cell to the right
        self.cmp = np.array([
            [1., 1., 2., 2.],
            [1., 2., 5., 5.],
            [2., 5., 5., 2.],
            [2., 5., 2., 1.],
        ])

    def _patch_read(self):
        return patch('austaltools.compare_weather._read_grid_file',
                    side_effect=[(self.ref, self.x, self.y),
                                (self.cmp, self.x, self.y)])

    def test_mutually_exclusive_thx_thp_raises(self):
        with self.assertRaises(ValueError):
            cw.compute_overlap('r', 'c', thx=1.0, thp=50.0)

    def test_mutually_exclusive_thx_thr_raises(self):
        with self.assertRaises(ValueError):
            cw.compute_overlap('r', 'c', thx=1.0, thr=50.0)

    def test_mutually_exclusive_thp_thr_raises(self):
        with self.assertRaises(ValueError):
            cw.compute_overlap('r', 'c', thp=50.0, thr=50.0)

    def test_explicit_thx_used_directly(self):
        with self._patch_read():
            result = cw.compute_overlap('r', 'c', thx=3.0)
        self.assertEqual(result['thx'], 3.0)
        # ref > 3 at (1,1),(1,2),(2,1),(2,2); cmp > 3 at (1,2),(1,3),
        # (2,1),(2,2),(3,1) -- 3 cells in common, 6 cells in the union
        self.assertAlmostEqual(result['overlap'], 3 / 6)

    def test_thp_resolves_percentile_of_reference(self):
        with self._patch_read():
            result = cw.compute_overlap('r', 'c', thp=50.0)
        expected_thx = float(np.nanpercentile(self.ref, 50.0))
        self.assertAlmostEqual(result['thx'], expected_thx)

    def test_thr_resolves_range_position(self):
        with self._patch_read():
            result = cw.compute_overlap('r', 'c', thr=50.0)
        lo = float(np.nanpercentile(self.ref, cw.DEFAULT_RANGE_LOW_PERCENTILE))
        hi = float(np.nanpercentile(self.ref, cw.DEFAULT_RANGE_HIGH_PERCENTILE))
        expected_thx = lo + 50.0 / 100.0 * (hi - lo)
        self.assertAlmostEqual(result['thx'], expected_thx)

    def test_default_equals_explicit_thr_default_range(self):
        """If none of thx/thp/thr is given, the result must be
        identical to passing thr=DEFAULT_RANGE explicitly."""
        with self._patch_read():
            result_default = cw.compute_overlap('r', 'c')
        with self._patch_read():
            result_explicit = cw.compute_overlap('r', 'c', thr=cw.DEFAULT_RANGE)
        self.assertAlmostEqual(result_default['thx'], result_explicit['thx'])

    def test_shape_mismatch_raises(self):
        with patch('austaltools.compare_weather._read_grid_file',
                  side_effect=[(self.ref, self.x, self.y),
                              (self.cmp[:, :3], self.x, self.y)]):
            with self.assertRaises(ValueError) as context:
                cw.compute_overlap('r', 'c', thx=1.0)
        self.assertIn('different shapes', str(context.exception))

    def test_coordinate_mismatch_raises(self):
        other_x = self.x + 100
        with patch('austaltools.compare_weather._read_grid_file',
                  side_effect=[(self.ref, self.x, self.y),
                              (self.cmp, other_x, self.y)]):
            with self.assertRaises(ValueError) as context:
                cw.compute_overlap('r', 'c', thx=1.0)
        self.assertIn('same coordinates', str(context.exception))

    def test_threshold_too_high_gives_nan_overlap(self):
        with self._patch_read():
            result = cw.compute_overlap('r', 'c', thx=100.0)
        self.assertTrue(np.isnan(result['overlap']))

    def test_area_fractions_computed_correctly(self):
        with self._patch_read():
            result = cw.compute_overlap('r', 'c', thx=3.0)
        self.assertAlmostEqual(result['reference_area_fraction'], 4 / 16)
        self.assertAlmostEqual(result['comparison_area_fraction'], 5 / 16)

    def test_border_touch_detected(self):
        ref = np.array([
            [9., 1., 1.],
            [1., 1., 1.],
            [1., 1., 1.],
        ])
        cmp_ = np.zeros((3, 3))
        with patch('austaltools.compare_weather._read_grid_file',
                  side_effect=[(ref, self.x[:3], self.y[:3]),
                              (cmp_, self.x[:3], self.y[:3])]):
            result = cw.compute_overlap('r', 'c', thx=5.0)
        self.assertTrue(result['reference_touches_border'])
        self.assertFalse(result['comparison_touches_border'])

    def test_returned_dict_keys(self):
        with self._patch_read():
            result = cw.compute_overlap('r', 'c', thx=3.0)
        expected_keys = {
            'overlap', 'thx', 'x', 'y', 'reference', 'comparison',
            'reference_touches_border', 'comparison_touches_border',
            'reference_area_fraction', 'comparison_area_fraction',
        }
        self.assertEqual(set(result.keys()), expected_keys)


class TestComputeOverlapEdgeCases(unittest.TestCase):
    """Edge cases for compute_overlap(): identical and disjoint fields."""

    def setUp(self):
        self.x = np.array([0., 1., 2.])
        self.y = np.array([0., 1., 2.])

    def test_identical_fields_full_overlap(self):
        field = np.array([[1., 5., 1.], [5., 9., 5.], [1., 5., 1.]])
        with patch('austaltools.compare_weather._read_grid_file',
                  side_effect=[(field, self.x, self.y),
                              (field.copy(), self.x, self.y)]):
            result = cw.compute_overlap('r', 'c', thx=3.0)
        self.assertEqual(result['overlap'], 1.0)

    def test_disjoint_fields_zero_overlap(self):
        ref = np.array([[9., 1., 1.], [1., 1., 1.], [1., 1., 1.]])
        cmp_ = np.array([[1., 1., 1.], [1., 1., 1.], [1., 1., 9.]])
        with patch('austaltools.compare_weather._read_grid_file',
                  side_effect=[(ref, self.x, self.y), (cmp_, self.x, self.y)]):
            result = cw.compute_overlap('r', 'c', thx=5.0)
        self.assertEqual(result['overlap'], 0.0)


# ---------------------------------------------------------------------
# run_austal(): against a fake `austal` executable
# ---------------------------------------------------------------------

class TestRunAustal:
    """
    Pytest-style tests for run_austal(), using the fake_austal fixture
    so no real AUSTAL installation is needed.
    """

    def test_successful_run_extracts_result_file(self, tmp_path, fake_austal):
        weather = tmp_path / 'zeitreihe.dmna'
        weather.write_text('dummy')
        extract_to = tmp_path / 'extracted'
        extracted = cw.run_austal(str(weather), nodes=5, delta=20,
                                  extract_to=str(extract_to),
                                  extract_suffix='ref')
        assert len(extracted) == 1
        assert os.path.basename(extracted[0]) == 'xx-y00a_ref.dmna'
        assert os.path.exists(extracted[0])

    def test_akterm_input_gets_staged(self, tmp_path, fake_austal):
        # use a real, full-year AKTERM timeseries to make sure a
        # genuinely large, real-world file is staged correctly, not
        # just a tiny dummy one
        extract_to = tmp_path / 'extracted'
        extracted = cw.run_austal(EXAMPLE_OBS, nodes=5, delta=20,
                                  extract_to=str(extract_to),
                                  extract_suffix='obs')
        assert len(extracted) == 1

    def test_akterm_content_staged_byte_identical(self, tmp_path, fake_austal,
                                                  monkeypatch):
        # spy on shutil.rmtree (as seen by compare_weather) to snapshot
        # the per-run temp directory just before it gets discarded
        captured = {}
        real_rmtree = shutil.rmtree

        def spy_rmtree(path, *a, **kw):
            az_name = os.path.basename(EXAMPLE_OBS)
            with open(os.path.join(path, az_name), 'rb') as f:
                captured['az_content'] = f.read()
            with open(os.path.join(path, 'austal.txt')) as f:
                captured['austal_txt'] = f.read()
            return real_rmtree(path, *a, **kw)

        monkeypatch.setattr(cw.shutil, 'rmtree', spy_rmtree)
        cw.run_austal(EXAMPLE_OBS, nodes=5, delta=20)

        with open(EXAMPLE_OBS, 'rb') as f:
            original = f.read()
        assert captured['az_content'] == original
        assert 'az %s' % os.path.basename(EXAMPLE_OBS) in captured['austal_txt']

    def test_missing_weather_file_raises(self, tmp_path, fake_austal):
        with pytest.raises(FileNotFoundError):
            cw.run_austal(str(tmp_path / 'does_not_exist.dmna'))

    def test_austal_not_found_raises_oserror(self, tmp_path):
        weather = tmp_path / 'zeitreihe.dmna'
        weather.write_text('dummy')
        with patch('austaltools.compare_weather._find_austal',
                  side_effect=OSError('austal executable not found')):
            with pytest.raises(OSError):
                cw.run_austal(str(weather))

    def test_nonzero_exit_without_finished_line_raises(self, tmp_path,
                                                       fake_austal):
        fake_austal(exit_code=1, final_line='some error')
        weather = tmp_path / 'zeitreihe.dmna'
        weather.write_text('dummy')
        with pytest.raises(ValueError):
            cw.run_austal(str(weather), nodes=5, delta=20)

    def test_nonzero_exit_with_finished_line_still_succeeds(self, tmp_path,
                                                            fake_austal):
        # mirrors real AUSTAL's own quirk of occasionally exiting
        # non-zero even after successfully finishing
        fake_austal(exit_code=1, final_line='AUSTAL beendet.')
        weather = tmp_path / 'zeitreihe.dmna'
        weather.write_text('dummy')
        extracted = cw.run_austal(str(weather), nodes=5, delta=20,
                                  extract_to=str(tmp_path / 'extracted'),
                                  extract_suffix='ref')
        assert len(extracted) == 1

    def test_extract_to_without_suffix_raises(self, tmp_path, fake_austal):
        weather = tmp_path / 'zeitreihe.dmna'
        weather.write_text('dummy')
        with pytest.raises(ValueError):
            cw.run_austal(str(weather), extract_to=str(tmp_path / 'extracted'))

    def test_no_extract_to_returns_empty_list(self, tmp_path, fake_austal):
        weather = tmp_path / 'zeitreihe.dmna'
        weather.write_text('dummy')
        extracted = cw.run_austal(str(weather), nodes=5, delta=20)
        assert extracted == []

    def test_temporary_directory_is_removed_after_success(self, tmp_path,
                                                          fake_austal):
        weather = tmp_path / 'zeitreihe.dmna'
        weather.write_text('dummy')
        cw.run_austal(str(weather), nodes=5, delta=20, tmproot=str(tmp_path))
        leftover = [n for n in os.listdir(str(tmp_path))
                   if n.startswith('cmpwx_')]
        assert leftover == []

    def test_progress_desc_and_position_forwarded(self, tmp_path, fake_austal):
        weather = tmp_path / 'zeitreihe.dmna'
        weather.write_text('dummy')
        with patch('austaltools.compare_weather._tools.progress') as mock_pg:
            mock_pg.return_value = MagicMock()
            cw.run_austal(str(weather), nodes=5, delta=20,
                          progress_desc='reference ', progress_position=0)
        _, kwargs = mock_pg.call_args
        assert kwargs['desc'] == 'reference '
        assert kwargs['position'] == 0


# ---------------------------------------------------------------------
# main(): orchestration (parallel/sequential, keep-files, plotting)
# ---------------------------------------------------------------------

class TestMainOrchestration(unittest.TestCase):
    """
    Tests for main()'s own orchestration logic, with run_austal() and
    compute_overlap() mocked out -- these test the parallel/sequential
    branching, --keep-files handling, and plot invocation, not the
    AUSTAL run or the overlap math itself (covered elsewhere).
    """

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.working_dir = self._tmpdir.name
        self.ref_file = os.path.join(self.working_dir, 'ref.dmna')
        self.cmp_file = os.path.join(self.working_dir, 'cmp.akterm')
        open(self.ref_file, 'w').close()
        open(self.cmp_file, 'w').close()

        self.canned_result = {
            'overlap': 0.5, 'thx': 1.0,
            'x': np.array([0., 1.]), 'y': np.array([0., 1.]),
            'reference': np.zeros((2, 2)), 'comparison': np.zeros((2, 2)),
            'reference_touches_border': False,
            'comparison_touches_border': False,
            'reference_area_fraction': 0.25,
            'comparison_area_fraction': 0.25,
        }

    def tearDown(self):
        self._tmpdir.cleanup()

    def _base_args(self, **overrides):
        args = dict(
            working_dir=self.working_dir,
            files=[self.ref_file, self.cmp_file],
            nodes=5, delta=20, throw=cw.DEFAULT_THROW, height=cw.DEFAULT_HEIGHT,
            thx=None, thp=None, thr=None,
            keep_files=None, plot=None,
        )
        args.update(overrides)
        return args

    @staticmethod
    def _fake_run_austal(weather_file, extract_to=None, extract_suffix=None,
                         **kwargs):
        path = os.path.join(extract_to, 'xx-y00a_%s.dmna' % extract_suffix)
        open(path, 'w').close()
        return [path]

    @patch('austaltools.compare_weather.compute_overlap')
    @patch('austaltools.compare_weather.run_austal')
    def test_parallel_by_default_runs_both(self, mock_run_austal, mock_compute):
        mock_run_austal.side_effect = self._fake_run_austal
        mock_compute.return_value = self.canned_result
        cw.main(self._base_args())
        self.assertEqual(mock_run_austal.call_count, 2)
        suffixes = {c.kwargs['extract_suffix']
                   for c in mock_run_austal.call_args_list}
        self.assertEqual(suffixes, {'ref', 'cmp'})

    @patch('austaltools.compare_weather.compute_overlap')
    @patch('austaltools.compare_weather.run_austal')
    def test_no_parallel_runs_both_sequentially(self, mock_run_austal,
                                               mock_compute):
        mock_run_austal.side_effect = self._fake_run_austal
        mock_compute.return_value = self.canned_result
        cw.main(self._base_args(parallel=False))
        self.assertEqual(mock_run_austal.call_count, 2)

    @patch('austaltools.compare_weather.compute_overlap')
    @patch('austaltools.compare_weather.run_austal')
    def test_returns_overlap_value(self, mock_run_austal, mock_compute):
        mock_run_austal.side_effect = self._fake_run_austal
        mock_compute.return_value = self.canned_result
        result = cw.main(self._base_args())
        self.assertEqual(result, 0.5)

    @patch('austaltools.compare_weather.compute_overlap')
    @patch('austaltools.compare_weather.run_austal')
    def test_threshold_kwargs_forwarded(self, mock_run_austal, mock_compute):
        mock_run_austal.side_effect = self._fake_run_austal
        mock_compute.return_value = self.canned_result
        cw.main(self._base_args(thr=50.0))
        _, kwargs = mock_compute.call_args
        self.assertEqual(kwargs['thr'], 50.0)
        self.assertIsNone(kwargs['thx'])
        self.assertIsNone(kwargs['thp'])

    @patch('austaltools.compare_weather.compute_overlap')
    @patch('austaltools.compare_weather.run_austal')
    def test_keep_files_copies_to_working_dir(self, mock_run_austal,
                                             mock_compute):
        mock_run_austal.side_effect = self._fake_run_austal
        mock_compute.return_value = self.canned_result
        cw.main(self._base_args(keep_files='__default__'))
        kept = [f for f in os.listdir(self.working_dir) if f.startswith('xx-')]
        self.assertEqual(len(kept), 2)

    @patch('austaltools.compare_weather.compute_overlap')
    @patch('austaltools.compare_weather.run_austal')
    def test_keep_files_named_dir(self, mock_run_austal, mock_compute):
        mock_run_austal.side_effect = self._fake_run_austal
        mock_compute.return_value = self.canned_result
        cw.main(self._base_args(keep_files='mykeep'))
        kept_dir = os.path.join(self.working_dir, 'mykeep')
        self.assertTrue(os.path.isdir(kept_dir))
        kept = [f for f in os.listdir(kept_dir) if f.startswith('xx-')]
        self.assertEqual(len(kept), 2)

    @patch('austaltools.compare_weather._plotting.overlap_plot')
    @patch('austaltools.compare_weather._plotting.consolidate_plotname')
    @patch('austaltools.compare_weather.compute_overlap')
    @patch('austaltools.compare_weather.run_austal')
    def test_plot_invoked_when_requested(self, mock_run_austal, mock_compute,
                                        mock_consolidate, mock_overlap_plot):
        mock_run_austal.side_effect = self._fake_run_austal
        mock_compute.return_value = self.canned_result
        mock_consolidate.return_value = 'out.png'
        cw.main(self._base_args(plot='__default__'))
        mock_overlap_plot.assert_called_once()
        _, kwargs = mock_overlap_plot.call_args
        self.assertEqual(kwargs['thx'], 1.0)
        self.assertIn('reference', kwargs)
        self.assertIn('comparison', kwargs)

    @patch('austaltools.compare_weather._plotting.overlap_plot')
    @patch('austaltools.compare_weather.compute_overlap')
    @patch('austaltools.compare_weather.run_austal')
    def test_no_plot_by_default(self, mock_run_austal, mock_compute,
                               mock_overlap_plot):
        mock_run_austal.side_effect = self._fake_run_austal
        mock_compute.return_value = self.canned_result
        cw.main(self._base_args())
        mock_overlap_plot.assert_not_called()

    @patch('austaltools.compare_weather.compute_overlap')
    @patch('austaltools.compare_weather.run_austal')
    def test_reference_failure_waits_for_comparison_before_propagating(
            self, mock_run_austal, mock_compute):
        """
        If the reference run fails, its exception must still be the
        one that propagates out of main() -- but the comparison run
        (submitted concurrently) must still be waited for rather than
        left dangling in the background. See compare_weather.main()'s
        own comment on this for the reasoning.
        """
        finished = []

        def side_effect(weather_file, extract_to=None, extract_suffix=None,
                        **kwargs):
            if extract_suffix == 'ref':
                raise ValueError('boom')
            time.sleep(0.05)
            finished.append(extract_suffix)
            return self._fake_run_austal(weather_file, extract_to=extract_to,
                                        extract_suffix=extract_suffix, **kwargs)

        mock_run_austal.side_effect = side_effect
        with self.assertRaises(ValueError):
            cw.main(self._base_args())
        self.assertIn('cmp', finished)


# ---------------------------------------------------------------------
# add_options(): argparse wiring
# ---------------------------------------------------------------------

class TestAddOptions(unittest.TestCase):
    """Tests for the add_options() function."""

    @staticmethod
    def _parser():
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')
        cw.add_options(subparsers)
        return parser

    def test_add_options_returns_parser(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        result = cw.add_options(subparsers)
        self.assertIsNotNone(result)

    def test_add_options_subcommand(self):
        parser = self._parser()
        args = parser.parse_args(['compare-weather', 'a.akterm'])
        self.assertEqual(args.command, 'compare-weather')

    def test_default_values(self):
        parser = self._parser()
        args = parser.parse_args(['compare-weather', 'a.akterm'])
        self.assertIsNone(args.thx)
        self.assertIsNone(args.thp)
        self.assertIsNone(args.thr)
        self.assertIsNone(args.keep_files)
        self.assertTrue(args.parallel)
        self.assertEqual(args.nodes, cw.DEFAULT_NODES)
        self.assertEqual(args.delta, cw.DEFAULT_DELTA)
        self.assertEqual(args.throw, cw.DEFAULT_THROW)
        self.assertEqual(args.height, cw.DEFAULT_HEIGHT)

    def test_no_parallel_flag(self):
        parser = self._parser()
        args = parser.parse_args(['compare-weather', '--no-parallel', 'a.akterm'])
        self.assertFalse(args.parallel)

    def test_keep_files_default_dir(self):
        parser = self._parser()
        # --keep-files' value is optional (nargs='?'): put the
        # positional FILE argument first so argparse doesn't try to
        # consume it as --keep-files' value
        args = parser.parse_args(['compare-weather', 'a.akterm', '--keep-files'])
        self.assertEqual(args.keep_files, '__default__')

    def test_keep_files_explicit_dir(self):
        parser = self._parser()
        args = parser.parse_args(
            ['compare-weather', '--keep-files', 'mydir', 'a.akterm'])
        self.assertEqual(args.keep_files, 'mydir')

    def test_thx_thp_mutually_exclusive(self):
        parser = self._parser()
        _assert_parse_error(self, parser, [
            'compare-weather', '--thx', '1.0', '--thp', '50', 'a.akterm'])

    def test_thp_thr_mutually_exclusive(self):
        parser = self._parser()
        _assert_parse_error(self, parser, [
            'compare-weather', '--thp', '50', '--thr', '30', 'a.akterm'])

    def test_thx_thr_mutually_exclusive(self):
        parser = self._parser()
        _assert_parse_error(self, parser, [
            'compare-weather', '--thx', '1.0', '--thr', '30', 'a.akterm'])

    def test_thr_out_of_range_rejected(self):
        parser = self._parser()
        _assert_parse_error(self, parser,
                            ['compare-weather', '--thr', '150', 'a.akterm'])

    def test_one_file_accepted(self):
        parser = self._parser()
        args = parser.parse_args(['compare-weather', 'a.akterm'])
        self.assertEqual(args.files, ['a.akterm'])

    def test_two_files_accepted(self):
        parser = self._parser()
        args = parser.parse_args(['compare-weather', 'a.akterm', 'b.akterm'])
        self.assertEqual(args.files, ['a.akterm', 'b.akterm'])

    def test_no_files_rejected(self):
        parser = self._parser()
        _assert_parse_error(self, parser, ['compare-weather'])


class TestCommandLineCompareWeather(unittest.TestCase):
    """
    Tests for the compare-weather command-line interface, invoked as a
    subprocess exactly like test_eap.py's TestCommandLineEap does --
    these assume a fully installed austaltools package.
    """

    def test_help(self):
        command = CMD + [SUBCMD, '-h']
        out, err, exitcode = capture(command)
        self.assertEqual(exitcode, 0)
        self.assertTrue(out.decode().startswith('usage'))

    def test_no_files_fails(self):
        command = CMD + [SUBCMD]
        out, err, exitcode = capture(command)
        self.assertNotEqual(exitcode, 0)

    def test_nonexistent_file_fails(self):
        command = CMD + [SUBCMD, '/no/such/file.akterm']
        out, err, exitcode = capture(command)
        self.assertNotEqual(exitcode, 0)


# ---------------------------------------------------------------------
# pytest-style parametrized tests
# ---------------------------------------------------------------------

class TestPytestStyleParametrized:
    """Pytest-style tests with parametrization."""

    @pytest.mark.parametrize("value,expected", [
        ('0', 0.0), ('100', 100.0), ('50.5', 50.5),
    ])
    def test_percentage_valid(self, value, expected):
        assert cw._percentage(value) == expected

    @pytest.mark.parametrize("value", ['-1', '100.01', 'abc', ''])
    def test_percentage_invalid(self, value):
        with pytest.raises(argparse.ArgumentTypeError):
            cw._percentage(value)

    @pytest.mark.parametrize("files,expected_ref,expected_cmp", [
        (['b.akterm'], None, 'b.akterm'),
        (['a.akterm', 'b.akterm'], 'a.akterm', 'b.akterm'),
    ])
    def test_resolve_files_parametrized(self, files, expected_ref,
                                       expected_cmp):
        ref, cmp_ = cw._resolve_files(files)
        assert ref == expected_ref
        assert cmp_ == expected_cmp


# ---------------------------------------------------------------------
# module constants
# ---------------------------------------------------------------------

class TestModuleConstants(unittest.TestCase):
    """Tests for module-level constants."""

    def test_default_nodes(self):
        self.assertEqual(cw.DEFAULT_NODES, 141)

    def test_default_delta(self):
        self.assertEqual(cw.DEFAULT_DELTA, 25)

    def test_default_throw(self):
        self.assertEqual(cw.DEFAULT_THROW, 0.278)

    def test_default_height(self):
        self.assertEqual(cw.DEFAULT_HEIGHT, 20)

    def test_default_range(self):
        self.assertEqual(cw.DEFAULT_RANGE, 33)

    def test_default_range_low_percentile(self):
        self.assertEqual(cw.DEFAULT_RANGE_LOW_PERCENTILE, 0.1)

    def test_default_range_high_percentile(self):
        self.assertEqual(cw.DEFAULT_RANGE_HIGH_PERCENTILE, 99.9)

    def test_extract_filenames(self):
        self.assertEqual(cw.EXTRACT_FILENAMES, ('xx-j00z.dmna', 'xx-y00a.dmna'))


# ---------------------------------------------------------------------
# true end-to-end test against a real AUSTAL installation and a full
# year of real weather data -- skipped unless austal is on PATH
# ---------------------------------------------------------------------

@pytest.mark.skipif(shutil.which('austal') is None,
                    reason='requires a real austal installation')
class TestIntegrationRealAustal:
    """
    True end-to-end test using the real AUSTAL model and a full year
    of real hourly weather data (tests/example_obs_2003.akterm,
    tests/example_mod_2003.akterm) -- skipped unless a real `austal`
    executable is on PATH. Everything else in this file is
    deliberately independent of a real AUSTAL installation; run this
    class specifically (e.g. on a machine with AUSTAL installed) for
    the strongest end-to-end confidence.
    """

    def test_full_pipeline_on_real_data(self, tmp_path):
        args = dict(
            working_dir=str(tmp_path),
            files=[EXAMPLE_OBS, EXAMPLE_MOD],
            nodes=41, delta=100, throw=cw.DEFAULT_THROW,
            height=cw.DEFAULT_HEIGHT,
            thx=None, thp=None, thr=None,
            keep_files=None, plot=None,
        )
        overlap = cw.main(args)
        assert 0.0 <= overlap <= 1.0


if __name__ == '__main__':
    unittest.main()
