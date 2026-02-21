#!/bin/env python3
# -*- coding: utf-8 -*-
"""
This module ...
"""
import logging
import os
import sys

import numpy as np
import pandas as pd
import readmet.dmna

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import matplotlib as mpl
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from . import _dispersion
from . import _corine
from . import _plotting
from . import _tools
from ._metadata import __version__
from . import _windutil

logger = logging.getLogger(__name__)
if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    logging.getLogger('readmet.dmna').setLevel(logging.ERROR)

# -------------------------------------------------------------------------


def plot_isometric(grid, xmin, ymin, delt, hh,
                   zoom=None):
    """
    Plot isometric view of a 3D binary grid.

    :param grid: 3D ndarray of 0s and 1s, shape (ni, nj, nk)
    :type grid: np.ndarray
    :param xmin: x origin
    :type xmin: float
    :param ymin: y origin
    :type ymin: float
    :param delt: grid spacing in x and y
    :type delt: float
    :param hh:   1D array of z-levels, length nk
    :type hh: np.ndarray | list
    :param zoom:
        zoom to
        - `out`: show full grid
        - 'center': keep center position, clip axes (symetrically) to max building extent
        - `in`: show only space filled with buildings
    """
    if zoom is None:
        zoom = 'out'

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')

    ni, nj, nk = grid.shape

    # Precompute all voxel faces for filled cells
    verts_list = []
    filled = np.argwhere(grid == 1)

    for (i, j, k) in filled:
        x0 = xmin + i * delt
        x1 = x0 + delt
        y0 = ymin + j * delt
        y1 = y0 + delt
        z0 = hh[k]
        z1 = hh[k + 1] if k + 1 < nk else hh[k] + (
            hh[1] - hh[0] if nk > 1 else delt)

        # 6 faces of the voxel cube
        faces = [
            [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0]],
            # bottom
            [[x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]],
            # top
            [[x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1]],
            # front
            [[x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1]],
            # back
            [[x0, y0, z0], [x0, y1, z0], [x0, y1, z1], [x0, y0, z1]],
            # left
            [[x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1]],
            # right
        ]
        verts_list.extend(faces)

    if verts_list:
        poly = Poly3DCollection(
            verts_list,
            facecolor='steelblue',
            edgecolor='navy',
            alpha=0.7,
            linewidth=0.3
        )
        ax.add_collection3d(poly)

    # Isometric-style view angle
    ax.view_init(elev=30, azim=45)
    ax.set_proj_type('ortho')  # true isometric (no perspective distortion)

    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_zlabel('Z')
    ax.set_title('Isometric Grid View')

    # Auto-scale axes
    # if zoom == 'out':
    if True:
        ax.auto_scale_xyz(
            [xmin, xmin + ni * delt],
            [ymin, ymin + nj * delt],
            [hh[0], hh[-1]]
        )
    # else ...

    plt.tight_layout()
    return

    # # --- Example usage ---
    # ni, nj, nk = 10, 10, 5
    # grid = (np.random.rand(ni, nj, nk) > 0.7).astype(int)
    #
    # xmin, ymin, delt = 0.0, 0.0, 1.0
    # hh = np.array([0.0, 1.0, 2.5, 4.0, 6.0])  # irregular z-levels

def main(args):
    """
    This is the main working function

    :param args: the command line arguments as dictionary
    :type args: dict
    """
    logger.debug(format(args))

    working_dir = args.get('working_dir', '.')

    # determine output
    plotfile = _plotting.consolidate_plotname(args['plot'],'volout.png')

    grid_no = int(args['grid'])
    volfile = os.path.join(working_dir, f'volout{grid_no:02d}.dmna')
    volume = readmet.dmna.DataFile(volfile)
    xmin = float(volume.header['xmin'])
    ymin = float(volume.header['ymin'])
    delt = float(volume.header['delt'])
    hh = [float(x) for x in volume.header['hh'].split()]
    grid = volume.data['']

    plot_isometric(grid, xmin, ymin, delt, hh)


    if plotfile == "__show__":
        logger.info('showing plot')
        plt.show()
    else:
        if os.path.sep in plotfile:
            outname = plotfile
        else:
            outname = os.path.join(args["working_dir"], plotfile)
        if not outname.endswith('.png'):
            outname = outname + '.png'
        logger.info('writing plot: %s' % outname)
        plt.savefig(outname, dpi=180)

# ----------------------------------------------------

def add_options(subparsers):

    pars_wrs = subparsers.add_parser(
        name='volout',
        help='Plot building volumes',
        formatter_class=_tools.SmartFormatter,
    )
    pars_wrs.add_argument('-k', '--kind',
                          dest='style',
                          choices=['default'],
                          default='default',
                          help='style of volume plot [%(default)s])]')
    pars_wrs.add_argument('-p', '--plot',
                        metavar="FILE",
                        nargs='?',
                        const='__default__',
                        help='save plot to a file. If `FILE` is "-" ' +
                             'the plot is shown on screen. If `FILE` is ' +
                             'missing, the file name defaults to ' +
                             'the data file name with extension `png`'
                        )
    pars_wrs_vol = pars_wrs.add_mutually_exclusive_group()
    pars_wrs_vol.add_argument('-g', '--grid',
                          dest='grid',
                          default=1,
                          help='Number of the grid for which to plot '
                               'the building volumes [%(default)s])].')
    pars_wrs_vol.add_argument('-f', '--file',
                              dest = 'file',
                              default = None,
                              help = 'Name of the file to read '
                                     '[%(default)s])].')
