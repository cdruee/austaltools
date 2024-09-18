#!/bin/env python3

import argparse
import glob
import logging
import os
import sys


try:
    from . import _tools
    from ._version import __version__, __title__
    from . import _corine
    from . import _datasets
    from . import buildings_geojson
    from . import eap
    from . import fill_timeseries
    from . import input_terrain
    from . import input_weather
    from . import steepness
    from . import transform
    from . import plot
    from . import windfield
except ImportError:
    import _tools
    from _version import __version__, __title__
    import _datasets
    import _corine
    import buildings_geojson
    import eap
    import fill_timeseries
    import input_terrain
    import input_weather
    import steepness
    import transform
    import plot
    import windfield
# ----------------------------------------------------

logging.basicConfig()
logger = logging.getLogger()

# ----------------------------------------------------


class UsageError(Exception):
    pass

# ----------------------------------------------------
def add_location_opts(pars,
                      stations=False,
                      required=True):
    loc_opt = pars.add_mutually_exclusive_group(required=required)
    loc_opt.add_argument('-L', '--ll',
                         metavar=("LAT", "LON"),
                         dest="ll",
                         nargs=2,
                         default=None,
                         help='Center position given as Latitude and ' +
                              'Longitude, respectively. ' +
                              'This is the default.')
    loc_opt.add_argument('-G', '--gk',
                         metavar=("X", "Y"),
                         dest="gk",
                         nargs=2,
                         default=None,
                         help='Center position given in Gauß-Krüger zone 3' +
                              'coordinates: X = `Rechtswert`, ' +
                              'Y = `Hochwert`. ')
    loc_opt.add_argument('-U', '--utm',
                         metavar=("X", "Y"),
                         dest="ut",
                         nargs=2,
                         default=None,
                         help='Center position given in UTM Zone 32N' +
                              'coordinates: X = `easting`, ' +
                              'Y = `northing`.')
    if stations:
        loc_opt.add_argument('-D', '--dwd',
                             metavar="NUMBER",
                             dest="dwd",
                             help='Weather station position with ' +
                                  'German weather service (DWD) ID `NUMBER`')
        loc_opt.add_argument('-W', '--wmo',
                             metavar="NUMBER",
                             dest="wmo",
                             help='Postion of weather station with ' +
                                  'World Meteorological Organization (WMO)' +
                                  'station ID `NUMBER`')

    return pars

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

    pars_bldg = subparsers.add_parser(
        name='buildings-geojson',
        aliases=['bg'],
        help="get buildings from geojson and write to `austal.txt`")
    pars_bldg.add_argument('-g', '--geojson',
                           dest='file',
                           help='file containing building info' +
                                '[%s]' % buildings_geojson.DEFAULT_FILE,
                           default=buildings_geojson.DEFAULT_FILE)
    pars_bldg.add_argument('-n', '--dry-run',
                           action="store_true",
                           help='do not change austal.txt, ' +
                                'show changes instead.')
    pars_bldg.add_argument('-t', '--tolerance',
                           help='limit for accepting a polygon '
                                'as rectangle (max difference of the '
                                'lenght of the diagonals) ' +
                                '[%.2f]' % buildings_geojson.DEFT_TOLRANCE,
                           default=buildings_geojson.DEFT_TOLRANCE)
    pars_bldg_hgt = pars_bldg.add_mutually_exclusive_group()
    pars_bldg_hgt.add_argument('-z', '--zvalue',
                        help='name of property that gives building height' +
                             '[%s]' % buildings_geojson.DEFAULT_ZVALUE,
                        default=buildings_geojson.DEFAULT_ZVALUE)
    pars_bldg_hgt.add_argument('-Z', '--height',
                        help='height of all buildings')
    pars_bldg = _tools.add_arguents_common_plot(pars_bldg)

    # ----------------------------------------------------

    pars_eap = subparsers.add_parser(
        name='eap',
        help='find substitute anemometer position ' +
                    'according to VDI 3783 Part 16 ' +
                    'from a wind library generated by AUSTAL')
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
                          help='effective anemometer height, i.e. height '
                               'to evaluate EAP at in m. '
                               'Defaults to 10.0')
    pars_eap.add_argument('-r', '--reference',
                          default='simple',
                          choices=['simple', 'file', 'austal'],
                          help='choose kind of reference profile. '
                               '`simple` produces a log wind profile, '
                               '`file` reads reference profile from file. '
                               'Defaults to `simple`')
    pars_eap.add_argument('-q', '--report',
                          action='store_true',
                          help='show detailed results')
    pars_eap.add_argument('--edge-nodes',
                          default=eap.N_EGDE_NODES,
                          nargs='?',
                          help='number of edge nodes along each side, '
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
                               '[%02i]' % fill_timeseries.DEFAULT_BEGIN,
                          default=fill_timeseries.DEFAULT_BEGIN)
    pars_fts.add_argument('-e', '--hour-end', metavar='HOUR',
                          nargs=1,
                          help='daily work end time in hours, ' +
                               '0-23. Only relevant with -w or -W .' +
                               '[%02i]' % fill_timeseries.DEFAULT_END,
                          default=fill_timeseries.DEFAULT_END)
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
    pars_fts.add_argument('-s', '--source-id',
                          help='source ID. ' +
                               'Required if more than one source. ' +
                               'list IDs in file with -l.',
                          default=None)
    pars_fts.add_argument('-o', '--output', nargs=1,
                          help='output of the source in g/s. ' +
                               '-o is relevant with -w or -W. ',
                          default=None)

    # ----------------------------------------------------
    pars_plot = subparsers.add_parser(
        name='plot',
        help='plot AUSTAL output data')
    pars_plot.add_argument(dest="file", metavar="DATA",
                      help="data file to plot."
                      )
    pars_plot.add_argument('-s', '--stdvs',
                      metavar="STDVs",
                      nargs='?',
                      default=0.,
                      const=1.,
                      help='hash areas where the data are not ' +
                           'significant. Sigingicant is defined as ' +
                           'larder than `STDVs` times the standard ' +
                           'deviation caculated by austal. ' +
                           'If missing, `STDVs` defaults to 1.0.')

    pars_plot.add_argument("--version",
                      version="%(prog)s " + str(__version__),
                      action="version")

    pars_plot = _tools.add_arguents_common_plot(pars_plot)

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
    pars_ste = subparsers.add_parser(
        name="steepness",
        help='Plot AUSTAL topography steepness'
    )
    pars_ste.add_argument('-g', '--grid',
                          metavar='ID',
                          nargs='?',
                          default=0,
                          help='ID (number) of the grid to evaluate. '
                               'Defaults to 0')
    pars_ste = _tools.add_arguents_common_plot(pars_ste)

    # ----------------------------------------------------

    if len(input_terrain.AVAILABLE_DEMS) > 0:
        default_dem = list(input_terrain.AVAILABLE_DEMS)[0]
    else:
        default_dem = None
    default_extent = 6.

    pars_ter = subparsers.add_parser(
        name='terrain',
        help='generate terrain input for AUSTAL'
    )
    pars_ter.add_argument(dest="output", metavar="NAME",
                          help="file name to store data in.",
                          )

    pars_ter = add_location_opts(pars=pars_ter)

    pars_ter.add_argument('-s', '--source',
                          metavar="CODE",
                          nargs=None,
                          choices=input_terrain.AVAILABLE_DEMS,
                          default=default_dem,
                          help='code for the source digital elevation ' +
                               'model (DEM). Known DEMs are: ' +
                               ' '.join(input_terrain.AVAILABLE_DEMS) +
                               ' Defaults to ' + str(default_dem))
    pars_ter.add_argument('-e', '--extent',
                          metavar="KM",
                          nargs=None,
                          default=default_extent,
                          help='extent of the extracted area in km ' +
                               '(side length of the sqare)' +
                               'Defaults to {}'.format(default_extent))

    # ----------------------------------------------------

    pars_transf = subparsers.add_parser(
        name='transform',
        help='transfrom coordinates into other projections')
    pars_transf = add_location_opts(pars_transf, stations=True,
                                    required=False)
    pars_transf.add_argument('-M', '--model',
                         metavar=("x", "y"),
                         dest="xy",
                         nargs=2,
                         default=None,
                         help='Transform position given in model '
                              'coordinats x and y (relative '
                              'to the model origin) into '
                              'geographic coordinates.')


    # ----------------------------------------------------

    default_year = 2020
    #
    # command line args
    #
    pars_wea = subparsers.add_parser(
        name='weather',
        help='Extract atmospheric time series for AUSTAL ' +
             'from various sources'
    )
    pars_wea.add_argument(dest="output", metavar="NAME", nargs='?',
                          help="file name to store data in."
                          )
    pars_wea = add_location_opts(pars_wea, stations=True)
    pars_wea.add_argument('-s', '--source',
                        metavar="CODE",
                        nargs=None,
                        choices=input_weather.KNOWN_SOURCES,
                        default=input_weather.KNOWN_SOURCES[0],
                        help='select the source for the weather data. ' +
                             'Known ``CODE`` values are ' +
                             ' '.join(input_weather.KNOWN_SOURCES) +
                             ' Defaults to ' +
                             input_weather.KNOWN_SOURCES[0])
    pars_wea.add_argument('-y', '--year', dest='year',
                        metavar='YEAR',
                        nargs=None,
                          required=True,
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

    pars_wif = subparsers.add_parser(
        name='windfield',
        help='Plot wind field'
    )
    DEFAULT_WIF_COLORMAP = 'plasma'
    pars_wif.add_argument(dest='style',
                          choices=['stream', 'stream-color',
                                   'arrows', 'arrows-color',
                                   'barbs', 'barbs-color',],
                          help='style of wind field plot')
    pars_wif.add_argument('-c', '--colormap',
                         default=DEFAULT_WIF_COLORMAP,
                         help='name of colormap to use. '
                              'Defaults to "%s"' %
                              DEFAULT_WIF_COLORMAP)
    pars_wif.add_argument('-g', '--grid',
                         default=0,
                         help='number of grid to plot. '
                              'Defaults to 0')
    slice = pars_wif.add_mutually_exclusive_group(required=True)
    slice.add_argument('-a', '--altitude',
                       dest='alt',
                       metavar='ASL',
                       default=None,
                       help='display horizontal slice at ``ASL`` meters '
                            'above sea level. '
                            'Defaults to `None`')
    slice.add_argument('-z', '--height',
                       dest='hgt',
                       metavar='AGL',
                       default=None,
                       help='display horizontal slice at height ``AGT`` '
                            'above ground level. '
                            'Defaults to `None`')
    slice.add_argument('-l', '--level',
                       dest='lvl',
                       metavar='NUMBER',
                       default=None,
                       help='display horizontal slice at model level '
                            'NUMBER (0-based). '
                            'Defaults to `None`')
    wval = pars_wif.add_mutually_exclusive_group(required=True)
    wval.add_argument('-t', '--time',
                      dest='time',
                      metavar='"YYY-MM-DD HH:MM:SS"',
                      default=None,
                      help='display windfield corresponding '
                           'to the wind and stability from akterm '
                           'for the time given by ``YYY-MM-DD HH:MM:SS``. '
                           'Defaults to `None`')
    wval.add_argument('-w', '--wind',
                      dest='wind',
                      metavar='SPEED DIR AK',
                      nargs=3,
                      default=None,
                      help='display windfield corresponding '
                           'to the wind `SPEED`, `DIR`ection and '
                           'stability class `AK`. '
                           'Defaults to `None`')
    wval.add_argument('-W', '--wind-vector',
                      dest='vector',
                      metavar='U V AK',
                      nargs=3,
                      default=None,
                      help='display windfield corresponding '
                           'to the wind vector (`U`, `V`) and '
                           'stability class `AK`. '
                           'Defaults to `None`')
    pars_wif.add_argument('-p', '--plot',
                        metavar="FILE",
                        nargs='?',
                        const='__default__',
                        help='save plot to a file. If `FILE` is "-" ' +
                             'the plot is shown on screen. If `FILE` is ' +
                             'missing, the file name defaults to ' +
                             'the data file name with extension `png`'
                        )
    pars_wif.add_argument('-f', '--force',
                        action='store_true',
                        default=False,
                        help='force overwriting plotfile if it exists.')

    # ----------------------------------------------------

    parser.add_argument('-w','--working-dir',
                        dest='working_dir',
                        metavar='PATH',
                        help='woking directory '
                             '[%s]' % default['working_dir'],
                        default=default['working_dir'])
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
    # call weather
    #
    print('collecting weather data')
    #
    # collect args
    w_args = {x: args[x] for x in ['verb', 'output']}
    for x in ['dwd', 'gk', 'ut', 'sources', 'ele']:
        w_args[x] = None
    w_args['ll'] = [args['lat'], args['lon']]
    w_args['source'] = 'CERRA'
    w_args['year'] = 2003
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
    # collect args
    t_args = {x: args[x] for x in ['verb', 'output']}
    for x in ['gk', 'ut', 'sources', 'ele']:
        t_args[x] = None
    t_args['ll'] = [args['lat'], args['lon']]
    t_args['source'] = "DGM25-RP"
    t_args['extent'] = 6.
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
        x, y, _ = _tools.ll2gk(lat, lon)
        f.write('%.0f %.0f : Gauss-Krueger Coordinates\n' % (x, y))
        z0 = _corine.mean_roughness(x, y, 20.)
        f.write('%.1f : z0 at position of wind measurement\n' % z0)


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

    logger.debug('args: %s' % args)

    if args["temp_dir"] is not None:
        _tools.TEMP = args["temp_dir"]

    try:
        if args['command'] in ['buildings-geojson', 'bg']:
            buildings_geojson.main(args)
        elif args['command'] == 'eap':
            eap.main(args)
        elif args['command'] in ['fill-timeseries', 'ft']:
            fill_timeseries.main(args)
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
        #else:
         #   raise ValueError('unknown command: %s' % args['command'])
    except UsageError as e:
        parser.print_usage()
        print(str(e))
        sys.exit(2)

# ----------------------------------------------------


if __name__ == "__main__":
    main()
