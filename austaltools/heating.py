#!/usr/bin/env python3
import csv
import sys
from collections import OrderedDict
import inspect
import logging
import os
import re

import numpy as np
import pandas as pd

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import meteolib as m
    import yaml
    from tqdm import tqdm

try:
    from . import _common
    from . import _tools
except ImportError:
    import _common
    import _tools

# ----------------------------------------------------

logging.basicConfig()
logger = logging.getLogger()

# ----------------------------------------------------


if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    cp = m.constants.cp

SOIL_EPSILON = 0.80
""" soil surface default spectral emissivity in 1,
 for dry soil, also for a mixture of forest and fields, see [Tah1992]_ """
SOIL_ALBEDO = 0.15
""" soil surface default albedo in 1, 
typical values form Central Europe mixed vegetation after [SSS2016]_ """
WALL_EPSILON = 0.95
""" wall default spectral emissivity in 1,
 for brick as well as grey to white paint from [Tah1992]_ """
WALL_ALBEDO = 0.45
""" soil surface default albedo in 1, 
median value for typical European building materials after [Tah1992]_ """
DEFAULT_SLABS_OPT = 'even'
""" default scheme how walls are partitioned into slabs """
DEFAULT_SLAB = 0.04
""" wall slab default thickness in m """
WIDTHMIN = 0.01
""" wall slab minimal thickness for exponentially growing slabs in m """
WIDTHSTEP = 0.005
""" wall slab thickness steps for exponentially growing slabs in m """
WIDTHEXP = 2.
""" all slab thickness max exponent (>1)"""
TIMESTEP = 1
""" model timestep in s """
PRESSURE = 101325
""" ambient air pressure in Pa """
DEFAULT_WIND = 3.0
""" default wind speed in m/s 
mean 10-m wind speed for Europe (https://www.eea.europa.eu/publications/
europes-changing-climate-hazards-1/wind/wind-mean-wind-speed) """
DEFAULT_COVER = 8. * 0.6
""" default cloud cover in octa 
mean value the 1991–2020 reference period 
(https://climate.copernicus.eu/esotc/2022/clouds-and-sunshine-duration) """
HEATING_LIMIT = 15  # °C
DEFAULT_ROOMTEMP = 20  # °C

# ------------------------------------------------

_ROOM_DEFAULT = '_default'

# ------------------------------------------------

def surface_heat_transfer_resistance(
        indoor: bool, angle: float = 0,
        t_wall:float=None, wind:float=None):
    r"""
    Calculate heat transfer resistance between wall and air.

    :param indoor: Surface is indoor (`True`) or outdoor (`False`)
    :type indoor: bool
    :param angle: Elevation angle of the wall normal direction.
      0 means the wall is vertical. +90 means the wall is a floor.
      -90 a ceiling.
    :type angle: float
    :param t_wall: wall surface temperature in °C
    :type t_wall: float
    :param wind: wind speed
    :type wind: float
    :return: heat transfer resistance in :math:`m^2 K / W`
    :rtype: float

    Commonly H is parameterized as:
    :math:`H = C_\mathrm{H} \left( T_\mathrm{sfc} - \mathrm{air}\right)`
    or in resistance notation:
    :math:`R_\mathrm{H} = \frac{ T_\mathrm{sfc} - \mathrm{air}}{H}`
    where :math:`C_\mathrm{H} = \frac{1}{R_\mathrm{H}}`

    DIN 6946:2008 appendix A.1 "even surface" states
    :math:`R_\mathrm{S} = \frac{1}{h_\mathrm{c} + h_\mathrm{r}}`

    with:
      - :math:`h_\mathrm{c}`: heat transfer coefficient due to convection
      - :math:`h_\mathrm{r}`: heat transfer coefficient due to radiation

    values in case of a "well ventilated" indoor surfaces:
    :math:`h_\mathrm{c} ~=~ h_\mathrm{ci}`
    with

      - :math:`h_\mathrm{ci} ~=~ 5.0 \mathrm{W}/(\mathrm{W}^2 \mathrm{K})`
        for heat flow upwards (i.e. from the floor);
      - :math:`h_\mathrm{ci} ~=~ 2.5 \mathrm{W}/(\mathrm{W}^2 \mathrm{K})`
        for heat flow horizontal (i.e. from a wall);
      - :math:`h_\mathrm{ci} ~=~ 0.7 \mathrm{W}/(\mathrm{W}^2 \mathrm{K})`
        for heat flow downwards (i.e. from the ceiling)

    values in case of outdoor surfaces:
    :math:`h_\mathrm{c} ~=~ h_\mathrm{ce}`

    with
    :math:`h_\mathrm{ce} ~=~ 4. + 4. v \mathrm{W}/(\mathrm{W}^2 \mathrm{K})`

    where :math:`v` is the wind speed ''above he surface'' in m/s

    """
    #

    if wind in [None, np.nan]:
        # no wind -> only wall convection
        # DIN EN ISO 6946:2008-04 Table 1
        # set r_s
        if indoor:
            if angle > 30.:
                r_s = 0.10
            elif angle < -30.:
                r_s = 0.17
            else:
                r_s = 0.13
        else:
            r_s = 0.04
    else:
        # set r_s = 1/(h_c + h_r)
        if indoor:
            # hc = h_ci(wall direction)
            # no wind -> only wall convection
            # even surfaces:
            # DIN EN ISO 6946:2008-04 Table A.1
            h_ci_up = 5.0  # W/m²K
            h_ci_ho = 2.5  # W/m²K
            h_ci_dn = 0.7  # W/m²K
            # select value by wall-normal elevation angle
            if angle > 45:
                h_c = h_ci_up
            elif angle < -45:
                h_c = h_ci_dn
            else:
                h_c = h_ci_ho
        else:
            # hc = h_ce(wind speed)
            # wind "above wall" (no distance etc. defined !!?!)
            h_c = 4.0 + 4.0 * wind
        # h_r ((longwave) radiative transfer)
        h_r = (WALL_EPSILON *
               4 * m.constants.sigma * m.temperature.CtoK(t_wall))

        # DIN EN ISO 6946:2008-04 eqn 1.1:
        # R = 1/(h_r+h_c)
        r_s = 1. / (h_c + h_r)

    return r_s


# ------------------------------------------------

def surface_net_radiation(time: pd.Timestamp, lat: float, lon: float,
                          t_wall: float, t_air: float,
                          heading: float, slant: float,
                          octa: float,
                          albedo: float = None,
                          epsilon: float = None,
                          components: bool = False,
                          ) -> float | tuple[
                                float, float, float, float]:
    """
    Calculate the surface radiation budget for a specified wall.

    This function computes the net radiation budget of a
    vertical or slanted surface at a particular location and time,
    considering both shortwave and longwave radiation components.

    :param time: Time for which the calculation is made.
    :type time: pd.Timestamp
    :param lat: Latitude of the location in degrees.
    :type lat: float
    :param lon: Longitude of the location in degrees.
    :type lon: float
    :param t_wall: Temperature of the wall surface in degrees Celsius.
    :type t_wall: float
    :param t_air: Air temperature in degrees Celsius.
    :type t_air: float
    :param heading: Orientation angle of the wall normal
      with respect to north in degrees.
    :type heading: float
    :param slant: Slant angle of the wall from horizontal
      in degrees upward.
    :type slant: float
    :param octa: Cloud cover in oktas,
      an integer from 0 (clear sky) to 8 (completely overcast).
    :type octa: float
    :param albedo: Surface albedo of the wall,
      default is set to WALL_ALBEDO if None.
    :type albedo: float, optional
    :param epsilon: Emissivity of the wall surface,
      default is set to WALL_EPSILON if None.
    :type epsilon: float, optional
    :param components: If True, returns the individual
      radiation components, otherwise returns the net radiation.
    :type components: bool, optional

    :return: Net radiation (or individual components if requested),
      consisting of shortwave and longwave calculation terms.
    :rtype: float or tuple[float]

    :raises ValueError: If the input values are out of expected ranges.

    .. note::
        This function uses the simplified Kasten and Czeplak [Kas1980]_
        model for clear-sky conditions with adjustments for cloud cover.
    """

    # insert default values
    if albedo is None:
        albedo = WALL_ALBEDO
    if epsilon is None:
        epsilon = WALL_EPSILON

    # abbreviation for Stefan-Boltzmann law
    def _sboltz(t_c):
        return m.constants.sigma * m.temperature.CtoK(t_c) ** 4

    # sky view factor / soil view factor
    f_sky = (np.pi - 2 * np.deg2rad(slant)) / (2 * np.pi)
    f_soil = (np.pi + 2 * np.deg2rad(slant)) / (2 * np.pi)

    # get sun position
    ele, azi = m.radiation.fast_sun_position(time, lat, lon)

    # convert angles to radians
    rele = np.deg2rad(ele)
    razi = np.deg2rad(azi)
    rhdg = np.deg2rad(heading)
    rsla = np.deg2rad(slant)

    # calculate angular distance between sun and wall normal
    dele = rele - rsla
    dazi = razi - rhdg
    d = (np.sin(dele * 0.5) ** 2
         + np.cos(rsla) * np.cos(rele) * np.sin(dazi * 0.5) ** 2)
    theta = 2. * np.arcsin(np.sqrt(d))

    # get clear-sky irradiance
    i_dir, i_diff = m.radiation.shortwave_incoming(
        time, lat, lon, heading, slant, albedo=SOIL_ALBEDO)

    # clearness index after Kasten and Czeplak (1980)
    k_clear = 1. - 0.75 * (octa/8.) ** 3.4

    # shortwave incoming radiation (direct + diffuse)
    k_in = np.cos(theta) * k_clear * i_dir + f_sky * k_clear * i_diff

    # shortwave outgoing (reflected) radiation
    k_out = albedo * k_in

    # get longwave sky radiation
    l_down = m.radiation.longwave_incoming(
        t_k=m.temperature.CtoK(t_air),
        e=m.humidity.esat_w(t=t_wall, Kelvin=False, hPa=False)* 0.5)

    # incoming longwave radiation
    l_in = f_sky * l_down + f_soil * SOIL_EPSILON * _sboltz(t_air)

    # outgoing longwave radiation
    l_out = epsilon * _sboltz(t_wall)

    # sum up net radiation
    q = k_in - k_out + l_in - l_out

    if components:
        return k_in, k_out, l_in, l_out
    else:
        return q


