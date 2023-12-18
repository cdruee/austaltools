#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Mar 20 09:57:48 2022

@author: clemens
"""
import logging
import argparse
import os
import re
import shlex
import json
import tempfile

import numpy as np
import readmet.dmna
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

KNOWN_DEMS = [
    "SRTM", "DGM25"
]
STORAGE_PATH = {
    "SRTM": "/local/data/druee/datensaetze/srtm/srtm3/eurasia/",
    "DGM25": "/localdata/druee/software/austaltools/data/dgm25_rp.tif",
    # file name dgm25_rp.tif made from downloaded xyz files by:
    # $ for X in *.xyz; do gdalwarp -s_srs EPSG:25832 -t_srs EPSG:5677 $X ${X%.xyz}.tif; done
    # $ gdal_merge.py -o dgm25_rp.tif DGM25_*.tif
    # $ rm DGM25_*tif
}
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
    parser.add_argument(dest="center_lon", metavar="LON",
                        help="Center point longitude."
                        )
    parser.add_argument(dest="center_lat", metavar="LAT",
                        help="Center point latitude."
                        )
    parser.add_argument(dest="output", metavar="NAME",
                        help="file name to store data in."
                        )
    cspars = parser.add_mutually_exclusive_group()
    cspars.add_argument('-G', '--gk',
                        action='store_true',
                        help='LON and LAT are given in Gauß-Krüger zone 3' +
                             'coordinates: LON = `Rechtswert`, ' +
                             'LAT = `Hochwert`. ')
    cspars.add_argument('-U', '--utm',
                        action='store_true',
                        help='LON and LAT are given in UTM Zone 32N' +
                             'coordinates: LON = `easting`, ' +
                             'LAT = `northing`.')
    parser.add_argument('-s', '--source',
                        metavar="CODE",
                        nargs='+',
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

    if "gk" in args and args["gk"]:
        rechts, hoch = float(args['center_lon']), float(args['center_lat'])
        lon, lat, _ = gk2ll(rechts, hoch)
    elif "utm" in args and args["utm"]:
        rechts, hoch = ut2gk(
            float(args['center_lon']), float(args['center_lat']))
        lon, lat, _ = gk2ll(rechts, hoch)
    else:
        lon, lat = float(args['center_lon']), float(args['center_lat'])
        rechts, hoch, _ = ll2gk(lon, lat)
    logger.debug("rechts: %s, hoch: %s" % (rechts, hoch))
    logger.debug("lon: %s, lat: %s" % (lon, lat))

    file_name = STORAGE_PATH[args['source']]
    logger.debug("file_name: %s" % (file_name))
    dataset = gdal.Open(file_name)

    gt = dataset.GetGeoTransform()
    # GT(0) x-coordinate of the upper-left corner of the upper-left pixel.
    # GT(1) w-e pixel resolution / pixel width.
    # GT(2) row rotation (typically zero).
    # GT(3) y-coordinate of the upper-left corner of the upper-left pixel.
    # GT(4) column rotation (typically zero).
    # GT(5) n-s pixel resolution / pixel height (negative value for a north-up image).
    logger.debug("gt: %s" % format(gt))
    x_center = int((rechts - gt[0]) / gt[1])
    y_center = int((hoch - gt[3]) / gt[5])
    logger.debug("x_center: %s, y_center: %s" % (x_center, y_center))

    size = args['extent'] * 1000  # km -> m
    x_count = int(1. + size / gt[1])
    y_count = int(1. + size / gt[5])
    x_topleft = int(x_center - x_count / 2)
    y_topleft = int(y_center - y_count / 2)

    # data = dataset.ReadAsArray()
    # projection = dataset.GetProjection()
    #
    # tmp_name = tempfile.mktemp(suffix='.tif')
    # out_name = '%s.grid' % args['output']
    # subset = data[x_topleft:x_topleft+x_count,
    #          y_topleft:y_topleft + y_count]
    # logger.debug("projection: %s" % (projection))
    # driver = gdal.GetDriverByName('GTiff')
    # out = driver.Create(tmp_name, abs(x_count), abs(y_count), 1, gdal.GDT_Byte)
    # out.SetProjection(projection)
    # out.SetGeoTransform((
    #     gt[0] + x_topleft*gt[1],# GT(0) x-coordinate of the upper-left corner of the upper-left pixel.
    #     gt[1],                  # GT(1) w-e pixel resolution / pixel width.
    #     gt[2],                  # GT(2) row rotation (typically zero).
    #     gt[3] + x_topleft*gt[5],# GT(3) y-coordinate of the upper-left corner of the upper-left pixel.
    #     gt[4],                  # GT(4) column rotation (typically zero).
    #     gt[5],                  # GT(5) n-s pixel resolution / pixel height (negative value for a north-up image).
    # ))
    # out.data = subset
    # logger.debug("tmp_name: %s" % (tmp_name))
    # out.GetRasterBand(1).WriteArray(subset)
    # logger.debug("out: %s" % (out_name))
    # gdal.Translate(out_name, out,format='AAIGrid')

    out_name = '%s.grid' % args['output']
    logger.debug("out: %s" % (out_name))
    gdal.Translate(out_name, dataset, format='AAIGrid',
                   projWin=[rechts - size/2.,hoch + size/2.,
                            rechts + size/2.,hoch - size/2.])



# -------------------------------------------------------------------------

if __name__ == "__main__":
    main()
