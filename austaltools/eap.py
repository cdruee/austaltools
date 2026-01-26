#!/bin/env python3
# -*- coding: utf-8 -*-
"""
This module implements the process described in VDI 3783 Part 16
:cite:`VDI3783p16` to find a substitute anemometer position (EAP)
when wind measurements provided as input to the dispersion model
AUSTAL :cite:`AST31` are **not** taken by an anemometer inside the
AUSTAL model domain (i.e., on a nearby weather station or taken from
a weather model).

The position is referred to as "EAP" since in German it is called
"Ersatz-Anemometer-Position" (substitute anemometer position).

The module provides three approaches for calculating reference wind profiles:

1. **General approach** (``calc_ref_geostrophic()``): Uses geostrophic wind
   speeds from VDI 3783 Part 16 Table 1 prescribed at inversion height.

2. **Adapted approach** (``calc_ref_adapted()``): Uses frequency-weighted
   mean wind speeds from the meteorological time series at the effective
   anemometer height. This matches the approach used by AUSTAL/TALdia
   for wind library generation.

3. **Austal approach** (``austal_ref()``): Runs the AUSTAL model that
   creates a wind library for the current configuration but with
   terrain removed adn retrieves the reference profiles from this library

Approaches 1 & 2 use the two-layer wind profile model from VDI 3783 Part 8
[VDI3783p8]_ with Monin-Obukhov similarity theory in the surface
layer and an Ekman spiral solution in the upper layer.

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
    import readmet

from . import _dispersion
from . import _plotting
from . import _tools

logger = logging.getLogger(__name__)

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    logging.getLogger('readmet.dmna').setLevel(logging.ERROR)
# -------------------------------------------------------------------------

# Constants
KAPPA = 0.4  # von Kármán constant
F_C = 1.1e-4  # Coriolis parameter at mid-latitudes (rad/s)

# VDI
VDI_GEOSTROPIC_WIND = [1.6, 2.5, 7.8, 5.6, 4.2, 3.8]
"""list of float: Geostrophic wind speed :math:`v_g` (m/s) for each 
stability class.

Values from VDI 3783 Part 16, Table 1.

Index 0 corresponds to Class I (very stable), 
Index 5 corresponds to Class V (very unstable).
"""

VDI_THETA_GRADIENT = [0.0080, 0.0057, 0.0032, 0.0012, 0.0003, 0.0000]
"""list of float: Potential temperature vertical gradient (K/m) for each 
stability class.

Values from VDI 3783 Part 16, Table 1.

Index 0 corresponds to Class I (very stable), 
Index 5 corresponds to Class V (very unstable).
"""

VDI_INVERSION_HEIGHT = [250, 250, 800, 800, 1100, 1100]
"""list of int: Mixing layer / inversion height :math:`h_m` (m) for each 
stability class.

Values from VDI 3783 Part 8 (2002), Table 4.

Index 0 corresponds to Class I (very stable), 
Index 5 corresponds to Class V (very unstable).
"""

# VDI_DEFAULT_ROUGHNESS = 0.02
# value for LBM-DE landcover class 231 (Wiesen und Weiden)
# as required by VDI 3783 Blatt 8 sect. 6.1
VDI_DEFAULT_ROUGHNESS = 0.1
"""float: Default roughness length :math:`z_0` (m) for wind profile 
calculation.

Value of 0.1 m is used instead of the original VDI value (0.02 m for 
LBM-DE class 231 "Wiesen und Weiden") since 2023, according to 
UBA TEXTE 144/2023 "Weiterentwicklung ausgewählter methodischer 
Grundlagen der Schornsteinhöhenbestimmung und der Ausbreitungsrechnung 
nach TA Luft".
"""

# VDI 3783 part 8:
N_CLASS = 6
"""int: Number of Klug-Manier stability classes (I through V, with III 
split into III/1 and III/2).
"""

N_EGDE_NODES = 3
"""int: Number of model nodes along each side of the model domain that 
should be excluded to avoid edge effects in the EAP search algorithm.
"""

MIN_FF = 0.5
"""float: Minimum wind speed (m/s) for which wind data are included in 
the EAP search algorithm.
"""

MAX_HEIGHT = 100.
"""float: Maximum height (m) above ground to which wind data are included 
in the EAP search algorithm.
"""

# VDI 3783 part 8 : "roughness matching the CLC land use class
# 'Meadows and Pastures (231)' of the LBM-DE"
# UBA Texte  36/2015: Tables 8
# CLC-class 231 corresponds to METRAS-class 3100 "Gras, kurz"
# Table 7: class 3100 -> z_0 = 0.0100
AUSTAL_ROUGHNESS = 0.0100
"""float: Roughness length :math:`z_0` (m) used for reference wind profile 
calculation.

