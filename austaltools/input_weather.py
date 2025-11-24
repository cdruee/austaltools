#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Dec 17 13:36:08 2021

@author: clemens
"""
import datetime as dt
import itertools
import logging
import os
import sys
import zipfile

import numpy as np
import pandas as pd

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import netCDF4
    import meteolib as m
    import readmet
else:
    from ._mock import netCDF4

try:
    from ._metadata import __version__, __title__
    from . import _corine
    from . import _datasets
    from . import _dispersion as dis
    from . import _geo
    from . import _storage
    from . import _tools
except ImportError:
    from _version import __version__, __title__
    import _corine
    import _datasets
    import _dispersion as dis
    import _geo
    import _storage
    import _tools


logging.basicConfig()
logger = logging.getLogger(__name__)

# ----------------------------------------------------

DEFAULT_WIND_VARIANT = os.environ.get('WIND_VARIANT', 'model_uv10')
""" 
  Default method to calculate the 10-m wind 
 
  Overridden by environment variable "WIND_VARIANT"
 
  Possible values are: 'fixed_057' 'fixed_010' 'model_mean' 
  'model_uv10' 'model_fsr'
"""
DEFAULT_INTER_VARIANT = os.environ.get('INTER_VARIANT', 'weighted')
"""
  Default method to interpolate to a given position
  
  Overridden by environment variable "INTER_VARIANT"
  
  Possible values are: 'weighted', 'nearest', 'mean'
"""
DEFAULT_CLASS_SCHEME = os.environ.get('CLASS_SCHEME', 'all')
"""
  Default method to calculate stability class
  
  Overridden by environment variable "CLASS_SCHEME"
   
  Possible values: 'all'  or a space-delimited list containing one ore
  multiple of: 'kms', 'k2s', 'kmc', 'pts, 'pgc' 
"""
# ----------------------------------------------------

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    kappa = m.constants.kappa
    gn = m.constants.gn

# ----------------------------------------------------

def h_eff(has: float, z0s: float) -> list:
    """
    Calculate the effective anemometer heights of an anemometer
    mounted at height `has` at a postion
    with roughness length `z0s` (in m), for each of the 9
    AUSTAL roughness-lenght classes
    (0.01m, 0.02m, 0.05m, 0.1m, 0.2m, 0.5m, 1m, 1.5m, 2m).
    :param has: actual aneometer height above ground in m
    :param z0s: roughness length at the anemoeter position in m
    :return: nine effective anemometer heights corresponding
    to the nine roughness classes.
    :rtype: list of float
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

def area_of_triangle(abc: list[tuple[float, float]]) -> float:
    """
    calculate area of the triangle spanned by the corners `abc`

    :param abc: corner positions of the triangle
    :type abc: list[tuple[float, float]]
    :return: area of the triangle. Positive if triangle node
        numbering is counter-clockwise, negative if clockwise
    :rtype: float
    """
    a, b, c = abc
    area = 0.5 *(-b[1]*c[0] + a[1]*(-b[0] + c[0]) +
                 a[0]*(b[1] - c[1]) + b[0]*c[1])
    return area

# ----------------------------------------------------

def point_in_triangle(p: tuple[float, float],
                          abc: list[tuple[float, float]]) -> bool:

    """
    check if point `p` is inside the triangle spanned by the corners `abc`

    :param p: position of point `p`
    :type p:  tuple[float, float]
    :param abc: corner positions of the triangle
    :type abc: list[tuple[float, float]]
    :return: returns True if point is inside triangle, returns False
        otherwise OR when the triangle is trivial (has zero area)
    :rtype: bool
    """
    # inspired by https://stackoverflow.com/a/2049593

    area = area_of_triangle(abc)
    if area == 0:
        return False
    a, b, c = abc
    s = (a[1]*c[0] - a[0]*c[1] + (c[1] - a[1])*p[0] + (a[0] - c[0])*p[1]) \
        / (2 * area)
    t = (a[0]*b[1] - a[1]*b[0] + (a[1] - b[1])*p[0] + (b[0] - a[0])*p[1]) \
        / (2 * area)
    res = s > 0. and t > 0. and 1 - s - t > 0.
    return res

# ----------------------------------------------------

def grid_surrounding_nodes(lat: float, lon: float, dims: dict) \
        -> list[tuple[float, float, float]]:
    """
    get the three nodes from dims that surround position lat / lon

    :param lat: point position latitude
    :type lat: float
    :param lon: point position longitude
    :type lon: float
    :param dims: 2-D array of lat and lon grid positions
    :type dims: dict[np.array]
    :return: Three corner positions and the distance to each of them
        as tuple (grid-index x, grid-index y, distance)
    :rtype: list[tuple[float, float, float]]
    """
    dims_dim = set(len(np.shape(dims[x])) for x in ['lat', 'lon'])
    if len(dims_dim) > 1:
        raise ValueError('dims have different shapes')
    if 2 in dims_dim:
        grd_lat = dims['lat']
        grd_lon = dims['lon']
    else:
        raise ValueError('dims have unsupported shape')
    vec_s_d = np.vectorize(_geo.spheric_distance)
    tgt_lat = np.full(np.shape(dims['lat']), lat)
    tgt_lon = np.full(np.shape(dims['lon']), lon)
    distance = vec_s_d(tgt_lat, tgt_lon, grd_lat, grd_lon)
    # https://stackoverflow.com/a/30577520
    sort_index = list(map(tuple,
                          np.dstack(np.unravel_index(
                              np.argsort(distance.ravel()),
                              distance.shape)).reshape(-1,2)
                          ))
    sorted_grd = [(i, j, distance[i,j]) for i, j in sort_index]

    min_dist_sum = np.inf
    min_triangle = None
    # get all possible triangles out of the nearest 3, 4, 5, ... points
    for n in range(3, len(sorted_grd)):
        logger.debug('iterating points: %s' % n)
        triangles = list(itertools.combinations(sorted_grd[0:n], 3))
        # calculate sum of corner distances for triangles
        # that include the target position
        dist_sums = []
        for t in triangles:
            corners = [(grd_lon[i, j], grd_lat[i, j]) for i, j, _ in t]
            if point_in_triangle((lon, lat), corners):
                ds = np.sum([d**2 for _, _, d in t])
            else:
                ds = np.inf
            dist_sums.append(ds)
        # stop searching if this value of n brings no better triangles
        if not any([x < min_dist_sum for x in dist_sums]) and \
                min_triangle is not None:
            break
        # get the triangle that has the lowest sum of corner distances
        for i, t in enumerate(triangles):
            if dist_sums[i] < min_dist_sum:
                min_dist_sum = dist_sums[i]
                min_triangle = t
        logger.debug('min_triangle: %s %s' % (str(min_triangle),str(min_dist_sum)))

    return min_triangle

# ----------------------------------------------------

def cloud_type_from_cover(tcc: pd.Series, lmcc: pd.Series) -> pd.Series:
    """
    Estimate dominant cloud type from total and low/middle cloud cover

    :param tcc: total cloud cover in 1
    :type tcc: pd.Series[float]
    :param lmcc: low/middle cloud cover in 1
    :type lmcc: pd.Series[float]
    :return: cloud type
    :rtype: pd.Series[str]
    """
    ratio = lmcc/tcc
    cty=pd.Series("", index=tcc.index, dtype=str)
    for i in cty.index:
        if tcc[i] == 0:
            # no clouds
            pass
        elif tcc[i] <= 0.1:
            # low clouds not reported < 0.1
            cty[i] = 'CI'
        elif ratio[i] > 0.80:
            # majority of the energy from low clouds
            cty[i] = 'CU'
        else:
            # mainority of the energy from low clouds
            cty[i] = 'CI'
    return cty


# ----------------------------------------------------

