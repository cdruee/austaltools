#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive test suite for austaltools.fill_timeseries module.

This module tests the fill-timeseries functionality for creating
time-dependent source strength timeseries for AUSTAL.
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
from austaltools import fill_timeseries


# Helper function for subprocess tests
CMD = ['python', '-m', 'austaltools.command_line']
COMMAND = 'fill-timeseries'


def capture(command):
    """Run command and capture output."""
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out, err = proc.communicate()
    print('command stdout: \n' + out.decode())
    print('command stderr: \n' + err.decode())
    print('cmd exit code : \n%s' % proc.returncode)
    return out, err, proc.returncode


def make_zeitreihe():
    """Create a test zeitreihe.dmna file."""
    with open(os.path.join('tests', 'test.dmna'), 'r') as fi:
        with open(os.path.join('tests', 'zeitreihe.dmna'), 'w') as fo:
            fo.write(fi.read())


def make_cycle(name):
    """Create a test cycle YAML file."""
    lines = """
cycle01.so2:
    source: 01.so2
    start:
        at:
            time: 2-50/2
            unit: week
        offset:
            time: 12
            unit: hour
    list: [1.000, 1.000, 1.000, 2.000, 2.000, 2.000, 2.000, 2.000, 1.000, 1.000, 1.000]

"""
    with open(os.path.join('tests', name), 'w') as fo:
        fo.write(lines)


# =============================================================================
# Tests for CLI parser subcommand
# =============================================================================

class TestCliParserSubcommand(unittest.TestCase):
    """Tests for subcommand availability in cli_parser."""

    def setUp(self):
        """Set up parser for tests."""
        self.parser = command_line.cli_parser()

    def test_has_fill_timeseries_subcommand(self):
        """Test 'fill-timeseries' subcommand is available."""
        args = self.parser.parse_args(['fill-timeseries', '-l'])
        self.assertEqual(args.command, 'fill-timeseries')

    def test_has_ft_alias_subcommand(self):
        """Test 'ft' alias for fill-timeseries is available."""
        args = self.parser.parse_args(['ft', '-l'])
        self.assertEqual(args.command, 'ft')


# =============================================================================
# Tests for main function dispatch
# =============================================================================

class TestMain(unittest.TestCase):
    """Tests for the main function."""

    @patch('austaltools.command_line.fill_timeseries.main')
    def test_main_calls_fill_timeseries(self, mock_ft_main):
        """Test main dispatches to fill_timeseries.main for 'fill-timeseries' command."""
        args = {
            'command': 'fill-timeseries',
            'working_dir': '/tmp',
            'verb': None,
            'temp_dir': None
        }
        command_line.main(args)
        mock_ft_main.assert_called_once_with(args)

    @patch('austaltools.command_line.fill_timeseries.main')
    def test_main_calls_ft_alias(self, mock_ft_main):
        """Test main dispatches to fill_timeseries.main for 'ft' alias command."""
        args = {
            'command': 'ft',
            'working_dir': '/tmp',
            'verb': None,
            'temp_dir': None
        }
        command_line.main(args)
        mock_ft_main.assert_called_once_with(args)

    def test_main_no_working_dir_raises(self):
        """Test main raises when working_dir is None."""
        args = {
            'command': 'fill-timeseries',
            'working_dir': None,
            'verb': None,
            'temp_dir': None
        }
        with self.assertRaises(ValueError) as context:
            command_line.main(args)
        self.assertIn('PATH not given', str(context.exception))

    @patch('austaltools.command_line._storage')
    @patch('austaltools.command_line.fill_timeseries.main')
    def test_main_sets_temp_dir(self, mock_ft_main, mock_storage):
        """Test main sets _storage.TEMP when temp_dir provided."""
        args = {
            'command': 'fill-timeseries',
            'working_dir': '/tmp',
            'verb': None,
            'temp_dir': '/custom/temp'
        }
        command_line.main(args)
        self.assertEqual(mock_storage.TEMP, '/custom/temp')


# =============================================================================
# Tests for parse_time_unit function
# =============================================================================