Corresponds to CORINE class 231 "short grass", according to 
VDI 3783 Part 8 [VDI3783p8]_ .
"""


# -------------------------------------------------------------------------


def same_sense_rotation(val, ref):
    """
    Check if wind directions rotate in the same sense.

    Determines whether the wind directions in ``val`` and ``ref`` both
    rotate in the same direction (both clockwise or both counter-clockwise)
    as the input wind direction varies.

    :param val: Tested wind directions (degrees, meteorological convention).
    :type val: array-like
    :param ref: Reference wind directions (degrees, meteorological convention).
    :type ref: array-like
    :returns: ``True`` if both arrays rotate in the same sense, 
        ``False`` otherwise.
    :rtype: bool

    .. note::
        This function is used in the EAP algorithm to reject grid points 
        where the wind does not rotate consistently with the reference 
        profile as required by VDI 3783 Part 16, Section 6.1, criterion 2
        [vdi3783p16]_ .
    """

    def angdiff(ang: np.ndarray) -> np.ndarray:
        """Calculate angular differences wrapped to [-180, 180]."""
        return (np.diff(ang) + 180) % 360 - 180

    val_diff = np.sign(angdiff(val))
    ref_diff = np.sign(angdiff(ref))
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
def contiguous_areas(array: np.ndarray) -> tuple[np.ndarray, int]:
    """
    Identify and label contiguous areas in a 2D binary array.

    Assigns a unique label to each contiguous region of adjacent ``True``
    values using 4-connectivity (top, bottom, left, right neighbors).

    :param array: A 2D boolean array where ``True`` represents cells 
        belonging to a contiguous region and ``False`` represents background.
    :type array: numpy.ndarray
    :returns: A tuple containing:
    
        - **labels** (*numpy.ndarray*) -- A 2D integer array of the same 
          shape as ``array`` where each contiguous region is labeled with 
          a unique non-negative integer. Background cells are labeled with -1.
        - **num_areas** (*int*) -- The number of unique contiguous areas found.
    :rtype: tuple(numpy.ndarray, int)

    .. note::
        The function uses the union-find algorithm with path compression 
        for efficient region labeling in a two-pass approach.

    :example:

        >>> arr = np.array([[1, 0, 0], [1, 1, 0], [0, 1, 1]]).astype(bool)
        >>> labels, num = contiguous_areas(arr)
        >>> print(labels)
        [[ 0 -1 -1]
         [ 0  0 -1]
         [-1  0  0]]
        >>> print(num)
        1
    """
    nx, ny = array.shape
    # initialize labels as with -1 = not an area
    labels = np.full((nx, ny), -1, dtype=int)
    # parents dictionary
    parent = {}
    # starting value = 0
    next_label = 0

    def getroot(mother, label):
        """Find the root label using path compression."""
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

    # pass 2: Resolve labels to their roots
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
    Calculate the quality measure ``g`` according to VDI 3783 Part 16.

    Compares an AUSTAL wind library to a reference profile and calculates
    quality criteria for wind direction (``gd``) and wind speed (``gf``),
    which are combined into an overall quality measure ``g = gd * gf``.

    :param u_grid: Eastward wind component from the wind library.
        Shape: ``(nx, ny, nz, nstab, ndir)``.
    :type u_grid: numpy.ndarray
    :param v_grid: Northward wind component from the wind library.
        Shape: ``(nx, ny, nz, nstab, ndir)``.
    :type v_grid: numpy.ndarray
    :param u_ref: Eastward reference wind component.
        Shape: ``(nz, nstab, ndir)``.
    :type u_ref: numpy.ndarray
    :param v_ref: Northward reference wind component.
        Shape: ``(nz, nstab, ndir)``.
    :type v_ref: numpy.ndarray
    :param nedge: Number of edge nodes to exclude along each boundary.
        Default is :data:`N_EGDE_NODES`.
    :type nedge: int, optional
    :param minff: Minimum wind speed threshold (m/s). Grid points with 
        wind speed below this value are excluded. Default is :data:`MIN_FF`.
    :type minff: float, optional
    :param maxlev: Maximum level index to evaluate. Negative values mean 
        all levels are evaluated. Default is -1.
    :type maxlev: int, optional
    :returns: A tuple containing:
    
        - **g** (*numpy.ndarray*) -- Overall quality measure, 
          shape ``(nx, ny, nz)``. Values in [0, 1], where 1 indicates 
          perfect agreement.
        - **gd** (*numpy.ndarray*) -- Quality measure for wind direction, 
          shape ``(nx, ny, nz)``.
        - **gf** (*numpy.ndarray*) -- Quality measure for wind speed, 
          shape ``(nx, ny, nz)``.
    :rtype: tuple(numpy.ndarray, numpy.ndarray, numpy.ndarray)
    :raises ValueError: If grid shapes do not match or reference profile 
        dimensions are incompatible with the wind library.

    .. note::
        The algorithm follows VDI 3783 Part 16, Section 6.1 [vdi3783p16]_ :
        
        1. Exclude edge nodes (``nedge`` from each boundary).
        2. Reject points where wind doesn't rotate consistently or
           wind speed is below ``minff``.
        3. Calculate correlation-based direction criterion ``gd``.
        4. Calculate speed ratio criterion ``gf``.
        5. Combine: ``g = gd * gf``.

    .. seealso:: :func:`find_eap`
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
    u_ref3d = np.broadcast_to(u_ref, (nx, ny, nz, nstab, ndir)) # type: ignore[arg-type]
    v_ref3d = np.broadcast_to(v_ref, (nx, ny, nz, nstab, ndir)) # type: ignore[arg-type]
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
    ff_ref3d = np.broadcast_to(np.sqrt(u_ref ** 2 + v_ref ** 2), # type: ignore
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
    Find the substitute anemometer position (EAP) from quality measure.

    Identifies the optimal grid point for the substitute anemometer
    position based on the quality measure ``g`` at a single vertical level.

    :param g_lower: 2D array of quality measure values for each 
        (x, y) grid point.
    :type g_lower: numpy.ndarray
    :returns: A tuple containing:
    
        - **eap** (*list of tuple*) -- List of EAP candidate coordinates 
          ``(i, j)`` in the grid, sorted by decreasing quality 
          (best candidate first).
        - **g_upper** (*list of float*) -- List of corresponding summed 
          quality measures ``G`` for each contiguous region, sorted in 
          decreasing order.
    :rtype: tuple(list, list)

    .. note::
        The algorithm follows VDI 3783 Part 16, Section 6.1:
        
        1. Within each contiguous region of valid points, sum the quality
           measures to get ``G``.
        2. In the region with the largest ``G``, find the point with the
           largest individual ``g``.
        3. This point is defined as the EAP.

    :example:

        >>> g_lower = np.array([[0.5, 0.8, 0.3],
        ...                     [0.2, 0.7, 0.9],
        ...                     [0.4, 0.6, 0.1]]).astype(float)
        >>> eap, g_upper = find_eap(g_lower)
        >>> print(eap[0])  # Best EAP location
        (1, 2)

    .. seealso:: :func:`calc_quality_measure`, :func:`calc_all_eap`
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
    Find the substitute anemometer position (EAP) for all vertical levels.

    :param g: 3D array of quality measure values, shape ``(nx, ny, nz)``.
    :type g: numpy.ndarray
    :param mx_lvl: Maximum level index to process. If ``None``, all levels 
        are processed. Default is ``None``.
    :type mx_lvl: int or None, optional
    :returns: A tuple containing:
    
        - **eap_levels** (*list of list*) -- List containing, for each 
          level, a list of EAP candidate coordinates ``(i, j)``.
        - **g_upper_levels** (*list of list*) -- List containing, for 
          each level, a list of summed quality measures ``G`` for each 
          contiguous region.
    :rtype: tuple(list, list)

    .. note::
        For levels beyond ``mx_lvl``, empty lists are returned.

    .. seealso:: :func:`find_eap`

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
    Interpolate wind components to specified heights.

    Uses logarithmic interpolation for wind speed and linear interpolation
    for wind direction.

    :param u_in: Eastward wind component values at input heights.
    :type u_in: list of float
    :param v_in: Northward wind component values at input heights.
    :type v_in: list of float
    :param z_in: Heights (m) corresponding to input wind values.
    :type z_in: list of float
    :param levels: Target heights (m) to interpolate to.
    :type levels: list of float
    :returns: A tuple containing:
    
        - **u_out** (*list of float*) -- Interpolated eastward wind components.
        - **v_out** (*list of float*) -- Interpolated northward wind components.
    :rtype: tuple(list, list)
    :raises ValueError: If ``u_in``, ``v_in``, and ``z_in`` do not have 
        the same length.

    :example:

        >>> u_in = [1.0, 2.0, 3.0]
        >>> v_in = [0.5, 1.0, 1.5]
        >>> z_in = [10.0, 50.0, 100.0]
        >>> levels = [25.0, 75.0]
        >>> u_out, v_out = interpolate_wind(u_in, v_in, z_in, levels)
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
    Create a reference wind library using AUSTAL/TALdia.

    Invokes AUSTAL with the ``-l`` parameter to generate a wind library
    for flat terrain with the anemometer at the model origin.

    :param workdir: Path to the working directory containing ``austal.txt``.
    :type workdir: str or path-like
    :param tmproot: Directory for temporary files. If ``None``, uses 
        ``workdir``. Default is ``None``.
    :type tmproot: str or path-like or None, optional
    :returns: A tuple containing:
    
        - **u_tmp** (*numpy.ndarray*) -- Eastward wind component grid.
        - **v_tmp** (*numpy.ndarray*) -- Northward wind component grid.
        - **ax_tmp** (*dict*) -- Dictionary containing grid axes and metadata.
    :rtype: tuple(numpy.ndarray, numpy.ndarray, dict)
    :raises ValueError: If ``austal.txt`` is not found or AUSTAL fails.
    :raises OSError: If the AUSTAL executable is not found.

    .. note::
        This function creates a temporary directory, modifies the AUSTAL
        configuration for flat terrain, runs AUSTAL, extracts the results,
        and cleans up the temporary files.
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
                    v = AUSTAL_ROUGHNESS
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
    Generate reference wind profiles using AUSTAL/TALdia.

    Creates reference profiles by running AUSTAL on flat terrain and
    extracting the wind profile at the model origin.

    :param workdir: Path to the working directory containing ``austal.txt``.
    :type workdir: str or path-like
    :param levels: Heights (m) to interpolate the wind profile to.
    :type levels: list of float
    :param dirs: Wind directions (degrees) for which to generate profiles.
    :type dirs: list of float
    :param tmproot: Directory for temporary files. Default is ``None``.
    :type tmproot: str or path-like or None, optional
    :param overwrite: Whether to overwrite existing reference file. 
        Default is ``False``.
    :type overwrite: bool, optional
    :returns: A tuple containing:
    
        - **u_ref** (*numpy.ndarray*) -- Eastward reference wind components,
          shape ``(len(levels), N_CLASS, len(dirs))``.
        - **v_ref** (*numpy.ndarray*) -- Northward reference wind components,
          shape ``(len(levels), N_CLASS, len(dirs))``.
    :rtype: tuple(numpy.ndarray, numpy.ndarray)

    .. seealso:: :func:`run_austal`, :func:`calc_ref_geostrophic`, 
        :func:`calc_ref_adapted`
    """
    logger.debug("calculating reference wind fields")
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

