#!/bin/env python3
# -*- coding: utf-8 -*-
"""
This module plots wind roses.

The functions :func:`windrose_histogram` and :func:`plot_windrose`
can also be used by other code, :func:`main` implements the
command ``windrose``.
"""
import logging
import os
import sys
from typing import NamedTuple

import numpy as np
import pandas as pd

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import matplotlib as mpl
    import matplotlib.pyplot as plt

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

BEAUF = 'beaufort'
MPERS = '2ms'
QUANT = 'quantile'
STAB = 'stability'
SEAS = 'halfyear'
QUAD = 'season'

SCALES = [BEAUF, MPERS, QUANT, STAB, SEAS, QUAD]
""" all known classification scales """

STYLES = ['default', 'star', 'step', 'ring']
""" all known plot styles """

UNITS = ['hours', 'percent']
""" units of the radial axis """

DEFAULT_STYLE = 'default'
""" default plot style """
DEFAULT_SECTORS = '12'
""" default number of sectors to plot """
DEFAULT_SCALE = BEAUF
""" default classification scale """
DEFAULT_UNIT = 'hours'
""" default unit of the radial axis """

DEFAULT_CMAPS = {
    'default': 'Paired',
    'star': 'Pastel1',
    'step': 'Set1',
    'ring': None,  # matplotlib color cycle
}
""" default colormap for each plot style """

STAB_CMAP = 'RdYlBu_r'
""" default colormap for scale ``stability``
(class I = very stable = blue ... class V = very unstable = red) """

# -------------------------------------------------------------------------


class RoseHistogram(NamedTuple):
    """
    Wind rose histogram as returned by :func:`windrose_histogram`.
    """
    hist: np.ndarray
    """ number of hours, shape (sectors, classes) """
    labels: list
    """ label of each class """
    calm: int
    """ number of calm hours (not contained in `hist`) """
    total: int
    """ number of hours with valid wind data (including calms) """
    scale: str
    """ classification scale used """

    @property
    def sectors(self) -> int:
        """ number of direction sectors """
        return int(np.shape(self.hist)[0])

    @property
    def borders(self) -> list[float]:
        """ direction boundaries of the sectors in degrees
        (``sectors + 1`` values from 0 to 360) """
        return [float(x * 360. / float(self.sectors))
                for x in range(self.sectors + 1)]

# -------------------------------------------------------------------------


def _colors(cmap: str, n: int) -> list:
    """
    Get (at least) `n` colors from colormap `cmap`.
    Qualitative colormaps (listed, up to 20 colors) are used color
    by color if they contain enough colors, otherwise the colormap
    is sampled evenly.
    """
    cm = mpl.colormaps[cmap]
    if hasattr(cm, 'colors') and n <= len(cm.colors) <= 20:
        return cm.colors
    return [cm(x) for x in np.linspace(0.05, 0.95, n)]

# -------------------------------------------------------------------------


