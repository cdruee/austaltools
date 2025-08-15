#!/bin/env python3

import argparse
import logging
import os
import sys

try:
    from . import _tools
    from ._metadata import __version__, __title__
    from . import _storage
    from . import import_buildings
    from . import eap
    from . import fill_timeseries
    from . import heating
    from . import input_terrain
    from . import input_weather
    from . import steepness
    from . import simple
    from . import transform
    from . import plot
    from . import windfield
    from . import windrose
except ImportError:
    import _tools
    from _version import __version__, __title__
    import _storage
    import import_buildings
    import eap
    import fill_timeseries
    import heating
    import input_terrain
    import input_weather
    import simple
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
    verb.add_argument('--insane',
                      dest='verb',
                      action='store_const',
                      const=5, help=argparse.SUPPRESS)
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

    for subcmd in [
        import_buildings,
        eap,
        fill_timeseries,
        heating,
        plot,
        simple,
        steepness,
        input_terrain,
        transform,
        input_weather,
        windfield,
        windrose,
    ]:
        _ = subcmd.add_options(subparsers)

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
    # set logging level
    logginglevel_name={
        logging.DEBUG: 'DEBUG',
        logging.INFO: 'INFO',
        logging.WARNING: 'WARNING',
        logging.ERROR: 'ERROR',
        logging.CRITICAL: 'CRITICAL'
    }
    if (args.get('verb',None) is not None
            and args.get('verb') != logger.getEffectiveLevel()):
        logger.setLevel(args.get('verb'))
        logger.warning(f"changed logging level to '%s'" %
                       logginglevel_name[args.get('verb')])
    #
    if logger.getEffectiveLevel() >= logging.DEBUG:
        # suppress too frequend debug output unlsess --insane
        logging.getLogger('austaltools._dispersion').setLevel(logging.INFO)
    elif logger.getEffectiveLevel() >= logging.INFO:
        # reduce the amount of traceback
        sys.tracebacklimit = 1
    elif logger.getEffectiveLevel() >= logging.WARNING:
        # switch off traceback
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
            simple.main(args)
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
