"""

Thisn module provides geo-position related functionality.

"""
import logging
import os

EARTH_RADIUS = 6371

if os.getenv('BUILDING_SPHINX', 'false') == 'false':
    import numpy as np
    import osgeo.osr as osr
    import pandas as pd

    try:
        osr.UseExceptions()
    except ImportError:
        pass

from . import _fetch_dwd
from . import _storage
from . import _wmo_metadata

logger = logging.getLogger()

# -------------------------------------------------------------------------

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    # WGS84 - World Geodetic System 1984, https://epsg.io/4326
    LL = osr.SpatialReference()
    LL.ImportFromEPSG(4326)
    # DHDN / 3-degree Gauss-Kruger zone 3 (E-N), https://epsg.io/5677
    GK = osr.SpatialReference()
    GK.ImportFromEPSG(5677)
    # # ETRS89 / UTM zone 32N, https://epsg.io/25832
    # # has easting of 500000
    # # -> yields x coordinates < 1.000.000
    # # but coordinates < 1.000.000 in .grid terrain file
    # # are not understood by austal
    # ETRS89 / UTM zone 32N (zE-N), https://epsg.io/4647
    # has easting of 32.500.000
    # -> yields x coordinates > 32.000.000
    # understood by austal
    UT = osr.SpatialReference()
    UT.ImportFromEPSG(4647)

# -------------------------------------------------------------------------

def gk2ll(rechts: float, hoch: float) -> (float, float):
    """
    Converts Gauss-Krüger rechts/hoch (east/north) coordinates
    (DHDN / 3-degree Gauss-Kruger zone 3 (E-N), https://epsg.io/5677)
    into Latitude/longitude  (WGS84, https://epsg.io/4326) position.

    :param rechts: "Rechtswert" (eastward coordinate) in m
    :type: float
    :param hoch: "Hochwert" (northward coordinate) in m
    :type: float
    :return: latitude in degrees, longitude in degrees, altitude in meters
    :rtype: float, float, float
    """
    transform = osr.CoordinateTransformation(GK, LL)
    lat, lon, zz = transform.TransformPoint(rechts, hoch)
    return lat, lon

# -------------------------------------------------------------------------

def ll2gk(lat: float, lon: float) -> (float, float):
    """
    Converts Latitude/longitude  (WGS84, https://epsg.io/4326) position
    into Gauss-Krüger rechts/hoch (east/north) coordinates
    (DHDN / 3-degree Gauss-Kruger zone 3 (E-N), https://epsg.io/5677).

    :param lat: latitude in degrees
    :type: float
    :param lon: longitude in degrees
    :type: float
    :return: "Rechtswert" (eastward coordinate) in m,
        "Hochwert" (northward coordinate) in m
    :rtype: float, float
    """
    transform = osr.CoordinateTransformation(LL, GK)
    x, y, z = transform.TransformPoint(lat, lon)
    return x, y

# -------------------------------------------------------------------------

def ut2ll(east: float, north:float) -> (float, float):
    """
    Converts UTM east/north coordinates
    (ETRS89 / UTM zone 32N, https://epsg.io/25832)
    into Latitude/longitude  (WGS84, https://epsg.io/4326) position.

    :param east: eastward UTM coordinate in m
    :type: float
    :param north: northward UTM coordinate in m
    :type: float
    :return: latitude in degrees, longitude in degrees, altitude in meters
    :rtype: float, float, float
    """
    transform = osr.CoordinateTransformation(UT, LL)
    lat, lon, zz = transform.TransformPoint(east, north)
    return lat, lon

# -------------------------------------------------------------------------

def ll2ut(lat: float, lon: float) -> (float, float):
    """
    Converts Latitude/longitude  (WGS84, https://epsg.io/4326) position
    into UTM east/north coordinates
    (ETRS89 / UTM zone 32N, https://epsg.io/25832)

    :param lat: latitude in degrees
    :type: float
    :param lon: longitude in degrees
    :type: float
    :return: "easting" (eastward coordinate) in m,
        "northing" (northward coordinate) in m
    :rtype: float, float
    """
    transform = osr.CoordinateTransformation(LL, UT)
    easting, nothing, zz = transform.TransformPoint(lat, lon)
    return easting, nothing

