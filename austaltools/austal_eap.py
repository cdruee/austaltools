#!/bin/env python3

import argparse
import glob
import logging
import os
import re
import shutil
import subprocess
import tempfile
from time import sleep

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import numpy as np
    import pandas as pd
    from scipy import ndimage

    import readmet
    import meteolib

try:
    from . import _dispersion, _tools
except ImportError:
    import _dispersion, _tools

try:
    from ._version import __version__
except ImportError:
    from _version import __version__

logging.basicConfig()
logger = logging.getLogger()
logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
logging.getLogger('readmet.dmna').setLevel(logging.ERROR)
# -------------------------------------------------------------------------

# VDI 3783 part 8:
N_CLASS = 6
N_EGDE_NODES = 3
MIN_FF = 0.5
MAX_HEIGHT = 100.
# VDI 3783 part 8 : "roughness matching the CLC land use class
# 'Meadows and Pastures (231)' of the LBM-DE"
# UBA Texte  36/2015: Tables 8
# CLC-class 231 corresponds to METRAS-class 3100 "Gras, kurz"
# Table 7: class 3100 -> z_0 = 0.0100
Z0_REFERENCE = 0.0100


# -------------------------------------------------------------------------


def wind_library(path):
    # find directory that contains wind library
    if os.path.basename(path) == "lib":
        # path ist the lib-dir:
        libpath = path
    elif os.path.isdir(os.path.join(path, 'lib')):
        # lib-dir is in path:
        libpath = os.path.join(path, 'lib')
    else:
        logger.info('Warning: directory is NOT named lib')
        libpath = path
    logger.info('reading from directory: %s' % libpath)
    return libpath


def analyze_name(name):
    # grid index
    try:
        grid = int(name[6])
    except (ValueError, IndexError):
        raise ValueError("invalid filename (grid index): %s" % name)
    # wind direction
    try:
        adir = name[3:5]
        if adir == "sn":
            wdir = 18
        elif adir == "we":
            wdir = 27
        else:
            wdir = int(adir)
    except (ValueError, IndexError):
        raise ValueError("invalid filename (wind direction): %s" % name)
    # stability class
    try:
        ak = int(name[1:2])
    except (ValueError, IndexError):
        raise ValueError("invalid filename (stability class): %s" % name)
    return grid, wdir, ak


def wind_files(path):
    """
    find wind library files
    :param path: path where to search. Wind library files are expected
    to be in this path or in the subdirectory 'lib' of this path.
    :return: dict of lists containing names, stability classes,
    general wind directions, and grid indexes of all files.
    """
    wn = re.compile("w[0-9asnwe]{7}\.dmna")
    f_name = [x for x in os.listdir(path) if wn.match(x)]
    logger.debug('filenames: %s' % str(f_name))
    f_grid = []
    f_wdir = []
    f_stab = []
    for f in f_name:
        grid, wdir, ak = analyze_name(f)
        f_grid.append(grid)
        f_wdir.append(wdir)
        f_stab.append(ak)
    logger.debug('stabilty classes: %s' % str(f_stab))
    logger.debug('wind directions: %s' % str(f_wdir))
    logger.debug('grid indexes: %s' % str(f_grid))
    return {'name': f_name, 'stab': f_stab, "wdir": f_wdir, 'grid': f_grid}


def read_wind(file_info: dict, path: str = '.', grid: int = 0):
    """
    read wind library files

    :param file_info: dict of lists containing names, stability classes,
    general wind directions, and grid indexes of all files.
    :type file_info: dict
    :param path: Wind library files are expected
    to be in this path
    :type path: str
    :param grid: index of the grid for which to read the wind data
    :type grid: int
    :return: u_grid, v_grid, axes
    :rtype: tuple of (np.ndarray, np,dnarray, dict of lists of float)

    """
    if not isinstance(grid, int):
        raise ValueError('grid number is not numeric')
    if grid not in file_info['grid']:
        raise ValueError('grid %i not available in data' % grid)
    else:
        logger.info('reading grid: %i' % grid)
    # extract info for the wanted grid:
    grid_info = {}
    for k,v in file_info.items():
        grid_info[k] = [
            x for i,x in enumerate(file_info[k])
            if file_info['grid'][i] == grid
        ]
    ndir = len(set(grid_info["wdir"]))
    dirs = sorted(list(set(grid_info["wdir"])))
    nstab = len(set(grid_info['stab']))
    stabs = sorted(list(set(grid_info['stab'])))

    axes = readmet.dmna.DataFile(
        os.path.join(path, grid_info['name'][0])).axes()
    nx = len(axes['x'])
    ny = len(axes['y'])
    nz = len(axes['z'])

    u_grid = np.full((nx, ny, nz, nstab, ndir), np.nan)
    v_grid = np.full((nx, ny, nz, nstab, ndir), np.nan)

    for i in _tools.progress(range(len(grid_info['name'])),
                      desc="reading wind fields"):
        igrd, wdir, stab = analyze_name(grid_info['name'][i])
        if grid == igrd:
            filename = os.path.join(path, grid_info['name'][i])
            logger.debug('loading file: %s' % filename)
            dmna = readmet.dmna.DataFile(filename)
            istab = stabs.index(stab)
            idir = dirs.index(wdir)
            u_grid[:, :, :, istab, idir] = dmna.data['Vx']
            v_grid[:, :, :, istab, idir] = dmna.data['Vy']
    axes['dir'] = [x * 10. for x in dirs]
    axes['ak'] = stabs
    return u_grid, v_grid, axes