class TestParseTimeUnit(unittest.TestCase):
    """Tests for the parse_time_unit function."""

    def test_parse_months(self):
        """Test parsing month variants."""
        self.assertEqual(fill_timeseries.parse_time_unit('month'), 'months')
        self.assertEqual(fill_timeseries.parse_time_unit('months'), 'months')
        self.assertEqual(fill_timeseries.parse_time_unit('mon'), 'months')
        self.assertEqual(fill_timeseries.parse_time_unit('MONTH'), 'months')

    def test_parse_weeks(self):
        """Test parsing week variants."""
        self.assertEqual(fill_timeseries.parse_time_unit('week'), 'weeks')
        self.assertEqual(fill_timeseries.parse_time_unit('weeks'), 'weeks')
        self.assertEqual(fill_timeseries.parse_time_unit('w'), 'weeks')
        self.assertEqual(fill_timeseries.parse_time_unit('WEEK'), 'weeks')

    def test_parse_days(self):
        """Test parsing day variants."""
        self.assertEqual(fill_timeseries.parse_time_unit('day'), 'days')
        self.assertEqual(fill_timeseries.parse_time_unit('days'), 'days')
        self.assertEqual(fill_timeseries.parse_time_unit('d'), 'days')
        self.assertEqual(fill_timeseries.parse_time_unit('DAY'), 'days')

    def test_parse_hours(self):
        """Test parsing hour variants."""
        self.assertEqual(fill_timeseries.parse_time_unit('hour'), 'hours')
        self.assertEqual(fill_timeseries.parse_time_unit('hours'), 'hours')
        self.assertEqual(fill_timeseries.parse_time_unit('hr'), 'hours')
        self.assertEqual(fill_timeseries.parse_time_unit('hrs'), 'hours')
        self.assertEqual(fill_timeseries.parse_time_unit('h'), 'hours')
        self.assertEqual(fill_timeseries.parse_time_unit('HOUR'), 'hours')

    def test_parse_unknown_raises(self):
        """Test that unknown unit raises ValueError."""
        with self.assertRaises(ValueError) as context:
            fill_timeseries.parse_time_unit('seconds')
        self.assertIn('unknown', str(context.exception))

        with self.assertRaises(ValueError):
            fill_timeseries.parse_time_unit('year')

        with self.assertRaises(ValueError):
            fill_timeseries.parse_time_unit('')


# =============================================================================
# Tests for parse_time function
# =============================================================================

class TestParseTime(unittest.TestCase):
    """Tests for the parse_time function."""

    def test_parse_time_basic(self):
        """Test basic time parsing."""
        info = {'time': '1', 'unit': 'hour'}
        count, unit = fill_timeseries.parse_time(info)
        self.assertEqual(unit, 'hours')
        self.assertIsInstance(count, list)

    def test_parse_time_multi_true(self):
        """Test parsing with multi=True allows multiple values."""
        info = {'time': '1-3', 'unit': 'day'}
        count, unit = fill_timeseries.parse_time(info, multi=True)
        self.assertEqual(unit, 'days')
        self.assertEqual(len(count), 3)

    def test_parse_time_multi_false_single(self):
        """Test parsing with multi=False and single value."""
        info = {'time': '5', 'unit': 'hour'}
        count, unit = fill_timeseries.parse_time(info, multi=False)
        self.assertEqual(unit, 'hours')
        self.assertEqual(count, 5)

    def test_parse_time_multi_false_multiple_raises(self):
        """Test parsing with multi=False raises for multiple values."""
        info = {'time': '1-3', 'unit': 'day'}
        with self.assertRaises(ValueError) as context:
            fill_timeseries.parse_time(info, multi=False)
        self.assertIn('multiple', str(context.exception))

    def test_parse_time_no_time_raises(self):
        """Test missing 'time' key raises ValueError."""
        info = {'unit': 'hour'}
        with self.assertRaises(ValueError) as context:
            fill_timeseries.parse_time(info, name='test')
        self.assertIn('no time info', str(context.exception))

    def test_parse_time_no_unit_raises(self):
        """Test missing 'unit' key raises ValueError."""
        info = {'time': '1'}
        with self.assertRaises(ValueError) as context:
            fill_timeseries.parse_time(info, name='test')
        self.assertIn('no unit info', str(context.exception))


# =============================================================================
# Tests for expand_cycles function
# =============================================================================

