#!/bin/env python3
# -*- coding: utf-8 -*-
"""
This module implements the ``windprofile`` subcommand, which plots a
vertical profile of wind speed and wind direction at a given position
in the AUSTAL model domain. It is deliberately kept as similar as
possible to the ``windfield`` subcommand (same wind-library handling,
same wind-reference selection), but instead of a horizontal or
vertical *slice* through the wind field it extracts and plots the
full vertical column (speed and direction vs. height) at one point.
"""
import logging
import os
import re

import numpy as np
import pandas as pd

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':

    import readmet
    import meteolib

from . import _dispersion
from . import _geo
from . import _plotting
from . import _tools
from ._metadata import __version__
from . import _windutil

logger = logging.getLogger(__name__)

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    logging.getLogger('readmet.dmna').setLevel(logging.ERROR)

# -------------------------------------------------------------------------

#: number of grid rows outside the model domain that is still tolerated
#: (with a warning). Beyond this, an error is raised.
MAX_ROWS_OUTSIDE = 2

# -------------------------------------------------------------------------


# NOTE: position resolution (model coordinates vs. location options,
# and looking up the AUSTAL model origin to convert between the two)
# used to be implemented locally in this module. It has been moved to
# `_geo.py` (as `_geo.resolve_position` / `_geo.model_origin`), since
# `transform.py` needs the same lookup. Both are private utility
# modules, so importing `_geo` here does not introduce a dependency
# between sibling subcommand modules -- see `_tools.superpose` for the
# same reasoning. Station-based positions (`-D`/`-W`) are not offered
# by `windprofile`'s own parser (see `add_options` below), since `-W`
# is used (matching `windfield`) for the wind reference vector; this
# does not affect `_geo.resolve_position`, which simply finds no such
# option set.

# -------------------------------------------------------------------------


def _axis_status(value: float, axis, name: str):
    """
    Classify a coordinate value with respect to one grid axis.

    :param value: the coordinate value to check
    :type value: float
    :param axis: the grid axis (cell-center coordinates), ascending
    :type axis: list|np.ndarray
    :param name: name of the axis, used in messages (e.g. ``'x'``)
    :type name: str
    :return: severity (``'ok'``, ``'warn'`` or ``'error'``) and, if
        not ``'ok'``, a human-readable message
    :rtype: (str, str)
    """
    axis = np.asarray(axis, dtype=float)
    lo, hi = float(axis[0]), float(axis[-1])
    step = abs(float(axis[1] - axis[0])) if len(axis) > 1 else 0.
    if value < lo:
        dist = lo - value
    elif value > hi:
        dist = value - hi
    else:
        dist = 0.
    at_edge = np.isclose(value, lo) or np.isclose(value, hi)
    rows = dist / step if step > 0 else 0.
    if rows > MAX_ROWS_OUTSIDE:
        return 'error', (
            f'{name} = {value:.1f} m is {rows:.1f} grid rows outside '
            f'the model domain ({lo:.1f} ... {hi:.1f} m)')
    elif rows > 0. or at_edge:
        return 'warn', (
            f'{name} = {value:.1f} m is at or outside the edge of '
            f'the model domain ({lo:.1f} ... {hi:.1f} m)')
    else:
        return 'ok', ''

# -------------------------------------------------------------------------


def check_position(x: float, y: float, axes: dict):
    """
    Check a requested profile position against the model domain and
    raise or log as appropriate.

    :param x: requested position, model x coordinate in m
    :type x: float
    :param y: requested position, model y coordinate in m
    :type y: float
    :param axes: grid axes as returned by
        :func:`austaltools._tools.read_wind` (keys ``'x'``, ``'y'``)
    :type axes: dict
    :raises ValueError: if the position is more than
        :data:`MAX_ROWS_OUTSIDE` grid rows outside the model domain
        (in x or y direction)
    """
    errors = []
    warnings = []
    for name, value, axis in [('x', x, axes['x']), ('y', y, axes['y'])]:
        level, msg = _axis_status(value, axis, name)
        if level == 'error':
            errors.append(msg)
        elif level == 'warn':
            warnings.append(msg)
    if errors:
        raise ValueError('; '.join(errors))
    for msg in warnings:
        logger.warning(msg)