# -------------------------------------------------------------------------

def ut2gk(east: float, north:float) -> (float, float):
    """
    Converts UTM east/north coordinates
    (ETRS89 / UTM zone 32N, https://epsg.io/25832)
    into Gauss-Krüger rechts/hoch (east/north) coordinates
    (DHDN / 3-degree Gauss-Kruger zone 3 (E-N), https://epsg.io/5677).

    :param east: eastward UTM coordinate in m
    :type: float
    :param north: northward UTM coordinate in m
    :type: float
    :return: "Rechtswert" (eastward coordinate) in m,
        "Hochwert" (northward coordinate) in m,
        Altitude in m
    :rtype: float, float, float
    """
    transform = osr.CoordinateTransformation(UT, GK)
    rechts, hoch, zz = transform.TransformPoint(east, north)
    return rechts, hoch

# -------------------------------------------------------------------------

def gk2ut(rechts: float, hoch: float) -> (float, float):
    """
    Converts Gauss-Krüger rechts/hoch (east/north) coordinates
    (DHDN / 3-degree Gauss-Kruger zone 3 (E-N), https://epsg.io/5677)
    into UTM east/north coordinates
    (ETRS89 / UTM zone 32N, https://epsg.io/25832).

    :param rechts: "Rechtswert" (eastward coordinate) in m
    :type: float
    :param hoch: "Hochwert" (northward coordinate) in m
    :type: float
    :return: "easting" (eastward coordinate) in m,
        "northing" (northward coordinate) in m
    :rtype: float, float
    """
    transform = osr.CoordinateTransformation(GK, UT)
    easting, nothing, zz = transform.TransformPoint(rechts, hoch)
    return easting, nothing

# -------------------------------------------------------------------------

def evaluate_location_opts(args: dict):
    """
    get position from the command-line location options and
    if applicable the WMO station number of this position

    :param args: parsed arguments
    :type args: dict
    :return: position as lat, lon (WGS84) and rechts, hoch in Gauss-Krüger Band 3
       and WMO station number of this position (0 if not applicable)
    :rtype: float, float, float, float, int

    """
    station = 0
    ele = None
    nam = None
    if args.get("dwd", None) is not None:
        station = int(pd.to_numeric(args["dwd"]))
        with _fetch_dwd.DWDStationinfo() as si:
            lat, lon, ele = si.position(station)
            nam = si.name(station)
    elif args.get("wmo", None) is not None:
        lat, lon, ele, nam = _wmo_metadata.wmo_stationinfo(
            args["wmo"])
    elif args.get("gk", None) is not None:
        rechts, hoch = [float(x) for x in args['gk']]
        lat, lon = gk2ll(rechts, hoch)
    elif args.get("ut", None) is not None:
        rechts, hoch = ut2gk(*[float(x) for x in args['ut']])
        lat, lon = gk2ll(rechts, hoch)
    elif args.get("ll", None) is not None:
        lat, lon = [float(x) for x in args['ll']]
    else:
        lat, lon = None, None
    return lat, lon, ele, station, nam

# -------------------------------------------------------------------------

def spheric_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points
    (specified in decimal degrees) on a spheric earth.
    Reference:
    https://stackoverflow.com/a/29546836/7657658

    :param lat1: Position 1 latitude in degrees
    :type: float
    :param lon1: Position 1 longitude in degrees
    :type: float
    :param lat2: Position 2 latitude in degrees
    :type: float
    :param lon2: Position 2 longitude in degrees
    :type: float
    :returns: Great circle distance in km
    :rtype: float
    """
    rlat1 = np.radians(lat1)  # deg -> rad
    rlon1 = np.radians(lon1)  # deg -> rad
    rlat2 = np.radians(lat2)  # deg -> rad
    rlon2 = np.radians(lon2)  # deg -> rad

    dlon = rlon2 - rlon1  # rad
    dlat = rlat2 - rlat1  # rad
    a = (np.sin(dlat / 2.0) ** 2 +
         np.cos(rlat1) * np.cos(rlat2) * np.sin(dlon / 2.0) ** 2)
    c = 2 * np.arcsin(np.sqrt(a))
    km = EARTH_RADIUS * c  # km

    return km
