#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import calendar
import glob
import json
import logging
import os
import shutil
import tempfile
import time
import zipfile
from copy import deepcopy
from typing import Any

# Sentinel defaults so names are always bound (Sphinx builds, missing libs)
_USE_DATASTORES: bool = False
def DSClient():
    return None           # type: ignore[assignment]
_cdsapi_legacy = None     # type: ignore[assignment]

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import multiprocessing as mp
    try:
        from ecmwf.datastores import Client as DSClient  # type: ignore[assignment]
        _USE_DATASTORES = True
    except ImportError:
        try:
            import cdsapi as _cdsapi_legacy  # type: ignore[assignment]
        except ImportError:
            pass  # both remain None / False

from . import _storage
from . import _netcdf
from . import _tools

logger = logging.getLogger(__name__)

WEA_WINDOW = (33, 71, -12, 36)
""" standard lat/lon window for worldwide weather datasets 
    latmin, latmax, lonmin, lonmax """
API_LIMIT_PARALLEL = 2
""" Copernicus per-user limit for parallel queries """
CDSAPI_CHUNKS = True
""" Copernicus per-request limit does not permit download of 
    yearly files and requires splitting up donwloads. 
    For possible values see 
    :py:func:`austaltools._dataset.cds_get_cerra_year` """
CACHE_FILE: str = "cds_job_cache.json"
""" written next to the nc files """


# -------------------------------------------------------------------------

def cds_merge_zipped(source, destination,
                     compression= _storage.COMPRESS_NETCDF):
    """
    Merge the files in a zipped archive downloaded from
    cds.climate.eu into one nc file.

    :param source: path of the archive file to read
    :type source: str

    :param destination: path of the destination file to create
    :type destination: str

    :param compression: (optional) compression type,
      defaults to :py:const:`_storage.COMPRESS_NETCDF`
    :type compression: str | None
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
    Replaces the variable ``valid_time`` in ECMWF products
    (measured in seconds since 1970-01-01) by the more widely
    used variable ``time`` (measured in hours since 1900-01-01).

    :param compression: compression method for netCDF files produced.
      Ususally 'zlib'. Default to :py:const:`COMPRESS_NETCDF`.
    :type compression: str | None

    :return: `replace` and `convert` for use with
      function from the _netcdf module.
    :rtype: dict, dict
    """

    # replace time variable
    stime_name = 'valid_time'
    stime_unit = 'seconds since 1970-01-01'
    dtime_name = 'time'
    dtime_unit = 'hours since 1900-01-01'

    dtime_var = _netcdf.VariableSkeleton(
        dtime_name, 'd',
        dimensions=(dtime_name),
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

def _load_cache(cache_path: str) -> dict[str, dict]:
    """Return the job cache as ``{target_filename: job_info_dict}``."""
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                f"Could not read job cache {cache_path!r}: {exc}")
    return {}

# -------------------------------------------------------------------------

def _save_cache(cache_path: str, cache: dict[str, dict]) -> None:
    """Atomically write the job cache."""
    tmp = cache_path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, indent=2)
        os.replace(tmp, cache_path)
    except OSError as exc:
        logger.error(f"Could not write job cache {cache_path!r}: {exc}")

# -------------------------------------------------------------------------

def _cache_set(cache_path: str, target: str, info: dict) -> None:
    """Upsert one entry and persist the cache immediately."""
    cache = _load_cache(cache_path)
    cache[target] = info
    _save_cache(cache_path, cache)

# -------------------------------------------------------------------------

def _cache_get(cache_path: str, target: str) -> dict | None:
    return _load_cache(cache_path).get(target)

# -------------------------------------------------------------------------

def _cache_del(cache_path: str, target: str) -> None:
    cache = _load_cache(cache_path)
    cache.pop(target, None)
    _save_cache(cache_path, cache)

# -------------------------------------------------------------------------