def calc_ref_geostrophic(levels: list[float], dirs: list[float],
                         z0: float | None = None,
                         overwrite: bool = False
                         ) -> tuple[np.ndarray, np.ndarray]:
    """
    Calculate reference wind profiles using geostrophic wind values.

    Uses the two-layer wind profile model from VDI 3783 Part 8 with
    geostrophic wind speeds from VDI 3783 Part 16 Table 1 prescribed
    at the inversion height for each stability class.

    :param levels: Heights above ground (m) for the output profile.
    :type levels: list of float
    :param dirs: Wind directions (degrees, meteorological convention) for
        which to generate profiles.
    :type dirs: list of float
    :param z0: Roughness length (m). Default is :data:`VDI_DEFAULT_ROUGHNESS`.
    :type z0: float or None, optional
    :param overwrite: Whether to overwrite existing reference file. 
        Default is ``False``.
    :type overwrite: bool, optional
    :returns: A tuple containing:
    
        - **u_ref** (*numpy.ndarray*) -- Eastward reference wind components,
          shape ``(len(levels), N_CLASS, len(dirs))``.
        - **v_ref** (*numpy.ndarray*) -- Northward reference wind components,
          shape ``(len(levels), N_CLASS, len(dirs))``.
    :rtype: tuple(numpy.ndarray, numpy.ndarray)

    .. note::
        This is the "general" approach that uses standardized geostrophic
        wind values independent of the actual meteorological data.
        
        The friction velocity :math:`u_*` is calculated iteratively to match
        the prescribed geostrophic wind at the top of the boundary layer.

    .. seealso:: :func:`calc_ref_adapted`, :func:`calc_vdi3783_8`
    """
    logger.info("calculating general wind reference profile")

    if z0 is None:
        z0 = VDI_DEFAULT_ROUGHNESS

    return calc_vdi3783_8(levels, dirs, z0=z0,
                          u_a_classes=None,
                          h_a_classes=None,
                          overwrite=overwrite)