# ------------------------------------------------

def exponential_slabs(dist):
    """
    Function to partition distance `dist` into the minimal set of intervals
    that grow approximately exponentially from the edge to the middle,
    are multiples of `WIDTHSTEP` (except the two in the center two),
    have a minimal width of `WIDTHMIN` and
    are symmetrical around the center of L.

    :param dist: distance  to patition
    :type dist: float
    :return: interval widths
    :rtype: list
    """
    # Check that the distance L is within valid range
    if dist < 0.:
        raise ValueError("distance is less than zero")

    if dist < WIDTHMIN:
        res = [dist]
    elif dist < 2. * WIDTHMIN:
        res = [dist / 2.] * 2
    else:
        res = None

        # Initial number of partitions on one side
        minl = 2 * WIDTHMIN
        n = int(np.ceil(dist / minl))
        number = n + 1

        # Iterate until a satisfactory partition is found
        for g in np.linspace(1., WIDTHEXP, 200):
            widths = [WIDTHMIN * g ** i for i in range(n)]

            # Reduce n if we overshoot
            for i in range(len(widths)):
                if np.sum(widths[:i]) > dist/2.:
                    widths = widths[:i]
                    break

            # Check for interval multiples of 0.5
            widths = [round(x / WIDTHSTEP) * WIDTHSTEP for x in widths]

            # Calculate sum and compare to half of L
            r = sum(widths) - dist / 2
            if len(widths) < number and abs(r) <= WIDTHSTEP:
                widths[-1] -= r
                res = widths + widths[::-1]

        if res is None:
            raise RuntimeError("could not partition distance")

    return res

# ------------------------------------------------


