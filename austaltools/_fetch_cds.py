#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import calendar
import datetime
import glob
import logging
import os
import json
import shutil
import tempfile
import time
import zipfile
from copy import deepcopy
from typing import Any

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import multiprocessing as mp
    import ecmwf.datastores as _edsapi

from . import _storage
from . import _netcdf
from . import _tools

logger = logging.getLogger(__name__)

WEA_WINDOW = (33, 71, -12, 36)
""" standard lat/lon window for worldwide weather datasets 
    latmin, latmax, lonmin, lonmax """
API_LIMIT_PARALLEL = 2
""" Copernicus per-user limit for parallel queries """
ECMWF_CHUNKS = True
""" Copernicus per-request limit does not permit download of 
    yearly files and requires splitting up donwloads. 
    For possible values see 
    :py:func:`austaltools._dataset.cds_get_cerra_year` """
ORDERFILE: str = "cds_orders.json"
""" JSON file used to persist CDS request IDs across interrupted runs.
    Written to the current working directory (i.e. next to the output
    ``.nc`` files). """

# -------------------------------------------------------------------------

def cds_merge_zipped(source, destination,
                     compression= _storage.COMPRESS_NETCDF):
    """
    Merge the netCDF files contained in a zipped archive downloaded from
    the Copernicus Climate Data Store (cds.climate.copernicus.eu) into a
    single netCDF file.

    The archive is extracted to a temporary directory; all ``*.nc`` files
    found there are merged via :py:func:`_netcdf.merge_variables` and
    written to *destination*.  The temporary directory is deleted
    afterwards unless the logger is set to ``DEBUG`` level.

    :param source: path of the zip archive to read
    :type source: str

    :param destination: path of the netCDF output file to create
    :type destination: str

    :param compression: compression method passed to
      :py:func:`_netcdf.merge_variables`.
      Defaults to :py:const:`_storage.COMPRESS_NETCDF`.
    :type compression: str | None

    :raises IOError: if the archive contains no ``*.nc`` files
    """
    source_file = os.path.abspath(source)
    logger.info("unpacking downloaded zip archive %s" % source_file)
    destination_file = os.path.abspath(destination)
    delete_tmp = (logger.getEffectiveLevel() > logging.DEBUG)
    with (tempfile.TemporaryDirectory(
            ignore_cleanup_errors=True, dir=_storage.TEMP,
            delete=delete_tmp) as td):
        with zipfile.ZipFile(source_file, 'r') as zf:
            zf.extractall(td)
        ncfiles = glob.glob(os.path.join(td, '*.nc'))
        if len(ncfiles) == 0:
            raise IOError("No files found in %s" % source)

        logger.debug("creating netcdf file %s" % destination_file)
        if os.path.exists(destination_file):
            os.remove(destination_file)

        _netcdf.merge_variables(ncfiles, destination_file,
                                compression=compression)

# -------------------------------------------------------------------------

def cds_replace_valid_time(compression:str|None = _storage.COMPRESS_NETCDF):
    """
    Build the *replace* and *convert* dicts needed to swap the
    ``valid_time`` variable in ECMWF/CDS products (seconds since
    1970-01-01) for the more widely used ``time`` variable (hours since
    1900-01-01).

    The returned dicts are intended to be passed directly to
    :py:func:`_netcdf.merge_variables` as its ``replace`` and ``convert``
    keyword arguments.

    :param compression: compression method used when constructing the
      target :py:class:`_netcdf.VariableSkeleton`.
      Usually ``'zlib'``.  Defaults to :py:const:`_storage.COMPRESS_NETCDF`.
    :type compression: str | None

    :returns: A 2-tuple ``(replace, convert)`` where

      * ``replace`` maps the source variable name ``'valid_time'`` to a
        :py:class:`_netcdf.VariableSkeleton` describing the new ``'time'``
        variable.
      * ``convert`` maps ``'valid_time'`` to a callable that converts
        values from *seconds since 1970-01-01* to *hours since 1900-01-01*.
    :rtype: tuple[dict, dict]
    """

    # replace time variable
    stime_name = 'valid_time'
    stime_unit = 'seconds since 1970-01-01'
    dtime_name = 'time'
    dtime_unit = 'hours since 1900-01-01'

    dtime_var = _netcdf.VariableSkeleton(
        dtime_name, 'd',
        dimensions=(dtime_name,),
        compression=compression,
    )
    dtime_var.setncattr('long_name', dtime_name)
    dtime_var.setncattr('standard_name', dtime_name)
    dtime_var.setncattr('units', dtime_unit)
    dtime_var.setncattr('calendar', 'proleptic_gregorian')

    dtime_fun = _netcdf.timeconverter(stime_unit, dtime_unit)

    replace = {stime_name: dtime_var}
    convert = {stime_name: dtime_fun}

    return replace, convert

