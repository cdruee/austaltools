#!/usr/bin/env python3
"""
create basic plot for austal result files
"""
import argparse
import logging
import os

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import numpy as np
    import readmet

try:
    from . import _tools
except ImportError:
    import _tools

try:
    from ._version import __version__
except ImportError:
    from _version import __version__

logger = logging.getLogger()
logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
# -------------------------------------------------------------------------

DEFAULT_WORKING_DIR = "."
DEFAULT_COLORMAP = "cividis"

# -------------------------------------------------------------------------


def cli_parser():
    parser = argparse.ArgumentParser(
        description='Plot AUSTAL topography steepness')
    parser = _tools.add_arguents_common_plot(parser)
    parser.add_argument('-g', '--grid',
                        metavar='ID',
                        nargs='?',
                        default=0,
                        help='ID (number) of the grid to evaluate. '
                             'Defaults to 0')
    parser.add_argument("--version",
                        version="%(prog)s " + str(__version__),
                        action="version")
    verb = parser.add_mutually_exclusive_group()
    verb.add_argument('--debug', dest='verb', action='store_const',
                      const=logging.DEBUG, help='show informative output')
    verb.add_argument('-v', '--verbose', dest='verb', action='store_const',
                      const=logging.INFO, help='show detailed output')
    return parser
# -------------------------------------------------------------------------


def main():
    parser = cli_parser()
    args = vars(parser.parse_args())
    #
    # logging level
    #
    if args["verb"] is not None:
        logger.setLevel(args["verb"])
    else:
        logger.setLevel(logging.WARNING)
    logger.info(os.path.basename(__file__) + ' version: ' + __version__)

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
    gammax = [ x  - dd / 2 for x in topx[1:]]
    gammay = [ y  - dd / 2 for y in topy[1:]]
    gammaz = np.sqrt(dzdx ** 2 + dzdy ** 2)[1:, 1:]

    gamma = {'x': gammax, 'y':gammay, 'z': gammaz}
    logging.info('max: 1:%f' % (1 / np.nanmax(gammaz)))

    dots = np.full(np.shape(gammaz), 2.5)
    dots[gammaz > 1. / 20.] = 1.
    dots[gammaz > 1. / 5.] = -0.5

    if args['plot'] is None or args['plot'] == '-':
        args['plot'] = '__show__'
    elif args['plot'] == '__default__':
        args['plot'] = "steepness0%01d" % args["grid"]

    _tools.common_plot(args, gamma, unit="m/m", topo=topo_path, dots=dots)


# ------------------------------------------------------------------------


if __name__ == "__main__":
    main()
