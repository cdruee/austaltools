#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Mar 20 09:57:48 2022

@author: clemens
"""
import csv
import datetime as dt
import glob
import gzip
import logging
import os
import re
import shutil
import sys
import tarfile
import tempfile
import zipfile
from importlib import resources
from xml.etree import ElementTree

import requests
import pip

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

DEM_FMT = "%s.lzw.tif"
WEA_FMT = "%s_ak_eu_%04i.nc"
DIST_AUX_FILES = resources.files(__title__ + '.data')
MAX_RETRY = 3

DATASET_DEFINITIONS = [
    {
        "name": "DGM25-RP",
        "storage": "terrain",
        "assemble": "assemble_DGM25_RP",
        "doi": "10.5281/zenodo.12740424"
    },
    {
        "name": "DGM10-RP",
        "storage": "terrain",
        "assemble": "assemble_DGMxx",
        "arguments": {
            'resolution': 10,
            'check_cert': False,
            'host': 'https://geobasis-rlp.de',
            'path': '/data/dgm1/current',
            'filelist': '/meta4/dgm1_tif_07.meta4',
            'xmlpath': '/file[name=.tif$]/url',
            'CRS': 'EPSG:25832'
        },
    },
    {
        "name": "DGM10-NW",
        "storage": "terrain",
        "assemble": "assemble_DGMxx",
        "arguments": {
            'resolution': 10,
            'host': 'https://www.opengeodata.nrw.de',
            'path': 'produkte/geobasis/hm/dgm1_tiff/dgm1_tiff',
            'filelist': 'index.xml',
            'xmlpath': '/datasets/dataset[0]/files/file::name',
            'xmlattribute': 'name',
            'datapath': '',
            'CRS': 'EPSG:25832'
        },
    },
    {
        "name": "GLO-30",
        "storage": "terrain",
        "assemble": "assemble_GLO_30"
    },
    {
        "name": "GTOPO30",
        "storage": "terrain",
        "assemble": "assebmle_GTOPO30"
    },
    {
        "name": "ERA5",
        "storage": "weather",
        "assemble": "assemble_ERA5"
    },
    {
        "name": "CERRA",
        "storage": "weather",
        "assemble": "assemble_CERRA"
    },
]
KNOWN_DEMS = [x['name'] for x in DATASET_DEFINITIONS
              if x['storage'] == _tools.STORAGE_TERRAIN]
KNOWN_WEATHER = [x['name'] for x in DATASET_DEFINITIONS
                 if x['storage'] == _tools.STORAGE_WAETHER]


# =========================================================================


class DataSet:
    name = str()
    available = False
    path = None
    storage = None
    file_license = None
    file_notice = None
    file_data = None
    uri = None
    years = []
    arguments = None

    # ----------------------------------------------------

    def assemble(self):
        """Placeholder for download function"""
        pass

    # ----------------------------------------------------

    def download(self, path=None, uri=None):
        """Download assembled dataset from reopository"""
        if path is None:
            path = self.path
        else:
            self.path = path
        if uri is None:
            if self.uri is not None:
                uri = self.uri
            else:
                raise ValueError("No uri defined or provided")
        if uri.startswith('doi'):
            doi = re.sub('^doi[:/]*', '', uri)
            doi_url = f"https://doi.org/{doi}"
            logger.debug(f"resolving {doi_url}")
            for i in range(MAX_RETRY):
                try:
                    resolver = requests.head(doi_url)
                    redirect = resolver.url
                    resolver.close()
                    break
                except requests.HTTPError:
                    continue
            else:
                raise Exception("Could not resolve DOI")
            if "zenodo" in redirect:
                url = f"{redirect}/files/{self.file_data}?download=1"
            else:
                raise ValueError(f"Dont know how to hande redirect " +
                                 "URL: {URL}")
        elif uri.startswith('http'):
            url = uri
        with open(os.path.join(path, self.file_data), 'wb') as f:
            f.write(requests.get(url, allow_redirects=True).content)

    # ----------------------------------------------------

    def __init__(self, **kwargs):
        if 'name' not in kwargs:
            raise ValueError('no name given')
        if 'storage' not in kwargs:
            raise ValueError('no storage given')
        for x in kwargs:
            if x == "assemble":
                self.assemble = getattr(sys.modules[__name__], kwargs[x])
            elif hasattr(self, x):
                setattr(self, x, kwargs[x])
        if self.file_license is None:
            self.file_license = f"{self.name}.LICENSE.txt"
        if self.file_notice is None:
            self.file_notice = f"{self.name}.NOTICE.txt"
        if self.file_data is None:
            if self.storage == 'terrain':
                self.file_data = DEM_FMT % self.name
            elif self.storage == 'weather':
                self.file_data = WEA_FMT % (self.name, 0)


# =========================================================================


def locations_available(locs):
    return [x for x in locs if os.path.isdir(x)]


# -------------------------------------------------------------------------


def locations_writable(locs):
    return [x for x in locs if os.access(x, os.W_OK)]


# -------------------------------------------------------------------------


def location_has_storage(location, storage):
    return os.path.exists(os.path.join(location, storage))


# -------------------------------------------------------------------------


def dataset_get(name):
    for x in DATASETS:
        if x.name == name:
            return x
    else:
        raise ValueError(f"Dataset {name} not found")


# -------------------------------------------------------------------------


def dataset_available(name):
    return dataset_get(name).available


# -------------------------------------------------------------------------

def dataset_scan(locs=None):
    if locs is None:
        locs = _tools.STORAGE_LOCATIONS
    loc_avail = locations_available(locs)
    if len(loc_avail) == 0:
        raise ValueError("No locations available")
    for ds in DATASETS:
        for loc in reversed(loc_avail):
            if ds.storage is None:
                raise ValueError(f'storage not defined in: {ds.name}')
            if location_has_storage(loc, ds.storage):
                path = os.path.join(loc, str(ds.storage))
                datafile = os.path.join(path, ds.file_data)
                if os.path.exists(datafile):
                    ds.available = True
                    ds.path = path


# -------------------------------------------------------------------------


def find_writeable_storage(locs: str = None, stor: str = None) -> str or None:
    """
    Finds a viable data storage directory and returns its path.
    If `storage_path` is provided, only this path is checked
    for existance.

    :param locs: Candidate locations
    :type locs: str
    :param stor: Storage directory expected at location
    :type stor: str
    :return: path to a writable data storage directory
    :rtype: str
    """
    if stor is None:
        raise ValueError('stor must be provided')
    if locs is None:
        locs = _tools.STORAGE_LOCATIONS
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


def assebmle_GTOPO30(path: str, name = "GTOPO30",
                     replace=False, args: dict ={}):
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
    target = os.path.join(path, DEM_FMT % "GTOPO30")
    logger.debug(f'data file path: {target}')
    if os.path.exists(target) and not replace:
        logger.info("dataset exists ... %s" % name)
        return False
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


def assemble_GLO_30(path, name = "GLO_30", replace=False, args: dict ={}):
    target = os.path.join(path, DEM_FMT % name)
    logger.debug(f'data file path: {target}')
    if os.path.exists(target) and not replace:
        logger.info("dataset exists ... %s" % name)
        return False

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

def xmlpath(xml, path):
    res = []
    if '::' in path:
        getpath, getatt = path.split("::")
    else:
        getpath = path
        getatt = None
    levels = getpath.split('/')
    if levels[0] == '':
        levels.pop(0)
    root = ElementTree.fromstring(xml)
    m = re.search('{.*}', root.tag)
    if m:
        ns = '%s' % m.group(0)
    else:
        ns = ''
    nodes = [root]
    spec = attr = sel = None
    for level in levels:
        if "[" in level:
            name = re.sub('\[.*]', '', level)
            spec = re.sub('.*\[(.*)].*', r'\1', level)
            try:
                sel = int(spec)
                attr = None
            except ValueError:
                if '=' in spec:
                    attr, sel = [x.strip() for x in spec.split('=')]
                else:
                    attr = spec
                    sel = None
        else:
            name = level
            spec = attr = sel = None
        tag = ''.join((ns, name))
        print(name, spec, attr, sel)
        next = []
        for node in nodes:
            # iterate over children
            for i, ele in enumerate(node):
                if not ele.tag == tag:
                    continue
                if sel is None and attr is None:
                    next.append(ele)
                elif sel == i:
                    next.append(ele)
                elif (attr is not None and
                      attr in ele.attrib and
                      bool(re.search(sel, ele.attrib[attr]))):
                    next.append(ele)
        nodes = next
    if getatt is None:
        res = [x.text for x in nodes]
    else:
        res = [x.get(getatt, default='') for x in nodes]
    return res


def assemble_DGMxx(path: str, name: str, replace : bool,
                   provider: dict):
    if 'resolution' in provider:
        out_res = provider['resolution']
    else:
        out_res = 25
    target = os.path.join(path, DEM_FMT % name)
    logger.debug(f'data file path: {target}')
    if os.path.exists(target) and not replace:
        logger.info("skipping because dataset exists: %s" % name)
        return False

    base_url = '/'.join((provider['host'], provider['path']))
    if 'check_cert' in provider:
        verify = provider['check_cert']
    else:
        verify = True
    filelist = provider['filelist']
    url = '/'.join((base_url, filelist))
    # switch formats:
    if filelist.endswith(('.xml', 'meta4')):
        # xml
        logger.debug("downloading xml metadata: %s" % url)
        rsp = requests.get(url, allow_redirects=True, verify=verify)
        input_files = xmlpath(xml=rsp.content.decode(),
                              path=provider['xmlpath'])
    else:
        raise NotImplementedError(f'cannot handle meta format: {filelist}')

    tile_files = []
    for inp in _tools.progress(input_files):
        if re.match('^http[s]*://', inp):
            url = inp
            tf1 = os.path.basename(inp)
        else:
            url = f"{base_url}/{inp}"
            tf1 = inp
        logger.debug(f"downloading ... {url}")
        for i in range(MAX_RETRY):
            #try:
            with open(tf1, 'wb') as f:
                f.write(requests.get(url,verify=verify).content)
            break
            #except Exception as e:
            #    pass
        else:
            raise Exception("failed to download tile files")
        tf25 = os.path.splitext(tf1)[0] + ".reduced.tif"
        logger.debug(f"converting tile ... {tf1} -> {tf25}")
        try:
            gdal.Warp(destNameOrDestDS=tf25,
                      xRes=out_res,
                      yRes=out_res,
                      dstSRS="EPSG:5677",
                      srcDSOrSrcDSTab=tf1,
                      format="GTiff")
            tile_files.append(tf25)
        except Exception as e:
            logger.error(str(e))
        os.remove(tf1)
    # merge the GeoTiff Files from all tiles into one file
    if os.path.exists(target):
        logger.info("removing old source file")
        os.remove(target)
    logger.debug("merging tiles ...")
    gdal_merge.main(["", "-co", "compress=lzw",
                     "-o", target,
                     ] + tile_files)
    logger.debug("... done")
    return True


# -------------------------------------------------------------------------


def assemble_DGM25_RP(path, name = "DGM25-RP", replace=False):
    target = os.path.join(path, DEM_FMT % name)
    logger.debug(f'data file path: {target}')
    if os.path.exists(target) and not replace:
        logger.info("dataset exists ... %s" % name)
        return False

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
    if os.path.exists(target):
        logger.info("removing old source file")
        os.remove(target)
    logger.debug("merging tiles ...")
    gdal_merge.main(["", "-co", "compress=lzw",
                     "-o", target,
                     ] + glob.glob("DGM25_*.tif"))
    logger.debug("... done")

    return True
# -------------------------------------------------------------------------


def provide_dem(source: str, path: str = None,
                force: bool = False, method: str = 'download'):
    if path is None:
        path = find_writeable_storage(path, _tools.STORAGE_TERRAIN)
    dataset = dataset_get(source)
    logger.info("downloading terrain source %s" % source)
    if method == 'download':
        if dataset.uri is None:
            raise Exception("Dataset has no download uri, assemble it.")
        dataset.download(path)
    elif method == 'assemble':
        # change to temp directory
        pwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)
            logger.debug('calling %s' % str(dataset.assemble))
            dataset.assemble(path, source, force, dataset.arguments)
            # return before clean up
            os.chdir(pwd)
    else:
        raise ValueError("method must be either 'download' or 'assemble'")

    for aux_path in DIST_AUX_FILES.iterdir():
        aux_file = os.path.basename(str(aux_path))
        if aux_file in [dataset.file_license, dataset.file_notice]:
            logger.debug('copying auxiliary file: %s' % aux_file)
            shutil.copyfile(str(aux_path),
                            os.path.join(path, aux_file))
    return
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


# -------------------------------------------------------------------------


def assemble_ERA5(path: str, years: list):
    # create option tuples
    combi = []
    for y in years:
        if not 1940 <= y <= dt.datetime.now().year:
            raise ValueError(f"year is out of range (1940-today): {y}")
        combi.append((y, path))
    # get data in parallel directly to storage
    with Pool(10) as pool:
        pool.map(era5_getyear, combi)


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


def assemble_CERRA(path: str, years: list):
    tempPath = './tmp/'
    data = cdo.Cdo(tempdir=tempPath)
    print("python-cdo version: %s" % data.__version__())
    print("cdo        version: %s" % data.version())
    data.debug = True
    data.cleanTempDir()

    # get sets of bunches to retrieve
    combi = []
    for y in years:
        if not 1940 <= y <= dt.datetime.now().year:
            raise ValueError(f"year is out of range (1941-2019): {y}")
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


def provide_weather(source: str, path: str = None, years: list = None,
                    method: str = 'download'):
    if path is None:
        path = find_writeable_storage(path, _tools.STORAGE_TERRAIN)
    logger.info("downloading weather source %s" % source)
    success = True
    pwd = os.getcwd()
    with tempfile.TemporaryDirectory() as temp_dir:
        os.chdir(temp_dir)
        try:
            if source == "ERA5":
                assemble_ERA5(path, years)
            elif source == "CERRA":
                assemble_CERRA(path, years)
            else:
                logger.error("unknown dataset to download %s" % source)
                success = False
        except Exception as e:
            logger.error(str(e))
            success = False
    # return before clean up
    os.chdir(pwd)
    return success


# -------------------------------------------------------------------------


# initialize
DATASETS = [DataSet(**x) for x in DATASET_DEFINITIONS]
dataset_scan()

# RP: https://geobasis-rlp.de/data/dgm1/current/meta4/dgm1_tif_07.meta4

# for x in root.findall('./metalink:file',{"metalink":"urn:ietf:params:xml:ns:metalink"}):
#     if x.attrib['name'].endswith('tif'):
#         u = x.find('./metalink:url',{"metalink":"urn:ietf:params:xml:ns:metalink"})
#         print(u.text)


# BW: https://opengeodata.lgl-bw.de/data/dgm/dgm1_32_501_5380_2_bw.zip
#  re: 387-609/2  ho:5264-5514/2

# NS: https://ni-lgln-opengeodata.hub.arcgis.com/apps/lgln-opengeodata::digitales-gel%C3%A4ndemodell-dgm1/about