# -------------------------------------------------------------------------

def _cds_orderlist_clear(orderfile:str = ORDERFILE):
    """
    Delete the order-list file from disk, discarding all cached request IDs.

    Silently does nothing when the file does not exist.

    :param orderfile: path of the JSON order-list file to remove.
      Defaults to :py:const:`ORDERFILE`.
    :type orderfile: str
    """
    if os.path.exists(orderfile):
        logger.debug(f"cleared orderlist")
        os.unlink(orderfile)

# -------------------------------------------------------------------------

def _cds_orderlist_get(target:str, orderfile:str = ORDERFILE):
    """
    Retrieve the cached CDS request ID for *target* from the order-list file.

    :param target: name of the target file whose request ID is sought
    :type target: str

    :param orderfile: path of the JSON order-list file.
      Defaults to :py:const:`ORDERFILE`.
    :type orderfile: str

    :returns: the stored request ID string, or ``None`` if the file does
      not exist or *target* has no entry.
    :rtype: str | None
    """
    if not os.path.exists(orderfile):
        logger.debug(f"could not orderlist: {target}")
        return None
    with open(orderfile, 'r') as f:
        orders = json.load(f)
    if target not in orders:
        logger.debug(f"could not find in orderlist: {target}")
        return None
    return orders[target]

# -------------------------------------------------------------------------

def _cds_orderlist_add(target:str, result: _edsapi.Remote,
                       orderfile:str = ORDERFILE):
    """
    Persist a CDS request ID in the order-list file.

    If the file already exists its contents are read first so that
    existing entries are preserved.  The file is always written as
    pretty-printed JSON.

    :param target: name of the target file associated with the request
    :type target: str

    :param result: the CDS request ID to store (typically a string
      returned by ``_edsapi.Remote.request_id``)
    :type result: str

    :param orderfile: path of the JSON order-list file.
      Defaults to :py:const:`ORDERFILE`.
    :type orderfile: str
    """
    orders: dict
    if os.path.exists(orderfile):
        with open(orderfile, 'r') as f:
            orders = json.load(f)
    else:
        orders = {}
    logger.debug(f"add to orderlist: {target}")
    orders[target] = result
    with open(orderfile, 'w') as f:
            json.dump(orders, f)

# -------------------------------------------------------------------------

def _cds_orderlist_del(target:str, orderfile:str = ORDERFILE):
    """
    Remove a target's entry from the order-list file.

    If the file does not exist, or *target* has no entry, the function
    logs a debug message and returns without error.

    :param target: name of the target file whose entry should be removed
    :type target: str

    :param orderfile: path of the JSON order-list file.
      Defaults to :py:const:`ORDERFILE`.
    :type orderfile: str
    """
    orders: dict
    if os.path.exists(orderfile):
        with open(orderfile, 'r') as f:
            orders = json.load(f)
    else:
        orders = {}
    if target in orders:
        del orders[target]
        logger.debug(f"deleted from orderlist: {target}")
    else:
        logger.debug(f"could not delete noexistent order: {target}")
    with open(orderfile, 'w') as f:
            json.dump(orders, f)

# -------------------------------------------------------------------------