def cleanup_cds_cache(cache_path: str = CACHE_FILE,
                      remove_partial_files: bool = False) -> None:
    """
    Delete the job-cache file and optionally remove every partial/incomplete
    target file listed in it.

    Call this when you want to start a year download completely from scratch
    regardless of any previous state.

    :param cache_path: path to the JSON cache file.
    :param remove_partial_files: if True, also unlink every target file that
        was registered as *not yet completed* in the cache.
    """
    if not os.path.exists(cache_path):
        logger.info(
            f"No cache file found at {cache_path!r} – nothing to do.")
        return

    if remove_partial_files:
        cache = _load_cache(cache_path)
        for target, info in cache.items():
            if not info.get("completed", False) and os.path.exists(target):
                logger.info(f"Removing partial file {target!r}")
                try:
                    os.unlink(target)
                except OSError as exc:
                    logger.warning(f"Could not remove {target!r}: {exc}")

    os.unlink(cache_path)
    logger.info(f"Cache file {cache_path!r} removed.")

# -------------------------------------------------------------------------

def cds_getorder(order_args: dict[str, Any],
                 cache_path: str = CACHE_FILE,
                 ignore_cache: bool = False) -> str:
    """
    Submit *one* CDS order and return the target filename.

    Unlike the original version this function:

    * Checks whether *target* already exists on disk → skips.
    * Checks the job cache for a previously obtained ``request_id`` so it
      can re-attach to an in-progress server job after a reboot rather than
      re-submitting.
    * Persists the ``request_id`` to the cache immediately after submission
      so a crash between submission and completion doesn't lose the job.

    Requires ``ecmwf-datastores-client`` (``pip install ecmwf-datastores-client``).
    Falls back to the legacy ``cdsapi`` if the new client is not installed,
    but **without** resumability (the legacy client's retrieve() is
    monolithic and does not expose a request_id).

    :param order_args: same dict accepted by the original ``cds_getorder``
        (keys: ``dataset``, ``request``, ``target``; optionally ``subset``).
    :param cache_path: path to the JSON cache file.
    :param ignore_cache: if True, ignore any cached job info and re-submit.
    :returns: target filename (the file is guaranteed to exist on return).
    :raises RuntimeError: if the client libraries are unavailable.
    """
    dataset = order_args["dataset"]
    request = order_args["request"]
    target = order_args["target"]

    # 1. Target already on disk?
    if os.path.exists(target) and not ignore_cache:
        logger.info(
            f"Target {target!r} already exists – skipping download.")
        return target

    # 2a. New datastores client path (preferred)
    if _USE_DATASTORES:
        return _cds_getorder_datastores(
            dataset, request, target, cache_path, ignore_cache
        )

    # 2b. Legacy cdsapi fallback – no resumability                          #
    if _cdsapi_legacy is None:
        raise RuntimeError(
            "Neither 'ecmwf-datastores-client' nor 'cdsapi' is installed."
        )
    logger.warning(
        "ecmwf-datastores-client not found; falling back to legacy cdsapi "
        "(no resume support – install ecmwf-datastores-client for resilience)."
    )
    quiet = logger.getEffectiveLevel() > logging.INFO
    debug = logger.getEffectiveLevel() <= logging.DEBUG
    cdsapi = _cdsapi_legacy.Client(quiet=quiet, debug=debug)
    cdsapi.retrieve(dataset, request, target)

    return target

# -------------------------------------------------------------------------

