#!/bin/env python3

import argparse
import glob
import logging
import os
import sys

import austaltools._geo

try:
    from . import _tools
    from ._version import __version__, __title__
    from . import _corine
    from . import _storage
    from . import import_buildings
    from . import eap
    from . import fill_timeseries
    from . import heating
    from . import input_terrain
    from . import input_weather
    from . import steepness
    from . import transform
    from . import plot
    from . import windfield
    from . import windrose
except ImportError:
    import _tools
    from _version import __version__, __title__
    import _corine
    import _storage
    import import_buildings
    import eap
    import fill_timeseries
    import heating
    import input_terrain
    import input_weather
    import steepness
    import transform
    import plot
    import windfield
    import windrose

# ----------------------------------------------------

logging.basicConfig()
logger = logging.getLogger()

# ----------------------------------------------------

class UsageError(Exception):
    pass

# ----------------------------------------------------

def cli_parser():
    """
    funtion to parse command line arguments
    :return: parser object
    :rtype: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(description=__title__)
    parser.add_argument("--version",
                        version=f"{parser.prog} {__version__}",
                        action="version")
    verb = parser.add_mutually_exclusive_group()
    verb.add_argument('--debug',
                      dest='verb',
                      action='store_const',
                      const=logging.DEBUG, help='show informative output')
    verb.add_argument('-v', '--verbose',
                      dest='verb',
                      action='store_const',
                      const=logging.INFO, help='show detailed output')
    subparsers = parser.add_subparsers(help='sub-commands help',
                                       dest='command',
                                       required=True,
                                       metavar='COMMAND')

    # ------------------------------------------------------------

    pars_bldg = import_buildings.add_options(subparsers)

    # ----------------------------------------------------

    pars_eap = eap.add_options(subparsers)

    # ----------------------------------------------------

    pars_fts = fill_timeseries.add_options(subparsers)

    # ----------------------------------------------------

    pars_htg = heating.add_options(subparsers)

    # ----------------------------------------------------

    pars_plot = plot.add_options(subparsers)

    # ----------------------------------------------------

    pars_sim = subparsers.add_parser(
        name="simple",
        help='simple-to-use interface '
             'to the most basic funtionality of `austaltools`:'
             'the creation of input files for simulations'
    )
    pars_sim.add_argument(dest="lat", metavar="LAT",
                        help='Center position latitude',
                        nargs=None
                        )
    pars_sim.add_argument(dest="lon", metavar="LON",
                        help='Center position longitude',
                        nargs=None
                        )
    pars_sim.add_argument(dest="output", metavar="NAME",
                        help="Stem for file names.",
                        nargs=None
                        )

    # ----------------------------------------------------

    pars_ste = steepness.add_options(subparsers)

    # ----------------------------------------------------

    pars_ter = input_terrain.add_options(subparsers)

    # ----------------------------------------------------

    pars_transf = transform.add_options(subparsers)

    # ----------------------------------------------------

    pars_wea = input_weather.add_options(subparsers)

    # ----------------------------------------------------

    pars_wif = windfield.add_options(subparsers)

    # ----------------------------------------------------

    pars_wrs = windrose.add_options(subparsers)

    # ----------------------------------------------------

    parser.add_argument('-d','--working-dir',
                        dest='working_dir',
                        metavar='PATH',
                        help='woking directory '
                             '[%s]' % _tools.DEFAULT_WORKING_DIR,
                        default=_tools.DEFAULT_WORKING_DIR)
    parser.add_argument('--temp-dir',
                        dest='temp_dir',
                        metavar='PATH',
                        help='directory where temporary files'
                             'are stored. None means use system'
                             'temporary files dir. [None]',
                        default=None)
    return parser

# ----------------------------------------------------

def simple(args):
    print(os.path.basename(__file__) + ' version: ' + __version__)
    #
    # get customized defaults from config
    #
    conf = _storage.read_config()
    simple_conf = conf.get('simple', {})
    w_source = simple_conf.get(
        'weather', _storage.SIMPLE_DEFAULT_TERRAIN)
    w_year = int(simple_conf.get(
        'year', _storage.SIMPLE_DEFAULT_YEAR))
    t_source = simple_conf.get(
        'terrain', _storage.SIMPLE_DEFAULT_TERRAIN)
    t_extent = float(simple_conf.get(
        'extent', _storage.SIMPLE_DEFAULT_EXTENT))
    #
    args['ele'] = _tools.estimate_elevation(args['lat'], args['lon'])
    #
    # call weather
    #
    print('collecting weather data')
    #
    # collect args
    w_args = {x: args[x] for x in ['verb', 'output']}
    for x in ['dwd', 'gk', 'ut', 'sources']:
        w_args[x] = None
    w_args['ll'] = [args['lat'], args['lon']]
    w_args['ele'] = args['ele']
    w_args['source'] = w_source
    w_args['year'] = w_year
    w_args['prec'] = False
    w_args['station'] = None
    # call program
    input_weather.austal_weather(w_args)
    # select one output file, simply file name, remove the rest
    pick = 'kms'
    file_to_pick = ("%s_%s_%04i_%s.%s" %
                    (w_args['source'].lower(), w_args['output'].lower(),
                     int(w_args['year']), pick, 'akterm'))
    rename = '%s.akterm' % args['output']
    logger.info('picking output file: %s -> %s' % (file_to_pick, rename))
    os.rename(file_to_pick, '%s.akterm' % args['output'])
    for x in glob.glob(file_to_pick.replace(pick, '*')):
        logger.info('discarding output file: %s' % x)
        os.remove(x)
    #
    # call terrain
    #
    print('collecting terrain data')
    # collect args
    t_args = {x: args[x] for x in ['verb', 'output']}
    for x in ['gk', 'ut', 'sources', 'ele']:
        t_args[x] = None
    t_args['ll'] = [args['lat'], args['lon']]
    t_args['source'] = t_source
    t_args['extent'] = t_extent
    # call program
    input_terrain.main(t_args)
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
        x, y, _ = austaltools._geo.ll2gk(lat, lon)
        f.write('%.0f %.0f : Gauss-Krueger Coordinates\n' % (x, y))

        print('getting averaged surface roughness')
        z0 = _corine.roughness_austal(x, y, 20.)
        if z0 is None:
            z0 = _corine.roughness_web(x, y, 20.)
        f.write('%.1f : z0 at position of wind measurement\n' % z0)

    print('done.')

# ----------------------------------------------------

# noinspection SpellCheckingInspection
def main(args=None):
    #
    # defaults
    if args is None:
        parser = cli_parser()
        args = vars(parser.parse_args())
    else:
        parser = None
    logger.debug('args: %s' % args)
    #
    # logging level
    #
    if args["verb"] is not None:
        logger.setLevel(args["verb"])
    else:
        logger.setLevel(logging.WARNING)
    # reduce amount of traceback
    if logger.getEffectiveLevel() >= logging.INFO:
        sys.tracebacklimit = 1
    elif logger.getEffectiveLevel() >= logging.WARNING:
        sys.tracebacklimit = 0

    logger.info(os.path.basename(__file__) + ' version: ' + __version__)

    if args.get("working_dir", None) is None:
        raise ValueError('PATH not given')

    logger.debug('args: %s' % args)

    if args.get("temp_dir",None) is not None:
        _storage.TEMP = args["temp_dir"]

    try:
        if args['command'] in ['import-buildings', 'bg']:
            import_buildings.main(args)
        elif args['command'] == 'eap':
            eap.main(args)
        elif args['command'] in ['fill-timeseries', 'ft']:
            fill_timeseries.main(args)
        elif args['command'] == 'heating':
            heating.main(args)
        elif args['command'] == 'plot':
            plot.main(args)
        elif args['command'] == 'simple':
            simple(args)
        elif args['command'] == 'steepness':
            steepness.main(args)
        elif args['command'] == 'terrain':
            input_terrain.main(args)
        elif args['command'] == 'transform':
            transform.main(args)
        elif args['command'] == 'weather':
            input_weather.main(args)
        elif args['command'] == 'windfield':
            windfield.main(args)
        elif args['command'] == 'windrose':
            windrose.main(args)
        #else:
         #   raise ValueError('unknown command: %s' % args['command'])
    except UsageError as e:
        if parser is not None:
            parser.print_usage()
        print(str(e))
        sys.exit(2)

# ----------------------------------------------------


if __name__ == "__main__":
    main()