def cds_getorder(order_args: dict[str, Any],
                 ignore_cache: bool = False) -> str:
    """
    Submit one CDS order and return the path of the fully processed
    target file.

    The function implements a three-level resume strategy so that
    interrupted runs can be restarted without re-submitting jobs or
    re-downloading data:

    - Target already on disk and valid → return immediately.
    - Download file already on disk and valid →
      go straight to post-processing via :py:func:`cds_processorder`.
    - Cached request ID found (in :py:const:`ORDERFILE`) → re-attach
       to the running server job, wait for completion, then download.
    - No cache entry → submit a new order, store the request ID,
       wait for completion, then download.

    After downloading, the raw file is post-processed by
    :py:func:`cds_processorder` (unzipping, spatial subsetting, time
    variable conversion) before the target path is returned.

    :param order_args: order description dictionary with the keys:

      * ``dataset`` *(str)* – CDS dataset name (e.g.
        ``'reanalysis-era5-single-levels'``).
      * ``request`` *(dict)* – request body as described in the
        `CDS API how-to
        <https://cds.climate.copernicus.eu/how-to-api>`_.
      * ``target`` *(str)* – local filename of the final processed file
        to produce.
      * ``subset`` *(dict, optional)* – spatial subset passed through to
        :py:func:`cds_processorder`.
    :type order_args: dict[str, Any]

    :param ignore_cache: if ``True``, skip all on-disk and order-list
      checks and unconditionally re-submit the request.
      Defaults to ``False``.
    :type ignore_cache: bool

    :returns: path of the processed target file (guaranteed to exist).
    :rtype: str

    :raises RuntimeError: if the ``ecmwf-datastores`` client library is
      not available.
    """
    dataset = order_args["dataset"]
    request = order_args["request"]
    target = order_args["target"]
    downloaded = "_" + target


    logger.info(f"processing file {target}")

    request_id = False
    if not  ignore_cache:
        # Target already on disk?
        if os.path.exists(target):
            if not _netcdf.file_check_ok(target):
                logger.info(f"Target {target!r} already exists, "
                         f"but contains errors.")
                os.unlink(target)
            else:
                logger.info(f"Target {target!r} already exists, "
                            f"skipping order process.")
                _cds_orderlist_del(target)
                return target

        # Download file already on disk?
        if os.path.exists(downloaded):
            if not _netcdf.file_check_ok(downloaded):
                logger.info(f"Download {downloaded!r} already exists, "
                            f"but contains errors.")
                os.unlink(downloaded)
            else:
                logger.info(f"Download {downloaded!r} already exists, ")
                target = cds_processorder(downloaded, order_args)
                _cds_orderlist_del(target)
                return target

        request_id = _cds_orderlist_get(target)

    if ignore_cache or not request_id:
        logger.info(f"Placing an order for target: {target} ")
        client = _edsapi.Client()
        remote = client.submit(dataset, request)
        request_id = remote.request_id
        _cds_orderlist_add(target, request_id)
        del client

    client = _edsapi.Client()
    remote = client.get_remote(request_id)

    while remote.status != "successful":
        logger.debug(f"order {target} has remote status: {remote.status}")
        time.sleep(30)

    logger.info(f"downloading {target}")
    remote.download(downloaded)
    _cds_orderlist_del(target)

    logger.info(f"preprocessing {target}")
    produced = cds_processorder(downloaded, order_args)

    return produced

# -------------------------------------------------------------------------