class Wall:
    r"""
    Represents a wall element within a building, handling thermal dynamics
    between two rooms (room_w and room_c).

    :param name: The name of the wall.
    :type name: str
    :param d: The thickness of the wall in meters.
    :type d: float
    :param room_w: Name of the room on the warmer side of the wall.
    :type room_w: str
    :param room_c: Name of the room on the cooler side of the wall.
    :type room_c: str
    :param l: The length of the wall in meters, optional.
    :type l: float, optional
    :param h: The height of the wall in meters, optional.
    :type h: float, optional
    :param area: The full area of the wall in square meters, optional.
    :type area: float, optional
    :param c: The heat capacity of the wall material in J/kgK, optional.
    :type c: float, optional
    :param k: The thermal conductivity of the wall material in W/mK, optional.
    :type k: float, optional
    :param rho: The density of the wall material in kg/m³, optional.
    :type rho: float, optional
    :param partof: Indicates what part of the building the wall belongs to, optional.
    :type partof: str, optional
    :param t_start: Starting temperature for the wall slabs in degrees Celsius, optional.
    :type t_start: float, optional

    Definition of positive flux:

    room_w (warm)    ->         positive flux            -> room_c (cold)

    The wall consists of slabs and flux nodes for thermal calculations:

    The grid is staggered like this:

    +--------+---+-----------+-+--------+-+-----+-+-----------+-+
    |        |   |  layer0   | | layer1 | | ... | |   layerN  | |
    +========+===+===========+=+========+=+=====+=+===========+=+
    | width  |   |   slab    | | slab   | | ... | |    slab   | |
    +--------+---+-----------+-+--------+-+-----+-+-----------+-+
    | temp   |   |    X      | |  X     | |  X  | |     X     | |
    +--------+---+-----------+-+--------+-+-----+-+-----------+-+
    | width  |   |   slab +  | |  slab  | | ... | |  slab +   | |
    |        |   |   excess  | |        | |     | |  excess   | |
    +--------+---+-----------+-+--------+-+-----+-+-----------+-+
    | flux   | X |           |X|        |X|     |X|           |X|
    +--------+---+-----------+-+--------+-+-----+-+-----------+-+

    **Surface heat fluxes**

    generally:
      :math:`Q_\mathrm{s} - B_\mathrm{s} - H_\mathrm{s} - E_\mathrm{s} = 0`

    indoor wall:
      Shortwave radiation fluxes are approximately zero;
      longwave radiative transfer included in surfac-to-atmosphere
      heat transfer coefficient, effecitvily making
      :math:`Q_\mathrm{s} = 0`.
      Walls are assumed to be dry making
      :math:`E_\mathrm{s} = 0`.

      Hence: :math:`- B_\mathrm{s} - H_\mathrm{s} = 0`

      Following DIN 6946, write
      :math:`H_\mathrm{s} = h_c (T_\mathrm{s} - T_\mathrm{air})`

      where :math:`T_\mathrm{s}` is the temperature of the surface.
      Because this model uses thin slabs, it
      can be approximated by the temperature of the outemost slab.

    outdoor wall:
      Shortwave radiation fluxes are significant;
      longwave radiative transfer is again included in
      surface-to-atmosphere heat transfer coefficient, effecitvily making
      :math:`Q_\mathrm{s} = K_\mathrm{s}`.

      Hence: :math:`K_\mathrm{s} - B_\mathrm{s} - H_\mathrm{s} = 0`

    **Class attributes**

        name : str
            The name of the wall.
        partof : str
            Indicates what part of the building the wall belongs to.
        thickness : float
            The thickness of the wall in meters (default is 0.36m).
        length : float
            The length of the wall in meters.
        height : float
            The height of the wall in meters.
        area_full : float
            The full area of the wall without any corrections
            in square meters.
        area : float
            The effective area of the wall, adjusted for embedded elements,
            in square meters.
        facing : float
            The horizontal orientation of the wall
            in degrees clockwise from north.
        slant : float
            The vertical orientation of the wall
            in degrees upward from horizontal.
        d_slab : float
            The thickness of each slab section in the wall in meters.
        n_slab : int
            The number of slab sections in the wall.
        t_slab : list
            List containing the temperature of each slab section
            in degrees Celsius.
        n_flux : int
            The number of flux nodes calculated across the wall.
        f_flux : list
            List containing the flux values at each node in watts
            per square meter.
        d_flux : list
            List containing the distance between slab centers used
            in flux calculations in meters.
        heat_conduct : float
            The thermal conductivity of the wall material
            in watts per meter kelvin (default is 0.58 W/mK).
        heat_capacity : float
            The heat capacity of the wall material
            in joules per kilogram kelvin (default is 836 J/kgK).
        density : float
            The density of the wall material
            in kilograms per cubic meter (default is 1400 kg/m³).
        albedo : float
            The albedo of the cold-side wall material in 1,
            defaults to WALL_ALBEDO
        epsilon : float
            The emissivity of the cold-side wall material in 1,
            defaults to WALL_EPSILON
        k_in, k_out, l_in, l_out: float, float, float, float
            The net radiation components on the cold-side wall surface:
            shortwave (solar) incoming, shortwave (solar) outgoing,
            longwave (infrared) incoming, longwave (infrared) outgoing,

    """
    TOLERANCE = 0.001
    """ allowed difference between sum ob slab thicknesses 
    and wall thickness """
    name = str()
    partof = str()
    thickness = .36  # m
    lenght = float()  # m
    height = float()  # m
    area_full = float()  # m²
    area = float()  # m²
    facing = float()  # deg clockwise from north
    slant = float() # deg, 0 = vertical wall, pos = cold side facing upwards
    d_slab = float()  # m
    n_slab = int()  # 1
    t_slab = list()  # °C
    n_flux = int()  # 1
    f_flux = list()  # W/m²
    d_flux = list()  # m
    # source: https://www.schweizer-fn.de/stoff/wleit_isolierung/wleit_isolierung.php
    heat_conduct = 0.58  # W/mK (brick wall)
    # source https://www.schweizer-fn.de/stoff/wkapazitaet/wkapazitaet_baustoff_erde.php
    heat_capacty = 836.  # J/kgK (brick wall)
    density = 1400  # kg/m³ (brick wall)
    albedo = None
    epsilon = None
    k_in = np.nan
    k_out = np.nan
    l_in = np.nan
    l_out = np.nan

    def __init__(self, name: str, d: float, room_w: str, room_c: str,
                 l: float = None, h: float = None, area: float = None,
                 facing: float = None, slant: float = None,
                 c: float = None, k: float = None, rho: float = None,
                 albedo: float = None, epsilon: float = None,
                 partof: str = None, t_start: float = None,
                 slabs: str|float|list = None):
        """
        Initialize a new Wall instance.

        """
        self.name = name
        logger.debug(f"initializing wall: {name}")
        self.room_w = room_w
        self.room_c = room_c
        if c is not None:
            self.heat_capacty = c
        if k is not None:
            self.heat_conduct = k
        if rho is not None:
            self.density = rho
        if l is not None and h is not None:
            self.lenght = l
            self.height = h
            self.area_full = l * h
        if area is not None:
            self.area_full = area
        # area is full area minus embeddded elements (corrected by WallList)
        self.partof = partof
        self.area = self.area_full
        # orientation:
        self.facing = facing if facing is not None else np.nan
        self.slant = slant if slant is not None else 0.
        # optical properties
        self.albedo = albedo if albedo is not None else WALL_ALBEDO
        self.epsilon = epsilon if epsilon is not None else WALL_EPSILON

        # calculate number of slabs
        self.thickness = d
        if slabs is None:
            # nothing selected -> default option
            slabs = DEFAULT_SLABS_OPT
        if slabs == 'even':
            # even selected -> select default width
            slabs = DEFAULT_SLAB
        if isinstance(slabs, str):
            if slabs == 'even':
                # we shouldn't be getting here
                raise RuntimeError('internal error in Wall.__init__')
            elif slabs == 'exponential':
                self.d_slab = exponential_slabs(d)
                self.n_slab = len(self.d_slab)
            else:
                raise ValueError(f"unknown slabs option: {slabs}")
        elif isinstance(slabs, float):
            # if d is a multiple of slabs (with some tolerance)
            self.n_slab = int(round(d/slabs))
            self.d_slab = [slabs] * self.n_slab
            excess = self.thickness % slabs
            self.d_slab[int(self.n_slab / 2.)] += excess
        elif isinstance(slabs, list):
            if not all([isinstance(i, float) for i in slabs]):
                raise ValueError(f"slabs option does non only contain "
                                 "floats: {str(slabs)}")
            # lower limit is WIDTHMIN
            if any([i < WIDTHMIN for i in slabs]):
                raise ValueError(f"slabs option contains negative or "
                                 "too small values: {str(slabs)}")
            #
            if abs(sum(slabs) - d) > self.TOLERANCE:
                raise ValueError(f"slabs option values do not add up "
                                 "to wall thickness: {str(slabs)}")
            self.d_slab = slabs
            self.n_slab = len(self.d_slab)
        else:
          raise ValueError(f"unknown slabs option: {str(slabs)}")
        logger.debug("slab sizes : %s cm" %
                     str([100*x for x in self.d_slab]))

        # calculate distances between slab centers for
        # flux calculation (add excess thickness at the two
        # outermost slabs)
        self.n_flux = self.n_slab + 1
        self.d_flux = self.n_flux * [np.nan]
        self.f_flux = self.n_flux * [np.nan]
        for i in range(self.n_flux):
            if i == 0:
                self.d_flux[i] = self.d_slab[0] / 2.
            elif i == self.n_flux - 1:
                self.d_flux[i] = self.d_slab[-1] / 2.
            else:
                self.d_flux[i] = (self.d_slab[i-1] + self.d_slab[i]) / 2.
        logger.debug("flux deltas: %s cm" %
                     str([100*x for x in self.d_flux]))

        # initialize temperature
        if t_start is None:
            raise ValueError('start temperature not given')
            # # assume linear temperature profile if no t_start is given
            # t_a = room_w.temp
            # t_b = room_c.temp
            # self.t_slab = [(t_b - t_a) / (self.n_slab + 1) * (x + 1)
            #                for x in range(self.n_slab)]
        else:
            # set alls slabs to have temperature t_start
            self.t_slab = self.n_slab * [t_start]

    def set_solar(self, time, lat, lon, octa, rooms):
        outdoor = self.room_c == 'outside'
        if not outdoor:
            self.k_in = self.k_out = self.l_in = self.l_out = np.nan
        else:
            t_air = rooms[self.room_c].temp
            t_wall = self.t_slab[-1]
            qtuple = surface_net_radiation(
                time, lat, lon, t_wall, t_air,
                self.facing, self.slant,
                octa, self.albedo, self.epsilon,
                components = True
            )
            self.k_in, self.k_out, self.l_in, self.l_out = qtuple
        
    def tick(self, rooms, timedelta=TIMESTEP):
        """
        Update the wall's state by advancing the simulation.

        :param rooms: A dictionary of room objects linked to the wall.
        :type rooms: dict
        :param timedelta: The duration by which the simulation advances, default is TIMESTEP.
        :type timedelta: float, optional
        """
        for i in range(self.n_flux):
            # temperature difference
            if i == 0:
                # warm wall surface
                dth = self.t_slab[0] - rooms[self.room_w].temp
                t_wall = self.t_slab[0]
                indoor = (rooms[self.room_w].name != 'outside')
                angle = - self.slant
                wind =  rooms[self.room_c].wind
                h_c = 1. / surface_heat_transfer_resistance(
                    indoor=indoor, angle=angle, t_wall=t_wall,
                    wind=wind
                )
            elif i == self.n_slab:
                # cold wall surface
                dth = rooms[self.room_c].temp - self.t_slab[i - 1]
                t_wall = self.t_slab[i - 1]
                indoor = (rooms[self.room_c].name != 'outside')
                # if indoor:
                #     q_net = 0.
                # else:
                #     q_net = surface_radiation_budget()
                angle = self.slant
                wind =  rooms[self.room_c].wind
                h_c = 1. / surface_heat_transfer_resistance(
                    indoor=indoor, angle=angle, t_wall=t_wall,
                    wind=wind
                )
                if all(np.isfinite(x) for x in (
                       self.k_in, self.k_out, self.l_in, self.l_out)):
                    h_c = h_c + (self.k_in - self.k_out +
                                 self.l_in - self.l_out)
            else:
                # inside wall
                dth = self.t_slab[i] - self.t_slab[i - 1]
                h_c = self.heat_conduct / self.d_flux[i]
            # heat flux
            self.f_flux[i] = - h_c *  dth
        for i in range(self.n_slab):
            diff = (self.f_flux[i] - self.f_flux[i + 1])
            dtdt = diff / (
                    self.density * self.d_slab[i] * self.heat_capacty)
            self.t_slab[i] += dtdt * timedelta
        return


