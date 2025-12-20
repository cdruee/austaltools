#!/bin/env python3
# -*- coding: utf-8 -*-
"""
This module ...
"""
import itertools
import logging
import os

import numpy as np
import pandas as pd

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':

    import readmet
    import meteolib

try:
    from . import _corine
    from . import _dispersion
    from . import _plotting
    from . import _tools
    from ._metadata import __version__
    from . import _windutil
except ImportError:
    import _corine
    import _dispersion
    import _plotting
    import _tools
    from _version import __version__
    import _windutil

logger = logging.getLogger(__name__)

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    logging.getLogger('readmet.dmna').setLevel(logging.ERROR)

# -------------------------------------------------------------------------

DEFAULT_WIF_COLORMAP = 'plasma'

# -------------------------------------------------------------------------

def load_topo(path: str, variable: str = '') -> (list, list, np.ndarray):
    """
    Get the AUSTAL model topography from the file `topo_path`

    :param path: file name of the topography file
    :type path: str
    :param variable: variable name, defaults to empty string
    :type variable: str
    :return: axes coordinates and topography grid
    :rtype: (list, list, np.ndarray)
    """
    logger.info('reading topography from %s' % path)
    topofile = readmet.dmna.DataFile(path)
    topz = topofile.data[variable]
    topx = topofile.axes(ax="x")
    topy = topofile.axes(ax="y")
    return topx, topy, topz

# -------------------------------------------------------------------------

def superpose(u_grid:np.ndarray, v_grid:np.ndarray, axes:dict,
              dirs: np.ndarray,
              ua:float, va:float, xa:float, ya:float, ha:float, ak:int):
    """
    Calculate the wind field by superposition of `u_grid` and `v_grid`

    :param u_grid: wind field for eastward flow,
        eastward (u) and northward (v) components
    :type u_grid: np.ndarray
    :param v_grid: wind field for northward flow
    :type v_grid: np.ndarray
    :param axes: x and y axes
    :type axes: dict[str, list[float]]
    :param ua: anemometer eastward wind component
    :type ua: float
    :param va: anemometer northward wind component
    :type va: float
    :param xa: anemometer position
    :type xa: float
    :param ya: anemometer position
    :type ya: float
    :param ha: anemometer height
    :type ha: float
    :param ak: Klug/Manier stability class
    :type ak: int
    :return: superposed wind field eastward (u) and northward (v) components
    :rtype: (np.ndarray[float], np.ndarray[float])
    """
    # anemometer position index
    ix = np.argmin(abs(np.array(axes['x']) - xa))
    iy = np.argmin(abs(np.array(axes['y']) - ya))

    # components of unit vector in direction of anomemeter wind
    fa = np.sqrt(ua * ua + va * va)
    sia = -ua / fa
    coa = -va / fa


    n_dir = u_grid.shape[4]
    ui = np.full((n_dir),np.nan)
    vi = np.full((n_dir),np.nan)
    dr = np.full((n_dir),np.nan)
    rot = np.full((n_dir),np.nan)
    for i in range(n_dir):
        ui[i] = np.interp(ha, axes['z'], u_grid[ix, iy, :, ak, i])
        vi[i] = np.interp(ha, axes['z'], v_grid[ix, iy, :, ak, i])
        # unit vector components
        fi = (ui[i] * ui[i] + vi[i] * vi[i])
        si = -ui[i] / fi
        co = -vi[i] / fi
        # caculate directional distance:
        dr[i] = (si - sia) * (si - sia) + (co - coa) * (co - coa)
        rot[i] = va * vi[i] - va * ui[i]
    
    # select wind field with the closest wind direction
    i0 = dr.argmin()
    # select wind field with the closest wind direction on the other side
    other_side = np.ma.array(dr, mask=(np.sign(rot) == np.sign(rot[i0])))
    if other_side.count() > 0:
        # if there are values on the other side, take the closest one
        i1 = other_side.argmin()
    else:
        # if there are none take 2nd closest on same side
        i1 = dr.argsort()[1]

    # solve equation so that u, v = linea combi of ui,vi at anemometer
    det = (vi[i0] * ui[i1] - ui[i0] * vi[i1])
    if det == 0:
        raise ValueError('wind fields in the wind library '
                         'are not linearily independent')
    f0 = (va * ui[i1] - ua * vi[i1]) / (vi[i0] * ui[i1] - ui[i0] * vi[i1])
    f1 = (ua * vi[i0] - va * ui[i0]) / (vi[i0] * ui[i1] - ui[i0] * vi[i1])
    # if vi[i1] > ui[i1]:
    #     f1 = (va - a * vi[i0]) / vi[i1]
    # else:
    #     f1 = (ua - a * ui[i0]) / ui[i1]
    logger.debug(f'selected directions  : i0:{dirs[i0]}, i1={dirs[i1]}')
    logger.debug(f'superposition factors: f0={f0}, f1={f1}')
    # calculate wind field
    u_field = (f0 * u_grid[:, :, :, ak, i0] +
               f1 * u_grid[:, :, :, ak, i1])
    v_field = (f0 * v_grid[:, :, :, ak, i0] +
               f1 * v_grid[:, :, :, ak, i1])
    logger.debug('  umin=%f, umax=%f' % (np.min(u_field), np.max(u_field)))
    logger.debug('  vmin=%f, vmax=%f' % (np.min(v_field), np.max(v_field)))
    return u_field, v_field

