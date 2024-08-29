#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module that provides funtions to assembe, download, and handle
datasets that serve as input for austaltools

:_`unpack string`:
    Several funtions make use of the unpack string that describes
    how to extract data from a (downloaded) file.
    The syntax is simple:

    - Empty, missing, 'false', or 'tif' the downloaded file itself
      is regared as the file.
    - strings starting with 'zip://', 'unzip://' command unpacking
      of files matching the glob pattern following '://'.
      Any path contained in this epxression are discarded, all files
      are extracted to the working diretory.

    Example:
      ::

        zip://data/*.tif

      unpack all files from the archive that are in directory `data`
      and en on `.tif`

"""
import glob
import gzip
import itertools
import json
import logging
import os
import random
import re
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import time
import zipfile
from importlib import resources
from pathlib import PurePath


import numpy as np
import pandas as pd
import pip
import requests
from urllib3 import disable_warnings, exceptions


if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    from osgeo import gdal
    from osgeo import osr
    from osgeo_utils import gdal_merge
    import multiprocessing as mp
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
    from ._version import __version__, __title__
    from . import _tools
    from . import _dwd_observations
except ImportError:
    from _version import __version__, __title__
    import _tools
    import _dwd_observations

disable_warnings(exceptions.InsecureRequestWarning)
logger = logging.getLogger()

# -------------------------------------------------------------------------
DEM_FMT = '%s.elevation.nc'  # % NAME
""" terrain database file name template"""
DEM_CRS = "EPSG:5677"
""" terrain data projection (GAUSS-KRÜGER zone 3)"""
WEA_FMT = '%s.ak-input.nc'
""" weather model database file name template"""
OBS_FMT = '%s.obs.zip'
""" weather observation database file name template"""
CDSAPI_LIMIT_PARALLEL = 2
""" Copernicus per-user limit for parallel queries """
DIST_AUX_FILES = resources.files(__title__ + '.data')
""" path to the auxiliary data files distributes alongside the coee """
TEMP = tempfile.gettempdir()
""" default path for temp files/dierctories """
MAX_RETRY = 3
""" number of tries made to download a ceratin file """
NODATA = 9.96920996838686905e+36
""" terrain data `noddata` value """

with (DIST_AUX_FILES / 'dataset_definitions.json').open() as f:
    DATASET_DEFINITIONS = json.load(f)

SOURCES_TERRAIN = [k for k, v in DATASET_DEFINITIONS.items()
                   if v['storage'] == _tools.STORAGE_TERRAIN]
""" list of known terrain data sources """
SOURCES_WEATHER = [k for k, v in DATASET_DEFINITIONS.items()
                 if v['storage'] == _tools.STORAGE_WAETHER]
""" list of known weather data sources """


# =========================================================================


class DataSet:
    """
    Class that describes and handles a dataset
    """
    name = str()
    """ID of the dataset (short uppercase code)"""
    available = False
    """If dataset is available on the system"""
    path = None
    """Path of the storage location where the dataset resides 
        (if available)"""
    storage = None
    """Kind of dataset. 
    Also the name of the storage (i.e. subdiretory of the storage location)
    the dataset is stored in.
    """
    license = None
    """source of the license of the dataset"""
    file_license = None
    """name of the file containing the license of the dataset"""
    notice = None
    """text of the notice to be shown"""
    file_notice = None
    """name of the file containing the notice to be shown
        if the dataset is used"""
    file_data = None
    """name of the file containing the data of the dataset"""
    uri = None
    """uri describing the location from where the assembled dataset 
        can be downloaded. Currently supported: http(s):// and doi://
        (if such a location exists)"""
    years = []
    """list of years covered by the dataset (if `storage` is 'weather')"""
    position = None
    """keyword how position is provided"""
    arguments = None
    """arguments to the assemble funtion that generates the dataset
        from the original source."""

    # -------------------------------------------------------------------------
    def assemble(self, path, name, replace, args):
        """
        Funtion that generates the dataset from the original source.

        In an empty Dataset onject, this function is just a placeholder
        and does nothing.

        :param path: path to the storage location where the
          dataset shall reside
        :type path: str
        :param name: name of the dataset (short uppercase code)
        :type name: str
        :param replace: replace the dataset if it alread exists
        :type replace: bool
        :param args: arguments to the assembling funtion that generates the dataset
        :type args: dict
        :returns: If the assembly was successful
        :rtype: bool
        """
        return True

    # -------------------------------------------------------------------------
    def download(self, path=None, uri=None):
        """
        Download assembled dataset from reopository
        :param path: path to the storage location where the
        dataset shall reside. Only needed if the attribute
        :py:attr:`DataSet.path` is not set or should be overridden.
        :type path: str, optional
        :param uri: uri describing the location from where the assembled
        dataset shall be downloaded. Only needed if the attribute
        :py:attr:`DataSet.uri` is not set or should be overridden.
        :type uri: str, optional
        """
        if uri is None:
            uri = self.uri
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
                    with requests.head(doi_url) as resolver:
                        redirect = resolver.url
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
        else:
            raise ValueError(f'cannot handle URI: {uri}')
        with open(os.path.join(path, self.file_data), 'wb') as f:
            with requests.get(url, allow_redirects=True) as req:
                f.write(req.content)

    # -------------------------------------------------------------------------
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
            self.file_data = DEM_FMT % self.name


# =========================================================================


def locations_available(locs):
    """
    Check whether locations exist
    :param locs: paths of storage location directories
    :type locs: list[str]
    :return: True if locations exist, False otherwise
    :rtype: bool
    """
    return [x for x in locs if os.path.isdir(x)]


# -------------------------------------------------------------------------
def locations_writable(locs):
    """
    Check whether locations are writable
    :param locs: paths of storage location directories
    :type locs: list[str]
    :return: True if locations are writable, False otherwise
    :rtype: bool
    """
    return [x for x in locs if os.access(x, os.W_OK)]


# -------------------------------------------------------------------------
def location_has_storage(location, storage):
    """
    Check if location has storage
    :param location: path to storage location
    :type location: str
    :param storage: name of storage
    :type storage: str
    :return: True if location has storage
    :rtype: bool
    """
    return os.path.exists(os.path.join(location, storage))


# -------------------------------------------------------------------------
def dataset_get(name):
    """
    Yield the dataset with the given ID
    :param name: dataset ID
    :type name: str
    :return: the requested dataset object
    :rtype: Dataset

    :raises ValueError: if the dataset does not exist
    """
    for x in DATASETS:
        if x.name == name:
            return x
    else:
        raise ValueError(f"Dataset {name} not found")


# -------------------------------------------------------------------------
def dataset_available(name):
    """
    Return if dataset is available
    :param name:  dataset id of dataset to be checked
    :type name: str
    :return: True if dataset is available, False otherwise
    :rtype: bool

    """
    return dataset_get(name).available


# -------------------------------------------------------------------------
def dataset_scan(locs:list=None):
    """
    Scan for datasets available on the system.
    Set the :py:attr:`DataSet.available` attribute
    in the global list :py:const:`DATASETS` accordingly.

    :param locs: list of possible storage loactions
    :type locs: list[str]
    """
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
def find_writeable_storage(locs: str = None,
                           stor: str = None) -> str or None:
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


# -------------------------------------------------------------------------
def xyz2csv(inputfile, output, utm_remove_zone=False):
    """
    Clean the xyz flies downloaded in a way that gdal accepts them as csv

    :param inputfile: input file
    :type inputfile: str
    :param output: output file
    :type output: str
    :param utm_remove_zone: Some providers prefix UTM easting with the
      zone numer, which results in easting values exceeding 1000km.
      Remove the leading digits to keep easting in the allowed range
      0m < easting < 1000000 m. defaults to False.
    :type utm_remove_zone: bool
    :return: True if successful, False otherwise
    :rtype: bool
    """
    # test if file has a header line
    with open(inputfile, 'r') as fd:
        line1 = fd.readline()
    if bool(re.search('[a-zA-Z]', line1)) > 0:
        header = 0
    else:
        header = None
    df = pd.read_csv(inputfile,
                     sep=r'\s+', header=header, names=['x', 'y', 'z'])
    if len(df.index) < 4:
        # skip empty files
        return False

    if utm_remove_zone:
        df['x'] = np.sign(df['x']) * (np.abs(df['x']) % 1000000)
    # get full grid axes
    try:
        x_res = np.mean(np.diff(sorted(set(df['x']))))
        x_vals = set(
            np.arange(df['x'].min(), df['x'].max() + x_res, x_res))
        y_res = np.mean(np.diff(sorted(set(df['y']))))
        y_vals = set(
            np.arange(df['y'].min(), df['y'].max() + y_res, y_res))
    except ValueError:
        # skip all-NaN files etc.
        return False
    # create full dataframe
    ff = pd.DataFrame.from_records(itertools.product(x_vals, y_vals),
                                   columns=['x', 'y'])
    of = pd.merge(ff, df, how='left', left_on=['x', 'y'],
                  right_on=['x', 'y'])
    del [ff, df]
    of = of.replace(np.nan, -9999.)

    # sort it so gdal doesnt complain
    of = of.sort_values(['y', 'x'])

    of.to_csv(output, index=False, header=False)

    return True


# -------------------------------------------------------------------------
def get_dataset_crs(filename):
    """
    Query the projection of a geo data file
    :param filename: name of the file (optionally with leading path)
    :type filename: str
    :return: Projection of the geo data file ind the form "EPSG:xxxx"
    :rtype: str
    """
    # with ... does not work with gda.Open()
    ds = gdal.Open(filename, gdal.GA_ReadOnly)
    prj = ds.GetProjection()
    # make sure file is closed
    del ds
    srs = osr.SpatialReference(wkt=prj)
    jsrs = srs.ExportToPROJJSON()
    srsid = json.loads(jsrs)['id']
    epsg = '%s:%i:' % (srsid['authority'], srsid['code'])
    return epsg

# -------------------------------------------------------------------------
def get_dataset_driver(filename):
    """
    Query the driver (i.e. fiel format) of a geo data file
    :param filename: name of the file (optionally with leading path)
    :type filename: str
    :return: Projection of the geo data file ind the form "EPSG:xxxx"
    :rtype: str
    """
    # with ... does not work with gda.Open()
    ds = gdal.Open(filename, gdal.GA_ReadOnly)
    drv = ds.GetDriver().ShortName
    # make sure file is closed
    del ds
    return drv

# -------------------------------------------------------------------------
def get_dataset_nodata(filename):
    """
    Query the NODATA value of a geo data file
    :param filename: name of the file (optionally with leading path)
    :type filename: str
    :return: nodata value
    :rtype: float
    """
    # with ... does not work with gda.Open()
    ds = gdal.Open(filename, gdal.GA_ReadOnly)
    rc = ds.RasterCount
    if rc != 1:
        logger.warning(f'multiple Bands, returning Band1 of: {filename}')
    nodata = ds.GetRasterBand(1).GetNoDataValue()
    # make sure file is closed
    del ds
    return nodata

# -------------------------------------------------------------------------
def _ass_xyz2tif(inputfile, srcsrs, utm_remove_zone):
    """
    convert xyz file (via csv) to GeoTiff

    :param inputfile: input file
    :type inputfile: str
    :param srcsrs: SRS of the input file (as "EPSG:xxxxx")
    :type srcsrs: str
    :param utm_remove_zone: Some providers prefix UTM easting with the
      zone numer, which results in easting values exceeding 1000km.
      Remove the leading digits to keep easting in the allowed range
      0m < easting < 1000000 m. defaults to False.
    :type utm_remove_zone: bool
    :return: output file name (GeoTiff)
    :rtype: str
    """
    if os.stat(inputfile).st_size == 0:
        logger.debug(f"skipping empty  ... {inputfile}")
        os.remove(inputfile)
        return None
    tf1 = re.sub(r'\.xyz$', '.tif', inputfile)
    logger.debug(f"converting tile ... {inputfile} -> {tf1}")
    # returns a tuple containing file handle and the abs pathname!
    csvhdl, csvfile = tempfile.mkstemp(
        prefix='dgm', suffix='.csv', dir=TEMP)
    got_csv = xyz2csv(inputfile, csvfile,
                      utm_remove_zone=utm_remove_zone)
    os.remove(inputfile)
    if not got_csv:
        logger.warning(f"did not convert ... {inputfile}")
        os.close(csvhdl)
        os.remove(csvfile)
        return None
    gdal.Translate(destName=tf1,
                   srcDS=csvfile,
                   outputSRS=srcsrs,
                   noData=-9999,
                   )
    os.close(csvhdl)
    os.remove(csvfile)
    return tf1


# -------------------------------------------------------------------------
def _ass_reduce_tile(tf1, out_res, overwrite=True):
    """
    Resamples a tile (or any file that can be autodetected by gdal)
    to a differen (only lower makse sense) resolution and saves ist as
    GeoTiff

    :param tf1: name (and optionally path) of the input file
    :type tf1: str
    :param out_res: output resolution (i.e. pixel width) in km
    :type out_res: float
    :param overwrite: overwrite existing output file
    :type overwrite: bool
    :return: name (and path if supplied in `tf1`) of the output file
    or empty stringif no file is written
    :rtype: str
    """
    tfxx = os.path.splitext(tf1)[0] + ".reduced.tif"
    if os.path.exists(tfxx) and not overwrite:
        # reduced file exist and shall be kept
        return ''
    logger.debug(f"resampling tile ... {tf1} -> {tfxx}")
    try:
        gdal.Warp(destNameOrDestDS=tfxx,
                  xRes=out_res,
                  yRes=out_res,
                  srcDSOrSrcDSTab=tf1,
                  format="GTiff")
    except Exception as e:
        logger.error(str(e))
    os.remove(tf1)
    return tfxx


# -------------------------------------------------------------------------
def _ass_unpack(dl_file, unpack):
    """
    Unpack files from an archive

    :param dl_file: filename, otionally incl. path, of the archive (downloadad file)
    :type dl_file: str
    :param unpack: string describing what to unpack
    :type unpack: str
    :return: names of the files extracted
    :rtype: list[str]
    :raises ValeError: if `unpack` string is invalid
    """
    inputfiles = []
    if unpack in [None, '', 'tif', 'false']:
        inputfiles = [dl_file]
    elif unpack.startswith(('zip', 'unzip')):
        try:
            with zipfile.ZipFile(dl_file, 'r') as zf:
                pattern = re.sub('^(un|)zip://', '', unpack)
                unpack_files = [x for x in zf.namelist()
                                if PurePath(x).match(pattern)]
                inputfiles = []
                for un in unpack_files:
                    if not os.path.exists(os.path.basename(un)):
                        # in case of overlapping archives
                        # do not overwrite existing files
                        # leave the processing to the other thread
                        with zf.open(un) as fz:
                            with open(os.path.basename(un), 'wb') as fu:
                                fu.write(fz.read())
                        inputfiles.append(os.path.basename(un))
        except Exception as e:
            raise IOError(f'zip file error processing {dl_file}')
    else:
        raise IOError(f"dont know how to handle download: {dl_file}")

    if len(inputfiles) == 0:
        logger.warning(f"no data unpacked from {dl_file}")
    return inputfiles


# -------------------------------------------------------------------------
def _ass_merge_tiles(target, tile_files):
    """
    merge the GeoTiff Files from all tiles into one file

    :param target: name, optionally including path) of the file to generate
    :type target:  str
    :param tile_files: Input files to merge
    :type tile_files: list[str]
    :raises Exception: if gdal_merge aborts with error

    """
    if os.path.exists(target):
        logger.info("removing old source file")
        os.remove(target)
    logger.debug("merging tiles ...")
    # handling of nodata: see https://gis.stackexchange.com/a/304202
    in_nodata = get_dataset_nodata(tile_files[0])
    if in_nodata is None:
        n_option = []
    else:
        n_option = ['-n', str(in_nodata)]
    tile_drvs = [get_dataset_driver(x) for x in tile_files]
    drivers = sorted(set(tile_drvs), key = lambda x: tile_drvs.count(x))
    if len(drivers) > 1:
        logger.warning("merging mixed-format tiles")
    driver = drivers.pop()
    if driver == "GTiff":
        merged_file = 'merged.tif'
        co_opts = [
            "-co", "compress=lzw",
            "-co", "bigtiff=yes",
        ]
    elif driver == "netCDF":
        merged_file = 'merged.nc'
        co_opts = [
            "-co", "FORMAT=NC4C",
            "-co", "COMPRESS=DEFLATE",
            "-co", "ZLEVEL=9"
        ]
    else:
        raise ValueError(f"unsopported driver {driver}")
    gdal_merge_options = ["",
                     "-init", str(NODATA),
                     "-a_nodata", str(NODATA)
                     ] + n_option + co_opts + [
                     "-o", merged_file,
                     ] + tile_files
    gdal_merge.main(gdal_merge_options)
    s_srs = get_dataset_crs(merged_file)
    if DEM_FMT.endswith('.tif'):
        if s_srs == DEM_CRS:
            # we already have the wanted product
            shutil.move(merged_file, target)
        else:
            logger.debug(f"reprojecting to target projection {DEM_CRS}")
            gdal.Warp(destNameOrDestDS=target,
                      dstSRS=DEM_CRS,
                      srcDSOrSrcDSTab=merged_file,
                      format="GTiff",
                      creationOptions=["BIGTIFF=YES"]
                      )
    elif DEM_FMT.endswith('.nc'):
        logger.debug(f"converting and reprojecting to {DEM_CRS}")
        gdal.Warp(srcDSOrSrcDSTab=merged_file,
                  destNameOrDestDS=target,
                  dstSRS=DEM_CRS,
                  format="netCDF",
                  creationOptions=[
                      "FORMAT=NC4C",
                      "COMPRESS=DEFLATE",
                      "ZLEVEL=9"]
                  )
    else:
        raise Exception(f'cannot handle DEM_FMT: {DEM_FMT}')
    logger.debug(f"... written {target}")


# -------------------------------------------------------------------------

def _ass_expand_filelist_string(string, base_url, verify,
                                xmlp, jsonp, linkp):

    list_name = re.sub(r'::.*$', '', string)
    url = '/'.join((base_url, list_name))
    if string.endswith(('xml', 'meta4')):
        # xml
        if xmlp in ["",None]:
            ValueError("xmlpath needed but not defined")
        logger.debug("downloading xml metadata: %s" % url)
        with requests.get(url, allow_redirects=True,
                          verify=verify) as rsp:
            input_files = _tools.xmlpath(xml=rsp.content.decode(),
                                  path=xmlp)
    elif string.endswith(('json', 'geojson')):
        # json
        if jsonp in ["",None]:
            ValueError("jsonpath needed but not defined")
        logger.debug("downloading json metadata: %s" % url)
        with requests.get(url, allow_redirects=True,
                          verify=verify) as rsp:
            input_files = _tools.jsonpath(json_obj=rsp.json(),
                                   path=jsonp)
    elif string.endswith(('html')):
        # html
        if linkp in ["",None]:
            ValueError("links pattern needed but not defined")
        logger.debug("downloading html metadata: %s" % url)
        with requests.get(url, allow_redirects=True,
                          verify=verify) as rsp:
            text = rsp.content.decode()
            links = [x for x in re.findall(r'href="(.+?)"', text)]
            input_files = [x for x in links if bool(re.match(linkp, x))]
            method = 'http'
    elif '::' in string:
        # type specified but not known
        raise ValueError(f'unknown filelist type in: {string}')
    else:
        # no expansion
        input_files = [string]
    return input_files

# -------------------------------------------------------------------------
def _ass_clear_target(target, replace):
    """
    assure that a datafile is not already present

    :param target: path of the datafile
    :type target: str
    :param name: name of the datafile
    :type name: str
    :param replace: If True, the file is removed if it exists;
      if False, None is returned
    :type replace: bool
    :return: name and path of the datafile or None
    :rtype: str or None
    """
    logger.debug(f'data file path: {target}')
    res = True
    if os.path.exists(target):
        if not replace:
            logger.info("dataset exists ... %s" % target)
            res = False
        else:
            logger.info("deleting existig : %s" % target)
            os.remove(target)
    return res


# -------------------------------------------------------------------------
def _ass_process_input(args):
    """
    Worker funtion to process a downloaded file into one or more
    data (tile) file(s) of the desired resolution and projection

    :param args: tuple containg the arguments
      - inp: location of the input file. Either file and path or URL
      - base_url: base url to prepend to inp, omitted if inp is a URL
      - verify: enable (True) or disable (False) server certificate check
      - provider: dict containing the processing arguments
        - provider['localstore']: (str, optional)
          path where local copies of the download files are stored.
          Files that exist in this directory are copied from there and not downloaded.
          Successfully downloaded files are copied to this location.
        - provider['missing']: (str, optional)
          if 'ok', 'ignore', an empty list is returned,
          if the URL download fails with error 404 (not found)
        - provider["unpack"]: (str, optional)
          the description, what to unpack.
        - provider["CRS"]: (str, optional)
          the referecnce system of the input data (in the form "EPSG:xxxx")
        - provider["utm_remove_zone"]: (str, optional)
          If 'True', 'true', 'yes', True is passed
          to :py:func:`_ass_reduce`
    :type args: tuple[str, str, bool, dict]
    :return: list of the generated files
    :rtype: list[str]
    """
    inp, base_url, verify, provider = args
    unpack = provider.get('unpack', None)
    localstore = provider.get('localstore', None)
    out_res = provider.get('resolution', 25)
    srcsrs = provider.get('CRS', None)
    if provider.get('utm_remove_zone', 'true') in ['True', 'true', 'yes']:
        utm_remove_zone = True
    else:
        utm_remove_zone = False
    dl_file = os.path.basename(inp)

    url = None
    if localstore is not None:
        # 1st priority: get a locally stored file
        localfile = os.path.join(localstore, dl_file)
        if os.path.exists(localfile):
            url = 'file://' + os.path.abspath(localfile)
    if url is None:
        # 2nd priority: download the file
        if re.match('^http[s]*://', inp):
            url = inp
        else:
            url = f"{base_url}/{inp}"

    failure_ok = False
    if re.match('^http[s]*://', url):
        logger.debug(f"downloading ... {url}")
        for i in range(MAX_RETRY):
            with requests.get(url, verify=verify, stream=True) as req:
                if req.status_code == requests.codes.ok:
                    with open(dl_file, 'wb') as f:
                        for chunk in req.iter_content(chunk_size=4096):
                            if chunk:
                                f.write(chunk)
                elif req.status_code == 404:
                    missing = provider.get('missing', None)
                    if missing in ['ok', 'ignore']:
                        failure_ok = True
                        logger.info(f"ignoring failed download: {url}")
                        # break retry loop
                        break
                    elif missing == 'wait':
                        logger.info(f"wait after failed download: {url}")
                        time.sleep(30)
                        # netx try
                        continue
                try:
                    inputfiles = _ass_unpack(dl_file, unpack)
                    if localstore is not None:
                        shutil.move(dl_file, localstore)
                    # no retry if unpack successful
                    break
                except IOError as e:
                    logger.error(f"retry download after error "
                                 f"unpacking {dl_file}")
        else:
            raise Exception(f"failed to download: {url}")
    elif re.match('^file://', url):
        logger.debug(f"copying file... {url}")
        url = re.sub('^file:/+', '/', url)
        try:
            shutil.copy(url, dl_file)
        except IOError:
            if ('missing' in provider and
                    provider['missing'] in ['ok', 'ignore']):
                logger.info(f"ignoring missing file: {url}")
                failure_ok = True
        inputfiles = _ass_unpack(dl_file, unpack)

    tile_files = []
    if not failure_ok:
        for inputfile in inputfiles:
            if inputfile.endswith('tif'):
                tf1 = inputfile
            elif inputfile.endswith('xyz'):
                tf1 = _ass_xyz2tif(inputfile, srcsrs, utm_remove_zone)
            else:
                raise Exception(f'cannot handle {inputfile}')
            if tf1 is not None:
                tfxx = _ass_reduce_tile(tf1, out_res, overwrite=False)
                if tfxx != "":
                    tile_files.append(tfxx)

    if os.path.exists(dl_file):
        os.remove(dl_file)
    return tile_files


# -------------------------------------------------------------------------
def assemble_DGMxx(path: str, name: str, replace: bool,
                   args: dict):
    """
    Versatile function to assemble a dataset containing a
    digital elevation model (DEM),
    German: "digitales Geländemodell (DGM) of user selectable resolution.

    :param path: Path and filename of the file to generate
    :type path: str
    :param name: name (code) of the dataset to assemble
    :type name: str
    :param replace: If True, an existing file is overwritten.
        If False, an error is raises if the file already exists.
    :type replace: bool
    :param args: The arguments neede to preform the asembly.
        for more details see :doc:`configure-austaltools`.

        - provider['host']: (str)
          Hostname and protocol from where to download data.
          Supported protocols are :code:`"http://..."`,
          :code:`"https://..."`, and  :code:`"file:///..."`.
        - provider['cert-check']: (str, optional)
          Wether to check the server certificates of `host` or not.
          Disables verification by setting this value to
          "no" or "false". Defaults to "true".
        - provider['filelist']: (str or list, optional)
          list of filenames to download or "generate" or Path or URL
          to file that contains this list.
        - provider['localstore']: (str, optional)
          path to local storage of the downloaded files.
          Locally saved files have priority over downloaded files.
          Successfully downloaded files are copied to this location.
        - provider['jsonpath']: (str, optional)
          Pattern how to extract file list from `filelist`
          if it points to a json file
          See :py:func:`jsonpath`
        - provider['xmlpath']: (str, optional)
          Pattern how to extract file list from `filelist`
          if it points to an xml file
          See :py:func:`xmlpath`
        - provider['links']: (str, optional)
          Regular expression to extract file list from `filelist`
          if it points to a htmls file,
          by filtering all links in `filelist`.
        - provider['missing']: (str, optional)
          if 'ok', 'ignore', an empty list is returned,
          if the URL download fails with error 404 (not found)
        - provider["unpack"]: (str, optional)
          the description, what to unpack (see `unpack string`_)
        - provider["CRS"]: (str, optional)
          the referecnce system of the input data (in the form "EPSG:xxxx")
        - provider["utm_remove_zone"]: (str, optional)
          If 'True', 'true', 'yes', True is passed
          to :py:func:`_ass_reduce`
    :type args: dict
    :return: Success (True) of Failure (False)
    :rtype: bool
    """
    target = os.path.join(path, DEM_FMT % name)
    if not _ass_clear_target(target, replace):
        logger.info("skipping because dataset exists: %s" % name)
        return False

    base_url = '/'.join((args['host'], args['path']))
    if 'check_cert' in args:
        verify = args['check_cert']
    else:
        verify = True
    filelist = args['filelist']
    # switch formats:
    method = input_files = capabilities = layer = None
    # if filelist is string, make a list
    if isinstance(filelist, str):
        if filelist == 'generate':
            exp_val = []
            for x in args['values']:
                if isinstance(x, list):
                    exp_val.append(x)
                else:
                    exp_val.append(_tools.expand_sequence(x))
            combval = itertools.product(*exp_val)
            filelist = [args['format'] % x for x in combval]
        else:
            filelist = [filelist]
    input_files = []
    for string in filelist:
        x = _ass_expand_filelist_string(
            string, base_url, verify,
            args.get('xmlpath', None),
            args.get('jsonpath', None),
            args.get('links', None))
        input_files += x
    method = 'http'

    if method == 'http':
        # parallel processing of input_files:
        thread_args = []
        for inp in input_files:
            thread_args.append((inp, base_url, verify, args))
        tile_files = []
        if ((PROCS is None and os.cpu_count() > len(input_files)) or
                (PROCS is not None and PROCS > len(input_files))):
                pp = len(input_files)
        else:
            pp = PROCS
        i = 0
        with mp.Pool(pp) as pool:
            for tfs in _tools.progress(pool.imap_unordered(
                    _ass_process_input, thread_args),
                    total=len(thread_args)):
                i = i + 1
                logger.debug("file %5d / %5d" % (i, len(thread_args)))
                tile_files += tfs
    else:
        raise ValueError(f'method {method} not implemented')

    # merge the GeoTiff Files from all tiles into one file
    _ass_merge_tiles(target, tile_files)
    logger.info(f"data file written: {target}")

    return True


# -------------------------------------------------------------------------
def _ass_sh_getfid(args):
    """
    get individual file for DGM1-SH

    :param args: download number, total no of downloads, file-id, args
    :type args: tupe[int, int, int, dict]
    :return: names of extracted files
    :rtype: list[str]
    """
    i, ni, fid, provider = args
    baseurl = ('https://geodaten.schleswig-holstein.de/'
               'gaialight-sh/_apps/dladownload')

    localstore = provider.get('localstore', '.')
    localname = os.path.join(localstore, "id-%06d.zip" % fid)

    if os.path.exists(localname):
        shutil.copy(localname, '.')
        logger.debug('locally avalable fid: %s' % fid)
        dl_file = os.path.basename(localname)
    else:
        for ntry in range(MAX_RETRY):
            try:
                session = requests.Session()
                _ = session.get(baseurl + 'dl-dgm1.html',
                                verify=False)
                request = session.get(baseurl + '/_ajax/details.php?' +
                                      f'type=dgm1&id={str(fid)}')
                response = request.json()
                if 'object' not in response:
                    print(f"problem with fid {fid}: {str(response)}")
                    return

                tilename = response['object']['kachelname']
                filename = tilename + '.xyz'

                if os.path.exists(filename):
                    logger.debug(
                        "-- %5d/%5d -- exists   %s " % (i, ni, tilename))
                    return
                else:
                    logger.debug(
                        "-- %5d/%5d -- download %s " % (i, ni, tilename))

                timestr = time.strftime('%s', time.gmtime())
                start = session.get(
                    baseurl + '/multi.php?' +
                    f'url={filename}&buttonClass=file1&id={str(fid)}&'
                    f'type=dgm1&action=start&_={timestr}',
                    verify=False)
                response = start.json()
                if response['success']:
                    job_id = response['id']
                else:
                    if response['message'] == ('1 Datei konnte nicht '
                                               'gefunden werden'):
                        logger.debug("                  file not found")
                        return
                    else:
                        raise Exception(response['message'])
                running = True
                downloadurl = None
                while running:
                    request = session.get(
                        baseurl + f'/multi.php?action=status&job={job_id}',
                        verify=False)
                    response = request.json()
                    logger.debug(response)
                    if response.get('status', '') in ['wait', 'work']:
                        # wait
                        time.sleep(2)
                    elif response.get('msg', '') == 'Interner Fehler':
                        # next ty
                        continue
                    else:
                        # proceed to download
                        downloadurl = response['downloadUrl']
                        break
                request = session.get(downloadurl, verify=False)
                dl_file = tilename + '.zip'
                with open(dl_file, 'wb') as fn:
                    fn.write(request.content)
                break
            except (requests.exceptions.ConnectionError,
                    exceptions.ProtocolError) as e:
                logger.error("exception downloading %s; %s" % (fid, e))

            ntry = ntry + 1
        else:
            raise IOError("downloading failed %s times: fid %s" %
                          (MAX_RETRY, fid))

        if localstore is not None:
            shutil.copy(dl_file, localname)

    unpack = provider.get('unpack', None)
    out_res = provider.get('resolution', 25)
    inputfiles = _ass_unpack(dl_file, unpack)
    srcsrs = provider['CRS']
    utm_remove_zone = provider.get('UTM_ZONE', False)
    tilefiles = []
    for tile_xyz in inputfiles:
        logger.debug("converting tile ... %s" % tile_xyz)
        tf1 = _ass_xyz2tif(tile_xyz, srcsrs, utm_remove_zone)
        if tf1 is not None:
            tfxx = _ass_reduce_tile(tf1, out_res)
            if tfxx != "":
                tilefiles.append(tfxx)

    if os.path.exists(dl_file): os.remove(dl_file)
    return tilefiles


def assemble_DGM_SH(path, name, replace, args: dict):
    """
    Special function to assemble a digital elevation model (DEM)
    of the German state Schlewig-Holstein (SH)
    It is designed to scrape their "Downloadclient" website.

    :param path:  Path where to generate the file
    :type path: str
    :param name: name (code) of the dataset to assemble
    :type name: str
    :param replace: If True, an existing file is overwritten.
        If False, an error is raises if the file already exists.
    :type replace: bool
    :param args: Optionally accepted for compatiblity with the
        general asseble funtion call. Is not evaluated.
    :type args: dict
    :return: Success (True) of Failure (False)
    :rtype: bool
    """
    target = os.path.join(path, DEM_FMT % name)
    if not _ass_clear_target(target, replace):
        logger.info("skipping because dataset exists: %s" % name)
        return False

    # download all the tiles
    # number of tiles manually retrieved 2024-08-4:
    fids = [x for x in range(1, 18686)]
    random.shuffle(fids)
    args = [(i, len(fids), x, args) for i, x in enumerate(fids)]
    tile_files = []
    with mp.Pool(PROCS) as pool:
        for tf in _tools.progress(
                pool.imap_unordered(_ass_sh_getfid, args),
                total=len(args)
        ):
            tile_files += tf

    _ass_merge_tiles(target, tile_files)

    return True


# -------------------------------------------------------------------------
def assemble_DGM25_RP(path, name="DGM25-RP",
                      replace=False, args: dict = {}):
    """
    Special function to assemble the 25-m digital elevation model (DEM)
    of the German state Rheinland-Pfalz (RP) that has been
    avaliable online before all states had to licence their 1-m DEM
    as open data.

    .. deprecated:: 1.0
       use :py:func:`assemble_DGMxx` instead.

    :param path: Path where to generate the file
    :type path: str
    :param name: name (code) of the dataset to assemble
    :type name: str
    :param replace: If True, an existing file is overwritten.
        If False, an error is raises if the file already exists.
    :type replace: bool
    :param provider: Optionally accepted for compatiblity with the
        general asseble funtion call. Is not evaluated.
    :type provider: dict
    :return: Success (True) of Failure (False)
    :rtype: bool
    """
    target = os.path.join(path, DEM_FMT % name)
    if not _ass_clear_target(target, replace):
        logger.info("skipping because dataset exists: %s" % name)
        return False

    url = "https://vermkv.service24.rlp.de/opendat/dgm25/dgm25.zip"
    logger.debug("downloading ... %s" % url)
    zip_file, _ = _tools.download(url, os.path.basename(url))
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
    tile_files = glob.glob("DGM25_*.tif")
    _ass_merge_tiles(target, tile_files)

    return True


# -------------------------------------------------------------------------
def assemble_DGM_composit(path: str, name: str,
                          replace: bool = False, args: dict = {}):
    """
    Special function to assemble a digital elevation model (DEM)
    that is a composit of other datasets or files or a mixture thereof.

    .. note::
       If a composit includes other datasets, they must be assembled
       *before* calling this function.

    :param path: Path where to generate the file
    :type path: str
    :param name: name (code) of the dataset to assemble
    :type name: str
    :param replace: If True, an existing file is overwritten.
        If False, an error is raises if the file already exists.
    :type replace: bool
    :param provider: Optionally accepted for compatiblity with the
        general asseble funtion call. Is not evaluated.
    :type provider: dict
    :return: Success (True) of Failure (False)
    :rtype: bool
    """
    target = os.path.join(path, DEM_FMT % name)
    if not _ass_clear_target(target, replace):
        logger.info("skipping because dataset exists: %s" % name)
        return False

    logger.info("compositing ... %s" % name)
    logger.debug("target file ... %s" % target)
    members = []
    for x in args['filelist']:
        logger.debug("scanning input ... %s" % x)
        if x in SOURCES_TERRAIN:
            # expand dataset codes
            if not dataset_available(x):
                logger.error("dataset not available %s" % x)
                continue
            filename = os.path.join(dataset_get(x).path,
                                    dataset_get(x).file_data)
            if not os.path.isfile(filename):
                logger.error(f"dataset file {filename} not available")
                continue
        else:
            # use filename
            if os.path.exists(x):
                filename = x
            elif os.path.exists(os.path.join(path, x)):
                filename = os.path.join(path, x)
            else:
                logger.error("file not available %s" % x)
                continue
        members.append(filename)

    logger.debug("found input files: %s" % len(members))
    if len(members) <= 1:
        raise ValueError('no datasets available for compositing')

    vrt_name = "merged.vrt"
    out_res = args.get('resolution', None)
    if out_res is not None:
        res_opts = {"xRes": out_res, "yRes": out_res}
    else:
        res_opts = {}

    # tip from https://gis.stackexchange.com/a/385864
    with (tempfile.TemporaryDirectory(dir=TEMP) as tmp):
        logger.debug("build virtual dataset")
        gdal.BuildVRT(os.path.join(tmp, vrt_name), members)
        logger.debug("writing data file %s" % target)
        if DEM_FMT.endswith('.tif'):
            gdal.Translate(destName=target,
                           srcDS=os.path.join(tmp, vrt_name),
                           format="GTiff",
                           creationOptions=["BIGTIFF=YES"],
                           **res_opts
                           )
        elif DEM_FMT.endswith('.nc'):
            gdal.Translate(destName=target,
                           srcDS=os.path.join(tmp, vrt_name),
                           format="netCDF",
                           creationOptions=[
                               "FORMAT=NC4C",
                               "COMPRESS=DEFLATE",
                               "ZLEVEL=9"],
                           **res_opts
                           )
        else:
            raise Exception(f'cannot handle DEM_FMT: {DEM_FMT}')
    return True


# -------------------------------------------------------------------------
def assemble_GLO_30(path, name = "GLO_30",
                    replace : bool = False, args: dict = {}):
    """
    Special function to assemble the GLO_30 digital elevation model (DEM)
    from European Copernicus service.

    .. note::
        To run this funtion successfully,
        the user must have an active Copernicus user account that can be
        obtained at the Copernicus user's portal:
        <https://cdsportal.copernicus.eu/web/spdm/registeruser>

    :param path:  Path where to generate the file
    :type path: str
    :param name: name (code) of the dataset to assemble
    :type name: str
    :param replace: If True, an existing file is overwritten.
        If False, an error is raises if the file already exists.
    :type replace: bool
    :param args: Optionally accepted for compatiblity with the
        general asseble funtion call. Is not evaluated.
    :type args: dict
    :return: Success (True) of Failure (False)
    :rtype: bool
    """
    target = os.path.join(path, DEM_FMT % name)
    if not _ass_clear_target(target, replace):
        logger.info("skipping because dataset exists: %s" % name)
        return False

    download_dir = ("https://prism-dem-open.copernicus.eu/" +
                    "pd-desk-open-access/prismDownload/" +
                    "COP-DEM_GLO-30-DGED__2022_1/")
    file_fmt = "Copernicus_DSM_10_N%02i_00_E%03i_00.tar"

    for lat in range(47, 54):
        for lon in range(5, 16):
            url = download_dir + file_fmt % (lat, lon)
            logger.debug("downloading ... %s" % url)
            tar_file, _ = _tools.download(url, os.path.basename(url))
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
    tile_files = glob.glob("Copernicus_*.tif")
    _ass_merge_tiles(target, tile_files)

    return


# -------------------------------------------------------------------------
def assebmle_GTOPO30(path: str, name="GTOPO30",
                     replace=False, args: dict = {}):
    """
    Special function to assemble the GTOPO30 elevation model (DEM)
    from UCAR.edu.

    .. note::
        GTOPO30 has a worlwide coverage but only the tile 'W020N90'
        is downloaded as only this one covers the area where the
        target SRS is valid.

    :param path:  Path where to generate the file
    :type path: str
    :param name: name (code) of the dataset to assemble
    :type name: str
    :param replace: If True, an existing file is overwritten.
        If False, an error is raises if the file already exists.
    :type replace: bool
    :param provider: Optionally accepted for compatiblity with the
        general asseble funtion call. Is not evaluated.
    :type provider: dict
    :return: Success (True) of Failure (False)
    :rtype: bool
    """
    support_url = ("https://data.rda.ucar.edu/ds758.0/support/"
                   + "GTOPO30support.tar.gz")
    download_fmt = ("https://data.rda.ucar.edu/ds758.0/elevtiles/" +
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
    logger.debug("downloading ... %s" % support_url)
    support_file, _ = _tools.download(
        support_url, os.path.basename(support_url))
    with tarfile.open(support_file) as support_tar:
        # no get every tile we want
        for tile in tiles:
            # extract the matching supportive files
            to_extract = [x.name for x in support_tar.getmembers()
                          if tile in x.name]
            support_tar.extractall(members=to_extract)
            # now download the actual data file for the tile
            download_url = download_fmt % tile
            logger.debug("downloading ... %s" % download_url)
            tile_file, _ = _tools.download(
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
    tile_files = glob.glob("*.tif")
    _ass_merge_tiles(target, tile_files)

    return


# -------------------------------------------------------------------------
def provide_terrain(source: str, path: str = None,
                    force: bool = False, method: str = 'download'):
    """
    Funciton that makes a terrain dataset (digital elevation model, DEM)
    locally available, using the chosen method.

    :param source: ID of the dataset to make vailable
    :type source: str
    :param path: Path to where to write the dataset files.
      If None, the lowest-proirity (i.e. most system-wide)
      writable location of the standard stroage locations in
      :py:const:`_tools.STORAGE_LOCATIONS` is selected.
      Defaults to None.
    :type path: str or None, optional
    :param force: Wheter to overwrite a dataset that is already avialable.
      Defaults to False.
    :type force: bool, options
    :param method: The method how to get the dataset.
      Defaults to `'download'`.
        :`'download'`: the ready-assembled dataset ist downloadad
          form a location specified in the dataset definition.
        :`'assemble'`: the dataset is created from data that are acquired
          (if possible) from an original supplier.
    :type method: str

    :raises ValueError: if `method` is not one of the allowed values.
    """
    if path is None:
        path = find_writeable_storage(path, _tools.STORAGE_TERRAIN)
    dataset = dataset_get(source)
    logger.info("providing terrain source %s" % source)
    if method == 'download':
        if dataset.uri is None:
            raise Exception("Dataset has no download uri, assemble it.")
        dataset.download(path)
    elif method == 'assemble':
        # change to temp directory
        pwd = os.getcwd()
        with tempfile.TemporaryDirectory(dir=TEMP) as temp_dir:
            os.chdir(temp_dir)
            logger.debug('calling %s' % str(dataset.assemble))
            dataset.assemble(path, source, force, dataset.arguments)
            # return before clean up
            os.chdir(pwd)
    else:
        raise ValueError("method must be either 'download' or 'assemble'")

    # auxiliary files:
    if dataset.license is not None:
        lic_file = os.path.join(path, dataset.file_license)
        lic_src, lic_id = dataset.license.split(':')
        if lic_src == 'spdx':
            lic_url = ("https://spdx.org/licenses/%s.json" %
                       lic_id)
            with requests.get(lic_url).json() as lic_json:
                with open(lic_file, 'wb') as f:
                    f.write(lic_json['licenseText'])
        elif lic_src == 'file':
            if lic_id in [None, '']:
                lic_aux = os.path.join(str(DIST_AUX_FILES), lic_file)
            else:
                lic_aux = os.path.join(str(DIST_AUX_FILES), lic_id)
            shutil.copy(lic_aux, lic_file)
    if dataset.notice is not None:
        not_file = os.path.join(path, dataset.file_license)
        with open(not_file, 'w') as f:
            f.write(dataset.notice)
    return


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
    print('data copyright notice:')
    with open(os.path.join(storage_path,
                           "%s.NOTICE.txt" % source), "r") as f:
        for x in f.readlines():
            print(x)


# -------------------------------------------------------------------------
def _ass_era5_getyear(year):
    """
    Downloads ERA5 reanalysis data for a specific year and
    saves it as a NetCDF file.

    The function calls the Climate Data Store (CDS) API to retrieve
    a specific set of meteorological variables for
    the entire year specified by the user. It requests data in
    NetCDF format, covering a predefined geographic
    extent focusing on Alaska and Europe. This function is specifically
    designed to automate the retrieval process
    for ERA5 weather variables, saving the data in a structured format
    that's easier to work with for further analysis.

    :param opts: A tuple containing two elements:
                 - `y`: The year for which to download the data (integer).
                 - `path`: The directory path where the NetCDF file should
                   be saved (string).
    :type opts: tuple

    :returns: None. The function saves a NetCDF file to the specified
      path but does not return any value.

    :example:
        >>> # To download ERA5 data for the year 2020 and
        >>> save it to the specified directory
        >>> era5_getyear((2020, '/path/to/directory'))

    :note:
    - The function crafts a filename based on the year, prefixing it
      with `era5_ak_eu_` to denote the region and
      type of data retrieved. Ensure that the specified directory exists
      and is writable.
    - The library `cdsapi` must be installed and a **valid CDS API key**
      must be configured as per the `cdsapi` package documentation.
    """

    ncname = 'era5_ak_eu_{:04d}.nc'.format(int(year))
    c = cdsapi.Client()
    c.retrieve(
        'reanalysis-era5-single-levels',
        {
            'product_type': 'reanalysis',
            'variable': [
                '10m_u_component_of_wind', '10m_v_component_of_wind',
                '2m_dewpoint_temperature',
                '2m_temperature', 'forecast_surface_roughness',
                'friction_velocity',
                'surface_latent_heat_flux', 'surface_pressure',
                'surface_sensible_heat_flux',
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
        ncname)
    return ncname


# -------------------------------------------------------------------------
def assemble_ERA5(path: str, name="ERA5", years: list =[],
                  replace : bool = False, args : dict ={}):
    """
    Downloads and assembles ERA5 reanalysis data for a list of specified
    years, saving the data to a designated path.

    This function serves as a wrapper around the `era5_getyear` function,
    facilitating the batch retrieval of ERA5
    data for multiple years. It utilizes multiprocessing to download data
    in parallel, thereby significantly reducing
    the overall time required for downloading large datasets. Each year's
    data is saved as a separate NetCDF file within
    the specified directory path.

    :param path: The file system path where the downloaded NetCDF files
      will be saved.
    :type path: str
    :param name: name (code) of the dataset to assemble
    :type name: str
    :param years: A list of years for which ERA5 data should be downloaded.
      Each year should be an integer within the
      valid range (1940 to the current year).
    :type years: list
    :param replace: If True, an existing file is overwritten.
        If False, an error is raises if the file already exists.
    :type replace: bool
    :param args: Optionally accepted for compatiblity with the
        general asseble funtion call. Is not evaluated.
    :type args: dict

    :raises ValueError: If any year in the `years` list is outside the
      allowable range of 1940 to the current year.

    :example:

        >>> # To download ERA5 data for the years 2018 to 2020
        >>> # and save to '/data/ERA5'
        >>> assemble_ERA5('/data/ERA5', years=[2018, 2019])

    :note:

    - The function assumes that the `era5_getyear` function is defined
      and correctly set up to retrieve ERA5 data.
    - The parallel downloading process is set to use 10 worker processes.
      Adjust this value in the `Pool` initialization
      as needed based on system resources and desired performance.
    - Ensure that sufficient disk space is available at the specified
      path to accommodate the downloaded data files.
    - Needs `cdsapi` for data retrieval and a **valid CDS API** key.

    """

    # create option tuples
    combi = []
    for year in years:
        yn = name_yearly(name, year)
        if yn not in [x.name for x in DATASETS]:
            raise ValueError(f"year is out of range: {year}")
        if not replace:
            if dataset_get(yn).available:
                logger.info(f"skipping available year: {yn}")
                continue
        combi.append(year)
    # get data in parallel directly to storage
    with mp.Pool(PROCS) as pool:
        for dld in pool.map(_ass_era5_getyear, combi):
            year, ncname = dld
            yn = name_yearly(name, year)
            target = os.path.join(path, WEA_FMT % yn)
            # gently move the old file out of way
            if not _ass_clear_target(target, replace):
                logger.info("skipping because dataset exists: %s" % name)
                os.remove(ncname)
                continue
            shutil.move(ncname, target)

# -------------------------------------------------------------------------
def _cerraname(y, lt=None):
    """
    assembles CERRA data file name from year and part
    :param y: year
    :type y: int
    :param lt: part number
    :type lt: int
    :return:  filename
    :rtype: str
    """
    name = 'cerra_ak_eu_%04i' % y
    if lt is not None:
        name += '_%01i' % lt
    return name


# -------------------------------------------------------------------------
def _ass_cerra_getyear(opts):
    """
    Downloads and processes a year's worth of CERRA dataset as GRIB files,
    then converts them to NetCDF format for easier use.

    This function takes a tuple containing the year (`y`)
    and lead time (`lt`) for the forecast data.
    It builds the filename for the GRIB file from these parameters
    and checks if it exists locally.
    If not, it uses the CDS API to retrieve the data for all
    specified variables over the entire year, saving it as a GRIB file.
    After downloading, the function processes the GRIB file,
    converting it to a NetCDF file for more convenient analysis and removes
    the original GRIB file to conserve space.

    Requires the `cdsapi` and `cdo` (Climate Data Operators) packages,
    as well as an active Copernicus account for data retrieval.

    :param opts: A tuple containing two elements:
                 - `y` (int): The year of the dataset to retrieve.
                 - `lt` (int): The lead time in hours for the forecast data.
    :type opts: tuple

    A sample of expected parameter format: `(2023, 48)`

    :returns: None. The function's primary purpose is file I/O
              (downloading and converting data).
              It does not return a value but will print status messages
              regarding its progress.

    :raises FileNotFoundError: If the CDO command fails to find the
            downloaded GRIB file for conversion.

    :example:

        >>> # To download and process the CERRA data for the year 2023
        >>> # with a lead time of 48 hours
        >>> cerra_getyear((2023, 48))

    :note:

    - The 'cdsapi' Client is used for data retrieval, requiring
      a **valid CDS API key**
      set up as per the CDS API's documentation.
    - The 'cdo' tool is called for data processing, necessitating
      its installation and availability in the system's PATH.
    - This function assumes `cerraname` returns a base filename to which
      `.grib` or `.nc` is appended for output files.

    """
    logger.debug("start job %s" % str(opts))
    logger.debug(str(opts))
    y, lt = opts
    gribname = _cerraname(y, lt) + '.grib'
    c = cdsapi.Client()
    if not os.path.exists(gribname):
        print("cds getting: " + gribname)
        opts = (
            'reanalysis-cerra-single-levels',
            {
                'data_type': 'reanalysis',
                'product_type': 'forecast',
                'variable': [
                    '10m_wind_direction', '10m_wind_speed',
                    '2m_relative_humidity',
                    '2m_temperature', 'low_cloud_cover',
                    'medium_cloud_cover',
                    'momentum_flux_at_the_surface_u_component',
                    'momentum_flux_at_the_surface_v_component',
                    'surface_latent_heat_flux',
                    'surface_pressure', 'surface_roughness',
                    'surface_sensible_heat_flux',
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
        ncname = _cerraname(y, lt) + '.nc'
        logger.debug("cdo  subsetting: " + ncname)
        print(os.getcwd())
        oper = cdo.Cdo(os.getcwd())
        print(" ".join([str(x) for x in
                       ['489,649,479,659', '-f nc',
                        gribname, ncname]]
        ))
        oper.selindexbox('489,649,479,659', options='-f nc',
                        input=gribname, output=ncname)
        print('piep')
        del oper
        logger.debug("done subsetting: " + ncname)
        os.remove(gribname)
    logger.debug("done job %s" % str(opts))


# -------------------------------------------------------------------------
def assemble_CERRA(path: str, name="CERRA", years: list = [],
                   replace : bool = False, args : dict ={}):
    """
    Downloads, extracts, and merges CERRA dataset forecasts for specified
    years into single NetCDF files per year.

    This function orchestrates the retrieval and processing of
    CERRA forecast datasets for a list of years.
    For each year, it fetches data for multiple lead times, extracts a
    specific region from the datasets, and then merges
    the forecast data into a single NetCDF file per year. The operation
    utilizes the Climate Data Operators (CDO) for data
    manipulation and assumes a temporary directory is defined for
    intermediate data storage.

    :param path: The path where the final merged NetCDF files
      will be stored.
    :type path: str
    :param name: name (code) of the dataset to assemble
    :type name: str
    :param years: A list of years (integer) for which CERRA data should
      be downloaded and processed. The years should fall
      within the range of 1940 to the current year.
    :type years: list
    :param replace: If True, an existing file is overwritten.
        If False, an error is raises if the file already exists.
    :type replace: bool
    :param args: Optionally accepted for compatiblity with the
        general asseble funtion call. Is not evaluated.
    :type args: dict

    :raises ValueError: If any of the years specified is outside the
      valid range (1940 to the current year).

    :example:

        >>> # To process CERRA data for the years 2015 to 2017
        >>> assemble_CERRA('/path/to/final/storage', years=[2015, 2016])

    :note:

    - The function utilizes `cdo.Cdo` for data manipulation tasks such as
      merging time steps. Make sure that python-cdo is
      installed and properly configured along with the actual CDO
      command-line tools.
    - A temporary directory for storing intermediate data files is
      required. This directory is assumed to be configured before
      the function call.
    - After processing, intermediate data files are removed to free
      up space.
    - This function assumes that a global `TEMP` variable is defined and
      points to a valid temporary directory for intermediate files.

    """
    temp_path = TEMP
    logger.debug(f"looking for cdo ...{temp_path}")
    data = cdo.Cdo(tempdir=temp_path)
    logger.debug("python-cdo version: %s" % data.__version__())
    logger.debug("cdo        version: %s" % data.version())
    data.debug = True
    data.cleanTempDir()

    # get sets of bunches to retrieve
    combi = []
    for year in years:
        yn = name_yearly(name, year)
        if yn not in [x.name for x in DATASETS]:
            raise ValueError(f"year is out of range: {year}")
        if not replace:
            if dataset_get(yn).available:
                logger.info(f"skipping available year: {yn}")
                continue
        for lt in range(1, 4):
            combi.append((year, lt))
    logger.debug("forking parallel jobs: "+str(combi))


    # get data and extract region
    with mp.Pool(CDSAPI_LIMIT_PARALLEL) as pool:
        _ = pool.map(_ass_cerra_getyear, combi)

    logger.debug("finished parallel jobs")
    # combine forecasts
    for year in set([x for x, _ in combi]):
        logger.debug(f"processing year: {year}")
        lts = set([y for x, y in combi if x == year])
        infiles = [_cerraname(year, lt) + '.nc' for lt in lts]
        yn = name_yearly(name, year)
        target = os.path.join(path, WEA_FMT % yn)
        # gently move the old file out of way
        if not _ass_clear_target(target, replace):
            logger.info("skipping because dataset exists: %s" % name)
            continue
        # build new file
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
        logger.debug(f"finished with: {year}")


# -------------------------------------------------------------------------
def assemble_DWD(path: str, name="DWD", years: list = None,
                   replace : bool = False, args : dict ={}):
    """
    Downloads, extracts, and merges DWD dataset observations for specified
    years into single NetCDF files per year.

    :param path: The path where the final merged NetCDF files
      will be stored.
    :type path: str
    :param name: name (code) of the dataset to assemble
    :type name: str
    :param years: A list of years (integer) for which DWD data should
      be downloaded and processed.
    :type years: list
    :param replace: If True, an existing file is overwritten.
        If False, an error is raises if the file already exists.
    :type replace: bool
    :param args: Optionally accepted for compatiblity with the
        general asseble funtion call. Is not evaluated.
    :type args: dict

    :raises ValueError: If any of the years specified is outside the
      valid range (1940 to the current year).

    - This function assumes that a global `TEMP` variable is defined and
      points to a valid temporary directory for intermediate files.

    """
    # check years
    if years is None:
        if 'years' in args:
            years = args['years']
        else:
            raise ValueError(f"years is required for DWD dataset")
    # check database
    target = os.path.join(path, OBS_FMT % name)
    if not _ass_clear_target(target, replace):
        logger.info("skipping because dataset exists: %s" % name)
        return False
    # get list of stations
    logger.info("fetching stationlists")
    stations = _dwd_observations.dwd_fetch_stationlist(years)
    station_numbers = stations.keys()

    # download and process all stations
    #zip = zipfile.ZipFile(target)
    logger.info("writing stationlist")
    sf = pd.DataFrame.from_dict(stations, orient='index')
    with zipfile.ZipFile(target,
                         mode='a',
                         compression=zipfile.ZIP_DEFLATED) as zf:
        sf.to_csv(path_or_buf=zf.open('stationlist.csv',
                                          mode='w'))

    logger.info("fetching data")
    for station in _tools.progress(station_numbers):
        dat_in, meta_in =_dwd_observations.dwd_fetch_station(station,
                                                             store=False)
        df = _dwd_observations.build_table(dat_in, meta_in, years)

        with zipfile.ZipFile(target,
                             mode='a',
                             compression=zipfile.ZIP_DEFLATED) as zf:
            df.to_csv(path_or_buf=zf.open("%05i.csv" % station,
                                          mode='w'))

# -------------------------------------------------------------------------
def provide_weather(source: str, path: str = None,
                    years: list = None,
                    force: bool = False, method: str = 'download'):
    """
    Manages the downloading and organizing of weather data from
    specified sources for given years into a target directory.

    This function serves as a high-level interface for downloading
    weather datasets (for example, ERA5 or CERRA) for a specified set of
    years and organizing them into a specified directory. The function
    currently supports the 'download' method with potential for future
    expansion.

    :param source: The name of the weather dataset source.
      Currently supports "ERA5" or "CERRA".
    :type source: str
    :param path: Optional; the file system path where the downloaded
      data will be saved. If not specified, the function
      attempts to find a writable storage location using
      `find_writeable_storage`.
    :type path: str, optional
    :param years: A list of integer years for which to download
      the data. If not specified, no year-specific
      data fetching is performed, which may depend on the
      implementation details of the dataset handling functions.
    :type years: list, optional
    :param force: Wheter to overwrite a dataset that is already avialable.
      Defaults to False.
    :type force: bool, options
    :param method: The method to use for obtaining the data.
      Currently, only "download" is implemented, but the parameter
      is designed to accommodate future methods like "cache" or "stream".
    :type method: str, optional

    :returns: A boolean value indicating the success (`True`) or failure
      (`False`) of the data downloading and organization process.

    :example:

        >>> # To download ERA5 data for the years 2020 and 2021
        >>> # into the default storage location
        >>> success = provide_weather("ERA5", years=[2020, 2021])
        True

    :note:

    - This function logs its operations, including informational messages
      on progress and errors encountered.
    - The actual implementation for finding writable storage or the setup
      for the logger is not defined in this function, and
      should be provided in the surrounding context.

    :raises:

    - This function may raise exceptions internally but catches them to
      return a boolean success status. Detailed error
      information is logged.
    """

    # param method is implemented for future use
    if path is None:
        path = find_writeable_storage(path, _tools.STORAGE_WAETHER)
    #dataset = dataset_get(source)
    logger.info("downloading weather source %s" % source)
    success = True
    pwd = os.getcwd()
    with tempfile.TemporaryDirectory(dir=TEMP) as temp_dir:
        os.chdir(temp_dir)
#        try:
        success = True
        if source == "ERA5":
            assemble_ERA5(path, years=years)
        elif source == "CERRA":
            assemble_CERRA(path, years=years, replace=force)
        elif source == "DWD":
            dataset = dataset_get(source)
            assemble_DWD(path, years=years, replace=force,
                         args=dataset.arguments)
        else:
            logger.error("unknown dataset to download %s" % source)
            success = False
        # except Exception as e:
        #     logger.error(str(e))
        #     success = False
    # return before clean up
    os.chdir(pwd)
    return success


# -------------------------------------------------------------------------
def name_yearly(name, year):
    return '%s-%04i' % (name, year)

# -------------------------------------------------------------------------
def expand_datasets(defs: dict):
    datasets = []
    for k,v in defs.items():
        if "split" in v.keys():
            if v["split"] == "years":
                years_available = _tools.expand_sequence(
                    v["years_available"])
                for ya in years_available:
                    name = name_yearly(k, ya)
                    vy = v.copy()
                    if 'uri' in v and isinstance(v['uri'], dict):
                        vy['uri'] = v['uri'][str(ya)]
                    datasets.append(DataSet(name=name, **vy))
            else:
                raise ValueError(f"unkown split type {v['split']}")
        else:
            datasets.append(DataSet(name=k, **v))
    return datasets

# -------------------------------------------------------------------------
# initialize
DATASETS = expand_datasets(DATASET_DEFINITIONS)
"""
All known datasets as :py:class:`DataSet` instances.

:meta hide-value:
"""
PROCS = None
"""
Number of parallel processes to run downlading data or  
`None`. If `None` the number of processor cores in the system is used.
"""
dataset_scan()