def read_heff(working_dir):
    """
    get effective anemometer height from
    z0 defined in austal.txt and the heights
    given in the akterm file (weather timeseries) given
    as parameter 'az'

    :param working_dir: the working directoty of austal[2000],
    where austal.txt resides
    :return: effective anemometer height
    :rtype float

    """
    austxt = _tools.find_austxt(working_dir)
    conf = _tools.get_austxt(austxt)
    if 'z0' in conf:
        z0 = float(conf['z0'][0])
    else:
        raise ValueError('no z0 defined, cannot read h_eff')
    if 'az' in conf:
        az_file = conf['az'][0]
    else:
        raise ValueError('no az defined, cannot read h_eff')
    z0_class = _tools.find_z0_class(z0)
    az = readmet.akterm.DataFile(file=az_file)
    heff = float(az.heights[z0_class])
    return heff


def same_sense_rotation(val, ref):
    """
    return true if directions (in degrees) in
    val and ref both rotate in the same direction

    :param val: (array of float) tested wind directions
    :param ref: (array of float) reference wind directions
    :returns bool: Sense ist the same
    """
    val_diff = np.sign(np.diff(val % 360.))
    ref_diff = np.sign(np.diff(ref % 360.))
    if all(ref_diff >= 0):
        sense = +1
    elif all(ref_diff <= 0):
        sense = -1
    else:
        # logger.warning("wind reference not sorted: %s" % str(ref))
        sense = 0
    if all(val_diff >= 0) and sense > 0:
        res = True
    elif all(val_diff <= 0) and sense < 0:
        res = True
    else:
        res = False
    return res


