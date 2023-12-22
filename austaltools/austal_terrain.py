#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Mar 20 09:57:48 2022

@author: clemens
"""
import logging
import argparse
import glob
import gzip
import os
import shutil
import tarfile
import tempfile
from urllib.request import urlretrieve

from importlib import resources
from osgeo import gdal
from osgeo import osr
from osgeo_utils import gdal_merge

try:
    from . import _tools
except ImportError:
    import _tools

try:
    from ._version import __version__, __title__
except ImportError:
    from _version import __version__, __title__

logging.basicConfig()
logger = logging.getLogger()

# -------------------------------------------------------------------------

KNOWN_DEMS = ["GTOPO30", "DGM25-RP", "GLO-30"]
STORAGE_LOCATIONS = ["/opt/%s" % __title__,
                     os.path.expanduser("~/.local/share/%s" % __title__),
                     os.path.expanduser("~/.%s" % __title__),
                     "."
                     ]
STORAGE_DIR = "terrain"
STORAGE_PATH = None      # will be filled lazy
DEM_FMT = "%s.lzw.tif"
STORAGE_AUX_FILES = resources.files('data')

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

def download_GTOPO30(path):

    support = ("https://data.rda.ucar.edu/ds758.0/support/"
                       + "GTOPO30support.tar.gz")
    download = ("https://data.rda.ucar.edu/ds758.0/elevtiles/" +
                "%s.DEM.gz")
    tiles = ["W020N90"]
    # known_tiles = \
    # "W180N90 W140N90 W100N90 W060N90 W020N90 E020N90 E060N90 E100N90"\
    # "E140N90 W180N40 W140N40 W100N40 W060N40 W020N40 E020N40 E060N40"\
    # "E100N40 E140N40 W180S10 W140S10 W100S10 W060S10 W020S10 E020S10"\
    # "E060S10 E100S10 E140S10 W180S60 W120S60 W060S60 W000S60 E060S60"\
    # "E120S60 ".split()
    # get the single archive that holds the supportive
    # files for all tiles
    logger.debug("downloading ... %s" % support)
    support_file , _ = urlretrieve(
        support, os.path.basename(support))
    with tarfile.open(support_file) as support_tar:
        # no get every tile we want
        for tile in tiles:
            # extract the matching supportive files
            to_extract = [x.name for x in support_tar.getmembers()
                         if tile in x.name]
            support_tar.extractall(members=to_extract)
            # now download the actual data file for the tile
            download_url = download % tile
            logger.debug("downloading ... %s" % download_url)
            tile_file, _ = urlretrieve(
                download_url, os.path.basename(download_url))
            # expand the terrain data holding file *.DEM
            # and convert it to a GeoTiff file
            tile_dem = tile_file.replace(".gz", "")
            tile_tif = tile_dem.replace(".DEM", ".tif")
            logger.debug("... decompressing %s" % tile_dem)
            with gzip.open(tile_file,'rb') as tf:
                with open(tile_dem, 'wb') as td:
                    shutil.copyfileobj(tf, td, length=16*1024)
            logger.debug("... converting to %s" % tile_tif)
            gdal.Warp(destNameOrDestDS=tile_tif,
                      srcDSOrSrcDSTab=tile_dem,
                      format="GTiff")
    # merge the GeoTiff Files from all tiles into one file
    target = os.path.join(path,DEM_FMT % "GTOPO30")
    if os.path.exists(target):
        logger.info("removing old source file")
        os.remove(target)
    logger.debug("merging tiles ...")
    gdal_merge.main(["", "-co", "compress=lzw",
                     "-o", target
                     ] + glob.glob("*.tif"))
    logger.debug("... done")

    return

# -------------------------------------------------------------------------

def download_GLO_30(path):

    download_dir = ("https://prism-dem-open.copernicus.eu/" +
                    "pd-desk-open-access/prismDownload/" +
                    "COP-DEM_GLO-30-DGED__2022_1/")
    file_fmt = "Copernicus_DSM_10_N%02i_00_E%03i_00.tar"

    for lat in range(47,54):
        for lon in range(5,16):
            url = download_dir + file_fmt % (lat,lon)
            logger.debug("downloading ... %s" % url)
            tar_file, _ = urlretrieve(url, os.path.basename(url))
            name_root = tar_file.replace(".tar", "")
            with tarfile.open(tar_file) as tf:
                to_extract = [x for x in tf.getmembers()
                              if name_root+"/DEM/" in x.name]
                for x in to_extract:
                    # remove path from name of tar member to extract
                    x.name = os.path.basename(x.name)
                    logger.debug("... extracting %s" % x.name)
                    # now extract tar member to current dir
                    tf.extract(x, '.')
    # merge the GeoTiff Files from all tiles into one file
    target = os.path.join(path,DEM_FMT % "GLO-30")
    if os.path.exists(target):
        logger.info("removing old source file")
        os.remove(target)
    logger.debug("merging tiles ...")
    gdal_merge.main(["", "-co", "compress=lzw",
                     "-o", target,
                     "-ot","Int16"] +
                     glob.glob("Copernicus_*.tif"))
    logger.debug("... done")

    return

# -------------------------------------------------------------------------

def download_DGM25_RP(path):

    url = "https://vermkv.service24.rlp.de/opendat/dgm25/dgm25.zip"
    logger.debug("downloading ... %s" % url)
    zip_file, _ = urlretrieve(url, os.path.basename(url))
    logger.debug("extracting ... %s" % zip_file)
    shutil.unpack_archive(zip_file)
    for tile_xyz in glob.glob("*.xyz"):
        logger.debug("converting tile ... %s" % tile_xyz)
        tile_tif = tile_xyz.replace(".xyz",".tif")
        try:
            gdal.Warp(destNameOrDestDS=tile_tif,
                  dstSRS="EPSG:5677",
                  srcDSOrSrcDSTab=tile_xyz,
                  srcSRS="EPSG:25832",
                  format="GTiff")
        except Exception as e:
            logger.error(str(e))
    # merge the GeoTiff Files from all tiles into one file
    target = os.path.join(path,DEM_FMT % "DGM25-RP")
    if os.path.exists(target):
        logger.info("removing old source file")
        os.remove(target)
    logger.debug("merging tiles ...")
    gdal_merge.main(["", "-co", "compress=lzw",
                     "-o", target,
                     ] + glob.glob("DGM25_*.tif"))
    logger.debug("... done")

    return

# -------------------------------------------------------------------------

def download_dem(dem, path):
    logger.info("downloading terrain source %s" % dem)
    success = True
    pwd = os.getcwd()
    with tempfile.TemporaryDirectory() as temp_dir:
        os.chdir(temp_dir)
        try:
            if dem == "GTOPO30":
                download_GTOPO30(path)
            elif dem == "GLO-30":
                download_GLO_30(path)
            elif dem == "DGM25-RP":
                download_DGM25_RP(path)
            else:
                logger.error("unknown dataset to download %s" % dem)
                success = False
        except Exception as e:
            logger.error(str(e))
            success = False
    # return before clean up
    os.chdir(pwd)
    return success


# -------------------------------------------------------------------------


def provide_terrain_data(storage_path=None, force_download=False):
    extension = DEM_FMT % ""
    datasets = []
    if storage_path is not None:
        # path is prescribed
        if not os.path.isdir(storage_path):
            raise ValueError("terrain storage not found at: %s" %
                             storage_path)
    else:
        # path is not prescribed: search
        for location in reversed(STORAGE_LOCATIONS):
            # start from current dir, user dirs to system dirs
            # so user can override system installation
            directory = os.path.join(location, STORAGE_DIR)
            if os.path.isdir(directory):
                storage_path = directory
                break
    # did we find it?
    if storage_path is not None:
        logger.info("terrain data storage found at: %s" % storage_path)
        # if a location is found, we are happy
        # but does it contain any data?
        for file in os.listdir(storage_path):
            if file.endswith(extension):
                datasets.append(file.replace(extension, ""))
        if len(datasets) == 0:
            logger.error("No terrain data found in storage")
    if storage_path is None or force_download:
        # no location was found, we must create one:
        logger.warning("no preexisting terrain data storage found")
        for location in STORAGE_LOCATIONS:
            directory = os.path.join(location, STORAGE_DIR)
            if os.access(directory, os.W_OK):
                # exists and is writable, keep
                storage_path = directory
                break
            try:
                # does not exist: try to make it
                os.makedirs(directory)
                # if we are here, we succeeded making directory, keep
                storage_path = directory
                break
            except OSError:
                pass
        if storage_path is None:
            # we couldn't create any location WTF
            raise OSError("Could not create terrain storage dir")
        for aux_path in STORAGE_AUX_FILES.iterdir():
            aux_file = os.path.basename(aux_path)
            if aux_file.startswith('_'):
                continue
            logger.debug('copying auxiliary file: %s' % aux_file)
            shutil.copyfile(aux_path,
                            os.path.join(storage_path, aux_file))
        logger.warning("terrain data storage created: %s" % storage_path)
        # now fill the storage with data
        for dem in KNOWN_DEMS:
            if (os.path.exists(os.path.join(storage_path, DEM_FMT % dem)) and
                    not force_download):
                logger.info("dataset found in storage: %s" % dem)
                datasets.append(dem)
            else:
                success = download_dem(dem, storage_path)
                if success:
                    logger.error("successfully downloaded dataset %s" % dem)
                    datasets.append(dem)
                else:
                    logger.error("dataset %s failed to download" % dem)
    return storage_path, datasets

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
    parser.add_argument('--list-sources',
                        action='store_true',
                        help='list available terrein sources ' +
                             'and exit')
    parser.add_argument('--force-download',
                        action='store_true',
                        help='force dowloadinf the terrain sources ' +
                             'even if they exist.')

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


def main():
    args = cli()
    logger.debug("args: %s" % format(args))

    global STORAGE_PATH
    STORAGE_PATH, sources = provide_terrain_data(
        force_download=args['force_download'])
    if args["list_sources"]:
        print(" ".join(sources))
        return


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