def grid_calulate_weights(pos: list, inter_variant=None) -> list[float]:
    """
    calculate the weights for barycentrict averaging of the
    sourrounding values

    :param pos: the three grid node positions and distances
      as tuple (x,y,d)
    :type pos: list[tuple[float, float, float]]
    :param inter_variant: method user for interpolation
    :type inter_variant: str
    :return: weights
    :rtype: list[float]
    """
    if inter_variant is None:
        inter_variant = DEFAULT_INTER_VARIANT
    logging.info('interpolation variant: %s' % inter_variant)
    w = [None, None, None]
    if inter_variant == 'weighted':
        a = [1. / d if d > 0. else 1. for _, _, d in pos[0:3]]
        b = np.sum(a)
        w = [x / b for x in a]
    elif inter_variant == 'mean':
        w[0] = 1. / 3.
        w[1] = 1. / 3.
        w[2] = 1. / 3.
    elif inter_variant == 'nearest':
        w[0] = 1.
        w[1] = 0.
        w[2] = 0.
    else:
        raise ValueError('unknown interpolation variant: %s' %
                         inter_variant)
    logger.debug('w: %s' % w)
    return w

# ----------------------------------------------------

def decode_nc_time(nc: netCDF4.Dataset,timevar: str = 'time') -> pd.Series:
    """
    Decode a time variable from a NetCDF dataset into a pandas Series of
    datetime objects.

    This function reads a time variable from a NetCDF4 dataset, extracts
    its time units and calendar, and decodes the raw time values into
    Timestamps using :py:func:`netCDF4.num2date`.

    :param nc: The NetCDF dataset containing the time variable.
    :type nc: netCDF4.Dataset
    :param timevar: Name of the time variable to decode. Defaults to 'time'.
    :type timevar: str, optional

    :return: A pandas Series of decoded time values as pandas.Timestamp.
    :rtype: pandas.Series

    :raises KeyError: If the specified time variable does not exist.
    :raises AttributeError: If the time variable lacks 'units' or 'calendar'.
    :raises ValueError: If the units or calendar are invalid for decoding.

    :notes:
         - Uses `netCDF4.num2date` for decoding.
         - Ensures native Python `datetime` objects with:
           `only_use_cftime_datetimes=False` and
           `only_use_python_datetimes=True`.
         - Expects the time variable to follow CF conventions.

    :example:

         >>> import netCDF4
         >>> import pandas as pd
         >>> ds = netCDF4.Dataset('example.nc')
         >>> times = decode_nc_time(ds)
         >>> print(times.head())

    """
    if not isinstance(nc, netCDF4.Dataset):
        raise TypeError('nc must be an instance of netCDF4.Dataset')

    time_unit = nc.variables[timevar].getncattr('units')
    time_calendar = nc.variables[timevar].getncattr('calendar')
    logger.debug(f"time_unit: {time_unit}")
    logger.debug(f"calendar: {time_calendar}")
    datetime = netCDF4.num2date(nc.variables['time'][:],
                              units=time_unit,
                              calendar=time_calendar,
                              only_use_cftime_datetimes=False,
                              only_use_python_datetimes=True)
    return pd.to_datetime(datetime, utc=True)

# ----------------------------------------------------

def read_era5_nc(ncfile, lat, lon, wind_variant=None):
    """
    Read an ERA5 NetCDF file, interpolate meteorological variables to a
    specific geographic position (latitude, longitude), and calculate
    wind speed and direction adjusted for surface roughness.

    This function extracts required and optional ERA5 meteorological
    variables from the input NetCDF file, interpolates them to the given
    point location, applies surface flux and roughness adjustments, and
    optionally computes wind speed based on selected surface roughness
    models.

    :param ncfile: Path to the ERA5 NetCDF file.
    :type ncfile:  str

    :param lat: Latitude (in degrees) of the point at which to
      interpolate values.
    :type lat: float
    :param lon: Longitude (in degrees) of the point at which to
      interpolate values.
    :type lon: float
    :param wind_variant: Method used to compute 10 m wind speed (`ff`).
      Default is :py:const:`DEFAULT_WIND_VARIANT`.
      Supported options:

        - `'fixed_057'` : Assumes fixed surface roughness z₀ = 0.57 m.
        - `'fixed_010'` : Assumes fixed surface roughness z₀ = 0.10 m.
        - `'model_mean'` : Uses mean surface roughness from model data.
        - `'model_uv10'` : Uses u10 and v10 without adjustment.
        - `'model_fsr'` : Uses model-provided roughness field (fsr).

    :type wind_variant: str

    :returns:
        DataFrame containing interpolated meteorological variables
        and computed wind metrics.
        Includes the following variables (if present in the input data):

        Required:
            - `time` : datetime64[ns], timestamps
            - `u10`  : float, 10 m u-component of wind [m/s]
            - `v10`  : float, 10 m v-component of wind [m/s]
            - `sp`   : float, surface pressure [Pa]
            - `zust` : float, friction velocity [m/s]
            - `fsr`  : float, forecast surface roughness [m]
            - `t2m`  : float, 2 m temperature [K]
            - `d2m`  : float, 2 m dewpoint temperature [K]
            - `cbh`  : float, cloud base height [m]
            - `sshf` : float, surface sensible heat flux [W/m²]
            - `slhf` : float, surface latent heat flux [W/m²]
            - `lcc`  : float, low cloud cover [fraction]
            - `tcc`  : float, total cloud cover [fraction]

        Optional (included if available):
            - `mcc`  : float, medium cloud cover [fraction]
            - `tp`   : float, total precipitation [mm]

        Computed:
            - `ff`   : float, 10 m wind speed [m/s]
            - `dd`   : float, wind direction in degrees from North [°]
    :rtype: pandas.DataFrame

    :raises ValueError:
      If a required variable is missing from the NetCDF file or
      if the `wind_variant` is unknown or unsupported.

    :notes:
        The ERA5 variables expected in the input file are:

        ======  ========    ==========================  ======
         name   unit        description                 code
        ======  ========    ==========================  ======
        'time'
        'u10'   m s**-1     10m_u-component_of_wind     10u
        'v10'   m s**-1     10m_v-component_of_wind     10v
        'sp'    Pa          surface_pressure            sp
        'zust'  m s**-1     friction_velocity           zust
        'fsr'   m           forecast_surface_roughness  fsr
        't2m'   K           2m_temperature              2t
        'd2m'   K           2m_dewpoint_temperature     2d
        'cbh'   m           cloud_base_height           cbh
        'sshf'  J m**-2     surface_sensible_heat_flux  sshf
        'slhf'  J m**-2     surface_latent_heat_flux    slhf
        'lcc'   1           low_cloud_cover             lcc
        'tcc'   1           total_cloud_cover           tcc
        ------  --------    --------------------------  ------
        optional:
        ------------------------------------------------------
        'mcc'   1           medium_cloud_cover          mcc
        'tp'    m           total_precipitation         tp
        ======  ========    ==========================  ======

        - The function uses logarithmic wind profile theory to estimate
          wind speeds when `wind_variant` involves surface roughness.
        - Heat fluxes (`sshf`, `slhf`) are converted from J/m² per hour
          to W/m² (SI units).
        - Total precipitation (`tp`) is converted from meters to millimeters.
        - Wind direction (`dd`) is computed as meteorological direction
          (from which the wind blows).
        - Wind components (u10, v10) in ERA5 are based on a fixed
          roughness length for short grass (z₀=0.03m),
          so wind speed (`ff`) is recalculated accordingly.

    :example:

        >>> df = read_era5_nc("era5_data.nc", lat=52.52, lon=13.405)
        >>> print(df[['time', 'ff', 'dd']].head())

    """
    if wind_variant is None:
        wind_variant = DEFAULT_WIND_VARIANT

    _VAR_NEEDED = ['u10', 'v10', 'sp', 'zust', 'fsr',
                   't2m', 'd2m', 'cbh', 'sshf', 'slhf',
                   'lcc', 'tcc']
    _VAR_OPTIONAL = ['mcc', 'tp']

    nc = netCDF4.Dataset(ncfile)

    for x in _VAR_NEEDED:
        if x not in nc.variables:
            raise ValueError('needed variable not in input data: %s' % x)
    all_variables = _VAR_NEEDED
    for x in _VAR_OPTIONAL:
        if x not in nc.variables:
            logging.warning('optional variable not in input data: %s' % x)
        else:
            all_variables.append(x)
    #
    # make lat lon 2-D fields
    nx = len(nc['longitude'])
    ny = len(nc['latitude'])
    dims = {'lat': np.full((nx, ny), np.nan),
            'lon': np.full((nx, ny), np.nan)}
    for x in range(nx):
        for y in range(ny):
            dims['lon'][x, y] = nc['longitude'][x].data
            dims['lat'][x, y] = nc['latitude'][y].data
    #
    # convert time
    logger.info('calculating time')
    values = pd.DataFrame()
    # epoch = dt.datetime(1900, 1, 1, 0, 0, tzinfo=dt.timezone.utc)
    # values['time'] = pd.to_datetime(
    #     [epoch + dt.timedelta(hours=int(x)) for x in nc['time']])
    values['time'] = decode_nc_time(nc)
    #
    # interpolate values to position
    #
    logger.info('calculating position')
    positions = grid_surrounding_nodes(lat, lon, dims)
    # extract input values at positions
    pv = {}
    for val in _tools.progress(all_variables, 'extract variables'):
        pv[val] = [nc[val][:, x, y].data for x, y, _ in positions]
    # free memory
    nc.close()

    # calculate weights and average the values
    weights = grid_calulate_weights(positions)
    for val in _tools.progress(pv.keys(), 'interpolating vars'):
        if np.ndim(pv[val]) > 1:
            logger.debug('interpolating value: %s' % val)
            values[val] = np.dot(weights, pv[val])
    #
    #  convert values
    #
    #   surface fluxes are in J/hm² down, convert to W/m² up:
    for val in ['sshf', 'slhf']:
        if val in all_variables:
            values[val] = values[val] / (-3600.)  # W/m²
    #   total precipitation is m (per hour) , convert to mm:
    for val in ['tp']:
        if val in all_variables:
            values[val] = values[val] * 1000  # mm
    #   remove negative cbh values:
    for val in ['cbh']:
        if val in all_variables:
            # Replace values where the condition is True.
            values[val] = values[val].mask(values[val] < 0, np.nan)
    #
    #    values['ff'] = np.sqrt(values['u10']*values['u10'] +
    #                           values['v10']*values['v10'])
    #
    #   BUT:
    #   These '10m wind components' are diagnostic quantities generally
    #   computed not by using the roughness length of the tile itself,
    #   but instead assuming a roughness length for short grass (=0.03m),
    #   the surface over which (by WMO convention) winds should be measured
    #   https://confluence.ecmwf.int/display/FUG/Section+9.3+Surface+Wind
    #
    #   Therefore: u10 = u*/k * ln(z/z0)
    if wind_variant == 'fixed_057':
        z0 = 0.57  # m
        values['fsr'] = z0  # m
        values['ff'] = (values['zust'] / kappa *
                        np.log((10. + 7. * z0) / z0))  # m/s
    elif wind_variant == 'fixed_010':
        z0 = 0.10  # m
        values['fsr'] = z0  # m
        values['ff'] = (values['zust'] / kappa *
                        np.log((10. + 7. * z0) / z0))  # m/s
    elif wind_variant == 'model_mean':
        z0 = np.nanmean(values['fsr'])  # m
        values['fsr'] = z0  # m
        values['ff'] = (values['zust'] / kappa *
                        np.log((10. + 7. * z0) / z0))  # m/s
    elif wind_variant == 'model_uv10':
        values['ff'] = np.sqrt(values['u10'] ** 2 +
                               values['v10'] ** 2)  # m/s
    elif wind_variant == 'model_fsr':
        values['ff'] = (values['zust'] / kappa *
                        np.log((10. + 7. * values['fsr']) /
                               values['fsr']))  # m/s
    else:
        raise ValueError('unknown wind variant: %s' % wind_variant)
    logging.info('wind variant: %s' % wind_variant)
    values['dd'] = np.rad2deg(np.arctan2((-values['u10']),
                                         (-values['v10'])))  # deg

    return values