def calc_ref_adapted(levels: list[float], dirs: list[float],
                     working_dir: str | None = None,
                     z0: float | None = None,
                     overwrite: bool = False
                     ) -> tuple[np.ndarray, np.ndarray]:
    """
    Calculate reference wind profiles adapted to the meteorological data.

    Uses the two-layer wind profile model from VDI 3783 Part 8 with
    frequency-weighted mean wind speeds from the meteorological time
    series prescribed at the effective anemometer height for each
    stability class.

    This approach matches what AUSTAL/TALdia uses internally when
    generating wind libraries from dispersion class statistics (AKS).

    :param levels: Heights above ground (m) for the output profile.
    :type levels: list of float
    :param dirs: Wind directions (degrees, meteorological convention) for
        which to generate profiles.
    :type dirs: list of float
    :param working_dir: Working directory containing ``austal.txt`` and 
        the time series file. Default is current directory.
    :type working_dir: str or path-like or None, optional
    :param z0: Roughness length (m). Default is :data:`VDI_DEFAULT_ROUGHNESS`.
    :type z0: float or None, optional
    :param overwrite: Whether to overwrite existing reference file. 
        Default is ``False``.
    :type overwrite: bool, optional
    :returns: A tuple containing:
    
        - **u_ref** (*numpy.ndarray*) -- Eastward reference wind components,
          shape ``(len(levels), N_CLASS, len(dirs))``.
        - **v_ref** (*numpy.ndarray*) -- Northward reference wind components,
          shape ``(len(levels), N_CLASS, len(dirs))``.
    :rtype: tuple(numpy.ndarray, numpy.ndarray)
    :raises FileNotFoundError: If the time series file specified in 
        ``austal.txt`` is not found.
    :raises ValueError: If no time series file is defined in ``austal.txt`` 
        or all wind data are invalid.

    .. note::
        This is the "adapted" approach that uses:
        
        - The effective anemometer height :math:`h_a` from the time series
          file header (dependent on roughness length class).
        - The frequency-weighted mean wind speed for each stability class
          from the time series data.
        
        For stability classes with no data, the wind speed is estimated by
        scaling the VDI geostrophic wind values proportionally.

    .. seealso:: :func:`calc_ref_geostrophic`, :func:`calc_vdi3783_8`
    """
    logger.info("calculating adapted wind reference profile")

    if z0 is None:
        z0 = VDI_DEFAULT_ROUGHNESS
    if working_dir is None:
        working_dir = os.getcwd()

    austxt = _tools.get_austxt()
    azfile = austxt['az']
    if isinstance(azfile, list):
        azfile = azfile[0]
    if 'az' in austxt:
        try:
            az = readmet.akterm.DataFile(os.path.join(working_dir, azfile))
        except FileNotFoundError:
            raise FileNotFoundError(f"In austal.txt the timeseries "
                                    f"file (az) is defined but the "
                                    f"file does not exists: "
                                    f"{austxt['az']}")
    else:
        raise ValueError('adapted wind reference profile can only be'
                         'calculated if a timeseries file (az) is defined'
                         'in austal.txt')

    ha = az.get_h_anemo(z0)
    h_a_classes = [ha] * N_CLASS

    u_a_classes = [np.nan] * N_CLASS
    for i in range(N_CLASS):
        u_a_classes[i] = np.nanmean(az.data['FF'][az.data['KM'] == i + 1])

    logger.debug(f"class anemomtr heights: {h_a_classes}")
    logger.debug(f"class mean wind speeds: {u_a_classes}")

    # Ensure all classes have values:
    nan_classes = [np.isnan(x) for x in u_a_classes]
    if all(nan_classes):
        raise ValueError("all wind data are invalid, cannot calculate"
                         "adapted wind reference profile")
    elif any(nan_classes):
        factor = float(np.nanmean((u_a_classes /
                                   np.array(VDI_GEOSTROPIC_WIND))))
        for i in range(N_CLASS):
            if np.isnan(u_a_classes[i]):
                u_a_classes[i] = factor * VDI_GEOSTROPIC_WIND[i]

    logger.info(f"effective anemo height: {ha}")
    pp = {_dispersion.KM2021.name(i + 1): u_a_classes[i]
          for i in range(N_CLASS)}
    logger.info(f"class mean wind speeds: {pp}")

    return calc_vdi3783_8(levels, dirs, z0=z0,
                          u_a_classes=u_a_classes,
                          h_a_classes=h_a_classes,
                          overwrite=overwrite)


