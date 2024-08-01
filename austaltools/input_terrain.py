#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Mar 20 09:57:48 2022

@author: clemens
"""
import logging
import os
import tempfile
from importlib import resources

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    from osgeo import gdal

try:
    from . import _tools
    from . import _datasets
    from ._version import __title__
except ImportError:
    import _tools
    import _datasets
    from _version import __title__

logging.basicConfig()
logger = logging.getLogger()

# -------------------------------------------------------------------------

KNOWN_DEMS = _datasets.KNOWN_DEMS
STORAGE_DIR = "terrain"
DEM_FMT = '%s.elevation.nc'
STORAGE_AUX_FILES = resources.files(__title__ + '.data')


# -------------------------------------------------------------------------


def find_terrain_data():
    datasets = {}
    for ds in _datasets.DATASETS:
        # is ds a terrain dataset?
        if ds.storage == 'terrain':
            # is it locally available (i.e. downloaded already?):
            if ds.available:
                datasets[ds.name] = ds.path
    return datasets


# -------------------------------------------------------------------------


def show_notice(storage_path, source):
    noticefile = os.path.join(storage_path,
                           "%s.NOTICE.txt" % source)
    print('data copyright notice:')
    if os.path.exists(noticefile):
        with open(noticefile, "r") as f:
            for x in f.readlines():
                print(x)


# -------------------------------------------------------------------------
def main(args: dict):
    """
    This is the main working function

    :param args: the command line arguments as dictionary
    :type args: dict
    """
    logger.debug("args: %s" % format(args))

    if args["gk"] is not None:
        rechts, hoch = [float(x) for x in args['gk']]
        lat, lon, _ = _tools.gk2ll(rechts, hoch)
    elif args["ut"] is not None:
        rechts, hoch, _ = _tools.ut2gk(*[float(x) for x in args['ut']])
        lat, lon, _ = _tools.gk2ll(rechts, hoch)
    elif args["ll"] is not None:
        lat, lon = [float(x) for x in args['ll']]
        rechts, hoch, _ = _tools.ll2gk(lat, lon)
    else:
        return

    if args["source"] in AVAILABLE_DEMS:
        source = args["source"]
        storage_path = AVAILABLE_DEMS[source]
    else:
        raise ValueError("Source must be one of the available sources")

    logger.debug("rechts: %s, hoch: %s" % (rechts, hoch))
    logger.debug("lon: %s, lat: %s" % (lon, lat))
    size = float(args['extent']) * 1000  # km -> m
    logger.debug("size: %s m" % size)
    source = args['source']
    #
    # show notice
    #
    logger.info('reading topography data: %s' % source)
    show_notice(storage_path=storage_path, source=source)
    #
    # load dataset
    #
    file_name = os.path.join(storage_path, DEM_FMT % source)
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

    bounds = (rechts - size / 2.,  # minX
              hoch - size / 2.,  # minY
              rechts + size / 2.,  # maxX,
              hoch + size / 2.,  # maxY
              )
    logger.debug("bounds: %s" % format(bounds))
    tif_name = tempfile.mkstemp(suffix=".tif")[1]
    logger.debug("tempfile: %s" % tif_name)
    gdal.Warp(tif_name, dataset,
              dstSRS="EPSG:5677",
              outputBounds=bounds,
              )
    out_name = '%s.grid' % args['output']
    logger.info("writing output to: %s" % out_name)
    gdal.Translate(out_name, tif_name, noData=-9999., format='AAIGrid')
    #
    # clean up
    #
    if logger.getEffectiveLevel() > logging.DEBUG:
        os.remove(tif_name)
    #
    return


# =========================================================================
# init at import:

AVAILABLE_DEMS = find_terrain_data()