# ----------------------------------------------------

def get_era5_weather(lat, lon, year, wind_variant=None, datafile=None) \
        -> (pd.DataFrame, float):
    """
    Get weather timeseries for the provided position
    from source ERA5 for the year provided and calulate
    cloud cover of non-high clouds (`lmcc`) and roughness
    length `z0` from "forecast surface roughness"

    :param lat: position latitude in degrees
    :type lat: float
    :param lon: position laongitude  in degrees
    :type lon: float
    :param year: get data from this calendar year
    :type year: int
    :param wind_variant: (optional) select the variant how the wind
      at 10 m height is caclulated from the ERA5 data
    :type wind_variant: str | None
    :param datafile: (optional) read from this ERA5 data file
    :type datafile: str | None
    :return: weather timeseries as dataframe and surface roughness in m.
        The index of the dataframe is the measurement time as `datetime64`,
        the columns are:

        ======  ========= =============================
        column   unit     comment
        ======  ========= =============================
        'time'   UTC
        'ff'     m/s      wind speed at 10m height
        'dd'     degrees  wind direction
        'sp'     Pa       surface air pressure (QFE)
        't2m'    K        air temperature at 2 m height
        'lmcc'   1        low and medium cloud cover
        'tcc'    1        total cloud cover
        'sshf'   W/m²     surface sensible heat flux
        'slhf'   W/m²     surface latent heat flux
        'fsr'    m        forecast surface roughness
        'tp'     mm       total precipitation per hour
        ======  ========= =============================

    :rtype: (pd.DataFrame, float)
    """
    ds = _datasets.dataset_get(
        _datasets.name_yearly("ERA5", year)
    )
    if not ds.available:
        raise ValueError(f"Dataset not available: {ds.name}")

    if datafile is None:
        datafile = os.path.join(ds.path, ds.file_data)
    logging.info('reading data from; %s' % datafile)

    v = read_era5_nc(datafile, lat, lon, wind_variant)
    v.index = v['time']
    v.sort_index(inplace=True)

    logging.debug('lmcc')
    if 'mcc' in v.keys():
        v['lmcc'] = np.maximum(v['lcc'], v['mcc'])  # 1
    else:
        v['lmcc'] = v['lcc']  # 1

    z0 = v['fsr'].mean()
    logger.info("roughness length: %6f m" % z0)

    res = v.filter(['time',  # UTC
                    'ff',  # m/s
                    'dd',  # deg
                    'sp',  # Pa
                    't2m', 'd2m',  # K
                    'lmcc', 'tcc',  # 1
                    'sshf', 'slhf',  # W/m²
                    'cbh',  # m
                    'fsr',  # m
                    'tp'  # mm
                    ])
    logger.debug("got: %s" % res.keys())
    logger.debug("z0 : %s" % z0)
    return res, z0


