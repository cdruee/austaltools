#!/usr/bin/env python3
"""
create basic plot for austal result files
"""
import argparse
import logging
import os

import matplotlib.colors
import matplotlib.pyplot as plt
import numpy as np
import readmet

logger = logging.getLogger()
logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
# -------------------------------------------------------------------------

DEFAULT_WORKING_DIR = "."
DEFAULT_COLORMAP = "cividis"


# -------------------------------------------------------------------------
def cli() -> dict:
    """
    command line interface

    :return: conf (dict)
    """

    parser = argparse.ArgumentParser(
        description='plot AUSTAL topography steepness')
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
    parser.add_argument('-g', '--grid',
                        default=0,
                        help="grid number. " +
                             "Defaults to 0.")
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

    # try to load topography
    topo_path = os.path.join(args['working_dir'],
                             "zg%02d.dmna" % args["grid"])
    if os.path.exists(topo_path):
        logger.info('reading topography from %s' % topo_path)
    topofile = readmet.dmna.DataFile(topo_path)
    topz = topofile.data[""]
    topx = topofile.axes(ax="x")
    topy = topofile.axes(ax="y")

    dd = float(topofile.header["delta"])
    dzdx = np.diff(topz, axis=0, prepend=np.nan) / dd
    dzdy = np.diff(topz, axis=1, prepend=np.nan) / dd
    gamma = np.sqrt(dzdx ** 2 + dzdy ** 2)

    # --------------------------------
    matplotlib.rcParams.update({'font.size': 16})
    fig, ax = plt.subplots()
    fig.set_size_inches(11, 8)

    cmap = args["colormap"]
    logging.info('max: 1:%f' % (1 / np.nanmax(gamma)))

    img = plt.imshow(gamma.T[1:, 1:], origin="lower",
                     extent=(topx[0] + dd / 2, topx[-1] - dd / 2,
                             topy[0] + dd / 2, topy[-1] - dd / 2),
                     aspect='equal',
                     cmap=cmap,
                     alpha=0.8)
    plt.colorbar(img, label="steepness", extend='both')

    plt.contour(topx, topy, gamma.T, origin="lower",
                levels=[1 / 20, 1 / 5],
                colors=['white', 'red'],
                linewidths=2
                )

    con = plt.contour(topx, topy, topz.T, origin="lower",
                      colors='black',
                      linewidths=1.
                      )
    ax.clabel(con, con.levels, inline=True, fontsize=10)
    ax.set_xlabel("x in m")
    ax.set_ylabel("y in m")

    if args["plot"] is None:
        plt.show()
    else:
        if args["plot"] == '__default__':
            outname = os.path.join(args["working_dir"] + 'steepness.png')
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