class TestExpandCycles(unittest.TestCase):
    """Tests for the expand_cycles function."""

    def test_expand_cycles_not_dict_raises(self):
        """Test that non-dict input raises ValueError."""
        with self.assertRaises(ValueError) as context:
            fill_timeseries.expand_cycles(['not', 'a', 'dict'])
        self.assertIn('not associative list', str(context.exception))

    def test_expand_cycles_null_key_raises(self):
        """Test that None key raises ValueError."""
        yinfo = {None: {'column': '01.so2'}, 'valid': {'column': '02.so2'}}
        with self.assertRaises(ValueError) as context:
            fill_timeseries.expand_cycles(yinfo)
        self.assertIn('contain null', str(context.exception))

    def test_expand_cycles_simple_cycle(self):
        """Test expanding a simple cycle without template."""
        yinfo = {
            'cycle1': {'column': '01.so2'}
        }
        result = fill_timeseries.expand_cycles(yinfo)
        self.assertIn('cycle1', result)
        self.assertEqual(result['cycle1']['multiplier'], 1.0)
        self.assertEqual(result['cycle1']['emissionfactor'], 1.0)
        self.assertIsNone(result['cycle1']['substance'])

    def test_expand_cycles_with_template(self):
        """Test expanding cycles with template application."""
        yinfo = {
            'template1': {'column': None, 'factors': {'NOX': 1.5}},
            'cycle1': {
                'column': '01.nox',
                'template': {'name': 'template1', 'substance': 'NOX'}
            }
        }
        result = fill_timeseries.expand_cycles(yinfo)
        self.assertIn('cycle1', result)
        self.assertNotIn('template1', result)  # Templates not in output
        self.assertEqual(result['cycle1']['emissionfactor'], 1.5)
        self.assertEqual(result['cycle1']['substance'], 'NOX')

    def test_expand_cycles_undefined_template_raises(self):
        """Test that referencing undefined template raises ValueError."""
        yinfo = {
            'cycle1': {
                'column': '01.nox',
                'template': {'name': 'nonexistent', 'substance': 'NOX'}
            }
        }
        with self.assertRaises(ValueError) as context:
            fill_timeseries.expand_cycles(yinfo)
        self.assertIn('not defined', str(context.exception))

    def test_expand_cycles_template_identified_by_null_column(self):
        """Test that templates are identified by null column."""
        yinfo = {
            'is_template': {'column': None, 'factors': {'SO2': 2.0}},
            'is_cycle': {'column': '01.so2'}
        }
        result = fill_timeseries.expand_cycles(yinfo)
        self.assertNotIn('is_template', result)
        self.assertIn('is_cycle', result)


# =============================================================================
# Tests for parse_cycle function
# =============================================================================

