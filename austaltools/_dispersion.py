#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This module provides funtions to determine the stability classes
as used by atmospheric dispersion model by varius methods.
"""
import logging
import os

import numpy as np
import pandas as pd

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import meteolib as m

logger = logging.getLogger(__name__)

# ----------------------------------------------------

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    kappa = m.constants.kappa
    gn = m.constants.gn
    _check = m._utils._check
    _isscalar = pd.api.types.is_scalar


# =========================================================================


class StabiltyClass:
    """
    Class that holds information about a set of stabilty classes.

    :param bounds: for each stability class, a 2-element list or tuple
        must be given. The first list must contain the z0 vlaues for
        the roughness lenght classes in ascending order, the second
        list must be of the same length and contain the boundary
        values of the Obukhov lenght separating the 1st and 2nd class,
        the 2nd and the 3rd, ... .
        Mutually exclusive with `centers`.
    :type bounds: list[tuple[list]]
    :param centers: for each stability class, a 2-element list or tuple
        must be given. The first list must contain the z0 vlaues for
        the roughness lenght classes in ascending order, the second
        list must be of the same length and contain the center
        values of the Obukhov lenght for 1st, 2nd, 3rd, ... class
        Mutually exclusive with `bounds`.
    :type centers: list[tuple[list]]
    :param inverted: False if the bounds or center values should
        be taken as they are. True if values shoud be inverted
        i.e. :math:`1/x`. Defaults to False.
    :type inverted: bool
    :param reverse_index: False if the numric class index is acsending.
        True if it is decending. Defaults to False.
    :type reverse_index:
    :param names: Names of the stability classes. Must be same lenght
        as `centers` or one more element as `bounds`
    :type names: list[str]
    """
    _bounds = None
    _centers = None
    _index = None
    count = 0
    names = None
    reverse_index = False

    def __init__(self, bounds=None, centers=None, inverted=False,
                 reverse_index=True, names=None):
        if bounds is not None and centers is not None:
            raise ValueError('bounds and centers are mutualy exclusive')
        elif bounds is not None:
            if type(bounds) not in [list, tuple]:
                raise ValueError('bounds must be list or tuple')
            if any([type(x) not in [list, tuple] or len(x) != 2
                    for x in bounds]):
                raise ValueError('bounds must contain ' +
                                 '2-element lists or tuples')
            if any([type(y) not in [list, tuple] for x in bounds
                    for y in x]):
                raise ValueError('bounds elements contain ' +
                                 'lists or tuples')
            if any([len(x[0]) != len(x[1]) for x in bounds]):
                raise ValueError('lists in bounds elements must ' +
                                 'be of same length')
            if any([sorted(x[0]) != x[0] for x in bounds]):
                raise ValueError('lists in bounds elements must ' +
                                 'be sorted by ascending z0')
            if inverted:
                self._bounds = bounds
            else:
                self._bounds = []
                for b in bounds:
                    self._bounds.append([b[0], [1 / x for x in b[1]]])
            self.count = len(bounds) + 1
            self._bounds = self._sort(self._bounds)
            self._bounds2centers()
        elif centers is not None:
            if type(centers) not in [list, tuple]:
                raise ValueError('centers must be list or tuple')
            if any([type(x) not in [list, tuple] or len(x) != 2
                    for x in centers]):
                raise ValueError('centers must contain ' +
                                 '2-element lists or tuples')
            if any([type(y) not in [list, tuple] for x in centers
                    for y in x]):
                raise ValueError('centers elements contain ' +
                                 'lists or tuples')
            if any([len(x[0]) != len(x[1]) for x in centers]):
                raise ValueError('lists in centers elements must ' +
                                 'be of same length')
            if any([sorted(x[0]) != x[0] for x in centers]):
                raise ValueError('lists in centers elements must ' +
                                 'be sorted by ascending z0')
            if inverted:
                self._centers = centers
            else:
                self._centers = []
                for b in centers:
                    self._centers.append([b[0], [1 / x for x in b[1]]])
            self.count = len(centers)
            self._centers = self._sort(self._centers)
            self._centers2bounds()
        if names is not None:
            if not type(names) in [list, tuple]:
                raise ValueError('names must be list or tuple')
            if any([not isinstance(x, str) for x in names]):
                raise ValueError('names must be strings')
            if len(names) != self.count:
                raise ValueError('number of names must equal ' +
                                 'number of classes')
            self.names = names
        if reverse_index:
            self.reverse_index = True
        else:
            self.reverse_index = False

    def _sort(self, lines):
        # get median z0
        all_z0 = sorted(set([y for x in lines for y in x[0]]))
        mz0 = all_z0[int(len(all_z0) / 2)]
        ils = [self._getval(mz0, x) for x in lines]
        re = [x for _, x in sorted(zip(ils, lines))]
        return re

    def _getval(self, z0, line):
        # interpolate z0 along a line
        lz0, lil = line
        if z0 in lz0:
            il = lil[lz0.index(z0)]
        elif z0 < lz0[0]:
            slope = (lil[1] - lil[0]) / (np.log(lz0[1]) - np.log(lz0[0]))
            il = lil[0] + (np.log(z0) - np.log(lz0[0])) * slope
        elif z0 > lz0[-1]:
            slope = (lil[-1] - lil[-2]) / (np.log(lz0[-1]) - np.log(lz0[-2]))
            il = lil[0] + (np.log(z0) - np.log(lz0[-1])) * slope
        else:
            il = np.interp(np.log(z0), np.log(lz0), lil)
        return il

    def _bounds2centers(self):
        # calculate center values if bounds values are defined
        bz0, bil = self._bounds[0]
        lbounds = [[bz0, [1. / 9999. for x in bil]], ] + self._bounds[:-1]
        bz0, bil = self._bounds[-1]
        rbounds = self._bounds[1:] + [[bz0, [1. / 9999. for x in bil]], ]

        self._centers = []
        for lb, rb in zip(lbounds, rbounds):
            lz0, lil = lb
            rz0, ril = rb
            cz0 = sorted(lz0 + list(set(rz0) - set(lz0)))
            cil = [(self._getval(x, lb) + self._getval(x, rb)) / 2.
                   for x in cz0]
            self._centers.append([cz0, cil])

    def _centers2bounds(self):
        # calculate bounds values if center values are defined
        lcenters = self._centers[:-1]
        rcenters = self._centers[1:]

        self._bounds = []
        for lc, rc in zip(lcenters, rcenters):
            lz0, lil = lc
            rz0, ril = rc
            bz0 = sorted(lz0 + list(set(rz0) - set(lz0)))
            bil = [(self._getval(x, lc) + self._getval(x, rc)) / 2.
                   for x in bz0]
            self._bounds.append([bz0, bil])

    def get_bound(self, num, z0, inverted=False):
        """
        get the upper boundary value of Obukhov lentgh :math:`L` for the
        class with index `num` for roughness length `z0`.

        :param num: numeric class index
        :type num: int
        :param z0: roughness length in m
        :type z0: float
        :param inverted: True if :math:`1/L` should be returned instead
          of :math:`L`
        :type inverted: bool (optional)
        :return: Obukhov length :math:`L` in m
        :rtype: float
        """

        if num not in range(self.count - 1):
            # print(self.count)
            raise ValueError('no boundary number #%i' % int(num))
        il = self._getval(z0, self._bounds[num])
        if inverted:
            return il
        else:
            return 1 / il

    def get_center(self, num, z0, inverted=False):
        """
        get the center value of Obukhov lentgh :math:`L` for the
        class with index `num` for roughness length `z0`.

        :param num: numeric class index
        :type num: int
        :param z0: roughness length in m
        :type z0: float
        :param inverted: True if :math:`1/L` should be returned instead
          of :math:`L`
        :type inverted:  bool (optional)
        :return: Obukhov length :math:`L` in m
        :rtype: float
        """
        if num not in range(self.count):
            raise ValueError('no class number #%i' % int(num))
        il = self._getval(z0, self._centers[num])
        if inverted:
            return il
        else:
            return 1 / il

    def get_index(self, z0, lob, inverted=False):
        """
        get the numeric class index for roughness length `z0` and
        Obukhov lentgh :math:`L`.

        :param z0: roughness length in m
        :type z0: float
        :param lob: Obukhov lentgh
        :param inverted: True if `lob` is :math:`1/L` instead
          of :math:`L`
        :type inverted:  bool (optional)
        :return: Numeric class index
        :rtype: int
        """
        if inverted:
            il = lob
        else:
            il = 1. / lob
        bs = [self.get_bound(i, z0, inverted=True)
              for i in range(self.count - 1)]
        for i, x in enumerate(bs):
            if il < x:
                cl = i
                break
        else:
            cl = self.count - 1
        if self.reverse_index:
            return self.count - cl
        else:
            return cl + 1

    def get_name(self, z0, index, inverted=False):
        """
        get the class name for roughness length `z0` and
        Obukhov lentgh :math:`L`.

        :param z0: roughness length in m
        :type z0: float
        :param index: class index
        :param inverted: True if `lob` is :math:`1/L` instead
            of :math:`L`
        :type inverted:  bool (optional)
        :return: class name
        :rtype: str
        """
        return self.names[self.get_index(z0, index, inverted) - 1]

    def name(self, num):
        """
        get the class name for numeric class index

        :param num: numeric class index
        :return: class name
        :rtype: str
        """
        if not num - 1 in range(self.count):
            raise ValueError('no class number #%i' % int(num))
        return self.names[int(num) - 1]

    def index(self, name):
        """
        get the numeric class index for class name

        :param name: class name
        :type name: str
        :return: numeric class index
        :rtype: int
        """
        if name not in self.names:
            raise ValueError('no class name "%s"' % name)
        return self.names.index(name) + 1


# ----------------------------------------------------
#
KM2021 = StabiltyClass(centers=[
    ([0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 1.00, 1.50, 2.00],
     [5, 7, 9, 13, 17, 28, 44, 60, 77]),
    ([0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 1.00, 1.50, 2.00],
     [25, 31, 44, 59, 81, 133, 207, 280, 358]),
    ([0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 1.00, 1.50, 2.00],
     [350, 450, 630, 840, 1160, 1890, 2950, 4000, 5110]),
    ([0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 1.00, 1.50, 2.00],
     [-37, -47, -66, -88, -122, -199, -310, -420, -536]),
    ([0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 1.00, 1.50, 2.00],
     [-15, -19, -27, -36, -49, -80, -125, -170, -217]),
    ([0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 1.00, 1.50, 2.00],
     [-6, -8, -11, -15, -20, -33, -52, -70, -89]),
],
    inverted=False,
    reverse_index=True,
    names=['I', 'II', 'III1', 'III2', 'IV', 'V'])
"""
Klug/Manier stabilty classes. Class center values taken from 
TA Luft 2021 [TAL2021]_.


Tabelle 17: Klassierung der Obukhov-Länge L in m