def calc_quality_measure(u_grid, v_grid, u_ref, v_ref,
                         nedge=N_EGDE_NODES, minff=MIN_FF,
                         maxlev=-1):
    """
    :param u_grid: np.array of wind field eastward components
    :param v_grid: np.array of wind field northward components
    :param u_ref: np.array of reference wind eastward component
    :param v_ref: np.array of reference wind northward component
    :param nedge: number of excluded edge nodes
    :param minff: exclude data below this minimum wind speed
    :param maxlev: index of highest level to evaluate. <0 = evaluate all

    shape of wind fields: (nx, ny, nz, nstab, ndir)
    shape of reference wind profiles: (nz, nstab, ndir)
    levels of wind fields must match heights of the reference wind profiles
    """
    #
    # check if wind grid sizes do match:
    if not (np.shape(u_grid) == np.shape(v_grid)):
        raise ValueError('wind grid shapes do not match')
    nx, ny, nz, nstab, ndir = np.shape(u_grid)
    if 0 <= maxlev < nz:
        nz_eval = maxlev
    else:
        nz_eval = nz
    # check if reference wind grid sizes do match:
    if not (np.shape(u_ref) == np.shape(v_ref)):
        raise ValueError('wind grid shapes do not match')
    if not (nz, nstab, ndir) == np.shape(u_ref):
        raise ValueError('wind grid shape does not match wind grid shape')

    # create result
    keep = np.full((nx, ny, nz, nstab, ndir), 1.)

    # VDI 3783 pt 16 sct 6.1
    # 1) Only grid points inside the largest calculation
    # area without the three outer boundary points are
    # considered.
    keep[:nedge, :, :, :, :] = np.nan
    keep[:, :nedge, :, :, :] = np.nan
    keep[-nedge:, :, :, :, :] = np.nan
    keep[:, -nedge:, :, :, :] = np.nan

    # VDI 3783 pt 16 sct 6.1
    # 2) All grid points are rejected at which the wind
    # does not rotate in the same sense with every
    # rotation of the undisturbed flow direction or at
    # which in at least one of the wind fields the wind
    # speed is below 0,5 m · s–1. The rest of the steps
    # are performed only for the remaining grid
    # points.
    for ibar in _tools.progress(range(nz_eval * nstab),
                         desc="do quality measure "):
        iz = ibar // nstab
        istab = ibar % nstab
        if iz <= nz_eval:
            ff_ref, dd_ref = meteolib.wind.uv2dir(u_ref[iz, istab, :],
                                                  v_ref[iz, istab, :])
            logger.debug('lvl: %4.0f, AK: %1i' % (iz, istab))
            if any(ff_ref < minff):
                keep[:, :, iz, istab, :] = np.nan
            else:
                for ix in range(nx):
                    for iy in range(ny):
                        ff_val, dd_val = meteolib.wind.uv2dir(
                            u_grid[ix, iy, iz, istab, :],
                            v_grid[ix, iy, iz, istab, :]
                        )
                        if any(ff_val < minff):
                            keep[ix, iy, iz, istab, :] = np.nan
                        elif not same_sense_rotation(dd_val, dd_ref):
                            keep[ix, iy, iz, istab, :] = np.nan
    for iz in range(nz_eval + 1, nz):
        keep[:, :, iz, :, :] = np.nan
    u_keep = u_grid * keep
    v_keep = v_grid * keep

    # 3) At each grid point, the quality criteria gd (for the
    # wind direction) and gf (for the wind speed) are
    # calculated over all undisturbed flow sectors and
    # stability classes:
    u_ref3d = np.broadcast_to(u_ref, (nx, ny, nz, nstab, ndir))
    v_ref3d = np.broadcast_to(v_ref, (nx, ny, nz, nstab, ndir))
    sumw = np.sum(np.sum(u_keep + v_keep, axis=4), axis=3)
    sumw2 = np.sum(np.sum(u_keep ** 2 + v_keep ** 2, axis=4), axis=3)
    sumwr = np.sum(np.sum(u_keep * u_ref3d + v_keep * v_ref3d, axis=4), axis=3)
    sumr = np.sum(np.sum(u_ref3d + v_ref3d, axis=4), axis=3)
    sumr2 = np.sum(np.sum(u_ref3d ** 2 + v_ref3d ** 2, axis=4), axis=3)
    korr = float( 2 * nstab * ndir)
    gd = np.full((nx, ny, nz), np.nan)
    for iz in range(nz):
        if iz <= nz_eval:
            for iy in range(ny):
                for ix in range(nx):
                    cov_wr = sumwr[ix, iy, iz] - (sumr[ix, iy, iz] * sumw[ix, iy, iz]) / korr
                    var_r = sumr2[ix, iy, iz] - (sumr[ix, iy, iz] ** 2) / korr
                    war_w = sumw2[ix, iy, iz] - (sumw[ix, iy, iz] ** 2) / korr
                    gd[ix, iy, iz] = (cov_wr ** 2) / (var_r * war_w)
        else:
            gd[:, :, iz] = np.nan

    ff_grid = np.sqrt(u_keep ** 2 + v_keep ** 2)
    ff_ref3d = np.broadcast_to(np.sqrt(u_ref ** 2 + v_ref ** 2), np.shape(ff_grid))
    beta_v = np.mean(np.mean(ff_grid / ff_ref3d, axis=4), axis=3)
    gf = np.minimum(beta_v, 1 / beta_v)

    # 4) The quality criteria gd and gf are combined into
    # an overall criterion g = gd · gf. g always lies in
    # the interval [0,1], where 0 means no agreement
    # and 1 perfect agreement with the one-dimensional
    # reference profiles.
    g = gf * gd

    return g, gd, gf

def find_eap(g_lower):
    # 5) Within each individual contiguous region with
    # the wind direction rotating in the same sense,
    # the overall criteria g are added up to G.
    # ones = np.prod(np.prod(keep * 1, axis=4), axis=3)
    ones = np.isfinite(g_lower) * 1
    label, num_features = ndimage.label(ones)
    if num_features > 0:
        g_upper = ndimage.labeled_comprehension(g_lower,
                                                label,
                                                range(1, num_features + 1),
                                                np.nansum,
                                                float,
                                                0)

        # In the contiguous region with the largest sum G,
        # the grid point that exhibits the largest g is found.
        # This location is defined as EAP.
        # get index sort order (largest value first)
        g_upper_descending_indexes = np.argsort(g_upper)[::-1]
        # ! maximum_position raises meaningless Index error
        #   if nan values are in the array
        g_notnan = g_lower
        g_notnan[np.isnan(g_notnan)] = 0
        # ! label is 1-based but index in g_upper_max is 0-based -> add 1
        eap = [ ndimage.maximum_position(g_notnan,
                                         label,
                                         x + 1)
                for x in g_upper_descending_indexes]
    else:
        eap = []
        g_upper = []

    return eap, g_upper