class TestParseCycle(unittest.TestCase):
    """Tests for the parse_cycle function."""

    def setUp(self):
        """Set up test time series."""
        self.time = pd.date_range(
            "2000-01-01 00:00",
            "2000-01-02 00:00",
            freq="1h",
            tz="UTC"
        )

    def test_parse_cycle_invalid_time_type_raises(self):
        """Test that invalid time type raises ValueError."""
        c_info = {'column': '01.so2', 'start': {'at': {'time': 1, 'unit': 'day'}}}
        with self.assertRaises(ValueError) as context:
            fill_timeseries.parse_cycle('test', c_info, "not a time")
        self.assertIn('not list-like', str(context.exception))

    def test_parse_cycle_no_column_raises(self):
        """Test that missing column raises ValueError."""
        c_info = {'start': {'at': {'time': 1, 'unit': 'day'}}}
        with self.assertRaises(ValueError) as context:
            fill_timeseries.parse_cycle('test', c_info, self.time)
        self.assertIn('no column info', str(context.exception))

    def test_parse_cycle_name_equals_column_raises(self):
        """Test that cycle name equal to column name raises ValueError."""
        c_info = {'column': 'same_name', 'start': {'at': {'time': 1, 'unit': 'day'}}}
        with self.assertRaises(ValueError) as context:
            fill_timeseries.parse_cycle('same_name', c_info, self.time)
        self.assertIn('equal to column name', str(context.exception))

    def test_parse_cycle_illegal_factors_raises(self):
        """Test that 'factors' key in cycle raises ValueError."""
        c_info = {
            'column': '01.so2',
            'factors': {'SO2': 1.0},
            'start': {'at': {'time': 1, 'unit': 'day'}}
        }
        with self.assertRaises(ValueError) as context:
            fill_timeseries.parse_cycle('test', c_info, self.time)
        self.assertIn('illegal factors', str(context.exception))

    def test_parse_cycle_illegal_template_raises(self):
        """Test that 'template' key in cycle raises ValueError."""
        c_info = {
            'column': '01.so2',
            'template': {'name': 'foo'},
            'start': {'at': {'time': 1, 'unit': 'day'}}
        }
        with self.assertRaises(ValueError) as context:
            fill_timeseries.parse_cycle('test', c_info, self.time)
        self.assertIn('illegal template', str(context.exception))

    def test_parse_cycle_no_start_raises(self):
        """Test that missing start info raises ValueError."""
        c_info = {'column': '01.so2'}
        with self.assertRaises(ValueError) as context:
            fill_timeseries.parse_cycle('test', c_info, self.time)
        self.assertIn('no start info', str(context.exception))

    def test_parse_cycle_no_at_raises(self):
        """Test that missing 'at' in start raises ValueError."""
        c_info = {'column': '01.so2', 'start': {'offset': {'time': 1, 'unit': 'day'}}}
        with self.assertRaises(ValueError) as context:
            fill_timeseries.parse_cycle('test', c_info, self.time)
        self.assertIn('no at info', str(context.exception))

    def test_parse_cycle_non_uniform_time_raises(self):
        """Test that non-uniform time intervals raise ValueError."""
        # Create non-uniform time series
        non_uniform = pd.DatetimeIndex([
            '2000-01-01 00:00',
            '2000-01-01 01:00',
            '2000-01-01 03:00'  # Gap of 2 hours instead of 1
        ], tz='UTC')
        c_info = {
            'column': '01.so2',
            'start': {'at': {'time': 1, 'unit': 'day'}},
            'list': [1.0, 2.0]
        }
        with self.assertRaises(ValueError) as context:
            fill_timeseries.parse_cycle('test', c_info, non_uniform)
        self.assertIn('not uniform', str(context.exception))

    def test_parse_cycle_deprecated_source_warning(self):
        """Test that 'source' key triggers deprecation warning."""
        c_info = {
            'source': '01.so2',  # Deprecated
            'start': {'at': {'time': 1, 'unit': 'hour'}},
            'list': [1.0]
        }
        with self.assertWarns(DeprecationWarning):
            fill_timeseries.parse_cycle('test', c_info, self.time)


# =============================================================================
# Tests for module constants
# =============================================================================

class TestModuleConstants(unittest.TestCase):
    """Tests for module-level constants."""

    def test_default_begin(self):
        """Test DEFAULT_BEGIN constant."""
        self.assertEqual(fill_timeseries.DEFAULT_BEGIN, 8)

    def test_default_end(self):
        """Test DEFAULT_END constant."""
        self.assertEqual(fill_timeseries.DEFAULT_END, 17)


# =============================================================================
# Tests for add_options function
# =============================================================================