# -------------------------------------------------------------------------


def _read_reference_ascii(path: str
                          ) -> (np.ndarray, np.ndarray, np.ndarray):
    """
    Read a reference wind profile from a plain ASCII file.

    The file is expected to contain (whitespace- or comma-separated)
    three columns: height above ground in m, wind speed in m/s, and
    wind direction in degrees. Any number of leading (or interspersed)
    lines that do not parse as three numeric values -- such as a
    header line with column names or units, or comment lines -- are
    skipped automatically; no fixed number of header lines needs to be
    given.

    :param path: file name of the reference profile
    :type path: str
    :return: height (m), wind speed (m/s), wind direction (deg),
        sorted by height
    :rtype: (np.ndarray, np.ndarray, np.ndarray)
    :raises ValueError: if no data lines could be parsed from the file
    """
    heights = []
    speeds = []
    dirs = []
    with open(path, 'r') as f:
        for lineno, line in enumerate(f, 1):
            stripped = line.strip()
            if stripped == '' or stripped.startswith('#'):
                continue
            fields = re.split(r'[,\s]+', stripped)
            try:
                z, ff, dd = (float(x) for x in fields[:3])
            except (ValueError, IndexError):
                logger.debug('skipping non-data line %d in %s: %s' %
                             (lineno, path, line.rstrip()))
                continue
            heights.append(z)
            speeds.append(ff)
            dirs.append(dd)
    if not heights:
        raise ValueError('no data found in reference profile file: %s' %
                         path)
    order = np.argsort(heights)
    heights = np.array(heights)[order]
    speeds = np.array(speeds)[order]
    dirs = np.array(dirs)[order] % 360.
    return heights, speeds, dirs

# -------------------------------------------------------------------------

#: units (lower-case) accepted as marking a Scintec1 variable as a wind
#: speed or wind direction column, respectively, when auto-detecting
#: which variable is which (see `_read_reference_scintec1`)
_SCINTEC_SPEED_UNITS = {'m/s'}
_SCINTEC_DIR_UNITS = {'deg', 'degree', 'degrees', 'grad', '°'}
#: label substrings (lower-case) that exclude a variable from being
#: picked as the plain wind speed/direction (e.g. a standard deviation
#: or error/quality variable that happens to share the same unit)
_SCINTEC_EXCLUDE_LABELS = ('sigma', 'std', 'deviation', 'error', 'quality')