def calc_all_eap(g, mx_lvl=None):
    g_upper_levels =[]
    eap_levels = []
    for lvl in range(np.shape(g)[2]):
        if mx_lvl is None or lvl <= mx_lvl:
            eap, g_upper = find_eap(g[:, :, lvl])
            logger.info('level %2i: EAP %s' % (lvl, eap))
        else:
            eap = g_upper = []
        eap_levels.append(eap)
        g_upper_levels.append(g_upper)
    return eap_levels, g_upper_levels


def interpolate_wind(u_in:list, v_in:list, z_in:list, levels:list):
    if not (len(u_in) == len(v_in) == len(z_in)):
        raise ValueError('u, v,, and z must have the same length')
    u_out = []
    v_out = []
    for ilev, lev in enumerate(levels):
        if lev in z_in:
            i1 = z_in.index(lev)
            u = u_in[i1]
            v = v_in[i1]
        elif lev > 0:
            # get indices of reference heights neighbouring lev
            if lev <= min(z_in):
                i1 = 0
                i2 = 1
            elif lev >= max(z_in):
                i1 = len(z_in) - 2
                i2 = len(z_in) - 1
            else:
                i1 = np.searchsorted(np.array(z_in), lev, 'left')
                i2 = np.searchsorted(np.array(z_in), lev, 'right')
            # convert to reference heights (index of ref dataframe)
            z1 = z_in[i1]
            z2 = z_in[i2]
            u1, d1 = meteolib.wind.uv2dir(u_in[i1], v_in[i1])
            u2, d1 = meteolib.wind.uv2dir(u_in[i2], v_in[i2])
            ww = meteolib.wind.LogWind(u=u1, z=z1, u2=u2, z2=z2)
            ff = ww.u(lev)
            um = np.interp([lev], [z1, z2], [u_in[i1],u_in[i2]])
            vm = np.interp([lev], [z1, z2], [v_in[i1],v_in[i2]])
            _, dd = meteolib.wind.uv2dir(um, vm)
            u, v = meteolib.wind.dir2uv(ff, dd)
        else:
            u = 0.
            v = 0.
        u_out.append(u)
        v_out.append(v)
    return u_out, v_out

class GridASCII(object):
    file = None
    data = None
    _keys = ["ncols", "nrows", "xllcorner", "yllcorner", "cellsize", "NODATA_value"]
    header = {x: None for x in _keys}

    def __init__(self, file=None):
        if file is not None:
            self.read(file)

    def read(self, file):
        self.file = file
        self.data = np.loadtxt(file, skiprows=6)
        with open(file, "r") as f:
            for l in f:
                k, v = re.split("\s+", l.strip(), 1)
                if re.match('[0-9-.E]+', k):
                    # if fist field is a number the header is over
                    break
                elif k in self._keys:
                    self.header[k] = v
                else:
                    raise ValueError('unknown header value in file: %s' % k)

    def write(self, file=None):
        if file is None:
            file = self.file
        ascii_header = "\n".join(["%-12s %s" % (k, self.header[k])
                                  for k in self._keys])

        np.savetxt(file, self.data, header=ascii_header,
                   comments='', fmt="%4.0f", delimiter="")


def run_austal(workdir, tmproot=None):
    if tmproot is None:
        tmpdir = tempfile.mkdtemp(prefix="eap_", dir=workdir)
    else:
        tmpdir = tempfile.mkdtemp(prefix="eap_", dir=tmproot)
    #
    # copy modified austal command file
    #
    austal_org = os.path.join(workdir, 'austal.txt')
    if not os.path.exists(austal_org):
        raise ValueError('original austal.txt not found')
    austal_mod = os.path.join(tmpdir, 'austal.txt')
    topo_file = None
    with open(austal_org, 'r') as a:
        with open(austal_mod, 'w') as w:
            for line in a:
                try:
                    k, v = re.split("\s+", line.strip(), 1)
                except ValueError:
                    k = line.strip()
                    v = ''
                if k == 'gh':
                    topo_file = v.strip('\"\'')
                elif k == 'az':
                    akterm_file = v.strip('\"\'')
                elif k == 'z0':
                    v = Z0_REFERENCE
                elif k not in ['gx', 'gy', 'ux', 'uy', 'az', 'os',
                               'dd', 'x0', 'y0', 'nx', 'ny', 'nz']:
                    continue
                w.write(f"{k} {v}\n")
            for line in """
                
                xa 0
                ya 0
                
                xq 0
                yq 0
                xx 0.1
                hq 10
                
                qs -4
                """.splitlines():
                w.write("{}\n".format(line.strip()))
    #
    # make flat topography at same mean elevation
    #
    if topo_file is None:
        raise ValueError('no complex terrain defined')
    topo = GridASCII(os.path.join(workdir, topo_file))
    topo.data = np.full(np.shape(topo.data), np.nanmedian(topo.data))
    topo.write(os.path.join(tmpdir, topo_file))

    # copy weather file
    shutil.copy(os.path.join(workdir, akterm_file), os.path.join(tmpdir, akterm_file))

    # start austal model
    austal = shutil.which('austal')
    if austal is None:
        # if not in path: search other apparent locations
        for x in ['~/bin', '.local/bin', '~/ast', '~/a2k']:
            k = os.path.join(os.path.expanduser(x), 'austal')
            if os.path.exists(k):
                austal = k
                break
        else:
            raise OSError('austal executable not found')
    p = subprocess.Popen([austal, ".", "-l"], cwd=tmpdir,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)
    logging.info('started austal in: %s' % tmpdir)

    dmna_expected = N_CLASS * 2
    dmna_found = 0
    pbar = _tools.progress(total=dmna_expected)
    while p.poll() is None:
        sleep(0.5)
        dmna_files = glob.glob(os.path.join(tmpdir, 'lib', 'w*.dmna'))
        nglob = len(dmna_files)
        if nglob > dmna_found:
            if hasattr(pbar, 'update'):
                _tools.progress.update(nglob - dmna_found)
            dmna_found = nglob
            logging.debug('caluclated wind fields: %i of %i' %
                          (dmna_found, dmna_expected))
    del pbar

    if p.returncode == 0:
        austal_ok = True
    else:
        for line in p.stdout.readlines():
            if "Windfeldbibliothek wurde erstellt" in line:
                austal_ok = True
                break
        else:
            austal_ok = False
    if not austal_ok:
        raise ValueError('austal finished with an error')

    file_info = wind_files(os.path.join(tmpdir, 'lib'))
    u_tmp, v_tmp, ax_tmp = read_wind(file_info, os.path.join(tmpdir, 'lib'))

    shutil.rmtree(tmpdir)
    logger.debug('removed temp directory: %s' % tmpdir)

    return u_tmp, v_tmp, ax_tmp