def main(args):
    """
    This is the main working function

    :param args: The command line arguments as a dictionary, with keys:

      - ``working_dir``: The working directory where files are located
        (i.e. where ``austal.txt`` is stored). Defaults to
        ``_tools.DEFAULT_WORKING_DIR`` if missing or ``None``.
      - ``weather``: name of the weather data file to read. Defaults
        to ``None`` if missing, in which case the file name is
        determined from ``austal.txt``.
      - ``scale``: how to classify the values, one of ``BEAUF``,
        ``MPERS``, ``QUANT``, ``STAB``, ``SEAS``, ``QUAD``. Defaults
        to ``DEFAULT_SCALE`` if missing or ``None``.
      - ``sectors``: number of sectors to plot. Defaults to
        ``DEFAULT_SECTORS`` if missing or ``None``.
      - ``style``: plot style, one of 'default', 'star', 'step',
        'ring'. Defaults to ``DEFAULT_STYLE`` if missing or ``None``.
      - ``colormap``: name of colormap to use. The default depends on
        ``style``; defaults to ``None`` if missing.
      - ``unit``: unit of the radial axis, one of ``UNITS``.
        Defaults to ``DEFAULT_UNIT`` if missing or ``None``.
      - ``plot``: The plot file name. Defaults to 'windrose.png' if
        missing or ``None``.

    :type args: dict

    :raises ValueError: If ``scale`` is not a recognised value.
    """
    logger.debug(format(args))

    working_dir = args.get('working_dir', None)
    if working_dir is None:
        working_dir = _tools.DEFAULT_WORKING_DIR

    # determine output
    plotfile = _plotting.consolidate_plotname(
        args.get('plot', None), 'windrose.png')

    weather = args.get('weather', None)
    if weather is not None:
        az = _windutil.load_weather(working_dir, file=weather)
    else:
        conf = _tools.get_austxt(_tools.find_austxt(working_dir))
        az = _windutil.load_weather(working_dir, conf=conf)

    rose = windrose_histogram(az, scale=args.get('scale', None),
                              sectors=args.get('sectors', None))

    style = args.get('style', None)
    if style is None:
        style = DEFAULT_STYLE
    logger.info(f"using plot style: {style}")
    cmap = args.get('colormap', None)
    logger.info(f"user-selected colorscale: {cmap}")

    mpl.rcParams.update({'font.size': 16})
    fig = plt.figure(figsize=(11, 8))
    ax = fig.add_subplot(projection='polar')
    plot_windrose(ax, rose, style=style, cmap=cmap,
                  unit=args.get('unit', None))
    # save space
    fig.tight_layout()

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

# -------------------------------------------------------------------------


def windrose_histogram(az: pd.DataFrame, scale: str | None = None,
                       sectors: int | str | None = None
                       ) -> RoseHistogram:
    """
    Sort wind data into direction sectors and classes.

    :param az: weather data with columns ``FF`` (wind speed in m/s),
      ``DD`` (wind direction in degrees), ``KM`` (stability class
      1...6) and the time as index, as returned by
      :func:`austaltools._windutil.load_weather`. Hours with
      ``FF`` and ``DD`` both 0 are calms and are not sorted
      into the histogram.
    :type az: pandas.DataFrame
    :param scale: how to classify the values, one of :data:`SCALES`.
      Defaults to :data:`DEFAULT_SCALE` if ``None``.
    :type scale: str | None
    :param sectors: number of sectors to plot. Defaults to
      :data:`DEFAULT_SECTORS` if ``None``.
    :type sectors: int | str | None
    :return: histogram
    :rtype: RoseHistogram
    :raises ValueError: If ``scale`` is not a recognised value.
    """
    ff = az['FF'].mask((az['FF'] == 0) & (az['DD'] == 0), np.nan)
    dd = az['DD'].mask((az['FF'] == 0) & (az['DD'] == 0), np.nan)
    ak = az['KM']
    mo = pd.to_datetime(az.index).month

    # AK (ak) in file and command line is 1-based,
    # ak0 is zero-based so it can be used as field index
    ak0 = [int(x) - 1 for x in ak]
    #akstr = _dispersion.KM2021.name(int(ak))
    if scale is None:
        scale = DEFAULT_SCALE
    logger.info(f"using scale {scale}")
    if sectors is None:
        sectors = DEFAULT_SECTORS
    sectors = int(sectors)
    logger.info(f"number of sectors {scale}")

    d_bnds = [float(x * 360./float(sectors)) for x in range(sectors + 1)]

    if scale in [BEAUF, MPERS, QUANT]:
        if scale == BEAUF:
            r_bnds = [0, 0.2, 1.5, 3.3, 5.4, 7.9, 10.7, 13.8, 17.1, 299.]
        elif scale == MPERS:
            step = 2.
            nbnds = int(max(np.ceil(np.nanmax(ff) / step), 5)) + 1
            r_bnds = [float(i) * step
                       for i in range(nbnds)]
        elif scale == QUANT:
            nbnds = 6
            step = 1. / float(nbnds - 1)
            r_bnds = [np.nanquantile(ff, float(i) * step)
                       for i in range(nbnds)]
            r_bnds[0] = 0.
        else:
            raise ValueError(f"scale out of range: {scale}")
        labels = []
        for i in range(len(r_bnds) - 2):
            labels.append("%4.1f-%4.1f" % (r_bnds[i], r_bnds[i+1]))
        labels.append(u"    \u2265 %4.1f" % r_bnds[-2])
        hist,xx,yy = np.histogram2d(dd,ff, bins=[d_bnds, r_bnds])
    elif scale == STAB:
        r_bnds = [0. + i for i in range(7)]
        labels = [_dispersion.KM2021.num2name(j+1) for j in range(6)]
        hist,xx,yy = np.histogram2d(dd,ak0, bins=[d_bnds, r_bnds])
    elif scale in [SEAS, QUAD]:
        if scale == SEAS:
            r_bnds = [0., 1., 2.]
            labels = ['winter half', 'summer half']
            seas = [1 if 4 <= x < 10 else 0 for x in mo]
            hist, xx, yy = np.histogram2d(dd, seas, bins=[d_bnds, r_bnds])
        elif scale == QUAD:
            r_bnds = [0., 1., 2., 3., 4.]
            labels = ['Spring', 'Summe', 'Fall', 'Winte']
            seas = [float((x - 4) % 12) / 3.  for x in mo]
            hist, xx, yy = np.histogram2d(dd, seas, bins=[d_bnds, r_bnds])
        else:
            raise ValueError(f"scale out of range: {scale}")
    else:
        sys.tracebacklimit=0
        raise ValueError(f"unkonwn scale `{scale}`")

    calm = int(((az['FF'] == 0) & (az['DD'] == 0)).sum())
    total = int((az['FF'].notna() & az['DD'].notna()).sum())

    return RoseHistogram(hist=hist, labels=labels, calm=calm,
                         total=total, scale=scale)

