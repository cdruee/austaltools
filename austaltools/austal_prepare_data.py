#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Mar 20 09:57:48 2022

@author: clemens
"""
import argparse
import csv
import glob
import gzip
import io
import logging
import os
import sys

import pip
import shutil
import tarfile
import tempfile
import zipfile
from importlib import resources
from urllib.request import urlretrieve

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    from osgeo import gdal
    from osgeo_utils import gdal_merge
    from multiprocessing import Pool
    import cdo

try:
    import cdsapi
except ImportError:
    pip.main(['install', 'cdsapi'])
    import cdsapi

try:
    import cdo
except ImportError:
    pip.main(['install', 'cdo'])
    import cdo

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

KNOWN_DEMS = ["DGM25-RP", "DGM25-NW", "GLO-30", "GTOPO30"]
KNOWN_WEATHER = ["CERRA5", "ERA5", "DWD"]
STORAGE_TERRAIN = "terrain"
STORAGE_WAETHER = "weather"
DEM_FMT = "%s.lzw.tif"
STORAGE_AUX_FILES = resources.files(__title__ + '.data')
MAX_RETRY = 3


# -------------------------------------------------------------------------


def locations_available(candidates):
    return [x for x in candidates if os.path.isdir(x)]


def locations_writable(candidates):
    return [x for x in candidates if os.access(x, os.W_OK)]


def location_has_storage(location, storage):
    path = os.path.join(location, storage)
    return os.path.exists(path)


def find_storage_path(locs: str = None, stor: str = None) -> str:
    """
    Finds a viable data storage directory and returns its path.
    If `storage_path` is provided, only this path is checked
    for existance.

    :param storage_path: (optional) user selected path
    :return: data storage directory
    :rtype: str
    """
    if stor is None:
        raise ValueError('stor must be provided')
    if locs is None:
        locs = _tools.DEFAULT_DATA_DIRS
    loc_exist = locations_available(locs)
    if len(loc_exist) == 0:
        return None
    loc_write = locations_writable(loc_exist)
    if len(loc_write) == 0:
        return None
    for loc in loc_write:
        if location_has_storage(loc, stor):
            location = loc
            break
    else:
        for loc in loc_write:
            try:
                os.makedirs(os.path.join(loc, stor))
            except IOError:
                continue
            if os.path.isdir(os.path.join(loc, stor)):
                location = loc
                break
        else:
            raise Exception('Could not create data storage directory')
    return os.path.join(location, stor)


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
    support_file, _ = urlretrieve(
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
            with gzip.open(tile_file, 'rb') as tf:
                with open(tile_dem, 'wb') as td:
                    shutil.copyfileobj(tf, td, length=16 * 1024)
            logger.debug("... converting to %s" % tile_tif)
            gdal.Warp(destNameOrDestDS=tile_tif,
                      srcDSOrSrcDSTab=tile_dem,
                      format="GTiff")
    # merge the GeoTiff Files from all tiles into one file
    target = os.path.join(path, DEM_FMT % "GTOPO30")
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

    for lat in range(47, 54):
        for lon in range(5, 16):
            url = download_dir + file_fmt % (lat, lon)
            logger.debug("downloading ... %s" % url)
            tar_file, _ = urlretrieve(url, os.path.basename(url))
            name_root = tar_file.replace(".tar", "")
            with tarfile.open(tar_file) as tf:
                to_extract = [x for x in tf.getmembers()
                              if name_root + "/DEM/" in x.name]
                for x in to_extract:
                    # remove path from name of tar member to extract
                    x.name = os.path.basename(x.name)
                    logger.debug("... extracting %s" % x.name)
                    # now extract tar member to current dir
                    tf.extract(x, '.')
    # merge the GeoTiff Files from all tiles into one file
    target = os.path.join(path, DEM_FMT % "GLO-30")
    if os.path.exists(target):
        logger.info("removing old source file")
        os.remove(target)
    logger.debug("merging tiles ...")
    gdal_merge.main(["", "-co", "compress=lzw",
                     "-o", target,
                     "-ot", "Int16"] +
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
        tile_tif = tile_xyz.replace(".xyz", ".tif")
        try:
            gdal.Warp(destNameOrDestDS=tile_tif,
                      dstSRS="EPSG:5677",
                      srcDSOrSrcDSTab=tile_xyz,
                      srcSRS="EPSG:25832",
                      format="GTiff")
        except Exception as e:
            logger.error(str(e))
    # merge the GeoTiff Files from all tiles into one file
    target = os.path.join(path, DEM_FMT % "DGM25-RP")
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

def download_DGM25_NW(path):
    out_res = 25  # m in EPSG:5677 aka Gauss-Krueger band 3
    base_url = ("https://www.opengeodata.nrw.de/" +
                "produkte/geobasis/hm/dgm1_tiff/dgm1_tiff/")
    meta_file = "dgm1_meta.zip"
    url = f"{base_url}/{meta_file}"
    logger.debug("downloading metadata: %s" % path)
    zip_file, _ = urlretrieve(url, os.path.basename(url))
    input_files = []
    with zipfile.ZipFile(zip_file, 'r') as zf:
        with io.TextIOWrapper(zf.open('dgm1_tiff.csv')) as csvfile:
            for row in csv.reader(csvfile, delimiter=';',
                                  quoting=csv.QUOTE_NONE):
                if "ETRS89_UTM32" in row:
                    input_files.append(row[0])
    tile_files = []
    for tf1 in _tools.progress(input_files):
        url = f"{base_url}/{tf1}"
        logger.debug(f"downloading ... {url}")
        for i in range(MAX_RETRY):
            try:
                zip_file, _ = urlretrieve(url, tf1)
                break
            except Exception as e:
                pass
        else:
            raise Exception("failed to download tile files")
        tf25 = tf1.replace("dgm1", "dgm25") + ".tif"
        logger.debug(f"converting tile ... {tf1} -> {tf25}")
        try:
            gdal.Warp(destNameOrDestDS=tf25,
                      xRes=out_res,
                      yRes=out_res,
                      dstSRS="EPSG:5677",
                      srcDSOrSrcDSTab=tf1,
                      srcSRS="EPSG:25832",
                      format="GTiff")
            tile_files.append(tf25)
        except Exception as e:
            logger.error(str(e))
        os.remove(tf1)
    # merge the GeoTiff Files from all tiles into one file
    target = os.path.join(path, DEM_FMT % "DGM25-NW")
    if os.path.exists(target):
        logger.info("removing old source file")
        os.remove(target)
    logger.debug("merging tiles ...")
    gdal_merge.main(["", "-co", "compress=lzw",
                     "-o", target,
                     ] + tile_files)
    logger.debug("... done")

    return


# -------------------------------------------------------------------------

def download_dem(dem: str, path: str = None):
    if path is None:
        path = find_storage_path(path, STORAGE_TERRAIN)
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
            elif dem == "DGM25-NW":
                download_DGM25_NW(path)
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


def provide_terrain_data(storage_path: str, source=None,
                         force=False, download=True):
    extension = DEM_FMT % ""
    datasets = []
    # if a location is found, we are happy
    # but does it contain any data?
    for file in os.listdir(storage_path):
        if file.endswith(extension):
            datasets.append(file.replace(extension, ""))
    if download:
        for aux_path in STORAGE_AUX_FILES.iterdir():
            aux_file = os.path.basename(str(aux_path))
            if aux_file.startswith('_'):
                continue
            if (not os.path.isfile(os.path.join(storage_path, aux_file)) or
                    force):
                logger.debug('copying auxiliary file: %s' % aux_file)
                shutil.copyfile(str(aux_path),
                                os.path.join(storage_path, aux_file))
        # now fill the storage with data
        for dem in KNOWN_DEMS:
            if (os.path.exists(
                    os.path.join(storage_path, DEM_FMT % dem)) and
                    not force):
                logger.info("dataset found in storage: %s" % dem)
                datasets.append(dem)
            else:
                logger.debug(f"{dem} -- {source}")
                if dem == source:
                    success = download_dem(dem, storage_path)
                    if success:
                        logger.error("successful download of dataset %s" % dem)
                        datasets.append(dem)
                    else:
                        logger.error("dataset %s failed to download" % dem)
    return datasets


# -------------------------------------------------------------------------


def show_notice(storage_path, source):
    print('data copyright notice:')
    with open(os.path.join(storage_path,
                           "%s.NOTICE.txt" % source), "r") as f:
        for x in f.readlines():
            print(x)


# -------------------------------------------------------------------------
# -------------------------------------------------------------------------

def era5_getyear(opts):
    y, path = opts
    year = '{:04d}'.format(y)
    ncname = 'era5_ak_eu_' + year + '.nc'
    target = os.path.join(path, ncname)
    c = cdsapi.Client()
    c.retrieve(
        'reanalysis-era5-single-levels',
        {
            'product_type': 'reanalysis',
            'variable': [
                '10m_u_component_of_wind', '10m_v_component_of_wind', '2m_dewpoint_temperature',
                '2m_temperature', 'forecast_surface_roughness', 'friction_velocity',
                'surface_latent_heat_flux', 'surface_pressure', 'surface_sensible_heat_flux',
                'low_cloud_cover', 'total_cloud_cover',
                'cloud_base_height', 'total_precipitation',
            ],
            'year': year,
            'month': [
                '01', '02', '03',
                '04', '05', '06',
                '07', '08', '09',
                '10', '11', '12',
            ],
            'day': [
                '01', '02', '03',
                '04', '05', '06',
                '07', '08', '09',
                '10', '11', '12',
                '13', '14', '15',
                '16', '17', '18',
                '19', '20', '21',
                '22', '23', '24',
                '25', '26', '27',
                '28', '29', '30',
                '31',
            ],
            'time': [
                '00:00', '01:00', '02:00',
                '03:00', '04:00', '05:00',
                '06:00', '07:00', '08:00',
                '09:00', '10:00', '11:00',
                '12:00', '13:00', '14:00',
                '15:00', '16:00', '17:00',
                '18:00', '19:00', '20:00',
                '21:00', '22:00', '23:00',
            ],
            'area': [
                71, -12, 33,
                36,
            ],
            'format': 'netcdf',
        },
        target)

def era_process(years, path):
    # create option tuples
    combi = []
    for y in range(years[0], years[1]):
        combi.append((y, path))
    # get data in parallel directly to storage
    with Pool(10) as pool:
        p = pool.map(era5_getyear, combi)

# -------------------------------------------------------------------------


def cerraname(y, lt=None):
    name = 'cerra_ak_eu_%04i' % y
    if lt is not None:
        name += '_%01i' % lt
    return name

# -------------------------------------------------------------------------


def cerra_getyear(opts):
    y, lt = opts
    gribname = cerraname(y, lt) + '.grib'
    c = cdsapi.Client()
    if not os.path.exists(gribname):
        print("cds getting: " + gribname)
        opts = (
            'reanalysis-cerra-single-levels',
            {
                'data_type': 'reanalysis',
                'product_type': 'forecast',
                'variable': [
                    '10m_wind_direction', '10m_wind_speed', '2m_relative_humidity',
                    '2m_temperature', 'low_cloud_cover', 'medium_cloud_cover',
                    'momentum_flux_at_the_surface_u_component',
                    'momentum_flux_at_the_surface_v_component', 'surface_latent_heat_flux',
                    'surface_pressure', 'surface_roughness', 'surface_sensible_heat_flux',
                    'total_cloud_cover', 'total_precipitation',
                ],
                'level_type': 'surface_or_atmosphere',
                'year': '%04i' % y,
                'month': [
                    '01', '02', '03',
                    '04', '05', '06',
                    '07', '08', '09',
                    '10', '11', '12',
                ],
                'day': [
                    '01', '02', '03',
                    '04', '05', '06',
                    '07', '08', '09',
                    '10', '11', '12',
                    '13', '14', '15',
                    '16', '17', '18',
                    '19', '20', '21',
                    '22', '23', '24',
                    '25', '26', '27',
                    '28', '29', '30',
                    '31',
                ],
                'time': [
                    '00:00', '03:00', '06:00',
                    '09:00', '12:00', '15:00',
                    '18:00', '21:00',
                ],
                'leadtime_hour': '%i' % lt,
                'format': 'grib',
            },
            gribname
        )
        c.retrieve(*opts)
        ncname = cerraname(y, lt) + '.nc'
        print("cdo processing: " + ncname)
        cdo.selindexbox('489,649,479,659', options='-f nc',
                        input=gribname, output=ncname)
        os.remove(gribname)

# -------------------------------------------------------------------------


def cerra_process(years, path):
    tempPath = './tmp/'
    data = cdo.Cdo(tempdir=tempPath)
    print("python-cdo version: %s" % data.__version__())
    print("cdo        version: %s" % data.version())
    data.debug = True
    data.cleanTempDir()

    # get sets of bunches to retrieve
    combi = []
    for y in range(years[0], years[1]):
        for lt in range(1, 4):
            combi.append((y, lt))

    # get data and extract region
    with Pool(10) as pool:
        p = pool.map(cerra_getyear, combi)

    # combine forecasts
    for yr in set([x for x, _ in combi]):
        lts = set([y for x, y in combi if x == yr])
        infiles = [cerraname(yr, lt) + '.nc' for lt in lts]
        target = os.path.join(path, cerraname(yr, None) + '.nc')
        data.mergetime(
            input=" ".join([
                data.setgridtype('curvilinear', input=x)
                for x in infiles
            ]),
            output=target,
            options='-f nc4 -z zip_6 --reduce_dim'
        )
        for x in infiles:
           os.remove(x)

# -------------------------------------------------------------------------


def download_weather(source: str, path: str = None, years: list = None):
    if path is None:
        path = find_storage_path(path, STORAGE_TERRAIN)
    logger.info("downloading weather source %s" % source)
    success = True
    pwd = os.getcwd()
    with tempfile.TemporaryDirectory() as temp_dir:
        os.chdir(temp_dir)
        try:
            if source == "ERA5":
                download_GTOPO30(years, path)
            elif source == "CERRA":
                download_GLO_30(years, path)
            else:
                logger.error("unknown dataset to download %s" % source)
                success = False
        except Exception as e:
            logger.error(str(e))
            success = False
    # return before clean up
    os.chdir(pwd)
    return success


# =========================================================================


def cli_parser():
    """
    funtion to parse command line arguments
    :return: parser object
    :rtype: argparse.ArgumentParser
    """

    default_dem = KNOWN_DEMS[0]
    default_extent = 6.

    parser = argparse.ArgumentParser(
        description='Prepare modify datasets used by austaltools',
    )
    verb = parser.add_mutually_exclusive_group()
    verb.add_argument('--debug', dest='verb', action='store_const',
                      const=logging.DEBUG, help='show informative output')
    verb.add_argument('-v', '--verbose', dest='verb', action='store_const',
                      const=logging.INFO, help='show detailed output')
    parser.add_argument("--version",
                        version="%(prog)s " + str(__version__),
                        action="version")
    subparsers = parser.add_subparsers(dest='action',
                                       metavar='COMMAND',
                                       required=True
                                       )
    sub_list = subparsers.add_parser('list')
    sub_only_grp = sub_list.add_mutually_exclusive_group()
    sub_only_grp.add_argument('-w', '--weather',
                              dest='only',
                              action='store_const',
                              const='weather',
                              default='all')
    sub_only_grp.add_argument('-t', '--terrain',
                              dest='only',
                              action='store_const',
                              const='terrain',
                              default='all')
    sub_only_grp.add_argument('--all',
                              dest='only',
                              action='store_const',
                              const='all',
                              default='all')
    sub_state_grp = sub_list.add_mutually_exclusive_group()
    sub_state_grp.add_argument('-k', '--known',
                               dest='state',
                               action='store_const',
                               const='known',
                               default='available')
    sub_state_grp.add_argument('--available',
                               dest='state',
                               action='store_const',
                               const='available',
                               default='available')
    sub_list.add_argument('-l', '--long',
                          action="store_true",
                          help='show verbose list instead of just codes')

    sub_down = subparsers.add_parser('download')
    sub_down.add_argument('-s', '--source',
                          metavar="CODE",
                          nargs=None,
                          choices=KNOWN_DEMS + KNOWN_WEATHER,
                          default=default_dem,
                          help='code for the source digital elevation ' +
                               'model (DEM). Known DEMs are: ' +
                               ' '.join(KNOWN_DEMS) + ' ' +
                               'Defaults to ' + default_dem)
    sub_down.add_argument('-y', '--years',
                          metavar="YEAR",
                          nargs=2,
                          choices=KNOWN_DEMS + KNOWN_WEATHER,
                          help='years for which to download weather data' +
                               '. Data will be downloaded from first to ' +
                               'second year given, including both. ' +
                               'To download a singe year, give the year ' +
                               'twice. No default, required with ' +
                               'weather datasets.')

    parser.add_argument("--storage",
                        metavar='PATH',
                        default=None,
                        help='custom location for data storage'
                        )

    return parser


# -------------------------------------------------------------------------


def main():
    """
    Command line interface.
    Evaluates the command line arguments from cli_parser()
    performs additional checks and sets the logging level

    :return: configuration values
    :rtype: dict
    """
    parser = cli_parser()
    args = vars(parser.parse_args())

    # set logging level
    if args['verb'] is not None:
        logger.setLevel(args['verb'])
    else:
        logger.setLevel(logging.WARNING)

    # if args['output'] is None and args['source_action'] is None:
    #     parser.print_help()
    #     logger.critical('NAME is required with -L, -G, -U, -D or -W')
    #     sys.exit(1)

    logger.info(os.path.basename(__file__) + ' version: ' + __version__)

    logger.debug(args)

    if args['action'] == 'download':
        if args['source'] in KNOWN_DEMS:
            download_dem(args['source'], args['storage'])
        elif args['source'] in KNOWN_WEATHER:
            if not 'years' in args:
                sys.tracebacklimit = 0
                raise ValueError('-y required with dataset: %s '
                                 % args['source'])
            download_weather(args['source'], args['storage'],
                             args['years'])
        else:
            raise ValueError("Source not recognized: %s "
                             % args['source'])
    else:
        raise ValueError("Action not recognized: %s "
                         % args['source'])


# -------------------------------------------------------------------------
# initialize: call main routine
if __name__ == "__main__":
    main()