def austal_ref(workdir, levels, dirs, tmproot=None):
    logger.debug("calculating refernce wind fields")
    u_tmp, v_tmp, ax_tmp = run_austal(workdir, tmproot)
    z_tmp = ax_tmp['z']
    d_tmp = ax_tmp['dir']
    s_tmp = ax_tmp['ak']


    logger.debug("extracting wind reference profile")
    # get index of position closest to the origin
    ix = np.argmin(np.abs(ax_tmp['x']))
    iy = np.argmin(np.abs(ax_tmp['y']))

    write_ref("Ref1d.dat", z_tmp, d_tmp, u_tmp[ix, iy, :, :, :],
              v_tmp[ix, iy, :, :, :], (z_tmp, s_tmp, d_tmp))


    # shape of reference wind profiles: (nz, nstab, ndir)
    u_ref = np.full((len(levels), N_CLASS, len(dirs)), np.nan)
    v_ref = np.full((len(levels), N_CLASS, len(dirs)), np.nan)

    for iso in range(N_CLASS):
        for ido, do in enumerate(dirs):
            # find profile with same stability class and nearest direction
            diff_min = 360.
            rf = rd = pd.Series(dtype=float)
            for idi, di in enumerate(d_tmp):
               for isi,_ in enumerate(s_tmp):
                    # difference in -180 ... 180
                    diff_dir = (((do - di) + 180.) % 360.) - 180.
                    if isi == iso and abs(diff_dir) < abs(diff_min):
                      # this is the selected reference profile:
                        ui = u_tmp[ix, iy, :, isi, idi]
                        vi = v_tmp[ix, iy, :, isi, idi] + diff_dir
                        diff_min = diff_dir
            if diff_min == 360.:
                raise ValueError('no reference profile for ' +
                                 'stability class: %s' %
                                 _dispersion.KM2021.name(iso + 1))
            u_ref[:, iso, ido], v_ref[:, iso, ido] = \
                interpolate_wind(ui, vi, z_tmp, levels)

    return u_ref, v_ref