# -------------------------------------------------------------------------

def main(args):
    """
    This is the main working function

    :param args: the command line arguments as dictionary
    :type args: dict
    """
    logger.debug(format(args))

    # act normally otherwise
    try:
        import matplotlib
        have_matplotlib = True
        if os.name == 'posix' and "DISPLAY" not in os.environ:
            matplotlib.use('Agg')
            have_display = False
        else:
            have_display = True
        import matplotlib.pyplot as plt
        import matplotlib.colors as mco
        import matplotlib.patches as patches
        logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
    except ImportError:
        have_matplotlib = False
        have_display = False
        matplotlib = None
        plt = None

    working_dir = args["working_dir"]
    grid = int(args["grid"])
    #
    conf = _tools.get_austxt(_tools.find_austxt(working_dir))
    #
    if args['vector']:
        u, v, ak = [float(x) for x in args['vector']]
    elif args['wind']:
        ff, dd, ak = [float(x) for x in args['wind']]
        u, v = meteolib.wind.dir2uv(ff, dd)
    elif args['time']:
        timestamp = pd.to_datetime(args['time'])
        az = _windutil.load_weather(working_dir, conf)
        time = az.index[(
                az.index - timestamp).to_series().abs().argsort()[0]]
        if abs(time -timestamp) > pd.Timedelta('1H'):
            raise ValueError('time outside data: %s' % str(timestamp))
        else:
            logger.info('using data from: %s' % str(timestamp))
        ff = az['FF'][time]
        dd = az['DD'][time]
        ak = az['KM'][time]
        u, v = meteolib.wind.dir2uv(ff, dd)
    else:
        raise ValueError('no wind reference value defined')

    # AK (ak) in file and command line is 1-based,
    # ak0 is zero-based so it can be used as field index
    ak0 = int(ak) - 1
    akstr = _dispersion.KM2021.name(int(ak))
    logger.info(f"wind: {u:.1f}, {v:.1f}, stability class: {akstr}")
    cmap = args['colormap']
    #
    # read the wind library data
    #
    lib_dir = _tools.wind_library(working_dir)
    file_info = _tools.wind_files(lib_dir)
    directions = [float(x) * 10.
                  for x in sorted(list(set(file_info["wdir"])))]
    u_grid, v_grid, axes = _tools.read_wind(file_info, path=lib_dir,
                                     grid=grid, centers=True)
    ha = _tools.read_heff(working_dir, conf=conf, z0=args.get('z0', None))
    xa = conf.get('xa', 0)
    ya = conf.get('ya', 0)

    # _grid indices: nx, ny, nz, nstab, ndir
    u_field, v_field = superpose(u_grid, v_grid, axes, directions,
                                 u, v, xa, ya, ha, ak0)
    nx, ny, nz = u_field.shape
    # try to load topography
    if grid == 0:
        topo_path = os.path.join(args['working_dir'], "zg00.dmna")
        topo_var = ""
    else:
        topo_path = os.path.join(args['working_dir'],
                             "lib/zg%01d1.dmna" % grid)
        topo_var = "zg"
    if os.path.exists(topo_path):
        logger.info('reading terrain from %s' % topo_path)
    else:
        if conf and "gh" in conf:
            logging.warning('file not found: %s' % topo_path)
        topo_path = None
    if topo_path:
        topx, topy, topz = load_topo(topo_path, topo_var)
    else:
        logger.warning('no topography: assuming zero elevation')
        topz = np.full((nx, ny), 0.)

    if args['buildings']:
        buildings = _tools.get_buildings(conf)
        logging.info('buildings in config: %d' % len(buildings))

    altitude = np.nan

    if args.get('hgt', False):
        height = float(args['hgt'])
        level = np.argmin(abs(np.array(axes['z']) - height))
        logger.info(f'nearest model level: {level}')
    elif args.get('lvl', False):
        level = int(args['lvl'])
    else:
        level = False
    if level:
        u_slice = u_field[:,:,level]
        v_slice = v_field[:,:,level]
        h_ccord = np.array(axes['x'])
        v_ccord = np.array(axes['y'])
        view = 'top'
    elif args.get('alt') is not None:
        altitude = float(args['alt'])
        cols = itertools.product(range(nx), range(ny))
        u_slice = np.full((nx, ny), np.nan)
        v_slice = np.full((nx, ny), np.nan)
        for col in _tools.progress(cols):
            i, j = col
            alt = axes['z'] + topz[i, j]
            u_slice[i, j] = np.interp([altitude], alt, u_field[i, j, :],
                                      left=np.nan)[0]
            v_slice[i, j] = np.interp([altitude], alt, v_field[i, j, :],
                                      left=np.nan)[0]
        h_ccord = np.array(axes['x'])
        v_ccord = np.array(axes['y'])
        view = 'top'
    elif args.get('vxz', False):
        plane = int(args['vxz'])
        u_slice = u_field[plane, :, :]
        v_slice = v_field[plane, :, :]
        t_slice = topz[plane, :]
        h_ccord = np.array(axes['y'])
        v_ccord = np.array(axes['z'])
        view = 'side'
    elif args.get('vyz', False):
        plane = int(args['vyz'])
        u_slice = u_field[:, plane, :]
        v_slice = v_field[:, plane, :]
        t_slice = topz[:, plane]
        h_ccord = np.array(axes['x'])
        v_ccord = np.array(axes['z'])
        view = 'side'
    else:
        raise ValueError('no cut defined')

    style = args['style']
    color = args.get('color', 'blue')
    matplotlib.rcParams.update({'font.size': 16})
    fig, ax = plt.subplots()
    fig.set_size_inches(11, 8)
    if view == 'top':

        # show topography
        #
        if topo_path:
            if args.get('shade', False):
                ls = mco.LightSource(azdeg=315, altdeg=45)
                ax.imshow(ls.hillshade(topz.T),
                          cmap='gray',
                          extent=(min(topx), max(topx),
                                  min(topy), max(topy)),
                          origin='lower',
                          alpha=0.25,
                          )

            con = plt.contour(topx, topy, topz.T, origin='lower',
                              colors='black',
                              linewidths=0.75
                              )
            ax.clabel(con, con.levels, inline=True, fontsize=10)
            topcut = 1*(topz > altitude)
            ax.contourf(topx, topy, topcut.T,
                        levels=[0.99, 1.01], cmap='Greys')

        # show wind field
        #
        spd_slice = np.sqrt(u_slice*u_slice + v_slice*v_slice)
        u_slice[spd_slice < 0.5] = np.nan
        v_slice[spd_slice < 0.5] = np.nan
        spd_slice[spd_slice < 0.5] = np.nan
        # choose style
        if style == 'stream':
            ax.streamplot(h_ccord, v_ccord, u_slice.T, v_slice.T,
                          color=color,
                          density=1.5)
        elif style == 'stream-color':
            vmax = np.nanpercentile(np.sqrt(u_slice ** 2 + v_slice ** 2),90)
            sp = ax.streamplot(h_ccord, v_ccord, u_slice.T, v_slice.T,
                               color=spd_slice.T, cmap=cmap,
                               norm=matplotlib.colors.Normalize(
                                   vmin=0.0, vmax=vmax),
                               density=1.5)
            fig.colorbar(sp.lines, ax=ax, label='m/s')
        elif style == 'arrows':
            st = int(u_slice.shape[0]/30)
            plt.quiver(h_ccord[::st], v_ccord[::st],
                       u_slice[::st, ::st].T, v_slice[::st, ::st].T
                       )
        elif style == 'arrows-color':
            st = int(u_slice.shape[0]/30)
            qp = plt.quiver(h_ccord[::st], v_ccord[::st],
                            u_slice[::st, ::st].T, v_slice[::st, ::st].T,
                            spd_slice[::st, ::st].T, cmap=cmap)
            fig.colorbar(qp, ax=ax, label='m/s')
        elif style == 'barbs':
            st = int(u_slice.shape[0]/20)
            plt.barbs(h_ccord[::st], v_ccord[::st],
                      1.94 * u_slice[::st, ::st].T,
                      1.94 * v_slice[::st, ::st].T,
                      pivot='middle'
                      )
        elif style == 'barbs-color':
            st = int(u_slice.shape[0]/20)
            bp = plt.barbs(h_ccord[::st], v_ccord[::st],
                           1.94 * u_slice[::st, ::st].T,
                           1.94 * v_slice[::st, ::st].T,
                           1.94 * spd_slice[::st, ::st].T,
                           cmap=cmap,
                           pivot='middle')
            fig.colorbar(bp, ax=ax, label='m/s')

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

    elif view == 'side':
        v_pos = np.broadcast_to(v_ccord,u_slice.shape)
        t_pos = np.broadcast_to(t_slice[:,np.newaxis],u_slice.shape)
        h_pos = np.broadcast_to(h_ccord[:,np.newaxis],u_slice.shape)
        v_pos = v_pos + t_pos
        ax.quiver(h_pos, v_pos, u_slice.T, v_slice.T)
        ax.fill_between(h_ccord,t_slice,0*t_slice,
                        color='grey')

    else:
        raise ValueError(f'internal error: view={view}')
    fig.tight_layout()

    if args['plot'] is None or args['plot'] == '-':
        args['plot'] = '__show__'
    elif args['plot'] == '__default__':
        args['plot'] = 'windfield.png'

    if args["plot"] == "__show__":
        logger.info('showing plot')
        plt.show()
    else:
        if os.path.sep in args["plot"]:
            outname = args["plot"]
        else:
            outname = os.path.join(args["working_dir"], args["plot"])
        if not outname.endswith('.png'):
            outname = outname + '.png'
        logger.info('writing plot: %s' % outname)
        plt.savefig(outname, dpi=180)

