#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import itertools
import json
import logging
import os
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import PurePath


import numpy as np
import pandas as pd
import requests
from urllib3 import disable_warnings, exceptions

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    from osgeo import gdal
    from osgeo import osr
    from osgeo_utils import gdal_merge

try:
    from ._version import __version__, __title__
    from . import _tools
except ImportError:
    from _version import __version__, __title__
    import _tools

disable_warnings(exceptions.InsecureRequestWarning)
logger = logging.getLogger()

# -------------------------------------------------------------------------

NODATA = 9.96920996838686905e+36
""" terrain data `noddata` value """

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
    Query the projection of a geo data file.

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
def xyz2tif(inputfile, srcsrs, utm_remove_zone):
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
        prefix='dgm', suffix='.csv', dir=_tools.TEMP)
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
def reduce_tile(tf1, out_res, overwrite=True):
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
def unpack_file(dl_file, unpack):
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
def merge_tiles(target, tile_files):
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
    if _tools.DEM_FMT.endswith('.tif'):
        if s_srs == _tools.DEM_CRS:
            # we already have the wanted product
            shutil.move(merged_file, target)
        else:
            logger.debug(f"reprojecting to target projection "
                         f"{_tools.DEM_CRS}")
            gdal.Warp(destNameOrDestDS=target,
                      dstSRS=_tools.DEM_CRS,
                      srcDSOrSrcDSTab=merged_file,
                      format="GTiff",
                      creationOptions=["BIGTIFF=YES"]
                      )
    elif _tools.DEM_FMT.endswith('.nc'):
        logger.debug(f"converting and reprojecting to {_tools.DEM_CRS}")
        gdal.Warp(srcDSOrSrcDSTab=merged_file,
                  destNameOrDestDS=target,
                  dstSRS=_tools.DEM_CRS,
                  format="netCDF",
                  creationOptions=[
                      "FORMAT=NC4C",
                      "COMPRESS=DEFLATE",
                      "ZLEVEL=9"]
                  )
    else:
        raise Exception(f'cannot handle _tools.DEM_FMT: {_tools.DEM_FMT}')
    logger.debug(f"... written {target}")


# -------------------------------------------------------------------------

def expand_filelist_string(string, base_url, verify,
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

def dgm1_sh_getfid(args):
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
        for ntry in range(_tools.MAX_RETRY):
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
                          (_tools.MAX_RETRY, fid))

        if localstore is not None:
            shutil.copy(dl_file, localname)

    unpack = provider.get('unpack', None)
    out_res = provider.get('resolution', 25)
    inputfiles = unpack_file(dl_file, unpack)
    srcsrs = provider['CRS']
    utm_remove_zone = provider.get('UTM_ZONE', False)
    tilefiles = []
    for tile_xyz in inputfiles:
        logger.debug("converting tile ... %s" % tile_xyz)
        tf1 = xyz2tif(tile_xyz, srcsrs, utm_remove_zone)
        if tf1 is not None:
            tfxx = reduce_tile(tf1, out_res)
            if tfxx != "":
                tilefiles.append(tfxx)

    if os.path.exists(dl_file): os.remove(dl_file)
    return tilefiles

# -------------------------------------------------------------------------

def process_input(args):
    """
    Worker funtion to process a downloaded file into one or more
    data (tile) file(s) of the desired resolution and projection

    :param args: tuple containg the arguments:

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
        for i in range(_tools.MAX_RETRY):
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
                    inputfiles = unpack_file(dl_file, unpack)
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
        inputfiles = unpack_file(dl_file, unpack)

    tile_files = []
    if not failure_ok:
        for inputfile in inputfiles:
            if inputfile.endswith('tif'):
                tf1 = inputfile
            elif inputfile.endswith('xyz'):
                tf1 = xyz2tif(inputfile, srcsrs, utm_remove_zone)
            else:
                raise Exception(f'cannot handle {inputfile}')
            if tf1 is not None:
                tfxx = reduce_tile(tf1, out_res, overwrite=False)
                if tfxx != "":
                    tile_files.append(tfxx)

    if os.path.exists(dl_file):
        os.remove(dl_file)
    return tile_files
