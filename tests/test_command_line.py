#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for austaltools.command_line module.

This module tests the common command line interface elements
that are shared across all subcommands.
"""
import argparse
import logging
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import pytest

from austaltools import command_line
from austaltools._metadata import __version__, __title__


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


class TestCliParser(unittest.TestCase):
    """Tests for the cli_parser function."""

    def test_cli_parser_returns_parser(self):
        """Test cli_parser returns an ArgumentParser."""
        parser = command_line.cli_parser()
        self.assertIsInstance(parser, argparse.ArgumentParser)

    def test_cli_parser_has_version(self):
        """Test cli_parser includes version argument."""
        parser = command_line.cli_parser()
        # Try parsing --version (will exit, so we catch SystemExit)
        with self.assertRaises(SystemExit) as context:
            parser.parse_args(['--version'])
        self.assertEqual(context.exception.code, 0)

    def test_cli_parser_has_working_dir(self):
        """Test cli_parser includes working_dir argument."""
        parser = command_line.cli_parser()
        # Parse with a subcommand and check working_dir
        args = parser.parse_args(['-d', '/custom/path', 'simple', '49.75', '6.65', 'Test'])
        self.assertEqual(args.working_dir, '/custom/path')

    def test_cli_parser_default_working_dir(self):
        """Test cli_parser has default working_dir."""
        parser = command_line.cli_parser()
        args = parser.parse_args(['simple', '49.75', '6.65', 'Test'])
        self.assertIsNotNone(args.working_dir)

    def test_cli_parser_has_temp_dir(self):
        """Test cli_parser includes temp_dir argument."""
        parser = command_line.cli_parser()
        args = parser.parse_args(['--temp-dir', '/tmp/custom', 'simple', '49.75', '6.65', 'Test'])
        self.assertEqual(args.temp_dir, '/tmp/custom')

    def test_cli_parser_temp_dir_default_none(self):
        """Test cli_parser temp_dir defaults to None."""
        parser = command_line.cli_parser()
        args = parser.parse_args(['simple', '49.75', '6.65', 'Test'])
        self.assertIsNone(args.temp_dir)

    def test_cli_parser_verbosity_debug(self):
        """Test cli_parser accepts --debug."""
        parser = command_line.cli_parser()
        args = parser.parse_args(['--debug', 'simple', '49.75', '6.65', 'Test'])
        self.assertEqual(args.verb, logging.DEBUG)

    def test_cli_parser_verbosity_verbose(self):
        """Test cli_parser accepts --verbose."""
        parser = command_line.cli_parser()
        args = parser.parse_args(['--verbose', 'simple', '49.75', '6.65', 'Test'])
        self.assertEqual(args.verb, logging.INFO)

    def test_cli_parser_verbosity_short(self):
        """Test cli_parser accepts -v for verbose."""
        parser = command_line.cli_parser()
        args = parser.parse_args(['-v', 'simple', '49.75', '6.65', 'Test'])
        self.assertEqual(args.verb, logging.INFO)

    def test_cli_parser_verbosity_mutual_exclusion(self):
        """Test --debug and --verbose are mutually exclusive."""
        parser = command_line.cli_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(['--debug', '--verbose', 'simple', '49.75', '6.65', 'Test'])

    def test_cli_parser_requires_subcommand(self):
        """Test cli_parser requires a subcommand."""
        parser = command_line.cli_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([])


# class TestCliParserSubcommands(unittest.TestCase):
#     """Tests for subcommand availability in cli_parser."""
#
#     def setUp(self):
#         """Set up parser for tests."""
#         self.parser = command_line.cli_parser()
#
#     def test_has_eap_subcommand(self):
#         """Test 'simple' subcommand is available."""
#         args = self.parser.parse_args(['eap'])
#         self.assertEqual(args.command, 'eap')
#
#     def test_has_plot_subcommand(self):
#         """Test 'plot' subcommand is available."""
#         args = self.parser.parse_args(['plot'])
#         self.assertEqual(args.command, 'plot')
#
#     def test_has_simple_subcommand(self):
#         """Test 'simple' subcommand is available."""
#         args = self.parser.parse_args(['simple', '49.75', '6.65', 'Test'])
#         self.assertEqual(args.command, 'simple')
#
#     def test_has_steepness_subcommand(self):
#         """Test 'steepness' subcommand is available."""
#         args = self.parser.parse_args(['steepness'])
#         self.assertEqual(args.command, 'steepness')
#
#     def test_has_terrain_subcommand(self):
#         """Test 'terrain' subcommand is available."""
#         args = self.parser.parse_args(['terrain'])
#         self.assertEqual(args.command, 'terrain')
#
#     def test_has_transform_subcommand(self):
#         """Test 'transform' subcommand is available."""
#         args = self.parser.parse_args(['transform'])
#         self.assertEqual(args.command, 'transform')
#
#     def test_has_weather_subcommand(self):
#         """Test 'weather' subcommand is available."""
#         args = self.parser.parse_args(['weather'])
#         self.assertEqual(args.command, 'weather')
#
#     def test_has_windfield_subcommand(self):
#         """Test 'windfield' subcommand is available."""
#         args = self.parser.parse_args(['windfield'])
#         self.assertEqual(args.command, 'windfield')
#
#     def test_has_windrose_subcommand(self):
#         """Test 'windrose' subcommand is available."""
#         args = self.parser.parse_args(['windrose'])
#         self.assertEqual(args.command, 'windrose')
#
#     def test_has_heating_subcommand(self):
#         """Test 'heating' subcommand is available."""
#         args = self.parser.parse_args(['heating'])
#         self.assertEqual(args.command, 'heating')
#
#     def test_has_import_buildings_subcommand(self):
#         """Test 'import-buildings' subcommand is available."""
#         args = self.parser.parse_args(['import-buildings'])
#         self.assertEqual(args.command, 'import-buildings')
#
#     def test_has_bg_alias_subcommand(self):
#         """Test 'bg' alias for import-buildings is available."""
#         args = self.parser.parse_args(['bg'])
#         self.assertEqual(args.command, 'bg')
#
#     def test_has_fill_timeseries_subcommand(self):
#         """Test 'fill-timeseries' subcommand is available."""
#         args = self.parser.parse_args(['fill-timeseries', '-w'])
#         self.assertEqual(args.command, 'fill-timeseries')
#
#     def test_has_ft_alias_subcommand(self):
#         """Test 'ft' alias for fill-timeseries is available."""
#         args = self.parser.parse_args(['ft','-w'])
#         self.assertEqual(args.command, 'ft')


# class TestMain(unittest.TestCase):
#     """Tests for the main function."""
#
#     @patch('austaltools.command_line.eap.main')
#     def test_main_calls_eap(self, mock_eap_main):
#         """Test main dispatches to eap.main for 'simple' command."""
#         args = {
#             'command': 'simple',
#             'working_dir': '/tmp',
#             'verb': None,
#             'temp_dir': None
#         }
#         command_line.main(args)
#         mock_eap_main.assert_called_once_with(args)
#
#     @patch('austaltools.command_line.plot.main')
#     def test_main_calls_plot(self, mock_plot_main):
#         """Test main dispatches to plot.main for 'plot' command."""
#         args = {
#             'command': 'plot',
#             'working_dir': '/tmp',
#             'verb': None,
#             'temp_dir': None
#         }
#         command_line.main(args)
#         mock_plot_main.assert_called_once_with(args)
#
#     @patch('austaltools.command_line.simple.main')
#     def test_main_calls_simple(self, mock_simple_main):
#         """Test main dispatches to simple.main for 'simple' command."""
#         args = {
#             'command': 'simple',
#             'working_dir': '/tmp',
#             'verb': None,
#             'temp_dir': None
#         }
#         command_line.main(args)
#         mock_simple_main.assert_called_once_with(args)
#
#     @patch('austaltools.command_line.import_buildings.main')
#     def test_main_calls_import_buildings(self, mock_main):
#         """Test main dispatches for 'import-buildings' command."""
#         args = {
#             'command': 'import-buildings',
#             'working_dir': '/tmp',
#             'verb': None,
#             'temp_dir': None
#         }
#         command_line.main(args)
#         mock_main.assert_called_once_with(args)
#
#     @patch('austaltools.command_line.import_buildings.main')
#     def test_main_calls_bg_alias(self, mock_main):
#         """Test main dispatches for 'bg' alias command."""
#         args = {
#             'command': 'bg',
#             'working_dir': '/tmp',
#             'verb': None,
#             'temp_dir': None
#         }
#         command_line.main(args)
#         mock_main.assert_called_once_with(args)
#
#     def test_main_no_working_dir_raises(self):
#         """Test main raises when working_dir is None."""
#         args = {
#             'command': 'simple',
#             'working_dir': None,
#             'verb': None,
#             'temp_dir': None
#         }
#         with self.assertRaises(ValueError) as context:
#             command_line.main(args)
#         self.assertIn('PATH not given', str(context.exception))
#
#     @patch('austaltools.command_line._storage')
#     @patch('austaltools.command_line.eap.main')
#     def test_main_sets_temp_dir(self, mock_eap_main, mock_storage):
#         """Test main sets _storage.TEMP when temp_dir provided."""
#         args = {
#             'command': 'simple',
#             'working_dir': '/tmp',
#             'verb': None,
#             'temp_dir': '/custom/temp'
#         }
#         command_line.main(args)
#         self.assertEqual(mock_storage.TEMP, '/custom/temp')


class TestUsageError(unittest.TestCase):
    """Tests for UsageError exception."""

    def test_usage_error_exists(self):
        """Test UsageError exception class exists."""
        self.assertTrue(hasattr(command_line, 'UsageError'))

    def test_usage_error_is_exception(self):
        """Test UsageError is an Exception subclass."""
        self.assertTrue(issubclass(command_line.UsageError, Exception))

    def test_usage_error_can_be_raised(self):
        """Test UsageError can be raised and caught."""
        with self.assertRaises(command_line.UsageError):
            raise command_line.UsageError('test error')


class TestCommandLineVersion(unittest.TestCase):
    """Tests for version display."""

    def test_version_output(self):
        """Test --version shows version string."""
        command = CMD + ['--version']
        out, err, exitcode = capture(command)
        self.assertEqual(exitcode, 0)
        # Version should be in stdout or stderr
        output = out.decode() + err.decode()
        self.assertIn(__version__, output)


class TestCommandLineHelp(unittest.TestCase):
    """Tests for help display."""

    def test_main_help(self):
        """Test main --help shows usage."""
        command = CMD + ['--help']
        out, err, exitcode = capture(command)
        self.assertEqual(exitcode, 0)
        self.assertIn('usage', out.decode().lower())

    def test_main_help_short(self):
        """Test main -h shows usage."""
        command = CMD + ['-h']
        out, err, exitcode = capture(command)
        self.assertEqual(exitcode, 0)
        self.assertIn('usage', out.decode().lower())

    def test_subcommand_help(self):
        """Test subcommand --help shows subcommand usage."""
        command = CMD + ['simple', '--help']
        out, err, exitcode = capture(command)
        self.assertEqual(exitcode, 0)
        self.assertIn('usage', out.decode().lower())
        self.assertIn('simple', out.decode().lower())


class TestCommandLineVerbosity(unittest.TestCase):
    """Tests for verbosity settings via command line."""

    def test_debug_sets_logging(self):
        """Test --debug affects logging level."""
        # This is tested indirectly via parsing
        parser = command_line.cli_parser()
        args = parser.parse_args(['--debug', 'simple', '49.75', '6.65', 'Test'])
        self.assertEqual(args.verb, logging.DEBUG)

    def test_verbose_sets_logging(self):
        """Test --verbose affects logging level."""
        parser = command_line.cli_parser()
        args = parser.parse_args(['--verbose', 'simple', '49.75', '6.65', 'Test'])
        self.assertEqual(args.verb, logging.INFO)


# Pytest-style parametrized tests

# class TestPytestStyle:
#     """Pytest-style tests with parametrization."""
#
#     @pytest.mark.parametrize("subcommand", [
#         'simple', 'plot', 'simple', 'steepness', 'terrain',
#         'transform', 'weather', 'windfield', 'windrose',
#         'heating', 'import-buildings', 'bg', 'fill-timeseries', 'ft'
#     ])
#     def test_subcommand_help_available(self, subcommand):
#         """Test help is available for all subcommands."""
#         command = CMD + [subcommand, '-h']
#         out, err, exitcode = capture(command)
#         assert exitcode == 0
#         assert 'usage' in out.decode().lower()
#
#     @pytest.mark.parametrize("verbosity_flag,expected_level", [
#         ('--debug', logging.DEBUG),
#         ('--verbose', logging.INFO),
#         ('-v', logging.INFO),
#     ])
#     def test_verbosity_flags(self, verbosity_flag, expected_level):
#         """Test verbosity flags set correct logging levels."""
#         parser = command_line.cli_parser()
#         args = parser.parse_args([verbosity_flag, 'simple', '49.75', '6.65', 'Test'])
#         assert args.verb == expected_level


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and boundary conditions."""

    def test_unknown_subcommand_fails(self):
        """Test unknown subcommand causes error."""
        command = CMD + ['unknown_command']
        out, err, exitcode = capture(command)
        self.assertNotEqual(exitcode, 0)

    def test_empty_args_fails(self):
        """Test no arguments causes error."""
        command = CMD
        out, err, exitcode = capture(command)
        self.assertNotEqual(exitcode, 0)


class TestModuleImports(unittest.TestCase):
    """Tests for module-level attributes."""

    def test_logger_exists(self):
        """Test module logger is defined."""
        self.assertIsNotNone(command_line.logger)

    def test_version_importable(self):
        """Test __version__ is available."""
        from austaltools._metadata import __version__
        self.assertIsNotNone(__version__)

    def test_title_importable(self):
        """Test __title__ is available."""
        from austaltools._metadata import __title__
        self.assertIsNotNone(__title__)


if __name__ == '__main__':
    unittest.main()