def _apply_subset(target: str, subset: dict) -> None:
    """
    Apply a spatial subset to a netCDF file **in place** using xarray.

    The function writes the subsetted data to a temporary file alongside
    *target* and then atomically replaces *target* with it via
    :py:func:`os.replace`.

    The x- and y-dimension names are not assumed: the function tries the
    common variants ``('x', 'longitude', 'lon', 'rlon')`` and
    ``('y', 'latitude', 'lat', 'rlat')`` and uses the first pair that is
    actually present in the dataset.  If ``subset['by_index']`` is
    ``True``, integer positional slicing (:py:meth:`xarray.Dataset.isel`)
    is used; otherwise coordinate-value slicing
    (:py:meth:`xarray.Dataset.sel`) is used.

    .. note::
        In the normal download flow, subsetting is handled by
        :py:func:`cds_processorder` (via :py:func:`_netcdf.subset_xy`).
        This function is kept as a fallback for callers that cannot use
        ``cds_processorder`` (e.g. files not in the standard order-args
        format).

    :param target: path of the netCDF file to subset in place
    :type target: str

    :param subset: subsetting specification with the keys:

      * ``xmin`` *(int | float)* – lower bound of the x dimension
        (index or coordinate value, depending on ``by_index``).
      * ``xmax`` *(int | float)* – upper bound of the x dimension.
      * ``ymin`` *(int | float)* – lower bound of the y dimension.
      * ``ymax`` *(int | float)* – upper bound of the y dimension.
      * ``by_index`` *(bool, optional)* – if ``True``, treat the bounds
        as integer positional indices; if ``False`` (default), treat them
        as coordinate values.
    :type subset: dict

    :raises ImportError: if ``xarray`` is not installed (logged as a
      warning; the function returns without modifying *target*).
    """
    try:
        import xarray as xr
    except ImportError:
        logger.warning("xarray not available – skipping subset step.")
        return

    xmin = subset["xmin"]
    xmax = subset["xmax"]
    ymin = subset["ymin"]
    ymax = subset["ymax"]
    tmp = target + ".subset.tmp.nc"

    logger.info(f"Applying spatial subset to {target!r}")
    ds = xr.open_dataset(target)

    # Try index-based subsetting first, fall back to value-based.
    # The x/y dimension names differ between datasets; try common variants.
    for xdim in ("x", "longitude", "lon", "rlon"):
        for ydim in ("y", "latitude", "lat", "rlat"):
            if xdim in ds.dims and ydim in ds.dims:
                if subset.get("by_index", False):
                    ds = ds.isel({xdim: slice(xmin, xmax),
                                  ydim: slice(ymin, ymax)})
                else:
                    ds = ds.sel({xdim: slice(xmin, xmax),
                                 ydim: slice(ymin, ymax)})
                break

    enc = {v: {"zlib": True, "complevel": 4} for v in ds.data_vars} \
        if _storage.COMPRESS_NETCDF else {}
    ds.to_netcdf(tmp, encoding=enc)
    ds.close()
    os.replace(tmp, target)

# -------------------------------------------------------------------------

def cds_processorder(downloaded: str,
                     order_args: dict[str, str | dict],
                     compression: str | None = _storage.COMPRESS_NETCDF) -> str:
    """
    Post-process a file downloaded by :py:func:`cds_getorder`.

    Three transformations are applied in sequence:

    1. Unzip – if ``downloaded`` is a zip archive (as returned by the
       CDS API since 2024), its netCDF members are merged into a single
       plain netCDF file via :py:func:`cds_merge_zipped`.
    2. Spatial subset – if ``order_args['subset']`` is present, the
       data are cropped via :py:func:`_netcdf.subset_xy`.
    3. Time variable conversion – ``valid_time`` (seconds since
       1970-01-01) is replaced by ``time`` (hours since 1900-01-01) via
       :py:func:`cds_replace_valid_time` and :py:func:`_netcdf.merge_variables`.

    :param downloaded: path of the raw downloaded file to process.
      For the normal CDS flow this is ``'_' + target``.
    :type downloaded: str

    :param order_args: order description dictionary.  Must contain:

      * ``target`` (str) – name of the final output file to produce.

      May optionally contain:

      * ``subset`` (dict) – keyword arguments for
        :py:func:`_netcdf.subset_xy` (excluding ``src`` and ``dst``).
        If absent, no spatial subsetting is applied.
    :type order_args: dict[str, str | dict]

    :param compression: compression method passed to
      :py:func:`_netcdf.merge_variables` and :py:func:`_netcdf.subset_xy`.
      Defaults to :py:const:`_storage.COMPRESS_NETCDF`.
    :type compression: str | None

    :returns: path of the final processed output file (equal to
      ``order_args['target']``).
    :rtype: str

    :raises ValueError: if ``order_args`` does not contain the key
      ``'target'``.
    """
    target = order_args.get('target',None)
    if target is None:
        raise ValueError("target key must be specified in oder_args")

    # unzip if necessary
    if zipfile.is_zipfile(downloaded):
        zipname = downloaded + '.zip'
        shutil.move(downloaded, zipname)
        cds_merge_zipped(zipname, downloaded)
        os.remove(zipname)

    # subset
    oldtime = 'oldtime_' + target
    if order_args.get('subset', None) is not None:
        _netcdf.subset_xy(downloaded, oldtime, **order_args['subset'],
                          compression=compression)
        os.remove(downloaded)
    else:
        shutil.move(downloaded, oldtime)

    # convert time
    replace, convert = cds_replace_valid_time(compression)
    _netcdf.merge_variables([oldtime], target,
                            replace=replace, convert=convert,
                            compression=compression,
                            remove_source=True)
    if os.path.exists(oldtime):
        os.remove(oldtime)

    return target