# ----------------------------------------------------
def read_cerra_nc(ncfile, lat, lon):
    """
    Read a CERRA NetCDF file and interpolate variables to a given
    position (lat, lon), converting units where necessary and
    recalculating wind speed and direction using surface roughness.

    The function interpolates variables to the provided coordinates,
    converts units for physical consistency,
    decomposes and recomputes 10-meter wind speed and direction,
    decomposes accumulated variables and normalizes them
    and returns the processed data as a pandas DataFrame


    :param ncfile: Path to the NetCDF file.
    :type ncfile: str

    :param lat: Latitude (decimal degrees) for interpolation.
    :type lat: float

    :param lon: Longitude (decimal degrees) for interpolation.
    :type lon: float

    :returns:
        DataFrame containing time series of interpolated and
        derived variables at the specified location.
        Returned columns include:

        Required:
            - 'time' : Timestamp (UTC)
            - 't2m' : 2-metre temperature [K]
            - 'sp' : Surface pressure [Pa]
            - 'sshf' : Sensible heat flux [W m**-2]
            - 'slhf' : Latent heat flux [W m**-2]
            - 'sr' → 'fsr' : Surface roughness [m]
            - 'r2' → 'r2m' : Relative humidity [1]
            - 'lcc' : Low-level cloud cover [1]
            - 'mcc' : Medium-level cloud cover [1]
            - 'tcc' : Total cloud cover [1]

        Optional (if available):
            - 'tp' : Total precipitation [mm]

        Computed variables:
            - 'zust' : Friction velocity [m s**-1]
            - 'ff' : 10-metre wind speed [m s**-1]
            - 'dd' : 10-metre wind direction [deg]
    :rtype: pandas.DataFrame

    :raises ValueError:
        If any required variable is missing in the NetCDF file.

    :notes:
         The ERA5 variables expected in the input file are:

         ========= =========== ====================================
          name      unit        description
         ========= =========== ====================================
          'time'
          'wdir10'  deg         10-metre wind direction true
          'si10'    m s**-1     10-metre wind speed
          'r2'      %           2-metre relative humidity
          't2m'     K           2-metre temperature
          'lcc'     %           low-level cloud cover
          'mcc'     %           medium-level cloud cover
          'tisemf'  N m**-2 s   time integral of surface eastward
                                momentum flux
          'tisnmf'  N m**-2 s   time integral of surface northward
                                momentum flux
          'slhf'    J m**-2     surface latent heat flux
          'sp'      Pa          surface pressure
          'sr'      m           surface roughness
          'sshf'    J m**-2     surface sensible heat flux
          'tcc'     %           total cloud cover
         --------- ----------- ------------------------------------
         optional:
         ----------------------------------------------------------
         'tp'      kg m**=2    total precipitation
         ========= =========== ====================================

    :warning:
        Missing optional variables are skipped with a warning.


   """
    _VAR_NEEDED = [['wdir10','10wdir'], ['si10', '10si'],
                   ['r2', '2r'], ['t2m', '2t'], 'lcc',
                   'mcc', 'tisemf', 'tisnmf', 'slhf', 'sp',
                   'sr', 'sshf', 'tcc']
    _VAR_OPTIONAL = ['tp']

    _VAR_LAT = ['latitude', 'lat']
    _VAR_LON = ['longitude', 'lon']


    nc = netCDF4.Dataset(ncfile)

    for x in _VAR_NEEDED:
        if isinstance(x, list):
            if all([y not in nc.variables for y in x]):
                raise ValueError('needed variable not in input data: '
                                 '%s' % str(x))
        else:
            if x not in nc.variables:
                raise ValueError('needed variable not in input data: '
                                 '%s' % x)
    all_variables = _VAR_NEEDED
    for x in _VAR_OPTIONAL:
        if x not in nc.variables:
            logging.warning('optional variable not in input data: %s' % x)
        else:
            all_variables.append(x)

    for x in _VAR_LAT:
        if x in nc.variables:
            break
    else:
        raise ValueError('no known variable for latitude input data:'
                                 '%s' % _VAR_LAT)
    tal_nc = x
    for x in _VAR_LON:
        if x in nc.variables:
            break
    else:
        raise ValueError('no known variable for longitude input data:'
                                 '%s' % _VAR_LON)
    lon_nc = x



    dims = {'lat': nc[tal_nc][:].data,
            'lon': nc[lon_nc][:].data}
    #
    # convert time
    logger.info('calculating time')
    values = pd.DataFrame()
    # time_unit_string = nc.variables['time'].units
    # time_unit, _, base_date = time_unit_string.split(maxsplit=2)
    # logger.debug(f"time_unit: {time_unit}")
    # logger.debug(f"base_date: {base_date}")
    # epoch = pd.to_datetime(base_date, utc=True)
    # values['time'] = [epoch + pd.Timedelta(x, unit=time_unit)
    #                   for x in nc.variables['time'][:].data]
    values['time'] = decode_nc_time(nc)
    logger.debug(f"time: {values['time'][0:2].values} ...")
    #
    # interpolate values to position
    #
    logger.info('calculating position')
    positions = grid_surrounding_nodes(lat, lon, dims)
    # extract input values at positions
    pv = {}
    for val in _tools.progress(all_variables, 'extract variables'):
        if isinstance(val, list):
            val_pv = val[0]
            for x in val:
                if x in nc.variables:
                    break
            else:
                raise ValueError('none of the variable names in input '
                                 'data: %s' % str(val))
            val_nc = x
        else:
            val_pv = val_nc = val
        pv[val_pv] = [nc[val_nc][:, x, y].data for x, y, _ in positions]
    # free memory
    nc.close()
    # decompose wind into vector components before interpolating
    pv['u10'] = []
    pv['v10'] = []
    for i, _ in _tools.progress(enumerate(positions),'decomposoing wind'):
        u10, v10 = m.wind.dir2uv(pv['si10'][i], pv['wdir10'][i])
        pv['u10'].append(u10)
        pv['v10'].append(v10)
    # calculate weights and average the values
    weights = grid_calulate_weights(positions)
    for val in _tools.progress(pv.keys(), 'interpolating vars'):
        if np.ndim(pv[val]) > 1:
            logger.debug('interpolating value: %s' % val)
            values[val] = np.dot(weights, pv[val])
    #
    #  convert values
    values.rename({
        'sr': 'fsr',
        'r2': 'r2m',
    }, axis=1, inplace=True)
    #
    #  un-accumulate the cumulative values
    #  model run starts at 00, 03, 06,
    #  forcast values are accumulated, i.e.
    #  start time +01:00 is 1-h mean
    #  start time +02:00 is 2-h mean
    #  start time +03:00 is 3-h mean
    #  subtract +02:00-values from +03:00 values to get 1-h mean
    #  from +02:00 to +03:00, ...
    #
    # Check if the series is tz-aware
    tz = getattr(values['time'].dt, "tz", None)

    if tz is not None:
    # tz-aware: make epoch tz-aware with the same tz
        epoch = pd.Timestamp(year=values['time'].min().year,
                             month=1, day=1, tz=tz)
    else:
        # tz-naive: keep epoch tz-naive
        epoch = pd.Timestamp(year=values['time'].min().year,
                             month=1, day=1)
    # Vectorized difference in hours
    hours_total = ((values['time'] - epoch) /
                   pd.Timedelta('1 hour')).astype(int)

    hours_lead = ((hours_total - 1) % 3 + 1).to_numpy()
    for val in ['sshf', 'slhf', 'tisemf', 'tisnmf', 'tp']:
        values[val] = values[val].mask(
            cond=(hours_lead > 1),
            other=values[val].diff()
        )
    #
    #  2-meter relative humidity (%) to (1)
    values['r2m'] = values['r2m'] / 100.
    #
    #   cloud cover values are in %, convert to fraction of 1:
    for val in ['lcc', 'mcc', 'tcc']:
        if val in all_variables:
            values[val] = values[val] / 100.  # 1
    #
    #   surface fluxes are in J/hm² down, convert to W/m² up:
    for val in ['sshf', 'slhf']:
        if val in all_variables:
            values[val] = values[val] / (-3600.)  # W/m²
    #
    #   total precipitation is kg = 0.999 l (per hour) , convert to mm:
    for val in ['tp']:
        if val in all_variables:
            values[val] = values[val] * 0.999  # mm
    #
    #   friction velocity
    for val in ['tisemf', 'tisnmf']:
        # Momentum flux components ...  .
        # Positive (negative) values denote stress in the eastward
        # (westward) direction. It is an accumulated (time-integrated)
        # parameter meaning that it is accumulated from the beginning
        # of the forecast. The parameter is given in N m-2 s.
        # i.e. after un-accumulating we have an hourly summation here:
        if val in all_variables:
            values[val] = values[val] / 3600.  # N/m² s -> N/m²
    rho = m.thermodyn.gas_rho(p=values['sp'], T=values['t2m'],
                              hPa=False, Kelvin=True)
    values['zust'] = np.sqrt(
        np.sqrt(values['tisemf'] ** 2 + values['tisnmf'] ** 2) / rho
    )
    values.drop(['tisemf', 'tisnmf'], axis=1)
    #
    # convert wind back into speed and direction
    values['ff'], values['dd'] = m.wind.uv2dir(
        values['u10'], values['v10'])
    values.drop(['u10', 'v10'], axis=1)

    newyear = pd.Timestamp(year=values['time'][0].year, month=1, day=1,
                           tz=values['time'][0].tz)
    if values['time'][0] > newyear:
        first_hours = pd.date_range(start=newyear,
                                    end=(values['time'][0] -
                                         pd.Timedelta(1,"m")),
                                    freq='1h')
        #   right end -1 min to exclude the full-hour value
        #   this could be done by `inclusive="left"`
        #   but only for pandas 1.4.0 and later
        first_rows = []
        for x in first_hours:
            first_rows.append({c: np.nan if c != 'time' else x
                               for c in values.columns})
        values = pd.concat([pd.DataFrame(first_rows), values],
                           ignore_index=True)
    return values

# ----------------------------------------------------