class WallList(dict):
    """
    A class to manage a list of Room objects in a building simulation context,
    inheriting from Python's dictionary to map room names to Room instances.

    """
    def __setitem__(self, index, value: Wall):
        dict.__setitem__(self, index, value)
        if index != value.name:
            raise ValueError(f"key does not match name in {value.name}")
        for x in self.values():
            if x.partof is not None:
                if x.partof not in self.keys():
                    raise ValueError(
                        f"partof element not found in: {value.name}")
                if x.partof == x.name:
                    raise ValueError(
                        f"partof self found in: {value.name}")
                self[x.partof].area -= x.area
                if self[x.partof].area < 0:
                    raise ValueError(
                        f"parts larger than parent: "
                        f"{self[x.partof].name}")

    def append(self, wall: Wall):
        """
        Add a Wall instance to the WallList.

        :param wall: The Room instance to be added to the list.
        :type wall: Wall

        a ValueError is raised

        - if `wall` declares a parent wall via its `partof`
          attribute that is not already contained in the `WallList`
        - if `partof` attribute of `wall` refers to itself.
        - if `wall` declares a parent wall via its `partof`
          attribute whos area is not larger
       """

        self[wall.name] = wall
        
    def set_solar(self, time, lat, lon, octa, rooms):
        """
        set or update the solar ration upon external wall surfaces
        
        :param time: local time 
        :type time: pd.Timestamp
        :param lat: latitude in degrees
        :type lat:  float
        :param lon: longitude in degrees
        :type lon: float
        :param octa: cloud cover in octa (0: clear, 8: overcats)
        :type octa: float
        :param rooms: Room objects linked to the walls
        :type rooms: RoomList
        """
        for x in self.values():
            x.set_solar(time, lat, lon, octa, rooms)
    
    def tick(self, rooms, timedelta: float = TIMESTEP):
        """
        Advance the simulation state by a given time interval, updating each Room's state.

        :param rooms: Reference to room data necessary for updating the state of each wall.
        :param timedelta: The time step duration by which to advance the simulation, default is TIMESTEP.
        :type timedelta: float, optional
        """
        for x in self.values():
            x.tick(rooms, timedelta)


class Room:
    """
    Represents a room within a building simulation, capable of handling temperature and power dynamics.

    :param name: The name of the room.
    :type name: str
    :param width: The width of the room in meters, optional.
    :type width: float, optional
    :param length: The length of the room in meters, optional.
    :type length: float, optional
    :param height: The height of the room in meters, optional.
    :type height: float, optional
    :param maxpower: The maximum power that can be supplied to the room in watts.
    :type maxpower: float
    :param area: The area of the room in square meters, which can override width * length.
    :type area: float, optional
    :param volume: The volume of the room in cubic meters, which can override area * height.
    :type volume: float, optional
    :param t_set: The target temperature to be maintained in the room, optional.
    :type t_set: float, optional
    :param p_set: The target power setting for the room, optional.
    :type p_set: float, optional
    :param t_start: The starting temperature of the room, optional.
    :type t_start: float, optional
    :param special: Flag to indicate if the room is of a special type, optional.
    :type special: bool, optional

    :raises ValueError: If required parameters for normal rooms are not provided.

    **Class attributes**

        name : str
            The name of the room.
        temp : float
            The current temperature of the room in degrees Celsius.
        target_temp : float
            The target temperature for the room, default is NaN.
        target_power : float
            The target power setting for the room (1 represents 100%
            of `self.power`), default is NaN.
        maxpower : float
            The maximum power that can be supplied to the room in watts.
        power : float
            The current power being used by the room in watts.
        width : float
            The width of the room in meters.
        length : float
            The length of the room in meters.
        height : float
            The height of the room in meters.
        area : float
            The area of the room in square meters, which can override width * length.
        volume : float
            The volume of the room in cubic meters, which can override area * height.
        add_c : float
            Additional heat capacity by objects in the room, in Joules per Kelvin.
        wall_sign : dict
            Mapping of wall names to directional signs indicating their association with the room.

    """
    _special = False
    name = str()
    temp = float() # room air temperature in °C
    wind = float() # room "wind speed" in m/s
    target_temp = np.nan  # °C
    target_power = np.nan  # 1 (1= 100% of self.power)
    maxpower = float()  # W
    power = float()  # W
    width = float()  # m
    length = float()  # m
    height = float()  # m
    area = float()  # m² overrides width * lenght
    volume = float()  # m³ overrides area * height
    add_c = 0.  # J/K additional heat capacity by objects in the room
    wall_sign = {}

    def __init__(self, name, width=None, length=None, height=None,
                 maxpower=None, area=None, volume=None,
                 t_set=None, p_set=None, t_start=None, special=None):
        """
        Initialize a new Room instance.

        """
        self.name = name
        if special in [True,1,'yes','true']:
            self._special = True
            if t_start is None:
                self.temp = np.nan
            else:
                self.temp = t_start
            self.wind = np.nan
            self.target_temp = np.nan
            self.target_power = np.nan
            self.maxpower = 0.
            self.length = np.nan
            self.height = np.nan
            self.area = np.nan
            self.volume = 0.
        else:
            self._special = False
            if t_start is not None:
                self.temp = t_start
            else:
                self.temp = t_set
            self.wind = np.nan
            if t_set is not None:
                self.target_temp = t_set
            else:
                self.target_temp = np.nan
            if p_set is not None:
                self.target_power = p_set
            else:
                self.target_power = 100.
            if maxpower is None:
                raise ValueError('maxpower is required with normal rooms')
            else:
                self.maxpower = maxpower
            self.width = width
            self.length = length
            self.height = height
            if area is not None:
                self.area = area
            else:
                if length is None or width is None:
                    raise ValueError(
                        f'either width & length or area '
                        f'are required with normal rooms: {name}')
                self.area = self.width * self.length
            if volume is not None:
                self.volume = volume
            else:
                if length is None and width is None:
                    raise ValueError(
                        'either height or volume'
                        'are required with normal rooms')
                self.volume = self.area * self.height

    def init_walls(self, walls: WallList):
        """
        Associate walls with the room based on their configurations.

        :param walls: A WallList containing wall objects to be linked with the room.
        :type walls: WallList
        """
        for w in walls.values():
            if w.room_w == self.name:
                self.wall_sign[w.name] = -1.
            if w.room_c == self.name:
                self.wall_sign[w.name] = +1.

    def get_fluxes(self, walls: WallList):
        """
        Calculate and return the fluxes for each wall associated with the room.

        :param walls: A WallList containing wall objects to calculate fluxes for.
        :type walls: WallList
        :return: A dictionary mapping each wall's name to its flux.
        :rtype: dict
        """
        fluxes = {}
        for w in walls.values():
            if w.name in self.wall_sign.keys():
                if self.wall_sign[w.name] > 0:
                    fluxes[w.name] = w.f_flux[-1] * w.area
                elif self.wall_sign[w.name] < 0:
                    fluxes[w.name] = -1. * w.f_flux[0] * w.area

        return fluxes

    def is_special(self):
        """
        Determine whether the room is marked as a special room.

        :return: True if the room is special, False otherwise.
        :rtype: bool
        """
        return self._special

    def get_environment(self):
        return {'temp': self.temp, 'wind': self.wind}
    def set_environment(self, temp=None, wind=None):
        if self.is_special():
            if temp is not None:
                self.temp = temp
            if wind is not None:
                self.wind = wind
        else:
            raise ValueError('set_environment only allowed '
                             'for special rooms.')

    def get_thermo(self):
        return self.target_temp
    def set_thermo(self, temp):
        self.target_temp = temp

    def get_throttle(self):
        return self.target_power
    def set_throttle(self, percent):
        if not (0<=percent<=100):
            raise ValueError('Throttle percent must be between 0 and 100')
        self.target_power = percent

    def tick(self, walls: WallList, timedelta: float = TIMESTEP):
        """
        Update the room's state by advancing the simulation by a given time interval,
        adjusting temperature based on power input and fluxes.

        :param walls: A WallList containing wall objects linked to this room.
        :type walls: WallList
        :param timedelta: The duration by which the simulation is advanced, default is TIMESTEP.
        :type timedelta: float, optional
        :return: The updated temperature of the room.
        :rtype: float
        """
        if self.is_special():
            return
        # density of air
        rho = m.thermodyn.gas_rho(p=PRESSURE, T=self.temp,
                                  Kelvin=False, hPa=False)
        # calculate fluxes thrpugh all wall elements
        w_f = self.get_fluxes(walls)
        # external energy budget
        P_flux = np.nansum(list(w_f.values()))
        P_vent = 0.  # not implemented
        P_rad = 0.  # not implemented
        P_external = P_rad + P_flux + P_vent
        # calculate heating power needed to maintain target temperature
        if not np.isnan(self.target_temp):
            # if heatings is temperature regulated:
            # pwer to compensate heat loss by fluxes
            self.power = -P_external
            # power needed to heat up
            if self.temp < self.target_temp:
                self.power += ((self.target_temp - self.temp) * cp * rho
                               / timedelta)
            else:
                self.power = 0.
            # limit power to capabilities of heating
            if self.power > self.maxpower * self.target_power/100.:
                self.power = self.maxpower * self.target_power/100.
            elif self.power < 0.:
                self.power = 0.
        else:
            # if heating is power-regulated
            self.power = self.maxpower * self.target_power/100.
        P_heat = self.power
        dQ = (P_heat + P_vent + P_flux + P_vent) * timedelta
        dT = dQ / (m.constants.cp * rho * self.volume + self.add_c)
        self.temp = self.temp + dT
        return self.temp


