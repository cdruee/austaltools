#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive test suite for austaltools._plotting module.

This module tests plotting utilities for visualizing AUSTAL results
including topography, buildings, and data overlays.
"""
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock, PropertyMock

import numpy as np
import pandas as pd
import pytest

from austaltools import _plotting


class TestPlotAddMark(unittest.TestCase):
    """Tests for the plot_add_mark function."""

    def test_plot_add_mark_basic(self):
        """Test plot_add_mark adds markers to axes."""
        mock_ax = MagicMock()
        mark = {
            'x': [100, 200, 300],
            'y': [150, 250, 350]
        }
        
        _plotting.plot_add_mark(mock_ax, mark)
        
        # Should call plot for each point
        self.assertEqual(mock_ax.plot.call_count, 3)

    def test_plot_add_mark_with_symbol(self):
        """Test plot_add_mark with custom symbols."""
        mock_ax = MagicMock()
        mark = {
            'x': [100],
            'y': [150],
            'symbol': ['x']
        }
        
        _plotting.plot_add_mark(mock_ax, mark)
        
        mock_ax.plot.assert_called_once()

    def test_plot_add_mark_dataframe(self):
        """Test plot_add_mark with pandas DataFrame."""
        mock_ax = MagicMock()
        mark = pd.DataFrame({
            'x': [100, 200],
            'y': [150, 250]
        })
        
        _plotting.plot_add_mark(mock_ax, mark)
        
        self.assertEqual(mock_ax.plot.call_count, 2)


class TestPlotAddTopo(unittest.TestCase):
    """Tests for the plot_add_topo function."""

    def test_plot_add_topo_from_dict(self):
        """Test plot_add_topo with dict data."""
        mock_ax = MagicMock()
        mock_contour = MagicMock()
        mock_contour.levels = [0, 100, 200]
        mock_ax.contour.return_value = mock_contour
        
        topo = {
            'x': np.arange(10),
            'y': np.arange(10),
            'z': np.random.rand(10, 10) * 100
        }
        
        result = _plotting.plot_add_topo(mock_ax, topo)
        
        mock_ax.contour.assert_called_once()
        mock_ax.clabel.assert_called_once()

    @patch('austaltools._plotting.read_topography')
    def test_plot_add_topo_from_file(self, mock_read_topo):
        """Test plot_add_topo with file path."""
        mock_ax = MagicMock()
        mock_contour = MagicMock()
        mock_contour.levels = [0, 100, 200]
        mock_ax.contour.return_value = mock_contour
        
        mock_read_topo.return_value = (
            np.arange(10),
            np.arange(10),
            np.random.rand(10, 10) * 100,
            10.0
        )
        
        with tempfile.NamedTemporaryFile(suffix='.dmna', delete=False) as f:
            topo_path = f.name
        
        try:
            result = _plotting.plot_add_topo(mock_ax, topo_path)
            mock_read_topo.assert_called_once()
        finally:
            if os.path.exists(topo_path):
                os.remove(topo_path)

    def test_plot_add_topo_invalid_type_raises(self):
        """Test plot_add_topo raises for invalid topo type."""
        mock_ax = MagicMock()
        
        with self.assertRaises(ValueError) as context:
            _plotting.plot_add_topo(mock_ax, 12345)
        
        self.assertIn('must be dict', str(context.exception))

    @patch('os.path.exists')
    def test_plot_add_topo_file_not_found_raises(self, mock_exists):
        """Test plot_add_topo raises when file not found."""
        mock_ax = MagicMock()
        mock_exists.return_value = False
        
        with self.assertRaises(ValueError) as context:
            _plotting.plot_add_topo(mock_ax, 'nonexistent.dmna')
        
        self.assertIn('not found', str(context.exception))


class TestCommonPlot(unittest.TestCase):
    """Tests for the common_plot function."""

    @patch('austaltools._plotting.plt')
    @patch('austaltools._plotting.matplotlib')
    def test_common_plot_contour(self, mock_mpl, mock_plt):
        """Test common_plot with contour display."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        mock_plt.get_cmap.return_value = MagicMock()
        mock_plt.contourf.return_value = MagicMock()
        
        args = {
            'plot': None,
            'kind': 'contour',
            'fewcols': False,
            'working_dir': '.'
        }
        dat = {
            'x': np.arange(10),
            'y': np.arange(10),
            'z': np.random.rand(10, 10)
        }
        
        _plotting.common_plot(args, dat)
        
        mock_plt.contourf.assert_called()

    @patch('austaltools._plotting.plt')
    @patch('austaltools._plotting.matplotlib')
    def test_common_plot_grid(self, mock_mpl, mock_plt):
        """Test common_plot with grid display."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        mock_plt.get_cmap.return_value = MagicMock()
        mock_plt.pcolormesh.return_value = MagicMock()
        
        args = {
            'plot': None,
            'kind': 'grid',
            'fewcols': False,
            'working_dir': '.'
        }
        dat = {
            'x': np.arange(10),
            'y': np.arange(10),
            'z': np.random.rand(10, 10)
        }
        
        _plotting.common_plot(args, dat)
        
        mock_plt.pcolormesh.assert_called()

    @patch('austaltools._plotting.plt')
    @patch('austaltools._plotting.matplotlib')
    def test_common_plot_invalid_kind_raises(self, mock_mpl, mock_plt):
        """Test common_plot raises for invalid kind."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        mock_plt.get_cmap.return_value = MagicMock()
        
        args = {
            'plot': None,
            'kind': 'invalid',
            'fewcols': False,
            'working_dir': '.'
        }
        dat = {
            'x': np.arange(10),
            'y': np.arange(10),
            'z': np.random.rand(10, 10)
        }
        
        with self.assertRaises(ValueError) as context:
            _plotting.common_plot(args, dat)
        
        self.assertIn('invalid', str(context.exception).lower())

    @patch('austaltools._plotting.plt')
    @patch('austaltools._plotting.matplotlib')
    def test_common_plot_dat_shape_mismatch_raises(self, mock_mpl, mock_plt):
        """Test common_plot raises when x, y lengths don't match z shape."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        
        args = {
            'plot': None,
            'kind': 'contour',
            'fewcols': False,
            'working_dir': '.'
        }
        dat = {
            'x': np.arange(10),
            'y': np.arange(5),  # Wrong size
            'z': np.random.rand(10, 10)
        }
        
        with self.assertRaises(ValueError) as context:
            _plotting.common_plot(args, dat)
        
        self.assertIn('shape', str(context.exception))

    @patch('austaltools._plotting.plt')
    @patch('austaltools._plotting.matplotlib')
    def test_common_plot_dat_not_dict_raises(self, mock_mpl, mock_plt):
        """Test common_plot raises when dat is not a dict."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        
        args = {
            'plot': None,
            'kind': 'contour',
            'fewcols': False,
            'working_dir': '.'
        }
        
        with self.assertRaises(ValueError) as context:
            _plotting.common_plot(args, "not a dict")
        
        self.assertIn('must be dict', str(context.exception))

    @patch('austaltools._plotting.plt')
    @patch('austaltools._plotting.matplotlib')
    def test_common_plot_with_custom_colormap(self, mock_mpl, mock_plt):
        """Test common_plot with custom colormap."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        mock_plt.get_cmap.return_value = MagicMock()
        mock_plt.contourf.return_value = MagicMock()
        
        args = {
            'plot': None,
            'kind': 'contour',
            'fewcols': False,
            'working_dir': '.',
            'colormap': 'viridis'
        }
        dat = {
            'x': np.arange(10),
            'y': np.arange(10),
            'z': np.random.rand(10, 10)
        }
        
        _plotting.common_plot(args, dat)
        
        mock_plt.get_cmap.assert_called()

    @patch('austaltools._plotting.plt')
    @patch('austaltools._plotting.matplotlib')
    def test_common_plot_with_scale_tuple(self, mock_mpl, mock_plt):
        """Test common_plot with scale as tuple."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        mock_plt.get_cmap.return_value = MagicMock()
        mock_plt.contourf.return_value = MagicMock()
        
        args = {
            'plot': None,
            'kind': 'contour',
            'fewcols': False,
            'working_dir': '.'
        }
        dat = {
            'x': np.arange(10),
            'y': np.arange(10),
            'z': np.random.rand(10, 10)
        }
        
        _plotting.common_plot(args, dat, scale=(0, 1))
        
        mock_plt.contourf.assert_called()

    @patch('austaltools._plotting.plt')
    @patch('austaltools._plotting.matplotlib')
    def test_common_plot_with_scale_levels(self, mock_mpl, mock_plt):
        """Test common_plot with scale as explicit levels."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        mock_plt.get_cmap.return_value = MagicMock()
        mock_plt.contourf.return_value = MagicMock()
        
        args = {
            'plot': None,
            'kind': 'contour',
            'fewcols': False,
            'working_dir': '.'
        }
        dat = {
            'x': np.arange(10),
            'y': np.arange(10),
            'z': np.random.rand(10, 10)
        }
        
        _plotting.common_plot(args, dat, scale=[0, 0.25, 0.5, 0.75, 1.0])
        
        mock_plt.contourf.assert_called()

    @patch('austaltools._plotting.plt')
    @patch('austaltools._plotting.matplotlib')
    def test_common_plot_with_dots_dict(self, mock_mpl, mock_plt):
        """Test common_plot with dots overlay as dict."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        mock_plt.get_cmap.return_value = MagicMock()
        mock_plt.contourf.return_value = MagicMock()
        
        args = {
            'plot': None,
            'kind': 'contour',
            'fewcols': False,
            'working_dir': '.'
        }
        dat = {
            'x': np.arange(10),
            'y': np.arange(10),
            'z': np.random.rand(10, 10)
        }
        dots = {
            'x': np.arange(10),
            'y': np.arange(10),
            'z': np.random.rand(10, 10)
        }
        
        _plotting.common_plot(args, dat, dots=dots)

    @patch('austaltools._plotting.plt')
    @patch('austaltools._plotting.matplotlib')
    def test_common_plot_with_dots_array(self, mock_mpl, mock_plt):
        """Test common_plot with dots overlay as ndarray."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        mock_plt.get_cmap.return_value = MagicMock()
        mock_plt.contourf.return_value = MagicMock()
        
        args = {
            'plot': None,
            'kind': 'contour',
            'fewcols': False,
            'working_dir': '.'
        }
        dat = {
            'x': np.arange(10),
            'y': np.arange(10),
            'z': np.random.rand(10, 10)
        }
        dots = np.random.rand(10, 10)
        
        _plotting.common_plot(args, dat, dots=dots)

    @patch('austaltools._plotting.plt')
    @patch('austaltools._plotting.matplotlib')
    def test_common_plot_dots_shape_mismatch_raises(self, mock_mpl, mock_plt):
        """Test common_plot raises when dots shape doesn't match dat."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        mock_plt.get_cmap.return_value = MagicMock()
        mock_plt.contourf.return_value = MagicMock()
        
        args = {
            'plot': None,
            'kind': 'contour',
            'fewcols': False,
            'working_dir': '.'
        }
        dat = {
            'x': np.arange(10),
            'y': np.arange(10),
            'z': np.random.rand(10, 10)
        }
        dots = np.random.rand(5, 5)  # Wrong shape
        
        with self.assertRaises(ValueError) as context:
            _plotting.common_plot(args, dat, dots=dots)
        
        self.assertIn('shape', str(context.exception))

    @patch('austaltools._plotting.plt')
    @patch('austaltools._plotting.matplotlib')
    @patch('austaltools._plotting.patches')
    def test_common_plot_with_buildings(self, mock_patches, mock_mpl, mock_plt):
        """Test common_plot with buildings overlay."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        mock_plt.get_cmap.return_value = MagicMock()
        mock_plt.contourf.return_value = MagicMock()
        
        args = {
            'plot': None,
            'kind': 'contour',
            'fewcols': False,
            'working_dir': '.'
        }
        dat = {
            'x': np.arange(10),
            'y': np.arange(10),
            'z': np.random.rand(10, 10)
        }
        
        # Mock building objects
        mock_building = MagicMock()
        mock_building.x = 100
        mock_building.y = 100
        mock_building.a = 50
        mock_building.b = 30
        mock_building.w = 0
        
        _plotting.common_plot(args, dat, buildings=[mock_building])
        
        mock_ax.add_patch.assert_called()

    @patch('austaltools._plotting.plt')
    @patch('austaltools._plotting.matplotlib')
    @patch('austaltools._plotting.plot_add_mark')
    def test_common_plot_with_mark(self, mock_add_mark, mock_mpl, mock_plt):
        """Test common_plot with mark overlay."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        mock_plt.get_cmap.return_value = MagicMock()
        mock_plt.contourf.return_value = MagicMock()
        
        args = {
            'plot': None,
            'kind': 'contour',
            'fewcols': False,
            'working_dir': '.'
        }
        dat = {
            'x': np.arange(10),
            'y': np.arange(10),
            'z': np.random.rand(10, 10)
        }
        mark = {'x': [100], 'y': [100]}
        
        _plotting.common_plot(args, dat, mark=mark)
        
        mock_add_mark.assert_called_once()

    @patch('austaltools._plotting.plt')
    @patch('austaltools._plotting.matplotlib')
    def test_common_plot_save_to_file(self, mock_mpl, mock_plt):
        """Test common_plot saves to file."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        mock_plt.get_cmap.return_value = MagicMock()
        mock_plt.contourf.return_value = MagicMock()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            args = {
                'plot': 'test_output',
                'kind': 'contour',
                'fewcols': False,
                'working_dir': tmpdir
            }
            dat = {
                'x': np.arange(10),
                'y': np.arange(10),
                'z': np.random.rand(10, 10)
            }
            
            _plotting.common_plot(args, dat)
            
            mock_plt.savefig.assert_called_once()

    @patch('austaltools._plotting._HAVE_DISPLAY', False)
    @patch('austaltools._plotting.plt')
    @patch('austaltools._plotting.matplotlib')
    def test_common_plot_show_no_display_raises(self, mock_mpl, mock_plt):
        """Test common_plot raises when showing without display."""
        args = {
            'plot': '__show__',
            'kind': 'contour',
            'fewcols': False,
            'working_dir': '.'
        }
        dat = {
            'x': np.arange(10),
            'y': np.arange(10),
            'z': np.random.rand(10, 10)
        }
        
        with self.assertRaises(EnvironmentError):
            _plotting.common_plot(args, dat)

    @patch('austaltools._plotting.plt')
    @patch('austaltools._plotting.matplotlib')
    def test_common_plot_fewcols_true(self, mock_mpl, mock_plt):
        """Test common_plot with fewcols=True for discrete colors."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        mock_plt.get_cmap.return_value = MagicMock()
        mock_plt.contourf.return_value = MagicMock()
        
        args = {
            'plot': None,
            'kind': 'contour',
            'fewcols': True,
            'working_dir': '.'
        }
        dat = {
            'x': np.arange(10),
            'y': np.arange(10),
            'z': np.random.rand(10, 10)
        }
        
        _plotting.common_plot(args, dat)
        
        mock_plt.contourf.assert_called()


