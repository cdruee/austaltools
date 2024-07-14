#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Mar 20 09:57:48 2022

@author: clemens
"""
import logging
import argparse
import glob
import os
import sys

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    try:
        from . import input_weather, input_terrain
    except ImportError:
        import input_weather, input_terrain

    try:
        from ._tools import ll2gk
    except ImportError:
        from _tools import ll2gk

    try:
        from . import _corine
    except ImportError:
        import _corine

try:
    from ._version import __version__, __title__
except ImportError:
    from _version import __version__, __title__


logging.basicConfig()
logger = logging.getLogger()
# -------------------------------------------------------------------------


def cli_parser():
    """
    funtion to parse command line arguments
    :return: parser object
    :rtype: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        description='Convenience command to produce AUSTAL input')
    parser.add_argument(dest="lat", metavar="LAT",
                        help='Center position latitude',
                        nargs=None
                        )
    parser.add_argument(dest="lon", metavar="LON",
                        help='Center position longitude',
                        nargs=None
                        )
    parser.add_argument(dest="output", metavar="NAME",
                        help="Stem for file names.",
                        nargs=None
                        )
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

    # set logging level
    if args['verb'] is not None:
        logger.setLevel(args['verb'])
    else:
        logger.setLevel(logging.WARNING)

    if (args['output'] is None and args['sources'] is None):
        parser.print_help()
        logger.critical('NAME is required with -L, -G, -U, -D or -W')
        sys.exit(1)

    print(os.path.basename(__file__) + ' version: ' + __version__)
    #
    # call weather
    #
    print('collecting weather data')
    #
    # collect args
    w_args = {x: args[x] for x in ['verb', 'output']}
    for x in ['dwd', 'gk', 'ut', 'sources', 'ele']:
        w_args[x] = None
    w_args['ll'] = [args['lat'], args['lon']]
    w_args['source'] = 'ERA5'
    w_args['year'] = 2000
    w_args['prec'] = False
    w_args['station'] = None
    # call program
    austal_weather.austal_weather(w_args)
    # select one output file, simply file name, remove the rest
    pick = 'kms'
    file_to_pick = ("%s_%s_%04i_%s.%s" %
                    (w_args['source'].lower(), w_args['output'].lower(),
                     int(w_args['year']), pick, 'akterm'))
    rename = '%s.akterm' % args['output']
    logger.info('picking output file: %s -> %s' % (file_to_pick, rename))
    os.rename(file_to_pick, '%s.akterm' % args['output'])
    for x in  glob.glob(file_to_pick.replace(pick, '*')):
        logger.info('discarding output file: %s' % x)
        os.remove(x)
    #
    # call terrain
    #
    # collect args
    t_args = {x: args[x] for x in ['verb', 'output']}
    for x in ['gk', 'ut', 'sources', 'ele']:
        t_args[x] = None
    t_args['ll'] = [args['lat'], args['lon']]
    t_args['source'] = "DGM25-RP"
    t_args['extent'] = 6.
    # call program
    austal_terrain.austal_terrain(t_args)
    # remove confusing extra files
    for x in ['grid.aux.xml', 'prj']:
        file_to_remove = args['output'] + '.' + x
        if os.path.isfile(file_to_remove):
            os.remove(file_to_remove)
    #
    # write coordinates to txt file
    #
    with open(args['output'] + '.txt', 'w') as f:
        lat, lon = float(args['lat']), float(args['lon'])
        f.write('%s %s : Reference Position\n' % (lat, lon))
        x, y, _ = ll2gk(lat, lon)
        f.write('%.0f %.0f : Gauss-Krueger Coordinates\n' % (x, y))
        z0 = _corine.mean_roughness(x, y, 20.)
        f.write('%.1f : z0 at position of wind measurement\n' % z0)




# -------------------------------------------------------------------------
# initialize: call main routine
if __name__ == "__main__":
    main()