# ----------------------------------------------------

def add_options(subparsers):

    pars_wif = subparsers.add_parser(
        name='windfield',
        help='Plot wind field'
    )
    pars_wif.add_argument(dest='style',
                          choices=['stream', 'stream-color',
                                   'arrows', 'arrows-color',
                                   'barbs', 'barbs-color',],
                          help='style of wind field plot')
    pars_wif.add_argument('-b', '--no-buildings',
                        dest='buildings',
                        action='store_false',
                        help='do not show the buildings ' +
                             'defined in config file')
    pars_wif.add_argument('-c', '--colormap',
                         default=DEFAULT_WIF_COLORMAP,
                         help='name of colormap to use. '
                              'Defaults to "%s"' %
                              DEFAULT_WIF_COLORMAP)
    pars_wif.add_argument('-s', '--shade',
                          dest='shade',
                          action='store_true',
                          help='add hillshading in background')
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
                      metavar=('SPEED', 'DIR', 'AK'),
                      nargs=3,
                      default=None,
                      help='display windfield corresponding '
                           'to the wind `SPEED`, `DIR`ection and '
                           'stability class `AK`. '
                           'Defaults to `None`')
    wval.add_argument('-W', '--wind-vector',
                      dest='vector',
                      metavar=('U', 'V', 'AK'),
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
    pars_adv_wif = pars_wif.add_argument_group('advanced options')
    pars_adv_wif.add_argument('--z0',
                         dest='z0',
                         default=None,
                         help=f"roughness length at the position of the "
                              f"measurement used for calculation of "
                              f"the effective anemometer height. "
                              f"Overrides the value provided by the "
                              f"data source. Ignored if value is None. "
                              f"[%(default)s]"
                         )
