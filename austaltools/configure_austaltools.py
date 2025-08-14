#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
"""
import argparse
import logging
import os

from . import _datasets as DS
from . import _storage
from . import _tools
from ._metadata import __version__

logging.basicConfig()
logger = logging.getLogger()

# -------------------------------------------------------------------------

def list_datasets(only='all', state='known', long=False):
    """
    Print a list of all known or available datasets
    contaimning terrain or weather or both

    :param only: kind of datasets to print:
      `terrain` or `weather` or `all` (default)
    :type only: str
    :param state: which datasets to print:
        'available' or 'known' (default)
    :type state: str
    :param long: print short (``False``) or long (``True``, default) list
    :type long: bool
    """
    if long:
        lfmt = "| %-14s | %6s | %6s | %s"
        print(lfmt % (' Dataset      ', 'online',
                      'avail.', 'path'))
        print(lfmt % ('--------------', '------',
                      '------', '-------------'))
        for name, props in DS.dataset_list().items():
            if (only in [props['storage'], 'all'] and
                    (state == 'known' or props['available'])):
                if props['uri'] is not None:
                    dl_str = ' Yes  '
                else:
                    dl_str = ' No   '
                if props['available']:
                    pr_str = ' Yes  '
                    pa_str = props['path']
                else:
                    pr_str = ' No   '
                    pa_str = ''
                print(lfmt % (name, dl_str, pr_str, pa_str))
    else:
        names=[]
        for name, props in DS.dataset_list().items():
            if (only in [props['storage'], 'all'] and
                    (state == 'known' or props['available'])):
                names.append(name)
        print(" ".join(names))

# -------------------------------------------------------------------------

def set_austaldir(args: dict):
    """
    Set the Austal directory path based on user input or search criteria.

    This function sets the directory path for Austal based on
    user-provided arguments. It can either use a direct path given by the
    user or search within a directory tree for specific AUSTAL related
    files to determine the path. If no arguments are provided,
    it displays the current setting.

    :param args: The dictionary containing parsed command line arguments:
                 - 'path': A direct path provided by the user.
                 - 'find': A directory path to search within for AUSTAL.

    :type args: dict

    :raises EnvironmentError:
      If no Austal installation is found during the search.
    :raises ValueError: If the provided or chosen path does not exist.

    If a path is provided via 'path', it will be used directly. If 'find'
    is specified, a search for Austal's executable or related files is
    performed within the directory tree, and the user may be prompted to
    select the correct path if multiple candidates are found. The function
    saves the new setting if a valid path is determined.
    """
    conf = _storage.read_config()

    if args.get('path', None) is not None:
        # path given by user
        path = args['path']
    elif args.get('find', None) is not None:
        # search in directory tree given by user
        path_list = []
        sp = _tools.Spinner(step=100)
        for dirpath, _, filenames in list(os.walk(args['find'])):
            sp.spin()
            for filename in filenames:
                if filename in ['austal', 'austal.exe',
                                'taldia', 'taldia.exe',
                                'z0-gk.dmna', 'z0-utm.dmna']:
                    if not dirpath in path_list:
                        path_list.append(dirpath)
        sp.end()
        if len(path_list) == 0:
            
            raise EnvironmentError('No austal installation found.')
        elif len(path_list) > 1:
            num = -1
            for i, p in enumerate(path_list):
                print("%2i: %s" % (i, p))
            while num not in range(len(path_list)):
                num = int(input("input the number of your "
                                "preferred path: "))
            path = path_list[num]
        else:
            path = path_list[0]
    else:
        # show current setting
        path = conf.get('austaldir', None)
        if path is None:
            path = "(not set)"
        print("austaldir: %s" % path)
        return

    # save setting
    if not os.path.isdir(path):
        raise ValueError(f"Path does not exist: {path}")
    conf['austaldir'] = path
    _storage.write_config(conf)


# -------------------------------------------------------------------------

def set_simple(args: dict):
    """
    Set configuration for austaltools simple.

    This function updates the weather, year, terrain, and extent settings
    by checking the provided `args` dictionary. If the values are not
    assigned new values in `args`, and if not present in the config file,
    pre-defined defaults are used.

    :param args: The dictionary containing parsed command line arguments:
                 - 'simple_weather':
                   Desired weather source (must be in `DS.SOURCES_WEATHER`).
                 - 'simple_year':
                   Desired year for the weather source.
                 - 'simple_terrain':
                   Desired terrain source (must be in `DS.SOURCES_TERRAIN`).
                 - 'simple_extent':
                   Desired extent for the terrain source.

    :type args: dict

    :raises ValueError: If 'simple_weather' or 'simple_terrain'
        in `args` is not recognized.
    """
    conf = _storage.read_config()
    simple_conf = conf.get('simple', {})

    if args.get('simple_weather',None) is not None:
        weather = args.get('simple_weather')
        if weather not in DS.SOURCES_WEATHER:
            
            raise ValueError(f"unknwon weather source {weather}")
    elif 'weather' in simple_conf:
        weather =  simple_conf.get('weather')
    else:
        weather = _storage.SIMPLE_DEFAULT_WEATHER

    if args.get('simple_year',None) is not None:
        year = args.get('simple_year')
    elif 'year' in simple_conf:
        year = simple_conf.get('year')
    else:
        year = _storage.SIMPLE_DEFAULT_YEAR
    sourcename = DS.name_yearly(weather, year)

    if not DS.dataset_available(sourcename):
        logger.error(f"selected weather source {sourcename} "
                     f"is not available")

    if args.get('simple_terrain',None) is not None:
        terrain = args.get('simple_terrain')
        if terrain not in DS.SOURCES_TERRAIN:
            
            raise ValueError(f"unknwon terrain source {terrain}")
    elif 'terrain' in simple_conf:
        terrain =  simple_conf.get('terrain')
    else:
        terrain = _storage.SIMPLE_DEFAULT_TERRAIN

    if not DS.dataset_available(terrain):
        logger.error(f"selected terrain source {terrain} "
                     f"is not available")

    if args.get('simple_extent',None) is not None:
        extent = args.get('simple_extent')
    elif 'extent' in simple_conf:
        extent =  simple_conf.get('extent')
    else:
        extent = _storage.SIMPLE_DEFAULT_EXTENT

    if all([args.get(f'simple_{x}', None) is None
                for x in ['weather', 'year', 'terrain', 'extent']]):
        # show current setting
        print("weather source: %s" % weather)
        print("weather year  : %s" % str(year))
        print("terrain source: %s" % terrain)
        print("terrain extent: %s" % str(extent))

    else:
        # save setting
        if not 'simple' in conf:
            conf['simple'] = {}
        conf['simple']['weather'] = weather
        conf['simple']['year'] = year
        conf['simple']['terrain'] = terrain
        conf['simple']['extent'] = extent
        _storage.write_config(conf)


# -------------------------------------------------------------------------

def cli_parser():
    """
    funtion to parse command line arguments
    :return: parser object
    :rtype: argparse.ArgumentParser
    """

    default_dem = DS.SOURCES_TERRAIN[0]

    parser = argparse.ArgumentParser(
        description="Prepare modify datasets used by austaltools",
    )
    verb = parser.add_mutually_exclusive_group()
    verb.add_argument('--debug', dest='verb', action='store_const',
                      const=logging.DEBUG, help='show informative output')
    verb.add_argument('-v', '--verbose', dest='verb', action='store_const',
                      const=logging.INFO, help='show detailed output')
    parser.add_argument('--version',
                        version="%(prog)s " + str(__version__),
                        action="version")
    subparsers = parser.add_subparsers(dest='action',
                                       metavar='COMMAND',
                                       required=True
                                       )

    sub_assm = subparsers.add_parser('assemble',
                                     help='assemble dataset from original ' +
                                     'data source. \n' +
                                     'WARNING: This may take a ' +
                                     'LONG time and may require excessive ' +
                                     'memory and disk space.'
                                     )
    sub_assm.add_argument('-s', '--source',
                          metavar="CODE",
                          nargs=None,
                          choices=DS.SOURCES_TERRAIN + DS.SOURCES_WEATHER,
                          default=default_dem,
                          help='code for the source digital elevation ' +
                               'model (DEM). Known DEMs are: ' +
                               ' '.join(DS.SOURCES_TERRAIN) + ' ' +
                               'Defaults to ' + default_dem)
    sub_assm.add_argument('-y', '--years',
                          metavar="YEAR",
                          help='Year for which to generate weather data.' +
                               ' A range of years may be given as ' +
                               '<start year>-<end year>. ' +
                               'No default, required with ' +
                               'weather datasets.')
    sub_assm.add_argument('-p', '--path',
                          metavar="PATH",
                          default=None,
                          help='create files in PATH instead of one ' +
                               'of the default locations. Note: ' +
                               'data downloaded to a custom PATH are ' +
                               'not considered by austaltools by default.')

    sub_assm.add_argument('-f', '--force',
                          action='store_true',
                          help='overwrite dataset if it exists.'
                               'If dataset exists in a system-wide ' +
                               'installation, it might be downloaded ' +
                               'to the user directory (again), where ' +
                               'it takes higher preference.')


    sub_ast = subparsers.add_parser('austal',
                                     help='set/show location of the austal '
                                          'installation. If none of '
                                          '`path` of `find` is given,'
                                          'the current setting is shwon.')
    sub_ast_how = sub_ast.add_mutually_exclusive_group()
    sub_ast_how.add_argument('-p', '--path',
                          metavar="PATH",
                          default=None,
                          help='directory where the austal executable'
                               'is stored.')
    sub_ast_how.add_argument('-f', '--find',
                          metavar="PATH",
                          default=None,
                          help='recursively search this directory '
                               'for the austal executable.')

    sub_down = subparsers.add_parser('download',
                                     help='download pre-assembled dataset '
                                          'from a location configured '
                                          'for the dataset.')
    sub_down.add_argument('-s', '--source',
                          metavar="CODE",
                          nargs=None,
                          choices=DS.SOURCES_TERRAIN + DS.SOURCES_WEATHER,
                          default=default_dem,
                          help='code for the source digital elevation ' +
                               'model (DEM). Known DEMs are: ' +
                               ' '.join(DS.SOURCES_TERRAIN) + ' ' +
                               'Defaults to ' + default_dem)
    sub_down.add_argument('-y', '--years',
                          metavar="YEAR",
                          help='Year for which to download weather data.' +
                               ' A range of years may be given as ' +
                               '<start year>-<end year>. ' +
                               'No default, required with ' +
                               'weather datasets.')
    sub_down.add_argument('-p', '--path',
                          metavar="PATH",
                          default=None,
                          help='download files to PATH instead of one ' +
                               'of the default locations. Note: ' +
                               'data downloaded to a custom PATH are ' +
                               'not considered by austaltools by default.')

    sub_down.add_argument('-f', '--force',
                          action='store_true',
                          help='overwrite dataset if it exists.'
                               'If dataset exists in a system-wide ' +
                               'installation, it might be downloaded ' +
                               'to the user directory (again), where ' +
                               'it takes higher preference.')

    sub_list = subparsers.add_parser('list',
                                     help='list known datasets '
                                          'and show availability and '
                                          'storage locations')
    sub_only_grp = sub_list.add_mutually_exclusive_group()
    sub_only_grp.add_argument('-w', '--weather',
                              dest='only',
                              action='store_const',
                              const='weather',
                              default='all')
    sub_only_grp.add_argument('-t', '--terrain',
                              dest='only',
                              action='store_const',
                              const='terrain',
                              default='all')
    sub_only_grp.add_argument('--all',
                              dest='only',
                              action='store_const',
                              const='all',
                              default='all')
    sub_state_grp = sub_list.add_mutually_exclusive_group()
    sub_state_grp.add_argument('-k', '--known',
                               dest='state',
                               action='store_const',
                               const='known',
                               default='available')
    sub_state_grp.add_argument('--available',
                               dest='state',
                               action='store_const',
                               const='available',
                               default='available')
    sub_list.add_argument('-l', '--long',
                          action='store_true',
                          help='show verbose list instead of just codes')

    sub_scan = subparsers.add_parser('scan',
                                     help='search for known datasets, '
                                          'show availability and '
                                          'storage locations')

    sub_smpl = subparsers.add_parser('simple',
                                   help="change settings for austaltools "
                                        "simple / austal-input. "
                                        "If called without options, "
                                        "the current sinngs are shown.")
    sub_smpl.add_argument('--weather',
                          metavar="CODE",
                          dest='simple_weather',
                          help="select weather source")
    sub_smpl.add_argument('--year',
                          metavar="CODE",
                          dest='simple_year',
                          help="select weather year")
    sub_smpl.add_argument('--terrain',
                          metavar="CODE",
                          dest='simple_terrain',
                          help="select terrain source")
    sub_smpl.add_argument('--extent',
                          metavar="CODE",
                          dest='simple_extent',
                          help="select terrain source")

    sub_sl = subparsers.add_parser('stationlist',
                                   help="generate new stationlist for "
                                        "one of the weather sources")
    sub_sl.add_argument('-s', '--source',
                        metavar="CODE",
                        dest="sl_source",
                        help="Select the respectice source "
                             "from: %(choices)s. [%(default)s]",
                        choices=["DWD"],
                        default="DWD")
    sub_sl.add_argument('-f', '--format',
                        metavar="CODE",
                        dest="sl_format",
                        help="Select the output file format "
                             "from: %(choices)s. [%(default)s]",
                        choices=["csv", "json"],
                        default="json")
    sub_sl.add_argument('-o', '--out',
                        metavar="PATH",
                        dest="sl_out",
                        help="File to write to or None for stdout. [None]",
                        default=None)

    parser.add_argument('--storage',
                        metavar='PATH',
                        default=None,
                        help='custom location for data storage'
                        )
    parser.add_argument('--temp',
                        metavar='PATH',
                        default=None,
                        help='custom location for temp files [/tmp]'
                        )
    parser.add_argument('--noparallel',
                        action='store_true',
                        help='disable parallel execution of downloads.'
                        )
    return parser

# -------------------------------------------------------------------------


def main():
    """
    Command line interface.
    Evaluates the command line arguments from cli_parser()
    performs additional checks and sets the logging level

    :return: configuration values
    :rtype: dict
    """
    parser = cli_parser()
    args = vars(parser.parse_args())

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

    if logger.getEffectiveLevel() <= logging.DEBUG:
        global PROCS
        PROCS = 1

    logger.info(os.path.basename(__file__) + ' version: ' + __version__)

    logger.debug(args)

    if args['temp'] is not None:
        _storage.TEMP = args['temp']

    if args['noparallel'] is True:
        DS.RUNPARALLEL = False

    if args['action'] == 'list':
        list_datasets(args['only'], args['state'], args['long'])

    elif args['action'] == 'scan':
        DS.update_available()

    elif args['action'] == 'stationlist':
        DS.provide_stationlist(source=args["sl_source"],
                               fmt=args["sl_format"],
                               out=args["sl_out"])

    elif args['action'] == 'austal':
        set_austaldir(args)

    elif args['action'] in ['download', 'assemble']:
        if args['source'] in DS.SOURCES_TERRAIN:
            if DS.dataset_available(args['source']) and not args['force']:
                
                raise ValueError(f"dataset exists: {args['source']} ")
            DS.provide_terrain(args['source'],
                               path=args['path'],
                               force=args['force'],
                               method=args['action'])
        elif args['source'] in DS.SOURCES_WEATHER:
            if 'years' not in args:
                
                raise ValueError('-y required with dataset: %s '
                                 % args['source'])
            else:
                try:
                    year_list = _tools.expand_sequence(args['years'])
                except ValueError:
                    raise ValueError("cannot argument to -y: %s" %
                                         args["years"])
                logger.debug('years parsed into int: %s',
                             year_list)
            if args['source'] in DS.dataset_list():
                avl = DS.dataset_available(args['source'])
                if avl and not args['force']:
                    
                    raise ValueError(f"dataset exists: {args['source']} ")
            else:
                for yr in year_list:
                    yn = DS.name_yearly(args['source'], yr)
                    avl = DS.dataset_available(yn)
                    if avl and not args['force']:
                        
                        raise ValueError(f"dataset exists: {yn} ")
            DS.provide_weather(args['source'],
                               path=args['path'],
                               years=year_list,
                               method=args['action'],
                               force=args['force']
                               )
        else:
            raise ValueError("Source not recognized: %s "
                             % args['source'])


    elif args['action'] == 'simple':
        set_simple(args)

    else:
        raise ValueError("Action not recognized: %s "
                         % args['action'])

# -------------------------------------------------------------------------
# initialize and call main routine
if __name__ == "__main__":
    main()
