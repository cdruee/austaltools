import argparse
import importlib.util
import logging
import os
import sys

import pandas as pd



if os.getenv('BUILDING_SPHINX', 'false') == 'false':
    import numpy as np
    import readmet

logger = logging.getLogger(__name__)

# ----------------------------------------------------

DEFAULT_COLORMAP = "YlOrRd"
"""Default colors used for the commpon plot type"""

NO_MATPLOTLIB_HELP = ("The matplotlib library "
                      "does not appear to be installed. "
                      "You can install it by running "
                      "`pip install matplotlib` "
                      "or using the package manager of your choice.")
# ----------------------------------------------------

def have_matplotlib(mock: bool = False):
    if not os.getenv('BUILDING_SPHINX', 'false') == 'false':
      res = importlib.util.find_spec("matplotlib") is not None
      if mock:
          # dynamic import of plotting
          raise EnvironmentError("Plotting is not possible." +
                           NO_MATPLOTLIB_HELP)
      return res
    else:
      return True
# ----------------------------------------------------
matplotlib = None
colors = None
patches = None
plt = None
def import_matplotlib():
    """ import a libray that is installed
    :param lib: name of libray
    :type lib: str
    """
    try:
        globals()['matplotlib'] = importlib.import_module('matplotlib')
        if os.name == 'posix' and "DISPLAY" not in os.environ:
            matplotlib.use('Agg')
            have_display = False
        else:
            have_display = True
        for k,v in {'colors': 'matplotlib.colors',
                    'patches': 'matplotlib.patches',
                    'plt': 'matplotlib.pyplot'}.items():
            globals()[k] = importlib.import_module(v)
        logger.debug("importing matplotlib")
    except ImportError:
        
        raise EnvironmentError(f"matplotlib not found. "
                               f"Run `pip install matplotlib` to install.")
    logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
    return have_display

# ----------------------------------------------------
def import_plotlib(lib):
    """
    return a libray that is installed or return None
    :param lib: name of libray
    :type lib: str
    """
    known_libs = {
        'mpl': 'matplotlib',
        'mco': 'matplotlib.colors',
        'mpt': 'matplotlib.patches',
        'plt': 'matplotlib.pyplot'
    }
    mob = known_libs.get(lib, None)
    if mob is None:
        raise ValueError(f"module id {lib} not known")
    try:
        res = importlib.import_module(mob)
        logger.debug(f"importing {mob}")
    except ImportError:
        res = None
        logger.debug(f"failed to import {mob}")
    return res

# -------------------------------------------------------------------------

def _add_epilog(parser: argparse.ArgumentParser
                ) -> argparse.ArgumentParser:
    """
    Add note as epilog to parser

    :param parser: parser to add arguments to
    :type parser: argparse.ArgumentParser
    :return: parser with added arguments
    :rtype:  argparse.ArgumentParser

    """
    parser.epilog = ("Note: Plotting is not possible." +
                     NO_MATPLOTLIB_HELP)
    return parser

# -------------------------------------------------------------------------

def _add_arguments(parser: argparse.ArgumentParser
                             ) -> argparse.ArgumentParser:
    """
    Actually add agruments to a parser

    :param parser: parser to add arguments to
    :type parser: argparse.ArgumentParser
    :return: parser with added arguments
    :rtype:  argparse.ArgumentParser

    """
    parser.add_argument('-b', '--no-buildings',
                        dest='buildings',
                        action='store_false',
                        help='do not show the buildings ' +
                             'defined in config file')
    parser.add_argument('-l', '--low-colors',
                        dest='fewcols',
                        action='store_true',
                        help='use only few discrete colors ' +
                             'for better print results')
    parser.add_argument('-c', '--colormap',
                        default=DEFAULT_COLORMAP,
                        help='name of colormap to use. Defaults to "%s"' %
                             DEFAULT_COLORMAP)
    parser.add_argument('-k', '--kind',
                        default='contour',
                        choices=['contour', 'grid'],
                        help='choose kind of display. ' +
                             '`contour` produces filled contours, ' +
                             '`grid` produces coloured grid cells. ' +
                             'Defaults to `contour`')
    parser.add_argument('-p', '--plot',
                        metavar="FILE",
                        nargs='?',
                        const='__default__',
                        help='save plot to a file. If `FILE` is "-" ' +
                             'the plot is shown on screen. If `FILE` is ' +
                             'missing, the file name defaults to ' +
                             'the data file name with extension `png`'
                        )
    parser.add_argument('-f', '--force',
                        action='store_true',
                        default=False,
                        help='force overwriting plotfile if it exists.')
    return parser

