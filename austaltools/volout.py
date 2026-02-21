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
    import matplotlib.colors as mcolors
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

def face_lighting(grid, light=None, base_color='steelblue', ambient=0.3):
    """
    Build a flat (N_faces, 4) RGBA array for simulated directional lighting,
    compatible with the facecolors argument of ax.voxels().

    ax.voxels() lays out faces in the order:
        -x, +x, -y, +y, -z, +z  (6 groups, each of size n_filled voxels)

    :param grid: boolean or 0/1 ndarray, shape (ni, nj, nk)
    :param light: light direction vector (x, y, z); defaults to [1, 1, 2]
    :param base_color: any matplotlib color string
    :param ambient: minimum brightness for faces pointing away from light [0..1]
    :returns: (N_faces, 4) float32 RGBA array
    """
    if light is None:
        light = np.array([1.0, 1.0, 2.0])
    light = np.asarray(light, dtype=float)
    light = light / np.linalg.norm(light)

    # face order used internally by ax.voxels
    normals = [[-1, 0, 0], [1, 0, 0],
               [0, -1, 0], [0, 1, 0],
               [0, 0, -1], [0, 0, 1]]

    base_rgb = np.array(mcolors.to_rgb(base_color))
    n_filled = int(grid.astype(bool).sum())

    colors = []
    for normal in normals:
        diffuse = max(0.0, np.dot(light, normal))
        factor = ambient + (1.0 - ambient) * diffuse
        rgba = np.append(base_rgb * factor, 0.9)
        colors.append(np.tile(rgba, (n_filled, 1)))

    # concatenate: (face0_vox0..voxN, face1_vox0..voxN, ...) → (6*n_filled, 4)
    return np.concatenate(colors, axis=0).astype(np.float32)

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

    hh = np.asarray(hh, dtype=float)
    ni, nj, nk = grid.shape
    filled = np.argwhere(grid == 1)

    if len(filled) == 0:
        logger.warning('Grid is entirely empty — nothing to plot.')
        return

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection='3d')

    # Build coordinate arrays for ax.voxels()
    # x, y are uniform; z follows hh (possibly irregular)
    x = xmin + np.arange(ni + 1) * delt
    y = ymin + np.arange(nj + 1) * delt

    # z edges: check if hh already has nk+1 entries (includes top edge)
    # or nk entries (lower edges only, need to append one more)
    if len(hh) == nk + 1:
        z = hh  # already cell edges
    elif len(hh) == nk:
        dz_last = hh[1] - hh[0] if nk > 1 else delt
        z = np.append(hh, hh[-1] + dz_last)  # append top edge
    else:
        raise ValueError(f"hh length {len(hh)} incompatible with nk={nk} "
                         f"(expected {nk} or {nk + 1})")

    # ax.voxels needs coordinate meshes of shape (ni+1, nj+1, nk+1)
    X, Y, Z = np.meshgrid(x, y, z, indexing='ij')


    facecolors = face_lighting(grid)

    ax.voxels(X, Y, Z, grid.astype(bool),
              facecolors=facecolors,
              edgecolors='navy',
              shade=False,       # disable matplotlib's own shading — we do it ourselves
              linewidth=0.75)

    ax.view_init(elev=30, azim=45)
    # ax.set_proj_type('ortho')
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_zlabel('Z')
    ax.set_title('Isometric Grid View')

    # --- zoom ---
    i_min, j_min, k_min = filled.min(axis=0)
    i_max, j_max, k_max = filled.max(axis=0)

    bx_min, bx_max = x[i_min], x[i_max + 1]
    by_min, by_max = y[j_min], y[j_max + 1]
    bz_min, bz_max = z[k_min], z[k_max + 1]

    if zoom == 'in':
        xmin_val, xmax_val = bx_min, bx_max
        ymin_val, ymax_val = by_min, by_max
        zmin_val, zmax_val = bz_min, bz_max
    elif zoom == 'center':
        cx, cy = xmin + ni * delt / 2.0, ymin + nj * delt / 2.0
        half_x = max(cx - bx_min, bx_max - cx)
        half_y = max(cy - by_min, by_max - cy)
        xmin_val, xmax_val = cx - half_x, cx + half_x
        ymin_val, ymax_val = cy - half_y, cy + half_y
        zmin_val, zmax_val = float(z[0]), bz_max
    else:  # 'out'
        xmin_val, xmax_val = float(x[0]), float(x[-1])
        ymin_val, ymax_val = float(y[0]), float(y[-1])
        zmin_val, zmax_val = float(z[0]), float(z[-1])

    ax.set_xlim(xmin_val, xmax_val)
    ax.set_ylim(ymin_val, ymax_val)
    ax.set_zlim(zmin_val, zmax_val)

    x_range = xmax_val - xmin_val
    y_range = ymax_val - ymin_val
    z_range = zmax_val - zmin_val if zmax_val != zmin_val else 1.0
    try:
        ax.set_box_aspect((x_range, y_range, z_range))
    except AttributeError:
        pass

    plt.tight_layout()

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

    plot_isometric(grid, xmin, ymin, delt, hh,
                   zoom=args.get('zoom', None))


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
    pars_wrs.add_argument('-z', '--zoom',
                          dest = 'zoom',
                          default='in',
                          choices=['in', 'center', 'out'],
                          help=r'Zoom level for plotting: \n'
                               r'  - "out": view full grid\n'
                               r'  - "center": zoom to grid center\n'
                               r'  - "in": zoom closest to buildings\n'
                               r'Defaults to [%(default)s])].')
