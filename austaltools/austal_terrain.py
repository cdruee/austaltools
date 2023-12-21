#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Mar 20 09:57:48 2022

@author: clemens
"""
import logging
import argparse
import os
import tempfile

from osgeo import gdal
from osgeo import osr
try:
    from . import _tools
except ImportError:
    import _tools

try:
    from ._version import __version__
except ImportError:
    from _version import __version__

logging.basicConfig()
logger = logging.getLogger()

# -------------------------------------------------------------------------

KNOWN_DEMS = ["GTOPO30", "DGM25-RP", "GLO-30"]
STORAGE_PATH = data_path = os.path.join(os.path.dirname(__file__), 'data')
DEM_FMT = "%s.lzw.tif"

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

def cli() -> dict:
    """
    command line interface

    :return: conf (dict)
    """

    default_dem = KNOWN_DEMS[1]
    default_extent = 6.

    parser = argparse.ArgumentParser(
        description='get AUSTAL terrain data')
    parser.add_argument(dest="center_lon", metavar="X",
                        help="Center point eastward coordinate. "
                        )
    parser.add_argument(dest="center_lat", metavar="Y",
                        help="Center point northward coordinate."
                        )
    parser.add_argument(dest="output", metavar="NAME",
                        help="file name to store data in."
                        )
    cspars = parser.add_mutually_exclusive_group()
    cspars.add_argument('-L', '--ll',
                        dest="coords",
                        action='store_const',
                        const="lonlat",
                        default="lonlat",
                        help='X and Y are given as Longitude and ' +
                             'Latitude, respectively. ' +
                             'This is the default.')
    cspars.add_argument('-G', '--gk',
                        dest="coords",
                        action='store_const',
                        const="gk",
                        default="lonlat",
                        help='X and Y are given in Gauß-Krüger zone 3' +
                             'coordinates: X = `Rechtswert`, ' +
                             'Y = `Hochwert`. ')
    cspars.add_argument('-U', '--utm',
                        dest="coords",
                        action='store_const',
                        const="utm",
                        default="lonlat",
                        help='X and Y are given in UTM Zone 32N' +
                             'coordinates: X = `easting`, ' +
                             'Y = `northing`.')
    parser.add_argument('-s', '--source',
                        metavar="CODE",
                        nargs='?',
                        choices=KNOWN_DEMS,
                        default=default_dem,
                        help='code for the source digital elevation ' +
                             'model (DEM). Known DEMs are: ' +
                             ' ' . join(KNOWN_DEMS) + ' ' +
                             'Defaults to ' + default_dem)
    parser.add_argument('-e', '--extent',
                        metavar="KM",
                        nargs='+',
                        default=default_extent,
                        help='extent of the extracted area in km ' +
                             '(side length of the sqare)' +
                             'Defaults to {}'.format(default_extent))

    verb = parser.add_mutually_exclusive_group()
    verb.add_argument('--debug', dest='verb', action='store_const',
                      const=logging.DEBUG, help='show informative output')
    verb.add_argument('-v', '--verbose', dest='verb', action='store_const',
                      const=logging.INFO, help='show detailed output')
    args = parser.parse_args()

    # set logging level
    if args.verb is not None:
        logger.setLevel(args.verb)
    else:
        logger.setLevel(logging.WARNING)
    logger.info(os.path.basename(__file__) + ' version: ' + __version__)

    logger.debug(format(args))
    return vars(args)

# -------------------------------------------------------------------------

def gk2ll(rechts, hoch):
    transform = osr.CoordinateTransformation(GK, LL)
    return transform.TransformPoint(rechts , hoch)

# -------------------------------------------------------------------------
def ll2gk(lon, lat):
    transform = osr.CoordinateTransformation(LL, GK)
    return transform.TransformPoint(lon, lat)

# -------------------------------------------------------------------------

def ut2gk(east, north):
    transform = osr.CoordinateTransformation(UT, GK)
    return transform.TransformPoint(east , north)

# -------------------------------------------------------------------------

def main():
    args = cli()
    logger.debug("args: %s" % format(args))

    if args["coords"] == "gk":
        rechts, hoch = float(args['center_lon']), float(args['center_lat'])
        lon, lat, _ = gk2ll(rechts, hoch)
    elif args["coords"] == "utm":
        rechts, hoch = ut2gk(
            float(args['center_lon']), float(args['center_lat']))
        lon, lat, _ = gk2ll(rechts, hoch)
    elif args["coords"] == "lonlat":
        lon, lat = float(args['center_lon']), float(args['center_lat'])
        rechts, hoch, _ = ll2gk(lat, lon)
    else:
        raise ValueError("unknown coords: %s" % args['coords'])
    logger.debug("rechts: %s, hoch: %s" % (rechts, hoch))
    logger.debug("lon: %s, lat: %s" % (lon, lat))
    size = args['extent'] * 1000  # km -> m
    logger.debug("size: %s m" % size)
    source = args['source']
    #
    # show notice
    #
    logger.info('reading topography data: %s' % source)
    print('data copyright notice:')
    with open(os.path.join(STORAGE_PATH,
                           "%s.NOTICE.txt" % source), "r") as f:
        for x in f.readlines():
            print (x)
    #
    # load dataset
    #
    file_name = os.path.join(STORAGE_PATH,DEM_FMT % source)
    logger.debug("file_name: %s" % file_name)
    dataset = gdal.Open(file_name)

    gt = dataset.GetGeoTransform()
    # GT(0) x-coordinate of the upper-left corner of the upper-left pixel.
    # GT(1) w-e pixel resolution / pixel width.
    # GT(2) row rotation (typically zero).
    # GT(3) y-coordinate of the upper-left corner of the upper-left pixel.
    # GT(4) column rotation (typically zero).
    # GT(5) n-s pixel resolution / pixel height (negative value for a north-up image).
    logger.debug("gt: %s" % format(gt))

    bounds = (rechts - size/2., # minX
              hoch - size/2.,   # minY
              rechts + size/2., # maxX,
              hoch + size/2.,   # maxY
              )
    logger.debug("bounds: %s" % format(bounds))
    tif_name = tempfile.mkstemp(suffix=".tif")[1]
    logger.debug("tempfile: %s" % tif_name)
    gdal.Warp(tif_name, dataset,
              dstSRS="EPSG:5677",
              outputBounds=bounds,
              )
    out_name = '%s.grid' % args['output']
    logger.debug("out: %s" % out_name)
    gdal.Translate(out_name, tif_name, format='AAIGrid')
    #
    # clean up
    #
    if logger.getEffectiveLevel() > logging.DEBUG:
        os.remove(tif_name)


# -------------------------------------------------------------------------

if __name__ == "__main__":
    main()