def _read_reference_scintec1(path: str, target_time=None
                             ) -> (np.ndarray, np.ndarray, np.ndarray):
    """
    Read a reference wind profile from a Scintec FORMAT-1/1.1 sodar
    file (see :mod:`readmet.scintec1`).

    Such a file can hold many timestamped profile scans; one of them
    is picked as described for `target_time`. The wind speed and wind
    direction variables are identified among the file's own
    (device-/configuration-dependent) variable symbols by their unit
    (``m/s`` for speed, degrees for direction), excluding variables
    whose label looks like a standard deviation, error or quality
    variable.

    :param path: file name of the Scintec1 reference profile
    :type path: str
    :param target_time: if given, the profile scan closest to this
        time is used; if omitted, the last scan in the file is used
    :type target_time: datetime-like, optional
    :return: height (m), wind speed (m/s), wind direction (deg),
        sorted by height
    :rtype: (np.ndarray, np.ndarray, np.ndarray)
    :raises ValueError: if the file has no profile data, or if the
        wind speed or wind direction variable cannot be identified
        unambiguously among the file's variables
    """
    data = readmet.scintec1.DataFile(path)
    if not data.profile:
        raise ValueError('no profile data found in Scintec file: %s' %
                         path)

    def _find_variable(units, kind):
        candidates = []
        for sym in data.profile.keys():
            if sym not in data.vars.index:
                continue
            unit = str(data.vars.loc[sym, 'unit']).strip().lower()
            label = str(data.vars.loc[sym, 'label']).strip().lower()
            if unit not in units:
                continue
            if any(x in label for x in _SCINTEC_EXCLUDE_LABELS):
                continue
            candidates.append(sym)
        if len(candidates) == 0:
            raise ValueError(
                f'could not identify a wind {kind} variable (by unit) '
                f'in Scintec file: {path}')
        elif len(candidates) > 1:
            raise ValueError(
                f'found several candidate wind {kind} variables '
                f'({", ".join(candidates)}) in Scintec file: {path}; '
                f'cannot pick one automatically')
        return candidates[0]

    speed_sym = _find_variable(_SCINTEC_SPEED_UNITS, 'speed')
    dir_sym = _find_variable(_SCINTEC_DIR_UNITS, 'direction')

    speed_df = data.profile[speed_sym]
    dir_df = data.profile[dir_sym].reindex(columns=speed_df.columns)

    if target_time is not None:
        target_time = pd.to_datetime(target_time)
        # NOTE: deliberately not `.to_series().argsort()[0]` (an idiom
        # used elsewhere in this codebase, e.g. windfield.py's own
        # `-t` handling): `argsort()` on a Series keeps the original
        # (here: TimedeltaIndex) as its index rather than a plain
        # positional one, so `[0]` becomes a *label* lookup and raises
        # on current pandas unless a literal zero-length timedelta
        # happens to be present. `np.argmin` on the plain array avoids
        # the ambiguity by returning an unambiguous integer position.
        pos = int(np.argmin(np.abs((speed_df.index -
                                    target_time).to_numpy())))
        idx = speed_df.index[pos]
        logger.info('Scintec reference profile: using scan at %s '
                   '(nearest to %s)' % (idx, target_time))
    else:
        idx = speed_df.index[-1]
        logger.info('Scintec reference profile: using last scan at %s' %
                   idx)

    heights = np.array(speed_df.columns, dtype=float)
    speeds = speed_df.loc[idx].to_numpy(dtype=float)
    dirs = dir_df.loc[idx].to_numpy(dtype=float)

    order = np.argsort(heights)
    heights = heights[order]
    speeds = speeds[order]
    dirs = dirs[order] % 360.
    return heights, speeds, dirs

# -------------------------------------------------------------------------


def _read_reference_hpl(path: str) -> (np.ndarray, np.ndarray, np.ndarray):
    """
    Read a reference wind profile from a Halo Photonics lidar
    "Processed Wind Profile" ``.hpl`` file (see :mod:`readmet.hpl`).

    :param path: file name of the HPL reference profile
    :type path: str
    :return: height (m), wind speed (m/s), wind direction (deg),
        sorted by height
    :rtype: (np.ndarray, np.ndarray, np.ndarray)
    :raises ValueError: if `path` is a regular (per-ray) ``.hpl`` scan
        file rather than a "Processed Wind Profile" file
    """
    data = readmet.hpl.DataFile(path)
    if data.profile is None:
        raise ValueError('not an HPL "Processed Wind Profile" file '
                         '(looks like a regular scan file): %s' % path)
    profile = data.profile.sort_index()
    heights = profile.index.to_numpy(dtype=float)
    speeds = profile['speed'].to_numpy(dtype=float)
    dirs = profile['direction'].to_numpy(dtype=float) % 360.
    return heights, speeds, dirs

# -------------------------------------------------------------------------


