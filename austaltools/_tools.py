import argparse
import os
import re
import shlex
import logging

import numpy as np
import pandas as pd
import matplotlib.colors
import matplotlib.patches
import matplotlib.pyplot as plt

import readmet
# -------------------------------------------------------------------------

DEFAULT_WORKING_DIR = "."
DEFAULT_COLORMAP = "YlOrRd"

# -------------------------------------------------------------------------

logger = logging.getLogger(__name__)

class Geometry():
    x = 0.
    y = 0.
    a = 0.
    b = 0.
    c = 0.
    w = 0.

    def __init__(self, x=0, y=0, a=0, b=0, c=0, w=0):
        self.x = x
        self.y = y
        self.a = a
        self.b = b
        self.c = c
        self.w = w


class Building(Geometry):
    def __init__(self, *args, **kwargs):
        Geometry.__init__(self, *args, **kwargs)


class Source(Geometry):
    def __init__(self, *args, **kwargs):
        Geometry.__init__(self, *args, **kwargs)

def get_buildings(conf):
    pars = ["xb", "yb", "ab", "bb", "cb", "wb"]
    res = []
    if "xb" in conf and "yb" in conf:
        number = len(conf["xb"])
        lb = {}
        val={}
        for par in pars:
            if par in conf:
                if number != len(conf[par]):
                    raise ValueError('different numbers of ' +
                                     'building-definig parameters')
                val[par] = conf[par]
            else:
                val = [0] * len(conf())
        for i in range(number):
            res.append(Building(*[val[p][i] for p in pars]))
    else:
        logger.warning('no buildings in cofig')
    return res


def find_austxt(wdir='.'):
    if wdir == '':
        wdir = '.'
    xnames = [os.path.join(wdir, x) for x in ["austal.txt",
                                              "austal2000.txt"]]
    for x in xnames:
        if os.path.exists(x):
            ausname = x
            break
    else:
        raise IOError('austal.txt or austal200.txt not found')
    logger.debug('austal config: %s' % ausname)
    return ausname


def get_austxt(path="austal.txt"):
    logger.info('reading: %s' % path)
    # return config as dict
    conf = {}
    with open(path, 'r') as file:
        for line in file:
            # remove comments in each line
            text = re.sub("^[ ]*-.*", "", line)
            text = re.sub("'.*", "", text).strip()
            # if empty line remains: skip
            if text == "":
                continue
            logger.debug('%s - %s' % (os.path.basename(path), text))
            # split line into key / value pair
            key, val = text.split(maxsplit=1)
            # make numbers numeric
            try:
                values = [float(x) for x in val.split()]
            except ValueError:
                values = shlex.split(val)
            # in Liste abspeichern (Zahlen als Zahlen, Strings als Strings)
            conf[key] = values
    # fill missing values with default 0
    for x in ['xq', 'yq', 'aq', 'bq', 'cq', 'wq',
              'xb', 'yb', 'ab', 'bb', 'cb', 'wb',
              'cb']:
        if x not in conf:
            conf[x] = [0.]
    # fill other missing values with defaults
    if 'hq' not in conf:
        conf['hq'] = [20.]
    # liste zurückgeben
    return conf


def put_austxt(path="austal.txt", data={}):
    # get config as text
    logger.debug('reading: %s' % path)
    with open(path, 'r') as file:
        lines = file.readlines()
    # backup
    logger.debug('writing backup: %s' % path+'~')
    with open(path+'~', 'w') as file:
        for line in lines:
            file.write(line)
    # rewrite old file
    logger.info('rewriting file: %s' % path)
    with open(path, 'w') as file:
        last_line_was_empty = False
        for line in lines:
            keep = True
            # In jeder Zeile Kommentare entfernen
            stripped = re.sub("^[ ]*-.*", "", line)
            stripped = re.sub("'.*", "", stripped).strip()
            # wenn Zeile Daten enthält
            if stripped != "":
                # Zeile in Einzelwerte zerlegen
                key, val = stripped.split(maxsplit=1)
                # Soll der Wert ersetzt werden?
                if key in data.keys():
                    keep = False
            # no repeated empty lines
            if keep and last_line_was_empty and line.strip() == "":
                keep = False
            if keep:
                logger.debug('%s + %s' %
                             (os.path.basename(path), line.strip()))
                file.write(line)
                if line.strip() == "":
                    last_line_was_empty = True
                else:
                    last_line_was_empty = False
            else:
                logger.debug('%s - %s' %
                             (os.path.basename(path), line.strip()))
        file.write("\n")
        for k, v in data.items():
            line = "{:s}  {:s}\n".format(k, v)
            logger.debug('%s + %s' %
                         (os.path.basename(path), line.strip()))
            file.write(line)