# -------------------------------------------------------------------------
# -------------------------------------------------------------------------

def calc_vdi3783_8(levels: list, dirs: list, z0: float = None,
                   u_a_classes: list[float] | None = None,
                   h_a_classes: list[float] | None = None,
                   overwrite: bool = False):
    """
    Calculate wind profiles using the VDI 3783 Part 8 two-layer model.

    Implements the two-layer boundary layer wind profile model consisting
    of a Monin-Obukhov surface layer with linear direction turning and
    an Ekman spiral solution in the upper layer.

    :param levels: Heights above ground (m) for the output profile, 
        must be positive and increasing.
    :type levels: array-like
    :param dirs: Wind directions at reference height (degrees, meteorological
        convention, 0° = North, 90° = East).
    :type dirs: array-like
    :param z0: Roughness length (m). Default is :data:`VDI_DEFAULT_ROUGHNESS`.
    :type z0: float or None, optional
    :param u_a_classes: Reference wind speed (m/s) for each stability class. 
        If ``None``, uses :data:`VDI_GEOSTROPIC_WIND` (geostrophic wind at 
        inversion height). Default is ``None``.
    :type u_a_classes: list of float or None, optional
    :param h_a_classes: Reference height (m) for each stability class where 
        ``u_a_classes`` is prescribed. If ``None``, uses 
        :data:`VDI_INVERSION_HEIGHT` (inversion height). Default is ``None``.
    :type h_a_classes: list of float or None, optional
    :param overwrite: Whether to overwrite existing output file. 
        Default is ``False``.
    :type overwrite: bool, optional
    :returns: A tuple containing:
    
        - **u_ref** (*numpy.ndarray*) -- Eastward wind components, 
          shape ``(len(levels), N_CLASS, len(dirs))``.
        - **v_ref** (*numpy.ndarray*) -- Northward wind components, 
          shape ``(len(levels), N_CLASS, len(dirs))``.
    :rtype: tuple(numpy.ndarray, numpy.ndarray)

    .. note::
        The two-layer model from VDI 3783 Part 8 :cite:`VDI3783p8` consists of:
        
        **Lower layer** (:math:`z \\leq h_1`):
            Surface layer following Monin-Obukhov similarity with wind speed:
            
            .. math::
            
                u_1(z) = \\frac{u_*}{\\kappa} \\left[ \\ln\\frac{z}{z_0} -
                         \\psi_m\\left(\\frac{z}{L}\\right) \\right]
            
            and linear direction turning with gradient :math:`a = -0.2 A`.
        
        **Upper layer** (:math:`z > h_1`):
            Ekman spiral solution with exponentially decaying oscillations:
            
            .. math::
            
                \\tilde{u}(z) = u_1(h_1) c_1 + \\frac{1}{2A}[(1-c_z)p + s_z q]
            
                \\tilde{v}(z) = u_1(h_1) s_1 + \\frac{1}{2A}[(c_z-1)q + s_z p]
            
            where :math:`A = \\sqrt{|f_c|/(2K)}` is the Ekman parameter.
        
        The layer interface height :math:`h_1` is calculated from Eq. (A19):
        
        - Stable: :math:`h_1 = \\frac{L}{20}\\left(\\sqrt{1 + \\frac{10 h_m}{3\\alpha L}} - 1\\right)`
        - Unstable/neutral: :math:`h_1 = \\frac{h_m}{12\\alpha}`

    .. seealso:: :func:`_calc_h1`, :func:`_calc_Km`, :func:`_calc_ekman_layer`,
        :func:`_calc_u_star_from_vg`
    """
    # Set defaults
    if z0 is None:
        z0 = VDI_DEFAULT_ROUGHNESS
    if u_a_classes is None:
        u_a_classes = VDI_GEOSTROPIC_WIND
    if h_a_classes is None:
        h_a_classes = VDI_INVERSION_HEIGHT

    levels = np.asarray(levels, dtype=float)
    dirs = np.asarray(dirs, dtype=float)

    nz = len(levels)
    ndir = len(dirs)

    u_ref = np.zeros((nz, N_CLASS, ndir))
    v_ref = np.zeros((nz, N_CLASS, ndir))

    # Get Obukhov lengths for all stability classes (depends on z0)
    l_obukhov = [_dispersion.KM2021.get_center(x, z0=z0) for x in
                 range(N_CLASS)]

    for istab in range(N_CLASS):
        L = l_obukhov[istab]
        u_a = u_a_classes[istab]
        h_a = h_a_classes[istab]
        h_m = VDI_INVERSION_HEIGHT[istab]

        # Calculate layer interface height h1
        h1 = _calc_h1(L, h_m)

        if h_a > h1:
            # Reference height is in upper layer:
            # Calculate friction velocity iteratively to match u_a at h_a
            u_star, A, a = _calc_u_star_from_vg(h1, u_a, h_a, z0, L, h_m)

            # Create diabatic wind profile object with calculated u_star
            wind_profile = meteolib.wind.DiabaticWind(
                ust=u_star,
                z0=z0,
                LOb=L
            )
        else:
            # Reference height is in lower (surface) layer:
            # Calculate u_star directly from u_a at h_a
            wind_profile = meteolib.wind.DiabaticWind(
                u=u_a,
                z=h_a,
                z0=z0,
                LOb=L
            )
            u_star = wind_profile.ust
            K = _calc_Km(h1, u_star, L, h_m)
            A = np.sqrt(np.abs(F_C) / (2 * K))
            a = -0.2 * A

        for idir in range(ndir):
            dd_ref = dirs[idir]
            h_ref = 0.  # AUSTAL uses surface wind direction as reference

            for iz in range(nz):
                z = levels[iz]

                if z <= h1:
                    # Lower layer: surface layer with linear direction turning
                    ff_z = wind_profile.u(z)
                    dd_z = dd_ref - np.rad2deg(
                        a * (z - h_ref))  # met convention
                    dd_z = dd_z % 360

                    u, v = meteolib.wind.dir2uv(ff_z, dd_z)
                else:
                    # Upper layer: Ekman solution
                    u, v = _calc_ekman_layer(
                        z, h1, wind_profile, L, dd_ref, a, h_ref, A
                    )

                u_ref[iz, istab, idir] = u
                v_ref[iz, istab, idir] = v

    write_ref("Ref1d.dat", levels, dirs, u_ref, v_ref,
              (levels, [x for x in range(N_CLASS)], dirs),
              overwrite=overwrite)

    return u_ref, v_ref