class TestReadTopography(unittest.TestCase):
    """Tests for the read_topography function."""

    @patch('austaltools._plotting.readmet')
    def test_read_topography_dmna(self, mock_readmet):
        """Test read_topography with .dmna file."""
        mock_datafile = MagicMock()
        mock_datafile.data = {"": np.random.rand(10, 10)}
        mock_datafile.axes.side_effect = [np.arange(10), np.arange(10)]
        mock_datafile.header = {"delta": "10.0"}
        mock_readmet.dmna.DataFile.return_value = mock_datafile
        
        topx, topy, topz, dd = _plotting.read_topography('test.dmna')
        
        mock_readmet.dmna.DataFile.assert_called_once_with('test.dmna')
        self.assertEqual(dd, 10.0)

    @patch('austaltools._plotting._tools.GridASCII')
    def test_read_topography_grid(self, mock_grid_ascii):
        """Test read_topography with .grid file."""
        mock_gridfile = MagicMock()
        mock_gridfile.data = np.random.rand(10, 10)
        mock_gridfile.header = {
            "cellsize": "10.0",
            "xllcorner": "0.0",
            "yllcorner": "0.0",
            "ncols": "10",
            "nrows": "10"
        }
        mock_grid_ascii.return_value = mock_gridfile
        
        topx, topy, topz, dd = _plotting.read_topography('test.grid')
        
        mock_grid_ascii.assert_called_once_with('test.grid')
        self.assertEqual(dd, 10.0)
        self.assertEqual(len(topx), 10)
        self.assertEqual(len(topy), 10)

    def test_read_topography_unknown_extension_raises(self):
        """Test read_topography raises for unknown extension."""
        with self.assertRaises(ValueError) as context:
            _plotting.read_topography('test.unknown')
        
        self.assertIn('unknown', str(context.exception).lower())


