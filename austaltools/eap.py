#!/bin/env python3
# -*- coding: utf-8 -*-
"""
This module is a custom implementation ot the process decsribed in
VDI 3783 part 16 [VDI3783p16]_ to find a replacement position
in case the wind measurements provided as input to the dispesion model
AUSTAL [AST31]_ are **not** taken by an anemometer inside the AUSTAL
model domain (i.e. on a nearby waether station or taken from a weather
model).

This position is referred to as "EAP" since in German,
it is called "Ersatz-AnemometerPosition" (anemometer spare position).
"""
import glob
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import warnings
from time import sleep

import numpy as np

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import pandas as pd

    import meteolib

try:
    from . import _dispersion
    from . import _plotting
    from . import _tools
    from ._metadata import __version__
except ImportError:
    import _dispersion
    import _plotting
    import _tools
    from _version import __version__

logger = logging.getLogger(__name__)

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    logging.getLogger('readmet.dmna').setLevel(logging.ERROR)
# -------------------------------------------------------------------------

# VDI 3783 part 8:
N_CLASS = 6
"""number of stability classes"""
N_EGDE_NODES = 3
"""
number of model nodes alon each side of the model domain
that should be excluded to avoid edge effects
"""
MIN_FF = 0.5
"""
minimum wind speed for which wind data are included
in the search algorithm
"""
MAX_HEIGHT = 100.
"""
maximum height to which wind data are included
in the search algorithm
"""
# VDI 3783 part 8 : "roughness matching the CLC land use class
# 'Meadows and Pastures (231)' of the LBM-DE"
# UBA Texte  36/2015: Tables 8
# CLC-class 231 corresponds to METRAS-class 3100 "Gras, kurz"
# Table 7: class 3100 -> z_0 = 0.0100
Z0_REFERENCE = 0.0100
"""
roughness lenght $z_0$ used for the calculation of reference wind
profiles, corresponding to CORINE class 231 "short grass",
according to VDI 3783 part 8 [VDI3783p8]_
"""


# -------------------------------------------------------------------------


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


# -------------------------------------------------------------------------
def contiguous_areas(array: np.ndarray) -> (np.ndarray, int):
    """
    Identify and label contiguous areas in a 2D binary array.

    This function takes a binary (boolean) 2D NumPy array as input and
    assigns a unique label to each contiguous region of adjacent 'True'
    values (considering 4-connectivity: top, bottom, left, right). The
    function returns a labeled array where each contiguous region has a
    unique integer label and the total number of unique contiguous areas.

    :param array: A 2D NumPy array of boolean values. Each 'True' or '1'
      in the array represents a part of a contiguous region, while 'False'
      or '0' represents the background.
    :type array: np.array
    :return: A tuple containing:
      - A 2D array of integers of the same shape as the input where each
      contiguous region of 'True' values is labeled with a unique
      integer.
      - The number of unique contiguous labeled areas in the input array.
    :rtype: Tuple[np.array, int]

    :notes: The function uses the union-find algorithm with path
      compression for efficient region labeling. The `getroot` helper
      function finds the root label of a given label to ensure each part
      of a contiguous area is assigned the same label.

    :examples:

        >>> arr = np.array([[1, 0, 0], [1, 1, 0], [0, 1, 1]]).astype(bool)
        >>> contiguous_areas(arr)
        (array([[0, -1, -1], [0, 0, -1], [-1, 0, 0]]), 1)
    """
    nx, ny = array.shape
    # initialize labels as with -1 = not an area
    labels = np.full((nx, ny), -1, dtype=int)
    # parents dictionary
    parent = {}
    # starting value = 0
    next_label = 0

    def getroot(mother, label):
        """ Helper function: find the root of the label """
        while mother[label] != label:
            label = mother[label]
        return label

    # pass 1: assign preliminary labels
    for i in range(nx):
        for j in range(ny):
            if array[i, j]:
                # check the neighbors up and left
                neighbors = []
                if i > 0 and array[i - 1, j]:
                    neighbors.append(labels[i - 1, j].item())
                if j > 0 and array[i, j - 1]:
                    neighbors.append(labels[i, j - 1].item())

                if not neighbors:
                    # next area label
                    labels[i, j] = next_label
                    parent[next_label] = next_label
                    next_label += 1
                else:
                    # assign point the min neighbour labels
                    min_label = min(neighbors)
                    labels[i, j] = min_label
                    # make the neighbour labels uniform
                    for n in neighbors:
                        root_n = getroot(parent, n)
                        root_min = getroot(parent, min_label)
                        if root_n != root_min:
                            parent[root_n] = root_min

    # pass 1: Resolve labels to their roots
    for i in range(nx):
        for j in range(ny):
            if labels[i, j] != -1:
                labels[i, j] = getroot(parent, labels[i, j])

    return labels, np.max(labels) + 1