def _calc_u_star_from_vg(h1, u_a, h_a, z0, L, h_m, alpha=None):
    """
    Calculate friction velocity from wind speed at reference height.

    Iteratively determines the friction velocity :math:`u_*` such that
    the two-layer wind profile produces the prescribed wind speed
    :math:`u_a` at reference height :math:`h_a`.

    :param h1: Layer interface height (m).
    :type h1: float
    :param u_a: Reference wind speed (m/s) at height ``h_a``.
    :type u_a: float
    :param h_a: Reference height (m) where ``u_a`` is prescribed.
    :type h_a: float
    :param z0: Roughness length (m).
    :type z0: float
    :param L: Obukhov length (m).
    :type L: float
    :param h_m: Mixing layer height (m).
    :type h_m: float
    :param alpha: Parameter for h1 calculation. Default is 1.0.
    :type alpha: float or None, optional
    :returns: A tuple containing:
    
        - **u_star** (*float*) -- Friction velocity (m/s).
        - **A** (*float*) -- Ekman parameter (1/m).
        - **a** (*float*) -- Direction gradient in surface layer (rad/m).
    :rtype: tuple(float, float, float)

    .. note::
        The iteration adjusts :math:`u_*` until the calculated wind speed
        at :math:`h_a` matches the prescribed value within tolerance
        (1e-6 m/s) or maximum 20 iterations.
    """
    if alpha is None:
        alpha = 1.0

    zeta_h1 = h1 / L if np.abs(L) < 1e9 else 0.0
    psi_m_h1 = meteolib.wind.psi_m(zeta_h1)
    phi_m_h1 = meteolib.wind.phi_m(zeta_h1)

    # Initial guess using neutral log profile
    u_star = KAPPA * u_a / np.log(h_a / z0)
    A = None
    a = None
    # Assume wind at h_a aligned with u-axis (only interested in magnitude)
    alpha_a = 0

    for _ in range(20):
        # Calculate K, A, a from current u_star
        K = _calc_Km(h1, u_star, L, h_m)
        A = np.sqrt(np.abs(F_C) / (2 * K))
        a = -0.2 * A

        # Wind speed at h1 from surface layer formula (A3)
        u1_h1 = (u_star / KAPPA) * (np.log(h1 / z0) - psi_m_h1)
        du1_dz_h1 = u_star * phi_m_h1 / (KAPPA * h1)

        # Direction at h1 (A10, A11)
        c1 = np.cos(alpha_a + a * (h1 - h_a))
        s1 = np.sin(alpha_a + a * (h1 - h_a))

        # Auxiliary quantities (A14, A15)
        w_plus = c1 + s1
        w_minus = c1 - s1

        # Matching coefficients (A12, A13)
        p = du1_dz_h1 * w_plus + a * u1_h1 * w_minus
        q = du1_dz_h1 * w_minus - a * u1_h1 * w_plus

        # Ekman spiral functions at h_a (A16, A17)
        c_z = np.exp(-A * (h_a - h1)) * np.cos(A * (h_a - h1))
        s_z = np.exp(-A * (h_a - h1)) * np.sin(A * (h_a - h1))

        # Wind components at h_a from Ekman solution (A8, A9)
        u_tilde = u1_h1 * c1 + 1 / (2 * A) * ((1 - c_z) * p + s_z * q)
        v_tilde = u1_h1 * s1 + 1 / (2 * A) * ((c_z - 1) * q + s_z * p)

        v_a_calc = np.sqrt(u_tilde ** 2 + v_tilde ** 2)

        # Update u_star proportionally
        u_star_new = u_star * (u_a / v_a_calc)

        if np.abs(u_star_new - u_star) < 1e-6:
            break
        u_star = u_star_new

    return u_star, A, a


def _calc_h1(L, h_m, alpha=None):
    """
    Calculate layer interface height between surface and Ekman layers.

    Implements Equation (A19) from VDI 3783 Part 8.

    :param L: Obukhov length (m). Positive for stable, negative for unstable.
    :type L: float
    :param h_m: Mixing layer height (m).
    :type h_m: float
    :param alpha: Empirical parameter. Default is 1.0.
    :type alpha: float or None, optional
    :returns: Layer interface height (m).
    :rtype: float

    .. note::
        For stable stratification (L > 0):
        
        .. math::
        
            h_1 = \\frac{L}{20} \\left( \\sqrt{1 + \\frac{10 h_m}{3 \\alpha L}} - 1 \\right)
        
        For unstable or neutral stratification (L ≤ 0 or L → ∞):
        
        .. math::
        
            h_1 = \\frac{h_m}{12 \\alpha}
    """
    if alpha is None:
        alpha = 1.0

    if L >= 0:
        if L > 1e9:  # neutral limit
            return h_m / (12 * alpha)
        else:
            return L / 20 * (np.sqrt(1 + 10 * h_m / (3 * alpha * L)) - 1)
    else:
        return h_m / (12 * alpha)


