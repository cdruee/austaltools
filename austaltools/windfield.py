#!/bin/env python3
# -*- coding: utf-8 -*-
"""
This module ...
"""
import itertools
import logging
import os
import sys

import numpy as np
import pandas as pd

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':

    import readmet
    import meteolib

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
    except ImportError:
        have_matplotlib = False
        have_display = False
        matplotlib = None
        plt = None

try:
    from . import _tools
    from ._version import __version__
    from . import _corine
    from . import _dispersion
except ImportError:
    import _tools
    from _version import __version__
    import _corine
    import _dispersion

logger = logging.getLogger()

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    logging.getLogger('readmet.dmna').setLevel(logging.ERROR)

# -------------------------------------------------------------------------

DEFAULT_WIF_COLORMAP = 'plasma'

# -------------------------------------------------------------------------

def load_topo(topo_path: str) -> (list, list, np.ndarray):
    logger.info('reading topography from %s' % topo_path)
    topofile = readmet.dmna.DataFile(topo_path)
    topz = topofile.data[""]
    topx = topofile.axes(ax="x")
    topy = topofile.axes(ax="y")
    return topx, topy, topz

# -------------------------------------------------------------------------

def load_weather(working_dir: str, conf: dict = None) -> pd.DataFrame:
    """
    Get the weather time series height `working_dir`.
    Files are evaluated in the same order as by AUSTAL:
    `zeitreihe.dmna` or `timeseries.dmna` are tried to read first,
    then the AKTERM file spezified in the config file under
    parameter 'az'

    :param working_dir: the working directoty of austal(2000),
      where austal.txt resides
    :type working_dir: str
    :param conf: (optional) configuration file contents as dict
    :type conf: dict

    :return: effective anemometer height
    :rtype: float

    If `conf` is provided, this configuration is evaluated,
    else the configuration file from `working_dir` is read.
    This option is indended for situation in which `conf`
    has already been read into memory for other purposes.
    """
    if conf is None:
        austxt = _tools.find_austxt(working_dir)
        conf = _tools.get_austxt(austxt)
    working_dir_files = os.listdir(working_dir)
    for x in ['zeitreihe.dmna', 'timeseries.dmna']:
        if x in working_dir_files:
            ts_file=os.path.join(working_dir, x)
            break
    else:
        ts_file=None
    if ts_file:
        zr = readmet.dmna.DataFile(os.path.join(working_dir,ts_file)).data
        res = pd.DataFrame(index=pd.to_datetime(zr['te']))
        res['FF'] = zr['ua'].values
        res['DD'] = zr['ra'].values
        z0 = get_roughness_length(working_dir=working_dir, conf=conf)
        res['KM'] = [_dispersion.KM2021.get_index(z0,x) for x in zr['ra']]
    else:
        if 'az' in conf:
            az_file = conf['az'][0]
        else:
            raise ValueError('no az defined, cannot read h_eff')
        az = readmet.akterm.DataFile(file=os.path.join(working_dir,
                                                       az_file))
        res = az.data[['FF', 'DD', 'KM']]
    return res

# -------------------------------------------------------------------------

def superpose(u_grid:np.ndarray, v_grid:np.ndarray, axes:dict, dirs,
              u:float, v:float, xa:float, ya:float, ha:float, ak:int):
    # _grid indices: nx, ny, nz, nstab, ndir
    ix = np.argmin(abs(np.array(axes['x']) - xa))
    iy = np.argmin(abs(np.array(axes['y']) - ya))
    i_dir = [0,1]
    ui = [np.nan, np.nan]
    vi = [np.nan, np.nan]
    for i, id in enumerate(i_dir):
        ui[i] = np.interp(ha, axes['z'], u_grid[ix, iy, :, ak, id])
        vi[i] = np.interp(ha, axes['z'], v_grid[ix, iy, :, ak, id])
    # solve equation so that u, v = linea combi of ui,vi at anemometer
    a = (v*ui[1] - u *vi[1]) / (vi[0]*ui[1] - ui[0]*vi[1])
    if vi[1] > ui[1]:
        b = (v - a * vi[0]) / vi[1]
    else:
        b = (u - a * ui[0]) / ui[1]
    logger.debug(f'superposition factors: a={a}, b={b}')
    # calculate wind field
    u_field = (a * u_grid[:, :, :, ak, i_dir[0]] +
               b * u_grid[:, :, :, ak, i_dir[1]])
    v_field = (a * v_grid[:, :, :, ak, i_dir[0]] +
               b * v_grid[:, :, :, ak, i_dir[1]])
    logger.debug('  umin=%f, umax=%f' % (np.min(u_field), np.max(u_field)))
    logger.debug('  vmin=%f, vmax=%f' % (np.min(v_field), np.max(v_field)))
    return u_field, v_field

# -------------------------------------------------------------------------

def get_roughness_length(working_dir=None, conf=None):
    if working_dir is None:
        working_dir = _tools.DEFAULT_WORKING_DIR
    z0 = _tools.read_z0(working_dir, conf)
    if z0 is None:
        logger.info("no z0 defined, calculating mean z0")
        if conf is None:
            austxt = _tools.find_austxt(working_dir)
            conf = _tools.get_austxt(austxt)
        if 'xg' in conf and 'yg' in conf:
            xg = conf['xg']
            yg = conf['yg']
        elif 'xu' in conf and 'yu' in conf:
            xu = conf['xu']
            yu = conf['yu']
            xg, yg = _tools.ut2gk(xu, yu)
        else:
            sys.tracebacklimit = 0
            raise ValueError("neither z0 nor position defined, "
                             "cannot determine z0")
        if 'hq' in conf:
            hq = conf['hq']
        else:
            logger.warning("no source height defined, assuming 10m")
            hq = 10.
        z0 = _corine.mean_roughness(xg, yg, hq)
    return z0