def get_cerra_weather(lat, lon, year, datafile=None) \
        -> (pd.DataFrame, float):
    """
    Get weather timeseries for the provided position
    from source CERRA for the year provided and calulate
    cloud cover of non-high clouds (`lmcc`) and roughness
    length `z0` from "forecast surface roughness"

    :param lat: position latitude in degrees
    :type lat: float
    :param lon: position laongitude  in degrees
    :type lon: float
    :param year: get data from this calendar year
    :type year: int
    :param datafile: (optional) read from this CERRA data file
    :type datafile: str | None
    :return: weather timeseries as dataframe and surface roughness in m.
        The index of the dataframe is the measurement time as `datetime64`,
        the columns are:

        ======  ========= =============================
        column   unit     comment
        ======  ========= =============================
        'time'   UTC
        'ff'     m/s      wind speed at 10m height
        'dd'     degrees  wind direction
        'sp'     Pa       surface air pressure (QFE)
        't2m'    K        air temperature at 2 m height
        'lmcc'   1        low and medium cloud cover
        'tcc'    1        total cloud cover
        'sshf'   W/m²     surface sensible heat flux
        'slhf'   W/m²     surface latent heat flux
        'fsr'    m        forecast surface roughness
        'tp'     mm       total precipitation per hour
        ======  ========= =============================

    :rtype: (pd.DataFrame, float)
    """
    ds = _datasets.dataset_get(
        _datasets.name_yearly("CERRA", year)
    )
    if not ds.available:
        raise ValueError(f"Dataset not available: {ds.name}")
    if datafile is None:
        datafile = os.path.join(ds.path, ds.file_data)
    logging.info('reading data from; %s' % datafile)

    v = read_cerra_nc(datafile, lat, lon)
    v.index = v['time']
    v.sort_index(inplace=True)

    logging.debug('lmcc')
    if 'mcc' in v.keys():
        v['lmcc'] = np.maximum(v['lcc'], v['mcc'])  # 1
    else:
        v['lmcc'] = v['lcc']  # 1

    z0 = v['fsr'].mean()
    logger.info("roughness length: %6f m" % z0)

    res = v.filter(['time',  # UTC
                    'ff',  # m/s
                    'dd',  # deg
                    'sp',  # Pa
                    't2m',  # K
                    'r2m',  # 1
                    'lmcc', 'tcc',  # 1
                    'sshf', 'slhf',  # W/m²
                    'fsr',  # m
                    'tp'  # mm
                    ])
    logger.debug("got: %s" % res.keys())
    logger.debug("z0 : %s" % z0)
    return res, z0

# ----------------------------------------------------

def read_hostrada_nc(ncfile, lat, lon, wind_variant=None):
    """
    Read a HOSTRADA NetCDF file and interpolate variables to a given
    position (lat, lon), converting units where needed.

    This function reads the NetCDF file, interpolates variables
    to the specified location, converts units to standardized formats,
    returning the interpolated values renamed to the
    unified naming convention


    :param ncfile: Path to the HOSTRADA NetCDF file.
    :type ncfile: str

    :param lat: Latitude (decimal degrees) at which to interpolate data.
    :type lat: float

    :param lon: Longitude (decimal degrees) at which to interpolate data.
    :type lon: float

    :param wind_variant:
        Placeholder for future use (e.g., handling different wind
        input schemes). Currently unused.
    :type wind_variant: str | None

    :returns: A DataFrame containing interpolated and converted variables
      at the given point. The following variables are included:

        Required:
            - 'time' : Timestamp (UTC)
            - 'sp' : Surface pressure [Pa]
            - 'ff' : Wind speed at 10 m [m s**-1]
            - 'dd' : Wind direction at 10 m [deg]

        Computed:
            - 't2m' : 2-metre temperature [K] (converted from °C)
            - 'tcc' : Total cloud cover [1] (from 0–8 octas)
            - 'r2m' : Relative humidity [1] (from %)
    :rtype: pandas.DataFrame

    :raises ValueError:
        If any required variable is missing in the NetCDF file.

    :notes:
        Variables expected in the input file are:

        ===================  ========  ==========================
         name                 unit      long name
        ===================  ========  ==========================
        'time'
        'tas'                 °C        Near-Surface Air Temperature
        'clt'                 octa      Total Cloud Fraction
        'hurs'                %         Near-Surface Relative Humidity
        'ps'                  Pa        Surface Air Pressure
        'sfcWind_direction'   deg       Near-Surface Wind Direction
        'sfcWind'             m s**-1   Near-Surface Wind Speed
        ===================  ========  ==========================

        - The function assumes the NetCDF contains 2D longitude/latitude
          fields.
        - Missing or malformed wind data will result in interpolation
          errors or incorrect wind values.

    """
    if wind_variant is None:
        wind_variant = DEFAULT_WIND_VARIANT

    _VAR_NEEDED = ['tas', 'clt', 'hurs', 'ps',
                   'sfcWind_direction', 'sfcWind']

    nc = netCDF4.Dataset(ncfile)

    for x in _VAR_NEEDED:
        if x not in nc.variables:
            raise ValueError('needed variable not in input data: %s' % x)
    all_variables = _VAR_NEEDED
    #
    # get lat lon 2-D fields
    dims = {
        'lon': nc['lon'][:,:],
        'lat': nc['lat'][:,:]
    }
    #
    # convert time
    logger.info('calculating time')
    values = pd.DataFrame()
    values['time'] = decode_nc_time(nc)
    #
    # interpolate values to position
    #
    logger.info('calculating position')
    positions = grid_surrounding_nodes(lat, lon, dims)
    # extract input values at positions
    pv = {}
    for val in _tools.progress(all_variables, 'extract variables'):
        logger.debug(f"extract variable: {val}")
        pv[val] = [nc[val][:, x, y].data for x, y, _ in positions]
    # free memory
    nc.close()

    # calculate weights and average the values
    weights = grid_calulate_weights(positions)
    for val in _tools.progress(pv.keys(), 'interpolating vars'):
        logger.debug(f"interpolate variable: {val}")
        if np.ndim(pv[val]) > 1:
            logger.debug('interpolating value: %s' % val)
            values[val] = np.dot(weights, pv[val])
    #
    #  convert values
    #
    values.rename(
        inplace=True,
        columns={
            'sfcWind': 'ff',            # m/s
            'sfcWind_direction': 'dd',  # deg
            'ps': 'sp',                 # Pa
        }
    )
    #
    # temperature to Celsius to Kelvin
    values['t2m'] = [m.temperature.CtoF(x) for x in  values['tas']]
    values.drop('tas', axis=1, inplace=True)
    #
    # cloud cover octa to 1
    values['tcc'] = [float(x) / 8. for x in values['clt']]
    values.drop('clt', axis=1, inplace=True)
    #
    # relative humidity % to 1
    values['r2m'] = [float(x) / 100. for x in values['hurs']]
    values.drop('hurs', axis=1, inplace=True)

    logger.debug("got: %s" % values.keys())
    return values

# ----------------------------------------------------