def read_reference_profile(path: str, target_time=None
                           ) -> (np.ndarray, np.ndarray, np.ndarray):
    """
    Read a reference wind profile, auto-detecting its file format:

    - a Scintec FORMAT-1 or FORMAT-1.1 sodar file (recognised by its
      first line, the format's own magic string), see
      :func:`_read_reference_scintec1`;
    - a Halo Photonics lidar "Processed Wind Profile" file (recognised
      by its first line being a single bare integer, the header-less
      format's level count), see :func:`_read_reference_hpl`; a
      regular (per-ray) ``.hpl`` scan file is not a reference profile
      and raises a clear error instead of being misread;
    - otherwise, a plain ASCII file (see :func:`_read_reference_ascii`).

    :param path: file name of the reference profile
    :type path: str
    :param target_time: for a Scintec1 file (which can hold many
        timestamped scans), the scan closest to this time is used; if
        omitted, the last scan in the file is used. Ignored for the
        other formats, which hold a single profile.
    :type target_time: datetime-like, optional
    :return: height (m), wind speed (m/s), wind direction (deg),
        sorted by height
    :rtype: (np.ndarray, np.ndarray, np.ndarray)
    :raises IOError: if `path` does not exist
    :raises ValueError: if no data lines could be parsed from the file
    """
    if not os.path.exists(path):
        raise IOError('reference profile file not found: %s' % path)

    with open(path, 'r') as f:
        first_line = f.readline().rstrip('\n')
    first_stripped = first_line.strip()

    if first_stripped in ('FORMAT-1', 'FORMAT-1.1'):
        logger.info('reference profile %s: detected Scintec %s format' %
                   (path, first_stripped))
        return _read_reference_scintec1(path, target_time=target_time)

    # a header-less HPL "Processed Wind Profile" file starts with a
    # single bare integer (the number of levels); try it, and fall
    # back to plain ASCII if that doesn't pan out
    tokens = first_stripped.split()
    if len(tokens) == 1:
        try:
            int(tokens[0])
        except ValueError:
            pass
        else:
            try:
                logger.debug('reference profile %s: first line looks '
                             'like an HPL "Processed Wind Profile" '
                             'level count, trying that format' % path)
                return _read_reference_hpl(path)
            except Exception as e:
                logger.debug('reference profile %s: not a usable HPL '
                             'profile (%s), falling back to plain '
                             'ASCII' % (path, e))

    if path.lower().endswith('.hpl') and ':' in first_line:
        raise ValueError(
            'file looks like a regular (per-ray) HPL scan file; only '
            'the "Processed Wind Profile" export is supported as a '
            'reference profile: %s' % path)

    logger.debug('reference profile %s: assuming plain ASCII format' %
                path)
    return _read_reference_ascii(path)

# -------------------------------------------------------------------------