def _calc_Km(z, u_star, L, h_m):
    """
    Calculate eddy diffusivity for momentum at height z.

    Implements Equation (36) / (A20) from VDI 3783 Part 8.

    :param z: Height above ground (m).
    :type z: float
    :param u_star: Friction velocity (m/s).
    :type u_star: float
    :param L: Obukhov length (m).
    :type L: float
    :param h_m: Mixing layer height (m).
    :type h_m: float
    :returns: Eddy diffusivity (m²/s), minimum value 0.1 m²/s.
    :rtype: float

    .. note::
        The eddy diffusivity is calculated as:
        
        .. math::
        
            K_m = \\frac{\\kappa u_* z}{\\phi_m(z/L)} \\left(1 - \\frac{z}{h_m}\\right)
        
        where :math:`\\phi_m` is the dimensionless wind shear from
        Monin-Obukhov similarity theory.
    """
    zeta = z / L if np.abs(L) < 1e9 else 0.0
    phi_m = meteolib.wind.phi_m(zeta)

    z_eff = min(z, h_m)
    Km = KAPPA * u_star * z_eff / phi_m * (1 - z_eff / h_m)
    Km = max(Km, 0.1)

    return Km


def _calc_ekman_layer(z, h1, wind_profile, L, dd_ref, a, h_ref, A):
    """
    Calculate wind components in the upper (Ekman) layer.

    Implements Equations (A8)-(A17) from VDI 3783 Part 8.

    :param z: Height above ground (m), must be > h1.
    :type z: float
    :param h1: Layer interface height (m).
    :type h1: float
    :param wind_profile: Surface layer wind profile object.
    :type wind_profile: meteolib.wind.DiabaticWind
    :param L: Obukhov length (m).
    :type L: float
    :param dd_ref: Reference wind direction (degrees, meteorological convention).
    :type dd_ref: float
    :param a: Direction gradient in surface layer (rad/m).
    :type a: float
    :param h_ref: Reference height for direction (m).
    :type h_ref: float
    :param A: Ekman parameter (1/m).
    :type A: float
    :returns: A tuple containing:
    
        - **u** (*float*) -- Eastward wind component (m/s).
        - **v** (*float*) -- Northward wind component (m/s).
    :rtype: tuple(float, float)

    .. note::
        The Ekman layer solution matches the surface layer at h1 in both
        wind speed and direction, with boundary conditions that the solution
        remains bounded as z → ∞.
        
        The wind components are:
        
        .. math::
        
            \\tilde{u}(z) = u_1(h_1) c_1 + \\frac{1}{2A}[(1-c_z)p + s_z q]
        
            \\tilde{v}(z) = u_1(h_1) s_1 + \\frac{1}{2A}[(c_z-1)q + s_z p]
        
        where :math:`c_z = e^{-A(z-h_1)} \\cos[A(z-h_1)]` and
        :math:`s_z = e^{-A(z-h_1)} \\sin[A(z-h_1)]`.
    """
    # Values at h1
    u1_h1 = wind_profile.u(h1)
    u_star = wind_profile.ust

    # Derivative du1/dz at h1 using phi_m (A7)
    zeta_h1 = h1 / L if np.abs(L) < 1e9 else 0.0
    phi_m_h1 = meteolib.wind.phi_m(zeta_h1)
    du1_dz_h1 = u_star * phi_m_h1 / (KAPPA * h1)

    # Direction at h1 (meteorological convention)
    dd_h1 = dd_ref - np.rad2deg(a * (h1 - h_ref))
    alpha_h1 = np.deg2rad(270 - dd_h1)  # convert to math angle

    c1 = np.cos(alpha_h1)
    s1 = np.sin(alpha_h1)

    # Auxiliary quantities (A14, A15)
    w_plus = c1 + s1
    w_minus = c1 - s1

    # Matching coefficients (A12, A13)
    p = du1_dz_h1 * w_plus + a * u1_h1 * w_minus
    q = du1_dz_h1 * w_minus - a * u1_h1 * w_plus

    # Ekman spiral functions (A16, A17)
    exp_decay = np.exp(-A * (z - h1))
    A_dz = A * (z - h1)
    c_z = exp_decay * np.cos(A_dz)
    s_z = exp_decay * np.sin(A_dz)

    # Wind components (A8, A9)
    u = u1_h1 * c1 + 1 / (2 * A) * ((1 - c_z) * p + s_z * q)
    v = u1_h1 * s1 + 1 / (2 * A) * ((c_z - 1) * q + s_z * p)

    return u, v


# -------------------------------------------------------------------------
# -------------------------------------------------------------------------

