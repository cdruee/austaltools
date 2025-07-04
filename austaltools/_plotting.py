import logging
import os

import pandas as pd

try:
    from . import _tools
except ImportError:
    import _tools

if os.getenv('BUILDING_SPHINX', 'false') == 'false':
    import numpy as np
    import readmet

    import matplotlib
    if os.name == 'posix' and "DISPLAY" not in os.environ:
        matplotlib.use('Agg')
        _HAVE_DISPLAY = False
    else:
        _HAVE_DISPLAY = True
    import matplotlib.colors as colors
    import matplotlib.patches as patches
    import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)

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

# -------------------------------------------------------------------------

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
        topx, topy, topz, dd = read_topography(topo_path)
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
      Defaults to :py:const:`austaltools._tools.DEFAULT_COLORMAP`:.
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
    if args["plot"] == "__show__" and not _HAVE_DISPLAY:
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
        cmap_name = _tools.DEFAULT_COLORMAP
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
        logger.debug('scale range: %f' % (dmax - dmin))
        delta = (dmax - dmin) / 10.
        levels = np.arange(dmin, dmax, delta)

    logger.debug(f"levels: {levels}")
    if args['fewcols']:
        color_levels=levels
    else:
        color_levels = [levels[0]]
        for x in levels[1:]:
            color_levels += [np.nan] * 9 + [x]
        color_levels = pd.Series(color_levels).interpolate(method='quadratic').tolist()
    cmap = plt.get_cmap(cmap_name, len(color_levels) + 1)
    if args['kind'] == "contour":
        #
        # Note to self: "TypeError: 'NoneType' object is not callable"
        #               its pycharm's debugging mode, stupid
        #
        img = plt.contourf(datx, daty,
                           datz.T,
                           origin="lower",
                           levels=color_levels,
                           cmap=cmap,
                           extend='both',
                           )
    elif args['kind'] == "grid":
        img = plt.pcolormesh(datx, daty,
                         datz.T,
                         shading="nearest",
                         cmap=cmap,
                         norm = colors.BoundaryNorm(
                             boundaries= color_levels,
                             ncolors=len(color_levels),
                             clip=False
                         )
                         )
    else:
        raise ValueError('argument display missing or invalid')
    plt.colorbar(img, label=unit, format='%.3g', extend='both',
                 ticks=levels)
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

def read_topography(topo_path):
    topo_extension = os.path.splitext(topo_path)[1]
    logger.debug(f"file extension: {topo_extension}")
    if topo_extension == '.dmna':
        topofile = readmet.dmna.DataFile(topo_path)
        topz = topofile.data[""]
        topx = topofile.axes(ax="x")
        topy = topofile.axes(ax="y")
        dd = float(topofile.header["delta"])
    elif topo_extension == '.grid':
        topofile = _tools.GridASCII(topo_path)
        topz = topofile.data
        dd = float(topofile.header["cellsize"])
        xll = float(topofile.header["xllcorner"])
        yll = float(topofile.header["yllcorner"])
        nx = int(topofile.header["ncols"])
        ny = int(topofile.header["nrows"])
        topx = [xll + float(i) * dd for i in range(nx)]
        topy = [yll + float(i) * dd for i in range(ny)]
    else:
        raise ValueError(f"unknown topo file extension {topo_extension}")

    return topx, topy, topz, dd