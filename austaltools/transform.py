#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This module provides convenience funtions to
translate between ccordinate systems.
If the 'austal.txt' configuration file is
in the working directory, conversion from
model coordinates to real world coordinates is
also possible
"""
import logging
import os

if os.getenv('BUILDING_SPHINX', 'false') == 'false':
    from osgeo import osr

from . import _datasets
from . import _fetch_dwd
from . import _geo
from . import _tools
from . import _plotting
from ._metadata import __version__
from . import _wmo_metadata

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------

# NOTE: `model_origin()` used to live here. It has been moved to
# `_geo.py` (as `_geo.model_origin`), since the same origin lookup is
# also needed by other subcommands (e.g. `windprofile`) via
# `_geo.resolve_position`. Call it as `_geo.model_origin(...)`.

# -------------------------------------------------------------------------

def crs_bounds(crs):
    """
    return corners of area of use of a coordinate refernce system

    :param crs:  coordinate refernce system object
    :type crs: osgeo.osr.SpatialReference
    :return: area of use (lower left, upper right (LLUR)
        in lattitude / logitude)
    :rtype: list[float]
    """
    aou = crs.GetAreaOfUse()
    logging.debug('getting bounds of CRS %s' % crs.GetName())
    return[aou.west_lon_degree, aou.south_lat_degree,
           aou.east_lon_degree, aou.north_lat_degree]

# -------------------------------------------------------------------------

def in_bounds(lat, lon, crs):
    """
    check if a position is insidethe area of use
    of a coordinate refernce system

    :param lat: position latitude
    :type lat: float
    :param lon: position longitude
    :type lon: float
    :param crs:  coordinate refernce system object
    :type crs: osgeo.osr.SpatialReference
    :return: True if in area of use
    :rtype: bool
    """
    llur = crs_bounds(crs)
    logging.debug('checking (%f, %f) inside bounds: %s' %
                  (lat, lon, repr(llur)))
    return ((llur[0] <= lon <= llur[2]) and
            (llur[1] <= lat <= llur[3]))

# -------------------------------------------------------------------------

def main(args):
    """
    This is the main working function.

    :param args: The command line arguments as a dictionary, with keys:

      - ``xy``: Position given in model coordinates [x, y] (relative
        to the model origin), to be converted into geographic
        coordinates. Mutually exclusive with ``gk``, ``ut``, ``ll``,
        ``dwd``, and ``wmo``. Defaults to ``None`` if missing.
      - ``dwd``: DWD station ID. Defaults to ``None`` if missing.
      - ``wmo``: WMO station ID. Defaults to ``None`` if missing.
      - ``gk``: Gauß-Krüger coordinates as a list of two floats
        [rechts, hoch]. Defaults to ``None`` if missing.
      - ``ut``: UTM coordinates as a list of two floats [east, north].
        Defaults to ``None`` if missing.
      - ``ll``: Latitude and longitude as a list of two floats
        [lat, lon]. Defaults to ``None`` if missing.
      - ``decimals``: if true, print UTM and Gauss-Krüger coordinates
        as floating-point numbers with decimals. Defaults to ``False``
        if missing or ``None``.

      Exactly one of ``xy``, ``dwd``, ``wmo``, ``gk``, ``ut``, ``ll``
      must be given.

    :type args: dict

    :raises ValueError: If none of ``xy``, ``dwd``, ``wmo``, ``gk``,
      ``ut``, or ``ll`` is given, if ``xy`` is combined with any of
      ``gk``, ``ut``, ``ll``, ``dwd``, or ``wmo``, or on various
      internal/configuration errors (see messages).
    """
    xy = args.get('xy', None)
    dwd = args.get('dwd', None)
    wmo = args.get('wmo', None)
    gk = args.get('gk', None)
    ut = args.get('ut', None)
    ll = args.get('ll', None)

    GK_REFS = {x: osr.SpatialReference() for x in [1,2,3,4,5]}
    # DHDN / 3-degree Gauss-Kruger zone 1 (E-N), https://epsg.io/5680
    GK_REFS[1].ImportFromEPSG(5680)
    # DHDN / 3-degree Gauss-Kruger zone 2 (E-N), https://epsg.io/5676
    GK_REFS[2].ImportFromEPSG(5676)
    # DHDN / 3-degree Gauss-Kruger zone 3 (E-N), https://epsg.io/5677
    GK_REFS[3].ImportFromEPSG(5677)
    # DHDN / 3-degree Gauss-Kruger zone 4 (E-N), https://epsg.io/5678
    GK_REFS[4].ImportFromEPSG(5678)
    # DHDN / 3-degree Gauss-Kruger zone 5 (E-N), https://epsg.io/5679
    GK_REFS[5].ImportFromEPSG(5679)


    lat = lon = None
    rechts = hoch = None
    east = north = None
    rx, ry, rs = _geo.model_origin()

    if xy is not None:
        if any(x is not None for x in [gk, ut, ll, dwd, wmo]):

            raise ValueError('-M is mutaually exclusive with -D, -G, -L, '
                             '-U, and -W')
        mx, my = [float(x) for x in xy]
        if rs is None:

            raise ValueError('no AUSTAL configuration file')
        elif rs == 'ND':

            raise ValueError('no reference position defined in '
                             'AUSTAL configuration file')
        elif rs == 'GK':
            rechts = rx + mx
            hoch = ry + my
            lat, lon = _geo.gk2ll(rechts, hoch)
            east, north, _ = _geo.gk2ut(rechts, hoch)
        elif rs == 'UT':
            east = rx + mx
            north = ry + my
            rechts, hoch, _ = _geo.ut2gk(east, north)
            lat, lon = _geo.ut2ll(east, north)
        else:
            raise ValueError(f'internal error rs={rs}')

    if dwd is not None:
        storage_dwd = _datasets.dataset_get("DWD").path
        if storage_dwd is None:

            raise ValueError("Dataset DWD is not available, "
                       "download or assemble it.")
        station = int(dwd)
        with _fetch_dwd.DWDStationinfo(storage_dwd) as si:
            lat, lon, ele = si.position(station)
        rechts, hoch = _geo.ll2gk(lat, lon)
        east, north = _geo.ll2ut(lat, lon)
    elif wmo is not None:
        lat, lon, ele, nam = _wmo_metadata.wmo_stationinfo(wmo)
        rechts, hoch = _geo.ll2gk(lat, lon)
        east, north = _geo.ll2ut(lat, lon)
    elif gk is not None:
        rechts, hoch = [float(x) for x in gk]
        lat, lon = _geo.gk2ll(rechts, hoch)
        east, north = _geo.gk2ut(rechts, hoch)
    elif ut is not None:
        east, north = [float(x) for x in ut]
        rechts, hoch, _ = _geo.ut2gk(east, north)
        lat, lon = _geo.ut2ll(rechts, hoch)
    elif ll is not None:
        lat, lon = [float(x) for x in ll]
        rechts, hoch = _geo.ll2gk(lat, lon)
        east, north = _geo.ll2ut(lat, lon)
    elif xy is None:
        raise ValueError('a location is required: one of '
                         '-M, -D, -W, -G, -U, -L')

    decimals = args.get('decimals', None)
    if decimals is None:
        decimals = False
    if decimals:
        number_format = ' %-10.2f  %-10.2f'
    else:
        number_format = ' %-10.0f  %-10.0f'
    print("Latitude,   Longitude (WGS84):")
    print(" %-10.5f, %-10.5f " % (lat,lon))
    print("Rechtswert, Hochwert  (Gauss-Krüger Zone 3):")
    print(number_format % (rechts, hoch))
    print("Easting,    Northing  (UTM Zone 32):")
    print(number_format % (east, north))
    print("Rechtswert, Hochwert, Zone (Gauss-Krüger passende Zone):")
    crs = zone = None
    for k, v in GK_REFS.items():
        if in_bounds(lat, lon, v):
            crs = v
            zone = k
            logger.debug('in #%i' % zone)
            break
    if crs:
        transform = osr.CoordinateTransformation(_geo.LL, crs)
        gx, gy, _ = transform.TransformPoint(lat, lon)
        print((number_format + " %i") % (gx, gy, zone))
    else:
        print(" (position outside)")

    if rs in [None, 'ND']:
        pass
    else:
        if rs == 'GK':
            mx = rechts - rx
            my = hoch - ry
        elif rs == 'UT':
            mx = east - rx
            my = north -ry
        else:
            raise ValueError(f'internal error rs={rs}')
        print("model x   , model y   (AUSTAL coordinates in m):")
        print(" %-10.2f, %-10.2f " % (mx, my))

# -------------------------------------------------------------------------

def add_options(subparsers):

    pars_transf = subparsers.add_parser(
        name='transform',
        help='transfrom coordinates into other projections')
    pars_transf = _tools.add_location_opts(pars_transf, stations=True,
                                                       required=False)
    pars_transf.add_argument('-M', '--model',
                         metavar=("x", "y"),
                         dest="xy",
                         nargs=2,
                         default=None,
                         help='Transform position given in model '
                              'coordinats x and y (relative '
                              'to the model origin) into '
                              'geographic coordinates.')

    pars_transf.add_argument('-f', '--float',
                             dest='decimals',
                             action="store_true",
                             default=False,
                             help='Print UTM and Gauss-Krüger coordinates '
                                  'as floating-point numbers with decimals '
                                  'for more precision '
                                  '(Note that using floating-point numbers'
                                  'for the reference coordinates'
                                  'will cause AUSTAL to crash).')


    return pars_transf
