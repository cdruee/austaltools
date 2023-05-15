#!/usr/bin/env python3
"""
create basic plot for austal result files
"""
import argparse
import logging
import os
import re

import matplotlib.colors
import matplotlib.patches
import matplotlib.pyplot as plt
import numpy as np
import readmet

logger = logging.getLogger()
logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)

try:
    from ._tools import find_austxt, get_austxt, get_buildings, Building
except ImportError:
    from _tools import find_austxt, get_austxt, get_buildings, Building


# -------------------------------------------------------------------------

DEFAULT_WORKING_DIR = "."
DEFAULT_COLORMAP = "YlOrRd"


# -------------------------------------------------------------------------
def parse_austal_outputname(filename: str):
    """
    analyze name of austal output file

    :param filename: str

    :return: information about file contents:
      - substance: name of pollutant (xx for unknown/not specified)
      - averaging: duration of averaging interval
        (accumulation, year, day or hour)
      - rank: rank of output value in list of all averages
        of the same length
      - kind: type of output (load, stdev or index)
      - grid: number of grid. 0 if not given / no staggered grids.
    :rtype: dict
    """
    # strip path and extension
    name = os.path.splitext(os.path.basename(filename))[0]

    res = {"name": name}
    # name of substance
    if "-" not in name:
        raise ValueError("not a valid output name: %s" % name)
    res["substance"], what = name.split('-')
    #
    avg_char = what[0]
    if what.startswith('dep'):
        res["averaging"] = 'accumulation'
    elif avg_char in ['y', 'j']:
        res["averaging"] = 'year'
    elif avg_char in ['d', 't']:
        res["averaging"] = 'day'
    elif avg_char in ['h', 's']:
        res["averaging"] = 'hour'
    else:
        raise ValueError("unknown averaging in name: %s" % name)

    if res["averaging"] in ['accumulation']:
        res["rank"] = 0
    else:
        try:
            res["rank"] = int(what[1:3])
        except ValueError:
            raise ValueError("unknown rank in name: %s" % name)

    sel_char = what[3]
    if sel_char in ['a', 'z']:
        res["kind"] = 'load'
    elif sel_char in ['s']:
        res["kind"] = 'stdv'
    elif sel_char in ['i']:
        res["kind"] = 'index'
    else:
        raise ValueError("unknown kind of output in name: %s" % name)

    if len(what) <= 4:
        res["grid"] = 0
    else:
        try:
            res["grid"] = int(what[5:7])
        except ValueError:
            raise ValueError("unknown grid number in name: %s" % name)

    return res


# -------------------------------------------------------------------------
def cli() -> dict:
    """
    command line interface

    :return: conf (dict)
    """

    parser = argparse.ArgumentParser(
        description='create AUSTAL windlibrary using METRAS')
    parser.add_argument(dest="file", metavar="DATA",
                        help="data file to plot."
                        )
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
                        metavar="PLOTFILE",
                        nargs='?',
                        const='__default__',
                        help='save plot to a file. If given without' +
                             '`PLOT`, the file name defaults to ' +
                             'the data file name with extension `png`'
                        )
    parser.add_argument('-r', '--recreate',
                        action='store_true',
                        default=False,
                        help='recreate (overwrite) plotfile if it exists.')
    parser.add_argument('-s', '--stdvs',
                        metavar="STDVs",
                        nargs='?',
                        default=0.,
                        const=1.,
                        help='hash areas where the data are not ' +
                             'significant. Sigingicant is defined as ' +
                             'larder than `STDVs` times the standard ' +
                             'deviation caculated by austal. ' +
                             'If missing, `STDVs` defaults to 1.0.')
    varg = parser.add_mutually_exclusive_group()
    varg.add_argument('-v', '--verbose', action='count',
                      help='increase output verbosity')
    varg.add_argument('-q', '--quiet', action='count',
                      help='decrease output verbosity')
    arglist = vars(parser.parse_args())

    # set logging level
    logging_levels = [logging.CRITICAL, logging.ERROR, logging.WARNING,
                      logging.INFO, logging.DEBUG]
    logging_numeric = logging_levels.index(logger.getEffectiveLevel())
    if arglist['verbose'] is not None:
        logging_numeric = min(len(logging_levels) - 1,
                              logging_numeric + arglist['verbose'])
    elif arglist['quiet'] is not None:
        logging_numeric = max(0, logging_numeric - arglist['quiet'])
    logger.setLevel(logging_levels[logging_numeric])
    logging.info('logging level: {:s}'.format(
        logging.getLevelName(logging.root.getEffectiveLevel())))

    logger.debug(format(arglist))
    return arglist


# -------------------------------------------------------------------------