class TestAddOptions(unittest.TestCase):
    """Tests for the add_options function."""

    def test_add_options_returns_parser(self):
        """Test add_options returns an argument parser."""
        import argparse
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()

        result = fill_timeseries.add_options(subparsers)

        self.assertIsNotNone(result)

    def test_add_options_creates_subcommand(self):
        """Test add_options creates 'fill-timeseries' subcommand."""
        import argparse
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')

        fill_timeseries.add_options(subparsers)

        # Parse with fill-timeseries subcommand (requires action)
        args = parser.parse_args(['fill-timeseries', '-l'])
        self.assertEqual(args.command, 'fill-timeseries')

    def test_add_options_alias_ft(self):
        """Test add_options creates 'ft' alias."""
        import argparse
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')

        fill_timeseries.add_options(subparsers)

        args = parser.parse_args(['ft', '-l'])
        self.assertEqual(args.command, 'ft')

    def test_add_options_action_required(self):
        """Test that action argument is required."""
        import argparse
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')
        fill_timeseries.add_options(subparsers)

        with self.assertRaises(SystemExit):
            parser.parse_args(['fill-timeseries'])

    def test_add_options_action_list(self):
        """Test -l/--list sets action to 'list'."""
        import argparse
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')
        fill_timeseries.add_options(subparsers)

        args = parser.parse_args(['fill-timeseries', '-l'])
        self.assertEqual(args.action, 'list')

    def test_add_options_action_cycle(self):
        """Test -c/--cycle sets action to 'cycle'."""
        import argparse
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')
        fill_timeseries.add_options(subparsers)

        args = parser.parse_args(['fill-timeseries', '-c'])
        self.assertEqual(args.action, 'cycle')

    def test_add_options_action_week5(self):
        """Test -w/--week-5 sets action to 'week-5'."""
        import argparse
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')
        fill_timeseries.add_options(subparsers)

        args = parser.parse_args(['fill-timeseries', '-w'])
        self.assertEqual(args.action, 'week-5')

    def test_add_options_action_week6(self):
        """Test -W/--week-6 sets action to 'week-6'."""
        import argparse
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')
        fill_timeseries.add_options(subparsers)

        args = parser.parse_args(['fill-timeseries', '-W'])
        self.assertEqual(args.action, 'week-6')

    def test_add_options_actions_mutually_exclusive(self):
        """Test actions are mutually exclusive."""
        import argparse
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')
        fill_timeseries.add_options(subparsers)

        with self.assertRaises(SystemExit):
            parser.parse_args(['fill-timeseries', '-l', '-c'])

    def test_add_options_defaults(self):
        """Test default values are set correctly."""
        import argparse
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')
        fill_timeseries.add_options(subparsers)

        args = parser.parse_args(['fill-timeseries', '-l'])
        self.assertEqual(args.hour_begin, fill_timeseries.DEFAULT_BEGIN)
        self.assertEqual(args.hour_end, fill_timeseries.DEFAULT_END)
        self.assertEqual(args.cycle_file, 'cycle.yaml')


# =============================================================================
# Command line integration tests
# =============================================================================

class TestCommandLine(unittest.TestCase):
    """Tests for fill-timeseries command line interface."""

    def test_no_param(self):
        """Test that missing action parameter returns error."""
        command = CMD + [COMMAND]
        out, err, exitcode = capture(command)
        self.assertEqual(exitcode, 2)

    def test_help(self):
        """Test help displays usage."""
        # Test help when no action given (should show error with usage)
        command = CMD + [COMMAND]
        out, err, exitcode = capture(command)
        self.assertEqual(exitcode, 2)
        self.assertTrue(err.decode().startswith('usage'))

        # Test explicit help request
        command = CMD + [COMMAND, '-h']
        out, err, exitcode = capture(command)
        self.assertEqual(exitcode, 0)
        self.assertTrue(out.decode().startswith('usage'))

    def test_week5(self):
        """Test week-5 action."""
        make_zeitreihe()
        try:
            # Missing options should fail
            command = CMD + ['-d', 'tests', COMMAND]
            out, err, exitcode = capture(command)
            self.assertEqual(exitcode, 2)

            # With output option should succeed
            command = CMD + ['-d', 'tests', COMMAND, '-w', '-o', '1.0']
            out, err, exitcode = capture(command)
            self.assertEqual(exitcode, 0)
        finally:
            if os.path.exists('tests/zeitreihe.dmna'):
                os.remove('tests/zeitreihe.dmna')
            if os.path.exists('tests/zeitreihe.dmna~'):
                os.remove('tests/zeitreihe.dmna~')

    def test_cycle(self):
        """Test cycle action."""
        make_zeitreihe()
        make_cycle('cycle.yaml')
        try:
            # Cycle file with implicit default name
            command = CMD + ['-d', 'tests', COMMAND, '-c']
            out, err, exitcode = capture(command)
            self.assertEqual(exitcode, 0)

            # -c does not accept filename directly after it
            command = CMD + ['-d', 'tests', COMMAND, '-c', 'cycle.yaml']
            out, err, exitcode = capture(command)
            self.assertEqual(exitcode, 2)

            # Cycle file with explicit -f option
            command = CMD + ['-d', 'tests', COMMAND, '-c', '-f', 'cycle.yaml']
            out, err, exitcode = capture(command)
            self.assertEqual(exitcode, 0)

            # Rename and use non-default name
            os.renames('tests/cycle.yaml', 'tests/abcde.yaml')
            command = CMD + ['-d', 'tests', COMMAND, '-c', '-f', 'abcde.yaml']
            out, err, exitcode = capture(command)
            self.assertEqual(exitcode, 0)
        finally:
            for f in ['tests/zeitreihe.dmna', 'tests/zeitreihe.dmna~',
                      'tests/cycle.yaml', 'tests/abcde.yaml']:
                if os.path.exists(f):
                    os.remove(f)

    def test_ft_alias(self):
        """Test 'ft' alias works same as 'fill-timeseries'."""
        command = CMD + ['ft', '-h']
        out, err, exitcode = capture(command)
        self.assertEqual(exitcode, 0)
        self.assertTrue(out.decode().startswith('usage'))