def add_arguents_common_plot(parser: argparse.ArgumentParser
                             ) -> argparse.ArgumentParser:
    """
    add agruments to a parser that are honored by the common_plot
    funtion
    :param parser: parser to add arguments to
    :type parser: argparse.ArgumentParser
    :return: parser with added arguments
    :rtype:  argparse.ArgumentParser
    """
    parser.add_argument('-w', '--working-dir',
                        default=DEFAULT_WORKING_DIR,
                        help="working directory. " +
                             'In this directory the file `austal.txt` ' +
                             'is expected. Defaults to "%s"' %
                             DEFAULT_WORKING_DIR)
    parser.add_argument('-b', '--no-buildings',
                        dest='buildings',
                        action='store_false',
                        help='do not show the buildings ' +
                             'defined in config file')
    parser.add_argument('-l', '--low-colors',
                        dest='fewcols',
                        action='store_true',
                        help='use only few discrete colors ' +
                             'for better print results')
    parser.add_argument('-c', '--colormap',
                        default=DEFAULT_COLORMAP,
                        help='name of colormap to use. Defaults to "%s"' %
                             DEFAULT_COLORMAP)
    parser.add_argument('-d', '--display',
                        default='contour',
                        choices=['contour', 'grid'],
                        help='choose kind of display. ' +
                             '`contour` produces filled contours, ' +
                             '`grid` produces coloured grid cells. ' +
                             'Defaults to `contour`')
    parser.add_argument('-p', '--plot',
                        metavar="FILE",
                        nargs='?',
                        const='__default__',
                        help='save plot to a file. If `FILE` is "-" ' +
                             'the plot is shown on screen. If `FILE` is ' +
                             'missing, the file name defaults to ' +
                             'the data file name with extension `png`'
                        )
    parser.add_argument('-f', '--force',
                        action='store_true',
                        default=False,
                        help='force overwriting plotfile if it exists.')
    return parser

