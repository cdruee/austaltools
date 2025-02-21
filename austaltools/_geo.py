import os
import sys

import osgeo.osr as osr
import pandas as pd


try:
    osr.UseExceptions()
except:
    pass

try:
    from . import _datasets
    from . import _plotting
    from . import _wmo_metadata
except ImportError:
    import _datasets
    import _plotting
    import _wmo_metadata

# -------------------------------------------------------------------------

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    # WGS84 - World Geodetic System 1984, https://epsg.io/4326
    LL = osr.SpatialReference()
    LL.ImportFromEPSG(4326)
    # DHDN / 3-degree Gauss-Kruger zone 3 (E-N), https://epsg.io/5677
    GK = osr.SpatialReference()
    GK.ImportFromEPSG(5677)
    # ETRS89 / UTM zone 32N, https://epsg.io/25832
    UT = osr.SpatialReference()
    UT.ImportFromEPSG(25832)

# -------------------------------------------------------------------------

def gk2ll(rechts: float, hoch: float) -> (float, float, float):
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
    return transform.TransformPoint(rechts, hoch)

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
    return transform.TransformPoint(lat, lon)

# -------------------------------------------------------------------------

def ut2ll(east: float, north:float) -> (float, float, float):
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
    return transform.TransformPoint(east, north)

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
    return transform.TransformPoint(lat, lon)

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
    return transform.TransformPoint(east, north)


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
    return transform.TransformPoint(rechts, hoch)

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
        storage_dwd = _datasets.dataset_get("DWD").path
        if storage_dwd is None:
            sys.tracebacklimit = 0
            raise ValueError("Dataset DWD is not available, "
                       "download or assemble it.")
        station = int(pd.to_numeric(args["dwd"]))
        lat, lon, ele, nam = _plotting.read_dwd_stationinfo(
            station, datafile=storage_dwd)
        rechts, hoch, _ = ll2gk(lat, lon)
    elif args.get("wmo", None) is not None:
        lat, lon, ele, nam = _wmo_metadata.wmo_stationinfo(
            args["wmo"])
    elif args.get("gk", None) is not None:
        rechts, hoch = [float(x) for x in args['gk']]
        lat, lon, _ = gk2ll(rechts, hoch)
    elif args.get("ut", None) is not None:
        rechts, hoch, _ = ut2gk(*[float(x) for x in args['ut']])
        lat, lon, _ = gk2ll(rechts, hoch)
    elif args.get("ll", None) is not None:
        lat, lon = [float(x) for x in args['ll']]
    else:
        lat, lon = None
    return lat, lon, ele, station, nam