# -------------------------------------------------------------------------

def add_arguents_common_plot(parser: argparse.ArgumentParser
                             ) -> argparse.ArgumentParser:
    """
    Add agruments to a parser that are honored by the common_plot
    function add a notice instead if maptplotlib is not installed

    :param parser: parser to add arguments to
    :type parser: argparse.ArgumentParser
    :return: parser with added arguments
    :rtype:  argparse.ArgumentParser

    """
    if have_matplotlib():
        return _add_arguments(parser)
    else:
        return _add_epilog(parser)

# -------------------------------------------------------------------------

def add_location_opts(parser,
                      stations=False,
                      required=True):
    """
    This routine adds the input arguments defining a position:

    :param parser: the arguemnt parser to add the options to
    :type parser: argpargse.ArgumentParser
    :param stations: WMO or DWD station numbers are accepted as positions
    :type stations: bool
    :param required: if a location specification is required
      type required: bool

    Note:
        - dwd (str or None): DWD option, mutually exclusive with 'wmo' and required with 'ele'.
        - wmo (str or None): WMO option, mutually exclusive with 'dwd' and required with 'ele'.
        - ele (str or None): Element option, required with either 'dwd' or 'wmo'.
        - year (int or None): Year option, required with '-L', '-G', '-U', '-D', or '-W'.
        - output (str or None): Output name, required with '-L', '-G', '-U', '-D', or '-W'.
        - station (str or None): Station option, only valid with 'dwd' or 'wmo'.

    """
    loc_opt = parser.add_mutually_exclusive_group(required=required)
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

    return parser

# -------------------------------------------------------------------------

def plot_add_mark(ax, mark):
    pf = pd.DataFrame(mark)
    for i, p in pf.iterrows():
        x = p['x']
        y = p['y']
        if 'sym' in p:
            sym = p['symbol']
        else:
            sym = "o"
        ax.plot(x, y, sym, markersize=10)


def plot_add_topo(ax, topo, working_dir='.'):
    logger.debug('adding topography')
    if isinstance(topo, dict):
        logger.debug('... from data in arguments')
        topx = topo["x"]
        topy = topo["y"]
        topz = topo["z"]
    elif isinstance(topo, str):
        logger.debug('... from file: %s' % topo)
        if os.path.exists(topo):
            topo_path = topo
        elif os.path.exists(os.path.join(working_dir, topo)):
            topo_path = os.path.join(working_dir, topo)
        else:
            raise ValueError('topography file not found: %s' % topo)
        logger.info('reading topography from %s' % topo_path)
        topofile = readmet.dmna.DataFile(topo_path)
        topz = topofile.data[""]
        topx = topofile.axes(ax="x")
        topy = topofile.axes(ax="y")
    else:
        raise ValueError('topo must be dict of filename')
    con = ax.contour(topx, topy, topz.T, origin="lower",
                     colors='black',
                     linewidths=0.75
                     )
    ax.clabel(con, con.levels, inline=True, fontsize=10)
    return con

# -------------------------------------------------------------------------

