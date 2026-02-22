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

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import matplotlib as mpl
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    from matplotlib.colors import LightSource
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)

    import readmet

from . import _dispersion
from . import _corine
from . import _plotting
from . import _tools
from ._metadata import __version__
from . import _windutil

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------------

def is_valid_color(c):
    try:
        mcolors.to_rgba(c)
        return True
    except ValueError:
        return False

# -------------------------------------------------------------------------

def contrasting_shade(color, factor=0.4):
    """
    Return a darker or lighter shade of the same hue that
    contrasts with the input.

    If the color is light (luminance > 0.5), returns a darker shade.
    If the color is dark, returns a lighter shade.

    :param color: any matplotlib color specification
    :param factor: how far to shift the lightness (0..1)
    :returns: RGBA tuple
    """
    r, g, b, a = mcolors.to_rgba(color)
    # perceived luminance
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    if luminance > 0.5:
        r2, g2, b2 = (max(0.0, r * (1 - factor)),
                      max(0.0, g * (1 - factor)),
                      max(0.0, b * (1 - factor)))
    else:
        r2 = r + (1 - r) * factor
        g2 = g + (1 - g) * factor
        b2 = b + (1 - b) * factor
    return (r2, g2, b2, a)

# -------------------------------------------------------------------------

def plot_voxels(grid: np.ndarray,
                xmin: float, ymin: float, delt: float, hh: np.ndarray|list,
                color: tuple[str] | None = None,
                camera: tuple[float] | None = None,
                zoom: float | None = None,
                clip: str | None = None):
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
    :param camera: plot view from azimuth
      (geodetic, clockwise from north)
      and elevation (upward) angle
    :type camera: tuple[float]
    :param zoom: zoom focal length (1 = 90° viewing angle) or None
      for isometric plot
    :type zoom: float | None
    :param clip:
        zoom to
        - `out`: show full grid
        - 'center': keep center position, clip axes (symetrically) to max building extent
        - `in`: show only space filled with buildings
    :type clip: str | None
    """
    if clip is None:
        clip = 'no'
    if camera is None:
        camera = (45, 40)
    if color is None:
        color = ('tan', 'chocolate')

    hh = np.asarray(hh, dtype=float)
    ni, nj, nk = grid.shape
    filled = np.argwhere(grid == 1)

    if len(filled) == 0:
        logger.warning('Grid is entirely empty — nothing to plot.')
        return

    if isinstance(color, str):
        color = color.strip('()').replace(',', ' ').split()
    if not 1 <= len(color) <= 2:
        raise ValueError(f"One or two colors must be given, "
                         f"found {len(color)}")
    rgb = list()  # ensure mutable
    for i, c in enumerate(color):
        if is_valid_color(c):
            rgb.append(mcolors.to_rgba(c))
        else:
            raise ValueError(f"Invalid color: {c}")
    if len(color) < 2:
        rgb.append(contrasting_shade(color[0]))

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


    light_azi = (camera[0] + 135) % 360 # geodetic, clockwise from north
    light_ele = 45
    logger.debug("light: azi = %s , ele = %s" %
                 (light_azi, light_ele))
    ls = LightSource(light_azi, light_ele)  # azdeg, altdeg

    ax.voxels(X, Y, Z, grid.astype(bool),
              facecolors=rgb[0],
              edgecolors=rgb[1],
              shade=True,  # we handle shading ourselves
              lightsource=ls,
              linewidth=0.75)

    ax.view_init(elev=camera[1],
                 azim=(90 - camera[0]) % 360) # math, anticlockw. fr. east
    if zoom:
        ax.set_proj_type('persp', focal_length=float(zoom))
    else:
        ax.set_proj_type('ortho')
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_zlabel('Z')
    # ax.set_title('Isometric Grid View')

    # --- zoom ---
    i_min, j_min, k_min = filled.min(axis=0)
    i_max, j_max, k_max = filled.max(axis=0)

    bx_min, bx_max = x[i_min], x[i_max + 1]
    by_min, by_max = y[j_min], y[j_max + 1]
    bz_min, bz_max = z[k_min], z[k_max + 1]

    if clip == 'fit':
        xmin_val, xmax_val = bx_min, bx_max
        ymin_val, ymax_val = by_min, by_max
        zmin_val, zmax_val = bz_min, bz_max
    elif clip == 'center':
        cx, cy = xmin + ni * delt / 2.0, ymin + nj * delt / 2.0
        half_x = max(cx - bx_min, bx_max - cx)
        half_y = max(cy - by_min, by_max - cy)
        xmin_val, xmax_val = cx - half_x, cx + half_x
        ymin_val, ymax_val = cy - half_y, cy + half_y
        zmin_val, zmax_val = float(z[0]), bz_max
    else:  # 'no'
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

# -------------------------------------------------------------------------

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

    angle = args.get('angle', 'SW')
    if isinstance(angle, str):
        if angle.upper() in ['N', 'E', 'S', 'W']:
            if angle.upper() == 'N':
                azi_from = 0
            elif angle.upper() == 'E':
                azi_from = 90
            elif angle.upper() == 'S':
                azi_from = 180
            else:
                azi_from = 270
            ele_from = 0
            zoom = None
        elif angle.upper() in ['NE', 'SW', 'SE', 'NW']:
            if angle.upper() == 'NE':
                azi_from = 45
            elif angle.upper() == 'SE':
                azi_from = 135
            elif angle.upper() == 'SW':
                azi_from = 225
            else:
                azi_from = 315
            ele_from = 40
            zoom = None
        else:
            # remove parentheses if a litteral tuple is given
            angle = angle.strip("()")
            # string representing a number or tuple of numbers
            # e.g. "225", "225,40", "225,40,0.5"
            try:
                parts = [float(v)
                         for v in angle.replace(',', ' ').split()]
            except ValueError:
                raise ValueError(f"Unrecognised angle value: {angle!r}")
            if len(parts) == 1:
                azi_from = parts[0]
                ele_from = 40
                zoom = 1
            elif len(parts) == 2:
                azi_from = parts[0]
                ele_from = parts[1]
                zoom = 1
            elif len(parts) == 3:
                azi_from = parts[0]
                ele_from = parts[1]
                zoom = parts[2]
            else:
                raise ValueError(f"Angle string must have 1–3 values, "
                                 f"got: {angle!r}")
    elif isinstance(angle, (int, float)):
        azi_from = angle
        ele_from = 40
        zoom = 1
    elif isinstance(angle, (list, tuple)):
        if len(angle) == 2:
            azi_from = angle[0]
            ele_from = angle[1]
            zoom = 1
        elif len(angle) == 3:
            azi_from = angle[0]
            ele_from = angle[1]
            zoom = angle[2]
    else:
        raise ValueError(f"Angle must be string or float or tuple, "
                         f"not {type(angle)}")

    camera = ( float(azi_from) , float(ele_from))
    logger.debug("camera: azi = %s, ele = %s" %
                 (camera[0], camera[1]))
    clip = args.get('clip', None)
    logger.debug("clip = %s" % clip)
    logger.debug("zoom = %s" % zoom)
    color = args.get('color', None)
    logger.debug("color = %s" % color)
    plot_voxels(grid, xmin, ymin, delt, hh,
                camera=camera,
                clip=clip,
                color=color,
                zoom=zoom)


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
    pars_wrs.add_argument('-c', '--clip',
                          dest = 'clip',
                          default='fit',
                          choices=['fit', 'center', 'no'],
                          help=r'Zoom level for plotting: \n'
                               r'  - "no": view full grid\n'
                               r'  - "center": zoom to grid center\n'
                               r'  - "fit": zoom closest to buildings\n'
                               r'Defaults to [%(default)s])].')
    pars_wrs.add_argument('-a', '--angle',
                          dest = 'angle',
                          default = 'SW',
                          help=r"viewing angle:\n"
                               r"  - `N`, `E`, `S`, `W`: side view"
                               r" from north, east, south, west\n"
                               r"  - `NW`, `SW`, `SE`, `NE`: isometric"
                               r" view from ... \n"
                               r"  - 0...360: Perspective view from "
                               r" direction (geographic degrees,"
                               r" clockwise from north)\n"
                               r"  - AZI,ELE[,FL]: comma-sepatrated tuple"
                               r" of view-from direction and elevation, "
                               r" and optionally focal length "
                               r" (focal length of 1.0 corresponds to"
                               r" 90° field of view, defaults to 0.5 if"
                               r" absent)\n"
                               r"Default is [%(default)s])].")
    pars_wrs.add_argument_group('advanced options')
    pars_wrs.add_argument('--color',
                          dest='color',
                          default='sienna',
                          help="color of the buidlings as\n"
                               "  - color name or html color code"
                               " (a darker shade is used"
                               " for the edges\n"
                               "  - two comma-separated color names or"
                               " html color codes"
                               " (used for sides and egdes)\n"
                               "Html color codes in the form #rrggbb. "
                               "Defaults to [%(default)s])].")