# =============================================================================
# Pytest-style parametrized tests
# =============================================================================

class TestPytestStyle:
    """Pytest-style tests with parametrization."""

    @pytest.mark.parametrize("subcommand", [
        'fill-timeseries',
        'ft',
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
        args = parser.parse_args([verbosity_flag, 'fill-timeseries', '-l'])
        assert args.verb == expected_level

    @pytest.mark.parametrize("unit_string,expected", [
        ('month', 'months'),
        ('months', 'months'),
        ('mon', 'months'),
        ('week', 'weeks'),
        ('weeks', 'weeks'),
        ('w', 'weeks'),
        ('day', 'days'),
        ('days', 'days'),
        ('d', 'days'),
        ('hour', 'hours'),
        ('hours', 'hours'),
        ('hr', 'hours'),
        ('hrs', 'hours'),
        ('h', 'hours'),
    ])
    def test_parse_time_unit_variants(self, unit_string, expected):
        """Test all valid time unit variants."""
        assert fill_timeseries.parse_time_unit(unit_string) == expected

    @pytest.mark.parametrize("invalid_unit", [
        'second', 'seconds', 's', 'minute', 'minutes', 'm',
        'year', 'years', 'y', '', 'invalid'
    ])
    def test_parse_time_unit_invalid(self, invalid_unit):
        """Test invalid time units raise ValueError."""
        with pytest.raises(ValueError):
            fill_timeseries.parse_time_unit(invalid_unit)

    @pytest.mark.parametrize("action_flag,expected_action", [
        ('-l', 'list'),
        ('--list', 'list'),
        ('-c', 'cycle'),
        ('--cycle', 'cycle'),
        ('-w', 'week-5'),
        ('--week-5', 'week-5'),
        ('-W', 'week-6'),
        ('--week-6', 'week-6'),
    ])
    def test_action_flags(self, action_flag, expected_action):
        """Test all action flag variants."""
        import argparse
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')
        fill_timeseries.add_options(subparsers)

        args = parser.parse_args(['fill-timeseries', action_flag])
        assert args.action == expected_action


# =============================================================================
# Edge case tests
# =============================================================================

class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and boundary conditions."""

    def test_expand_cycles_empty_dict(self):
        """Test expand_cycles with empty dict."""
        result = fill_timeseries.expand_cycles({})
        self.assertEqual(result, {})

    def test_parse_time_unit_case_insensitive(self):
        """Test parse_time_unit is case insensitive."""
        self.assertEqual(fill_timeseries.parse_time_unit('MONTH'), 'months')
        self.assertEqual(fill_timeseries.parse_time_unit('Month'), 'months')
        self.assertEqual(fill_timeseries.parse_time_unit('mOnTh'), 'months')

    def test_parse_cycle_with_list_input(self):
        """Test parse_cycle accepts list as time input."""
        time_list = ['2000-01-01 00:00', '2000-01-01 01:00', '2000-01-01 02:00']
        c_info = {
            'column': '01.so2',
            'start': {'at': {'time': 1, 'unit': 'hour'}},
            'list': [1.0, 2.0]
        }
        # Should not raise - list is converted to DatetimeIndex
        try:
            fill_timeseries.parse_cycle('test', c_info, time_list)
        except ValueError as e:
            # May fail for other reasons, but not for time type
            self.assertNotIn('not list-like', str(e))


if __name__ == '__main__':
    unittest.main()