# -------------------------------------------------------------------------


def plot_windrose(ax, rose: RoseHistogram,
                  style: str | None = None,
                  cmap: str | None = None,
                  unit: str | None = None,
                  legend: bool = True):
    """
    Draw a wind rose into a polar axes.

    :param ax: polar axes to draw into
      (e.g. ``fig.add_subplot(projection='polar')``)
    :type ax: matplotlib.projections.polar.PolarAxes
    :param rose: histogram as returned by :func:`windrose_histogram`
    :type rose: RoseHistogram
    :param style: plot style, one of :data:`STYLES`.
      Defaults to :data:`DEFAULT_STYLE` if ``None``.
    :type style: str | None
    :param cmap: name of colormap to use. The default depends on
      `style` (see :data:`DEFAULT_CMAPS`) and is :data:`STAB_CMAP`
      for scale ``stability``. Not used by style ``ring``.
    :type cmap: str | None
    :param unit: unit of the radial axis, one of :data:`UNITS`.
      ``percent`` is relative to all hours with valid wind data,
      including calms. Defaults to :data:`DEFAULT_UNIT` if ``None``.
    :type unit: str | None
    :param legend: if a legend is added
    :type legend: bool
    :return: the axes
    """
    hist = rose.hist
    xx = rose.borders
    labels = rose.labels
    sectors = rose.sectors
    if unit is None:
        unit = DEFAULT_UNIT
    if unit == 'percent':
        hist = hist / float(rose.total) * 100.

    xmid = [(xx[i] + xx[i+1]) * np.pi / 360. for i in range(len(xx) - 1)]
    nxx, nyy = np.shape(hist)

    if style is None:
        style = DEFAULT_STYLE
    if cmap is None and rose.scale == STAB:
        cmap = STAB_CMAP

    # display degrees clockwise from north
    ax.set_theta_zero_location('N')
    ax.set_theta_direction(-1)

    if style == 'default':
        # default colors
        cmap = DEFAULT_CMAPS[style] if cmap is None else cmap
        # sum up histogram classes for each sector
        bottom = [0.] * sectors
        for cls in range(nyy):
            ax.bar(xmid, hist[:, cls], bottom=bottom,
                   color=_colors(cmap, nyy)[cls],
                   width=0.8 * 2. * np.pi / float(sectors),
                   edgecolor='black',
                   label=labels[cls])
            bottom = [bottom[i] + hist[i, cls] for i in range(len(hist))]

    elif style in ['star']:
        # add first value at the end to close the ring
        hist = np.vstack([hist, hist[0,:]])
        xmid.append(xmid[0])
        # rearrange histogram into individual lists
        nyy = np.shape(hist)[1]
        stacks = [hist[:,j] for j in range(nyy)]
        # default colors
        cmap = DEFAULT_CMAPS[style] if cmap is None else cmap
        # plot
        ax.stackplot(
            xmid, *stacks,
            colors=_colors(cmap, nyy),
            linestyle='-',
            edgecolor='black',
            linewidth=0.75,
            labels=labels
        )
    elif style in ['step']:
        # rearrange histogram into individual lists
        hist = np.vstack([hist, hist[0,:]])
        stacks = [hist[:,j] for j in range(nyy)]
        # default colors
        cmap = DEFAULT_CMAPS[style] if cmap is None else cmap
        # repeat last element before first avoid gap
        # between 0° and the first step
        xs = np.array([0, *xx[1:], 360.])
        ss = [[stacks[j][0], *stacks[j]] for j in range(nyy)]
        # plot
        ax.stackplot(
            np.deg2rad(xs), *ss, step='pre',
            colors=_colors(cmap, nyy),
            linestyle='-',
            edgecolor='black',
            linewidth=0.75,
            labels=labels
        )
    elif style in ['ring']:
        # rearrange histogram into individual lists
        hist = np.vstack([hist, hist[0,:]])
        stacks = [hist[:,j] for j in range(nyy)]
        # plot
        for i,stack in enumerate(stacks):
            ax.plot(np.deg2rad(xx), stack, linewidth=2., label=labels[i])
    if unit == 'percent':
        ax.yaxis.set_major_formatter(
            mpl.ticker.FuncFormatter(lambda v, _: f"{v:g} %"))
    if legend:
        # place legend (lower left corner at outer endhge at angle `angl`
        langl = np.deg2rad(90)
        ax.legend(loc="lower left",
                  bbox_to_anchor=(.5 + np.sin(langl)/2, .5 + np.cos(langl)/2))
    return ax