# -------------------------------------------------------------------------

def cds_get_order_list(
        args_list: list[dict[str, Any]],
        maxparallel: int | None = None,
        ignore_cache: bool = False,
) -> list[str]:
    """
    Execute a list of CDS orders and return the paths of all processed
    output files.

    When *maxparallel* resolves to 1 (or 0), orders are processed
    sequentially via a plain ``for`` loop.  When it resolves to more than
    1, a :py:class:`multiprocessing.Pool` of that size is used so that
    multiple server jobs are in flight simultaneously — useful because
    the bottleneck is server-side queue time, not local CPU.

    Each individual order is handled by :py:func:`cds_getorder`, which
    implements on-disk and order-list caching so that interrupted runs
    can be resumed without re-submitting already-queued jobs.

    :param args_list: list of order description dicts, each accepted by
      :py:func:`cds_getorder` (required keys: ``dataset``, ``request``,
      ``target``; optional key: ``subset``).
    :type args_list: list[dict[str, Any]]

    :param maxparallel: maximum number of concurrent server requests.
      ``None`` or ``0`` falls back to :py:const:`API_LIMIT_PARALLEL`.
      ``1`` forces sequential execution.
    :type maxparallel: int | None

    :param ignore_cache: passed through to :py:func:`cds_getorder`; if
      ``True``, all on-disk and order-list caches are ignored and every
      order is re-submitted from scratch.
    :type ignore_cache: bool

    :returns: list of processed output file paths, in submission order.
    :rtype: list[str]
    """

    if maxparallel is None or maxparallel == 0:
        maxparallel = API_LIMIT_PARALLEL

    downloaded: list[str] = []
    if maxparallel > 1:
        logger.debug(f"running parallel {maxparallel} parallel jobs")
        with mp.Pool(maxparallel) as pool:
            for f,args in zip(pool.map(cds_getorder, args_list),
                              args_list):
                downloaded.append(f)
    else:
        logger.debug(f"running jobs sequentially")
        for args in args_list:
            downloaded.append(cds_getorder(args))
    return downloaded

# -------------------------------------------------------------------------