def get_hostrada_weather(lat, lon, year, datafile=None) \
        -> (pd.DataFrame, float):
    """
    Get weather timeseries for the provided position
    from source HOSTRADA by DWD for the year provided and calulate
    cloud cover of non-high clouds (`lmcc`) and roughness
    length `z0` from "forecast surface roughness"

    :param lat: position latitude in degrees
    :type lat: float
    :param lon: position laongitude  in degrees
    :type lon: float
    :param year: get data from this calendar year
    :type year: int
    :param datafile: (optional) read from this HOSTRADA data file
    :type datafile: str | None
    :return: weather timeseries as dataframe and surface roughness in m.
        The index of the dataframe is the measurement time as `datetime64`,
        the columns are:

        ======  ========= =============================
        column   unit     comment
        ======  ========= =============================
        'time'   UTC
        'ff'     m/s      wind speed at 10m height
        'dd'     degrees  wind direction
        'sp'     Pa       surface air pressure (QFE)
        't2m'    K        air temperature at 2 m height
        'r2m'    %        relative humidity at 2 m height
        'tcc'    1        total cloud cover
        ======  ========= =============================

    :rtype: (pd.DataFrame, float)
    """
    ds = _datasets.dataset_get(
        _datasets.name_yearly("HOSTRADA", year)
    )
    if not ds.available:
        raise ValueError(f"Dataset not available: {ds.name}")
    if datafile is None:
        datafile = os.path.join(ds.path, ds.file_data)
    logging.info('reading data from; %s' % datafile)

    v = read_hostrada_nc(datafile, lat, lon)
    v.index = v['time']
    v.sort_index(inplace=True)

    # get roughness length from CORINE
    xg, yg = _geo.ll2gk(lat, lon)
    h = 3000.  # 3km used to construct dataset by DWD (Kräheman. 2015)
    z0 = None
    try:
        z0 = _corine.roughness_austal(xg, yg, h)
    except RuntimeError as e:
        logger.warning(f'cannot get roughness from austal configuration: '
                       f' {e}')
    if z0 is None:
        try:
            z0 = _corine.roughness_web(xg, yg, h)
            if z0 <= 0.:   # lookup failed
                z0 = None
        except Exception as e:
            logger.warning(f'cannot get roughness online, '
                           f'the error was: {e}')
    if z0 is None:
        logger.error(f'cannot get any roughness length')


    res = v.filter(['time',  # UTC
                    'ff',  # m/s
                    'dd',  # deg
                    'sp',  # Pa
                    't2m',  # K
                    'r2m',  # 1
                    'tcc',  # 1
                    ])
    logger.debug("got: %s" % res.keys())
    logger.debug("z0 : %s" % z0)

    return res, z0

# ----------------------------------------------------

def get_dwd_weather(lat: float, lon: float, year:int,
                    station: int = None, datafile:str = None
                    ) -> (pd.DataFrame, float):
    """
    Get weather timeseries for the provided position
    from source DWD for the year provided.
    Units are converted  and calulate
    cloud cover of non-high clouds (`lmcc`) and roughness
    length `z0` from "forecast surface roughness"

    :param lat: position latitude in degrees
    :type lat: float
    :param lon: position laongitude  in degrees
    :type lon: float
    :param year: get data from this calendar year
    :type year: int
    :param station: (optional) DWD station number
    :type station: int
    :param datafile: (optional) read from this data file
    :type datafile: str | None
    :return: weather timeseries as dataframe and surface roughness in m.
        The index of the dataframe is the measurement time as `datetime64`,
        the columns are:

        ======  ========= =============================
        column   unit     comment
        ======  ========= =============================
        'time'   UTC
        'ff'     m/s      wind speed at 10m height
        'dd'     degrees  wind direction
        'sp'     Pa       surface air pressure (QFE)
        't2m'    K        air temperature at 2 m height
        'r2m'    1        relative humidity at 2 m height
        'tcc'    1        total cloud cover
        'cbh'    m        cloud base height above ground
        'cty'             cloud type (2-letter code)
        'fsr'    m        forecast surface roughness
        'tp'     mm       total precipitation per hour
        ======  ========= =============================

    :rtype: (pd.DataFrame, float)
    """
    ds = _datasets.dataset_get("DWD")
    if not ds.available:
        
        raise ValueError(f"Dataset not available: {ds.name}")
    if datafile is None:
        datafile = os.path.join(ds.path, ds.file_data)
    logging.info('reading data from; %s' % datafile)
    if station is None:
        _, _, _, nam, station = _geo.read_dwd_stationinfo(
            station=None, pos_lat=lat, pos_lon=lon, datafile=datafile)
        logger.info(f"selected nearest station {nam}")
    else:
        _, _, _, nam = _geo.read_dwd_stationinfo(
            station, datafile=datafile)
    with zipfile.ZipFile(datafile,
                         mode='r') as zf:
        df = pd.read_csv(filepath_or_buffer=zf.open(
            '%05i.csv' % station, mode='r'),
            index_col='time', parse_dates=True,
            engine='python')
    logger.debug('done reading')
    #
    #  treat the data ------------------------------------------------
    #
    # select data from year
    df = df[df.index.year == year]
    #
    # rename / convert units
    data = pd.DataFrame(index=df.index)
    # wind direction 990 means "undetermined"/"umlaufender Wind"
    data['dd'] = df['D'].df(data['D'] == 990., np.nan)  # deg
    data['ff'] = df['F']  # m/s
    data['sp'] = df['P0'] * 100.  # hPa -> Pa
    data['t2m'] = df['TT_TU']  # °C
    data['r2m'] = df['RF_TU'] / 100.  # % -> 1
    data['tcc'] = df['V_N'] / 8.  # octa -> 1
    data['cbh'] = df['V_S1_HHS']  # m
    data['cty'] = ['//' if (pd.isna(x) or x == '-1') else x
                   for x in df['V_S1_CSA']]  # SNYOP key
    data['tp'] = df['R1']  # mm
    #
    #  treat the metadata --------------------------------------------
    #
    # get wind sensor height from metadata
    za = df['windgeschwindigkeit_geberhoehe ueber grund [m]']
    za_values = set(list(za))
    # if sensor height changed that year:
    if len(za_values) > 1:
        raise ValueError('change in anemometer setup in year: %d' % year)
    elif pd.notna(za.values[0]):
        z_a = za.values[0]
    else:
        logging.warning('wind measurement height unknown, ' +
                        'assuming 10m standard height')
        z_a = 10.

    z0 = dis.z0_verkaik(z_a, speed=df['F'],
                                gust=df['FX_911'], dirct=df['D'])
    logging.info("roughness length: %5f" % z0)

    data = data.filter(['time',  # UTC
                        'ff',  # m/s
                        'dd',  # deg
                        'sp',  # Pa
                        't2m',  # K
                        'r2m',  # 1
                        'tcc',  # 1
                        'cbh',  # m
                        'cty',  # code
                        'tp',  # mm
                        'fsr',  # m
                        ])

    logger.debug("got: %s" % data.keys())
    logger.debug("z0 : %s" % z0)
    return data, z0