# ----------------------------------------------------

def add_options(subparsers):

    pars_wrs = subparsers.add_parser(
        name='windrose',
        help='Plot wind rose',
        formatter_class=_tools.SmartFormatter,
    )
    pars_wrs.add_argument('-k', '--kind',
                          dest='style',
                          choices=STYLES,
                          default=DEFAULT_STYLE,
                          help='style of wind field plot [%(default)s])]')
    pars_wrs.add_argument('-n', '--sectors',
                          dest='sectors',
                          default=DEFAULT_SECTORS,
                          help='number of sectors to plot [%(default)s])]')
    pars_wrs.add_argument('-s', '--scale',
                          dest='scale',
                          choices=SCALES,
                          default=DEFAULT_SCALE,
                          help='How to classify the values '
                               '[%(default)s]:\n' +
                               ('  - `%s`: ' % BEAUF) +
                               'wind speed in beaufort\n' +
                               ('  - `%s`: ' % MPERS) +
                                'wind speed in steps of 2 m/s\n' +
                               ('  - `%s`: ' % QUANT) +
                                'wind speed quantiles\n' +
                               ('  - `%s`: ' % STAB) +
                                'stability class\n' +
                               ('  - `%s`: ' % SEAS) +
                                'summer/winter half year\n' +
                               ('  - `%s`: ' % QUAD) +
                                'meteorological season\n',
                          )
    pars_wrs.add_argument('-u', '--unit',
                          dest='unit',
                          choices=UNITS,
                          default=DEFAULT_UNIT,
                          help='unit of the radial axis. `percent` '
                               'is relative to all hours with valid '
                               'wind data [%(default)s]')
    pars_wrs.add_argument('-c', '--colormap',
                         default=None,
                         help='name of colormap to use. '
                              'The default depends on `-k`.')
    pars_wrs.add_argument('-p', '--plot',
                        metavar="FILE",
                        nargs='?',
                        const='__default__',
                        help='save plot to a file. If `FILE` is "-" ' +
                             'the plot is shown on screen. If `FILE` is ' +
                             'missing, the file name defaults to ' +
                             'the data file name with extension `png`'
                        )
    pars_wrs.add_argument('-w', '--weather',
                          dest='weather',
                          default=None,
                          help='name of the weather data file to'
                               'read. If this option is not given or'
                               'None, the name file is determined '
                               'from austal.txt [%(default)s])].')
