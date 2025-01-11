#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This module provides funtionailty to generate
terrain input files for simulations with the
German regulatory dispersion model AUSTAL [AST31]_
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

STORAGE_DIR = "terrain"
"""
keyword that marks terrain datasets and is the name of the subdirectory 
of each storage locaton, where terrain data are stored
"""
DEM_FMT = '%s.elevation.nc'
"""
string format that forms the data file name from the ID of a dataset
"""
STORAGE_AUX_FILES = resources.files(__title__ + '.data')
"""
location where auxiliary files (e.g. license texts and dataset definitions)
that are part of the module are stored
"""


# -------------------------------------------------------------------------


def find_terrain_data():
    """
    Searches all known storage locations for the known terrain datasets
    and yields a list of the datasets available locally.

    :return: dataset IDs of the locally available datasets
    :rtype: list[str]
    """
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
    """
    Shows a notice to the user when a dataset is accessed,
    if this is required by the original supplier of the dataset.

    :param storage_path: path to the dataset files
    :type storage_path: str
    :param source: dataset ID
    :type source: str

    """
    noticefile = os.path.join(storage_path,
                           "%s.NOTICE.txt" % source)
    logger.debug('noticefile: %s' % noticefile)
    if os.path.exists(noticefile):
        print('IMPORTANT: data copyright notice:')
        with open(noticefile, "r") as f:
            for x in f.readlines():
                print(x)
    else:
        logger.debug('(no noticefile)')

# -------------------------------------------------------------------------

def main(args: dict):
    """
    This is the main working function.

    :param args: The command line arguments as a dictionary.
    :type args: dict
    :param args["gk"]: Gauß-Krüger coordinates
      as a list of two floats [rechts, hoch].
    :type args["gk"]: list[float, float]
    :param args["ut"]: UTM coordinates
      as a list of three floats [rechts, hoch, zone].
    :type args["ut"]: list[float, float]
    :param args["ll"]: Latitude and longitude
      as a list of two floats [lat, lon].
    :type args["ll"]: list[float, float]
    :param args["source"]: The source of the terrain data,
      must be one of the available source IDs.
    :type args["source"]: str
    :param args["extent"]: The extent of the area
      to be extracted in kilometers.
    :type args["extent"]: float
    :param args["output"]: The output file name without extension.
    :type args["output"]: str

    :note:

    - ``args["gk"]``, ``args["ut"]``, and ``args["ll"]``
      are mutally exclusive.

    :raises ValueError: If the source is not one of the available sources.
    """
    logger.debug("args: %s" % format(args))

    lat, lon, ele, stat_no, stat_nam = _tools.evaluate_location_opts(args)
    rechts, hoch, _ = _tools.ll2gk(lat, lon)

    if args['source'] in AVAILABLE_DEMS:
        source = args['source']
        storage_path = AVAILABLE_DEMS[source]
    else:
        raise ValueError(f"Not an available source: {args['source']}")

    logger.debug("rechts: %s, hoch: %s" % (rechts, hoch))
    logger.debug("lon: %s, lat: %s" % (lon, lat))
    size = float(args['extent']) * 1000  # km -> m
    logger.debug("size: %s m" % size)
    source = args['source']
    #
    # show notice
    #
    print('reading terrain data: %s' % source)
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

    # -------------------------------------------------------------------------

def add_options(subparsers):

    if len(AVAILABLE_DEMS) > 0:
        default_dem = list(AVAILABLE_DEMS)[0]
    else:
        default_dem = None
    default_extent = 6.

    pars_ter = subparsers.add_parser(
        name='terrain',
        help='generate terrain input for AUSTAL'
    )
    pars_ter.add_argument(dest="output", metavar="NAME",
                          help="file name to store data in.",
                          )

    pars_ter = _tools.add_location_opts(parser=pars_ter)

    pars_ter.add_argument('-s', '--source',
                          metavar="CODE",
                          nargs=None,
                          choices=AVAILABLE_DEMS,
                          default=default_dem,
                          help='code for the source digital elevation ' +
                               'model (DEM). Known DEMs are: ' +
                               ' '.join(AVAILABLE_DEMS) +
                               ' Defaults to ' + str(default_dem))
    pars_ter.add_argument('-e', '--extent',
                          metavar="KM",
                          nargs=None,
                          default=default_extent,
                          help='extent of the extracted area in km ' +
                               '(side length of the sqare)' +
                               'Defaults to {}'.format(default_extent))
    return pars_ter

# =========================================================================
# init at import:

AVAILABLE_DEMS = find_terrain_data()
"""
List of locally available DEMs (filled upon imorting the module)

:meta hide-value:
"""
