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
from . import _tools
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
    lat, lon, zz = transform.TransformPoint(float(rechts), float(hoch))
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
    x, y, z = transform.TransformPoint(float(lat), float(lon))
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
    lat, lon, zz = transform.TransformPoint(float(east), float(north))
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
    easting, nothing, zz = transform.TransformPoint(float(lat), float(lon))
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
    rechts, hoch, zz = transform.TransformPoint(float(east), float(north))
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
    easting, nothing, zz = transform.TransformPoint(float(rechts), float(hoch))
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

def model_origin(conf: dict = None, path: str = None):
    """
    Determine the model origin, i.e. the geo-referenced position of
    the AUSTAL model coordinate x=0, y=0, from an AUSTAL configuration.

    Either `conf` (an already-parsed configuration, as returned by
    :func:`austaltools._tools.get_austxt`) or `path` (the file name of
    an ``austal.txt``/``austal2000.txt`` to read) may be given; if
    both are omitted, the configuration is read from ``austal.txt`` in
    the current directory (the default of
    :func:`austaltools._tools.get_austxt`). Passing an already-parsed
    `conf` avoids reading the configuration file a second time when
    the caller has already loaded it for other purposes.

    :param conf: AUSTAL configuration as returned by
        :func:`austaltools._tools.get_austxt`
    :type conf: dict, optional
    :param path: file name of the AUSTAL configuration file. Only used
        if `conf` is not given.
    :type path: str, optional
    :return: reference x, reference y, and reference coordinate system
        (``'GK'`` for Gauß-Krüger, ``'UT'`` for UTM, ``'ND'`` if the
        configuration does not define a reference position). If no
        configuration could be found at all (only possible if `conf`
        is not given), all three are ``None``.
    :rtype: (float|None, float|None, str|None)
    :raises ValueError: if the configuration contains an inconsistent
        or incomplete set of reference-position keys.
    """
    if conf is None:
        try:
            conf = _tools.get_austxt(path)
        except FileNotFoundError:
            return None, None, None
    xy_count = sum(x in conf for x in ["gx", "gy", "ux", "uy"])
    if xy_count == 0:
        return None, None, 'ND'
    elif xy_count > 2:
        raise ValueError('error in reference coordinates in austal.txt')
    if ("gx" in conf) and ("gy" in conf):
        return conf["gx"][0], conf["gy"][0], 'GK'
    elif ("ux" in conf) and ("uy" in conf):
        return conf["ux"][0], conf["uy"][0], 'UT'
    else:
        raise ValueError('inconsistent reference coordinates '
                         'in austal.txt')

# -------------------------------------------------------------------------

def resolve_position(args: dict, conf: dict = None, path: str = None):
    """
    Determine the model-grid position (x, y in m east-/northward of
    the model coordinate origin) requested on the command line, either
    from directly given model coordinates (``-M``/``--model``, parsed
    into ``args['xy']``) or from one of the location options added by
    :func:`austaltools._tools.add_location_opts` (``-L``, ``-G``,
    ``-U``, and, if enabled, ``-D``/``-W``).

    This centralises the position-resolution logic shared by the
    subcommands that accept a single point either as model coordinates
    or as a location (e.g. ``windprofile``, ``transform``), so it only
    needs to be maintained in one place.

    :param args: parsed command line arguments
    :type args: dict
    :param conf: AUSTAL configuration as returned by
        :func:`austaltools._tools.get_austxt`, if already available
    :type conf: dict, optional
    :param path: file name of the AUSTAL configuration file, used to
        determine the model origin if `conf` is not given
    :type path: str, optional
    :return: position as model coordinates x, y in m
    :rtype: (float, float)
    :raises ValueError: if neither or both kinds of position
        specification are given, or if a location is given but the
        AUSTAL configuration does not define a model-to-geographic
        reference position.
    """
    xy = args.get('xy', None)
    have_loc = any(args.get(k, None) is not None
                   for k in ('ll', 'gk', 'ut', 'dwd', 'wmo'))

    if xy is not None and have_loc:
        raise ValueError('position must be given either as model '
                         'coordinates (-M/--model) or as a location, '
                         'not both')

    if xy is not None:
        x, y = (float(v) for v in xy)
        return x, y

    if have_loc:
        lat, lon, ele, stat_no, stat_nam = evaluate_location_opts(args)
        rx, ry, rs = model_origin(conf=conf, path=path)
        if rs in (None, 'ND'):
            raise ValueError('no reference position (gx/gy or ux/uy) '
                             'defined in the AUSTAL configuration; '
                             'cannot convert a geographic location '
                             'into model coordinates. Use -M/--model '
                             'to give the position directly instead.')
        elif rs == 'GK':
            rechts, hoch = ll2gk(lat, lon)
            x = rechts - rx
            y = hoch - ry
        elif rs == 'UT':
            east, north = ll2ut(lat, lon)
            x = east - rx
            y = north - ry
        else:
            raise ValueError(f'internal error: rs={rs}')
        return x, y

    raise ValueError('no position given: use -M/--model or one of '
                     'the location options')

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