def calc_ref(levels, dirs):
    """
    calculate reference wind profile from diabatic wind profile
    after Monin-Obukhov

    :param levels: desired levels to get reference winds for
    :param dirs: desired wind directions to get reference winds for
    :return: u-reference wind and v-reference wind,
    dimensions: levels, stability classes, wind directions
    :rtype numpy.ndarray, numpy.ndarray
    """
    logger.debug("calculating wind reference profile")
    # z0 = 0.02 # value for LBM-DE landcover class 231 (Wiesen und Weiden)
    # as required by VDI 3783 Blatt 16 sect. 6.1
    z0 = 0.1  # to be used instead since 2023 according to UBA TEXTE 144/2023
    # "Weiterentwicklung ausgewählter methodischer Grundlagen
    #  der Schornsteinhöhenbestimmung und der
    #  Ausbreitungsrechnung nach TA Luft"
    # calculated values according to VDI 3783 Blatt 16 table 1
    #
    # \Theta_g = \frac{\partial \Theta}{\partial z}
    # in K/m
    # val_theta_g = [
    #     0.008,
    #     0.0057,
    #     0.0032,
    #     0.0012,
    #     0.0003,
    #     0.0000
    # ]
    # # v_g
    # in m/s
    val_v_g = [
        1.6,
        1.5,
        7.8,
        5.6,
        4.2,
        3.8
    ]
    # inversion heights after VDI 3783 Blatt 8 (2002) Tab.4
    val_z_i = [
        250,
        250,
        800,
        800,
        1100,
        1100
    ]
    # Obukhov-length
    l_ob = [_dispersion.KM2021.get_center(x, z0=z0)
            for x in range(N_CLASS)]
    # turning angle at inversion height after Van Ulden & Holtslag 1985)
    D_h = [
        35,
        35,
        15,
        0,
        0,
        0
    ]

    # shape of reference wind profiles: (nz, nstab, ndir)
    u_ref = np.full((len(levels), N_CLASS, len(dirs)), np.nan)
    v_ref = np.full((len(levels), N_CLASS, len(dirs)), np.nan)

    for istab in range(N_CLASS):
        # VDI 3783 Blatt 8 (2002)
        # Prandtl layer is 0.1 the inversion height z_i
        # Wind speed reaches 80% v_g at top of the Prandtl layer
        h_ref = val_z_i[istab] * 0.1
        ffref = val_v_g[istab] * 0.8
        ww = meteolib.wind.DiabaticWind(z0=z0,
                                        u=ffref,
                                        z=h_ref,
                                        zoL=h_ref / l_ob[istab])
        for idir, wdir in enumerate(dirs):
            D_20 = D_h[istab] * 1.58*(1.-np.exp(-1.0*20./val_z_i[istab]))
            for iz, z in enumerate(levels):
                if z < (ww.z0 + ww.d):
                    ff = 0
                elif z > h_ref:
                    ff = ww.u(h_ref)
                else:
                    ff = ww.u(z)
                D_z = D_h[istab] * 1.58*(1.-np.exp(-1.0*z/val_z_i[istab]))
                dd = wdir - D_20 + D_z
                logger.debug(str([istab, idir, z, ff, dd]))
                (u_ref[iz, istab, idir],
                 v_ref[iz, istab, idir]) = meteolib.wind.dir2uv(ff, dd)
    write_ref("Ref1d.dat", levels, dirs, u_ref, v_ref,
              (levels, [x for x in range(N_CLASS)], dirs))
    return u_ref, v_ref


def read_ref(file, levels, dirs):
    """
    read reference wind profiles from file and interpolate / rotate
    them to the desired levels / wind directions

    :param file: file to read, including path
    :param levels: desired levels to get reference winds for
    :param dirs: desired wind directions to get reference winds for
    :return: u-reference wind and v-reference wind,
    dimensions: levels, stability classes, wind directions
    :rtype numpy.ndarray, numpy.ndarray

    """
    logger.debug("reading wind reference file")
    ndir = len(dirs)
    nlev = len(levels)

    # isd have the form wS0DD
    x = pd.read_table(file, skiprows=1, nrows=0, sep='\s+',
                      skipinitialspace=True,
                      quotechar="'", engine="python")
    ref_id = [x.replace('\'', '') for x in list(x.columns)]
    # stab is zero-based: 0...5
    ref_stab = [int(x[1:2]) - 1 for x in ref_id]
    ref_dir = [float(x[3:5]) * 10 for x in ref_id]

    df = pd.read_table(file, skiprows=2, header=None, index_col=0,
                       sep='\s+',
                       engine="python")
    ref_ff = df[[2 * x + 1 for x in range(len(ref_id))]]
    ref_ff.columns = ref_id
    ref_dd = df[[2 * x + 2 for x in range(len(ref_id))]]
    ref_dd.columns = ref_id
    # FIXME is that choice OK?
    # we can only safely use levels above max value of z0
    ref_min_z_level = min(df.index[df.index > 2])

    # shape of reference wind profiles: (nz, nstab, ndir)
    u_ref = np.full((nlev, N_CLASS, ndir), np.nan)
    v_ref = np.full((nlev, N_CLASS, ndir), np.nan)

    for istab in range(N_CLASS):
        for idir, d in enumerate(dirs):
            # find profile with same stability class and nearest direction
            diff_min = 360.
            rf = rd = pd.Series(dtype=float)
            for i, rid in enumerate(ref_id):
                # difference in -180 ... 180
                diff_dir = (((d - ref_dir[i]) + 180.) % 360.) - 180.
                if ref_stab[i] == istab and abs(diff_dir) < abs(diff_min):
                    # this is the selected reference profile:
                    rf = ref_ff[rid][ref_min_z_level:]
                    rd = ref_dd[rid][ref_min_z_level:] + diff_dir
                    diff_min = diff_dir
            if diff_min == 360.:
                raise ValueError('no reference profile for ' +
                                 'stability class: %s' %
                                 _dispersion.KM2021.name(istab + 1))
            uf, vf = meteolib.wind.dir2uv(rf, rd)

            u_ref[:, istab, idir], v_ref[:, istab, idir] = \
                interpolate_wind(uf, vf, rf.index.values, levels)
    return u_ref, v_ref