def main():
    args = cli()
    logger.debug("args: %s" % format(args))
    infile = args['file']
    # make sure infile has an extension
    if not infile.endswith('.dmna'):
        infile = infile + '.dmna'
    # analyze file name:
    info = parse_austal_outputname(infile)
    logger.debug("info: %s" % format(info))

    have_buildings = args['buildings']
    if have_buildings:
        # get config:
        austxt = find_austxt(os.path.dirname(infile))
        logger.debug("conf file: %s" % format(austxt))
        conf = get_austxt(austxt)
        logger.debug("conf: %s" % format(conf))
        buildings = get_buildings(conf)
        logging.info('buildings in config: %d' % len(buildings))
        if len(buildings) == 0:
            have_buildings = False

    # warn, if not a file containing "additional load"
    if info["kind"] != "load":
        logger.warning(
            'file does not contain load distribution: %s' % infile)

    infile_path = os.path.join(args['working_dir'], infile)
    logger.info('reading data from %s' % infile_path)
    datafile = readmet.dmna.DataFile(infile_path)
    dat = datafile.data[datafile.variables[0]]
    datx = datafile.axes(ax="x")
    daty = datafile.axes(ax="y")
    try:
        dd = float(datafile.header['delta'][0])
    except ValueError:
        dd = datx[1] - datx[0]
        logger.warning('grid spacing "delta" not in data file, ' +
                       'guessing: %fm ' % dd)

    if len(dat.shape) == 3:
        dat = dat[:, :, 0]
    unit = bytes(datafile.header["unit"], "latin-1").decode()

    stdvs = float(args["stdvs"])
    if stdvs > 0:
        stdfile = re.sub(r'(.+-...)[sz]([0-9]{0,2}\.dmna)',
                         r'\1s\2', infile)
        stdfile_path = os.path.join(args['working_dir'], stdfile)
        logger.info('reading stdev from %s' % infile_path)
        errorfile = readmet.dmna.DataFile(stdfile_path)
        std = errorfile.data[errorfile.variables[0]]
        if len(std.shape) == 3:
            std = std[:, :, 0]
        if dat.shape != std.shape:
            raise ValueError('stdv shape does not match data shape')
        std[std==0] = 1.E-19
        signi = dat / (stdvs * std)

    # try to load topography
    topo_path = os.path.join(args['working_dir'],
                             "zg%02d.dmna" % info["grid"])
    if os.path.exists(topo_path):
        logger.info('reading topography from %s' % topo_path)
        have_topo = True
        topofile = readmet.dmna.DataFile(topo_path)
        topz = topofile.data[""]
        topx = topofile.axes(ax="x")
        topy = topofile.axes(ax="y")
    else:
        have_topo = False

    # --------------------------------
    matplotlib.rcParams.update({'font.size': 16})
    fig, ax = plt.subplots()
    fig.set_size_inches(11, 8)

    cmap_name = args["colormap"]
    scale = 10 ** (np.ceil(np.log10(np.max(dat))) - 1)
    logging.debug('scale: %f' % scale)
    levels = np.array([10, 20, 50, 100, 200, 500, 1000]
                      ) / 1000 * scale
    if args['fewcols']:
        norm = matplotlib.colors.BoundaryNorm(boundaries=levels,
                                              ncolors=len(levels) + 2,
                                              extend='both')
        cmap = plt.get_cmap(cmap_name, len(levels) + 1)
    else:
        norm = matplotlib.colors.PowerNorm(gamma=0.33,
                                           vmin=levels[0], vmax=levels[-1])
        cmap = plt.get_cmap(cmap_name)
    if args['display'] == "contour":
        img = plt.contourf([x + dd / 2. for x in datx],
                           [y + dd / 2. for y in daty],
                           dat.T,
                           origin="lower",
                           levels=levels,
                           norm=norm,
                           cmap=cmap,
                           extend='both'
                           )
        plt.colorbar(img, label=unit, extend='both')
    elif args['display'] == "grid":
        img = plt.pcolor([x + dd / 2. for x in datx],
                         [y + dd / 2. for y in daty],
                         dat.T,
                         shading="nearest",
                         norm=norm,
                         cmap=cmap,
                         )
        plt.colorbar(img, label=unit, extend='both', boundaries=levels)
    logging.debug('label=: %s' % unit)

    if stdvs > 0:
        plt.contourf(datx, daty, signi.T, origin="lower",
                     levels=[0, 1, 2],
                     colors=['white', 'white', 'white', 'white'],
                     hatches=['+', '..', '..', None],
                     extend='both',
                     alpha=0)
        plt.contourf(datx, daty, signi.T, origin="lower",
                     levels=[0, 1, 2],
                     colors=['white', 'white', 'white', 'white'],
                     hatches=['+', '..', '..', None],
                     extend='both',
                     alpha=0)

    if have_topo:
        con = plt.contour(topx, topy, topz.T, origin="lower",
                          colors='black',
                          linewidths=0.75
                          )
        ax.clabel(con, con.levels, inline=True, fontsize=10)

    if have_buildings:
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

    ax.set_xlabel("x in m")
    ax.set_ylabel("y in m")

    if args["plot"] is None:
        plt.show()
    else:
        if args["plot"] == '__default__':
            outname = os.path.splitext(infile_path)[0] + '.png'
        else:
            if os.path.sep in args["plot"]:
                outname = args["plot"]
            else:
                outname = os.path.join(args["working_dir"], args["plot"])
            if not outname.endswith('.png'):
                outname = outname + '.png'
        logger.info('writing plot: %s' % outname)
        plt.savefig(outname, dpi=100)


# ------------------------------------------------------------------------


if __name__ == "__main__":
    main()
