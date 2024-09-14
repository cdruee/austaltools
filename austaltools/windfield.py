#!/bin/env python3
# -*- coding: utf-8 -*-
"""
This module ...
"""
import itertools
import logging
import os

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import numpy as np

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
    except ImportError:
        have_matplotlib = False
        have_display = False
        matplotlib = None
        plt = None

try:
    from . import _tools
    from ._version import __version__
    from . import _dispersion
except ImportError:
    import _tools
    from _version import __version__
    import _dispersion

logging.basicConfig()
logger = logging.getLogger()

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    logging.getLogger('readmet.dmna').setLevel(logging.ERROR)


def load_topo(topo_path):
    logger.info('reading topography from %s' % topo_path)
    topofile = readmet.dmna.DataFile(topo_path)
    topz = topofile.data[""]
    topx = topofile.axes(ax="x")
    topy = topofile.axes(ax="y")
    return topx, topy, topz

def superpose(u_grid, v_grid, axes, dirs,
              u, v, xa, ya, ha, ak):
    # _grid indices: nx, ny, nz, nstab, ndir
    ix = np.argmin(abs(np.array(axes['x']) - xa))
    iy = np.argmin(abs(np.array(axes['y']) - ya))
    i_dir = [0,1]
    ui = [np.nan, np.nan]
    vi = [np.nan, np.nan]
    for i, id in enumerate(i_dir):
        ui[i] = np.interp(ha, axes['z'], u_grid[ix, iy, :, ak, id])
        vi[i] = np.interp(ha, axes['z'], v_grid[ix, iy, :, ak, id])
    print(u,ui)
    print(v,vi)
    # solve equation so that u, v = linea combi of ui,vi at anemometer
    a = (v*ui[1] - u *vi[1]) / (vi[0]*ui[1] - ui[0]*vi[1])
    if vi[1] > ui[1]:
        b = (v - a * vi[0]) / vi[1]
    else:
        b = (u - a * ui[0]) / ui[1]
    print(a,b)
    # calculate wind field
    u_field = (a * u_grid[:, :, :, ak, i_dir[0]] +
               b * u_grid[:, :, :, ak, i_dir[1]])
    v_field = (a * v_grid[:, :, :, ak, i_dir[0]] +
               b * v_grid[:, :, :, ak, i_dir[1]])
    print(np.min(u_field), np.max(u_field))
    print(np.min(v_field), np.max(v_field))
    return u_field, v_field


args={
    'working_dir': '../austal/Mayen80/',
    'grid':'0',
    #'vyz': '76',
    #'lvl': '2',
    'alt':'300',
}


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
    # read the wind library data
    #
    lib_dir = _tools.wind_library(working_dir)
    file_info = _tools.wind_files(lib_dir)
    directions = [float(x) * 10.
                  for x in sorted(list(set(file_info["wdir"])))]
    u_grid, v_grid, axes = _tools.read_wind(file_info, path=lib_dir,
                                     grid=grid)
    ha = _tools.read_heff(working_dir)
    # _grid indices: nx, ny, nz, nstab, ndir
    u=1;v=0;xa=0;ya=0;ak=1
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
    if args.get('lvl', False):
        level = int(args['lvl'])
        u_slice = u_field[:,:,level]
        v_slice = v_field[:,:,level]
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
    else:
        raise ValueError('no cut defined')


    fix, ax = plt.subplots()
    if view == 'top':
        con = plt.contour(topx, topy, topz.T, origin='lower',
                          colors='black',
                          linewidths=0.75
                          )
        ax.clabel(con, con.levels, inline=True, fontsize=10)
        topcut = 1*(topz > altitude)
        ax.contourf(topx,topy,topcut.T, levels=[0.99,1.01],cmap='Greys')
        spd_slice = np.sqrt(u_slice*u_slice + v_slice*v_slice)
        # sp = ax.streamplot(h_ccord, v_ccord, u_slice.T, v_slice.T,
        #               color=spd_slice, cmap='plasma',
        #               density=1.5)
        st=5
        plt.quiver(h_ccord[::st], v_ccord[::st],
                   u_slice[::st, ::st].T, v_slice[::st, ::st].T,
                   spd_slice[::st, ::st].T)
        #plt.colorbar(sp.lines, ax=ax, label='m/s')
    elif view == 'side':
        v_pos = np.broadcast_to(v_ccord,u_slice.shape)
        print(v_pos[0,:])
        t_pos = np.broadcast_to(t_slice[:,np.newaxis],u_slice.shape)
        print(t_pos[0,:])
        h_pos = np.broadcast_to(h_ccord[:,np.newaxis],u_slice.shape)
        v_pos = v_pos + t_pos
        ax.quiver(h_pos, v_pos, u_slice.T, v_slice.T)
        ax.fill_between(h_ccord,t_slice,0*t_slice,
                        color='grey')

    else:
        raise ValueError(f'internal error: view={view}')
    plt.show()
    # if args["plot"] == "__show__":
    #     logger.info('showing plot')
    #     plt.show()
    # elif args["plot"] not in [None, ""]:
    #     if os.path.sep in args["plot"]:
    #         outname = args["plot"]
    #     else:
    #         outname = os.path.join(args["working_dir"], args["plot"])
    #     if not outname.endswith('.png'):
    #         outname = outname + '.png'
    #     logger.info('writing plot: %s' % outname)
    #     plt.savefig(outname, dpi=180)

if __name__ == '__main__':
    main(args)