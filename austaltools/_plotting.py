import logging
import os
import sys

import pandas as pd

from . import _tools

if os.getenv('BUILDING_SPHINX', 'false') == 'false':
    import numpy as np
    import readmet

    import matplotlib
    if os.name == 'posix' and "DISPLAY" not in os.environ:
        matplotlib.use('Agg')
        HAVE_DISPLAY = False
    else:
        HAVE_DISPLAY = True
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

OVERLAP_REFERENCE_COLOR = 'darkorange'
"""str: matplotlib color name used for the reference field in
:func:`overlap_plot`."""

OVERLAP_COMPARISON_COLOR = 'darkviolet'
"""str: matplotlib color name used for the comparison field in
:func:`overlap_plot`."""


def consolidate_plotname(argument, default: str | None = None):
    # determine output
    if argument == '-':
        argument = '__show__'
    elif argument is None or argument == '__default__':
        if default:
            argument = default
        else:
            '__default__'

    if argument == '__show__' and not HAVE_DISPLAY:
        sys.tracebacklimit = 0
        raise EnvironmentError(f"No plotting window available, "
                               f"cannot show plot. Please give a "
                               f"-p/--plot <filename> or remove "
                               f"-p option for default plot file name"
                               f" ({default}).")
    return argument

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
    if args["plot"] == "__show__" and not HAVE_DISPLAY:
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
    # overlay topography, buildings and marks
    #
    plot_add_overlays(ax, topo=topo, buildings=buildings, mark=mark,
                      working_dir=args['working_dir'])

    finalize_plot(fig, ax, args)

# -------------------------------------------------------------------------

def plot_add_overlays(ax,
                      topo: dict or str = None,
                      buildings: list = None,
                      mark: dict or pd.DataFrame = None,
                      working_dir: str = '.'):
    """
    Overlay topography isolines, buildings and position marks on an
    existing plot axes. Shared between :func:`common_plot` and
    :func:`overlap_plot`.

    :param ax: matplotlib axes to draw on.
    :param topo: topography data as dict (same form as `dat` in
      :func:`common_plot`) or filename of a topography file in
      dmna/grid-format, or None for no topography.
    :type topo: dict or str or None
    :param buildings: List of `Building` objects to be displayed.
      If None or list is empty, no buildings are plotted.
    :type buildings: list
    :param mark: positions to mark, see :func:`common_plot`.
    :type mark: dict or pandas.DataFrame
    :param working_dir: working directory, used to resolve a relative
      `topo` filename.
    :type working_dir: str
    """
    if topo is not None:
        plot_add_topo(ax, topo, working_dir)

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
        plot_add_mark(ax, mark)

# -------------------------------------------------------------------------

def finalize_plot(fig, ax, args: dict):
    """
    Common finishing touches for a plot: axis labels, layout, and
    either showing the plot on screen or saving it to file, depending
    on ``args["plot"]``. Shared between :func:`common_plot` and
    :func:`overlap_plot`.

    :param fig: matplotlib figure.
    :param ax: matplotlib axes.
    :param args: dict containing at least ``args["plot"]`` (see
      :func:`common_plot`) and ``args["working_dir"]``.
    :type args: dict
    """
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

def _overlap_blend_rgb(z, thx, zmax, hue_rgb):
    """
    Linearly interpolate a scalar field ``z`` from white (at or below
    ``thx``) to a fully-saturated ``hue_rgb`` (at ``zmax`` and above),
    used by :func:`overlap_plot` to turn each of the two fields into an
    RGB raster before blending them multiplicatively.

    White is the multiplicative identity color (``(1, 1, 1)``), so a
    cell that is at/below the threshold in one field does not tint the
    other field's color at all once the two rasters are multiplied
    together -- only cells above threshold in *both* fields darken
    towards a mix of the two hues.

    :param z: 2D scalar field.
    :type z: numpy.ndarray
    :param thx: threshold value; ``z <= thx`` maps to white.
    :type thx: float
    :param zmax: value (and above) that maps to the fully-saturated
      ``hue_rgb``.
    :type zmax: float
    :param hue_rgb: RGB triple (0..1) of the fully-saturated color.
    :type hue_rgb: numpy.ndarray or tuple
    :return: RGB raster, shape ``z.shape + (3,)``.
    :rtype: numpy.ndarray
    """
    hue_rgb = np.asarray(hue_rgb, dtype=float)
    denom = zmax - thx
    if denom <= 0:
        frac = np.where(z > thx, 1.0, 0.0)
    else:
        frac = np.clip((z - thx) / denom, 0.0, 1.0)
    white = np.ones(3)
    return white + frac[..., np.newaxis] * (hue_rgb - white)