def common_plot(args: dict,
                dat: dict,
                unit: str = "",
                topo: dict or str = None,
                dots: dict or np.ndarray = None,
                buildings: list = None,
                mark: dict or pd.DataFrame = None,
                scale: list or tuple = None) -> object:
    """
    :param args: dict containing the plot configuration
    :param dat: dictionary of `x`, `y`, and `z` values to plot.
      'x' and 'y' must be lists of float or 1-D ndarray.
      'z' must be ndarray of a shape matching the lenght of `x` and `y`
    :type dat: dict
    :param unit: physical units of the values `z` in dat
    :type unit: str
    :param scale: range of the color scale. None means auto scaling.
    :type unit: tuple or None
    :param topo: topography data as dict (same form as `dat`)
      or filename of a topography file in dmna-format
      or None for no topography
    :type topo: dict or string or None
    :param dots: data to ovelay dotted areas (e.g. to mark significance).
      `dots` must either be a dict (same form as `dat`)
      or a ndarray matching the `z` data in `dat` in shape.
      dat values z < 0 are not overlaid,
      values 0 <= z < 1 are sparesely dotted,
      values 1 <= z < 2 are sparesely dotted,
      spography data as dict (same form as `dat`)
      or filename of a topography file in dmna-format
      or None for no topography
    :param buildings: List of `Building` objects to be displayed.
      If None or list is epmty, no buildings are plotted.
    :type buildings: list
    :param mark: positions to mark. either dict containing list-like
       objects of `x`, `y` and optionally 'symbol' of the same length
       or a pandas data frame containing such columns.
       `symbol` are matplotlib symbol strings. If missing 'o' is used.
    :type mark: dict or pandas.Dataframe

    """
    matplotlib.rcParams.update({'font.size': 16})
    fig, ax = plt.subplots()
    fig.set_size_inches(11, 8)

    # ---------------------------
    # plot data as color-coded map
    #
    if "colormap" in args:
        cmap_name = args["colormap"]
    else:
        cmap_name = DEFAULT_COLORMAP
    if isinstance(dat, dict):
        datx = dat['x']
        daty = dat['y']
        datz = dat['z']
        if (len(datx), len(daty)) != np.shape(datz):
            raise ValueError('lenghts of x and y do not match shape of z')
    else:
        raise ValueError('dat must be dict')

    levels = None
    if scale is None:
        dmin = np.nanmin(datz)
        dmax = np.nanmax(datz)
    elif isinstance(scale,float):
        dmin = 0.
        dmax = scale
    elif len(scale) == 2:
        dmin, dmax = scale
    elif len(scale) > 2:
        levels = np.array(scale)
    if levels is None:
        data_range = dmax - dmin
        order = 10**np.floor(np.log10(data_range))
        dmin = np.floor(dmin / order) * order
        dmax = np.ceil(dmax / order) * order
        logger.info('data_range: %f' % data_range)
        levels = np.arange(dmin, dmax, data_range / 10)

    if args['fewcols']:
        cmap = plt.get_cmap(cmap_name, len(levels) + 1)
    else:
        cmap = plt.get_cmap(cmap_name)
    if args['display'] == "contour":
        img = plt.contourf(datx, daty,
                           datz.T,
                           origin="lower",
                           levels=levels,
                           cmap=cmap,
                           extend='both'
                           )
        plt.colorbar(img, label=unit, extend='both')
    elif args['display'] == "grid":
        img = plt.pcolor(datx, daty,
                         dat.T,
                         shading="nearest",
                         cmap=cmap,
                         )
        plt.colorbar(img, label=unit, extend='both', boundaries=levels)
    else:
        raise ValueError('argument display missing or invalid')
    logger.debug('unit: %s' % unit)

    # ---------------------------
    # overlay dots e.g. to mark significance
    #
    if dots is not None:
        if isinstance(dots, dict):
            dotx = dots['x']
            doty = dots['y']
            dotz = dots['z']
        elif isinstance(dots,np.ndarray):
            dotz = dots
            if np.shape(dotz) != np.shape(datz):
                raise ValueError('dots shape does not equal dat shape')
            else:
                dotx = datx
                doty = daty
        else:
            raise ValueError('dots must be dict or ndarray')
        plt.contourf(dotx, doty, dotz.T, origin="lower",
                     levels=[0, 1, 2],
                     colors=['white', 'white', 'white', 'white'],
                     hatches=['+', '..', '..', None],
                     extend='both',
                     alpha=0)
        plt.contourf(datx, daty, dotz.T, origin="lower",
                     levels=[0, 1, 2],
                     colors=['white', 'white', 'white', 'white'],
                     hatches=['+', '..', '..', None],
                     extend='both',
                     alpha=0)

    # ---------------------------
    # overlay topography as isolines
    #
    if topo is not None:
        logger.debug('adding topography')
        if isinstance(topo, dict):
            logger.debug('... from data in arguments')
            topx = topo["x"]
            topy = topo["y"]
            topz = topo["z"]
        elif isinstance(topo, str):
            logger.debug('... from file: %s' % topo)
            if os.path.exists(topo):
                topo_path = topo
            elif os.path.exist(os.path.join(args['working_dir'], topo)):
                topo_path = os.path.join(args['working_dir'], topo)
            else:
                raise ValueError('topography file not found: %s' % topo)
            logger.info('reading topography from %s' % topo_path)
            topofile = readmet.dmna.DataFile(topo_path)
            topz = topofile.data[""]
            topx = topofile.axes(ax="x")
            topy = topofile.axes(ax="y")
        else:
            raise ValueError('topo must be dict of filename')
        con = plt.contour(topx, topy, topz.T, origin="lower",
                          colors='black',
                          linewidths=0.75
                          )
        ax.clabel(con, con.levels, inline=True, fontsize=10)

    # ---------------------------
    # show buildings
    #
    if buildings is not None:
        for bb in buildings:
            ax.add_patch(
                matplotlib.patches.Rectangle(
                    xy=(bb.x, bb.y),
                    width=bb.a,
                    height=bb.b,
                    angle=bb.w,
                    fill=True,
                    color="black",
                )
            )

    # ---------------------------
    # put marks on desired positions
    #
    if mark is not None:
        pf = pd.DataFrame(mark)
        for i,p in pf.iterrows():
            x = p['x']
            y = p['y']
            if 'sym' in p:
                sym = p['symbol']
            else:
                sym = "o"
        ax.plot(x, y, sym, markersize=10)

    ax.set_xlabel("x in m")
    ax.set_ylabel("y in m")

    if args["plot"] == "__show__":
        logger.info('showing plot')
        plt.show()
    elif args["plot"] not in [None, ""]:
        if os.path.sep in args["plot"]:
            outname = args["plot"]
        else:
            outname = os.path.join(args["working_dir"], args["plot"])
        if not outname.endswith('.png'):
            outname = outname + '.png'
        logger.info('writing plot: %s' % outname)
        plt.savefig(outname, dpi=180)