class RoomList(dict):
    """
    A class to manage a list of Room objects in a building simulation context,
    inheriting from Python's dictionary to map room names to Room instances.

    :param walls: A reference to wall structures to be associated with rooms.

    """

    def __init__(self, walls):
        """
        Initialize an empty RoomList with a reference to walls.
        """
        dict.__init__(self)

    def append(self, room):
        """
        Add a Room instance to the RoomList.

        :param room: The Room instance to be added to the list.
        :type room: Room
        """
        self[room.name] = room

    def init_walls(self, walls):
        """
        Initialize wall connections for each Room in the RoomList.

        :param walls: Reference to wall configurations used to initialize each room's wall associations.
        """
        for x in self.values():
            x.init_walls(walls)

    def tick(self, walls, timedelta: float = TIMESTEP):
        """
        Advance the simulation state by a given time interval, updating each Room's state.

        :param walls: Reference to wall data necessary for updating the state of each room.
        :param timedelta: The time step duration by which to advance the simulation, default is TIMESTEP.
        :type timedelta: float, optional
        """
        for x in self.values():
            x.tick(walls, timedelta)

class Hvac:
    current = 'none'
    modes = dict()
    timers = dict()
    rnames = list()  # rooms names
    starttable = None
    switchtables = {}

    def __init__(self, rnames):
        self.rnames = rnames

    @classmethod
    def from_yaml(cls, d, rnames):
        """
        Create a Hvac instance from YAML configuration data.

        :return: the cerated Hvac instance.
        :rtype: Hvac
        """
        _keywords = {'modes': ['throttle', 'roomtemp'],
                     'switch': ['mode', 'hhmm', 'week']
                     }
        obj = Hvac(rnames)
        # collect the named modes
        if 'modes' in d:
            for name, mdict in d['modes'].items():
                mode = {}
                for k, x in mdict.items():
                    if k not in _keywords['modes']:
                        raise ValueError(f"illegal keyword {x}")
                    # one value for all rooms
                    if isinstance(x, (float, int)):
                        kd = {_ROOM_DEFAULT:float(x)}
                    # idividual values for all rooms
                    # default must be given if not all rooms are listed
                    elif isinstance(x, dict):
                        for r in rnames:
                            if (r not in x.keys() and
                                _ROOM_DEFAULT not in x.keys()):
                                raise ValueError(f"mode {name}: "
                                                 f"room {r} not in "
                                                 f"roomtemp definions "
                                                 f"and no {_ROOM_DEFAULT} "
                                                 f"defined")
                        kd={}
                        for r in x.keys():
                            if r not in rnames and r != _ROOM_DEFAULT:
                                raise ValueError(f"unknown room {r}")
                            kd[r] = x[r]
                    else:
                        raise ValueError(f"illegal type of {x}")
                    mode[k] = kd

                # make sure the mode is complete:
                for k in _keywords['modes']:
                    if k not in mode.keys():
                       mode[k] = {}
                # make sure there are defaults
                if _ROOM_DEFAULT not in mode['throttle'].keys():
                    # no setting = full throttle
                    mode['throttle'][_ROOM_DEFAULT] = 100
                if _ROOM_DEFAULT not in mode['roomtemp'].keys():
                    # no setting = no limit to roomtemp
                    mode['roomtemp'][_ROOM_DEFAULT] = 9999


                obj.modes[name] = mode
        logger.debug(obj.modes)
        # collect the timers
        if 'timers' in d:
            obj.timers = {}
            # start must be given if more than one timer:
            if (len(d['timers']) > 1 and
                not all(['start' in v for k,v in d['timers'].items()])):
                raise ValueError(f"timers must contain `start` keyword "
                                 f"if more than one timer is defined")
            for name, tdict in d['timers'].items():
                td = {}
                # verify data formats
                sstr = tdict.get('start', '01-01')
                if not re.match('[0-9]{2}-[0-9]{2}', sstr):
                    raise ValueError(f"timer {name} start string does not"
                                     f"match format mm-dd")
                td['start'] = sstr
                if not isinstance(tdict['switch'], list):
                    raise ValueError(f"timer {name} switch keyword does not"
                                     f"contain a list")
                td['switch'] = []
                for sw in tdict['switch']:
                    td['switch'].append({})
                    for k,v in sw.items():
                        if not k in _keywords['switch']:
                            raise ValueError(f"timer {name} switch "
                                             f"#{len(td['switch'])+1} "
                                             f"unknown entry {k}")
                        td['switch'][-1][k] = v
                    if 'week' not in td['switch'][-1].keys():
                        td['switch'][-1]['week'] = 'mtwtfss'
                    for x in _keywords['switch']:
                        if not x in td['switch'][-1].keys():
                            raise ValueError(f"timer {name} switch "
                                             f"#{len(td['switch'])} "
                                             f"'missing entry {x}")
                    if isinstance(td['switch'][-1]['hhmm'], (int,float)):
                        td['switch'][-1]['hhmm'] = \
                            '%04i' % int(td['switch'][-1]['hhmm'])
                    if not re.match('[0-9]{4}',
                                    td['switch'][-1]['hhmm']):
                        raise ValueError(f"timer {name} "
                                         f"switch #{len(td['switch'])} "
                                         f"hhmm string does not "
                                         f"match format hhmm")
                    if not (0 <= int(td['switch'][-1]['hhmm'])//100 <= 23
                            and
                            0 <= int(td['switch'][-1]['hhmm'])%100 <= 59):
                        raise ValueError(f"timer {name} "
                                         f"switch #{len(td['switch'])} "
                                         f"hhmm string does not "
                                         f"represent valid time")
                    if td['switch'][-1]['mode'] not in obj.modes.keys():
                        raise ValueError(f"timer {name} "
                                         f"switch #{len(td['switch'])} "
                                         f"undefined mode: "
                                         f"{td['switch'][-1]['mode']}")
                    if not isinstance(td['switch'][-1]['week'], str)\
                            or not len(td['switch'][-1]['week']) == 7\
                            or not re.match('[-mtwfs]{7}',
                                    td['switch'][-1]['week']):
                        raise ValueError(f"timer {name} "
                                         f"switch #{len(td['switch'])} "
                                         f"week string invalid: "
                                         f"{td['switch'][-1]['week']}")

                obj.timers[name] = td
        return obj

    def _make_tables(self):
        self.starttable = OrderedDict(
            sorted({v['start']:k for k,v in self.timers.items()}.items())
        )

        # if no timer starts at the start of the year,
        # make last timer of the year start (again) at newyear
        if '01-01' not in self.starttable.keys():
            x = list(self.starttable.keys())[-1]
            self.starttable.update({'01-01':self.starttable[x]})
            # python >= 3.2: move to front by this:
            self.starttable.move_to_end('01-01', last=False)

        self.switchtables = {}
        for t,timer in self.timers.items():
            # one table per weekday for each timer:
            self.switchtables[t] = {}
            for wd in range(7):
                self.switchtables[t][wd] = OrderedDict(
                    sorted({x['hhmm']:x['mode']
                            for x in timer['switch']
                            if x['week'][wd] != '-' }.items()
                           )
                )
            lastsw = None
            for wd in range(7):
                if len(self.switchtables[t][wd]) > 0:
                    lastsw = (wd,
                              list(self.switchtables[t][wd].keys())[-1])
            if lastsw is None:
                raise ValueError(f"no active switch time in timer {t}")
            for wd in range(7):
                if len(self.switchtables[t][wd]) > 0:
                    x = (wd, list(self.switchtables[t][wd].keys())[-1])
                else:
                    x = None
                # if no mode starts at the start of the day,
                # make last mode of the day start (again) at midnight
                if '0000' not in self.switchtables[t][wd].keys():
                    k, v = lastsw
                    self.switchtables[t][wd].update(
                        {'0000':self.switchtables[t][k][v]})
                    # python >= 3.2: move to front by this:
                    self.switchtables[t][wd].move_to_end('0000',
                                                         last=False)
                if x is not None:
                    lastsw = x
        logger.debug(str(self.starttable))
        logger.debug(str(self.switchtables))
        pass

    def _max_le(self, itr, val):
        return sorted([x for x in itr if x <= val])[-1]

    def switch_mode(self, time: pd.Timestamp):
        # get mode
        datestr = time.strftime('%m-%d')
        timestr = time.strftime('%H%M')
        wd = time.weekday()
        if self.starttable is None:
            self._make_tables()
        timer = self.starttable[
            self._max_le(self.starttable.keys(), datestr)
        ]
        hhmm = self._max_le(self.switchtables[timer][wd].keys(), timestr)
        mode = self.switchtables[timer][wd][hhmm]

        # apply mode only if it changed
        if mode == self.current:
            return False

        self.current = mode
        return mode


