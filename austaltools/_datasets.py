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
import sys
import tarfile
import tempfile
import zipfile


import pandas as pd
import pip
import requests
from urllib3 import disable_warnings, exceptions

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import multiprocessing as mp
    import concurrent.futures as mpf
    from osgeo import gdal
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
    from . import _fetch_dwd_obs
    from . import _fetch_dgm_od
except ImportError:
    from _version import __version__, __title__
    import _tools
    import _fetch_dwd_obs
    import _fetch_dgm_od

disable_warnings(exceptions.InsecureRequestWarning)
logger = logging.getLogger()

# -------------------------------------------------------------------------
CDSAPI_LIMIT_PARALLEL = 2
""" Copernicus per-user limit for parallel queries """

with (_tools.DIST_AUX_FILES / 'dataset_definitions.json').open() as f:
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
            for i in range(_tools.MAX_RETRY):
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
            if self.storage == 'terrain':
                self.file_data = _tools.DEM_FMT % self.name
            elif self.storage == 'weather':
                pos = kwargs.get('position', None)
                if pos == 'station':
                    self.file_data = _tools.OBS_FMT % self.name
                elif pos in ['grid', None]:
                    self.file_data = _tools.WEA_FMT % self.name
                else:
                    raise ValueError(f"unkown position: {pos}")


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
def dataset_scan(locs : list = None):
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

def _ass_clear_target(target, replace):
    """
    assure that a datafile is not already present

    :param target: path of the datafile
    :type target: str
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
          to :py:func:`_fetch_dgm_od._ass_reduce_tile`
    :type args: dict
    :return: Success (True) of Failure (False)
    :rtype: bool
    """
    target = os.path.join(path, _tools.DEM_FMT % name)
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
        x = _fetch_dgm_od.expand_filelist_string(
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
                    _fetch_dgm_od.process_input, thread_args),
                    total=len(thread_args)):
                i = i + 1
                logger.debug("file %5d / %5d" % (i, len(thread_args)))
                tile_files += tfs
    else:
        raise ValueError(f'method {method} not implemented')

    # merge the GeoTiff Files from all tiles into one file
    _fetch_dgm_od.merge_tiles(target, tile_files)
    logger.info(f"data file written: {target}")

    return True


# -------------------------------------------------------------------------


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
    target = os.path.join(path, _tools.DEM_FMT % name)
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
                pool.imap_unordered(_fetch_dgm_od.dgm1_sh_getfid, args),
                total=len(args)
        ):
            tile_files += tf

    _fetch_dgm_od.merge_tiles(target, tile_files)

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
    target = os.path.join(path, _tools.DEM_FMT % name)
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
    _fetch_dgm_od.merge_tiles(target, tile_files)

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
    target = os.path.join(path, _tools.DEM_FMT % name)
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
    with (tempfile.TemporaryDirectory(dir=_tools.TEMP) as tmp):
        logger.debug("build virtual dataset")
        gdal.BuildVRT(os.path.join(tmp, vrt_name), members)
        logger.debug("writing data file %s" % target)
        if _tools.DEM_FMT.endswith('.tif'):
            gdal.Translate(destName=target,
                           srcDS=os.path.join(tmp, vrt_name),
                           format="GTiff",
                           creationOptions=["BIGTIFF=YES"],
                           **res_opts
                           )
        elif _tools.DEM_FMT.endswith('.nc'):
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
            raise Exception(f'cannot handle _tools.DEM_FMT: {_tools.DEM_FMT}')
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
    target = os.path.join(path, _tools.DEM_FMT % name)
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
    target = os.path.join(path, _tools.DEM_FMT % "GLO-30")
    tile_files = glob.glob("Copernicus_*.tif")
    _fetch_dgm_od.merge_tiles(target, tile_files)

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
    target = os.path.join(path, _tools.DEM_FMT % "GTOPO30")
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
    _fetch_dgm_od.merge_tiles(target, tile_files)

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
        with tempfile.TemporaryDirectory(dir=_tools.TEMP) as temp_dir:
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
                lic_aux = os.path.join(str(_tools.DIST_AUX_FILES), lic_file)
            else:
                lic_aux = os.path.join(str(_tools.DIST_AUX_FILES), lic_id)
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
        >>> # save it to the specified directory
        >>> _ass_era5_getyear((2020, '/path/to/directory'))

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
            target = os.path.join(path, _tools.WEA_FMT % yn)
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
        cwd = os.getcwd()
        logger.debug(f'cwd: {cwd}')
        oper = cdo.Cdo(tempdir=cwd)
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
    return True


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
    - This function assumes that a global `_tools.TEMP` variable is defined and
      points to a valid temporary directory for intermediate files.

    """
    temp_path = _tools.TEMP
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
    with mpf.ThreadPoolExecutor(max_workers=CDSAPI_LIMIT_PARALLEL) as e:
        for c in combi:
            future = e.submit(_ass_cerra_getyear, c)
            #_ = future.result()

    logger.debug("finished parallel jobs")
    # combine forecasts
    for year in set([x for x, _ in combi]):
        logger.debug(f"processing year: {year}")
        lts = set([y for x, y in combi if x == year])
        infiles = [_cerraname(year, lt) + '.nc' for lt in lts]
        yn = name_yearly(name, year)
        target = os.path.join(path, _tools.WEA_FMT % yn)
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

    - This function assumes that a global `_tools.TEMP` variable is defined and
      points to a valid temporary directory for intermediate files.

    """
    # check years
    if years is None:
        if 'years' in args:
            years = args['years']
        else:
            raise ValueError(f"years is required for DWD dataset")
    # check database
    target = os.path.join(path, _tools.OBS_FMT % name)
    if not _ass_clear_target(target, replace):
        logger.info("skipping because dataset exists: %s" % name)
        return False
    # get list of stations
    logger.info("fetching stationlists")
    stations = _fetch_dwd_obs.fetch_stationlist(years)
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
        dat_in, meta_in =_fetch_dwd_obs.fetch_station(station,
                                                      store=False)
        df = _fetch_dwd_obs.build_table(dat_in, meta_in, years)

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
    with tempfile.TemporaryDirectory(dir=_tools.TEMP) as temp_dir:
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

