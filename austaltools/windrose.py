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

try:
    from . import _dispersion
    from . import _corine
    from . import _plotting
    from . import _tools
    from ._metadata import __version__
    from . import _windutil
except ImportError:
    import _dispersion
    import _corine
    import _plotting
    import _tools
    from _version import __version__
    import _windutil

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

# -------------------------------------------------------------------------


def main(args):
    """
    This is the main working function

    :param args: the command line arguments as dictionary
    :type args: dict
    """
    logger.debug(format(args))

    working_dir = args.get('working_dir', '.')
    weather = args.get('weather', None)
    if weather is not None:
        az = _windutil.load_weather(working_dir, file=weather)
    else:
        conf = _tools.get_austxt(_tools.find_austxt(working_dir))
        az = _windutil.load_weather(working_dir, conf=conf)

    ff = az['FF']
    dd = az['DD']
    ak = az['KM']
    mo = pd.to_datetime(az.index).month
    # u, v = meteolib.wind.dir2uv(ff, dd)

    # AK (ak) in file and command line is 1-based,
    # ak0 is zero-based so it can be used as field index
    ak0 = [int(x) - 1 for x in ak]
    #akstr = _dispersion.KM2021.name(int(ak))
    scale = args['scale']
    logger.info(f"using scale {scale}")
    sectors = int(args['sectors'])
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
            r_bnds = [np.quantile(ff, float(i) * step)
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
        labels = [_dispersion.KM2021.name(j+1) for j in range(6)]
        hist,xx,yy = np.histogram2d(dd,ff, bins=[d_bnds, r_bnds])
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

    xmid = [(xx[i] + xx[i+1]) * np.pi / 360. for i in range(len(xx) - 1)]
    nxx, nyy = np.shape(hist)

    style = args['style']
    logger.info(f"using plot style: {style}")
    cmap = args['colormap']
    logger.info(f"user-selected colorscale: {cmap}")

    mpl.rcParams.update({'font.size': 16})
    fig = plt.figure(figsize=(11, 8))
    ax = fig.add_subplot(projection='polar')
    # display degrees clockwise from north
    ax.set_theta_zero_location('N')
    ax.set_theta_direction(-1)

    if style == 'default':
        # default colors
        cmap = 'Paired' if cmap is None else cmap
        # sum up histogram classes for each sector
        bottom = [0.] * sectors
        for cls in range(nyy):
            ax.bar(xmid, hist[:, cls], bottom=bottom,
                   color=mpl.colormaps[cmap].colors[cls],
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
        cmap = 'Pastel1' if cmap is None else cmap
        # plot
        ax.stackplot(
            xmid, *stacks,
            colors=mpl.colormaps[cmap].colors,
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
        cmap = 'Set1' if cmap is None else cmap
        # repeat last element before first avoid gap
        # between 0° and the first step
        xs = np.array([0, *xx[1:], 360.])
        ss = [[stacks[-1][j], *stacks[:][j]] for j in range(nyy)]
        # plot
        print (len(xs), len(ss), xs, ss)
        ax.stackplot(
            np.deg2rad(xs), *ss, step='pre',
            colors=mpl.colormaps[cmap].colors,
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
    # place legend (lower left corner at outer endhge at angle `angl`
    langl = np.deg2rad(90)
    ax.legend(loc="lower left",
              bbox_to_anchor=(.5 + np.sin(langl)/2, .5 + np.cos(langl)/2))
    # save space
    fig.tight_layout()

    # save figure
    if args['plot'] is None or args['plot'] == '-':
        args['plot'] = '__show__'
    elif args['plot'] == '__default__':
        args['plot'] = 'windrose.png'

    if args["plot"] == "__show__":
        logger.info('showing plot')
        plt.show()
    else:
        if os.path.sep in args["plot"]:
            outname = args["plot"]
        else:
            outname = os.path.join(args["working_dir"], args["plot"])
        if not outname.endswith('.png'):
            outname = outname + '.png'
        logger.info('writing plot: %s' % outname)
        plt.savefig(outname, dpi=180)

# ----------------------------------------------------

def add_options(subparsers):

    pars_wrs = subparsers.add_parser(
        name='windrose',
        help='Plot wind rose',
        formatter_class=_tools.SmartFormatter,
    )
    pars_wrs.add_argument('-k', '--kind',
                          dest='style',
                          choices=['default', 'star', 'step', 'ring'],
                          default='default',
                          help='style of wind field plot [%(default)s])]')
    pars_wrs.add_argument('-n', '--sectors',
                          dest='sectors',
                          default='12',
                          help='number of sectors to plot [%(default)s])]')
    pars_wrs.add_argument('-s', '--scale',
                          dest='scale',
                          choices=[BEAUF, MPERS, QUANT, STAB, SEAS, QUAD],
                          default=BEAUF,
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