def _cds_getorder_datastores(
        dataset: str,
        request: dict[str, Any],
        target: str,
        cache_path: str,
        ignore_cache: bool,
) -> str:
    """
    Inner implementation using ``ecmwf.datastores.Client``.

    Three stages, each independently resumable:
      1 submit (or re-attach to existing job)
      2 wait for server-side completion
      3 download
    """

    client = DSClient()

    # stage 1: submit or re-attach ----------------------------------
    cached = None if ignore_cache else _cache_get(cache_path, target)
    job = None

    if cached and cached.get("request_id"):
        request_id = cached["request_id"]
        logger.info(
            f"Re-attaching to existing CDS job {request_id!r} "
            f"for target {target!r}"
        )
        try:
            job = client.get_remote(request_id)
        except Exception as exc:
            logger.info(
                f"Could not re-attach to job {request_id!r}: {exc}. "
                "Re-submitting."
            )
            job = None

    if job is None:
        logger.info(f"Submitting new CDS order for {target!r}")
        job = client.submit(dataset, request)
        _cache_set(cache_path, target, {
            "request_id": job.request_id,
            "dataset": dataset,
            "target": target,
            "status": "submitted",
            "completed": False,
        })
        logger.info(
            f"Job submitted: request_id={job.request_id!r}  "
            f"target={target!r}"
        )

    # stage 2: wait for results --------------------------------------
    poll_interval = 60  # seconds; the library itself also backs off
    while not job.results_ready:
        status = job.status
        logger.info(
            f"[{target}] Job {job.request_id!r} status={status!r} – "
            "waiting …"
        )
        _cache_set(cache_path, target, {
            "request_id": job.request_id,
            "dataset": dataset,
            "target": target,
            "status": status,
            "completed": False,
        })
        time.sleep(poll_interval)
        # refresh the remote object so status is re-queried
        job = client.get_remote(job.request_id)

    # stage 3: download -----------------------------------------------
    logger.info(
        f"[{target}] Job {job.request_id!r} complete – downloading …"
    )
    _cache_set(cache_path, target, {
        "request_id": job.request_id,
        "dataset": dataset,
        "target": target,
        "status": "downloading",
        "completed": False,
    })
    job.download(target)

    # post-processing: unzip if needed, subset, fix time variable
    # Reconstruct order_args from the individual parameters this function
    # received, adding subset from the cache if it was stored there.
    order_args = {
        "dataset": dataset,
        "request": request,
        "target":  target,
        "subset":  (_cache_get(cache_path, target) or {}).get("subset"),
    }
    cds_processorder(order_args)

    _cache_set(cache_path, target, {
        "request_id": job.request_id,
        "dataset": dataset,
        "target": target,
        "status": "completed",
        "completed": True,
    })
    logger.info(f"[{target}] Download complete.")
    return target

# -------------------------------------------------------------------------

def order_args_subset_from_cache(cache_path: str,
                                 target: str) -> dict | None:
    """Return subset info stored alongside the job, or None.

    .. note::
        Not used in the main download path (subsetting is handled by
        :func:`cds_processorder`).  Kept for external callers that inspect
        the cache directly.
    """
    cached = _cache_get(cache_path, target)
    if cached:
        return cached.get("subset")
    return None

# -------------------------------------------------------------------------

