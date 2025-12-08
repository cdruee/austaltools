import glob
import logging
import os



try:
    from . import _storage
    from . import _tools
    from ._metadata import __version__
except ImportError:
    import _storage
    import _tools
    from _version import __version__

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------

def main(args):
    print(os.path.basename(__file__) + ' version: ' + __version__)
    #
    # sub-command-specific imports
    from osgeo import osr
    try:
        from . import _geo
        from . import _corine
        from . import input_terrain
        from . import input_weather
    except ImportError:
        import _geo
        from . import _corine
        from . import input_terrain
        from . import input_weather

    #
    # get customized defaults from config
    #
    conf = _storage.read_config()
    simple_conf = conf.get('simple', {})
    w_source = simple_conf.get(
        'weather', _storage.SIMPLE_DEFAULT_WEATHER)
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
        x, y = _geo.ll2gk(lat, lon)
        f.write('%.0f %.0f : Gauss-Krueger Coordinates\n' % (x, y))

        print('getting averaged surface roughness')
        z0 = _corine.roughness_austal(x, y, 20.)
        if z0 is None:
            z0 = _corine.roughness_web(x, y, 20.)
        f.write('%.1f : z0 at position of wind measurement\n' % z0)

    print('done.')

# -------------------------------------------------------------------------

def add_options(subparsers):
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
    return pars_sim

# -------------------------------------------------------------------------
