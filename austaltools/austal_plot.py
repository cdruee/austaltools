#!/usr/bin/env python3
"""
create basic plot for austal result files
"""
import argparse
import logging
import os
import re

import matplotlib.colors
import matplotlib.pyplot as plt
import numpy as np
import readmet

logger = logging.getLogger()
logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
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
    if avg_char.startswith('dep'):
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
    parser.add_argument('-c', '--colormap',
                        default=DEFAULT_COLORMAP,
                        help='name of colormap to use. Defaults to "%s"' %
                             DEFAULT_COLORMAP)
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
    topofile = readmet.dmna.DataFile(topo_path)
    topz = topofile.data[""]
    topx = topofile.axes(ax="x")
    topy = topofile.axes(ax="y")

    # --------------------------------
    matplotlib.rcParams.update({'font.size': 16})
    fig, ax = plt.subplots()
    fig.set_size_inches(11, 8)

    cmap = args["colormap"]
    scale = 10 ** (np.ceil(np.log10(np.max(dat))) - 1)
    logging.debug('scale: %f' % scale)
    levels = np.array([10, 20, 50, 100, 200, 500, 1000]
                      ) / 1000 * scale

    img = plt.contourf(datx, daty, dat.T, origin="lower",
                       levels=levels,
                       norm=matplotlib.colors.PowerNorm(gamma=0.33),
                       cmap=cmap,
                       extend='both'
                       )
    plt.colorbar(img, label=unit, extend='both')
    logging.debug('label=: %s' % unit)

    if stdvs > 0:
        # whites = matplotlib.colors.ListedColormap(
        #     [(1, 1, 1, 0.4),
        #      (1, 1, 1, 0.2),
        #      (1, 1, 1, 0.1),
        #      (1, 1, 1, 0.0)])
        # cmap = whites,

        plt.contourf(datx, daty, signi.T, origin="lower",
                     levels=[0, 1, 2],
                     colors=['white', 'white', 'white', 'white'],
                     hatches=['+', '..', '..', None],
                     extend='both',
                     alpha=0)

    con = plt.contour(topx, topy, topz.T, origin="lower",
                      colors='black',
                      linewidths=0.75
                      )
    ax.clabel(con, con.levels, inline=True, fontsize=10)
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
