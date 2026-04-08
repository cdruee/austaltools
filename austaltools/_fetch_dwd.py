#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Feb  3 19:20:42 2022

@author: clemens
"""
import datetime
import io
import logging
import os
import re
import shutil
import zipfile
from typing import Any

import numpy as np
import pandas as pd
import requests

from . import _tools
from . import _storage
from . import _geo

logger = logging.getLogger(__name__)

_PATH = "."
"""operate in current working dir by default"""
OLDEST = pd.to_datetime('1970-01-01', utc=True)
""" remove observations before ...
to avoid problems with odd observation timing in the very manual era) """
OBSFILE_DWD = 'observations_hourly_%05i.csv'
"""filename pattern for cached DWD observations"""
METAFILE_DWD = 'metadata_%05i.csv'
"""filename pattern for cached DWD metadata"""

#
TO_COLLECT = [
    ['air_temperature', 'TU', 'tu'],
    # ['cloudiness', 'N', 'n'],  # included in CS
    ['cloud_type', 'CS', 'cs'],
    # ['extreme_wind', 'FX', 'fx'],  # not needed
    ['precipitation', 'RR', 'rr'],
    ['pressure', 'P0', 'p0'],
    ['soil_temperature', 'EB', 'eb'],
    ['visibility', 'VV', 'vv'],
    ['wind', 'FF', 'ff'],
    ['wind_synop', 'F', 'f']
]
"""parameter groups to collect from opendata file tree"""

# =========================================================================

class DWDStationinfo():
    """
    Class that holds information about a weather stations from a dataset.

     This function retrieves metadata about a specific weather station from
     a dataset that is either provided or located in a default location. The
     dataset is expected to be a JSON file containing information about multiple
     weather stations, including their geographical coordinates, elevation, and
     names.

     :param stationfile: The path to the JSON file containing
        station information. If `None`, a default path is used.
        Defaults to `None`.
     :type stationfile: str | None

     This class can be used as a context manager.

     Example::

        with DWDStationinfo() as si:
            lat, lon, ele = si.position(1234)
    """
    data = pd.DataFrame()

    # -------------------------------------

    def __init__(self, stationfile=None):
        if stationfile is None:
            stationfile = os.path.join(_storage.DIST_AUX_FILES,
                                       'dwd_stationlist.json')

        logging.info('dwd station data from; %s' % stationfile)
        with open(stationfile, mode='r') as f:
            self.data = pd.read_json(f, orient='index', convert_dates=True)

    # -------------------------------------

    def __enter__(self):
        return self

    # -------------------------------------

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False  # don't suppress exceptions

    # -------------------------------------

    def _ensure_valid(self, station: Any, silent: bool = False) -> bool:
        """
        Make sure station with that number exists
        :param station: station number candicate
        :type station: int
        :param silent: (optional)
          If the function should silently return `False`
          or raise an error if `station` is invalid.
        :type silent: bool
        :return: True if station exists, False otherwise
        :rtype: bool
        """
        msg = None
        if station is None or not isinstance(station, int):
            msg = f"no station number: {str(station)}"
        if station not in self.data.index:
            msg = f"station not in stationinfo file: {station}"
        if msg:
            if silent:
                return False
            else:
                raise ValueError(msg)
        return True

    # -------------------------------------

    def position(self, station: int) -> tuple[float, float, float]:
        """
        Retrieves the position of a specific weather station 
        identified by the station number
        
        Returns latitude, longitude, elevation, and name
        :param station: 
        :type station: 
        :return: lat, lon, ele
        :rtype: (float, float, float)
        """
        self._ensure_valid(station)
        lat = self.data['latitude'][station]
        lon = self.data['longitude'][station]
        ele = self.data['elevation'][station]
        return lat, lon, ele

    # -------------------------------------

    def name(self, station: int) -> str:
        """
        Retrieves the name of a specific weather station
        identified by the station number
        :param station:
        :type station:
        :return: name
        :rtype: str
        """
        self._ensure_valid(station)
        return self.data['name'][station]

    # -------------------------------------

    def roughness(self, station: int) -> str:
        """
        Retrieves the surface roughness $z_0$ at a specific weather station
        identified by the station number
        :param station:
        :type station:
        :return: roughness length in m
        :rtype: float
        """
        self._ensure_valid(station)
        return self.data['roughness'][station]

    # -------------------------------------

    def nearest(self, lat: float, lon: float, radius: float| None=None
                ) -> int | None:
        """
        Returns the number of the nearest station in the stationinfo file.
        
        If limit is given, a station is only returned, if one if found
        within the given radius around the position.
        
        :param lat: latitude in degrees 
        :type lat: float
        :param lon: longitude in degrees
        :type lon: float
        :param radius: Max distance toe station returned in km
        :type radius: float
        :return: station number 
          or None if no station inside the search radius
        :rtype: int | None
        """
        sdist = pd.Series(
            {k: _geo.spheric_distance(
                v['latitude'], v['longitude'], lat, lon)
             for k, v in self.data.iterrows()}
        )  # km
        candidate = sdist.idxmin()
        if radius and sdist[candidate] > radius:
            return None
        return int(candidate)  # type: ignore[arg-type]

    # -------------------------------------

# =========================================================================

def fetch_dirlist(url: str, pattern: str = '.*') -> list[str]:
    """
    get directory listing from (opendata) server

    :param url: directory URL
    :type url: str
    :param pattern: filter directory entries by this regex pattern
    :type pattern: str
    :return: fle names
    :rtype: list
    """
    with requests.get(url, allow_redirects=True) as rsp:
        text = rsp.content.decode()
        links = [x for x in re.findall(r'href="(.+?)"', text)]
        files = [x for x in links if bool(re.match(pattern, x))]
    return files


# -------------------------------------------------------------------------

def fetch_file(group: str, station: int | str,
               era: str | None = None, local_path: str = '.') -> str:
    """
    download observation file from (opendata) server

    :param group: name of parameter group, for example ``ff``
    :type group: str
    :param station: DWD station number
    :type station: (int, str)
    :param era: ``current`` or ``historical``
    :type era: str
    :param local_path: where to store the downloaded file
    :type local_path: str
    :return: name of the downloaded file
    :rtype: str
    """
    http_addr = 'https://opendata.dwd.de'
    http_path = ('climate_environment/CDC/observations_germany'
                 '/climate/hourly')
    if era not in [None, 'recent', 'historical']:
        raise ValueError(f'unknwon era: {era}')
    if not era:
        era = 'historical'

    for (name, gtl, abbr) in TO_COLLECT:
        if group == gtl:
            groupname = name
            break
    else:
        raise ValueError(f'unknown group: {group}')

    baseurl = "/".join([http_addr, http_path, groupname, era])

    if station in ['stations', 'stationen']:
        fname = "%s_Stundenwerte_Beschreibung_Stationen.txt" % group
    else:
        stnr = int(station)
        flist = fetch_dirlist(
            baseurl, r"stundenwerte_%s_%05i_.*\.zip" % (gtl, stnr))
        if len(flist) != 1:
            logger.warning(
                'filename on server not unique: %s' % str(flist))
        fname = sorted(flist)[-1]

    local_name = os.path.join(local_path, fname)
    url = "/".join((baseurl, fname))

    return _tools.download(url, local_name)


# -------------------------------------------------------------------------

def fetch_stationlist(years: list[int] | int | None = None, fullyear=True
                      ) -> dict[str, dict]:
    """
    compile the station list from (opendata) server

    :param years: list of years for wich the station should habe reported data
      must be continuous and ascending order
    :type years: list
    :param fullyear: If True, stations are olny listed, if they have reported data
      for the full period. If False, stations that have strated operation
      in the first or ceised operation in the last year are also listed.
    :return: list of stations
    :rtype: dict[dict]
    """
    logger.debug(f"fetch_stationlist: years = {years}")
    if years is not None and not isinstance(years, list):
        years = [years]
    stations = {}
    for (groupname, gtl, groupabbr) in TO_COLLECT:
        listfile = fetch_file(gtl, 'stations')
        stations[gtl] = {}
        with open(listfile, 'r', encoding="latin-1") as f:
            # skip header
            f.readline()
            f.readline()
            for line in f.readlines():
                s_id = int(line[0:5])
                stations[gtl][s_id] = {
                    "start": pd.to_datetime(line[6:14],
                                            format="%Y%m%d", utc=True),
                    "end": pd.to_datetime(line[15:23],
                                          format="%Y%m%d", utc=True),
                    "elevation": float(line[31:40]),
                    "latitude": float(line[41:50]),
                    "longitude": float(line[51:60]),
                    "name": (line[61:102]).strip()
                }
    # get all station IDs
    sids = list(set([x for k, v in stations.items() for x in v.keys()]))
    # find stations that provide all parameters
    complete_stations = dict(dict())
    for sid in sids:
        # skip stations not listed in all groups
        if not all([sid in v.keys() for k, v in stations.items()]):
            continue
        # last start date
        s_start = max([v[sid]['start'] for k, v in stations.items()])
        logger.debug({k: v[sid]['start'] for k, v in stations.items()})
        # first end date
        s_end = min([v[sid]['end'] for k, v in stations.items()])
        logger.debug({k: v[sid]['end'] for k, v in stations.items()})
        # station name
        s_nam = stations[list(stations.keys())[0]][sid]['name']
        if not all(
                [s_nam == v[sid]['name'] for k, v in stations.items()]):
            logger.warning(f'multiple name for station {sid}')

        logger.debug(f"{sid:-5d} ({s_nam:16s}): {s_start} - {s_end}")

        # check elevation
        s_ele = stations[list(stations.keys())[0]][sid]['elevation']
        if not all([s_ele == v[sid]['elevation'] for k, v in
                    stations.items()]):
            logger.warning(f'multiple elevations for station {sid}')
        # check latitude
        s_lat = stations[list(stations.keys())[0]][sid]['latitude']
        if not all([s_lat == v[sid]['latitude'] for k, v in
                    stations.items()]):
            logger.warning(f'multiple latitudes for station {sid}')
        # check longitude
        s_lon = stations[list(stations.keys())[0]][sid]['longitude']
        if not all([s_lon == v[sid]['longitude'] for k, v in
                    stations.items()]):
            logger.warning(f'multiple longitudes for station {sid}')

        if years is None:
            # earliest and last time python can produce
            start_limit = pd.Timestamp.min.tz_localize('UTC')
            end_limit = pd.Timestamp.max.tz_localize('UTC')
        else:
            if fullyear:
                start_limit = pd.Timestamp(
                    years[0], 1, 1, 0, 0, 0).tz_localize('UTC')
                end_limit = pd.Timestamp(
                    years[-1], 12, 31, 23, 59, 59).tz_localize('UTC')
            else:
                start_limit = pd.Timestamp(
                    years[0], 1, 1, 0, 0, 0).tz_localize('UTC')
                end_limit = pd.Timestamp(
                    years[-1], 12, 31, 23, 59, 59).tz_localize('UTC')

        # if time overlaps window:
        if s_start <= end_limit and s_end >= start_limit:
            complete_stations[sid] = {
                "start": s_start,
                "end": s_end,
                "elevation": s_ele,
                "latitude": s_lat,
                "longitude": s_lon,
                "name": s_nam
            }
    return complete_stations


# -------------------------------------------------------------------------

def fetch_station_data(
        station: int, store: bool = True,
        time_start: pd.Timestamp | str | None = None,
        time_end: pd.Timestamp | str | None = None,
        force: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame] | tuple[str, str]:
    """
    Ensure that the DWD weather station data for station
    number `station` is available at `storage_path`.
    If not, data is downloaded and stored in the `storage_path`.

    :param station: DWD station number
    :type station: int
    :param store: If `True` data are be saved to files,
      if `False` data are returned as data frames
    :type store:
    :param time_start: start of desired time window or None
      for getting earliest available data
    :type time_start: pd.Timestamp | str
    :param time_end: end of desired time window or None
      for getting latest available data
    :type time_end: pd.Timestamp | str
    :param force: overwrite existing temp data
    :type force: bool
    :returns: data file name or DataFrame and
      metadata file name or DataFrame
    :rtype: tuple[pd.DataFrame, pd.DataFrame] | tuple[str, str]
    """
    # default: do not limit time
    if time_start is None:
        time_start = pd.Timestamp.min.tz_localize('UTC')
    if time_end is None:
        time_end = pd.Timestamp.max.tz_localize('UTC')

    # for each file to collect:
    # 1. subdir where it resides: .../<subdir>/hourly/*.zip
    # 2. ID of the zip archive:
    #       stundenwerte_<ID>_<station>_<date-from>_<date-to>_hist.zip
    # 3. ID of the data file inside the zip archive:
    #       produkt_<ID>_stunde_<from>_<to>_<station>.txt
    # create temp dir and change into it
    cwd = os.getcwd()
    tempdir = "%05i" % station
    if os.path.exists(tempdir):
        logger.debug(f"deleting existing tempdir {tempdir}")
        shutil.rmtree(tempdir)
    os.mkdir(tempdir)
    os.chdir(tempdir)
    #
    # make empty result and loop files to collect
    product_files = []
    metadata_files = []
    for (gname, gtl, gabbrev) in TO_COLLECT:
        #
        # construct url of the data directory and get file list
        zip_file = fetch_file(gtl, station)
        #
        # find the name of the data file inside the zip archive
        # and extract the product as well as the Metadata files
        product = "produkt_%s_stunde_[0-9_]*%05i.txt" % (gabbrev, station)
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            namelist = zip_ref.namelist()
            to_extract = []
            for name in namelist:
                if re.match(product, name):
                    to_extract.append(name)
                    product_files.append(name)
                elif re.match('Metadaten_' +
                              '(Geographie|Stationsname|Geraete)' +
                              '_.*_%05d.txt' % station, name):
                    to_extract.append(name)
                    metadata_files.append(name)
            zip_ref.extractall(members=to_extract, path=".")
    #
    os.chdir(cwd)
    # parse data files and store data locally
    dat_df_in = data_from_download(
        product_files, tempdir, oldest=pd.Timestamp.min.tz_localize('UTC'))
    meta_df_in = meta_from_download(metadata_files, station, tempdir)

    # limit time if desired:
    dat_df_in = dat_df_in[(dat_df_in.index > time_start)
                          & (dat_df_in.index < time_end)]
    meta_df_in = meta_df_in[(meta_df_in.index > time_start)
                            & (meta_df_in.index < time_end)]

    if store:
        dat_file = os.path.join(_PATH, OBSFILE_DWD % station)
        logging.debug('storing data locally in: %s' % dat_file)
        dat_df_in.to_csv(dat_file, sep=',', na_rep='NA')

        meta_file = os.path.join(_PATH, METAFILE_DWD % station)
        logging.debug('storing metadata in   : %s' % meta_file)
        meta_df_in.to_csv(meta_file, sep=',', na_rep='NA')
    else:
        dat_file = meta_file = None
    #
    # clean up tempdir
    shutil.rmtree(tempdir)
    if store:
        return dat_file, meta_file
    else:
        return dat_df_in, meta_df_in

    # main_frame = build_table(dat_df_in, meta_df_in, years)
    # return main frame


# -------------------------------------------------------------------------
def build_table(dat_df_in: pd.DataFrame, meta_df_in: pd.DataFrame,
                years: list) -> pd.DataFrame | None:
    if len(years) == 0:
        return None
    if not years == [x for x in range(min(years), max(years) + 1)]:
        raise ValueError('years not contiguous')

    hr_idx = pd.date_range(start=pd.Timestamp(years[0], 1, 1, 0, 0, 0),
                           end=pd.Timestamp(years[-1], 12, 31, 23, 59, 59),
                           freq='h', tz='UTC')
    # collect all columns
    dat_cols = dat_df_in.columns
    meta_cols = meta_df_in.columns

    dat_frame = pd.DataFrame(np.nan, index=hr_idx, columns=dat_cols)
    for c in dat_df_in.columns:
        dat_frame[c] = dat_df_in[c].reindex(hr_idx)

    meta_frame = pd.DataFrame(np.nan,
                              index=hr_idx, columns=meta_cols)
    meta_df_in.ffill(inplace=True)
    for c in meta_df_in.columns:
        meta_frame[c] = meta_df_in[c].reindex(hr_idx)
    meta_frame.ffill(inplace=True)

    main_frame = dat_frame.join(meta_frame, how='outer')
    main_frame.index.name = 'time'

    return main_frame


# -------------------------------------------------------------------------

def get_meta_value(metadata: str | pd.DataFrame,
                   time_begin: pd.DatetimeIndex | pd.Timestamp | np.datetime64 | str,
                   time_end: pd.DatetimeIndex | pd.Timestamp | np.datetime64 | str,
                   par_name: str) -> Any:
    """
    get station metadata value for parameter `par_name` valid for
    the time period info from `time_begin` to `time_end`

    :param metadata: filename or pandas dataframe
    :param time_begin: start time as string of datetime-like
    :param time_end: end time as string of datetime-like
    :param par_name: string containig the parameter name

    :return: values for parameter `par_name`
    :rtype: pandas.Series
    """
    logger.debug("getting station metadata: %s" % par_name)
    if isinstance(metadata, str):
        if os.path.isfile(metadata):
            metadata = pd.read_csv(metadata,
                                   index_col='time', parse_dates=True,
                                   sep=',', na_values='NA')
        else:
            raise ValueError('file not found: %s' % metadata)
    elif isinstance(metadata, pd.DataFrame):
        if 'time' in metadata.columns:
            metadata.set_index('time', inplace=True)
        if metadata.index.dtype != 'datetime64[ns]' and \
                metadata.index.dtype != 'datetime64[ns, UTC]':
            raise ValueError('metadata index must have datetime64[ns]'
                             ' or datetime64[ns, UTC]')
    else:
        raise ValueError('metadata must be filename or pandas dataframe')

    # Ensure metadata index is UTC-aware for comparison
    if metadata.index.tz is None:
        metadata.index = metadata.index.tz_localize('UTC')

    time_begin = pd.to_datetime(time_begin, utc=True)
    time_end = pd.to_datetime(time_end, utc=True)
    if time_end < time_begin:
        raise ValueError('time_end must be equal to or after time_begin')
    if par_name not in metadata.columns:
        raise ValueError('parameter not found: %s' % par_name)
    # get all info in time range:
    value = pd.Series()
    for i, v in metadata[par_name].items():
        if i < time_begin:
            value[time_begin] = v
        elif time_begin <= i < time_end:
            value[i] = v
        else:
            value[time_end] = v
            break
    # remove lines giving no new info:
    new = []
    old = None
    for i, v in value.items():
        if len(new) == 0:
            new.append(True)
            old = v
        else:
            if v == old:
                new.append(False)
            else:
                new.append(True)
                old = v
    new[-1] = True
    value = value[new]
    return value


# -------------------------------------------------------------------------

def data_from_download(product_files: list[str], path_to_files: str,
                       oldest: pd.Timestamp | datetime.datetime | str | None = None
                       ) -> pd.DataFrame:
    """
    Build one single table of weather data from the individual
    downloadad files

    :param product_files: list of extracted "produkt" files
    :param path_to_files: path where the product files are stored
    :return: weather timeseries as dataframe. The columns are
      named as they appear in the "produkt" files, except
      "MESS_DATUM" and "STATIONS_ID". Instead, the index contains
      the time of the measurement as `datetime64`.
    :rtype: pandas.DataFrame
    """
    if oldest is None:
        oldest = OLDEST
    elif not isinstance(oldest, pd.Timestamp):
        oldest = pd.to_datetime(oldest, utc=True)

    dat = None
    for name in product_files:
        # read it into DataFrame
        logger.debug('extracting product: %s' % name)
        prodata = pd.read_csv(os.path.join(path_to_files, name),
                              sep=';', skipinitialspace=True,
                              engine='python')
        logger.debug('columns: ' + ';'.join(prodata.columns))
        #
        # convert the time to datetime64
        if prodata['MESS_DATUM'].dtype in [np.dtype(str), object]:
            prodata['time'] = pd.to_datetime(
                prodata['MESS_DATUM'],
                format="%Y%m%d%H", utc=True)
        elif prodata['MESS_DATUM'].dtype == np.int64:
            prodata['time'] = pd.to_datetime(
                list(map(lambda s: '{:010d}'.format(s),
                         prodata['MESS_DATUM'])),
                format="%Y%m%d%H", utc=True)
        else:
            raise ValueError('unknown column dtype {:s}'.format(
                str(prodata['MESS_DATUM'].dtype)))
        #
        # merge dataframes
        prodata.set_index('time', inplace=True)
        prodata.drop(['STATIONS_ID', 'MESS_DATUM', 'eor'],
                     axis=1, inplace=True)
        if dat is None:
            dat = prodata
        else:
            cols_to_use = (list(prodata.columns.difference(dat.columns)))
            dat = dat.merge(prodata[cols_to_use], on='time', how='outer')
    #
    logger.debug("setting blank values to nan")
    #
    for i, col in enumerate(dat.columns):
        logging.debug('... column %s' % col)
        if dat.iloc[:, i].dtypes in [np.int64, np.float64]:
            dat.iloc[dat.iloc[:, i].values == -999, i] = np.nan
        elif dat.iloc[:, i].dtypes == 'object':
            dat.iloc[dat.iloc[:, i].values == '-999', i] = ''
        else:
            logging.debug('    ... skipped (%s)' %
                          format(dat.iloc[:, i].dtypes))
    #
    logging.debug("removing impossible values")
    #
    # remove "-999" from cloud types:
    for i in [1, 2, 3, 4]:
        if ('V_S%i_CSA' % i) in dat.columns:
            dat['V_S%i_CSA' % i] = dat['V_S%i_CSA' % i].map(
                (lambda x: x.replace('-999', '')
                if isinstance(x, str) else x)
            )

    if dat.index[0] < oldest:
        logging.info('remove values before ' + oldest.strftime('%Y-%m-%d'))
        dat = dat[dat.index >= oldest]

    return dat


# -------------------------------------------------------------------------

def meta_from_download(metadata_files: list[str], station: int,
                       path_to_files: str) -> pd.DataFrame:
    """
    Build one single table of the metadata provided by the individual
    metadata files contained in the downloadad zip archives

    :param metadata_files: list of extracted "Metadaten" files
    :param path_to_files: path where these files are stored
    :return: metadata table as dataframe. The columns are
      named as they appear in the "produkt" files, except
      "MESS_DATUM" and "STATIONS_ID". Instead, the index contains
      the time of the measurement as `datetime64`.
    :rtype: pandas.DataFrame
    """
    #
    # deduplicate list
    files = list(set(metadata_files))
    #
    # loop files
    meta = None
    for file in files:
        logging.debug('reading metadata file: %s' % file)

        text_cache = ""
        re_generated = re.compile(r"\s*(generated|generiert).*")
        re_blankline = re.compile(r"^\s*$")
        with open(os.path.join(path_to_files, file), 'r',
                  encoding='iso-8859-1') as f:
            for line in f.readlines():
                if re.match(re_blankline, line):
                    # stop reading at the first blank line
                    # (that separate multiple databank output
                    # blocks in these files)
                    break
                if re.match(re_generated, line):
                    # stop reading at the "generated ..." line
                    # (that concludes these files)
                    break
                text_cache += line

        df = pd.read_csv(io.StringIO(text_cache),
                         sep=';', skipinitialspace=True,
                         engine='python', header=0,
                         dtype=np.dtype(str))
        del text_cache
        df.columns = [x.lower() for x in df.columns]
        logging.debug('... contains: ' + '|'.join(df.columns))
        #
        # filter bad lines
        df = df[df['stations_id'] == str(station)]
        #
        # drop unneeded columns
        if 'Geographie' in file:
            suffix = ''
            cols_to_drop = ['stations_id', 'stationsname', 'eor']
        elif 'Geraete' in file:
            suffix = file.split('_')[2].lower()
            cols_to_drop = ['stations_id', 'stationsname',
                            'geo. laenge [grad]', 'geo. breite [grad]',
                            'stationshoehe [m]', 'eor']
            cols_to_drop += list(df.filter(regex='unnamed'))
        elif 'Stationsname' in file:
            suffix = ''
            cols_to_drop = ['stations_id', 'eor']
        else:
            raise ValueError('unknown metafile %s' % file)
        df = df.drop(cols_to_drop, axis=1, errors='ignore')
        # rename columns
        cols = []
        for c in df.columns:
            if c in ['von_datum', 'bis_datum'] or suffix == '':
                cols.append(c)
            else:
                cols.append('_'.join((suffix, c)))
        df.columns = cols
        #
        # convert dates
        df1 = df.copy()
        df1['time'] = pd.to_datetime(df1['von_datum'],
                                     format="%Y%m%d", utc=True)
        df1 = df1.set_index('time')
        df1.drop(['von_datum', 'bis_datum'], axis=1, inplace=True)
        df2 = df.copy()
        df2['time'] = (pd.to_datetime(df2['bis_datum'],
                                      format="%Y%m%d", utc=True)
                       + pd.Timedelta('23h'))

        df2 = df2.set_index('time')
        df2.drop(['von_datum', 'bis_datum'], axis=1, inplace=True)

        del df
        df = pd.concat((df1, df2))
        #
        logging.debug("fill blank metadata values")
        df = df.ffill()
        #
        logging.debug('merging metadata')
        if meta is None:
            meta = df
        else:
            # no duplicate columns (https://stackoverflow.com/a/19125531)
            cols_to_use = list(df.columns.difference(meta.columns))
            meta = meta.join(df[cols_to_use],
                             how='outer',
                             lsuffix=' ',
                             rsuffix=' (doppel)'
                             )
        logging.debug(meta.columns)

    meta = meta.ffill()
    # remove duplicates
    meta = meta.drop_duplicates()
    meta = meta[~meta.index.duplicated(keep='last')]
    #
    return meta