def cds_get_era5_year(year: int,
                      chunks: int | bool | None = None,
                      maxparallel: int | None = None,
                      area: list | None = None,
                      subset: list | None = None,
                      ignore_cache: bool = False):
    """
    Download ERA5 reanalysis data for one calendar year and save the
    result as a single netCDF file.

    The function submits requests to the Copernicus Climate Data Store
    (CDS) API for a fixed set of meteorological variables (see source for
    the full list) at hourly resolution.  Requests are split into
    *chunks* (typically one per month) and processed by
    :py:func:`cds_get_order_list`, which supports parallelism and
    transparent resumption of interrupted downloads.

    The final output filename follows the pattern
    ``era5_ak_eu_<YYYY>.nc`` and is written to the current working
    directory.  If the file already exists and *ignore_cache* is
    ``False``, the function returns immediately.

    :param year: calendar year to download (e.g. ``2020``).
    :type year: int

    :param chunks: controls how the year is split into individual CDS
      requests:

      * ``True`` or ``12`` – one request per month (12 total).
      * ``False`` or ``1`` – the entire year in one request (may exceed
        current CDS per-request size limits).
      * ``2``, ``3``, ``4``, or ``6`` – the year split into that many
        equal multi-month requests.
      * ``None`` – use the module default :py:const:`ECMWF_CHUNKS`.
    :type chunks: int | bool | None

    :param maxparallel: maximum number of concurrent CDS requests.
      ``None`` uses the default :py:const:`API_LIMIT_PARALLEL`.
    :type maxparallel: int | None

    :param area: geographic bounding box passed to the CDS API as
      ``[North, West, South, East]`` (i.e. ``[latmax, lonmin, latmin,
      lonmax]``).  ``None`` falls back to :py:const:`WEA_WINDOW`.
    :type area: list[float] | None

    :param subset: not used for ERA5; accepted only for a consistent
      call signature with :py:func:`cds_get_cerra_year`.  Passing a
      non-``None`` value logs an error and is otherwise ignored.
    :type subset: list | None

    :param ignore_cache: if ``True``, re-download even if the output
      file or intermediate chunk files already exist on disk.
    :type ignore_cache: bool

    :returns: path of the assembled yearly netCDF file.
    :rtype: str

    :raises ValueError: if *chunks* is not ``True``, ``False``, or a
      divisor of 12.
    :raises RuntimeError: if no files were downloaded.

    :example:

        >>> cds_get_era5_year(2020)

    .. note::
      The ``ecmwf-datastores`` package must be installed and a valid CDS
      API key must be configured (see the
      `CDS API how-to <https://cds.climate.copernicus.eu/how-to-api>`_).
    """
    if subset is not None:
        logger.error("option 'subset' given with a value that is "
                     "not equal to the only allowed value: 'None'")
    if area is not None:
        latmin, latmax, lonmin, lonmax = area
    else:
        latmin, latmax, lonmin, lonmax = WEA_WINDOW

    # get in chunks ?
    # (do not use module attribute directly, may have changed after import)
    if chunks is None:
        chunks = ECMWF_CHUNKS

    ncname = 'era5_ak_eu_{:04d}.nc'.format(int(year))

    # Early exit: final file already assembled
    if os.path.exists(ncname) and not ignore_cache:
        logger.info(f"Final file {ncname!r} already exists – nothing to do.")
        return ncname

    order_dataset = 'reanalysis-era5-single-levels'
    order_template = {
        'product_type': ['reanalysis'],
        'variable': [
            '10m_u_component_of_wind',
            '10m_v_component_of_wind',
            '2m_dewpoint_temperature',
            '2m_temperature',
            'surface_pressure',
            'total_precipitation',
            'forecast_surface_roughness',
            'friction_velocity',
            'surface_latent_heat_flux',
            'surface_sensible_heat_flux',
            'low_cloud_cover',
            'total_cloud_cover',
            'cloud_base_height',
        ],
        'year': ['null'],
        'month': ['null'],
        'day': ['null'],
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
        'data_format': 'netcdf',
        'download_format': 'unarchived',
        'area': [
            int(x) if x.is_integer() else x
            for x in [latmax, lonmin, latmin, lonmax]
        ],
    }
    args_list = []
    if chunks == True:
        chunk_count = 12
    elif chunks == False:
        chunk_count = 1
    elif 12 % chunks == 0:
        chunk_count = int(chunks)
    else:
        raise ValueError("chunks is neither divisor of 12, True or False")

    if chunk_count == 12:
        chunks_months = [['{:02d}'.format(x + 1)]  for x in range(12)]
        l_mon = [calendar.monthrange(year, x + 1)[1] for x in range(12)]
    else:
        chunks_months = [['{:02d}'.format(x + y + 1)
                          for y in range(int(12 / chunk_count))]
                         for x in range(0, 12, int(12 / chunk_count))]
        l_mon = [31] * len(chunks_months)

    for chunk in range(chunk_count):
        args = {
            'dataset': order_dataset,
            'request': deepcopy(order_template)   # deepcopy: mutable lists inside
        }
        args['request']['year'] = ['{:04d}'.format(year)]
        args['request']['month'] = chunks_months[chunk]
        args['request']['day'] = [
            '{:02d}'.format(x + 1) for x in range(l_mon[chunk])
        ]
        args['target'] = 'era5_ak_eu_{:04d}-{:02d}.nc'.format(
            int(year), chunk + 1)

        args_list.append(deepcopy(args))

    # execute orders
    logger.info(f"starting getting year {year}")
    downloaded = cds_get_order_list(args_list, maxparallel=maxparallel,
                                    ignore_cache=ignore_cache)
    logger.debug(f"downloaded files: {downloaded}")
    chunk_files = downloaded

    if len(downloaded) == 0:
        raise RuntimeError(f"nothing was downloaded (!?)")

    logger.info("assembling year")
    if len(chunk_files) > 1:
        _netcdf.merge_time(chunk_files, ncname, timevar='time',
                           compression=_storage.COMPRESS_NETCDF)
    else:
        shutil.move(chunk_files[0], ncname)

    logger.info(f"done getting year {year}")

    return ncname

