#!/bin/env python3

import argparse
import logging
import os
import sys

try:
    from . import _tools
    from ._version import __version__
    from . import eap
    from . import fill_timeseries
    from . import input_terrain
    from . import input_weather
    from . import steepness, eap
    from . import plot    
except ImportError:
    import _tools
    from _version import __version__
    import eap
    import fill_timeseries
    import input_terrain
    import input_weather
    import steepness, eap
    import plot    
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
    default = {'hour-begin': 8,
               'hour-end': 16,
               'cycle-file': 'cycle.yaml',
               'holiday-week': [25, 26, 27, 28, 29, 30, 52],
               'holiday-month': [7],
               'working_dir': '.'
               }
    parser = argparse.ArgumentParser(description='austatools')
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

    pars_fts = subparsers.add_parser(
        name='fill-timeseries',
        aliases=['ft'],
        help='fill source-strength columns in "zeitreihe.dmna"'
    )
    sched = pars_fts.add_mutually_exclusive_group(required=True)
    sched.add_argument('-l', '--list',
                       action='store_const', dest='action', const='list',
                       help='list source column IDs in file' +
                            'and exit without modifying ' +
                            '"zeitreihe.dmna". [default]')
    sched.add_argument('-c', '--cycle',
                       action='store_const', dest='action', const='cycle',
                       help='use production cycle from file')
    sched.add_argument('-w', '--week-5',
                       action='store_const', dest='action', const='week-5',
                       help='source active Mon-Fri')
    sched.add_argument('-W', '--week-6',
                       action='store_const', dest='action', const='week-6',
                       help='source active Mon-Sat')
    pars_fts.add_argument('-b', '--hour-begin', metavar='HOUR',
                          nargs=1,
                          help='daily work begin time in hours 0-23. ' +
                               'Only relevant with -w or -W. ' +
                               '[%02i]' % default['hour-begin'],
                          default=default['hour-begin'])
    pars_fts.add_argument('-e', '--hour-end', metavar='HOUR',
                          nargs=1,
                          help='daily work end time in hours, ' +
                               '0-23. Only relevant with -w or -W .' +
                               '[%02i]' % default['hour-end'],
                          default=default['hour-end'])
    hold = pars_fts.add_mutually_exclusive_group()
    hold.add_argument('-u', '--holiday-week', nargs="+",
                      help='work-free weeks 1-52 as space-delimited list. ' +
                           'Only relevant with -w or -W. [' +
                           ' '.join(['%d' % x
                                     for x in default['holiday-week']]) +
                           ']',
                      default=default['holiday-week'])
    hold.add_argument('-U', '--holiday-month', nargs="+",
                      help='work-free months as space-delimited list' +
                           '(1-12). Only relevant with -w or -W. ' +
                           ' '.join(['%d' % x
                                     for x in default['holiday-month']]) +
                           ']',
                      default=default['holiday-month'])
    pars_fts.add_argument('-f', '--cycle-file',
                          help='emission-cycle description file. ' +
                               'only relevant with -c. ' +
                               '[%s]' % default['cycle-file'],
                          default=default['cycle-file'])
    pars_fts.add_argument('-s', '--source-id', nargs=1,
                          help='source ID. ' +
                               'Required if more than one source. ' +
                               'list IDs in file with -l.',
                          default=None)
    pars_fts.add_argument('-o', '--output', nargs=1,
                          help='output of the source in g/s. ' +
                               '-o is relevant with -w or -W. ',
                          default=None)

    # ----------------------------------------------------

    default_source = input_weather.KNOWN_SOURCES[0]
    default_year = 2020
    #
    # command line args
    #
    pars_wea = subparsers.add_parser(
        name='weather',
        help='Extract amospheric time series for AUSTAL ' +
             'from various sources'
    )
    pars_wea.add_argument(dest="output", metavar="NAME", nargs='?',
                          help="file name to store data in."
                          )
    wea_pos = pars_wea.add_mutually_exclusive_group()
    wea_pos.add_argument('-L', '--ll',
                         metavar=("LAT", "LON"),
                         dest="ll",
                         nargs=2,
                         default=None,
                         help='Center position given as Latitude and ' +
                              'Longitude, respectively. ' +
                              'This is the default.')
    wea_pos.add_argument('-G', '--gk',
                         metavar=("X", "Y"),
                         dest="gk",
                         nargs=2,
                         default=None,
                         help='Center position given in Gauß-Krüger ' +
                              'zone 3 coordinates: ' +
                              'X = `Rechtswert`, ' +
                              'Y = `Hochwert`. ')
    wea_pos.add_argument('-U', '--utm',
                         metavar=("X", "Y"),
                         dest="ut",
                         nargs=2,
                         default=None,
                         help='Center position given in UTM coordinates: ' +
                              'X = `easting`, ' +
                              'Y = `northing`.')
    wea_pos.add_argument('-D', '--dwd',
                         metavar="NUMBER",
                         dest="dwd",
                         help='Weather station position with ' +
                              'German weather service (DWD) ID `NUMBER`')
    wea_pos.add_argument('-W', '--wmo',
                         metavar="NUMBER",
                         dest="wmo",
                         help='Postion of weather station with ' +
                              'World Meteorological Organization (WMO)' +
                              'station ID `NUMBER`')
    pars_wea.add_argument('-s', '--source',
                        metavar="CODE",
                        nargs=None,
                        choices=input_weather.KNOWN_SOURCES,
                        default=default_source,
                        help='select the source for the weather data. ' +
                             'Known ``CODE`` values are ' +
                             ' '.join(input_weather.KNOWN_SOURCES) + ' ' +
                             'Defaults to ' + default_source)
    pars_wea.add_argument('-y', '--year', dest='year',
                        metavar='YEAR',
                        nargs=None,
                        help='year of interest [%04i]' % default_year)

    pars_wea.add_argument('-e', '--elevation', dest='ele',
                        metavar='METERS',
                        help='surface elevation. ' +
                             'only allowed with -L, -G, -U.')

    # pars_wea.add_argument('-w', '--station', dest='station',
    #                     metavar='ID',
    #                     default=None,
    #                     help='weather station ID. ' +
    #                          'only allowed with -D, -W.')

    pars_wea.add_argument('-p', '--precip', dest='prec',
                        action='store_true',
                        help='add precipitation columns to output file')

    # ----------------------------------------------------

    default_dem = input_terrain.KNOWN_DEMS[0]
    default_extent = 6.

    pars_ter = subparsers.add_parser(
        name='terrain',
        help='generate terrain input for AUSTAL'
    )
    pars_ter.add_argument(dest="output", metavar="NAME",
                          help="file name to store data in.",
                          )
    ter_pos = pars_ter.add_mutually_exclusive_group(required=True)
    ter_pos.add_argument('-L', '--ll',
                         metavar=("LAT", "LON"),
                         dest="ll",
                         nargs=2,
                         default=None,
                         help='Center position given as Latitude and ' +
                              'Longitude, respectively. ' +
                              'This is the default.')
    ter_pos.add_argument('-G', '--gk',
                         metavar=("X", "Y"),
                         dest="gk",
                         nargs=2,
                         default=None,
                         help='Center position given in Gauß-Krüger zone 3' +
                              'coordinates: X = `Rechtswert`, ' +
                              'Y = `Hochwert`. ')
    ter_pos.add_argument('-U', '--utm',
                         metavar=("X", "Y"),
                         dest="ut",
                         nargs=2,
                         default=None,
                         help='Center position given in UTM Zone 32N' +
                              'coordinates: X = `easting`, ' +
                              'Y = `northing`.')

    pars_ter.add_argument('-s', '--source',
                          metavar="CODE",
                          nargs=None,
                          choices=input_terrain.KNOWN_DEMS,
                          default=default_dem,
                          help='code for the source digital elevation ' +
                               'model (DEM). Known DEMs are: ' +
                               ' '.join(input_terrain.KNOWN_DEMS) + ' ' +
                               'Defaults to ' + default_dem)
    pars_ter.add_argument('-e', '--extent',
                          metavar="KM",
                          nargs=None,
                          default=default_extent,
                          help='extent of the extracted area in km ' +
                               '(side length of the sqare)' +
                               'Defaults to {}'.format(default_extent))

    # ----------------------------------------------------

    pars_ste = subparsers.add_parser(
        name="steepness",
        description='Plot AUSTAL topography steepness'
    )
    pars_ste.add_argument('-g', '--grid',
                          metavar='ID',
                          nargs='?',
                          default=0,
                          help='ID (number) of the grid to evaluate. '
                               'Defaults to 0')
    pars_ste = _tools.add_arguents_common_plot(pars_ste)

    # ----------------------------------------------------

    pars_eap = subparsers.add_parser(
        name='eap',
        description='find substitute anemometer position ' +
                    'according to VDI 3783 Part 16 ' +
                    'from a wind library generated by austal')
    pars_eap.add_argument('-g', '--grid',
                          metavar='ID',
                          nargs='?',
                          default=0,
                          help='ID (number) of the grid to evaluate. '
                               'Defaults to 0')
    pars_eap.add_argument('-z', '--height',
                          metavar='METERS',
                          nargs='?',
                          default=None,
                          help='effective anemometer height, i.e. height ' +
                               'to evaluate EAP at in m. '
                               'Defaults to 10.0')
    pars_eap.add_argument('-r', '--reference',
                          default='simple',
                          choices=['simple', 'file', 'austal'],
                          help='choose kind of reference profile. ' +
                               '`simple` produces a log wind profile, ' +
                               '`file` reads reference profile from file. ' +
                               'Defaults to `simple`')
    pars_eap.add_argument('-q', '--report',
                          action='store_true',
                          help='show detailed results')
    pars_eap.add_argument('--edge-nodes',
                          default=eap.N_EGDE_NODES,
                          nargs='?',
                          help='number of edge nodes along each side, ' +
                               'where data are exluded. ' +
                               'Defaults to %i' % eap.N_EGDE_NODES)
    pars_eap.add_argument('--max-height',
                          default=eap.MAX_HEIGHT,
                          nargs='?',
                          help='maximum height to evaluate EAP. ' +
                               'Defaults to %f' % eap.MAX_HEIGHT)
    pars_eap.add_argument('--min-ff',
                          default=eap.MIN_FF,
                          nargs='?',
                          help='minimum wind speed below which data are '
                               'exluded. ' +
                               'Defaults to %f' % eap.MIN_FF)
    pars_eap = _tools.add_arguents_common_plot(pars_eap)

    # ----------------------------------------------------
    plot = subparsers.add_parser(
        name='plot',
        description='plot AUSTAL output data')
    plot.add_argument(dest="file", metavar="DATA",
                      help="data file to plot."
                      )
    plot.add_argument('-s', '--stdvs',
                      metavar="STDVs",
                      nargs='?',
                      default=0.,
                      const=1.,
                      help='hash areas where the data are not ' +
                           'significant. Sigingicant is defined as ' +
                           'larder than `STDVs` times the standard ' +
                           'deviation caculated by austal. ' +
                           'If missing, `STDVs` defaults to 1.0.')

    plot.add_argument("--version",
                      version="%(prog)s " + str(__version__),
                      action="version")

    plot = _tools.add_arguents_common_plot(plot)

    # ----------------------------------------------------

    parser.add_argument('working_dir',
                        metavar='PATH',
                        help='woking directory '
                             '[%s]' % default['working_dir'],
                        default=default['working_dir'])
    return parser


# ----------------------------------------------------


# noinspection SpellCheckingInspection
def main():
    # defaults
    parser = cli_parser()
    args = vars(parser.parse_args())
    logger.debug('args: %s' % args)
    #
    # logging level
    #
    if args["verb"] is not None:
        logger.setLevel(args["verb"])
    else:
        logger.setLevel(logging.WARNING)
    logger.info(os.path.basename(__file__) + ' version: ' + __version__)

    if args["working_dir"] is None:
        raise ValueError('PATH not given')

    try:
        if args['command'] == 'eap':
            eap.main(args)
        elif args['command'] == 'fill-timeseries':
            fill_timeseries.main(args)
        elif args['command'] == 'terrain':
            input_terrain.main(args)
        elif args['command'] == 'weather':
            input_weather.main(args)
        elif args['command'] == 'plot':
            plot.main(args)
        elif args['command'] == 'steepness':
            steepness.main(args)
        #else:
         #   raise ValueError('unknown command: %s' % args['command'])
    except UsageError as e:
        parser.print_usage()
        print(str(e))
        sys.exit(2)

# ----------------------------------------------------


if __name__ == "__main__":
    main()