class TestModuleImports(unittest.TestCase):
    """Tests for module-level imports and logger."""

    def test_logger_exists(self):
        """Test module logger is defined."""
        self.assertIsNotNone(_plotting.logger)

    def test_imports_tools(self):
        """Test _tools module is imported."""
        self.assertIsNotNone(_plotting._tools)


# Pytest-style parametrized tests

class TestPytestStyle:
    """Pytest-style tests for additional patterns."""

    @pytest.mark.parametrize("kind", ['contour', 'grid'])
    @patch('austaltools._plotting.plt')
    @patch('austaltools._plotting.matplotlib')
    def test_common_plot_kinds(self, mock_mpl, mock_plt, kind):
        """Test common_plot with different kinds."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        mock_plt.get_cmap.return_value = MagicMock()
        mock_plt.contourf.return_value = MagicMock()
        mock_plt.pcolormesh.return_value = MagicMock()
        
        args = {
            'plot': None,
            'kind': kind,
            'fewcols': False,
            'working_dir': '.'
        }
        dat = {
            'x': np.arange(10),
            'y': np.arange(10),
            'z': np.random.rand(10, 10)
        }
        
        _plotting.common_plot(args, dat)

    @pytest.mark.parametrize("scale", [
        None,
        1.0,
        (0, 1),
        [0, 0.25, 0.5, 0.75, 1.0],
    ])
    @patch('austaltools._plotting.plt')
    @patch('austaltools._plotting.matplotlib')
    def test_common_plot_scale_options(self, mock_mpl, mock_plt, scale):
        """Test common_plot with different scale options."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        mock_plt.get_cmap.return_value = MagicMock()
        mock_plt.contourf.return_value = MagicMock()
        
        args = {
            'plot': None,
            'kind': 'contour',
            'fewcols': False,
            'working_dir': '.'
        }
        dat = {
            'x': np.arange(10),
            'y': np.arange(10),
            'z': np.random.rand(10, 10)
        }
        
        _plotting.common_plot(args, dat, scale=scale)

    @pytest.mark.parametrize("extension", ['.dmna', '.grid'])
    def test_read_topography_extensions(self, extension):
        """Test read_topography recognizes valid extensions."""
        # Just test that the function attempts to read the right format
        # Actual file reading is mocked in individual tests
        with patch('austaltools._plotting.readmet') as mock_readmet:
            with patch('austaltools._plotting._tools.GridASCII') as mock_grid:
                mock_datafile = MagicMock()
                mock_datafile.data = {"": np.random.rand(10, 10)}
                mock_datafile.axes.side_effect = [np.arange(10), np.arange(10)]
                mock_datafile.header = {"delta": "10.0"}
                mock_readmet.dmna.DataFile.return_value = mock_datafile
                
                mock_gridfile = MagicMock()
                mock_gridfile.data = np.random.rand(10, 10)
                mock_gridfile.header = {
                    "cellsize": "10.0",
                    "xllcorner": "0.0",
                    "yllcorner": "0.0",
                    "ncols": "10",
                    "nrows": "10"
                }
                mock_grid.return_value = mock_gridfile
                
                _plotting.read_topography(f'test{extension}')


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and boundary conditions."""

    def test_plot_add_mark_empty_marks(self):
        """Test plot_add_mark with empty marks."""
        mock_ax = MagicMock()
        mark = {'x': [], 'y': []}
        
        _plotting.plot_add_mark(mock_ax, mark)
        
        mock_ax.plot.assert_not_called()

    @patch('austaltools._plotting.plt')
    @patch('austaltools._plotting.matplotlib')
    def test_common_plot_with_unit(self, mock_mpl, mock_plt):
        """Test common_plot passes unit to colorbar."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        mock_plt.get_cmap.return_value = MagicMock()
        mock_plt.contourf.return_value = MagicMock()
        
        args = {
            'plot': None,
            'kind': 'contour',
            'fewcols': False,
            'working_dir': '.'
        }
        dat = {
            'x': np.arange(10),
            'y': np.arange(10),
            'z': np.random.rand(10, 10)
        }
        
        _plotting.common_plot(args, dat, unit='µg/m³')
        
        mock_plt.colorbar.assert_called()

    @patch('austaltools._plotting.plt')
    @patch('austaltools._plotting.matplotlib')
    def test_common_plot_dots_invalid_type_raises(self, mock_mpl, mock_plt):
        """Test common_plot raises for invalid dots type."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        mock_plt.get_cmap.return_value = MagicMock()
        mock_plt.contourf.return_value = MagicMock()
        
        args = {
            'plot': None,
            'kind': 'contour',
            'fewcols': False,
            'working_dir': '.'
        }
        dat = {
            'x': np.arange(10),
            'y': np.arange(10),
            'z': np.random.rand(10, 10)
        }
        
        with self.assertRaises(ValueError) as context:
            _plotting.common_plot(args, dat, dots="invalid")
        
        self.assertIn('must be dict or ndarray', str(context.exception))


class TestIntegration(unittest.TestCase):
    """Integration tests combining multiple components."""

    @patch('austaltools._plotting.plt')
    @patch('austaltools._plotting.matplotlib')
    @patch('austaltools._plotting.plot_add_topo')
    @patch('austaltools._plotting.plot_add_mark')
    @patch('austaltools._plotting.patches')
    def test_common_plot_full_features(self, mock_patches, mock_add_mark,
                                        mock_add_topo, mock_mpl, mock_plt):
        """Test common_plot with all features enabled."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        mock_plt.get_cmap.return_value = MagicMock()
        mock_plt.contourf.return_value = MagicMock()
        
        args = {
            'plot': None,
            'kind': 'contour',
            'fewcols': True,
            'working_dir': '.',
            'colormap': 'viridis'
        }
        dat = {
            'x': np.arange(10),
            'y': np.arange(10),
            'z': np.random.rand(10, 10)
        }
        topo = {
            'x': np.arange(10),
            'y': np.arange(10),
            'z': np.random.rand(10, 10) * 100
        }
        dots = np.random.rand(10, 10)
        mark = {'x': [5], 'y': [5]}
        
        mock_building = MagicMock()
        mock_building.x = 3
        mock_building.y = 3
        mock_building.a = 2
        mock_building.b = 2
        mock_building.w = 0
        
        _plotting.common_plot(
            args, dat,
            unit='m/s',
            topo=topo,
            dots=dots,
            buildings=[mock_building],
            mark=mark,
            scale=(0, 1)
        )
        
        mock_plt.contourf.assert_called()
        mock_add_topo.assert_called_once()
        mock_add_mark.assert_called_once()
        mock_ax.add_patch.assert_called()


if __name__ == '__main__':
    unittest.main()