# -------------------------------------------------------------------------

def cds_get_cerra_year(
        year: int,
        chunks: int | bool | None = None,
        maxparallel: int | None = None,
        area: list | None = None,
        subset: list | None = None,
        ignore_cache: bool = False,
) -> str:
    """
    Download CERRA (Copernicus European Regional ReAnalysis) data for one
    calendar year and save the result as a single netCDF file.

    CERRA is a forecast product with three lead times (1 h, 2 h, 3 h)
    for each analysis time step.  For every chunk × lead-time combination
    a separate CDS request is submitted, giving
    ``chunk_count × 3`` requests in total.  After all requests have
    completed, the lead-time files within each chunk are merged along the
    time axis, and the chunk files are then merged into the final yearly
    file.

    The function supports transparent resumption of interrupted runs:

    * If the final output file ``cerra_ak_eu_<YYYY>.nc`` already exists
      and *ignore_cache* is ``False``, the function returns immediately.
    * Intermediate chunk files that already exist are reused without
      re-downloading or re-merging.
    * Already-submitted server jobs are tracked via the order-list file
      (see :py:const:`ORDERFILE`) and are re-attached rather than
      re-submitted.

    :param year: calendar year to download (e.g. ``2020``).
    :type year: int

    :param chunks: controls how the year is split into individual CDS
      requests:

      * ``True`` or ``12`` – one request per month (12 × 3 = 36 requests
        total).
      * ``False`` or ``1`` – the entire year in one request per lead time
        (3 requests total; may exceed CDS per-request size limits).
      * ``2``, ``3``, ``4``, or ``6`` – the year split into that many
        equal multi-month groups.
      * ``None`` – use the module default :py:const:`ECMWF_CHUNKS`.
    :type chunks: int | bool | None

    :param maxparallel: maximum number of concurrent CDS requests.
      ``None`` uses the default :py:const:`API_LIMIT_PARALLEL`.
    :type maxparallel: int | None

    :param area: not used for CERRA (the dataset uses a fixed rotated
      grid); accepted only for a consistent call signature with
      :py:func:`cds_get_era5_year`.  Passing a non-``None`` value logs
      an error and is otherwise ignored.
    :type area: list | None

    :param subset: spatial subset expressed as grid-cell indices
      ``[xmin, xmax, ymin, ymax]``.  ``None`` defaults to the index
      range covering Germany (xmin=489, xmax=649, ymin=479, ymax=659).
    :type subset: list[int] | None

    :param ignore_cache: if ``True``, re-download even if the output
      file or intermediate chunk files already exist on disk.
    :type ignore_cache: bool

    :returns: path of the assembled yearly netCDF file
      (``cerra_ak_eu_<YYYY>.nc`` in the current working directory).
    :rtype: str

    :raises ValueError: if *chunks* is not ``True``, ``False``, or a
      divisor of 12.
    :raises RuntimeError: if no files were downloaded, or if no source
      files are found for a given chunk during the merge step.

    :example:

        >>> cds_get_cerra_year(2023)

    .. note::
      The ``ecmwf-datastores`` package must be installed and a valid CDS
      API key must be configured (see the
      `CDS API how-to <https://cds.climate.copernicus.eu/how-to-api>`_).
    """
    import calendar

    if area is not None:
        logger.error(
            "option 'area' given with a value that is "
            "not equal to the only allowed value: 'None'"
        )

    # Spatial subset (index-based)
    if subset is not None:
        xmin, xmax, ymin, ymax = subset
    else:
        # default: Germany
        xmin, xmax, ymin, ymax = 489, 649, 479, 659

    # get in chunks ?
    # (do not use module attribute directly, may have changed after import)
    if chunks is None:
        chunks = ECMWF_CHUNKS

    ncname = f"cerra_ak_eu_{int(year):04d}.nc"

    # Already fully assembled?
    if os.path.exists(ncname) and not ignore_cache:
        logger.info(
            f"Final file {ncname!r} already exists – nothing to do.")
        return ncname

    # Build request list
    order_dataset = "reanalysis-cerra-single-levels"
    order_template: dict[str, Any] = {
        "variable": [
            "10m_wind_direction",
            "10m_wind_speed",
            "2m_relative_humidity",
            "2m_temperature",
            "low_cloud_cover",
            "medium_cloud_cover",
            "momentum_flux_at_the_surface_u_component",
            "momentum_flux_at_the_surface_v_component",
            "surface_latent_heat_flux",
            "surface_pressure",
            "surface_roughness",
            "surface_sensible_heat_flux",
            "total_cloud_cover",
            "total_precipitation",
        ],
        "level_type": "surface_or_atmosphere",
        "data_type": ["reanalysis"],
        "product_type": "forecast",
        "year": ["null"],
        "month": ["null"],
        "day": ["null"],
        "time": [
            "00:00", "03:00", "06:00",
            "09:00", "12:00", "15:00",
            "18:00", "21:00",
        ],
        "leadtime_hour": ["null"],
        "data_format": "netcdf",
    }

    # Determine chunk layout
    if chunks is True:
        chunk_count = 12
    elif chunks is False:
        chunk_count = 1
    elif 12 % int(chunks) == 0:
        chunk_count = int(chunks)
    else:
        raise ValueError(
            "chunks must be a divisor of 12, or True / False"
        )

    if chunk_count == 12:
        chunks_months = [[f"{m + 1:02d}"] for m in range(12)]
        l_mon = [calendar.monthrange(year, m + 1)[1]
                 for m in range(12)]
    else:
        step = 12 // chunk_count
        chunks_months = [
            [f"{m + 1:02d}" for m in range(start, start + step)]
            for start in range(0, 12, step)
        ]
        l_mon = [31] * chunk_count

    args_list: list[dict[str, Any]] = []
    for chunk in range(chunk_count):
        base_request = deepcopy(order_template)
        base_request["year"] = [f"{int(year):04d}"]
        base_request["month"] = chunks_months[chunk]
        base_request["day"] = [f"{d + 1:02d}" for d in range(l_mon[chunk])]

        for lead_time in range(1, 4):
            req = deepcopy(base_request)
            req["leadtime_hour"] = [str(lead_time)]
            target = (
                f"cerra_ak_eu_{int(year):04d}-{chunk + 1:02d}+{lead_time:02d}.nc"
            )
            args_list.append({
                "dataset": order_dataset,
                "request": req,
                "target": target,
                "subset": {
                    "xmin": xmin, "xmax": xmax,
                    "ymin": ymin, "ymax": ymax,
                    "by_index": True,
                },
            })

    # Execute (resumable)                                                  #
    logger.info(f"Start getting year {year}.")
    downloaded = cds_get_order_list(
        args_list,
        maxparallel=maxparallel,
        ignore_cache=ignore_cache,
    )
    logger.debug(f"Downloaded files: {downloaded}")

    if len(downloaded) == 0:
        raise RuntimeError("Nothing was downloaded.")

    # Merge lead-time files within each chunk
    logger.info("Sorting forecast lead times")
    chunk_files: list[str] = []
    for chunk in _tools.progress(range(chunk_count), "sorting time"):
        stem = f"cerra_ak_eu_{int(year):04d}-{chunk + 1:02d}"
        merge_to = stem + ".nc"

        if os.path.exists(merge_to) and not ignore_cache:
            logger.info(
                f"Chunk file {merge_to!r} already exists – skipping merge.")
            chunk_files.append(merge_to)
            continue

        sources = sorted(glob.glob(stem + "*.nc"))
        if not sources:
            raise RuntimeError(
                f"No source files found for chunk {chunk + 1} "
                f"(pattern: {stem}*.nc)"
            )
        logger.info(f"Merging {sources} → {merge_to!r}")
        if _netcdf is not None:
            _netcdf.merge_time(sources, merge_to, timevar="time",
                               compression=_storage.COMPRESS_NETCDF)
        else:
            raise ImportError("_netcdf module required for merge_time()")
        chunk_files.append(merge_to)

    # Assemble the full year
    logger.info("Assembling year")
    if len(chunk_files) > 1:
        if _netcdf is not None:
            _netcdf.merge_time(chunk_files, ncname, timevar="time",
                               compression=_storage.COMPRESS_NETCDF)
        else:
            raise ImportError("_netcdf module required for merge_time()")
    else:
        shutil.move(chunk_files[0], ncname)

    logger.info(f"Done getting year {year}.")
    return ncname