def common_plot(args: dict,
                dat: dict,
                unit: str = "",
                topo: dict or str = None,
                dots: dict or np.ndarray = None,
                buildings: list = None,
                mark: dict or pd.DataFrame = None,
                scale: list or tuple = None):
    """
    Standard plot function for the package.

    :param args: dict containing the plot configuration
    :type args: dict
    :param args["colormap"]: name of colormap to use
      Defaults to :py:const:`DEFAULT_COLORMAP`:.
    :type args["colormap"]: str
    :param args['kind']: How to display the data. Permitted values are
       "contour" for colour filled contour levels and
       "grid" for color-coded rectangular grid.
    :type args["display"]: str
    :param args['fewcols']: if True, a colormap of at most 9
      (or the numer of levels if explicitly passed by `scale`)
      discrete colors ist generated for easy print reproduction.
    :type args['fewcols']: bool
    :param args["plot"]: Destination for the plot.
      If empty or :py:const:`None` no plot is produced. If the value is
      a string, the plot will be saved to file with that name. If
      the name does have the extension ``.png``, this extension
      is appendend. If the string does not contain a path,
      the file will besaved in the current working directory.
      If the string contains a path, the file will be saved
      in the respective location.
    :param args['working_dir']: Working directory,
      where the data files reside.
    :type args["working_dir"]: str

    :param dat: dictionary of `x`, `y`, and `z` values to plot.
      'x' and 'y' must be lists of float or 1-D ndarray.
      'z' must be ndarray of a shape matching the lenght of `x` and `y`
    :type dat: dict
    :param unit: physical units of the values `z` in dat
    :type unit: str
    :param scale: range of the color scale. None means auto scaling.
    :type unit: tuple or None
    :param topo: topography data as dict (same form as `dat`)
      or filename of a topography file in dmna-format
      or None for no topography
    :type topo: dict or string or None
    :param dots: data to ovelay dotted areas (e.g. to mark significance).
      `dots` must either be a dict (same form as `dat`)
      or a ndarray matching the `z` data in `dat` in shape.
      dat values z < 0 are not overlaid,
      values 0 <= z < 1 are sparesely dotted,
      values 1 <= z < 2 are sparesely dotted,
      spography data as dict (same form as `dat`)
      or filename of a topography file in dmna-format
      or None for no topography
    :param buildings: List of `Building` objects to be displayed.
      If None or list is epmty, no buildings are plotted.
    :type buildings: list
    :param mark: positions to mark. either dict containing list-like
       objects of `x`, `y` and optionally 'symbol' of the same length
       or a pandas data frame containing such columns.
       `symbol` are matplotlib symbol strings. If missing 'o' is used.
    :type mark: dict or pandas.Dataframe



    """
    logger.debug(f"Found matplotlib: {have_matplotlib()}")
    if not have_matplotlib():
        raise EnvironmentError('matplotlib not available, cannot plot' +
                               NO_MATPLOTLIB_HELP)
    have_display = import_matplotlib()
    if args["plot"] == "__show__" and not have_display:
        raise EnvironmentError('no display, cannot show plot')

    matplotlib.rcParams.update({'font.size': 16})
    fig, ax = plt.subplots()
    fig.set_size_inches(11, 8)

    # ---------------------------
    # plot data as color-coded map
    #
    if "colormap" in args:
        cmap_name = args["colormap"]
    else:
        cmap_name = DEFAULT_COLORMAP
    if isinstance(dat, dict):
        datx = dat['x']
        daty = dat['y']
        datz = dat['z']
        if (len(datx), len(daty)) != np.shape(datz):
            raise ValueError('lenghts of x and y do not match shape of z')
    else:
        raise ValueError('dat must be dict')

    levels = None
    if scale is None:
        dmin = np.nanmin(datz)
        dmax = np.nanmax(datz)
    elif isinstance(scale, float):
        dmin = 0.
        dmax = scale
    elif len(scale) == 2:
        dmin, dmax = scale
    elif len(scale) > 2:
        levels = np.array(scale)
    if levels is None:
        data_range = dmax - dmin
        order = 10 ** np.floor(np.log10(data_range))
        dmin = np.floor(dmin / order) * order
        dmax = np.ceil(dmax / order) * order
        logger.debug('data_range: %f' % data_range)
        levels = np.arange(dmin, dmax, data_range / 10)

    if args['fewcols']:
        cmap = plt.get_cmap(cmap_name, len(levels) + 1)
    else:
        cmap = plt.get_cmap(cmap_name,1000)
        cl = levels
        levels = [cl[0]]
        for i in range(1,len(cl)):
            levels += list(np.linspace(cl[i-1], cl[i], 10))[1:]
    if args['kind'] == "contour":
        #
        # Note to self: "TypeError: 'NoneType' object is not callable"
        #               its pycharm's debugging mode, stupid
        #
        img = plt.contourf(datx, daty,
                           datz.T,
                           origin="lower",
                           levels=levels,
                           cmap=cmap,
                           extend='both',
                           )
        plt.colorbar(img, label=unit, format='%.2g', extend='both')
    elif args['kind'] == "grid":
        img = plt.pcolormesh(datx, daty,
                         datz.T,
                         shading="nearest",
                         cmap=cmap,
                         norm = colors.BoundaryNorm(
                             boundaries= levels,
                             ncolors=len(levels),
                             clip=False
                         )
                         )
        plt.colorbar(img, label=unit, format='%.2g', extend='both',
                     boundaries=levels)
    else:
        raise ValueError('argument display missing or invalid')
    logger.debug('unit: %s' % unit)

    # ---------------------------
    # overlay dots e.g. to mark significance
    #
    if dots is not None:
        if isinstance(dots, dict):
            dotx = dots['x']
            doty = dots['y']
            dotz = dots['z']
        elif isinstance(dots, np.ndarray):
            dotz = dots
            if np.shape(dotz) != np.shape(datz):
                raise ValueError('dots shape does not equal dat shape')
            else:
                dotx = datx
                doty = daty
        else:
            raise ValueError('dots must be dict or ndarray')
        plt.contourf(dotx, doty, dotz.T, origin="lower",
                     levels=[0, 1, 2],
                     colors=['white', 'white', 'white', 'white'],
                     hatches=['+', '..', '..', None],
                     extend='both',
                     alpha=0)
        plt.contourf(datx, daty, dotz.T, origin="lower",
                     levels=[0, 1, 2],
                     colors=['white', 'white', 'white', 'white'],
                     hatches=['+', '..', '..', None],
                     extend='both',
                     alpha=0)

    # ---------------------------
    # overlay topography as isolines
    #
    if topo is not None:
        plot_add_topo(ax, topo, args['working_dir'])

    # ---------------------------
    # show buildings
    #
    if buildings is not None:
        for bb in buildings:
            ax.add_patch(
                patches.Rectangle(
                    xy=(bb.x, bb.y),
                    width=bb.a,
                    height=bb.b,
                    angle=bb.w,
                    fill=True,
                    color="black",
                )
            )

    # ---------------------------
    # put marks on desired positions
    #
    if mark is not None:
        plot_add_mark(ax,mark)

    ax.set_xlabel("x in m")
    ax.set_ylabel("y in m")

    fig.tight_layout()
    if args["plot"] == "__show__":
        logger.info('showing plot')
        plt.show()
    elif args["plot"] not in [None, ""]:
        if os.path.sep in args["plot"]:
            outname = args["plot"]
        else:
            outname = os.path.join(args["working_dir"], args["plot"])
        if not outname.endswith('.png'):
            outname = outname + '.png'
        logger.info('writing plot: %s' % outname)
        plt.savefig(outname, dpi=180)

# -------------------------------------------------------------------------

def read_extracted_weather(csv_name: str) -> (
        float, float, float, str, str, pd.DataFrame):
    """
    read weather data that were previously extracted from a
    dataset and stored into a csv file with specially crafted header line

    :param csv_name: file name and path
    :type csv_name: str
    :return: latitude, longitude, elevation, roughness length z0,
      code of the original dataset, station name (if applicable),
      and the weather data
    :rtype: float, float, float, str, str, pd.DataFrame
    """
    # halt if file is not found
    if not os.path.exists(csv_name):
        raise IOError('weather data not found: %s' % csv_name)
    logger.info('reading weather data from: %s' % csv_name)

    # read position fom comment line
    with open(csv_name, 'r') as f:
        lat, lon, ele, z0, source, nam = f.readline(
        ).strip('# \n').split(maxsplit=6)
    stat_no = 0

    # read observation data from subsequent lines
    obs = pd.read_csv(csv_name, comment='#', index_col=0,
                      parse_dates=True, na_values='-999')

    return lat, lon, ele, z0, source, nam, obs