def write_ref(file, out_levels, out_dirs, u_ref, v_ref, axes_ref):
    logger.debug("writing wind reference file")
    levels, stabs, dirs = axes_ref
    ndir = len(dirs)
    nlev = len(levels)

    with open(file, "w") as fid:
        fid.write("%-8i' Anzahl Profilpunkte\n" % nlev)
        for ilev in range(-1,nlev):
            if ilev < 0:
                line = "        "
            else:
                line = "%5.1f   " % levels[ilev]
            for istab in range(N_CLASS):
                for idir in range(ndir):
                    if dirs[idir] not in out_dirs:
                        continue
                    if ilev < 0:
                        line += "'w%1i0%2.0f'        " % (istab + 1,
                                                          dirs[idir]/10)
                    else:
                        ff, dd = meteolib.wind.uv2dir(
                            u_ref[ilev, istab, idir],
                            v_ref[ilev, istab, idir])
                        line += "%5.2f %5.1f    " % (ff, dd)
            if levels[ilev] not in out_levels:
                continue
            fid.write(line + "\n")

def print_report(args, g, gd, gf, eaps, g_upper, axes):
    print('Bibliotheksverzeichnis ist %s' % args['working_dir'])
    print()
    print('-----------------------------------------------------------------------------------------------')
    print('Mindestanforderungen fuer Eignung von Modellgitterpunkten als Ersatz-Anemometerstandort:')
    print('Anzahl nicht ausgewerteter Randpunkte im aeusseren Gitter: %i' % N_EGDE_NODES)
    print('Windgeschwindigkeit immer groesser oder gleich ..........: %.1f m/s' % MIN_FF)
    print('-----------------------------------------------------------------------------------------------')
    print()
    print('Auswertegebiet Gitter  1  West - Ost : %9.0f bis %9.0f' % (min(axes['x']), max(axes['x'])))
    print('                          Sued - Nord: %9.0f bis %9.0f' % (min(axes['y']), max(axes['y'])))
    print()
    print('===============================================================================================================')
    print('==================    Objektiv bestimmte Ersatz-Anemometerorte im Gitter 1 je Modellebene:    =================')
    print('===============================================================================================================')
    print()
    for lvl,height in enumerate(axes['z']):
        if len(eaps[lvl]) > 0:
            i, j = eaps[lvl][0]
            print()
            print('******************    Modelllevel:%4i - Levelhoehe ueber Grund:%7.1f m         ******************'
                  % (lvl + 1, axes['z'][lvl]))
            print()
            print('...............................................................................................')
            print('Empfohlener Ersatzanemometerort:   Gesamt-G =%9.1f' % g_upper[lvl][0])
            print('                                   EAP-Punkt:')
            print('                                    i-Index =%9i' % (i + 1))
            print('                                    j-Index =%9i' % (j + 1))
            print('                                      x (m) =%9.0f' % axes['x'][i])
            print('                                      y (m) =%9.0f' % axes['y'][j])
            print('                                         gd =%9.2f' % gd[i,j,lvl])
            print('                                         gf =%9.2f' % gf[i,j,lvl])
            print('                                          g =%9.2f' % g[i,j,lvl])
            print('...............................................................................................')


