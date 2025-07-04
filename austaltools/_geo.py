"""

Thisn module provides geo-position related functionality.

"""
import logging
import os

if os.getenv('BUILDING_SPHINX', 'false') == 'false':
    import numpy as np
    import osgeo.osr as osr
    import pandas as pd

    try:
        osr.UseExceptions()
    except ImportError:
        pass

try:
    from . import _storage
    from . import _wmo_metadata
except ImportError:
    import _storage
    import _wmo_metadata

logger = logging.getLogger()

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
        lat, lon, ele, nam = read_dwd_stationinfo(station)
        rechts, hoch = ll2gk(lat, lon)
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

def read_dwd_stationinfo(station: int, pos_lat: float | None = None,
                         pos_lon: float | None = None,
                         datafile: str | None = None

                         ):
    """
     Reads information about a weather station from a dataset.

     This function retrieves metadata about a specific weather station from
     a dataset that is either provided or located in a default location. The
     dataset is expected to be a JSON file containing information about multiple
     weather stations, including their geographical coordinates, elevation, and
     names.

     :param station: The ID or identifier of the station whose information is
                     to be retrieved. If None, the nearest station to the provided
                     latitude and longitude coordinates is returned.
     :type station: str or None

     :param pos_lat: The latitude coordinate (in degrees) to search for the
                     nearest station when no station ID is provided. Should be
                     None if a station ID is specified.
     :type pos_lat: float or None

     :param pos_lon: The longitude coordinate (in degrees) to search for the
                     nearest station when no station ID is provided. Should be
                     None if a station ID is specified.
     :type pos_lon: float or None

     :param datafile: The path to the JSON file containing station information.
                      If not provided, a default path is used.
     :type datafile: str or None

     :return: A tuple containing the latitude, longitude, and elevation of the
              specified or nearest station, along with the station's name. If
              the nearest station is searched using coordinates, the index of
              that station in the dataset is also included in the returned tuple.
     :rtype: tuple(float, float, float, str) or tuple(float, float, float, str, int)

     :raises ValueError: If both station and coordinates (pos_lat and pos_lon)
                         are specified, if the specified station ID is not
                         found in the dataset, or if no station can be found
                         at the given coordinates.
    """
    if station is not None:
        if pos_lat is not None and pos_lon is not None:
            raise ValueError('lat and lon must be None ' +
                             'unless station is None')
    if datafile is None:
        datafile = os.path.join(_storage.DIST_AUX_FILES,
                                'dwd_stationlist.json')
    logging.info('reading data from; %s' % datafile)
    with open(datafile, mode='r') as f:
        sf = pd.read_json(f, orient='index', convert_dates=True)

    if station is not None:
        if station not in sf.index:
            raise ValueError('station not in datafile')
        srow = sf[station]
    else:
        sf['sdist'] = spheric_distance(
            sf['latitude'], sf['longitude'], pos_lat, pos_lon)
        srow = sf['sdist'].argmin()

    if srow is None:
        raise ValueError('station not found: %s' % station)
    lat = sf['latitude'][srow]
    lon = sf['longitude'][srow]
    ele = sf['elevation'][srow]
    nam = sf['name'][srow]
    logger.debug("station name: %s" % nam)
    if station is None:
        return lat, lon, ele, nam, int(srow)
    else:
        return lat, lon, ele, nam

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
    km = 6371 * c  # km

    return km