# -------------------------------------------------------------------------

def calc_quality_measure(u_grid, v_grid, u_ref, v_ref,
                         nedge=N_EGDE_NODES, minff=MIN_FF,
                         maxlev=-1):
    """
    Caluclate the quality measure `g` according to VDI 3783 pt 16
    [VDI3783p16]_ by comparing a AUSTAL wind library to a reference
    profile.

    The wind library ist provided via the paramters `u_grid` and `v_grid`;
    the reference profile via the parameters `u_ref` and `v_ref`.
    Shape of wind fields: (nx, ny, nz, nstab, ndir),
    Shape of reference wind profiles: (nz, nstab, ndir),
    where nx, ny and nz are the dimensions of the AUSTAL model grid.

    :param u_grid: np.array of wind field eastward components
    :param v_grid: np.array of wind field northward components
    :param u_ref: np.array of reference wind eastward component
    :param v_ref: np.array of reference wind northward component
    :param nedge: number of excluded edge nodes
    :param minff: exclude data below this minimum wind speed
    :param maxlev: index of highest level to evaluate. <0 = evaluate all

    :return: fields of the quality criteria `g` and the individual
      measures `gd` (for the wind direction) and `gf` (for the wind speed),
      from which `g` is calculated (see Sect. 6.1 of VDI 3783 pt 16
      [VDI3783p16]_).
    :rtype: tuple[numpy.narray, numpy.narray, numpy.narray]
      The levels of wind fields must match heights of
      the reference wind profiles

    :raises: ValueError: if the levels of wind fields do not
      match the heights of the reference wind profiles

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

    # create empty result field
    keep = np.full((nx, ny, nz, nstab, ndir), 1.)

    # VDI 3783 pt 16 sct 6.1
    # `1) Only grid points inside the largest calculation
    #  area without the three outer boundary points are
    #  considered.`
    keep[:nedge, :, :, :, :] = np.nan
    keep[:, :nedge, :, :, :] = np.nan
    keep[-nedge:, :, :, :, :] = np.nan
    keep[:, -nedge:, :, :, :] = np.nan

    # VDI 3783 pt 16 sct 6.1
    # `2) All grid points are rejected at which the wind
    #  does not rotate in the same sense with every
    #  rotation of the undisturbed flow direction or at
    #  which in at least one of the wind fields the wind
    #  speed is below 0,5 m · s–1. The rest of the steps
    #  are performed only for the remaining grid
    #  points.`
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

    # `3) At each grid point, the quality criteria gd (for the
    #  wind direction) and gf (for the wind speed) are
    #  calculated over all undisturbed flow sectors and
    #  stability classes:`
    u_ref3d = np.broadcast_to(u_ref, (nx, ny, nz, nstab, ndir))
    v_ref3d = np.broadcast_to(v_ref, (nx, ny, nz, nstab, ndir))
    sumw = np.sum(np.sum(u_keep + v_keep, axis=4), axis=3)
    sumw2 = np.sum(np.sum(u_keep ** 2 + v_keep ** 2, axis=4), axis=3)
    sumwr = np.sum(
        np.sum(u_keep * u_ref3d + v_keep * v_ref3d, axis=4), axis=3)
    sumr = np.sum(np.sum(u_ref3d + v_ref3d, axis=4), axis=3)
    sumr2 = np.sum(np.sum(u_ref3d ** 2 + v_ref3d ** 2, axis=4), axis=3)
    korr = float(2 * nstab * ndir)
    gd = np.full((nx, ny, nz), np.nan)
    for iz in range(nz):
        if iz <= nz_eval:
            for iy in range(ny):
                for ix in range(nx):
                    cov_wr = sumwr[ix, iy, iz] - (
                            sumr[ix, iy, iz] * sumw[ix, iy, iz]) / korr
                    var_r = sumr2[ix, iy, iz] - (
                            sumr[ix, iy, iz] ** 2) / korr
                    war_w = sumw2[ix, iy, iz] - (
                            sumw[ix, iy, iz] ** 2) / korr
                    gd[ix, iy, iz] = (cov_wr ** 2) / (var_r * war_w)
        else:
            gd[:, :, iz] = np.nan

    ff_grid = np.sqrt(u_keep ** 2 + v_keep ** 2)
    ff_ref3d = np.broadcast_to(np.sqrt(u_ref ** 2 + v_ref ** 2),
                               np.shape(ff_grid))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        beta_v = np.nanmean(np.nanmean(ff_grid / ff_ref3d, axis=4), axis=3)
        gf = np.minimum(beta_v, 1. / beta_v)

    # `4) The quality criteria gd and gf are combined into
    #  an overall criterion g = gd · gf. g always lies in
    #  the interval [0,1], where 0 means no agreement
    #  and 1 perfect agreement with the one-dimensional
    #  reference profiles.`
    g = gf * gd

    return g, gd, gf


# -------------------------------------------------------------------------

def find_eap(g_lower: np.ndarray):
    """
    Find the anemometer-position replacement
    (german: Ersatz-AnemometerPosition, EAP) location.

    :param g_lower: A 2D array representing the quality measure g
      for each x, y position in the model grid
    :type g_lower: numpy.ndarray
    :return:
      - List of EAP cancidate coordinates (x,y) in the grid.
      - List of corresponding upper-level quality measure 'g' values.
    :rtype: tuple[list[tuple[int, int]], list[float]]

    :note:
        - Within each individual contiguous region with wind direction
          rotating in the same sense,
          the overall criteria 'g' are added up to form 'G'.
        - In the contiguous region with the largest sum 'G',
          the grid point that exhibits the largest 'g'
          is considered the EAP location at each level.
        - If no contiguous regions are found,
          an empty list is returned.

    :example:
        >>> g_lower = np.array([[0.5, 0.8, 0.3],
        ...                     [0.2, 0.7, 0.9],
        ...                     [0.4, 0.6, 0.1]]).astype(float)
        >>> eap, g_upper = find_eap(g_lower)
        >>> print(eap)
        [(1, 2), (1, 1), (0, 1)]
        >>> print(g_upper)
        [2.4, 1.6, 1.3]
    """
    #
    # `5) Within each individual contiguous region with
    #  the wind direction rotating in the same sense,
    #  the overall criteria g are added up to G.`
    #
    # make array contents boolean
    good = np.isfinite(g_lower)
    # get map of labels (label=area number) and number of areas
    label, num_areas = contiguous_areas(good)
    # if there is at least one area
    if num_areas > 0:
        # add up the values of every area to G(area)
        g_upper = [np.nansum(g_lower[label == i]) for i in
                   range(num_areas)]
        # `In the contiguous region with the largest sum G,
        #  the grid point that exhibits the largest g is found.
        #  This location is defined as EAP.`
        #
        #  get index sort order (largest value first)
        g_upper_descending_indexes = np.argsort(g_upper)[::-1]
        # create sorted list of G(area)
        g_upper_sort = [g_upper[x] for x in g_upper_descending_indexes]
        # find max position for each label
        # ... make copy of g_lower that has zeroes instead of nans
        g_lower_no_nan = g_lower
        g_lower_no_nan[np.isnan(g_lower)] = 0.
        # ... max location for every area EAP(area) in descending oder of G
        eap = [
            np.unravel_index(
                np.multiply(g_lower_no_nan, label == x).argmax(),
                g_lower.shape
            ) for x in g_upper_descending_indexes
        ]
    else:
        eap = []
        g_upper_sort = []

    return eap, g_upper_sort


# -------------------------------------------------------------------------

def calc_all_eap(g, mx_lvl=None):
    """
     Find the anemometer-position replacement (EAP) location
     for all levels.

     :param g: A 3D array representing the criteria 'g'
       at all levels.
     :type g: numpy.ndarray

     :param mx_lvl: Maximum level to consider.
       If None, all levels are processed.
     :type mx_lvl: int, optional

     :return:

        A tuple containing two lists:

        - List of EAP coordinates (x, y) for each level.
        - List of corresponding upper-level 'g' values for each level.

     :rtype: tuple

     :notes:

       - For each level, the EAP location is determined
         using the `find_eap` function.
       - If `mx_lvl` is specified, only levels up to that
         value are processed.
       - Empty lists are returned for levels beyond `mx_lvl`.

     :example:

         >>> g = np.array([[[0.5, 0.8, 0.3],
         ...                [0.2, 0.7, 0.9],
         ...                [0.4, 0.6, 0.1]],
         ...               [[0.3, 0.6, 0.4],
         ...                [0.1, 0.5, 0.7],
         ...                [0.2, 0.8, 0.3]]])
         >>> eap_levels, g_upper_levels = calc_all_eap(g, mx_lvl=1)
         >>> print(eap_levels)
         [[[(1, 2), (1, 1), (0, 1)], [(1, 2), (1, 1), (0, 1)]]]
         >>> print(g_upper_levels)
         [[2.4, 1.6, 1.3], [1.6, 1.3, 1.1]]
     """
    g_upper_levels = []
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


# -------------------------------------------------------------------------

def interpolate_wind(u_in: list, v_in: list, z_in: list, levels: list):
    """
    Interpolates wind components (u, v) to specified levels.

    :param u_in: List of u-component wind values.
    :type u_in: list
    :v_in v_in: List of v-component wind values.
    :type v_in: list
    :param z_in: List of corresponding heights (z) for wind measurements.
    :type z_in: list
    :param levels: List of target heights to interpolate to.
    :type levels: list

    :return: Tuple containing interpolated u-component and v-component
      wind values.
    :rtype: tuple

    :raises: `ValueError` if lists are not all the same length

    :example:

        >>> u_values = [10.0, 15.0, 20.0]
        >>> v_values = [5.0, 8.0, 12.0]
        >>> heights = [0.0, 100.0, 200.0]
        >>> target_levels = [50.0, 150.0]
        >>> interpolate_wind(u_values, v_values, heights, target_levels)
        ([12.5, 17.5], [6.5, 10.0])
    """
    if not (len(u_in) == len(v_in) == len(z_in)):
        raise ValueError('u, v,, and z must have the same length')
    u_out = []
    v_out = []
    for ilev, lev in enumerate(levels):
        if lev in z_in:
            i1 = list(z_in).index(lev)
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
                i2 = np.searchsorted(np.array(z_in), lev)
                i1 = i2 - 1

            # convert to reference heights (index of ref dataframe)
            z1 = z_in[i1]
            z2 = z_in[i2]
            u1, d1 = meteolib.wind.uv2dir(u_in[i1], v_in[i1])
            u2, d1 = meteolib.wind.uv2dir(u_in[i2], v_in[i2])
            ww = meteolib.wind.LogWind(u=u1, z=z1, u2=u2, z2=z2)
            ff = ww.u(lev)
            um = np.interp([lev], [z1, z2], [u_in[i1], u_in[i2]])
            vm = np.interp([lev], [z1, z2], [v_in[i1], v_in[i2]])
            _, dd = meteolib.wind.uv2dir(um, vm)
            u, v = meteolib.wind.dir2uv(ff, dd)
        else:
            u = 0.
            v = 0.
        u_out.append(u)
        v_out.append(v)
    return u_out, v_out


# -------------------------------------------------------------------------


def run_austal(workdir, tmproot=None):
    """
    Creates a wind library using the diagnostig model TALdia
    by invoking the model AUSTAL with parameter ``-l``
    for the same location, but flat terrain,
    with the anemometer at the model origin.

    :param workdir: path to the working directory,
      i.e. the directory where ``austal.txt`` is stored
    :type workdir: str
    :param tmproot: path to a directory where temporary files are stored
    :type tmproot: str
    :return: grids of u and v windcomponents,
      dictionary containing axes, wind direction and stabilty classes,
      as out by `read_wind` and `read_grid`
    :rtype: tuple(numpy.ndarray, numpy.ndarray, dict)
    """
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
                    k, v = re.split(r"\s+", line.strip(), 1)
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
    topo = _tools.GridASCII(os.path.join(workdir, topo_file))
    topo.data = np.full(np.shape(topo.data), np.nanmedian(topo.data))
    topo.write(os.path.join(tmpdir, topo_file))

    # copy weather file
    shutil.copy(os.path.join(workdir, akterm_file),
                os.path.join(tmpdir, akterm_file))

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
                pbar.update(nglob - dmna_found)
            dmna_found = nglob
            logging.debug('caluclated wind fields: %i of %i' %
                          (dmna_found, dmna_expected))
    del pbar

    if p.returncode == 0:
        austal_ok = True
    else:
        for line in p.stdout.readlines():
            if "Windfeldbibliothek wurde erstellt" in line.decode():
                austal_ok = True
                break
        else:
            austal_ok = False
    if not austal_ok:
        raise ValueError('austal finished with an error')

    file_info = _tools.wind_files(os.path.join(tmpdir, 'lib'))
    u_tmp, v_tmp, ax_tmp = _tools.read_wind(
        file_info, os.path.join(tmpdir, 'lib'), centers=True)

    shutil.rmtree(tmpdir)
    logger.debug('removed temp directory: %s' % tmpdir)

    return u_tmp, v_tmp, ax_tmp


# -------------------------------------------------------------------------


def austal_ref(workdir, levels, dirs, tmproot=None, overwrite=False):
    """
    Extract the reference windprofile from the TALdia
    output generated by `run_austal`.

    :param workdir: path to the working directory,
      i.e. the directory where ``austal.txt`` is stored
    :type workdir: str
    :param levels: levels to interpolate the modeled wind profile to
    :type levels: list[float]
    :param dirs: wind directions wor which a reference profile should
      be generated. For each direction, the modeled wind profile with
      the nearest (input) wind direction is returned.
    :type dirs: list[float]
    :param tmproot: path to a directory where temporary files are stored
    :type tmproot: str
    :param overwrite: overwrite existing refence file
        (details see :py:func:`write_ref`)
    :type overwrite: bool|None
    :return: reference profiles at `levels` for each stability and each
       direction in `dirs`
    :rtype: numpy.ndarray of shape
      (<number of `levels`>, <number of stabilty classes>,
      <number of `dirs`>)
    """
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
              v_tmp[ix, iy, :, :, :], (z_tmp, s_tmp, d_tmp),
              overwrite=overwrite)

    # shape of reference wind profiles: (nz, nstab, ndir)
    u_ref = np.full((len(levels), N_CLASS, len(dirs)), np.nan)
    v_ref = np.full((len(levels), N_CLASS, len(dirs)), np.nan)

    for iso in range(N_CLASS):
        for ido, do in enumerate(dirs):
            # find profile with same stability class and nearest direction
            diff_min = 360.
            ui = vi = None
            for idi, di in enumerate(d_tmp):
                for isi, _ in enumerate(s_tmp):
                    # difference in -180 ... 180
                    diff_dir = (((do - di) + 180.) % 360.) - 180.
                    if isi == iso and abs(diff_dir) < abs(diff_min):
                        # this is the selected reference profile:
                        ui = u_tmp[ix, iy, :, isi, idi]
                        vi = v_tmp[ix, iy, :, isi, idi] + diff_dir
                        diff_min = diff_dir
            if diff_min == 360. or ui is None or vi is None:
                raise ValueError('no reference profile for ' +
                                 'stability class: %s' %
                                 _dispersion.KM2021.name(iso + 1))
            u_ref[:, iso, ido], v_ref[:, iso, ido] = \
                interpolate_wind(ui, vi, z_tmp, levels)

    return u_ref, v_ref


# -------------------------------------------------------------------------

def calc_ref(levels, dirs, overwrite=False):
    """
    calculate reference wind profile from diabatic wind profile
    after Monin-Obukhov

    :param levels: desired levels to get reference winds for
    :param dirs: desired wind directions to get reference winds for
    :param overwrite: overwrite existing refence file
        (details see :py:func:`write_ref`)
    :type overwrite: bool|None
    :return: u-reference wind and v-reference wind,
      dimensions (#levels, #stability classes, #wind directions)
    :rtype: numpy.ndarray, numpy.ndarray
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
    # turning angle at inversion height after Van Ulden & Holtslag (1985)
    d_h = [
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
            d_20 = d_h[istab] * 1.58 * (
                        1. - np.exp(-1.0 * 20. / val_z_i[istab]))
            for iz, z in enumerate(levels):
                if z < (ww.z0 + ww.d):
                    ff = 0
                elif z > h_ref:
                    ff = ww.u(h_ref)
                else:
                    ff = ww.u(z)
                d_z = d_h[istab] * 1.58 * (
                            1. - np.exp(-1.0 * z / val_z_i[istab]))
                dd = wdir - d_20 + d_z
                logger.debug(str([istab, idir, z, ff, dd]))
                (u_ref[iz, istab, idir],
                 v_ref[iz, istab, idir]
                 ) = meteolib.wind.dir2uv(ff, dd)
    write_ref("Ref1d.dat", levels, dirs, u_ref, v_ref,
              (levels, [x for x in range(N_CLASS)], dirs))
    return u_ref, v_ref


# -------------------------------------------------------------------------

def read_ref(file: str, levels: list[float], dirs: list[float],
             linear_interpolation: bool = False):
    """
    read reference wind profiles from file and interpolate / rotate
    them to the desired levels / wind directions

    :param file: file to read, including path
    :type file: str
    :param levels: desired levels to get reference winds for
    :type levels: list[float]
    :param dirs: desired wind directions to get reference winds for
    :type dirs: list[float]
    :param linear_interpolation: linearly interpolate wind profile
      instead of using a log wind profile (for comparison to the VDI
      reference implementation)
    :type linear_interpolation: bool
    :return: u-reference wind and v-reference wind,
      dimensions: levels, stability classes, wind directions
    :rtype: numpy.ndarray, numpy.ndarray

    """
    logger.debug("reading wind reference file")
    ndir = len(dirs)
    nlev = len(levels)

    # isd have the form wS0DD
    x = pd.read_table(file, skiprows=1, nrows=0, sep=r'\s+',
                      skipinitialspace=True,
                      quotechar="'", engine="python")
    ref_id = [x.replace('\'', '') for x in list(x.columns)]
    # stab is zero-based: 0...5
    ref_stab = [int(x[1:2]) - 1 for x in ref_id]
    ref_dir = [float(x[3:5]) * 10 for x in ref_id]

    df = pd.read_table(file, skiprows=2, header=None, index_col=0,
                       sep=r'\s+',
                       engine="python")
    ref_ff = df[[2 * x + 1 for x in range(len(ref_id))]]
    ref_ff.columns = ref_id
    ref_dd = df[[2 * x + 2 for x in range(len(ref_id))]]
    ref_dd.columns = ref_id

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
                    rf = ref_ff[rid][:]
                    rd = ref_dd[rid][:] + diff_dir
                    diff_min = diff_dir
            if diff_min == 360.:
                raise ValueError('no reference profile for ' +
                                 'stability class: %s' %
                                 _dispersion.KM2021.name(istab + 1))
            uf, vf = meteolib.wind.dir2uv(rf, rd)

            if linear_interpolation:
                u_ref[:, istab, idir] = np.interp(levels, rf.index.values,
                                                  uf)
                v_ref[:, istab, idir] = np.interp(levels, rf.index.values,
                                                  vf)
            else:
                # get index of first height that is > 0
                i0 = np.argmax(rf.index.values > 0)
                u_ref[:, istab, idir], v_ref[:, istab, idir] = \
                    interpolate_wind(uf[i0:], vf[i0:],
                                     rf.index.values[i0:], levels)

    return u_ref, v_ref


# -------------------------------------------------------------------------

def write_ref(file: str, out_levels: list[float] | np.ndarray,
              out_dirs: list[float] | np.ndarray,
              u_ref: np.ndarray,
              v_ref: np.ndarray,
              axes_ref: tuple[
                  list[float] | np.ndarray,
                  list[float] | np.ndarray,
                  list[float] | np.ndarray
              ],
              overwrite:bool|None = None):
    """
    Write a set of windprofiles (one for each stability calass and each
    wind direction) into a file in the format of the example file
    ``Ref1d.dat`` provided as part of the reference implemetation in
    ``TAL-Anemo.zip`` wich belongs to the auxiliary material published
    with VDI norm 3783 part 16 [VDI3783p16]_

    :param file: fiell name of the file to write
    :type file: str
    :param out_levels: Levels at which the wind profiles should be stored
    :type out_levels: list[float]
    :param out_dirs: Directions for which the wind should be stored.
      This is the input wind (i.e. the larger-scale wind direction)
    :type out_dirs: list[float]
    :param u_ref: u-reference wind field as out by `read_wind`
    :type u_ref: numpy.ndarray
    :param v_ref: v-reference wind field as out by `read_wind`
    :type v_ref: numpy.ndarray
    :param axes_ref: dictionary containing axes, wind direction and stabilty classes,
      as out by `read_wind` and `read_grid`
    :type axes_ref: dict[numpy.ndarray]
    :param overwrite: overwrite existing reference profile file.
      If True, an existing file is overwritten, if False a FileExistsError
      is raises, if None and the file exists, the user is prompted
      with timeout
      (overwrites if yes, exits if not, defaults to overwrite).
    :type overwrite: bool|None

    :raises FileExistsError: if the file exists and overwrite is False
    """

    if os.path.exists(file):
        logger.debug('file %s already exists' % file)
        if overwrite is None:
            yesno = ""
            while yesno not in ["y", "n"]:
                yesno = _tools.prompt_timeout(
                    f'replace {file} [y]/n ?', 10, 'y')
            if yesno == "n":
                logger.critical('aborting')
                sys.exit(0)
        elif not overwrite:
            
            raise FileExistsError('file %s already exists'  % file)


    logger.debug("writing wind reference file")
    levels, stabs, dirs = axes_ref
    ndir = len(dirs)
    nlev = len(levels)

    with open(file, "w") as fid:
        fid.write("%-8i' Anzahl Profilpunkte\n" % nlev)
        for ilev in range(-1, nlev):
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
                                                          dirs[idir] / 10)
                    else:
                        ff, dd = meteolib.wind.uv2dir(
                            u_ref[ilev, istab, idir],
                            v_ref[ilev, istab, idir])
                        line += "%5.2f %5.1f    " % (ff, dd)
            if levels[ilev] not in out_levels:
                continue
            fid.write(line + "\n")


# -------------------------------------------------------------------------

def print_report(args: dict, g: np.ndarray, gd: np.ndarray,
                 gf: np.ndarray, eaps: list[list[tuple]],
                 g_upper: [list[list[float]]], axes: dict[str, list]):
    """
    print a report that mimics the output of the reference implemetation in
    ``TAL-Anemo.zip`` wich belongs to the auxiliary material published
    with VDI norm 3873 part 16 [VDI3783p16]_

    :param args:  the command line arguments as dictionary
    :type args: dict
    :param g: quality measure `g` (see `calc_quality_measure`)
    :type g: numpy.ndarray
    :param gd: quality measure `gd` (see `calc_quality_measure`)
    :type gd: numpy.ndarray
    :param gf: quality measure `gf` (see `calc_quality_measure`)
    :type gf: numpy.ndarray
    :param eaps: ErsatzAneometerPosition EAPs
      (anemometer replacement positions)
      as output by `calc_all_eap`
    :type eaps: numpy.ndarray
    :param g_upper: List of quality measures `g` calculates at the EAP
      positions
    :type g_upper: numpy.ndarray
    :param axes: grid positions alon each axis of the AUSTAL model domain
      in m
    :type axes: dict[str, list]
    """

    print('Bibliotheksverzeichnis ist %s' % args['working_dir'])
    print()
    print('------------------------------------------------------------'
          '-----------------------------------')
    print('Mindestanforderungen fuer Eignung von Modellgitterpunkten '
          'als Ersatz-Anemometerstandort:')
    print('Anzahl nicht ausgewerteter Randpunkte im aeusseren Gitter: '
          '%i' % N_EGDE_NODES)
    print('Windgeschwindigkeit immer groesser oder gleich ..........: '
          '%.1f m/s' % MIN_FF)
    print('------------------------------------------------------------'
          '-----------------------------------')
    print()
    print('Auswertegebiet Gitter  1  West - Ost : %9.0f bis %9.0f' %
          (min(axes['x']), max(axes['x'])))
    print('                          Sued - Nord: %9.0f bis %9.0f' %
          (min(axes['y']), max(axes['y'])))
    print()
    print(
        '=============================================================='
        '=================================================')
    print(
        '==================    Objektiv bestimmte Ersatz-Anemometerorte'
        ' im Gitter 1 je Modellebene:    =================')
    print(
        '=============================================================='
        '=================================================')
    print()
    for lvl, height in enumerate(axes['z']):
        if len(eaps[lvl]) > 0:
            i, j = eaps[lvl][0]
            print()
            print('******************    Modelllevel:%4i - Levelhoehe '
                  'ueber Grund:%7.1f m         ******************'
                  % (lvl + 1, axes['z'][lvl]))
            print()
            print('...................................'
                  '...................................'
                  '.........................')
            print('Empfohlener Ersatzanemometerort:   '
                  'Gesamt-G =%9.1f' % g_upper[lvl][0])
            print('                                   '
                  'EAP-Punkt:')
            print('                                   '
                  ' i-Index =%9i' % (i + 1))
            print('                                   '
                  ' j-Index =%9i' % (j + 1))
            print('                                   '
                  '   x (m) =%9.0f' % axes['x'][i])
            print('                                   '
                  '   y (m) =%9.0f' % axes['y'][j])
            print('                                   '
                  '      gd =%9.2f' % gd[i, j, lvl].item())
            print('                                   '
                  '      gf =%9.2f' % gf[i, j, lvl].item())
            print('                                   '
                  '       g =%9.2f' % g[i, j, lvl].item())
            print('...................................'
                  '...................................'
                  '.........................')


# -------------------------------------------------------------------------

def main(args):
    """
    This is the main working function

    :param args: the command line arguments as dictionary
    :type args: dict
    """
    logger.debug(format(args))
    #
    # read the wind library data
    #
    working_dir = args["working_dir"]
    lib_dir = _tools.wind_library(working_dir)
    file_info = _tools.wind_files(lib_dir)
    directions = [float(x) * 10.
                  for x in sorted(list(set(file_info["wdir"])))]
    u_grid, v_grid, axes = _tools.read_wind(file_info,
                                            path=lib_dir,
                                            grid=int(args['grid']),
                                            centers=True)
    #
    # get the reference profile
    #
    vdi = args.get('vdi', False)
    overwrite = args.get('overwrite', None)
    if args['reference'] == 'simple':
        u_ref, v_ref = calc_ref(axes['z'], directions, overwite=overwrite)
    elif args['reference'] == 'file':
        u_ref, v_ref = read_ref('Ref1d.dat', axes['z'], directions,
                                linear_interpolation=vdi)
    elif args['reference'] == 'austal':
        u_ref, v_ref = austal_ref(working_dir, axes['z'], directions,
                                  tmproot=working_dir, overwrite=overwrite)
    else:
        raise ValueError(
            'unknown kind of reference: %s' % args['reference'])
    #
    # find EAPs for each level
    #
    mx_height = float(args['max_height'])
    mx_lvl = int(np.argmax(axes['z'] * (np.array(axes['z']) <= mx_height)))
    logging.info('evaluation limited to %.0fm = level %i' %
                 (mx_height, mx_lvl))
    g, gd, gf = calc_quality_measure(u_grid, v_grid, u_ref, v_ref,
                                     nedge=args['edge_nodes'],
                                     minff=args['min_ff'],
                                     maxlev=mx_lvl)
    eaps, g_upper = calc_all_eap(g, mx_lvl)

    #
    # show results on screen
    if args['report']:
        print_report(args, g, gd, gf, eaps, g_upper, axes)

    #
    # select level closest to height
    #
    if args['height'] is None:
        try:
            wind_height = _tools.read_heff(working_dir)
        except (IOError, FileNotFoundError) as e:
            logger.error('cannot determine h_eff from configuration. '
                         'Use -z to give height manually.')
            
            raise e
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
    # write to austal config
    #
    if args['austal']:
        _tools.put_austxt(data={
            'xa': [axes['x'][eaps[selected_level][0][0]]],
            'ya': [axes['y'][eaps[selected_level][0][1]]]
        })

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
        _plotting.common_plot(args, dat=dat_dict, mark=pos_dict,
                              scale=scale)
    else:
        logger.info('nothing selected, skipping plot')


# -------------------------------------------------------------------------

def add_options(subparsers):
    pars_eap = subparsers.add_parser(
        name='eap',
        help='find substitute anemometer position ' +
             'according to VDI 3783 Part 16 ' +
             'from a wind library generated by AUSTAL')
    pars_eap.add_argument('-a', '--austal',
                          action='store_true',
                          help='write EAP as anemometer position into'
                               'AUSTAL config file ``austal.txt``')
    pars_eap.add_argument('-g', '--grid',
                          metavar='ID',
                          nargs='?',
                          default=0,
                          help='ID (number) of the grid to evaluate. '
                               'Defaults to 0')
    pars_eap.add_argument('-o', '--overwrite',
                          action='store_true',
                          default=False,
                          help='force overwriting wind reference file '
                               'if it exists.')
    pars_eap.add_argument('-q', '--report',
                          action='store_true',
                          help='show detailed results')
    pars_eap.add_argument('-r', '--reference',
                          default='simple',
                          choices=['simple', 'file', 'austal'],
                          help='choose kind of reference profile. '
                               '`simple` produces a log wind profile, '
                               '`file` reads reference profile from file. '
                               'Defaults to `simple`')
    pars_eap.add_argument('-z', '--height',
                          metavar='METERS',
                          nargs='?',
                          default=None,
                          help='effective anemometer height, i.e. height '
                               'to evaluate EAP at in m. '
                               'Defaults to 10.0')
    pars_adv_eap = pars_eap.add_argument_group('advanced options')
    pars_adv_eap.add_argument('--edge-nodes',
                              default=N_EGDE_NODES,
                              nargs='?',
                              help='number of edge nodes along each side, '
                                   'where data are exluded. ' +
                                   'Defaults to %i' % N_EGDE_NODES)
    pars_adv_eap.add_argument('--max-height',
                              default=MAX_HEIGHT,
                              nargs='?',
                              help='maximum height to evaluate EAP. ' +
                                   'Defaults to %f' % MAX_HEIGHT)
    pars_adv_eap.add_argument('--min-ff',
                              default=MIN_FF,
                              nargs='?',
                              help='minimum wind speed below which data are '
                                   'exluded. ' +
                                   'Defaults to %f' % MIN_FF)
    pars_adv_eap.add_argument('--vdi-reference',
                              dest='vdi',
                              action='store_true',
                              help='Use linear wind profile interpolation '
                                   'for comparison with VDI 3783 p 16 '
                                   'reference implementation.')
    pars_eap = _tools.add_arguents_common_plot(pars_eap)

    return pars_eap