:meta hide-value:
"""
# ----------------------------------------------------
#
KM2002 = StabiltyClass(centers=[
    ([0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 1.00, 1.50, 2.00],
     [7, 9, 13, 17, 24, 40, 65, 90, 118]),
    ([0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 1.00, 1.50, 2.00],
     [25, 31, 44, 60, 83, 139, 223, 310, 406]),
    ([0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 1.00, 1.50, 2.00],
     [9999, 9999, 9999, 9999, 9999, 9999, 9999, 9999, 9999]),
    ([0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 1.00, 1.50, 2.00],
     [-25, -32, -45, -60, -81, -130, -196, -260, -326]),
    ([0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 1.00, 1.50, 2.00],
     [-10, -13, -19, -25, -34, -55, -83, -110, -137]),
    ([0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 1.00, 1.50, 2.00],
     [-4, -5, -7, -10, -14, -22, -34, -45, -56]),
],
    inverted=False,
    reverse_index=True,
    names=['I', 'II', 'III1', 'III2', 'IV', 'V'])
"""
Klug/Manier stabilty classes. Class center values taken from TA Luft 2002
[TAL2002]_.

Tabelle 17: Bestimmung der Monin–Obukhov–Länge L_M

:meta hide-value:
"""

# ----------------------------------------------------
#
PG1972 = StabiltyClass(bounds=[
    #        ([0.0010125, 0.0018802, 0.0047581,  0.008836,  0.022361,
    #           0.056587,   0.10508,   0.19514,   0.49384],
    #         [-0.130121,  -0.12399, -0.114696, -0.108358, -0.098456,
    #           -0.087685, -0.079713, -0.071017, -0.056878]),
    #        ([0.0010125, 0.0018802, 0.0047581,  0.008836,  0.022361,
    #           0.056587,   0.10508,   0.19514,   0.49384],
    #         [-0.086466, -0.081043, -0.072786, -0.067090, -0.057879,
    #           -0.047121, -0.039191, -0.031135, -0.015915]),
    #        ([0.0010125, 0.0018802, 0.0047581,  0.008836,  0.022361,
    #           0.056587,   0.10508,   0.19514,   0.49384],
    #         [-0.036088, -0.032579, -0.027597, -0.024512, -0.019885,
    #           -0.015090, -0.011871, -0.008705, -0.004281]),
    #        ([0.0010125, 0.0018802, 0.0047581,  0.008836,  0.022361,
    #           0.056587,   0.10508,   0.19514,   0.49384],
    #         [ 0.012206,  0.009979,  0.007739,  0.006889,  0.006501,
    #           0.004992,  0.004183,  0.003579,  0.002873]),
    #        ([0.0010125, 0.0018802, 0.0047581,  0.008836,  0.022361,
    #           0.056587,   0.10508,   0.19514,   0.49384],
    #         [ 0.040156,  0.033523,  0.025014,  0.021329,  0.016380,
    #           0.012502,  0.010628,  0.009159,  0.007393]),
    #        ([0.0010125, 0.0018802, 0.0047581,  0.008836,  0.022361,
    #           0.056587,   0.10508,   0.19514,   0.49384],
    #         [ 0.095955,  0.085088,  0.069084,  0.059677,  0.047705,
    #         0.038408,  0.032892,  0.028047,  0.022981]),
    ([0.005, 0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 2.00],
     [-0.114, -0.107, -0.099, -0.089, -0.081, -0.071, -0.057, -0.042]),
    ([0.005, 0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 2.00],
     [-0.072, -0.066, -0.059, -0.049, -0.040, -0.031, -0.016, -0.002]),
    ([0.005, 0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 2.00],
     [-0.028, -0.024, -0.021, -0.016, -0.013, -0.009, -0.004, -0.001]),
    ([0.005, 0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 2.00],
     [0.008, 0.007, 0.006, 0.005, 0.005, 0.004, 0.003, 0.0001]),
    ([0.005, 0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 2.00],
     [0.025, 0.020, 0.017, 0.013, 0.011, 0.009, 0.007, 0.0002]),
    ([0.005, 0.01, 0.02, 0.05, 0.10, 0.20, 0.50, 2.00],
     [0.068, 0.058, 0.049, 0.039, 0.033, 0.028, 0.023, 0.006]),
],
    inverted=True,
    reverse_index=False,
    names=['A', 'B', 'C', 'D', 'E', 'F', 'G'])
"""
Pasquill-Gifford stability classes.
Class Boundaries scraped from [GOL1972]_ Fig 5

According to EPA (link?) class G is neglected for regulatory modeling