def read_ref(file: str, levels: list[float], dirs: list[float],
             linear_interpolation: bool = False):
    """
    Read reference wind profiles from file.

    Reads wind profiles in the format of ``Ref1d.dat`` from the VDI 3783
    Part 16 reference implementation and interpolates to the requested
    heights and directions.

    :param file: Path to the reference profile file.
    :type file: str
    :param levels: Target heights (m) to interpolate to.
    :type levels: list of float
    :param dirs: Target wind directions (degrees) to extract.
    :type dirs: list of float
    :param linear_interpolation: If ``True``, use linear interpolation for 
        wind speed (for comparison with VDI reference implementation). 
        If ``False``, use logarithmic interpolation. Default is ``False``.
    :type linear_interpolation: bool, optional
    :returns: A tuple containing:
    
        - **u_ref** (*numpy.ndarray*) -- Eastward reference wind components,
          shape ``(len(levels), N_CLASS, len(dirs))``.
        - **v_ref** (*numpy.ndarray*) -- Northward reference wind components,
          shape ``(len(levels), N_CLASS, len(dirs))``.
    :rtype: tuple(numpy.ndarray, numpy.ndarray)
    :raises ValueError: If no matching profile is found for a stability class.

    .. seealso:: :func:`write_ref`
    """
    logger.debug("reading wind reference file")
    ndir = len(dirs)
    nlev = len(levels)

    # Column IDs have the form wS0DD (S=stability class, DD=direction/10)
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
              overwrite: bool | None = None):
    """
    Write reference wind profiles to file.

    Writes wind profiles in the format of ``Ref1d.dat`` from the VDI 3783
    Part 16 reference implementation (``TAL-Anemo.zip``).

    :param file: Output file path.
    :type file: str
    :param out_levels: Heights (m) to include in output.
    :type out_levels: array-like
    :param out_dirs: Wind directions (degrees) to include in output.
    :type out_dirs: array-like
    :param u_ref: Eastward wind components, shape ``(nz, N_CLASS, ndir)``.
    :type u_ref: numpy.ndarray
    :param v_ref: Northward wind components, shape ``(nz, N_CLASS, ndir)``.
    :type v_ref: numpy.ndarray
    :param axes_ref: Tuple of ``(levels, stability_classes, directions)`` 
        arrays corresponding to the dimensions of ``u_ref`` and ``v_ref``.
    :type axes_ref: tuple
    :param overwrite: If ``True``, overwrite existing file. If ``False``, 
        raise ``FileExistsError``. If ``None``, prompt user interactively.
        Default is ``None``.
    :type overwrite: bool or None, optional
    :raises FileExistsError: If file exists and ``overwrite`` is ``False``.

    .. seealso:: :func:`read_ref`
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

            raise FileExistsError('file %s already exists' % file)

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
                 g_upper: list[list[float]], axes: dict[str, list]):
    """
    Print a detailed report of EAP analysis results.

    Outputs a formatted report mimicking the style of the VDI 3783 Part 16
    reference implementation (``TAL-Anemo.zip``).

    :param args: Command line arguments dictionary.
    :type args: dict
    :param g: Overall quality measure, shape ``(nx, ny, nz)``.
    :type g: numpy.ndarray
    :param gd: Direction quality measure, shape ``(nx, ny, nz)``.
    :type gd: numpy.ndarray
    :param gf: Speed quality measure, shape ``(nx, ny, nz)``.
    :type gf: numpy.ndarray
    :param eaps: EAP coordinates for each level, as returned by 
        :func:`calc_all_eap`.
    :type eaps: list of list of tuple
    :param g_upper: Summed quality measures for each level.
    :type g_upper: list of list of float
    :param axes: Dictionary with keys 'x', 'y', 'z' containing grid coordinates.
    :type axes: dict

    .. seealso:: :func:`calc_all_eap`, :func:`calc_quality_measure`
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
    Main entry point for the EAP analysis.

    Reads a wind library, calculates reference profiles, computes quality
    measures, finds optimal EAP locations, and optionally creates plots
    and updates the AUSTAL configuration.

    :param args: Command line arguments dictionary with keys:
    
        - ``working_dir``: Path to working directory.
        - ``grid``: Grid ID to evaluate.
        - ``reference``: Reference profile method ('general', 'simple',
          'file', or 'austal').
        - ``overwrite``: Whether to overwrite existing files.
        - ``max_height``: Maximum evaluation height.
        - ``edge_nodes``: Number of edge nodes to exclude.
        - ``min_ff``: Minimum wind speed threshold.
        - ``height``: Target height for EAP selection.
        - ``report``: Whether to print detailed report.
        - ``austal``: Whether to update austal.txt.
        - ``plot``: Plot output specification.
    :type args: dict

    .. seealso:: :func:`add_options`
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
    if args['reference'] == 'general':
        u_ref, v_ref = calc_ref_geostrophic(axes['z'], directions,
                                            overwrite=overwrite)
    elif args['reference'] == 'simple':
        u_ref, v_ref = calc_ref_adapted(axes['z'], directions,
                                        overwrite=overwrite)
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
    for lvl in range(mx_lvl + 1):
        dz = abs(axes['z'][lvl] - wind_height)
        if len(eaps[lvl]) > 0 and dz < dz_old:
            selected_level = lvl
            dz_old = dz
    logger.info(f'selected_level: {selected_level}')

    #
    # write to austal config
    #
    if args['austal']:
        _tools.put_austxt(
            path=args['working_dir'] / "austal.txt",
            data={
                'xa': [axes['x'][eaps[selected_level][0][0]]],
                'ya': [axes['y'][eaps[selected_level][0][1]]]
            }
        )

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
                          default=None,
                          help='force overwriting wind reference file '
                               'if it exists.')
    pars_eap.add_argument('-q', '--report',
                          action='store_true',
                          help='show detailed results')
    pars_eap.add_argument('-r', '--reference',
                          default='simple',
                          choices=['general', 'simple', 'file', 'austal'],
                          help='choose kind of reference profile. '
                               '`simple` produces a log wind profile, '
                               '`file` reads reference profile from file. '
                               'Defaults to `vdi`')
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