# -------------------------------------------------------------------------
def austal_weather(args):

    """
    This is the main function implementing the command 'weather'.

    The function processes weather data based on the provided arguments
    and retrieves weather observations from various sources.

    :param args: A dictionary containing the following keys:

        - dwd (str or None): DWD station ID, used to retrieve station information.
        - wmo (str or None): WMO station ID, used to retrieve station information.
        - gk (list of float or None): Gauss-Krüger coordinates [rechts, hoch].
        - ut (list of float or None): UTM coordinates.
        - ll (list of float or None): Latitude and longitude coordinates.
        - ele (float or None): Elevation information.
        - year (int): Year for which the weather data is required.
        - output (str): Output name for the results.
        - source (str): Source of the weather data (e.g., "ERA5", "CERRA", "DWD").
        - prec (bool): Flag indicating whether precipitation data should be included.

    :type args: dict

    :raises ValueError: If an unknown source is provided.
    """
    logger.debug("args: %s" % format(args))

    if args.get('read-extracted', None) is not None:
        csv_name = args['read-extracted']
        lat, lon, ele, z0, source, stat_nam, obs = \
            _tools.read_extracted_weather(csv_name)

        year = obs.index.year[0]
        logger.debug("year: %s" % year)

    else:
        lat, lon, ele, stat_no, stat_nam = (
            _geo.evaluate_location_opts(args))
        logging.info('selected position: %.2f %.2f (%s)' %
                     (lat, lon, format(stat_nam)))

        year = int(args['year'])
        logger.debug("year: %s" % year)

        source = args['source']
        if source == "ERA5":
            wind_variant = args.get('wind-variant', None)
            obs, z0 = get_era5_weather(lat, lon, year, wind_variant)
        elif source == "CERRA":
            obs, z0 = get_cerra_weather(lat, lon, year)
        elif source == "HOSTRADA":
            obs, z0 = get_hostrada_weather(lat, lon, year)
            if z0 is None and args.get('z0, None') is None:
                raise RuntimeError(f'cannot determine roughness lenght '
                                   f'automatically.\n'
                                   f'Use option `--z0` to provide '
                                   f'the value.')
        elif source == "DWD":
            if not _datasets.dataset_get(source).available:
                raise ValueError(f"source {source} not available")
            path = _datasets.dataset_get(source).path
            obs, z0 = get_dwd_weather(lat, lon, year, stat_no, path)
        else:
            raise ValueError("source not implemented: %s" % source)

        # override roughness length if given
        if (user_z0 := args.get('z0, None')) is not None:
            logger.info('Roughness length provided by the source ({z0}m) '
                        'by user-provided value ({user_z0}m).')
            z0 = user_z0

    rechts, hoch = _geo.ll2gk(lat, lon)
    if ele is None:
        if args.get("ele", None) is not None:
            ele = float(args["ele"])
        else:
            logger.warning('no elevation info. Assuming sea level. ' +
                           'You should consider providing -e')
            ele = 0.

    nam = args['output']
    logger.debug("rechts: %s, hoch: %s" % (rechts, hoch))
    logger.debug("lat: %s, lon: %s" % (lat, lon))
    logger.debug("elevation: %s" % (ele))

    if args.get('write-extracted', False):
        csv_name = 'extracted_weather.csv'
        logger.info('writing raw weather data to: %s' % csv_name)
        with open(csv_name, 'w') as f:
            f.write('# %.4f %.4f %.1f %.3f %s, %s\n' %
                    (lat, lon, ele, z0, source, format(stat_nam)))
            obs.to_csv(f, float_format='%.2f', index=False, na_rep='-999')

    logger.debug(str(obs.iloc[0:2]))

    methods_available = []

    # 10-m wind speed for the correct roughness length
    logger.debug('v10')
    obs['v10'] = dis.vdi_3872_6_standard_wind(obs['ff'],
                                              hap=10.0 + 7. * z0,
                                              z0p=z0)

    # air density
    if all([x in obs.columns for x in ['sp', 't2m']]):
        logger.debug('rho')
        obs['rho'] = m.humidity.gas_rho(p=obs['sp'], T=obs['t2m'])

    # virtual temperature
    if all([x in obs.columns for x in ['sp', 't2m', 'r2m']]):
        logger.debug('d2m')
        obs['Tv'] = [m.humidity.Humidity(t=t, p=p, rh=rh).tvirt()
                     for t, p, rh in
                     zip(obs['t2m'], obs['sp'], obs['r2m'])]
        obs['d2m'] = [m.humidity.Humidity(t=t, p=p, rh=rh).td()
                     for t, p, rh in
                     zip(obs['t2m'], obs['sp'], obs['r2m'])]
    elif all([x in obs.columns for x in ['sp', 't2m', 'd2m']]):
        logger.debug('Tv')
        obs['Tv'] = [m.humidity.Humidity(t, p, td).tvirt()
                     for t, p, td in
                     zip(obs['t2m'], obs['sp'], obs['d2m'])]
    # air density
    if 'fsr' not in obs.columns:
        logger.debug('fill fsr')
        obs['fsr'] = z0
    else:
        logger.debug('fsr ok')

    # estimate cbh if do not know anything about the clouds
    if all([x not in obs.columns for x in ['cbh', 'cty']]):
        logger.debug('estimate cbh')
        # Henning's Formula
        obs['cbh'] = [(t - d) * 123.
                      for t, d in zip(obs['t2m'], obs['d2m'])]


    # Obukhov length
    if all([x in obs.columns for x in ['ff', 'fsr', 'rho',
                                       'Tv', 'sshf', 'slhf']]):
        logger.debug('Lo')
        # calculate u* from "ff" and roughness
        # instead of model-provided "zust"
        obs['ust'] = (
                obs['ff'] * kappa / (np.log((10 + 7 * obs['fsr']) / obs['fsr']))
        )
        obs['Lo'] = dis.obukhov_length(
            ust=obs['ust'], rho=obs['rho'], Tv=obs['Tv'],
            H=obs['sshf'], E=obs['slhf'])
        #  if ...:
        #     obs[['time', 'v10', 'rho', 'Tv', 'Lo', 'ust']].to_csv(
        #         'calculated_L_%05i_%04i.csv' % (stat_no, year),
        #         float_format='%.2f', index=False, na_rep='-999')

    #
    # kms -----------------------------
    if all([x in obs.columns for x in ['v10', 'tcc']]):
        logger.info('Method: kms')
        methods_available.append('kms')
        if 'cty' in obs:
            cty = obs['cty']
        elif 'lmcc' in obs and 'tcc' in obs:
            cty = cloud_type_from_cover(tcc=obs['tcc'], lmcc=obs['lmcc'])
        else:
            cty = None
        obs['kms'] = dis.klug_manier_scheme_2017(
            obs.index, obs['v10'], obs['tcc'],
            lat, lon, ele, cty=cty
        )
    #
    # kmo -----------------------------
    if all([x in obs.columns for x in ['v10', 'tcc']]):
        logger.info('Method: kmo')
        methods_available.append('kmo')
        cty = obs['cty'] if 'cty' in obs else None
        obs['kmo'] = dis.klug_manier_scheme_1992(
            obs.index, obs['v10'], obs['tcc'],
            lat, lon, cty=cty)
        del cty
    #
    # k2o -----------------------------
    if (all([x in obs.columns for x in ['v10', 'tcc']]) and
        any([x in obs.columns for x in ['cbh', 'cty']])):
        logger.info('Method: k2o')
        methods_available.append('k2o')
        cbh = obs['cbh'] if 'cbh' in obs else None
        cty = obs['cty'] if 'cty' in obs else None
        obs['k2o'] = dis.klug_manier_scheme_2017(
            obs.index, obs['v10'], obs['tcc'],
            lat, lon, ele, cbh=cbh, cty=cty)
        del cbh, cty
    #
    # pts -----------------------------
    if all([x in obs.columns for x in ['ff', 'tcc', 'cbh']]):
        logger.info('Method: pts')
        methods_available.append('pts')
        obs['pts'] = dis.pasquill_taylor_scheme(
            obs.index, obs['ff'], obs['tcc'], lat, lon, obs['cbh'])
    #
    # kmc -----------------------------
    if all([x in obs.columns for x in ['fsr', 'Lo']]):
        logger.info('Method: kmc')
        methods_available.append('kmc')
        obs['kmc'] = dis.stabilty_class(
            'KM', obs.index, obs['fsr'], obs['Lo'].copy())
    #
    # pgc -----------------------------
    if all([x in obs.columns for x in ['fsr', 'Lo']]):
        logger.info('Method: pgc')
        methods_available.append('pgc')
        pg = dis.stabilty_class(
            'PG', obs.index, obs['fsr'], obs['Lo'])
        # convert to corresponding AK number (class F&G->1)
        obs['pgc'] = [max((1, 7 - x)) for x in pg]

    #
    # create hour-complete data frame for output
    logger.debug('create w')
    w = pd.DataFrame(index=pd.date_range(start=obs.index[0],
                                         end=obs.index[-1],
                                         freq='1h'))
    #
    # fill hour-complete data frame with data
    logger.debug('fill w')
    obs = obs.drop(columns='time', errors='ignore')
    w['time'] = w.index.to_series
    data = w.join(obs, how='left')
    #
    # where wind speed is 0, wind direction must be 0, and vice versa
    # not to self:
    #       mask  = "replace, where cond is True"
    #       where = "replace, where cond is False"
    # and bring dd to range 0..360
    data['dd'] = np.remainder(
        data['dd'].mask(data['ff'] < 1., other=0.), 360.)
    data['ff'] = data['ff'].mask(
        (np.isnan(data['dd']) | data['dd'] < 1.), other=0.)

    #    print(pd.crosstab(data['kmc'],
    #                      data['pgc'],
    #                      margins = True))
    #
    #    print(skm.classification_report(data['kmc'], data['pgc']))
    logger.debug("methods_available: %s" % methods_available)
    for method in methods_available:
        if args.get('class-scheme',
                    DEFAULT_CLASS_SCHEME) in [method, 'all']:
            logger.debug('generating output for: ' + method)
            if args['prec']:
                df = pd.DataFrame({'FF': data['ff'],
                                   'DD': data['dd'],
                                   'KM': data[method],
                                   'PP': data['tp']},
                                  index=data.index)
                ak = readmet.akterm.DataFile(data=df, z0=z0,
                                             prec=True)
            else:
                df = pd.DataFrame({'FF': data['ff'],
                                   'DD': data['dd'],
                                   'KM': data[method]},
                                  index=data.index)
                ak = readmet.akterm.DataFile(data=df, z0=z0)
            outname = ('{:s}_{:s}_{:04d}_'.format(
                _tools.slugify(source),
                _tools.slugify(nam), year) +
                       method + '.akterm')
            logger.info('writing output file: %s' % outname)
            ak.write(outname)
    #
    return