class Building():
    """
    A class to represent a building with rooms and walls, capable of simulating temperature and power dynamics.

    :param name: The name of the building.
    :type name: str
    :param t_out: The starting temperature for the outdoor environment.
    :type t_out: float
    :param t_soil: The starting temperature for the soil environment.
    :type t_soil: float

    **Class attributes**

    name : str
        The name of the building.
    lat: float
        Latitute of the buildings postion in degrees.
    lon: float
        Longitude of the buildings postion in degrees.
    walls : WallList
        A list of walls associated with the building.
    rooms : RoomList
        A list of rooms within the building.
    hvac : dict
        Dictionary holding HVAC configuration details.
    init : bool
        Initialization flag for the building; if False, triggers initial wall setup.
    output : Any
        Storage for output data related to building operations (can be tailored as needed).
    _room_history : list
        Internal storage for the historical record of room variables such as temperature and power.
    _wall_history : list
        Internal storage for the historical record of wall variables such as temperature and flux.

    Methods
    -------
    """

    name = str()
    lat = None
    lon = None
    walls = WallList()
    rooms = RoomList(walls=walls)
    init = False
    output = None
    _room_history = list()
    _wall_history = list()
    hvac = Hvac([])


    def __init__(self, name, t_out, t_soil):
        """
        Initialize a new Building instance.
        """
        self.name = name
        self.rooms.append(Room('outside', t_start=t_out, special=True))
        self.rooms.append(Room('soil', t_start=t_soil, special=True))

    @classmethod
    def from_yaml(cls, name, d):
        """
        Create a Building instance from YAML configuration data.

        :param name: The name of the building.
        :type name: str
        :param d: A dictionary containing building setup data, expected to include walls, rooms, and their parameters.
        :type d: dict
        :return: A new instance of Building initialized with the configuration from the YAML data.
        :rtype: Building
        """
        t_out = d.get('t_out', np.nan)
        t_soil = d.get('t_soil', np.nan)
        obj = Building(name, t_out, t_soil)
        obj.lat = d.get('lat', None)
        obj.lon = d.get('lat', None)
        for k, v in d['walls'].items():
            args = {'name': k}
            # loop all parameters of Wall init call
            for x, y in inspect.signature(
                    Wall.__init__).parameters.items():
                if x in ['self', 'name']: continue
                # mandatory args (== no default value)
                if x not in v and y.default == inspect.Parameter.empty:
                    raise ValueError(f"{y.name} not declared in wall {k}")
                args[x] = v.get(x, y.default)
            obj.walls.append(Wall(**args))
        for k, v in d['rooms'].items():
            args = {'name': k}
            # loop all parameters of Room init call
            for x, y in inspect.signature(
                    Room.__init__).parameters.items():
                if x in ['self', 'name']: continue
                # mandatory args (== no default value)
                if x not in v and y.default == inspect.Parameter.empty:
                    raise ValueError(f"{y.name} not declared in wall {k}")
                args[x] = v.get(x, y.default)
            obj.rooms.append(Room(**args))
        obj.hvac = Hvac.from_yaml(d['hvac'],
                                  rnames=obj.get_rooms())
        return obj

    def __eq__(self, other):
        """
        Compares this Building instance with another for equality.

        :param other: Another instance of the Building class to compare against.
        :type other: Building
        :return: True if the two instances are equal, False otherwise.
        :rtype: bool
        """
        if not isinstance(other, Building):
            # don't attempt to compare against unrelated types
            return NotImplemented
        return (self.name == other.name and
                self.walls == other.walls and
                self.rooms == other.rooms and
                self.hvac == other.hvac and
                self.output == other.output
                )

    def record_variables(self, time):
        """
        Records current temperature and power variables of rooms
        and temperature and flux of walls to history.
        """
        self._room_history.append(
            {
                'time': time,
                **{f"tmp_{k}": v.temp for k, v in self.rooms.items()},
                **{f"pwr_{k}": v.power for k, v in self.rooms.items()}
            })
        self._wall_history.append(
            {
                'time': time,
                **{f"temp{i:03d}_{k}": t for k, v in self.walls.items()
                   for i, t in enumerate(v.t_slab)},
                **{f"flux{i:03d}_{k}": f for k, v in self.walls.items()
                   for i, f in enumerate(v.f_flux)},
                **{f"{i}_{k}": f for k, v in self.walls.items()
                   for i, f in {'k_in': v.k_in, 'k_out': v.k_out,
                                'l_in': v.l_in, 'l_out': v.l_out
                                }.items() }
            })

    def output_recording(self, rname='heating_rooms_history.csv',
                         wname='heating_walls_history.csv'):
        """
        Outputs the recorded room and wall data to CSV files.

        :param rname: The filename for room history data, default is 'heating_rooms_history.csv'.
        :type rname: str, optional
        :param wname: The filename for wall history data, default is 'heating_walls_history.csv'.
        :type wname: str, optional
        """
        if len(self._room_history) > 0:
            df = pd.DataFrame.from_records(self._room_history,
                                           index='time')
            df.to_csv(rname,
                      quoting=csv.QUOTE_NONE,
                      float_format="%12.5f")
        if len(self._wall_history) > 0:
            df = pd.DataFrame.from_records(self._wall_history,
                                           index='time')
            df.to_csv(wname,
                      quoting=csv.QUOTE_NONE,
                      float_format="%12.5f")

    def get_rooms(self):
        """
        Retrieves a list of non-special room names.

        :return: A list containing the names of all non-special rooms in the building.
        :rtype: list of str
        """
        return [x.name for x in self.rooms.values() if not x.is_special()]

    def init_walls(self):
        """
        Initializes wall objects by linking them with the respective
        rooms.

        :raises ValueError: If the special rooms 'soil' and 'outside'
            are not present in the room list.
        """
        rnames = self.rooms.keys()
        if 'outside' not in rnames or 'soil' not in rnames:
            raise ValueError('special rooms `soil` and `outside` missing')
        self.rooms.init_walls(self.walls)

    def switch_mode(self, mode):
        pass

    def set_solar(self, time, octa):
        """
        set or update the solar ration upon external wall surfaces

        :param time: local time 
        :type time: pd.Timestamp
        :param octa: cloud cover in octa (0: clear, 8: overcats)
        :type octa: float
        """
        self.walls.set_solar(time, self.lat, self.lon, octa, self.rooms)

    def tick(self, timedelta: float = TIMESTEP):
        """
        Advances the simulation state by a given time interval,
        updating room and wall states.

        :param timedelta: The duration by which the simulation is advanced. Default is TIMESTEP.
        :type timedelta: float, optional
        """
        if not self.init:
            self.init_walls()
        self.walls.tick(self.rooms, timedelta)
        self.rooms.tick(self.walls, timedelta)


def spreadsheed_engine(filename):
    extension = os.path.splitext(filename)[1]
    if extension == '':
        extension = '.ods'
        filename += extension
    if extension == ".ods":
        engine = "odf"
    elif extension == ".xlsx":
        engine = "openpyxl"
    elif extension == ".xls":
        engine = "openpyxl"
    else:
        raise ValueError(f"unsupported file extension: {extension}")
    return filename, engine