def _break_wrap(x, y):
    """
    Insert ``NaN`` values into a line where consecutive x-values
    (wind directions) jump by more than 180 degrees, so that a line
    plot does not draw a spurious connection across the 0/360 degree
    wrap-around.

    :param x: values to plot on the x-axis (e.g. wind direction, deg)
    :type x: array-like
    :param y: values to plot on the y-axis (e.g. height, m)
    :type y: array-like
    :return: x, y with ``NaN`` rows inserted at wrap-around points
    :rtype: (np.ndarray, np.ndarray)
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) == 0:
        return x, y
    xb = [x[0]]
    yb = [y[0]]
    for i in range(1, len(x)):
        if abs(x[i] - x[i - 1]) > 180.:
            xb.append(np.nan)
            yb.append(np.nan)
        xb.append(x[i])
        yb.append(y[i])
    return np.array(xb), np.array(yb)

# -------------------------------------------------------------------------


def main(args):
    """
    This is the main working function

    :param args: The command line arguments as a dictionary, with keys:

      - ``working_dir``: The working directory where files are located
        (i.e. where ``austal.txt`` is stored). Defaults to
        ``_tools.DEFAULT_WORKING_DIR`` if missing or ``None``.
      - ``grid``: number of grid to plot. Defaults to ``0`` if missing
        or ``None``.
      - ``xy``: model coordinates ``[x, y]`` of the profile position,
        in m east-/northward of the model origin. Mutually exclusive
        with the location options below.
      - ``ll``, ``gk``, ``ut``, ``dwd``, ``wmo``: location of the
        profile position, as added by
        :func:`austaltools._tools.add_location_opts`. Mutually
        exclusive with ``xy`` and with each other.
      - ``time``, ``wind``, ``vector``: mutually exclusive; select the
        reference wind by timestamp (looked up in the AKTERM data),
        by (speed, direction, stability class), or by (u, v, stability
        class), respectively. All default to ``None`` if missing.
        Required: raises ``ValueError`` if none of the three is given.
      - ``z0``: roughness length overriding the value from the data
        source. Defaults to ``None`` if missing.
      - ``reference``: file name of a reference wind profile to
        overplot. Its format (plain ASCII, Scintec FORMAT-1/1.1 sodar,
        or Halo Photonics lidar "Processed Wind Profile") is detected
        automatically; see :func:`read_reference_profile`. Defaults to
        ``None`` if missing (no reference profile is shown).
      - ``plot``: The plot file name. Defaults to ``'windprofile.png'``
        if missing or ``None``.

    :type args: dict

    :raises ValueError: If none of ``time``, ``wind``, or ``vector``
      is given, if ``time`` is more than an hour away from the nearest
      available data, if the profile position is not given (or given
      twice), or if the profile position is more than
      :data:`MAX_ROWS_OUTSIDE` grid rows outside the model domain.
    """
    logger.debug(format(args))

    try:
        import matplotlib
        if os.name == 'posix' and "DISPLAY" not in os.environ:
            matplotlib.use('Agg')
            have_display = False
        else:
            have_display = True
        import matplotlib.pyplot as plt
        logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
    except ImportError:
        have_display = False
        matplotlib = None
        plt = None

    working_dir = args.get("working_dir", None)
    if working_dir is None:
        working_dir = _tools.DEFAULT_WORKING_DIR
    grid = args.get("grid", None)
    if grid is None:
        grid = 0
    grid = int(grid)
    plotfile = _plotting.consolidate_plotname(args.get('plot', None),
                                              'windprofile.png')
    #
    conf = _tools.get_austxt(_tools.find_austxt(working_dir))

    # position of the requested profile (model coordinates)
    x_pos, y_pos = _geo.resolve_position(args, conf=conf)

    # get reference wind
    vector = args.get('vector', None)
    wind = args.get('wind', None)
    time_arg = args.get('time', None)
    # if a timestamp was used to select the wind reference, reuse it
    # (see below) to pick the closest scan from a multi-time Scintec1
    # reference profile file, if one is given
    ref_time = None
    if vector:
        u, v, ak = [float(x) for x in vector]
    elif wind:
        ff, dd, ak = [float(x) for x in wind]
        u, v = meteolib.wind.dir2uv(ff, dd)
    elif time_arg:
        timestamp = pd.to_datetime(time_arg)
        ref_time = timestamp
        az = _windutil.load_weather(working_dir, conf)
        # see the NOTE in `_read_reference_scintec1` on why this isn't
        # the `.to_series().argsort()[0]` idiom used in windfield.py
        nearest_pos = int(np.argmin(np.abs(
            (az.index - timestamp).to_numpy())))
        time = az.index[nearest_pos]
        if abs(time - timestamp) > pd.Timedelta('1H'):
            raise ValueError('time outside data: %s' % str(timestamp))
        else:
            logger.info('using data from: %s' % str(timestamp))
        ff = az['FF'][time]
        dd = az['DD'][time]
        ak = az['KM'][time]
        u, v = meteolib.wind.dir2uv(ff, dd)
    else:
        raise ValueError('no wind reference value defined')

    # AK (ak) in file and command line is 1-based,
    # ak0 is zero-based so it can be used as field index
    ak0 = int(ak) - 1
    akstr = _dispersion.KM2021.num2name(int(ak))
    logger.info(f"wind: {u:.1f}, {v:.1f}, stability class: {akstr}")
    #
    # read the wind library data
    #
    lib_dir = _tools.wind_library(working_dir)
    file_info = _tools.wind_files(lib_dir)
    directions = [float(x) * 10.
                  for x in sorted(list(set(file_info["wdir"])))]
    u_grid, v_grid, axes = _tools.read_wind(file_info, path=lib_dir,
                                     grid=grid, centers=True)
    ha = _windutil.read_heff(working_dir, conf=conf, z0=args.get('z0', None))
    xa = conf.get('xa', 0)
    ya = conf.get('ya', 0)

    # _grid indices: nx, ny, nz, nstab, ndir
    u_field, v_field = _tools.superpose(u_grid, v_grid, axes, directions,
                                        u, v, xa, ya, ha, ak0)

    logger.info('profile position: x=%.1f, y=%.1f' % (x_pos, y_pos))
    check_position(x_pos, y_pos, axes)

    ix = int(np.argmin(np.abs(np.array(axes['x']) - x_pos)))
    iy = int(np.argmin(np.abs(np.array(axes['y']) - y_pos)))

    heights = np.array(axes['z'])
    u_profile = u_field[ix, iy, :]
    v_profile = v_field[ix, iy, :]
    speed, wdir = meteolib.wind.uv2dir(u_profile, v_profile)

    reference = args.get('reference', None)
    if reference:
        ref_h, ref_ff, ref_dd = read_reference_profile(
            reference, target_time=ref_time)
    else:
        ref_h = ref_ff = ref_dd = None

    altitude_flag = args.get('altitude', False)
    ground_elev = 0.
    if altitude_flag:
        # try to load topography, same file naming as `windfield`
        if grid == 0:
            topo_path = os.path.join(working_dir, "zg00.dmna")
            topo_var = ""
        else:
            topo_path = os.path.join(working_dir,
                                     "lib/zg%01d1.dmna" % grid)
            topo_var = "zg"
        if os.path.exists(topo_path):
            logger.info('reading terrain from %s' % topo_path)
            topz = _tools.load_topo(topo_path, topo_var)[2]
            ground_elev = float(topz[ix, iy])
        else:
            if conf and "gh" in conf:
                logging.warning('file not found: %s' % topo_path)
            logger.warning('no topography: assuming zero elevation')
        heights = heights + ground_elev
        if ref_h is not None:
            ref_h = np.array(ref_h) + ground_elev

    #
    # plot
    #
    matplotlib.rcParams.update({'font.size': 16})
    fig, (ax_ff, ax_dd) = plt.subplots(ncols=2, sharey=True)
    fig.set_size_inches(11, 8)

    ax_ff.plot(speed, heights, marker='o', color='tab:blue',
              label='model')
    ax_ff.set_xlabel('wind speed [m/s]')
    if altitude_flag:
        ax_ff.set_ylabel('altitude [m]')
    else:
        ax_ff.set_ylabel('height above ground [m]')
    scale = args.get('scale', None)
    if scale:
        ax_ff.set_xlim(0, float(scale))
    else:
        ax_ff.set_xlim(left=0)
    ax_ff.grid(True, alpha=0.3)

    dd_plot, h_plot = _break_wrap(wdir, heights)
    ax_dd.plot(dd_plot, h_plot, marker='o', color='tab:blue',
              label='model')
    ax_dd.set_xlabel('wind direction [deg]')
    ax_dd.set_xlim(0, 360)
    ax_dd.set_xticks([0, 90, 180, 270, 360])
    ax_dd.grid(True, alpha=0.3)
    ax_dd.tick_params(axis='y', labelleft=False)

    if ref_h is not None:
        ax_ff.plot(ref_ff, ref_h, linestyle='--',
                  color='black', label='reference')
        ref_dd_plot, ref_h_plot = _break_wrap(ref_dd, ref_h)
        ax_dd.plot(ref_dd_plot, ref_h_plot, linestyle='--',
                  color='black', label='reference')
        ax_ff.legend(loc='best', fontsize=12)

    fig.suptitle('wind profile at x=%.0f m, y=%.0f m (%s)' %
                 (x_pos, y_pos, akstr))
    fig.tight_layout()
    # apply the small gap between the two panels only after tight_layout,
    # since sharey axes are not fully compatible with tight_layout's own
    # spacing computation
    fig.subplots_adjust(wspace=0.08)

    if plotfile == "__show__":
        logger.info('showing plot')
        plt.show()
    else:
        if os.path.sep in plotfile:
            outname = plotfile
        else:
            outname = os.path.join(working_dir, plotfile)
        if not outname.endswith('.png'):
            outname = outname + '.png'
        logger.info('writing plot: %s' % outname)
        plt.savefig(outname, dpi=180)

# ----------------------------------------------------


def add_options(subparsers):

    pars_wip = subparsers.add_parser(
        name='windprofile',
        help='Plot vertical profile of wind speed and direction'
    )
    pars_wip.add_argument('-g', '--grid',
                         default=0,
                         help='number of grid to plot. '
                              'Defaults to 0')

    pars_wip.add_argument('-M', '--model',
                         metavar=('X', 'Y'),
                         dest='xy',
                         nargs=2,
                         default=None,
                         help='position of the profile, given in model '
                              'coordinates `X` and `Y` (in m '
                              'east-/northward of the model '
                              'coordinate origin). Mutually exclusive '
                              'with the location options below.')
    # Note: `stations=True` is intentionally not used here: it would
    # add a `-W`/`--wmo` option, which collides with the `-W` used
    # below (matching `windfield`) for specifying the wind reference
    # as a vector. Station-based positions (`-D`/`-W`) are therefore
    # not available for `windprofile`; use `-L`, `-G`, `-U` or `-M`.
    pars_wip = _tools.add_location_opts(pars_wip, stations=False,
                                        required=False)

    wval = pars_wip.add_mutually_exclusive_group(required=True)
    wval.add_argument('-t', '--time',
                      dest='time',
                      metavar='"YYY-MM-DD HH:MM:SS"',
                      default=None,
                      help='display windprofile corresponding '
                           'to the wind and stability from akterm '
                           'for the time given by ``YYY-MM-DD HH:MM:SS``. '
                           'Defaults to `None`')
    wval.add_argument('-w', '--wind',
                      dest='wind',
                      metavar=('SPEED', 'DIR', 'AK'),
                      nargs=3,
                      default=None,
                      help='display windprofile corresponding '
                           'to the wind `SPEED`, `DIR`ection and '
                           'stability class `AK`. '
                           'Defaults to `None`')
    wval.add_argument('-W', '--wind-vector',
                      dest='vector',
                      metavar=('U', 'V', 'AK'),
                      nargs=3,
                      default=None,
                      help='display windprofile corresponding '
                           'to the wind vector (`U`, `V`) and '
                           'stability class `AK`. '
                           'Defaults to `None`')

    pars_wip.add_argument('-r', '--reference',
                         dest='reference',
                         metavar='FILE',
                         default=None,
                         help='overplot a reference wind profile read '
                              'from `FILE`. The format is detected '
                              'automatically: a plain ASCII file with '
                              'three columns (height above ground in '
                              'm, wind speed in m/s, wind direction in '
                              'degrees; leading header lines that do '
                              'not parse as three numbers are skipped '
                              'automatically), a Scintec FORMAT-1/1.1 '
                              'sodar file (the scan closest to the '
                              'time given by -t is used, or the last '
                              'scan in the file), or a Halo Photonics '
                              'lidar "Processed Wind Profile" `.hpl` '
                              'file. Defaults to `None` (no reference '
                              'profile shown)')

    pars_wip.add_argument('-p', '--plot',
                         metavar="FILE",
                         nargs='?',
                         const='__default__',
                         help='save plot to a file. If `FILE` is "-" ' +
                              'the plot is shown on screen. If `FILE` is ' +
                              'missing, the file name defaults to ' +
                              '`windprofile.png`'
                         )
    pars_wip.add_argument('--altitude',
                         dest='altitude',
                         action='store_true',
                         default=False,
                         help='display height above sea level (altitude) '
                              'instead of height above ground. Requires '
                              'a topography file; if none is found, '
                              'zero ground elevation is assumed and a '
                              'warning is shown.')
    pars_adv_wip = pars_wip.add_argument_group('advanced options')
    pars_adv_wip.add_argument('--z0',
                         dest='z0',
                         default=None,
                         help=f"roughness length at the position of the "
                              f"measurement used for calculation of "
                              f"the effective anemometer height. "
                              f"Overrides the value provided by the "
                              f"data source. Ignored if value is None. "
                              f"[%(default)s]"
                         )
    pars_adv_wip.add_argument('--scale',
                              metavar="VALUE",
                              nargs='?',
                              default=None,
                              help='Max value of the wind speed axis in '
                                   'm/s. '
                                   'Default is autoscale.')

    return pars_wip