# -------------------------------------------------------------------------

def overlap_plot(args: dict,
                 reference: dict,
                 comparison: dict,
                 thx: float,
                 unit: str = "",
                 topo: dict or str = None,
                 buildings: list = None,
                 mark: dict or pd.DataFrame = None,
                 scale: float or None = None):
    """
    Plot two scalar fields (typically the reference and comparison
    fields produced by :func:`austaltools.compare_weather.run_austal`)
    overlaid in a single map, as similar as reasonably possible to
    :func:`common_plot`, but using a bivariate color scheme instead of
    a single colormap + colorbar, since two independent fields are
    shown at once:

    The reference field is rendered in shades of
    :data:`OVERLAP_REFERENCE_COLOR` (orange), the comparison field in
    shades of :data:`OVERLAP_COMPARISON_COLOR` (purple); both ramp from
    white at/below the threshold ``thx`` to the fully-saturated color
    at the field's maximum (or ``scale``, if given). The two rasters
    are then combined with a multiplicative RGB blend (see
    :func:`_overlap_blend_rgb`): since white is the identity color for
    multiplication, a cell above threshold in only one field shows that
    field's pure hue, while a cell above threshold in *both* fields
    darkens towards a brown/maroon tone where the two hues overlap.
    Highly visible isolines at ``z == thx`` are drawn for both fields,
    in their respective hue (solid for the reference, dashed for the
    comparison).

    A color-key legend replaces the usual colorbar, since a single
    colorbar cannot represent a bivariate color scheme.

    :param args: dict containing the plot configuration -- the same
      keys as :func:`common_plot` accepts, except ``args['colormap']``
      is ignored (the two hues are fixed, see above).
    :type args: dict
    :param reference: dict of `x`, `y`, `z` values of the reference
      field (same form as `dat` in :func:`common_plot`).
    :type reference: dict
    :param comparison: dict of `x`, `y`, `z` values of the comparison
      field, on the same `x`/`y` grid as `reference`.
    :type comparison: dict
    :param thx: threshold value (both fields are white at/below it) --
      typically the same value used to compute the overlap ratio, see
      :func:`austaltools.compare_weather.compute_overlap`.
    :type thx: float
    :param unit: physical unit of the values in `reference`/
      `comparison`, shown in the legend.
    :type unit: str
    :param topo: topography, see :func:`common_plot`.
    :type topo: dict or str or None
    :param dots: not supported by ``overlap_plot`` (no `dots` parameter
      -- two fields are already shown at once).
    :param buildings: see :func:`common_plot`.
    :type buildings: list
    :param mark: see :func:`common_plot`.
    :type mark: dict or pandas.DataFrame
    :param scale: value that maps to the fully-saturated color of each
      field. ``None`` (default) means auto-scaling to the larger of the
      two fields' maxima.
    :type scale: float, optional

    .. seealso:: :func:`common_plot`,
      :func:`austaltools.compare_weather.compute_overlap`
    """
    if args["plot"] == "__show__" and not HAVE_DISPLAY:
        raise EnvironmentError('no display, cannot show plot')

    for name, dat in (('reference', reference), ('comparison', comparison)):
        if not isinstance(dat, dict):
            raise ValueError('%s must be dict' % name)
        if (len(dat['x']), len(dat['y'])) != np.shape(dat['z']):
            raise ValueError(
                'lengths of x and y do not match shape of z in %s' % name)
    if (len(reference['x']) != len(comparison['x'])
            or not np.array_equal(reference['x'], comparison['x'])
            or not np.array_equal(reference['y'], comparison['y'])):
        raise ValueError('reference and comparison must share the same '
                         'x/y grid')

    datx = reference['x']
    daty = reference['y']
    z_ref = np.asarray(reference['z'])
    z_cmp = np.asarray(comparison['z'])

    matplotlib.rcParams.update({'font.size': 16})
    fig, ax = plt.subplots()
    fig.set_size_inches(11, 8)

    # ---------------------------
    # determine the upper end of the color scale
    #
    if scale is None:
        zmax = float(max(np.nanmax(z_ref), np.nanmax(z_cmp)))
    else:
        zmax = float(scale)
    logger.debug('overlap_plot: thx=%.6g, zmax=%.6g' % (thx, zmax))

    ref_rgb = _overlap_blend_rgb(z_ref, thx, zmax,
                                 colors.to_rgb(OVERLAP_REFERENCE_COLOR))
    cmp_rgb = _overlap_blend_rgb(z_cmp, thx, zmax,
                                 colors.to_rgb(OVERLAP_COMPARISON_COLOR))

    if args.get('fewcols'):
        # posterize into a handful of discrete steps for better print
        # reproduction, mirroring common_plot's args['fewcols']
        steps = 5
        ref_rgb = np.round(ref_rgb * steps) / steps
        cmp_rgb = np.round(cmp_rgb * steps) / steps

    blended = ref_rgb * cmp_rgb  # multiplicative blend

    # ---------------------------
    # plot the blended field as an image
    #
    # dat['z'] (and hence blended) is indexed [x, y]; imshow expects
    # the first axis to be rows (-> y) and the second columns (-> x),
    # same transposition common_plot applies for contourf/pcolormesh.
    kind = args.get('kind', 'contour')
    interpolation = 'nearest' if kind == 'grid' else 'bilinear'
    extent = (np.min(datx), np.max(datx), np.min(daty), np.max(daty))
    ax.imshow(np.transpose(blended, (1, 0, 2)),
             extent=extent, origin='lower', aspect='auto',
             interpolation=interpolation)

    # ---------------------------
    # highly visible isolines at the threshold, for both fields
    #
    con_ref = ax.contour(datx, daty, z_ref.T, levels=[thx],
                         colors=[OVERLAP_REFERENCE_COLOR],
                         linestyles='solid', linewidths=2.5)
    con_cmp = ax.contour(datx, daty, z_cmp.T, levels=[thx],
                         colors=[OVERLAP_COMPARISON_COLOR],
                         linestyles='dashed', linewidths=2.5)

    # ---------------------------
    # color-key legend, replacing the usual colorbar (a single
    # colorbar cannot represent a bivariate color scheme)
    #
    both_rgb = (np.asarray(colors.to_rgb(OVERLAP_REFERENCE_COLOR))
               * np.asarray(colors.to_rgb(OVERLAP_COMPARISON_COLOR)))
    unit_suffix = ' > %.3g %s' % (thx, unit) if unit else ' > %.3g' % thx
    legend_handles = [
        patches.Patch(color=OVERLAP_REFERENCE_COLOR,
                     label='reference' + unit_suffix),
        patches.Patch(color=OVERLAP_COMPARISON_COLOR,
                     label='comparison' + unit_suffix),
        patches.Patch(color=tuple(both_rgb), label='both (overlap)'),
        ax.plot([], [], color=OVERLAP_REFERENCE_COLOR, linestyle='solid',
               linewidth=2.5, label='reference threshold')[0],
        ax.plot([], [], color=OVERLAP_COMPARISON_COLOR, linestyle='dashed',
               linewidth=2.5, label='comparison threshold')[0],
    ]
    ax.legend(handles=legend_handles, loc='upper right', fontsize=11,
             framealpha=0.9)

    # ---------------------------
    # overlay topography, buildings and marks
    #
    plot_add_overlays(ax, topo=topo, buildings=buildings, mark=mark,
                      working_dir=args['working_dir'])

    finalize_plot(fig, ax, args)

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