def spredsheet_export(dictionary, building, basename):
    filename, engine = spreadsheed_engine(basename)
    bldg_names = dictionary['buildings'].keys()
    if building not in bldg_names:
            raise ValueError(f"building {building} not in building names")
    sheets = {}
    for k,v in dictionary['buildings'][building].items():
        if k in ['walls', 'rooms']:
            sheets[k] = v
    logger.info(f"exporting to {filename}")
    with pd.ExcelWriter(filename, engine=engine, mode='w') as f:
        for k,v in sheets.items():
            df = pd.DataFrame.from_dict(v, orient='index')
            df.to_excel(f, sheet_name=k)

def speradsheet_import(dictionary, building, filename):
    filename, engine = spreadsheed_engine(filename)
    if building not in dictionary['buildings'].keys():
        raise ValueError(f"un known building name: {building}")
    sheet_names = ['walls', 'rooms']
    logger.info(f"importing from {filename}")
    with pd.ExcelFile(filename, engine=engine) as f:
        sheets = {}
        for sh in sheet_names:
            if sh in f.sheet_names:
                df = f.parse(sh, header=0, index_col=0)
                fullsheet = df.to_dict(orient='index')
                # avoid 'dictionary changed size during iteration'
                sheet={x:{} for x in fullsheet.keys()}
                for k,v in fullsheet.items():
                    for kk,vv in v.items():
                        if not pd.isnull(vv):
                            sheet[k][kk] = vv
                sheets[sh] = sheet
            else:
                raise ValueError(f"{filename} does not contain the "
                                 f"required sheet named ``{sh}``")
    for k in sheet_names:
        dictionary['buildings'][building][k] = sheets[k]
    return dictionary

def run_building_model(bldg: Building,
                       tseries: pd.Series|str,
                       wseries: pd.Series|str=None,
                       cseries: pd.Series|str=None,
                       df: pd.DataFrame|None=None,
                       rec=None,
                       radiation=True
                       ):
    """
    Run a time dependent simulation of the building heating.

    :param bldg: the Building instance to run the model on
    :type bldg: Building
    :param tseries: Timeseries containg the air temperature,
        with time as index or column name if ``df`` is given
        and has temperature in column ``ts``
    :type tseries: pandas.Series | str
    :param wseries: (optional) Timeseries containg the wind speed,
        with time as index or column name if ``df`` is given
        and has temperature in column ``ts``
    :type wseries: pandas.Series | str
    :param cseries: (optional) Timeseries containg the cloud cover in octa,
        with time as index or column name if ``df`` is given
        and has temperature in column ``ts``
    :type cseries: pandas.Series | str
    :param df: (optional) Data frame containing timeseries of
        input data in the columns with the names given.
        ``df`` must not be given or None if ``tseries`` is a pandas.Series.
    :type df: pandas.DataFrame | None
    :param rec: (optional) a pandas interval string describing the time
        interval at which the model variables shall be recorded when
        running the model. For exampe "1min" for every minute.
        Defaults to for no recording
    :type rec: str or None
    :param radiation: Enable heat gain by net radiation on outside walls.
        Defaults to True.
    :type radiation: bool
    :return: the modeled temperatures and heating powers.
        The index is the time, columns are
        `seconds` (passed since last time),
        `power` (total heating power of all rooms),
        `tmp_NAME` and `pwr_NAME` for every room where `NAME` is the name
        the respective room
    :rtype: pandas.DataFrame

    """

    if all([
        isinstance(tseries, str),
        isinstance(wseries, str|None),
        isinstance(cseries, str|None),
    ]):
        if df is None:
            raise ValueError("df is required if tseries, cseries and "
                             "wseries are column names")
        else:
            ts = df[tseries]
            if wseries is not None:
                ws = df[wseries]
            else:
                logger.warning('no wind speed column given, '
                               'assuming default values')
                ws = pd.Series(DEFAULT_WIND, index=ts.index)
            if cseries is not None:
                cs = df[wseries]
            else:
                if radiation:
                    logger.warning('net radiation activated '
                                   'but no cloud cover column given, '
                                   'assuming default values')
                cs = pd.Series(DEFAULT_COVER, index=ts.index)
            del df
    elif all([
        isinstance(tseries, pd.Series),
        isinstance(wseries, pd.Series | None),
        isinstance(cseries, pd.Series | None),
    ]):
        if df is not None:
            raise ValueError("df is not allowed tseries and "
                             "wseries are pandas Series")
        else:
            ts = tseries
            if wseries is not None:
                ws = wseries
                if not ws.index.equals(ts.index):
                    raise ValueError("tseries and wseries indexes must "
                                     "be identical")
            else:
                logger.warning('no wind speed data given, '
                               'assuming default values')
                ws = pd.Series(DEFAULT_WIND, index=ts.index)
            if cseries is not None:
                cs = cseries
                if not cs.index.equals(ts.index):
                    raise ValueError("tseries and cseries indexes must "
                                     "be identical")
            else:
                if radiation:
                    logger.warning('net radiation activated '
                                   'but no cloud cover data are given, '
                                   'assuming default values')
                cs = pd.Series(DEFAULT_COVER, index=ts.index)
            del tseries, wseries, cseries
    else:
        raise ValueError("tseries, wseries and cseries "
                         "must all be either a "
                         "column name or a pandas.Series")

    if radiation and cs is None:
        logger.error('disabling net radiation because no '
                     'cloud cover data are given')
        radiation = False

    room_names = bldg.get_rooms()
    nrooms = len(room_names)
    columns = (['seconds', 'power'] +
               [y % x
                for x in room_names
                for y in ['tmp_%s', 'pwr_%s']
                ]
               )
    res = pd.DataFrame(np.nan, index=ts.index, columns=columns)

    if rec is None:
        recording_times = []
    else:
        recording_times = pd.date_range(start=ts.index[0],
                                        end=ts.index[-1],
                                        freq=rec)

    # timestep as datetime64
    dtick = pd.Timedelta(TIMESTEP, unit='s')  # seconds
    # simulation time
    pointer = ts.index[0]
    oldpointer = pointer
    # iterate over times in ts (execept last one)
    for ti in tqdm(range(ts.size - 1)):
        # calculate size of storage arrays
        dtime = (ts.index[ti + 1] - ts.index[ti]).total_seconds()
        nticks = int(dtime / dtick.total_seconds()) + 1
        # update parameters
        bldg.rooms['outside'].set_environment(
            temp = ts[ts.index[ti]],
            wind = ws[ws.index[ti]]
        )
        if radiation:
            bldg.set_solar(pointer, octa=cs[cs.index[ti]])
        switch = bldg.hvac.switch_mode(ts.index[ti])
        if switch:
            newmode = bldg.hvac.modes[switch]
            for r in room_names:
                if r in newmode['throttle'].keys():
                    x = r
                else:
                    x = _ROOM_DEFAULT
                bldg.rooms[r].set_throttle(newmode['throttle'][x])
                if r in newmode['roomtemp'].keys():
                    x = r
                else:
                    x = _ROOM_DEFAULT
                bldg.rooms[r].set_thermo(newmode['roomtemp'][x])
        # integrate forward until next time in ts
        tick = 0
        powers = np.full((nticks, nrooms), np.nan)
        rtemps = np.full((nticks, nrooms), np.nan)
        while pointer + dtick < ts.index[ti + 1]:
            bldg.tick(timedelta=dtick.total_seconds())
            rtemps[tick, :] = [bldg.rooms[x].temp for x in room_names]
            powers[tick, :] = [bldg.rooms[x].power for x in room_names]
            if pointer in recording_times:
                bldg.record_variables(pointer)
            pointer += dtick
            tick += 1
        # evaluate at timestep
        room_temps = np.nanmean(rtemps, axis=0)
        mean_powers = np.nanmean(powers, axis=0)
        ix = ts.index[ti]
        for i, x in enumerate(room_names):
            res.loc[ix, 'tmp_%s' % x] = room_temps[i]
            res.loc[ix, 'pwr_%s' % x] = mean_powers[i]
        res.loc[ix, 'power'] = mean_powers.sum()
        res.loc[ix, 'seconds'] = (pointer - oldpointer).total_seconds()

        # rememeber time
        oldpointer = pointer

    # repeat last value at the end of ts
    res.loc[res.index[-1], :] = res.loc[res.index[-2], :]

    # write internal variables if desired
    bldg.output_recording()

    return res