# -------------------------------------------------------------------------

def main(args):
    """
    This is the main working function

    :param args: the command line arguments as dictionary
    :type args: dict
    """
    logger.debug(format(args))
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
        az = load_weather(working_dir, conf)
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

    ak = int(ak)
    logger.debug(f"wind: {u}, {v}, stability class: {ak}")
    cmap = args['colormap']
    #
    # read the wind library data
    #
    lib_dir = _tools.wind_library(working_dir)
    file_info = _tools.wind_files(lib_dir)
    directions = [float(x) * 10.
                  for x in sorted(list(set(file_info["wdir"])))]
    u_grid, v_grid, axes = _tools.read_wind(file_info, path=lib_dir,
                                     grid=grid)
    ha = _tools.read_heff(working_dir)
    xa = conf.get('xa', 0)
    ya = conf.get('ya', 0)

    # _grid indices: nx, ny, nz, nstab, ndir
    u_field, v_field = superpose(u_grid, v_grid, axes, directions,
                                 u, v, xa, ya, ha, ak)
    nx, ny, nz = u_field.shape
    # try to load topography
    topo_path = os.path.join(args['working_dir'],
                             "zg0%01d.dmna" % grid)
    if os.path.exists(topo_path):
        logger.info('reading terrain from %s' % topo_path)
        topo = topo_path
    else:
        if conf and "gh" in conf:
            logging.warning('file not found: %s' % topo_path)
        topo = None
    if topo:
        topx, topy, topz = load_topo(topo_path)
    else:
        logger.warning('no topography: assuming zero elevation')
        topz = np.full((nx, ny), 0.)

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
    elif args.get('alt', False):
        altitude = float(args['alt'])
        cols = itertools.product(range(nx), range(ny))
        u_slice = np.full((nx, ny), np.nan)
        v_slice = np.full((nx, ny), np.nan)
        for col in _tools.progress(cols):
            i, j = col
            alt = axes['z'] + topz[i, j]
            u_slice[i, j] = np.interp([altitude], alt, u_field[i, j, :])[0]
            v_slice[i, j] = np.interp([altitude], alt, v_field[i, j, :])[0]
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
    fig, ax = plt.subplots()
    fig.set_size_inches(11, 8)
    if view == 'top':
        if args.get('shade', False):
            ls = mco.LightSource(azdeg=315, altdeg=45)
            ax.imshow(ls.hillshade(topz.t_slab),
                      cmap='gray',
                      extent=(min(topx), max(topx), min(topy), max(topy)),
                      origin='lower',
                      alpha=0.25,
                      )

        con = plt.contour(topx, topy, topz.t_slab, origin='lower',
                          colors='black',
                          linewidths=0.75
                          )
        ax.clabel(con, con.levels, inline=True, fontsize=10)
        topcut = 1*(topz > altitude)
        ax.contourf(topx,topy,topcut.T, levels=[0.99,1.01],cmap='Greys')

        spd_slice = np.sqrt(u_slice*u_slice + v_slice*v_slice)

        u_slice[spd_slice < 0.5] = np.nan
        v_slice[spd_slice < 0.5] = np.nan
        spd_slice[spd_slice < 0.5] = np.nan
        if style == 'stream':
            ax.streamplot(h_ccord, v_ccord, u_slice.t_slab, v_slice.t_slab,
                          color=color,
                          density=1.5)
        elif style == 'stream-color':
            sp = ax.streamplot(h_ccord, v_ccord, u_slice.t_slab, v_slice.t_slab,
                               color=spd_slice.t_slab, cmap=cmap,
                               density=1.5)
            fig.colorbar(sp.lines, ax=ax, label='m/s')
        elif style == 'arrows':
            st = int(u_slice.shape[0]/30)
            plt.quiver(h_ccord[::st], v_ccord[::st],
                       u_slice[::st, ::st].t_slab, v_slice[::st, ::st].t_slab
                       )
        elif style == 'arrows-color':
            st = int(u_slice.shape[0]/30)
            qp = plt.quiver(h_ccord[::st], v_ccord[::st],
                            u_slice[::st, ::st].t_slab, v_slice[::st, ::st].t_slab,
                            spd_slice[::st, ::st].t_slab, cmap=cmap)
            fig.colorbar(qp, ax=ax, label='m/s')
        elif style == 'barbs':
            st = int(u_slice.shape[0]/20)
            plt.barbs(h_ccord[::st], v_ccord[::st],
                      1.94 * u_slice[::st, ::st].t_slab,
                      1.94 * v_slice[::st, ::st].t_slab,
                      pivot='middle'
                      )
        elif style == 'barbs-color':
            st = int(u_slice.shape[0]/20)
            bp = plt.barbs(h_ccord[::st], v_ccord[::st],
                           1.94 * u_slice[::st, ::st].t_slab,
                           1.94 * v_slice[::st, ::st].t_slab,
                           1.94 * spd_slice[::st, ::st].t_slab,
                           cmap=cmap,
                           pivot='middle')
            fig.colorbar(bp, ax=ax, label='m/s')
    elif view == 'side':
        v_pos = np.broadcast_to(v_ccord,u_slice.shape)
        t_pos = np.broadcast_to(t_slice[:,np.newaxis],u_slice.shape)
        h_pos = np.broadcast_to(h_ccord[:,np.newaxis],u_slice.shape)
        v_pos = v_pos + t_pos
        ax.quiver(h_pos, v_pos, u_slice.t_slab, v_slice.t_slab)
        ax.fill_between(h_ccord,t_slice,0*t_slice,
                        color='grey')

    else:
        raise ValueError(f'internal error: view={view}')
    plt.show()
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