def cli_parser():
    # defaults
    default = {
    }
    parser = argparse.ArgumentParser(
        description='find substitute anemometer position ' +
                    'according to VDI 3783 Part 16 ' +
                    'from a wind library generated by austal')
    parser = _tools.add_arguents_common_plot(parser)
    parser.add_argument('-g', '--grid',
                        metavar='ID',
                        nargs='?',
                        default=0,
                        help='ID (number) of the grid to evaluate. '
                             'Defaults to 0')
    parser.add_argument('-z', '--height',
                        metavar='METERS',
                        nargs='?',
                        default=None,
                        help='effective anemometer height, i.e. height ' +
                             'to evaluate EAP at in m. '
                             'Defaults to 10.0')
    parser.add_argument('-r', '--reference',
                        default='simple',
                        choices=['simple', 'file', 'austal'],
                        help='choose kind of reference profile. ' +
                             '`simple` produces a log wind profile, ' +
                             '`file` reads reference profile from file. ' +
                             'Defaults to `simple`')
    parser.add_argument('-q', '--report',
                        action='store_true',
                        help='show detailed results')
    parser.add_argument('--edge-nodes',
                        default=N_EGDE_NODES,
                        nargs='?',
                        help='number of edge nodes along each side, ' +
                             'where data are exluded. ' +
                             'Defaults to %i' % N_EGDE_NODES)
    parser.add_argument('--max-height',
                        default=MAX_HEIGHT,
                        nargs='?',
                        help='maximum height to evaluate EAP. ' +
                             'Defaults to %f' % MAX_HEIGHT)
    parser.add_argument('--min-ff',
                        default=MIN_FF,
                        nargs='?',
                        help='minimum wind speed below which data are '
                             'exluded. ' +
                             'Defaults to %f' % MIN_FF)

    parser.add_argument("--version",
                        version="%(prog)s " + str(__version__),
                        action="version")
    verb = parser.add_mutually_exclusive_group()
    verb.add_argument('--debug', dest='verb', action='store_const',
                      const=logging.DEBUG, help='show informative output')
    verb.add_argument('-v', '--verbose', dest='verb', action='store_const',
                      const=logging.INFO, help='show detailed output')
    return parser


def main():
    #
    # process user interface
    parser = cli_parser()
    args = vars(parser.parse_args())
    #
    # logging level
    #
    if args["verb"] is not None:
        logger.setLevel(args["verb"])
    else:
        logger.setLevel(logging.WARNING)
    logger.info(os.path.basename(__file__) + ' version: ' + __version__)

    logger.debug(format(args))
    #
    #

    #
    # read the wind library data
    #
    working_dir = args["working_dir"]
    lib_dir = wind_library(working_dir)
    file_info = wind_files(lib_dir)
    directions = [float(x) * 10.
                  for x in sorted(list(set(file_info["wdir"])))]
    u_grid, v_grid, axes = read_wind(file_info, path=lib_dir,
                                     grid=int(args['grid']))
    #
    # get the reference profile
    #
    if args['reference'] == 'simple':
        u_ref, v_ref = calc_ref(axes['z'], directions)
    elif args['reference'] == 'file':
        u_ref, v_ref = read_ref('/local/data/druee/software/austaltools/TAL-Anemo/Ref1d.dat', axes['z'], directions)
    elif args['reference'] == 'austal':
        u_ref, v_ref = austal_ref(working_dir, axes['z'], directions, tmproot=working_dir)
    else:
        raise ValueError('unknown kind of reference: %s' % args['reference'])
    #
    # find EAPs for each level
    #
    mx_height = float(args['max_height'])
    mx_lvl = np.argmax(axes['z'] * (np.array(axes['z']) <= mx_height))
    logging.info('evaluation limited to %.0fm = level %i' %
                 (mx_height, mx_lvl))
    g, gd, gf = calc_quality_measure(u_grid, v_grid, u_ref, v_ref,
                                     nedge=args['edge_nodes'],
                                     minff=args['min_ff'],
                                     maxlev=mx_lvl)
    eaps, g_upper = calc_all_eap(g,mx_lvl)

    #
    # select level closest to height
    #
    if args['height'] is None:
        wind_height = read_heff(working_dir)
    else:
        wind_height = float(args['height'])
    dz_old = np.nanmax(axes['z'])
    selected_level = -1
    for lvl in range(mx_lvl):
        dz = abs(axes['z'][lvl] - wind_height)
        if len(eaps[lvl]) > 0 and dz < dz_old:
            selected_level = lvl
            dz_old = dz
    logger.info(f'selected_level: {selected_level}')

    #
    # show results on screen
    if args['report']:
        print_report(args, g, gd, gf, eaps, g_upper, axes)

    #
    # create plot
    #
    if args['plot'] is not None and selected_level >= 0:
        dat_dict = {
            'x': axes['x'],
            'y': axes['y'],
            'z': g[:, :, selected_level]
        }
        pos_dict = {
            'x': [axes['x'][eaps[selected_level][0][0]]],
            'y': [axes['y'][eaps[selected_level][0][1]]]
        }
        dmin = np.floor(np.nanmin(dat_dict['z']) * 10) / 10
        dmax = np.ceil(np.nanmax(dat_dict['z']) * 10) / 10
        if dmax > 1.:
            dmax = 1.
        if dmin < 0.:
            dmin = 0.
        scale = (dmin, dmax)
        if args['plot'] == '-':
            args['plot'] = '__show__'
            logger.debug('select to show plot')
        elif args['plot'] == '__default__':
            args['plot'] = "eap_quality_measure"
            logger.debug('select to write plot to default filename')
        else:
            logger.debug('select to write plot to custom filename')
        _tools.common_plot(args, dat=dat_dict, mark=pos_dict, scale=scale)



if __name__ == "__main__":
    main()