def main(args):
    # first evaluate global options
    if (txt :=args.get('slabs', '')).startswith('exponential'):
        if ',' in txt:
            args['slabs'] = 'exponential'
            tupl = txt.split(',')
            global WIDTHMIN, WIDTHSTEP, WIDTHEXP
            if len(tupl) > 1:
                WIDTHMIN = float(tupl[1])
            if len(tupl) > 2:
                WIDTHSTEP = float(tupl[2])
            if len(tupl) > 3:
                WIDTHEXP = float(tupl[3])
        logger.debug(f"set WIDTHMIN, WIDTHSTEP, WIDTHEXP to:"
                     f"{(WIDTHMIN, WIDTHSTEP, WIDTHEXP)}")

    if (slabs := args.get('slabs', None)) is not None:
        if ',' in slabs:
            # comma-separated list of floats
            try:
                slabs = [float(x) for x in slabs.split(',')]
            except:
                sys.tracebacklimit = 0
                raise ValueError("--slabs: non-numeric values in list.")
        else:
            # is it a number? Test by converting it.
            try:
                slabs = float(slabs)
            except ValueError:
                # does not convert. take the string.
                pass
        global DEFAULT_SLABS_OPT
        DEFAULT_SLABS_OPT = slabs
        logger.debug(f"set default slabs option to: {DEFAULT_SLABS_OPT}")

    if (timestep := args.get('timestep', None)) is not None:
        # is it a number? Test by converting it.
        try:
            timestep = float(timestep)
        except ValueError:
            sys.tracebacklimit = 0
            raise ValueError(f"timestep is not a floating point number: "
                             f"{timestep}")
        global TIMESTEP
        TIMESTEP = timestep
        logger.debug(f"set timestep option to: {TIMESTEP}")

    # get parameter file
    filename = args.get('file', 'heating.yaml')
    with open(filename, 'r') as f:
        dictionary = yaml.safe_load(f)
    logger.debug(f"reading parameter file: {filename}")

    # get and verify building name
    name = args.get('building', 'default')
    if name not in dictionary['buildings'].keys():
        raise ValueError(f"building {name} not in building names")
    logger.info(f"selected building: {name}")

    # run builtin export utility and exit
    if (spreadname := args.get('spread_out', None)) is not None:
        logger.info("running spreadsheet export only.")
        spredsheet_export(dictionary, name, spreadname)
        return

    # run builtin import utility and exit
    if (spreadname := args.get('spread_in', None)) is not None:
        logger.info("running spreadsheet import only.")
        speradsheet_import(dictionary, name, spreadname)
        logger.debug(f"writing paramters to {filename}")
        with open(filename, 'w') as f:
            yaml.dump(dictionary, f)
        return


    # get weather data
    csv_name = args['extracted_weather']
    lat, lon, ele, z0, source, stat_nam, obs = \
            _common.read_extracted_weather(csv_name)

    # extract variables from weather data
    tz = obs.index.tz
    logger.debug(f"observation timezone is {tz}")
    if tz is None:
        obs.index = obs.index.tz_localize('UTC')
    t_out = obs['t2m'].interpolate('linear').bfill().ffill()  # K
    t_out = t_out.apply(m.temperature._to_C)  # C
    w_out = obs['ff'].interpolate('linear').bfill().ffill() / 3. # m/s @ 2m
    c_out = obs['tcc'].interpolate('linear').bfill().ffill() * 8.  # octa

    # get the buildimg we want
    logger.info("intializing model")
    for k, v in dictionary['buildings'].items():
        if k == name:
            bldg = Building.from_yaml(k, v)
            break
    else:
        raise ValueError('no building named %s' % name)

    # run the model
    logger.info("running model")
    rec = args['recording']
    model_out = run_building_model(
        bldg=bldg,
        tseries=t_out,
        wseries=w_out,
        cseries=c_out,
        rec=rec,
        radiation=args['radiation'],
    )

    # write the direct output
    logger.info("writing model output")
    model_out.to_csv("heating_model_out.csv", quoting=csv.QUOTE_NONE,
                     float_format="%12.5f")

    # convert into emissions and write them into file
    energy = model_out['power'] * model_out['seconds']  # J
    emission_factors = {
        'xx': 2100.E-9,  # g/J
        'nox': 50.E-9,  # g/J
        'pm-u': 20.E-9,  # g/J
        'odor': 6 * 168000.E-9,  # GE/J
        'wood_kg': 1 / 4.04E6,  # kg/J
        'kWh': 1 / 3600000,  # kWh
    }
    res = pd.DataFrame({'energy': energy})
    for k, v in emission_factors.items():
        res[k] = res['energy'] * v
    print(res)
    res.to_csv("heating.csv", quoting=csv.QUOTE_NONE,
               float_format="%12.5f")
    print(res.sum(axis=0))

# ----------------------------------------------------

def add_options(subparsers):
    pars_htg = subparsers.add_parser(
        name='heating',
        aliases=[],
        help='simulate a building with heating.',
        formatter_class = _tools.SmartFormatter
    )
    default = {'building': 'default',
               'heating-file': 'heating.yaml',
               'extracted_weather': 'extracted_weather.csv',
               # 'source': 'CERRA',
               # 'year': 2003,
               'output': 'heating.csv',
               }
    pars_htg.add_argument('-f', '--heating-file',
                          metavar='FILE',
                          help='building/heating description file. ' +
                               '[%s]' % default['heating-file'],
                          default=default['heating-file'])
    pars_htg.add_argument('-b', '--building',
                          help='name of the building to simulate. ' +
                               '[%s]' % default['building'],
                          default=default['building'])
    pars_htg.add_argument('-x', '--extracted-weather',
                          help='name of the file containing the '
                               'weather data ' +
                               '[%s].' % default['extracted_weather'],
                          default=default['extracted_weather'])

    pars_htg.add_argument('-o', '--output', nargs=1,
                          metavar='FILE',
                          help='name for the output file. ' +
                               '[%s]' % default["output"],
                          default=default["output"])

    adv_htg = pars_htg.add_argument_group('advanced options')
    adv_htg.add_argument('--radiation',
                         type = _tools.str2bool,
                         help='enable or disable radiative heat gain'
                              'on outside walls [True].',
                         default = True)
    adv_htg.add_argument('--recording',
                         dest='recording',
                         metavar='FREQ',
                         help='recording interval for internal model'
                              'variables or `None` for no recording. '
                              'Must be a valid pandas frequency string '
                              '(`see Pandas documentation '
                              '<https://pandas.pydata.org/pandas-docs/'
                              'stable/user_guide/timeseries.html#'
                              'dateoffset-objects>`_), '
                              'for example ``1min``. '
                              '[None]',
                         default=None)
    adv_htg.add_argument('--slabs',
                         help='change the default value how walls are '
                         'partitioned into slabs '
                         f'[``{DEFAULT_SLABS_OPT}``].\n'
                         'Possible selections are: \n' 
                         '  - ``even``: envenly spaced slabs, if the '
                         'wall thickness is not a multiple of the slab '
                         'size, the remainder is added to the slab in '
                         'the middle\n'
                         '  - ``exponential``: slab size exponentially '
                         'increases from the minimal width of '
                         f'{WIDTHMIN}m at the surfaces to the center. '
                         f'All slabs are muliples of {WIDTHSTEP}m.\n'
                         '  - a number: like `even` but this thickness '
                         'in m is applied to all slabs, instead of the '
                         f'default value of {DEFAULT_SLAB} m\n',
                         default = DEFAULT_SLABS_OPT)
    adv_iex = adv_htg.add_mutually_exclusive_group()
    adv_iex.add_argument('--spreadsheet-export',
                         dest='spread_out',
                         metavar='FILE',
                         help='export rooms and walls from the yaml '
                              'file specified by `-f/--heating-file` '
                              'to a spreadsheet. '
                              'The file format of the spreadsheet is '
                              'inferred from the filename extension '
                              '(.ods, .xls, or .xslx).'
                              'The building name is `default` or must be '
                              'given by `-b/--building`.\n'
                              'The program exits after exporting the '
                              'spreadsheet data.',
                         default=None)
    adv_iex.add_argument('--spreadsheet-import',
                         dest='spread_in',
                         metavar='FILE',
                         help='import rooms and walls from spreadsheet '
                              'in .ods, .xls, or .xslx format and wirite '
                              'them in the heating file specified by '
                              '`-f/--heating-file`. Overwites all rooms '
                              'and walls in the heating file. '
                              'The building name is `default` or must be '
                              'given by `-b/--building`.\n'
                              'The program exits after importing the '
                              'spreadsheet data.',
                         default=None)
    adv_htg.add_argument('--timestep',
                         dest='timestep',
                         help='the model timestep in s'
                         f'[``{TIMESTEP}``].\n',
                         default = TIMESTEP)
    return pars_htg


# =========================================================================