def _apply_subset(target: str, subset: dict) -> None:
    """
    Apply spatial subsetting to a NetCDF file in-place using xarray.
    ``subset`` is expected to have keys ``xmin``, ``xmax``, ``ymin``,
    ``ymax``, ``by_index``.

    .. note::
        In the normal download flow subsetting is handled by
        :func:`cds_processorder` (via :func:`_netcdf.subset_xy`).
        This function is kept as a fallback for callers that cannot use
        ``cds_processorder`` (e.g. files not in the standard order-args
        format).
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

def cds_processorder(order_args: dict[str, str | dict],
                     compression: str | None = _storage.COMPRESS_NETCDF) -> str:
    """
    Preprocess a file downloaded by
    :py:func:`austaltools:_datasets.cds_getorder`
    by converting a dowanload file that is a zip archive containing
    netCDF files (new since 2024) into one plain netCDF file and / or by
    optionally subestting the data.

    :param order_args: order data dictionary
    :type order_args: dict
        must contain the keys:
        - ``target``: Name of the file to produce

       optionally may contain:
        - ``subset``: a dictionary containing arguments to
          :py: func:`austaltools._netcdf.subset_xy`,
          except `rsc` and `dst`.
          If the keyword is not contained in `order_args`,
          no subestting is applied.

    :returns: filename of the produced file
    :rtype: str

    """
    target = order_args.get('target',None)
    if target is None:
        raise ValueError("target key must be specified in oder_args")
    if zipfile.is_zipfile(target):
        zipname = target + '.zip'
        shutil.move(target, zipname)
        cds_merge_zipped(zipname, target)
        os.remove(zipname)

    if order_args.get('subset', None) is not None:
        fullname = 'full_' + target
        shutil.move(target, fullname)
        _netcdf.subset_xy(fullname, target, **order_args['subset'],
                          compression=compression)
        os.remove(fullname)

    fullname = 'oldtime_' + target
    shutil.move(target, fullname)
    replace, convert = cds_replace_valid_time(compression)
    _netcdf.merge_variables([fullname], target,
                            replace=replace, convert=convert,
                            compression=compression,
                            remove_source=True)

    return target

# -------------------------------------------------------------------------

def cds_get_order_list(
        args_list: list[dict[str, Any]],
        maxparallel: int | None = None,
        cache_path: str = CACHE_FILE,
        ignore_cache: bool = False,
) -> list[str]:
    """
    Execute a list of CDS orders sequentially, skipping any that are already
    present on disk or can be resumed from the job cache.

    The original parallel multiprocessing approach is replaced here with a
    sequential loop because the bottleneck is always the server (hours of
    queue + retrieval), not local CPU.  Submitting all jobs first and then
    polling in round-robin is the correct strategy – see the implementation
    below.

    :param args_list: list of order dicts (keys: ``dataset``, ``request``,
        ``target``; optionally ``subset``).
    :param maxparallel: kept for API compatibility; not used.
    :param cache_path: path to the JSON cache file.
    :param ignore_cache: if True, ignore cached job info (re-submit all).
    :returns: list of completed target filenames.
    """

    # cdsapi fallback ----------------------------------------------------
    #
    if not _USE_DATASTORES:
        # Legacy path – sequential, no resume
        downloaded: list[str] = []
        with mp.Pool(maxparallel) as pool:
            for f,args in zip(pool.map(cds_getorder, args_list),
                              args_list):
                print(f"downloading file {args['target']}", flush=True)
                downloaded.append(f)
        return downloaded

    # New datastores implementation ---------------------------------------
    # submit all first, then poll + download
    #
    client = DSClient()
    jobs: list[tuple[dict, Any]] = []  # (args, remote_or_None)

    # 1: submit all (or re-attach from cache) -----------------------------
    for args in args_list:
        target = args["target"]

        # Already on disk?
        if os.path.exists(target) and not ignore_cache:
            logger.info(f"Skipping {target!r} – already on disk.")
            jobs.append((args, "done"))
            continue

        cached = None if ignore_cache else _cache_get(cache_path, target)
        remote = None
        if cached and cached.get("request_id"):
            try:
                remote = client.get_remote(cached["request_id"])
                logger.info(
                    f"Re-attached to job {cached['request_id']!r} "
                    f"for {target!r} (status={remote.status})"
                )
            except Exception as exc:
                logger.warning(
                    f"Re-attach failed for {target!r}: {exc}. Re-submitting."
                )
                remote = None

        if remote is None:
            logger.info(f"Submitting {target!r}")
            remote = client.submit(args["dataset"], args["request"])
            _cache_set(cache_path, target, {
                "request_id": remote.request_id,
                "dataset": args["dataset"],
                "target": target,
                "status": "submitted",
                "completed": False,
                "subset": args.get("subset"),
            })
            logger.info(
                f"  → request_id={remote.request_id!r}  target={target!r}"
            )

        jobs.append((args, remote))

    # 2: poll in a loop until all complete -------------------------------
    poll_interval = 120  # seconds between full sweeps
    pending = [(a, r) for a, r in jobs if r != "done"]
    completed: list[str] = [a["target"]
                            for a, r in jobs if r == "done"]

    while pending:
        still_pending = []
        for args, remote in pending:
            target = args["target"]
            # Refresh status
            try:
                remote = client.get_remote(remote.request_id)
            except Exception as exc:
                logger.warning(
                    f"Status check failed for {target!r}: {exc}")
                still_pending.append((args, remote))
                continue

            _cache_set(cache_path, target, {
                "request_id": remote.request_id,
                "dataset": args["dataset"],
                "target": target,
                "status": remote.status,
                "completed": False,
                "subset": args.get("subset"),
            })

            if not remote.results_ready:
                logger.debug(
                    f"  {target!r}: {remote.status}"
                )
                still_pending.append((args, remote))
            else:
                # 3: download -----------------------------------------
                logger.info(f"Downloading {target!r} …")
                _cache_set(cache_path, target, {
                    "request_id": remote.request_id,
                    "dataset": args["dataset"],
                    "target": target,
                    "status": "downloading",
                    "completed": False,
                    "subset": args.get("subset"),
                })
                remote.download(target)

                # post-processing: unzip if needed, subset, fix time variable
                cds_processorder(args)

                _cache_set(cache_path, target, {
                    "request_id": remote.request_id,
                    "dataset": args["dataset"],
                    "target": target,
                    "status": "completed",
                    "completed": True,
                    "subset": args.get("subset"),
                })
                logger.info(f"  → {target!r} done.")
                completed.append(target)

        pending = still_pending
        if pending:
            logger.info(
                f"{len(pending)} job(s) still pending – "
                f"sleeping {poll_interval}s …"
            )
            time.sleep(poll_interval)

    return completed

# -------------------------------------------------------------------------

def cds_get_era5_year(year: int,
                      chunks: int | bool | None = None,
                      maxparallel: int | None = None,
                      area: list | None = None,
                      subset: list | None = None,
                      cache_path: str = CACHE_FILE,
                      ignore_cache: bool = False):
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

    :param year: The year for which to download the data (integer).
    :type year: int

    :param chunks: Whether to retrieve monthly chunks or yearly files.
      If True or 12, monthly chunks are downloaded.
      If False or 1, the year is downloaded in one piece
      (which exceeds current limits as of Apr 2025)
      If 2, 3, 4, or 6, multi-monthly chunks are downloaded
      (which can be faster, depending on the queue length)
    :type chunks: int | bool

    :param maxparallel: number of parallel queries that are
      submitted to the CDS API. Or `None` for the default value.
    :type maxparallel: int | None

    :param area: Area to extract from the CDS database
      as a list of "North, West, South, East"
      (Minimum latitude, maximum latitude,
      minimum longitude, maximum longitude)
      or `None` for the default value.
    :type area: list[float, float, float, float] | None

    :param subset: Accepted for consistency with other
      ``cds_get_...`` functions.
    :type subset: None

    :param cache_path: path to the JSON job-cache file.
      Default: ``cds_job_cache.json`` in the current directory.
    :type cache_path: str

    :param ignore_cache: if True, ignore all cached job information and
      restart the year download from scratch. Existing output files
      are also re-downloaded if this flag is set.
    :type ignore_cache: bool

    :returns: filename of the assembled NetCDF file.
    :rtype: str

    :example:
        >>> # To download ERA5 data for the year 2020 and
        >>> # save it to the specified directory
        >>> cds_get_era5_year(2020)

    :note:
      - The function crafts a filename based on the year, prefixing it
        with `era5_ak_eu_` to denote the region and type of data retrieved.
        Ensure that the specified directory exists and is writable.
      - Either ``ecmwf-datastores-client`` or ``cdsapi`` must be installed
        and a **valid CDS API key** must be configured.
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
        chunks = CDSAPI_CHUNKS

    ncname = 'era5_ak_eu_{:04d}.nc'.format(int(year))

    # Early exit: final file already assembled
    if os.path.exists(ncname) and not ignore_cache:
        logger.info(f"Final file {ncname!r} already exists – nothing to do.")
        return ncname

    if not _USE_DATASTORES and _cdsapi_legacy is None:
        raise RuntimeError(
            "Neither 'ecmwf-datastores-client' nor 'cdsapi' is installed.")

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
    logger.info("starting download process")
    downloaded = cds_get_order_list(args_list, maxparallel=maxparallel,
                                    cache_path=cache_path,
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
        cache_path: str = CACHE_FILE,
        ignore_cache: bool = False,
) -> str:
    """
    Download and process a year's worth of CERRA data, resuming
    automatically if a previous run was interrupted.

    See the original docstring for full parameter documentation.  New
    parameters:

    :param cache_path: path to the JSON job-cache file.
        Default: ``cds_job_cache.json`` in the current directory.
    :param ignore_cache: if True, ignore all cached job information and
        restart the year download from scratch.  Existing output files
        are also re-downloaded if this flag is set.

    Resume behaviour
    ----------------
    On startup the function reads ``cache_path`` (if it exists) and for
    every chunk+leadtime combination determines the minimum work still
    needed:

    * Target ``.nc`` already on disk → skip.
    * A ``request_id`` is in the cache → re-attach to the server job;
      if the server already finished → download only; if still running →
      wait and then download.
    * No cache entry → submit fresh.

    The year-level output file ``cerra_ak_eu_<year>.nc`` is only
    assembled once *all* chunk files are present.

    Use :func:`cleanup_cds_cache` to wipe the cache and start over::

        cleanup_cds_cache("cds_job_cache.json", remove_partial_files=True)
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
        chunks = CDSAPI_CHUNKS

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
    logger.info("Starting download process")
    downloaded = cds_get_order_list(
        args_list,
        maxparallel=maxparallel,
        cache_path=cache_path,
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