# -------------------------------------------------------------------------

# noinspection PyMissingOrEmptyDocstring
def add_options(subparsers):

    default_year = 2003
    known_sources = _datasets.SOURCES_WEATHER

    #
    # command line args
    #
    pars_wea = subparsers.add_parser(
        name='weather',
        help='Extract atmospheric time series for AUSTAL ' +
             'from various sources',
        formatter_class=_tools.SmartFormatter,
    )
    pars_wea.add_argument(dest="output", metavar="NAME", nargs='?',
                          help="file name to store data in."
                          )
    pars_wea = _tools.add_location_opts(pars_wea, stations=True)
    pars_wea.add_argument('-s', '--source',
                        metavar="CODE",
                        nargs=None,
                        choices=known_sources,
                        default=known_sources[0],
                        help='select the source for the weather data. ' +
                             'Known ``CODE`` values are ' +
                             ' '.join(known_sources) +
                             ' Defaults to ' +
                             known_sources[0])
    pars_wea.add_argument('-y', '--year', dest='year',
                        metavar='YEAR',
                        nargs=None,
                        help='year of interest [%04i]' % default_year)

    pars_wea.add_argument('-e', '--elevation', dest='ele',
                        metavar='METERS',
                        help='surface elevation. '
                             'An approximate value is sufficient' +
                             'only allowed with -L, -G, -U.')

    pars_wea.add_argument('-p', '--precip', dest='prec',
                          action='store_true',
                          help='add precipitation columns to output file')

    adv_wea = pars_wea.add_argument_group('advanced options')
    adv_wea.add_argument('--class-scheme',
                         dest='class-scheme',
                         choices=['all', 'kms', 'kmo', 'k2o', 'pts',
                                  'kmc', 'pgc'],
                         default=DEFAULT_CLASS_SCHEME,
                         help='Choose the method how stability classes'
                              'are derived from the weather data.'
                              'Possible values: %(choices)s. '
                              '[%(default)s]\n'
                              '  - kms: Klug/Manier scheme (after VDI 3782'
                              ' Part 6, issued Apr 2017) calculated from '
                              'date, time, wind speed, total cloud cover, '
                              'and cloud type of the lowest cloud layer\n'
                              '  - kmo: Klug/Manier scheme (after VDI 3782'
                              ' Part 1, issued 1992) calculated from '
                              'date, time, wind speed, total cloud cover,'
                              'and cloud type of the lowest cloud layer\n'
                              '  - k2o: Klug/Manier scheme (after VDI 3782'
                              ' Part 6, issued Apr 2017) calculated from '
                              'date, time, wind speed, total cloud cover,'
                              'and cloud base height (alternatively'
                              'cloud type of the lowest cloud layer)\n'
                              '  - pts: Pasquill/Turner scheme (after '
                              'EPA-454/R-99-005, issued 2000) calculated '
                              'from date, time, wind speed, '
                              'total cloud cover, '
                              'and cloud type of lowest cloud layer\n'
                              '  - kmc: classify the model-derived Obukhov'
                              'length into stability classes using the '
                              'class boundaries of the Klug/Manier scheme '
                              '(after TA-Luft, 2021 issued 1992)\n'
                              '  - pgc: classify the model-derived Obukhov'
                              'length into stability classes using the '
                              'class boundaries of the Pasquill/Gifford '
                              'stability classes '
                              '(scraped from Golder, 1972)\n'
                              )
    adv_wea.add_argument('--inter-variant',
                         dest='inter-variant',
                         choices=['weighted', 'nearest', 'mean'],
                         default=DEFAULT_INTER_VARIANT,
                         help='Controls the interpolation of gridded data '
                              'to the position specified. '
                              'Possible values: %(choices)s. '
                              '[%(default)s]\n'
                              '  - nearest: take model values from nearest'
                              'grid point\n'
                              '  - mean: arithmetic mean of the model '
                              'values at the three nearest grid poinst\n'
                              '  - weighted: barycentric mean (weighted '
                              'by distance) of the model '
                              'values at the three nearest grid poinst\n')
    adv_wea.add_argument('--read-extracted',
                         dest='read-extracted',
                         metavar="FILE",
                         help='Save time by re-reading extracted weather '
                              'data form a saved file. '
                              )
    adv_wea.add_argument('-x', '--write-extracted',
                          dest='write-extracted',
                          action='store_true',
                          help='write full extracted weather data '
                               'to an extra file')
    adv_wea.add_argument('--wind-variant',
                          dest=DEFAULT_WIND_VARIANT,
                          choices=['fixed_057', 'fixed_010', 'model_mean',
                                   'model_uv10', 'model_fsr'],
                          default='model_uv10',
                          help=('Controls how the 10-m wind is calculated'
                                'from ERA5 reanaysis data.'
                                'possible values: %(choices)s. '
                                '[%(default)s]\n'
                                '  - fixed_057: '
                                'from friction velocity using a fixed '
                                'roughness length :math:`z_0` = 0.57 m\n'
                                '  - fixed_010: '
                                'from friction velocity using a fixed '
                                'roughness length :math:`z_0` = 0.10 m\n'
                                ' - model_fsr: '
                                'from friction velocity using the instant '
                                '``forecast surface roughness`` '
                                'from the model for each hour\n'
                                ' - model_mean: '
                                'from friction velocity using the mean '
                                '``forecast surface roughness`` '
                                'from the model, averaged '
                                'over the whole data period\n'
                                ' - model_uv10: '
                                'use the ``10-m wind`` provided by the '
                                'model\n')
                         )
    adv_wea.add_argument('--z0',
                         dest='z0',
                         default=None,
                         help=f"roughness length at the position of the "
                              f"measurement used for calculation of "
                              f"the effective anemometer height. "
                              f"Overrides the value provided by the "
                              f"data source. Ignored if value is None. "
                              f"[%(default)s]"
                         )
    return pars_wea

# =========================================================================

def main(args):
    """
    This is the main routine that processes the input arguments and calls the main working function `austal_weather`.

    :param dict args: A dictionary containing the following keys:
        - dwd (str or None): DWD option, mutually exclusive with 'wmo' and required with 'ele'.
        - wmo (str or None): WMO option, mutually exclusive with 'dwd' and required with 'ele'.
        - ele (str or None): Element option, required with either 'dwd' or 'wmo'.
        - year (int or None): Year option, required with '-L', '-G', '-U', '-D', or '-W'.
        - output (str or None): Output name, required with '-L', '-G', '-U', '-D', or '-W'.
        - station (str or None): Station option, only valid with 'dwd' or 'wmo'.

    :raises SystemExit: If mutually exclusive options are provided or required options are missing.
    """
    if ((args['dwd'] is not None or args['wmo'] is not None)
            and args['ele'] is not None):

        logger.critical("options -D and -W are mutually exclusive with -e")
        sys.exit(1)
    # if ((args['dwd'] is None and args['wmo'] is None)
    #         and args['station'] is not None):
    #     logger.critical("options -w is only valid with -D or -W")
    #     sys.exit(1)
    if args['year'] is None:
        logger.critical("options -y is required with -L, -G, -U, -D or -W")
        sys.exit(1)
    if args['output'] is None:
        logger.critical("options NAME is required with -L, -G, -U, -D or -W")
        sys.exit(1)

    available_weather = _datasets.find_weather_data()
    if available_weather is None or len(available_weather) == 0:
        logger.warning("No available weather data in config file,"
                       "trying to search weather data. \n"
                       "Run configure_autaltools to collect the "
                       "available weather data infomation once.")
        available_weather = _datasets.find_weather_data()
        if len(available_weather) == 0:
            logger.error("No available weather data found.")
            sys.exit(1)

    ds_name = _datasets.name_yearly(args['source'], int(args['year']))
    if not ds_name in available_weather:
        logger.critical(f"dataset not available: {ds_name}")
        sys.exit(1)


    logger.info(os.path.basename(__file__) + ' version: ' + __version__)
    #
    # call the main working function
    austal_weather(args)

# =========================================================================
