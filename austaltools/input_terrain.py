#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This module provides funtionailty to generate
terrain input files for simulations with the
German regulatory dispersion model AUSTAL [AST31]_
"""
import logging
import os
import sys
import tempfile
from importlib import resources

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    from osgeo import gdal

from . import _datasets
from . import _geo
from . import _plotting
from . import _tools
from ._metadata import __title__

logging.basicConfig()
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
SUBCOMMAND = "terrain"
"""
the keyword under which the subcommand provided by this module appears
"""
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
DEFAULT_DEM = 'GTOPO30'
""" default source digital elevation model (DEM) code """
DEFAULT_EXTENT = 5.
""" default extent of the extracted area in km (side length of the square) """
DEFAULT_CRS = 'ut'
""" default coordinate reference system of the output ('ut' or 'gk') """


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

    :param args: The command line arguments as a dictionary, with keys:

      - ``gk``: Gauß-Krüger coordinates as a list of two floats
        [rechts, hoch]. Mutually exclusive with ``ut`` and ``ll``.
      - ``ut``: UTM coordinates as a list of three floats
        [rechts, hoch, zone]. Mutually exclusive with ``gk`` and ``ll``.
      - ``ll``: Latitude and longitude as a list of two floats
        [lat, lon]. Mutually exclusive with ``gk`` and ``ut``.
      - ``source``: The source of the terrain data, must be one of the
        available source IDs. Defaults to ``DEFAULT_DEM`` if missing or
        ``None``.
      - ``extent``: The extent of the area to be extracted in
        kilometers. Defaults to ``DEFAULT_EXTENT`` if missing or
        ``None``.
      - ``crs``: coordinate reference system of the output, 'gk' or
        'ut'. Defaults to ``DEFAULT_CRS`` if missing or ``None``.
      - ``output``: The output file name without extension. Required,
        no default: raises ``ValueError`` if missing or ``None``.

    :type args: dict

    :raises ValueError: If ``output`` is missing, or if ``source`` or
      ``crs`` is not one of the available/valid values.
    """
    logger.debug("args: %s" % format(args))

    output = args.get('output', None)
    if output is None:
        raise ValueError('output is required (file name to store data in)')

    lat, lon, ele, stat_no, stat_nam = _geo.evaluate_location_opts(args)

    available_dems = _datasets.find_terrain_data()
    if available_dems is None or len(available_dems) == 0:
        logger.warning("No available terrain data in config file,"
                       "trying to search terrain data. \n"
                       "Run configure_autaltools to collect the "
                       "available terrain data infomation once.")
        available_dems = _datasets.find_weather_data()
        if len(available_dems) == 0:
            logger.error("No available terrain data found.")
            sys.exit(1)

    ds_name = args.get('source', None)
    if ds_name is None:
        ds_name = DEFAULT_DEM
    if ds_name not in available_dems:
        logger.critical(f"Dataset not available: {ds_name}")
        sys.exit(1)

    storage_path = available_dems[ds_name]

    logger.debug("lon: %s, lat: %s" % (lon, lat))
    extent = args.get('extent', None)
    if extent is None:
        extent = DEFAULT_EXTENT
    size = float(extent) * 1000  # km -> m
    logger.debug("size: %s m" % size)
    #
    # show notice
    #
    print('reading terrain data: %s' % ds_name)
    show_notice(storage_path=storage_path, source=ds_name)
    #
    # load dataset
    #
    file_name = os.path.join(storage_path, DEM_FMT % ds_name)
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

    tif_handle, tif_name = tempfile.mkstemp(suffix=".tif")
    # close file handle so that file is not open and there is
    # no permission issue when gdal tries to open it by name
    # in contrast to tempfile.TemporaryFile this does not remove
    # the file. we need to remove ist explicitly by os.remove!
    os.close(tif_handle)
    logger.debug("tempfile: %s" % tif_name)

    crs = args.get('crs', None)
    if crs is None:
        crs = DEFAULT_CRS
    if crs == 'gk':
        rechts, hoch = _geo.ll2gk(lat, lon)
        epsg_code = f"EPSG:{_geo.GK.GetAuthorityCode(None)}"
    elif crs == 'ut':
        rechts, hoch = _geo.ll2ut(lat, lon)
        epsg_code = f"EPSG:{_geo.UT.GetAuthorityCode(None)}"
    else:
        raise ValueError("Unknown CRS: %s" % crs)

    bounds = (rechts - size / 2.,  # minX
              hoch - size / 2.,  # minY
              rechts + size / 2.,  # maxX,
              hoch + size / 2.,  # maxY
              )
    logger.debug("rechts: %s, hoch: %s" % (rechts, hoch))
    logger.debug("bounds: %s" % format(bounds))

    gdal.Warp(tif_name, dataset, dstSRS=epsg_code, outputBounds=bounds)

    out_name = '%s.grid' % output
    logger.info("writing output to: %s" % out_name)
    gdal.Translate(out_name, tif_name,
                   noData=-9999.,
                   format='AAIGrid',
                   creationOptions={'DECIMAL_PRECISION':2}
                   )
    #
    # clean up
    #
    if logger.getEffectiveLevel() > logging.DEBUG:
        os.remove(tif_name)
    #
    return

    # -------------------------------------------------------------------------

def add_options(subparsers):

    pars_ter = subparsers.add_parser(
        name=SUBCOMMAND,
        help='generate terrain input for AUSTAL'
    )
    pars_ter.add_argument(dest='output', metavar='NAME',
                          help="file name to store data in.",
                          )

    pars_ter = _tools.add_location_opts(parser=pars_ter)

    pars_ter.add_argument('-c', '--crs',
                          metavar='CODE',
                          nargs=None,
                          choices=['ut', 'gk'],
                          default=DEFAULT_CRS,
                          help="coordinate reference system of the output: "
                               "gk: Gauss-Krüger (zone 3), "
                               "ut: UTM (zone 32U).  "
                               "Defaults to %(default)s")
    pars_ter.add_argument('-e', '--extent',
                          metavar='KM',
                          nargs=None,
                          default=DEFAULT_EXTENT,
                          help="extent of the extracted area in km "
                               "(side length of the sqare)"
                               "Defaults to %(default)s")
    pars_ter.add_argument('-s', '--source',
                          metavar='CODE',
                          nargs=None,
                          # choices=AVAILABLE_DEMS,
                          default=DEFAULT_DEM,
                          help="code for the source digital elevation "
                               "model (DEM). "
                               " Defaults to %(default)s"
                          )
    return pars_ter

# =========================================================================
