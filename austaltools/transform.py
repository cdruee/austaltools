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

try:
    from . import _datasets
    from . import _geo
    from . import _tools
    from . import _plotting
    from ._metadata import __version__
    from . import _wmo_metadata
except ImportError:
    import _datasets
    import _geo
    import _tools
    import _plotting
    import _wmo_metadata
    from _version import __version__

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------

def model_origin(path=None):
    try:
        austxt = _tools.get_austxt(path)
        xy_count = sum([x in austxt for x in ["gx", "gy", "ux", "uy"]])
    except FileNotFoundError:
        austxt = {}
        xy_count = None

    if xy_count is None:
        rx = ry = rs = None
    elif xy_count == 0:
        rx = ry = None
        rs = 'ND'
    elif xy_count > 2:
        
        raise ValueError('error in reference coodinates in %s' %
                         os.path.basename(path))
    else:
        if ("gx" in austxt) and ("gy" in austxt):
            rx = austxt["gx"][0]
            ry = austxt["gy"][0]
            rs = 'GK'
        elif ("ux" in austxt) and ("uy" in austxt):
            rx = austxt["ux"][0]
            ry = austxt["uy"][0]
            rs = 'UT'
        else:
            raise ValueError('internal error')
    return rx, ry, rs

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
    rx, ry, rs = model_origin()

    if args["xy"] is not None:
        if any([(args[x] is not None)
                for x in ["gk", "ut", "ll", "dwd", "wmo"]]):
            
            raise ValueError('-M is mutaually exclusive with -D, -G, -L, '
                             '-U, and -W')
        mx, my = [float(x) for x in args["xy"]]
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

    if args["dwd"] is not None:
        storage_dwd = _datasets.dataset_get("DWD").path
        if storage_dwd is None:
            
            raise ValueError("Dataset DWD is not available, "
                       "download or assemble it.")
        station = int(args["dwd"])
        lat, lon, ele, nam = _geo.read_dwd_stationinfo(
            station, datafile=storage_dwd)
        rechts, hoch = _geo.ll2gk(lat, lon)
        east, north = _geo.ll2ut(lat, lon)
    elif args["wmo"] is not None:
        lat, lon, ele, nam = _wmo_metadata.wmo_stationinfo(args["wmo"])
        rechts, hoch = _geo.ll2gk(lat, lon)
        east, north = _geo.ll2ut(lat, lon)
    elif args["gk"] is not None:
        rechts, hoch = [float(x) for x in args['gk']]
        lat, lon = _geo.gk2ll(rechts, hoch)
        east, north = _geo.gk2ut(rechts, hoch)
    elif args["ut"] is not None:
        east, north = [float(x) for x in args['ut']]
        rechts, hoch, _ = _geo.ut2gk(east, north)
        lat, lon = _geo.ut2ll(rechts, hoch)
    elif args["ll"] is not None:
        lat, lon = [float(x) for x in args['ll']]
        rechts, hoch = _geo.ll2gk(lat, lon)
        east, north = _geo.ll2ut(lat, lon)


    decimals = args.get('decimals', False)
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