:meta hide-value:
"""


# ----------------------------------------------------
#
def stabilty_class(classifyer, time, z0, L):
    """
    Returns the atmospheric stability class according to
     the selected classification scheme.

    :param str classifyer: The classification method
        ('Klug/Manier', 'KM2021', 'KM', 'TA Luft 2021',
        'KM2002', or 'TA Luft 2002').
    :param time: Date and time
    :type time: pandas.DatetimeIndex or datetime64
    :param z0: Roughness length(s)
    :type z0: pandas.Series or float
    :param L: Monin-Obukhov length(s) in m
     :type L: pd.Series or float

    :return: Stability class indices (1-6; 9 for missing values)
    :rtype: list

    :raises ValueError: If shapes of time, z0, and L are not equal.
    :raises ValueError: If an unknown classification method is provided.

    :example:
        >>> import pandas as pd
        >>> time = pd.DatetimeIndex(['2024-08-02 12:00:00'])
        >>> z0 = pd.Series(0.1, index=time)
        >>> L = pd.Series(-100, index=time)  # Example Monin-Obukhov length
        >>> result = stabilty_class('KM2021', time, z0, L)
        >>> print("Stability class indices:", result)
        Stability class indices: [2]

    """
    # check / adjust types
    if _isscalar(time):
        time = pd.DatetimeIndex([time])
    else:
        time = pd.DatetimeIndex(time)
    if _isscalar(z0):
        z0 = pd.Series(z0, index=time)
    else:
        z0 = pd.Series(z0)
    L = pd.Series(L)
    if not (np.shape(time) == np.shape(z0) == np.shape(L)):
        raise ValueError('shapes of time, z0, L are not equal')

    if classifyer in ['Klug/Manier', 'KM2021', 'KM', 'TA Luft 2021']:
        scale = KM2021
    elif classifyer in ['KM2002', 'TA Luft 2002']:
        scale = KM2002
    elif classifyer in ['Pasquill/Gifford', 'PG1972', 'PG']:
        scale = PG1972
    else:
        return ValueError('unknown classication :%s' % classifyer)

    # 9 = missing value
    sclass = np.array([9] * len(time))
    for i, t in enumerate(time):
        sclass[i] = scale.get_index(z0.iloc[i], L.iloc[i], inverted=False)

    return sclass[()].tolist()


# =============================================================================

def vdi_3872_6_sun_rise_set(time, lat, lon):
    r"""
    Sunrise and sunset calculation
    according to VDI 3782 Part 6, Annex A

    Based on equation (B10) for the solar elevation angle :math:`{\gamma}`
    quoted in VDI 3789:

    :math:`\sin\gamma = \sin\phi + \cos\phi \cos\delta \cos\omega_0`

    :param time: (required, time-like)
        An arbitrary time during the day of year for which
        surise and sunset should be calculated.
        May be supplied as any form accepted by `pandas.to_datetime()`,
        e.g. timestamp (`"2000-12-14 18:00:00"`) or datetime64.
        If timezone is not supplied, CET (without daylight saving) is assumed.
        If timezone is supplied, time is converted to CET.
    :param lat: (required, float) latitude in degrees.
        Southern latitudes must be nagtive.
    :param lon: (required, float) longitude in degrees.
        Eastern longitudes are positive,
        western longitudes are negative.
        Only positions iside CET timezone (-9.5 < lon < 32.0)
        are allowed, by definition.

    :return: sunrise, sunset as decimal hours
        in the timezone supplied in parameter `time`.
    :rtype: `tuple(float)` if `time` is a scalar,
        `tuple(pandas.Series)` if `time` is array-like.
    """
    # check types
    if _isscalar(time):
        scalar = True
        idx = [pd.to_datetime(time)]
    else:
        idx = time
        scalar = False
    if not ((_isscalar(lat) and _isscalar(lon)) or
            (np.shape(time) == np.shape(lat) == np.shape(lon))):
        raise ValueError('lat, lon must be scalars or same shape as time')
    # check / adjust timezone
    # Etc/GMT-1 (fixed-offset timezone) equals CET without DST applied
    if idx.tz is None:
        idx_loc = idx.tz_localize('Etc/GMT-1')
    else:
        idx_loc = idx
    cet = idx_loc.tz_convert('Etc/GMT-1')
    if np.min(lon) < -9.5 or np.max(lon) > 32.:
        raise ValueError('VDI 3782 Part 6, Annex A defined for CET, only')
    # get day of year in CET
    jul = pd.Series(pd.to_datetime(cet).dayofyear, index=idx)  # days
    # latitude in radians
    phi_rad = np.deg2rad(lat)  # rad
    # equation (A3)
    x = 0.9856 * jul - 2.72  # deg
    # abbreviation
    sin_x = np.sin(np.deg2rad(x))  # 1
    # equation (A2)
    delta_rad = np.arcsin(0.3978 *
                          np.sin(np.deg2rad(x - 77.51 + 1.92 * sin_x)))
    # equation (A4)
    omega_0 = (np.rad2deg(np.arccos(-np.tan(delta_rad) * np.tan(phi_rad))) *
               12. / 180.)
    # equation (A7)
    Z_v = (15. - lon) * 1. / 15.  # hours
    # equation (A8)
    Z = (-0.1277 * sin_x -
         0.1645 * np.sin(np.deg2rad(2 * x + 24.99 + 3.83 * sin_x)))  # hours
    # equations (A9) and A(10)
    s_up = 12. - omega_0 + Z_v - Z
    s_dn = 12. + omega_0 + Z_v - Z

    # convert CET to tz given
    tzoff = (pd.Series([x.tzinfo.utcoffset(x).seconds / 3600. for x in idx_loc],
                       index=idx) -
             pd.Timestamp.now(tz='CET').utcoffset().seconds / 3600.)
    s_up = s_up + tzoff
    s_dn = s_dn + tzoff
    # return scalar if scalar was spupplied
    if scalar:
        s_up, s_dn = s_up[0], s_dn[0]
    return s_up, s_dn  # CET


# ----------------------------------------------------

def vdi_3872_6_standard_wind(va, hap, z0p):
    r"""
    Returns the Calculation value of wind speed
    according to VDI 3782 Part 6, Annex A

    The norm is based on wind speed values
    that are taken at the standard measurement
    height of 10 m above ground (VDI 3786 Part 2;
    VDI 3783 Part 8; [5; 6]) in combination with a
    roughness length of :math:`z0 = 0.1` m.
    If the wind speed :math:`v_a` is available for other than
    the standard conditions, a conversion needs to be
    carried out from the conditions (measurement height
    :math:`h_a'`, roughness lenght :math:`z_0'`) at the measurement
    site to the standard conditions.

    :param va: (required,float or array-like)
        measured wind speed (:math:`v_a`) in m/s.
    :param hap: (required,float) height of the wind measurement
        above ground (:math:`h_a`) in m.
    :param z0p: (required,float) roughness lenght at the
        measurement site (:math:`z_0`) in m.
    """
    va = np.array(va)
    # hr = 100 m
    # For hap >100 m , the reference height h r should be
    # set to hap′.
    hr = np.max((100., hap))

    ha = 10
    z0 = 0.1
    d0p = 6 * z0p
    d0 = 6 * z0

    f_1 = np.log((hr - d0p) / z0p) / np.log((hap - d0p) / z0p)
    f_2 = np.log((ha - d0) / z0) / np.log((hr - d0) / z0)
    f = f_1 * f_2

    v10 = np.array([np.round(f * x, 1) for x in va])

    return v10[()]  # Flatten 0d arrays to scalars


# ----------------------------------------------------

def klug_manier_scheme_1992(time: pd.Timestamp, ff, tcc, lat, lon, cty=None):
    """
    Calulate stability class after Klug/Manier
    accroding to according to VDI 3782 Part 1 (issued 1992)


     ========== ================= =======
      Category  Atmospheric        Index
                stability
     ========== ================= =======
      I         very stable         1
      II        stable              2
      III/1     neutral/stable      3
      III/2     neutral/unstable    4
      IV        unstable            5
      V         very unstable       6
     ========== ================= =======

    :param time: (required, time-like)
        An arbitrary time during the day of year for which
        surise and sunset should be calculated.
        May be supplied as any form accepted by `pandas.to_datetime()`,
        e.g. timestamp (`"2000-12-14 18:00:00"`) or datetime64.
        If timezone is not supplied, UTC is assumed.
        If timezone is supplied, time is converted to CET.
    :param ff: (required, float)
        wind speed in 10m height.
    :param tcc: (required, float)
        total cloud cover as fraction of 1
        (equals value in octa divided by 8).
    :param lat: (required, float) latitude in degrees.
        Southern latitudes must be nagtive.
    :param lon: (required, float) longitude in degrees.
        Eastern longitudes are positive,
        western longitudes are negative.
    :param cty: (optional, str) cloud type of lowest cloud layer.
        When it is "CI", "CS", or "CC", the condition
        "cloud coverage exclusively consits of high clouds (Cirrus)" is met.
        If absent, "CU" is assumed.

    :return: class value (numeric index)
    :rtype: `int` if `time` is a scalar,
        `pandas.Series(int64)` if `time` is array-like.
    """
    # check / adjust types
    if _isscalar(time):
        scalar = True
        time = pd.DatetimeIndex([time])
    else:
        scalar = False
        time = pd.DatetimeIndex(time)
    if not isinstance(ff, pd.Series):
        ff = pd.Series(ff, index=time)
    if not isinstance(tcc, pd.Series):
        tcc = pd.Series(tcc, index=time)
    if not (np.shape(time) == np.shape(ff) == np.shape(tcc)):
        raise ValueError('shapes of time, ff, tcc are not equal')
    if not ((_isscalar(lat) and _isscalar(lon)) or
            (np.shape(time) == np.shape(lat) == np.shape(lon))):
        raise ValueError('lat, lon must be scalars or same shape as time')
    if cty is None:
        cty = pd.Series('CU', index=time)
    else:
        if not isinstance(cty, pd.Series):
            cty = pd.Series(cty, index=time)
    if not (np.shape(time) == np.shape(cty)):
        raise ValueError('shapes of time and cty are not equal')
    # valid valid for Germmany:
    if ((np.min(lon) < -9.5) or
            (np.min(lat) < 35.) or
            (np.max(lon) > 32.) or
            (np.max(lat) > 62.)):
        logger.warning('Klug-Manier scheme is made for Central Europe, only.')

    logger.debug('klug_manier_scheme_1992 ---> %19s ...' % (time[0]))
    # Einlesen
    monat = pd.Series([x.month for x in time], index=time)
    stund = pd.Series([(float(x.hour) + float(x.minute) / 60.)
                       for x in time], index=time)

    # auf/unter UTC
    s_auf, _, s_unter = m.radiation.fast_rise_transit_set(time, lat, lon)
    if np.min(s_unter - s_auf) < 5:
        raise ValueError('scheme only defined where day length exceeds 5h')
    for x, y in zip(s_auf, s_unter):
        logger.debug('surise,sunset : (%f, %f)' % (x, y))
    #
    # Ausbreitungsklassen
    #
    k = {KM2002.name(i + 1): i + 1 for i in range(KM2002.count)}
    #
    # Tabelle A.1
    #
    # Wind-          |  Gesamtbedeckung in Achten  |
    # geschwindigkeit| für Nacht |     für Tages   |
    # in 10 m Höhe   | stunden**)|     stunden**)  |
    # in m/s         | 0/8 | 7/8 | 0/8 | 3/8 | 6/8 |
    #                | bis | bis | bis | bis | bis |
    #                | 6/8 | 8/8 | 2/8 | 5/8 | 8/8 |
    # 1 und darunter |  I  | II  | IV  | IV  | IV  |
    # 1,5 und 2      |  I  | II  | IV  | IV  |III2 |
    # 2,5 und 3      | II  |III1 | IV  | IV  |III2 |
    # 3,5 und 4      |III1 |III1 | IV  |III2 |III2 |
    # 4,5 und darüber|III1 |III1 |III2 |III1 |III1 |
    #
    # *) Bei den Fällen mit einer Gesamtbedeckung, die ausschließ-
    # lich aus hohen Wolken (Cirren) besteht, ist von einer um 3/8
    # erniedrigten Gesamtbedeckung auszugehen.
    ecc = pd.Series([np.max((0., x - 0.375)) if y in ['CI', 'CC', 'CS']
                     else x for x, y in zip(tcc, cty)], index=time)
    for x, y, z in zip(tcc, cty, ecc):
        logger.debug('tcc: %4f, cty: %2s, ecc: %4f' % (x, y, z))
    # K_N for night conditions
    kn = pd.Series(np.nan, index=time)
    # K_T for day conditions
    kt = pd.Series(np.nan, index=time)
    for i, _ in enumerate(time):
        # K_N for night conditions
        if ecc.iloc[i] <= 0.75:
            if ff.iloc[i] <= 2.:
                kn.iloc[i] = k['I']
            elif ff.iloc[i] <= 3:
                kn.iloc[i] = k['II']
            else:  # ff.iloc[i] > 3
                kn.iloc[i] = k['III1']
        else:
            if ff.iloc[i] <= 2.:
                kn.iloc[i] = k['II']
            else:  # ff.iloc[i] > 2)
                kn.iloc[i] = k['III1']
        # K_T for day conditions
        if ecc.iloc[i] <= 0.25:
            if ff.iloc[i] <= 4:
                kt.iloc[i] = k['IV']
            else:  # ff.iloc[i] > 4:
                kt.iloc[i] = k['III2']
        elif ecc.iloc[i] < 0.75:
            if ff.iloc[i] <= 3:
                kt.iloc[i] = k['IV']
            elif ff.iloc[i] <= 4:
                kt.iloc[i] = k['III2']
            else:  # ff.iloc[i] > 4
                kt.iloc[i] = k['III1']
        else:  # ecc.iloc[i] >= 0.75
            if ff.iloc[i] <= 1:
                kt.iloc[i] = k['IV']
            elif ff.iloc[i] <= 4:
                kt.iloc[i] = k['III2']
            else:  # ff.iloc[i] > 4:
                kt.iloc[i] = k['III1']

        logger.debug('table A.1: k_n: %4s, k_d: %4s' %
                     (KM2002.name(kn.iloc[i]), KM2002.name(kt.iloc[i])))
    #
    # **)  Für die Abgrenzung sind Sonnenaufgang und -untergang
    #      (MEZ) maßgebend. Die Ausbreitungsklasse für Nachtstunden
    #      wird noch für die auf den Sonnenaufgang folgende volle Stunde
    #      eingesetzt.
    #
    km = pd.Series(np.nan, index=time)
    for i, _ in enumerate(time):
        if stund.iloc[i] <= np.ceil(s_auf.iloc[i]):
            km.iloc[i] = kn.iloc[i]
            logger.debug('morning        -> %4s' % (KM2002.name(km.iloc[i])))
        elif stund.iloc[i] <= s_unter.iloc[i]:
            km.iloc[i] = kt.iloc[i]
            logger.debug('day            -> %4s' % (KM2002.name(km.iloc[i])))
        else:
            km.iloc[i] = kn.iloc[i]
            logger.debug('evening        -> %4s' % (KM2002.name(km.iloc[i])))

    #
    # besondere Ausbreitungsverhaeltnisse
    #
    for i, _ in enumerate(time):
        #
        # Teil a)
        # Ergeben sich für die Monate Juni bis August und
        # die Stunden von 10.00 bis 16.00 MEZ Ausbrei-
        # tungsklassen unter V, so ist für eine Gesamtbedek-
        # kung von nicht mehr als °/, oder eine Gesamtbe-
        # deckung von 6/8 und Windgeschwindigkeiten
        # unter 2,5 m/s die nächsthöhere Ausbreitungs-
        # klasse einzusetzen. Für die Stunden von 12.00 bis
        # 15.00 MEZ bei Bedeckung von nicht mehr als 5/8
        # ist, unter Beachtung von Satz 1, die nächsthöhere
        # Ausbreitungsklasse - im Fall der Klasse IV die
        # Klasse V - einzusetzen.
        #
        if monat.iloc[i] in [6, 7, 8]:
            if stund.iloc[i] >= 10 and stund.iloc[i] <= 16 and km.iloc[i] < k['V']:
                if ecc.iloc[i] <= 0.75:
                    km.iloc[i] = km.iloc[i] + 1
                    logger.debug('rule a.1a     -> %4s' % (KM2002.name(km.iloc[i])))
                elif ecc.iloc[i] <= 0.875 and ff.iloc[i] < 2.5:
                    km.iloc[i] = km.iloc[i] + 1
                    logger.debug('rule a.1b     -> %4s' % (KM2002.name(km.iloc[i])))
            if stund.iloc[i] >= 12 and stund.iloc[i] <= 15 and km.iloc[i] < k['V']:
                if ecc.iloc[i] <= 0.625:
                    km.iloc[i] = km.iloc[i] + 1
                    logger.debug('rule a.2      -> %4s' % (KM2002.name(km.iloc[i])))
        #
        # Teil b)
        # Für die Monate Mai und September ist für die
        # Stunden von 11.00 bis 15.00 MEZ und eine Be-
        # deckung von nicht mehr als 6/8 die nächsthöhere
        # Ausbreitungsklasse - im Fall der Klasse IV die
        # Klasse V - einzusetzen.
        #
        elif monat.iloc[i] in [5, 9]:
            if stund.iloc[i] >= 11 and stund.iloc[i] <= 15:
                if ecc.iloc[i] <= 0.75:
                    km.iloc[i] = km.iloc[i] + 1
                    logger.debug('rule b        -> %4s' % (KM2002.name(km.iloc[i])))
        #
        # Teil c)
        # Für jede volle Stunde der Zeiträume von 1 Stunde
        # bis 3 Stunden nach Sonnenaufgang (SA+1 bis
        # SA+3) und von 2 Stunden vor bis 1 Stunde nach
        # Sonnenuntergang (SU—2 bis SU+1) werden die
        # Ausbreitungsklassen nach Tabelle A2 sowohl
        # nach den Spalten für Nachtstunden (K_N) als auch
        # nach den Spalten für Tagstunden (K) bestimnt.
        # Tabelle A2 enthält alle möglichen Kombinatio-
        # nen der Ausbreitungsklassen K_N und K_T und gibt
        # welche statt dessen für diean, Ausbreitungsklasse
        # Ausbreitungsrechnung zu verwenden ist. Geht
        # z.B. die Sonne um 6.25 MEZ auf, dann ist für
        # SA+1 bis SA+2 der Wert für die Stunden von
        # 7.25 bis 8.25 MEZ einzusetzen. Bei stündlicher
        # Zeitfolge mit Beobachtungen zur vollen Stunde
        # ist die Bestimmung der Ausbreitungsklasse für
        # 8.00 MEZ gültig
        #
        # Tabelle A2. Ausbreitungsklassen
        # | KN | KT | SA+1 | SA+2 | SU-2 | SU-1 | SU   |
        # | KN | KT | bis  | bis  | bis  | bis  | bis  |
        # |    |    | SA+2 | SA+3 | SU-1 | SU   | SU+1 |
        # | I  | IV |I(II)*|  II  |  II |II(I)**|I(II)*|
        # | I  |III2|  II  |  II  | III1 | III1 |I(II)*|
        # | II | IV |  II  | III1 | III1 |  II  |  II  |
        # | II |III2| III2 | III1 | III1 | III1 |  II  |
        # |III1| IV | III1 | III2 | III2 | III1 | III1 |
        # |III1|III2| III1 | III1 | III2 | III2 | III1 |
        # |III1|III1| III1 | III1 | III1 | III1 | III1 |
        #
        # *) Für die Monate  März bis November und Windgeschwindig-
        #    keiten über 1 m/s ist der Wert in der Klammer einzusetzen.
        # **) Für die Monate Januar, Februar und Dezember, Windge-
        #    schwindigkeiten bis 1 m/s und Gesamtbedeckung bis 6/8 ist
        #    der Wert in der Klammer einzusetzen.
        #
        a2_star = None
        a2_col = None
        if kn.iloc[i] == k['I'] and kt.iloc[i] == k['IV']:
            if stund.iloc[i] >= s_auf.iloc[i] + 1. and stund.iloc[i] < s_auf.iloc[i] + 2.:
                # Fussnote *)
                if (monat.iloc[i] in [3, 4, 5, 6, 7, 8, 9, 10, 11] and ff.iloc[i] > 1.):
                    km.iloc[i] = k['II']
                    a2_star = '*'
                else:
                    km.iloc[i] = k['I']
            elif stund.iloc[i] >= s_auf.iloc[i] + 2. and stund.iloc[i] < s_auf.iloc[i] + 3.:
                km.iloc[i] = k['II']
            elif stund.iloc[i] >= s_unter.iloc[i] - 2. and stund.iloc[i] < s_unter.iloc[i] - 1.:
                km.iloc[i] = k['II']
            elif stund.iloc[i] >= s_unter.iloc[i] - 1. and stund.iloc[i] < s_unter.iloc[i]:
                # Fussnote **)
                if monat.iloc[i] in [1, 2, 12] and ff.iloc[i] <= 1 and ecc.iloc[i] <= 0.75:
                    km.iloc[i] = k['I']
                    a2_star = '**'
                else:
                    km.iloc[i] = k['II']
            elif stund.iloc[i] >= s_unter.iloc[i] and stund.iloc[i] < s_unter.iloc[i] + 1.:
                # Fussnote *)
                if (monat.iloc[i] in [3, 4, 5, 6, 7, 8, 9, 10, 11] and ff.iloc[i] > 1):
                    a2_star = '*'
                    km.iloc[i] = k['II']
                else:
                    km.iloc[i] = k['I']
        elif kn.iloc[i] == k['I'] and kt.iloc[i] == k['III2']:
            if stund.iloc[i] >= s_auf.iloc[i] + 1. and stund.iloc[i] < s_auf.iloc[i] + 2.:
                km.iloc[i] = k['II']
            elif stund.iloc[i] >= s_auf.iloc[i] + 2. and stund.iloc[i] < s_auf.iloc[i] + 3.:
                km.iloc[i] = k['II']
            elif stund.iloc[i] >= s_unter.iloc[i] - 2. and stund.iloc[i] < s_unter.iloc[i] - 1.:
                km.iloc[i] = k['III1']
            elif stund.iloc[i] >= s_unter.iloc[i] - 1. and stund.iloc[i] < s_unter.iloc[i]:
                km.iloc[i] = k['III1']
            elif stund.iloc[i] >= s_unter.iloc[i] and stund.iloc[i] < s_unter.iloc[i] + 1.:
                # Fussnote *)
                if (monat.iloc[i] in [3, 4, 5, 6, 7, 8, 9, 10, 11] and ff.iloc[i] > 1):
                    a2_star = '*'
                    km.iloc[i] = k['II']
                else:
                    km.iloc[i] = k['I']
        elif kn.iloc[i] == k['II'] and kt.iloc[i] == k['IV']:
            if stund.iloc[i] >= s_auf.iloc[i] + 1. and stund.iloc[i] < s_auf.iloc[i] + 2.:
                km.iloc[i] = k['II']
            elif stund.iloc[i] >= s_auf.iloc[i] + 2. and stund.iloc[i] < s_auf.iloc[i] + 3.:
                km.iloc[i] = k['III1']
            elif stund.iloc[i] >= s_unter.iloc[i] - 2. and stund.iloc[i] < s_unter.iloc[i] - 1.:
                km.iloc[i] = k['III1']
            elif stund.iloc[i] >= s_unter.iloc[i] - 1. and stund.iloc[i] < s_unter.iloc[i]:
                km.iloc[i] = k['II']
            elif stund.iloc[i] >= s_unter.iloc[i] and stund.iloc[i] < s_unter.iloc[i] + 1.:
                km.iloc[i] = k['II']
        elif kn.iloc[i] == k['II'] and kt.iloc[i] == k['III2']:
            if stund.iloc[i] >= s_auf.iloc[i] + 1. and stund.iloc[i] < s_auf.iloc[i] + 2.:
                km.iloc[i] = k['III1']
            elif stund.iloc[i] >= s_auf.iloc[i] + 2. and stund.iloc[i] < s_auf.iloc[i] + 3.:
                km.iloc[i] = k['III1']
            elif stund.iloc[i] >= s_unter.iloc[i] - 2. and stund.iloc[i] < s_unter.iloc[i] - 1.:
                km.iloc[i] = k['III1']
            elif stund.iloc[i] >= s_unter.iloc[i] - 1. and stund.iloc[i] < s_unter.iloc[i]:
                km.iloc[i] = k['III1']
            elif stund.iloc[i] >= s_unter.iloc[i] and stund.iloc[i] < s_unter.iloc[i] + 1.:
                km.iloc[i] = k['II']
        elif kn.iloc[i] == k['III1'] and kt.iloc[i] == k['IV']:
            if stund.iloc[i] >= s_auf.iloc[i] + 1. and stund.iloc[i] < s_auf.iloc[i] + 2.:
                km.iloc[i] = k['III1']
            elif stund.iloc[i] >= s_auf.iloc[i] + 2. and stund.iloc[i] < s_auf.iloc[i] + 3.:
                km.iloc[i] = k['III2']
            elif stund.iloc[i] >= s_unter.iloc[i] - 2. and stund.iloc[i] < s_unter.iloc[i] - 1.:
                km.iloc[i] = k['III2']
            elif stund.iloc[i] >= s_unter.iloc[i] - 1. and stund.iloc[i] < s_unter.iloc[i]:
                km.iloc[i] = k['III1']
            elif stund.iloc[i] >= s_unter.iloc[i] and stund.iloc[i] < s_unter.iloc[i] + 1.:
                km.iloc[i] = k['III1']
        elif kn.iloc[i] == k['III1'] and kt.iloc[i] == k['III2']:
            if stund.iloc[i] >= s_auf.iloc[i] + 1. and stund.iloc[i] < s_auf.iloc[i] + 2.:
                km.iloc[i] = k['III1']
            elif stund.iloc[i] >= s_auf.iloc[i] + 2. and stund.iloc[i] < s_auf.iloc[i] + 3.:
                km.iloc[i] = k['III1']
            elif stund.iloc[i] >= s_unter.iloc[i] - 2. and stund.iloc[i] < s_unter.iloc[i] - 1.:
                km.iloc[i] = k['III2']
            elif stund.iloc[i] >= s_unter.iloc[i] - 1. and stund.iloc[i] < s_unter.iloc[i]:
                km.iloc[i] = k['III2']
            elif stund.iloc[i] >= s_unter.iloc[i] and stund.iloc[i] < s_unter.iloc[i] + 1.:
                km.iloc[i] = k['III1']
        elif kn.iloc[i] == k['III1'] and kt.iloc[i] == k['III1']:
            if stund.iloc[i] >= s_auf.iloc[i] + 1. and stund.iloc[i] < s_auf.iloc[i] + 2.:
                km.iloc[i] = k['III1']
            elif stund.iloc[i] >= s_auf.iloc[i] + 2. and stund.iloc[i] < s_auf.iloc[i] + 3.:
                km.iloc[i] = k['III1']
            elif stund.iloc[i] >= s_unter.iloc[i] - 2. and stund.iloc[i] < s_unter.iloc[i] - 1.:
                km.iloc[i] = k['III1']
            elif stund.iloc[i] >= s_unter.iloc[i] - 1. and stund.iloc[i] < s_unter.iloc[i]:
                km.iloc[i] = k['III1']
            elif stund.iloc[i] >= s_unter.iloc[i] and stund.iloc[i] < s_unter.iloc[i] + 1.:
                km.iloc[i] = k['III1']

        if stund.iloc[i] >= s_auf.iloc[i] + 1. and stund.iloc[i] < s_auf.iloc[i] + 2.:
            a2_col = 'SA+1/SA+2'
        elif stund.iloc[i] >= s_auf.iloc[i] + 2. and stund.iloc[i] < s_auf.iloc[i] + 3.:
            a2_col = 'SA+2/SA+3'
        elif stund.iloc[i] >= s_unter.iloc[i] - 2. and stund.iloc[i] < s_unter.iloc[i] - 1.:
            a2_col = 'SU-2/SU-1'
        elif stund.iloc[i] >= s_unter.iloc[i] - 1. and stund.iloc[i] < s_unter.iloc[i]:
            a2_col = 'SU-1/SU'
        elif stund.iloc[i] >= s_unter.iloc[i] and stund.iloc[i] < s_unter.iloc[i] + 1.:
            a2_col = '  SU/SU+1'
        if a2_col is not None:
            logger.debug('rule c tab A.2:')
            if a2_star is not None:
                logger.debug('footnote (%2a) :' % a2_star)
            logger.debug('col: %9a-> %4s' % (a2_col, KM2002.name(km.iloc[i])))
        #
        # Teil d)
        #  Für die Monate Dezember, Januar und Februar
        # ist die Ausbreitungsklasse IV durch die Ausbrei-
        # tungsklasse III2 zu ersetzen.
        #
        if monat.iloc[i] in [1, 2, 12]:
            if km.iloc[i] == k['IV']:
                km.iloc[i] = k['III2']
                logger.debug('rule d        -> %4s' % (KM2002.name(km.iloc[i])))

    #
    # Fälle, bei denen keine Ausbreitungsklasse bestimmt
    # werden kann, werden bei Windgeschwindigkeiten
    # unter 2 m/s der Ausbreitungsklasse I, von 2,5 bis
    # 3 m/s der Klasse II und von mehr als 3,5 m/s der
    # Klasse III1 zugeordnet.
    for i, _ in enumerate(time):
        if km.iloc[i] == 0:
            if ff.iloc[i] < 2.0:
                km.iloc[i] = k['I']
            elif ff.iloc[i] <= 3.5:
                # here we include 2.0 ... 2.5 m/s as
                # else it would remain undefinded
                km.iloc[i] = k['II']
            else:
                km.iloc[i] = k['III1']
            logger.debug('savlatory rule-> %4s' % (KM2002.name(km.iloc[i])))

    logger.debug('return value  -> %s' % str([KM2002.name(x) for x in km]))
    if scalar:
        km = km[0]
    return km


# ----------------------------------------------------

def klug_manier_scheme_2017(time: pd.DatetimeIndex, ff, tcc, lat, lon, ele,
                            cty=None, cbh=None,
                            _cloudout=False):
    """
    Calulate stability class after Klug/Manier
    according to according to VDI 3782 Part 6 (issued Apr 2017)

     ========== ================= =======
      Category  Atmospheric        Index
                stability
     ========== ================= =======
      I         very stable         1
      II        stable              2
      III/1     neutral/stable      3
      III/2     neutral/unstable    4
      IV        unstable            5
      V         very unstable       6
     ========== ================= =======

    The norm states:

      Strictly speaking, the above correction conditions apply
      only to locations in Central Europe with a pronounced season-
      al climate and sunrise and sunset times definable over the
      whole year, which in particular during the winter months
      always exhibit a time difference exceeding six hours. These
      conditions are met in Germany. For other countries, CET
      should be replaced where relevant by the corresponding zone-
      time. In climatic zones with diurnal climate or other calendar
      classifications of astronomical seasons, the correction condi-
      tions are not directly applicable in the above form. Adaptation
      of subsections a to d for other global climatic zones does not
      form a part of this standard.

    :param time: (required, time-like)
        An arbitrary time during the day of year for which
        surise and sunset shout be calculated.
        May be supplied as any form accepted by `pandas.to_datetime()`,
        e.g. timestamp (`"2000-12-14 18:00:00"`) or datetime64.
        If timezone is not supplied, UTC is assumed.
        If timezone is supplied, time is converted to CET.
    :param ff: (required, float)
        wind speed in 10m height. VDI 3782 Part 6 states:

          The standard conditions for
          the wind speed (υa) are the standard measurement
          height of 10 m above ground (VDI 3786 Part 2;
          VDI 3783 Part 8) in combination with a
          roughness length of z0 = 0,1 m. Other measurement
          heights are suitable if they equal at least twelve
          times the roughness length and are at least 4 m
          above ground level. If the wind speed is available
          for other than the above standard conditions,
          i.e. for another suitable measurement height
          or a different roughness length,
          a conversion needs to be carried out.
    :param tcc: (required, float)
        total cloud cover as fraction of 1
        (equals value in octa divided by 8).
    :param lat: (required, float) latitude in degrees.
        Southern latitudes must be nagtive.
    :param lon: (required, float) longitude in degrees.
        Eastern longitudes are positive,
        western longitudes are negative.
    :param ele: (required, float) surface elvation above sea level in m.
    :param cbh: (optional, float) cloud base height in m.
    :param cty: (optional, str) cloud type of lowest cloud layer.
        When it is "CI", "CS", or "CC", the condition
        "cloud coverage exclusively consits of high clouds (Cirrus)" is met.
        If absent, "CU" is assumed.
    :param _cloudout: (optional, boolean) for verification only.

    :return: class value (numeric index)
    :rtype: `int` if `time` is a scalar,
        `pandas.Series(int64)` if `time` is array-like.
    """
    # check / adjust types
    if _isscalar(time):
        scalar = True
        time = pd.DatetimeIndex([time])
    else:
        scalar = False
        time = pd.DatetimeIndex(time)
    if not isinstance(ff, pd.Series):
        ff = pd.Series(ff, index=time)
    if not isinstance(tcc, pd.Series):
        tcc = pd.Series(tcc, index=time)
    # set negative values (invalid) to nan
    tcc = tcc.mask(tcc < 0, np.nan)
    if not (np.shape(time) == np.shape(ff) == np.shape(tcc)):
        logger.debug((np.shape(time), np.shape(ff), np.shape(tcc)))
        raise ValueError('shapes of time, ff, tcc are not equal')
    if not ((_isscalar(lat) and _isscalar(lon) and _isscalar(ele)) or
            (np.shape(time) == np.shape(lat) ==
             np.shape(lon) == np.shape(ele))):
        raise ValueError('lat, lon, and ele must be ' +
                         'scalars or same shape as time')
    if cbh is not None:
        if not isinstance(cbh, pd.Series):
            cbh = pd.Series(cbh, index = time)
        if not (np.shape(time) == np.shape(cbh)):
            raise ValueError('shapes of time and cbh are not equal')
    if cty is not None:
        if not isinstance(cty, pd.Series):
            cty = pd.Series(cty, index=time)
        if not (np.shape(time) == np.shape(cty)):
            raise ValueError('shapes of time and cty are not equal')
    # valid valid for Germany:
    if ((np.min(lon) < -9.5) or
            (np.min(lat) < 35.) or
            (np.max(lon) > 32.) or
            (np.max(lat) > 62.)):
        logger.warning('Klug-Manier scheme is made ' +
                        'for Central Europe, only.')

    logger.debug('klug_manier_scheme_2017 ---> %19s ...' % (time[0]))

    # Einlesen
    monat = pd.Series([x.month for x in time], index=time)
    stund = pd.Series([(float(x.hour) + float(x.minute) / 60.)
                       for x in time], index=time)

    # Sunrise and sunset times are to be quoted in the
    # relevant zonetime. For Germany, CET should be
    # used as zonetime. This time is assigned to
    # 15 degrees east longitude, thus also being the LMT
    # for this degree of longitude. The solar declination,
    # the time equation and the solar elevation are de-
    # termined in accordance with VDI 3789; further
    # information on calculating sunrise and sunset times
    # can be found in Annex A.
    sr, ss = vdi_3872_6_sun_rise_set(time, lat, lon)
    if np.min(ss - sr) < 5:
        raise ValueError('scheme only defined where day length > 5h')
    for i, x, y in zip(stund, sr, ss):
        logger.debug('stund: surise,sunset : %f (%f, %f)' % (i, x, y))

    # convert to 0..24 hours
    sr = sr % 24
    ss = ss % 24
    # ...  Formally, the
    # time range includes its end value, but not its start
    # value. For example, a measurement time t counts
    # as nighttime if it falls within the period defined by
    # SS < t ≤ SR+1.
    daytime = np.logical_or(
        np.logical_and(sr < ss,
                       np.logical_and(sr + 1. < stund, stund <= ss)
                       ),
        np.logical_and(sr > ss,
                       np.logical_or(sr + 1. < stund, stund <= ss)
                       ))
    #
    # Ausbreitungsklassen
    #
    k = {KM2021.name(i + 1): i + 1 for i in range(KM2021.count)}
    #
    # The dispersion categories I to IV are determined
    # according to the scheme shown in Table 2. Cate-
    # gory V may also be set through corrections of Sec-
    # tion 4.4.
    #

    # If “cirrus” is already the cloud type C1 of the first
    # (lowest) cloud layer, i.e. 0 ≤ C1 ≤ 2 (see Table B1),
    # then it is assumed that the total cloud cover con-
    # sists only of cirrus. In this way, the cirrus condition
    # can be checked solely by inspecting the cloud type
    # C1.
    #
    if cty is None:
        c1_cirrus = [np.nan for x in time]
    #        print('c1_cirrus in nan')
    else:
        c1_cirrus = []
        for x in cty:
            if x in ['CI', 'CS', 'CC']:
                # lowest clouds are cirrus
                c1_cirrus.append(True)
            elif x in ['XX', '//']:
                # lowest clouds are unknown
                c1_cirrus.append(np.nan)
            else:
                # lowest clouds are not Cirrus
                c1_cirrus.append(False)

    # If cloud type C1 is not available, e.g. due to the
    # absence of visual observations, the cirrus condition
    # should be checked by means of the condition
    # H1 ≥ H1,lim with H1,lim =
    #   5400 m for H_S <= 600 m amsl
    #   5100 m for 600 m < H_S <= 1200 m amsl
    #   4800 m for 1200 m < H_S <= 2100 m amsl
    #   4200 m for H_S > 2100 m amsl
    #
    if cbh is None:
        c1_base = [np.nan for x in time]
    #       print('c1_base in nan')
    else:
        if _isscalar(ele):
            x = pd.Series(ele, index=time)
        else:
            x = ele
        hlim = pd.Series(0, index=time)
        hlim[x <= 600] = 5400
        hlim[np.logical_and(x > 600, x <= 1200)] = 5100
        hlim[np.logical_and(x > 1200, x <= 2100)] = 4800
        hlim[x > 2100] = 4200
        #        ci_only = cbh.map(lambda x: x < hlim)
        c1_base = [(x > h) for x, h in zip(cbh, hlim)]

    if cty is None and cbh is None:
        logger.warning('both cty and chb missing: ' +
                        'assuming clouds never Ci only.')
        ci_only = [False for x in time]
    else:
        ci_only = []
        for x, y in zip(c1_cirrus, c1_base):
            if not pd.isna(x):
                ci_only.append(x)
            elif not pd.isna(y):
                ci_only.append(y)
            else:
                ci_only.append(False)
    #    for i,x,y,z in zip(time,c1_cirrus,c1_base,ci_only):
    #        print((i,x,y,z))

    # In cases with total cloud cover N > 0/8 consisting
    # solely of high clouds (cirrus), deduct 3/8 from N
    # (cirrus condition C = 1). If this results in a negative
    # value, set N = 0/8.
    #
    # note: np.nan values in ecc ar preserved, here
    # mask: Where cond is False, keep the original value.
    ecc = tcc.mask(ci_only, [np.max((0., x - 0.375)) for x in tcc])
    for i, x in enumerate(time):
        logger.debug('tcc: %f, day: %1i, ci: %1i, ecc: %f' %
                      (tcc.iloc[i], daytime.iloc[i],
                       ci_only[i], ecc.iloc[i]))

    # exit here for cloud verification (development only)
    if _cloudout:
        x = ecc.mask(pd.isna(ecc), -1)
        if scalar:
            return x[0], ci_only[0]
        else:
            return x, ci_only

    # Table 2
    # Wind speed v10 | nighttime | daytime hours   |
    # at 10 m height | hours     |                 |
    # (z_0 = 0.1m)   | total cloud cover in eights |
    # in m/s         | 0/8 | 7/8 | 0/8 | 3/8 | 6/8 |
    #                | to  | to  | to  | to  | to  |
    #                | 6/8 | 8/8 | 2/8 | 5/8 | 8/8 |
    # <= 1.2         |  I  | II  | IV  | IV  | IV  |
    # 1.3 and 2.3    |  I  | II  | IV  | IV  |III2 |
    # 2.4 and 3.3    | II  |III1 | IV  | IV  |III2 |
    # 3.4 and 4.3    |III1 |III1 | IV  |III2 |III2 |
    # >= 4.4         |III1 |III1 |III2 |III1 |III1 |
    #
    # K_N for night conditions
    kn = pd.Series(np.nan, index=time)
    # K_T for day conditions
    kt = pd.Series(np.nan, index=time)
    for i, _ in enumerate(time):
        # K_N for night conditions
        if ecc.iloc[i] <= 0.75:
            if ff.iloc[i] <= 2.3:
                kn.iloc[i] = k['I']
            elif ff.iloc[i] <= 3.3:
                kn.iloc[i] = k['II']
            else:  # ff[i] >= 3.3
                kn.iloc[i] = k['III1']
        elif ecc.iloc[i] > 0.75:
            if ff.iloc[i] <= 2.3:
                kn.iloc[i] = k['II']
            else:  # ff[i] >= 2.4)
                kn.iloc[i] = k['III1']
        else:  # ecc[i] == np.nan
            kn.iloc[i] = np.nan
        # K_T for day conditions
        if ecc.iloc[i] <= 0.25:
            if ff.iloc[i] <= 4.3:
                kt.iloc[i] = k['IV']
            else:  # ff[i] >= 4.4:
                kt.iloc[i] = k['III2']
        elif ecc.iloc[i] < 0.75:
            if ff.iloc[i] <= 3.3:
                kt.iloc[i] = k['IV']
            elif ff.iloc[i] <= 4.3:
                kt.iloc[i] = k['III2']
            else:  # ff[i] >= 4.4
                kt.iloc[i] = k['III1']
        elif ecc.iloc[i] >= 0.75:
            if ff.iloc[i] <= 1.2:
                kt.iloc[i] = k['IV']
            elif ff.iloc[i] <= 4.3:
                kt.iloc[i] = k['III2']
            else:  # ff[i] >= 4.4:
                kt.iloc[i] = k['III1']
        else:  # ecc ==np.nan
            kt.iloc[i] = np.nan

        # no values if cloud cover is missing
        # else show them
        if not np.isnan(kt.iloc[i]) and not np.isnan(kn.iloc[i]):
            logger.debug('ff: %4.1f, k_n: %4s, k_d: %4s' % (
                ff.iloc[i], KM2002.name(kn.iloc[i]), KM2002.name(kt.iloc[i])))

    # select value depending om day/night
    km = kt.where(daytime, kn)

    #
    # Corrections for special time intervals
    #
    for i, _ in enumerate(time):

        # no corrections if cloud cover is missing
        if np.isnan(kt.iloc[i]) or np.isnan(kn.iloc[i]):
            continue
        #
        # rule a)
        # For June to August (climatological summer
        # months) during the hours from 10:00 CET to
        # 16:00 CET, the next higher dispersion category
        # should be chosen for total cloud cover not ex-
        # ceeding 6/8 or total cloud cover of 7/8 and wind
        # speeds below 2,4 ms^–1. For the same months as
        # above during the hours from 12:00 CET to
        # 15:00 CET, again the next higher dispersion cat-
        # egory should be chosen for total cloud cover not
        # exceeding 5/8. If the dispersion category is al-
        # ready V, this modification does not take place.
        #
        if monat.iloc[i] in [6, 7, 8]:
            if stund.iloc[i] >= 10 and stund.iloc[i] <= 16 and km.iloc[i] < k['V']:
                if ecc.iloc[i] <= 0.75:
                    km.iloc[i] = km.iloc[i] + 1
                    logger.debug('rule a.1a     -> %4s' %
                                 (KM2002.name(km.iloc[i])))
                elif ecc.iloc[i] <= 0.875 and ff.iloc[i] < 2.4:
                    km.iloc[i] = km.iloc[i] + 1
                    logger.debug('rule a.1b     -> %4s' %
                                 (KM2002.name(km.iloc[i])))
            if stund.iloc[i] >= 12 and stund.iloc[i] <= 15 and km.iloc[i] < k['V']:
                if ecc.iloc[i] <= 0.625:
                    km.iloc[i] = km.iloc[i] + 1
                    logger.debug('rule a.2      -> %4s' %
                                 (KM2002.name(km.iloc[i])))
        #
        # rule b)
        # For May (last climatological spring month) and
        # September (first climatological autumn month)
        # during the hours from 11:00 CET to 15:00 CET,
        # the next higher dispersion category should be
        # chosen for total cloud cover not exceeding 6/8.
        #
        elif monat.iloc[i] in [5, 9]:
            if stund.iloc[i] >= 11 and stund.iloc[i] <= 15:
                if ecc.iloc[i] <= 0.75:
                    km.iloc[i] = km.iloc[i] + 1
                    logger.debug('rule b        -> %4s' %
                                 (KM2002.name(km.iloc[i])))
        #
        # rule c)
        # For the period from one hour until three hours
        # after sunrise (SR+1 to SR+3) and from two
        # hours before until one hour after sunset (SS–2
        # to SS+1), the dispersion categories in accord-
        # ance with Table 2 are determined both for
        # nighttime (KN) and for daytime (KT) hours re-
        # gardless of a and b above. Table 3 contains all
        # possible combinations of the dispersion catego-
        # ries CN and CD, and shows which dispersion
        # category should be used instead.

        #
        # Table 3. Assignment of dispersion categories
        #          for hours around sunrise and sunset
        # | KN | KT | SA+1 | SA+2 | SU-2 | SU-1 | SU   |
        # | KN | KT | bis  | bis  | bis  | bis  | bis  |
        # |    |    | SA+2 | SA+3 | SU-1 | SU   | SU+1 |
        # | I  | IV |I(II)a|  II  |  II |II(I)b |I(II)a|
        # | I  |III2|  II  |  II  | III1 | III1 |I(II)a|
        # | II | IV |  II  | III1 | III1 |  II  |  II  |
        # | II |III2| III2 | III1 | III1 | III1 |  II  |
        # |III1| IV | III1 | III2 | III2 | III1 | III1 |
        # |III1|III2| III1 | III1 | III2 | III2 | III1 |
        # |III1|III1| III1 | III1 | III1 | III1 | III1 |
        #
        # a) For March to November (climatological spring,
        #    summer and autumn months) and wind speeds >= 1,3 m/s,
        #    use the dispersion category shown in parentheses.
        # b) For January, February and December (climatological
        #    winter months), wind speeds < 1,3 m/s and
        #    total cloud cover not exceeding 6/8,
        #    use the dispersion category shown in parentheses.
        #
        t3_fn = None
        t3_col = None
        if kn.iloc[i] == k['I'] and kt.iloc[i] == k['IV']:
            if stund.iloc[i] >= sr.iloc[i] + 1. and stund.iloc[i] < sr.iloc[i] + 2.:
                # footnote a)
                if (monat.iloc[i] in [3, 4, 5, 6, 7, 8, 9, 10, 11] and
                        ff.iloc[i] > 1.):
                    km.iloc[i] = k['II']
                    t3_fn = 'a'
                else:
                    km.iloc[i] = k['I']
            elif stund.iloc[i] >= sr.iloc[i] + 2. and stund.iloc[i] < sr.iloc[i] + 3.:
                km.iloc[i] = k['II']
            elif stund.iloc[i] >= ss.iloc[i] - 2. and stund.iloc[i] < ss.iloc[i] - 1.:
                km.iloc[i] = k['II']
            elif stund.iloc[i] >= ss.iloc[i] - 1. and stund.iloc[i] < ss.iloc[i]:
                # footnote b)
                if (monat.iloc[i] in [1, 2, 12] and ff.iloc[i] <= 1 and
                        ecc.iloc[i] <= 0.75):
                    km.iloc[i] = k['I']
                    t3_fn = 'b'
                else:
                    km.iloc[i] = k['II']
            elif stund.iloc[i] >= ss.iloc[i] and stund.iloc[i] < ss.iloc[i] + 1.:
                # footnote a)
                if (monat.iloc[i] in [3, 4, 5, 6, 7, 8, 9, 10, 11] and
                        ff.iloc[i] > 1):
                    t3_fn = 'a'
                    km.iloc[i] = k['II']
                else:
                    km.iloc[i] = k['I']
        elif kn.iloc[i] == k['I'] and kt.iloc[i] == k['III2']:
            if sr.iloc[i] + 1. <= stund.iloc[i] < sr.iloc[i] + 2.:
                km.iloc[i] = k['II']
            elif sr.iloc[i] + 2. <= stund.iloc[i] < sr.iloc[i] + 3.:
                km.iloc[i] = k['II']
            elif ss.iloc[i] - 2. <= stund.iloc[i] < ss.iloc[i] - 1.:
                km.iloc[i] = k['III1']
            elif ss.iloc[i] - 1. <= stund.iloc[i] < ss.iloc[i]:
                km.iloc[i] = k['III1']
            elif ss.iloc[i] <= stund.iloc[i] < ss.iloc[i] + 1.:
                # Fussnote *)
                if (monat.iloc[i] in [3, 4, 5, 6, 7, 8, 9, 10, 11] and
                        ff.iloc[i] > 1):
                    t3_fn = 'a'
                    km.iloc[i] = k['II']
                else:
                    km.iloc[i] = k['I']
        elif kn.iloc[i] == k['II'] and kt.iloc[i] == k['IV']:
            if sr.iloc[i] + 1. <= stund.iloc[i] < sr.iloc[i] + 2.:
                km.iloc[i] = k['II']
            elif sr.iloc[i] + 2. <= stund.iloc[i] < sr.iloc[i] + 3.:
                km.iloc[i] = k['III1']
            elif ss.iloc[i] - 2. <= stund.iloc[i] < ss.iloc[i] - 1.:
                km.iloc[i] = k['III1']
            elif ss.iloc[i] - 1. <= stund.iloc[i] < ss.iloc[i]:
                km.iloc[i] = k['II']
            elif ss.iloc[i] <= stund.iloc[i] < ss.iloc[i] + 1.:
                km.iloc[i] = k['II']
        elif kn.iloc[i] == k['II'] and kt.iloc[i] == k['III2']:
            if sr.iloc[i] + 1. <= stund.iloc[i] < sr.iloc[i] + 2.:
                km.iloc[i] = k['III1']
            elif sr.iloc[i] + 2. <= stund.iloc[i] < sr.iloc[i] + 3.:
                km.iloc[i] = k['III1']
            elif ss.iloc[i] - 2. <= stund.iloc[i] < ss.iloc[i] - 1.:
                km.iloc[i] = k['III1']
            elif ss.iloc[i] - 1. <= stund.iloc[i] < ss.iloc[i]:
                km.iloc[i] = k['III1']
            elif ss.iloc[i] <= stund.iloc[i] < ss.iloc[i] + 1.:
                km.iloc[i] = k['II']
        elif kn.iloc[i] == k['III1'] and kt.iloc[i] == k['IV']:
            if sr.iloc[i] + 1. <= stund.iloc[i] < sr.iloc[i] + 2.:
                km.iloc[i] = k['III1']
            elif sr.iloc[i] + 2. <= stund.iloc[i] < sr.iloc[i] + 3.:
                km.iloc[i] = k['III2']
            elif ss.iloc[i] - 2. <= stund.iloc[i] < ss.iloc[i] - 1.:
                km.iloc[i] = k['III2']
            elif ss.iloc[i] - 1. <= stund.iloc[i] < ss.iloc[i]:
                km.iloc[i] = k['III1']
            elif ss.iloc[i] <= stund.iloc[i] < ss.iloc[i] + 1.:
                km.iloc[i] = k['III1']
        elif kn.iloc[i] == k['III1'] and kt.iloc[i] == k['III2']:
            if sr.iloc[i] + 1. <= stund.iloc[i] < sr.iloc[i] + 2.:
                km.iloc[i] = k['III1']
            elif sr.iloc[i] + 2. <= stund.iloc[i] < sr.iloc[i] + 3.:
                km.iloc[i] = k['III1']
            elif ss.iloc[i] - 2. <= stund.iloc[i] < ss.iloc[i] - 1.:
                km.iloc[i] = k['III2']
            elif ss.iloc[i] - 1. <= stund.iloc[i] < ss.iloc[i]:
                km.iloc[i] = k['III2']
            elif ss.iloc[i] <= stund.iloc[i] < ss.iloc[i] + 1.:
                km.iloc[i] = k['III1']
        elif kn.iloc[i] == k['III1'] and kt.iloc[i] == k['III1']:
            if sr.iloc[i] + 1. <= stund.iloc[i] < sr.iloc[i] + 2.:
                km.iloc[i] = k['III1']
            elif sr.iloc[i] + 2. <= stund.iloc[i] < sr.iloc[i] + 3.:
                km.iloc[i] = k['III1']
            elif ss.iloc[i] - 2. <= stund.iloc[i] < ss.iloc[i] - 1.:
                km.iloc[i] = k['III1']
            elif ss.iloc[i] - 1. <= stund.iloc[i] < ss.iloc[i]:
                km.iloc[i] = k['III1']
            elif ss.iloc[i] <= stund.iloc[i] < ss.iloc[i] + 1.:
                km.iloc[i] = k['III1']

        if sr.iloc[i] + 1. <= stund.iloc[i] < sr.iloc[i] + 2.:
            t3_col = 'SA+1/SA+2'
        elif sr.iloc[i] + 2. <= stund.iloc[i] < sr.iloc[i] + 3.:
            t3_col = 'SA+2/SA+3'
        elif ss.iloc[i] - 2. <= stund.iloc[i] < ss.iloc[i] - 1.:
            t3_col = 'SU-2/SU-1'
        elif ss.iloc[i] - 1. <= stund.iloc[i] < ss.iloc[i]:
            t3_col = 'SU-1/SU'
        elif ss.iloc[i] <= stund.iloc[i] < ss.iloc[i] + 1.:
            t3_col = '  SU/SU+1'
        if t3_col is not None:
            logger.debug('rule c tab 3:')
            if t3_fn is not None:
                logger.debug('footnote (%2a) :' % t3_fn)
            logger.debug('col: %9a-> %4s' % (t3_col, KM2002.name(km.iloc[i])))
        #
        # part d)
        # For December, January and February (climato-
        # logical winter months), dispersion category IV
        # should be replaced by III/2.
        #
        if monat.iloc[i] in [1, 2, 12]:
            if km.iloc[i] == k['IV']:
                km.iloc[i] = k['III2']
                logger.debug('rule d        -> %4s' % (KM2002.name(km.iloc[i])))

    # Missing total cloud cover
    #
    # If, due to a missing total cloud cover, it is impossi-
    # ble to determine a dispersion category in accordance
    # with Section 4.3, the dispersion category can be
    # determined alternatively in accordance with Ta-
    # ble 4.
    #
    # Table 4. Dispersion category in the absence of total cloud cover
    #
    # |Wind speed at 10m|  Time interval: later than ...|
    # |height (z0=0.1m) |  SS   | SR+1  |  SR+3 | SS-2  |
    # |                 | until | until | until | until |
    # |in m s^-1        | SR+1  | SR+3  |  SS-2 |  SS   |
    # | <= 2.3          |   I   |   II  |  III2 | III1  |
    # | 2.4 to 3.3      |   II  |  III1 |  III2 | III1  |
    # | >= 3.3          |  III1 |  III1 |  III1 | III1  |
    #
    for i, t in enumerate(time):
        if pd.isna(km.iloc[i]):
            logger.debug('missing tcc %s, ff: %4.1f' % (t, ff.iloc[i]))
            if not daytime.iloc[i] or stund.iloc[i] <= sr.iloc[i] + 1.:
                logger.debug('  -> Table 4 col 1')
                if ff.iloc[i] <= 2.3:
                    km.iloc[i] = k['I']
                elif ff.iloc[i] <= 3.3:
                    km.iloc[i] = k['II']
                else:  # km.iloc[i] >= 3.3
                    km.iloc[i] = k['III1']
            elif sr.iloc[i] + 1. < stund.iloc[i] <= sr.iloc[i] + 3.:
                logger.debug('  -> Table 4 col 2')
                if ff.iloc[i] <= 2.3:
                    km.iloc[i] = k['II']
                elif ff.iloc[i] <= 3.3:
                    km.iloc[i] = k['III1']
                else:  # km.iloc[i] >= 3.3
                    km.iloc[i] = k['III1']
            elif ss.iloc[i] - 2. < stund.iloc[i] <= ss.iloc[i]:
                logger.debug('  -> Table 4 col 4')
                if ff.iloc[i] <= 2.3:
                    km.iloc[i] = k['III1']
                elif ff.iloc[i] <= 3.3:
                    km.iloc[i] = k['III1']
                else:  # km.iloc[i] >= 3.3
                    km.iloc[i] = k['III1']
            else:  # daytime and >3 after sr and >2 before ss
                logger.debug('  -> Table 4 col 3')
                if ff.iloc[i] <= 2.3:
                    km.iloc[i] = k['III2']
                elif ff.iloc[i] <= 3.3:
                    km.iloc[i] = k['III2']
                else:  # km.iloc[i] >= 3.3
                    km.iloc[i] = k['III1']

    logger.debug('return value  -> %s' % str([KM2002.name(x) for x in km]))
    if scalar:
        km = km[0]
    else:
        km = np.array(km)
    return km


# ----------------------------------------------------

def klug_manier_scheme(*args, **kwargs):
    """
    shorthand for the currently valid version of the
    Klug/Manier scheme
    :meth:`austaltools._dispersion.klug_manier_scheme_2017`
    """
    return klug_manier_scheme_2017(*args, **kwargs)


# =============================================================================

def pasquill_taylor_scheme(time, ff, tcc, lat, lon, ceil):
    """
    Calulate stability class after Pasquill and Turner [EPA2000]_

    ========== ================= =======
      Category  Atmospheric        Index
                stability
    ========== ================= =======
      I         very stable         1
      II        stable              2
      III/1     neutral/stable      3
      III/2     neutral/unstable    4
      IV        unstable            5
      V         very unstable       6
    ========== ================= =======

    The norm states:
      Strictly speaking, the above correction conditions apply
      only to locations in Central Europe with a pronounced
      seasonal climate and sunrise and sunset times definable over the
      whole year, which in particular during the winter months
      always exhibit a time difference exceeding six hours. These
      conditions are met in Germany. For other countries, CET
      should be replaced where relevant by the corresponding zone-
      time. In climatic zones with diurnal climate or other calendar
      classifications of astronomical seasons, the correction
      conditions are not directly applicable in the above form. Adaptation
      of subsections a to d for other global climatic zones does not
      form a part of this standard.

    :param time: (required, time-like)
        An arbitrary time during the day of year for which
        surise and sunset should be calculated.
        May be supplied as any form accepted by `pandas.to_datetime()`,
        e.g. timestamp (`"2000-12-14 18:00:00"`) or datetime64.
        If timezone is not supplied, UTC is assumed.
        If timezone is supplied, time is converted to CET.
    :param ff: (required, float)
        wind speed in 10m height.
    :param tcc: (required, float)
        total cloud cover as fraction of 1
        (equals value in octa divided by 8).
    :param lat: (required, float) latitude in degrees.
        Southern latitudes must be nagtive.
    :param lon: (required, float) longitude in degrees.
        Eastern longitudes are positive,
        western longitudes are negative.
    :param ceil: (required, float) cloud base height in m.

    :return: class value (numeric index)
    :rtype: `int` if `time` is a scalar,
        `pandas.Series(int64)` if `time` is array-like.
    """
    # if arguments are scalars, convert to arrays
    if pd.api.types.is_scalar(time):
        scalar = True
        time = pd.DatetimeIndex([time])
        ff = pd.Series(ff)
        tcc = pd.Series(tcc)
        ceil = pd.Series(ceil)
    else:
        scalar = False
        time = pd.DatetimeIndex(time)

    logger.debug('pasquill_taylor_scheme ---> %19s ...' % (time[0]))

    # auf/unter UTC
    s_rise, _, s_set = m.radiation.fast_rise_transit_set(time, lat, lon)
    s_ele, _ = m.radiation.fast_sun_position(time, lat, lon)
    pt = pd.Series(np.nan, index=range(len(time)))
    for i in range(len(time)):
        logger.debug('surise,sunset,elevation : (%f, %f) %f)' %
                     (s_rise.iloc[i], s_set.iloc[i], s_ele.iloc[i]))
        rad_index = -999
        insolation_class = -999
        #
        # 1. If the total cloud1 cover is 10/10 and the ceiling is
        #   less than 7000 feet, use net radiation index equal to 0
        #   (whether day or night).
        if tcc.iloc[i] > 0.9 and ceil.iloc[i] <= (7000 * 0.3048):
            rad_index = 0

        # 2. For nighttime:
        #   (from one hour before sunset to one hour after sunrise):
        #  (a) If total cloud cover < 4/10, use net radiation index -2.
        #  (b) If total cloud cover > 4/10, use net radiation index -1.
        elif s_ele.iloc[i] < 0.:
            if tcc.iloc[i] <= 0.4:
                rad_index = -2
            else:
                rad_index = -1
        #
        # 3. For daytime:
        else:
            # (a) Determine the insolation class number as a function of
            #   solar altitude from Table 6-5.
            insolation_class = taylor_insolation_class(s_ele.iloc[i])

            # (b) If total cloud cover <5/10, use the net radiation index
            #   in Table 6-4 corresponding to the isolation class number.
            if tcc.iloc[i] < 0.5:
                rad_index = insolation_class

            # (c) If cloud cover >5/10, modify the insolation class number
            #   using the following six steps.
            else:
                # (1) Ceiling <7000 ft, subtract 2.
                if ceil.iloc[i] <= (7000 * 0.3048):
                    mod_ins_class = insolation_class - 2

                # (2) Ceiling >7000 ft but <16000 ft, subtract 1.
                elif (7000 * 0.3048) < ceil.iloc[i] < (16000 * 0.3048):
                    mod_ins_class = insolation_class - 1

                # (3) total cloud cover equal 10/10, subtract 1.
                #    (This will only apply to ceilings >7000 ft
                #     since cases with 10/10 coverage below 7000 ft
                #     are considered in item 1 above.)
                elif tcc.iloc[i] > 0.9:
                    mod_ins_class = insolation_class - 1

                # (4) If insolation class number has not been modified by
                #    steps (1), (2), or (3) above, assume modified
                #    class number equal to insolation class number.
                else:
                    mod_ins_class = insolation_class

                # (5) If modified insolation class number is less than 1,
                #    let it equal 1.
                if mod_ins_class < 1:
                    mod_ins_class = 1

                # (6) Use the net radiation index in Table 6-4
                #   corresponding to the modified insolation class number.
                rad_index = mod_ins_class

        logger.debug('tcc, insolation_class, rad_index: %f, %i, %i' % (
            tcc.iloc[i], insolation_class, rad_index))
        # use index in Table 6-4
        pt.iloc[i] = turners_key(ff.iloc[i], rad_index)

        # For EPA regulatory modeling applications, stability categories
        # 6 and 7 (F and G) are combined and considered category 6.
        if pt.iloc[i] > 6:
            pt.iloc[i] = 6

    pt = 7 - pt  # turn class values around to match K/M
    if scalar:
        pt = pt.iloc[0]
    else:
        pt = np.array(pt)
    return pt


def turners_key(ff: float, NRI:int) -> int:
    """
    Returns the P-G stability class matching a
    wind speed class and net radiation index
    [EPA2000]_

    :param ff: wind speed in m/s
    :type ff: float
    :param NRI: net radiation index
    :type NRI: int
    :return: P-G stability class as number (1=A, 2=B,...)
    :rtype: int
    """
    ff = _check('ff', ff, 'float', ge=0.)
    NRI = _check('NRI', NRI, 'int', ge=-2, le=4)
    #                 Table 6-4
    #
    #  Turner's Key to the P-G Stability Categories
    #  Wind Speed      Net Radiation Index
    #  (knots) (m/s)    4   3   2   1   0  -1  -2
    #  0,1    0 - 0.7   1   1   2   3   4   6   7
    #  2,3  0.8 - 1.8   1   2   2   3   4   6   7
    #  4,5  1.9 - 2.8   1   2   3   4   4   5   6
    #  6    2.9 - 3.3   2   2   3   4   4   5   6
    #  7    3.4 - 3.8   2   2   3   4   4   4   5
    #  8,9  3.9 - 4.8   2   3   3   4   4   4   5
    #  10   4.9 - 5.4   3   3   4   4   4   4   5
    #  11   5.5 - 5.9   3   3   4   4   4   4   4
    # >12   6.0 -       3   4   4   4   4   4   4
    #
    # 1) select wind-speed class:
    if ff <= 0.7:
        vals = [1, 1, 2, 3, 4, 6, 7]
    elif ff <= 1.8:
        vals = [1, 2, 2, 3, 4, 6, 7]
    elif ff <= 2.8:
        vals = [1, 2, 3, 4, 4, 5, 6]
    elif ff <= 3.3:
        vals = [2, 2, 3, 4, 4, 5, 6]
    elif ff <= 3.8:
        vals = [2, 2, 3, 4, 4, 4, 5]
    elif ff <= 4.8:
        vals = [2, 3, 3, 4, 4, 4, 5]
    elif ff <= 5.4:
        vals = [3, 3, 4, 4, 4, 4, 5]
    elif ff <= 5.9:
        vals = [3, 3, 4, 4, 4, 4, 4]
    else:
        vals = [3, 4, 4, 4, 4, 4, 4]
    #
    # 2) select net-radiation index:
    ri = [4, 3, 2, 1, 0, -1, -2]
    for i, ri in enumerate(ri):
        if NRI == ri:
            key = vals[i]
            break
    else:
        raise ValueError('illegal NRI value: %i' % NRI)
    return key


def taylor_insolation_class(solar_altitude):
    #                 Table 6-5
    #  Insolation Class as a Function of Solar Altitude
    #  Solar Altitude X (degrees)   Insolation   Insolation Class Number
    #    60 < X                      strong       4
    #    35 < X <= 60                moderate     3
    #    15 < X <= 35                slight       2
    #         X <= 15                weak         1
    if solar_altitude <= 15:
        res = 1
    elif solar_altitude <= 35:
        res = 2
    elif solar_altitude <= 60:
        res = 3
    else:
        res = 4
    return res


# ========================================================================

def obukhov_length(ust, rho, Tv, H, E, Kelvin=None):
    """
    Returns the Obuhkov lenght [GOL1972]_ from surface values
    of air density, virtual temperature, latent and sensible
    heat-flux density.

    :param ust: friction velocity in m/s.
    :type ust: pandas.Series or float
    :param rho: density of air kg/m^3.
    :type rho: pandas.Series or float
    :param Tv:  virtual temperature in K or C, depending on `Kelvin`.
    :type Tv: pandas.Series or float
    :param H:   surface sensible heat flux density in W/m^2.
    :type H: pandas.Series or float
    :param E:   surface latent heat flux density in W/m^2.
    :type E: pandas.Series or float
    :param Kelvin: (optional)
      If ``False``, all temperatures are assumed to
      be Kelvin. If ``False``, all temperatures are assumed to be Celsius.
      If missing of ``None``, unit  temperatures are autodetected.
      Defaults to ``None``.

    """

    TvK = [m.temperature._to_K(x, Kelvin) for x in np.array(Tv)]
    L = np.array(-(ust ** 3 * TvK * rho * 1004.) /
                 (kappa * gn * (H + 0.06 * E)))

    return L[()]  # Flatten 0d arrays to scalars


# ----------------------------------------------------

def h_eff(has, z0s):
    """
    Calculate effective anemometer heights for all nine
     z0 class values used by AUSTAL [AST31]_
     from the actual height of the wind measurement

    :param has: actual height of the wind measurement
    :type has: pandas.Series of float
    :param z0s: roughness lenght at the position of the wind measurement
    :type z0s:  pandas.Series of float
    :return: height for nine roughness lenght at the model position
      ordered from the smallest to the lagrest roughness length
    :rtype: list[float]

    :note: The effective roughness height is the height where
      the same wind speed would be measured considering the roughness
      at the model site as it is measured by a nearby the anemometer
      that is mounted at height `has` on a site where the roughness is
      `z0s`
    """
    z0_vals = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1., 1.5, 2]
    href = 250
    d0s = m.wind.DISPLACEMENT_FACTOR * z0s
    ps = np.log((has - d0s) / z0s) / np.log((href - d0s) / z0s)
    ha = []
    for z0 in z0_vals:
        d0 = m.wind.DISPLACEMENT_FACTOR * z0
        ha.append(d0 + z0 * ((href - d0) / z0) ** ps)
    return ha


# ----------------------------------------------------

def z0_verkaik(z, speed, gust, dirct, rose=False):
    """
    Calculates an estimate for the roughness lentgh of a site
    from the gustiness of the wind, according to the Method
    by Verkaik (as used by Koßmann and Namyslo [KoNa2019]_.

    :param z: height of the wind measurement in meters
    :type z: float, list or pandas.Series
    :param speed:
    :type speed:
    :param gust:
    :type gust: float, list or pandas.Series
    :param dirct:
    :type dirct: float, list or pandas.Series
    :param rose: If `True` individual values of roughness length in m
      and number of intervals when the wind cam from this sector.
      are returned for 12 wind-direction sectors (clockwise from north).
      If `False` one mean roughness lenght value in m
      for the site is returned.
      Default is `False`.
    :type rose: bool
    :return: roughness lenght either as mean or as sector-wise value(s)
    :rtype: float or tuple[list,list], depending on `rose`
    """
    df = pd.DataFrame({'u_m': speed, 'u_x': gust, 'd': dirct})
    #
    # Verkaik - method
    #
    # condition u=umin
    umin = 5  # Kossmann & Namyslo (2019) Glg 13
    cond1 = [x for x in df['u_m'] > umin]
    #
    # condition sigma/<u> < 0.5*Ab
    # Ab   = 0.9  # Kossmann & Namyslo (2019) Tab 2
    # cond2 = [x for x in (v['???']/df['u'] < (0.5 * Ab))]
    # no sigma =>
    cond2 = True
    #
    ok = np.logical_and(cond1, cond2)
    # hourly gustiness factor
    df['Gm'] = df['u_x'] / df['u_m']  # u_max_m/<u_m>
    # mean gustiness factor per sector
    Gm_sec = df['Gm'][ok].groupby(by=(df['d'][ok] + 15) % 360 // 30).mean()
    N_sec = df['Gm'][ok].groupby(by=(df['d'][ok] + 15) % 360 // 30).count()

    #
    B = 6  # VDI 3783-8, Kap. 7: wird für B der Wert "6" gesetzt
    C = 2.4  # VDI 3783-8, Kap. 6.3: C=2,4 stündlich gemittelte Winddaten
    Aw = 0.9  # Kossmann & Namyslo (2019) Tab 2 after Beljaars (1987)
    ux = 2.99  # = uxc aus Benschop und van der Meulen (2009)
    z0_sec = z / (np.exp(ux * (Aw * C * kappa) / (Gm_sec - 1)) + B)

    # make sure values for every sector exist:
    z0i = pd.DataFrame(np.nan, index=[1],
                       columns=[str(int(x * 30)) for x in range(12)])
    N = z0i.copy()
    for x in z0_sec.index:
        sec = str(int(x * 30))
        z0i.loc[1, sec] = z0_sec[x]
        N.loc[1, sec] = N_sec[x]

    # calculate "station value"
    z0 = np.nansum(z0_sec * N_sec) / np.nansum(N_sec)
    logger.debug("mean roughness length (Verkaik): %5f" % (z0))

    if rose:
        return z0i, N
    else:
        return z0
