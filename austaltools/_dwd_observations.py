#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Feb  3 19:20:42 2022

@author: clemens
"""
import argparse
import io
import logging
import os
import re
import shutil
import tempfile
import zipfile

import netCDF4
import requests
import numpy as np
import pandas as pd

try:
    from . import _tools
except ImportError:
    import _tools

logger = logging.getLogger()

_PATH = "."
# remove observations before ...
# (to avoid problems with odd observation timing in the very manual era)
OLDEST = pd.to_datetime('1970-01-01', utc=True)
# filename pattern for cached DWD observations
OBSFILE_DWD = 'observations_hourly_%05i.csv'
METAFILE_DWD = 'metadata_%05i.csv'
#
TO_COLLECT = [
    ['air_temperature', 'TU', 'tu'],
    #['cloudiness', 'N', 'n'],
    ['cloud_type', 'CS', 'cs'],
    ['extreme_wind', 'FX', 'fx'],
    ['precipitation', 'RR', 'rr'],
    ['pressure', 'P0', 'p0'],
    ['soil_temperature', 'EB', 'eb'],
    ['visibility', 'VV', 'vv'],
    ['wind', 'FF', 'ff'],
]

# -------------------------------------------------------------------------

def dwd_fetch_dirlist(url, pattern='.*'):
    with requests.get(url, allow_redirects=True) as rsp:
        text = rsp.content.decode()
        links = [x for x in re.findall(r'href="(.+?)"', text)]
        files = [x for x in links if bool(re.match(pattern, x))]
    return files

# -------------------------------------------------------------------------

def dwd_fetch_file(group: str, station: (int, str),
                   era=None, local_path='.'):

    http_addr = 'https://opendata.dwd.de'
    http_path = ('climate_environment/CDC/observations_germany'
                 '/climate/hourly')
    if era not in [None, 'recent', 'historical']:
        raise ValueError(f'unknwon era: {era}')
    if not era:
        era = 'historical'

    for (name, gtl, _) in TO_COLLECT:
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
        fname = dwd_fetch_dirlist(baseurl, "stundenwerte_%s_%05i_0003_.*\.zip")

    local_name = os.path.join(local_path, fname)
    url = "/".join((baseurl, fname))

    return _tools.download(url, local_name)


# -------------------------------------------------------------------------

def dwd_fetch_stationlist(year, fullyear=True):
    stations={}
    for (groupname, gtl, groupabbr) in TO_COLLECT:
        listfile = dwd_fetch_file(gtl, 'stations')
        stations[gtl]={}
        with open(listfile, 'r', encoding="latin-1") as f:
            # skip header
            f.readline()
            f.readline()
            for line in f.readlines():
                s_id = int(line[0:5])
                stations[gtl][s_id] = {
                    "start": pd.to_datetime(line[6:14], format="%Y%m%d"),
                    "end": pd.to_datetime(line[15:23], format="%Y%m%d"),
                    "elevation": float(line[31:40]),
                    "latitude": float(line[41:50]),
                    "longitude": float(line[51:60]),
                    "name": (line[61:102]).strip()
                }
    # get all station IDs
    sids = list(set([x for k,v in stations.items() for x in v.keys()]))
    # find stations that provide all parameters
    complete_stations={}
    for sid in sids:
        # skip stations not listed in all groups
        if not all([sid in v.keys() for k,v in stations.items()]):
            continue
        # last start date
        s_start = max([v[sid]['start'] for k,v in stations.items()])
        # first end date
        s_end = min([v[sid]['end'] for k,v in stations.items()])
        # check elevation
        s_ele = stations[list(stations.keys())[0]][sid]['elevation']
        if not all([s_ele == v[sid]['elevation'] for k,v in stations.items()]):
            logger.warning(f'multiple elevations for station {sid}')
        # check latitude
        s_lat = stations[list(stations.keys())[0]][sid]['latitude']
        if not all([s_lat == v[sid]['latitude'] for k,v in stations.items()]):
            logger.warning(f'multiple latitudes for station {sid}')
        s_lon = stations[list(stations.keys())[0]][sid]['longitude']
        if not all([s_lon == v[sid]['longitude'] for k,v in stations.items()]):
            logger.warning(f'multiple longitudes for station {sid}')
        # check longitude
        s_nam = stations[list(stations.keys())[0]][sid]['name']
        if not all(
                [s_nam == v[sid]['name'] for k, v in stations.items()]):
            logger.warning(f'multiple name for station {sid}')

        if not year:
            start_limit = s_start - pd.Timedelta(1, "year")
            end_limit = s_end + pd.Timedelta(1, "year")
        else:
            if fullyear:
                start_limit = pd.Timestamp(year, 1, 1, 0, 0, 0)
                end_limit = pd.Timestamp(year, 12, 31, 23, 59,59)
            else:
                start_limit = pd.Timestamp(year, 1, 1, 0, 0, 0)
                end_limit = pd.Timestamp(year, 12, 31, 23, 59, 59)

        # if time overlaps window:
        if s_start <= start_limit and s_end >= end_limit:
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

def dwd_fetch_station(station, storage_path='.'):
    """
    Ensure that the DWD weather station data for station
    number `station` is available at `storage_path`.
    If not, data is downloaded and stored in the `storage_path`.

    :param storage_path: data storage directory

    """
    # for each file to collect:
    # 1. subdir where it resides: .../<subdir>/hourly/*.zip
    # 2. ID of the zip archive:
    #       stundenwerte_<ID>_<station>_<date-from>_<date-to>_hist.zip
    # 3. ID of the data file inside the zip archive:
    #       produkt_<ID>_stunde_<from>_<to>_<station>.txt
    # create temp dir and change into it
    os.chdir(_PATH)
    tempdir = "%05i" % station
    os.mkdir(tempdir)
    os.chdir(tempdir)
    #
    # make empty result and loop files to collect
    product_files = []
    metadata_files = []
    for (gname, gtl, gabbrev) in TO_COLLECT:
        #
        # construct url of the data directory and get file list
        zip_file = dwd_fetch_file(gtl, station)
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
    os.chdir(_PATH)
    # parse data files and store data locally
    dat = dwd_data_from_download(product_files, tempdir)
    dat_file = os.path.join(_PATH, OBSFILE_DWD % station)
    logging.debug('storing data locally in: %s' % dat_file)
    dat.to_csv(dat_file, sep=',', na_rep='NA')
    #
    meta = dwd_meta_from_download(metadata_files, station, tempdir)
    meta_file = os.path.join(_PATH, METAFILE_DWD % station)
    logging.debug('storing metadata in   : %s' % meta_file)
    meta.to_csv(meta_file, sep=',', na_rep='NA')
    #
    # clean up tempdir
    shutil.rmtree(tempdir)
    return dat_file, meta_file

# -------------------------------------------------------------------------
def build_dataset_year(datafile, stations, year=None,
                       replace=False, path=_PATH):

    if os.path.exists(datafile):
        if replace:
            os.remove(datafile)
        else:
            raise IOError(f'file {datafile} already exists')

    dim_time = pd.date_range(start=pd.Timestamp(year, 1, 1, 0, 0, 0),
                             end=pd.Timestamp(year, 12, 31, 23, 59, 59),
                             freq='h')
    # collect all columns
    dat_cols=[]
    meta_cols=[]
    for station in stations:
        with  pd.read_csv(OBSFILE_DWD % station) as df:
            dat_cols = list({*dat_cols, *df.columns})
        with  pd.read_csv(METAFILE_DWD % station) as df:
            meta_cols = list({*dat_cols, *df.columns})

    # collect data
    main_index = pd.MultiIndex.from_product([dim_time, stations])

    with pd.HDFStore(datafile, mode='w', complib='zlib') as store:
        for station in _tools.progress(stations):
            dat_frame = pd.DataFrame(np.nan,
                                     index=main_index, columns=dat_cols)
            with  pd.read_csv(OBSFILE_DWD % station) as df:
                for c in df.columns:
                    for i in df.index:
                        im = (i, station)
                        dat_frame.loc[im, c] = df.loc[i, c]

            meta_frame = pd.DataFrame(np.nan,
                                      index=main_index, columns=meta_cols)
            with  pd.read_csv(METAFILE_DWD % station) as df:
                tf = pd.DataFrame(np.nan, index=dim_time, columns=[]
                                        ).join(df, how='outer')
                tf.fillna(method='ffill', inplace=True)
                tf = tf[tf.index.isin(dim_time)]
                for c in tf.columns:
                    for i in tf.index:
                        im = (i, station)
                        dat_frame.loc[im, c] = tf.loc[i, c]

            main_frame = dat_frame.join(meta_frame, how='outer')

            station_id = "%05i" % station
            main_frame.to_hdf(store, key=station_id)
    main_frame.to_netcdf(path=datafile)



# -------------------------------------------------------------------------

def dwd_metadata(station, time1, time2, param, path=_PATH):
    time1 = pd.to_datetime(time1, utc=True)
    time2 = pd.to_datetime(time2, utc=True)
    if time2 < time1:
        raise ValueError('time2 mut be equal or after time1')
    stninfo = os.path.join(path, METAFILE_DWD % station)
    logger.debug("read station info from: %s" % stninfo)
    md = pd.read_csv(stninfo, header=0)
    md.index = pd.to_datetime(md['time'])
    if param not in md.columns:
        raise ValueError('parameter not found: %s' % param)
    # get all info in time range:
    value = pd.Series()
    for i, v in md[param].items():
        if i < time1:
            value[time1] = v
        elif time1 <= i < time2:
            value[i] = v
        else:
            value[time2] = v
            break
    # reduce lines giving no new info:
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

def dwd_get_meta_value(metadata, time_begin, time_end, par_name):
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
        if metadata.index.dtype != 'datetime64[ns]':
            raise ValueError('metadata index must have datetime64[ns]')
    else:
        raise ValueError('metadata must be filename or pandas dataframe')
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

# def dwd_stationlist(group, year=None):
#     if station is not None:
#         sstr = '{:05d}'.format(station)
#         if pos_lat is not None and pos_lon is not None:
#             raise ValueError('lat and lon must be None ' +
#                              'unless station is None')
#     else:
#         sstr = None
#     stninfo = os.path.join(path, 'TU_Stundenwerte_Beschreibung_Stationen.txt')
#     logger.debug("read station info from: %s" % stninfo)
#     min_sdist = 9999999.
#     sid = None
#     with (open(stninfo, 'r') as f):
#         # skip header
#         f.readline()
#         f.readline()
#         for line in f.readlines():
#             s_id = line[0:5]
#             s_ele = float(line[31:40])
#             s_lat = float(line[41:50])
#             s_lon = float(line[51:60])
#             s_nam = (line[61:102]).strip()
#             if sstr is not None:
#                 if  line[0:5] == sstr:
#                     ele = s_ele
#                     lat = s_lat
#                     lon = s_lon
#                     nam = s_nam
#                     sid = station
#                     break
#             else:
#                 sdist = _tools.spheric_distance(s_lat, s_lon, pos_lat, pos_lon)
#                 if sdist < min_sdist:
#                     sid = s_id
#                     ele = s_ele
#                     lat = s_lat
#                     lon = s_lon
#                     nam = s_nam
#                     min_sdist = sdist
#     if sid is None:
#         raise ValueError('station not found: %s' % station)
#     logger.debug("station name: %s" % nam)
#     if station is None:
#         return lat, lon, ele, nam, int(sid)
#     else:
#         return lat, lon, ele, nam

# -------------------------------------------------------------------------

def dwd_stationinfo(station, path=_PATH, pos_lat=None, pos_lon=None):
    if station is not None:
        sstr = '{:05d}'.format(station)
        if pos_lat is not None and pos_lon is not None:
            raise ValueError('lat and lon must be None ' +
                             'unless station is None')
    else:
        sstr = None
    stninfo = os.path.join(path, 'TU_Stundenwerte_Beschreibung_Stationen.txt')
    logger.debug("read station info from: %s" % stninfo)
    min_sdist = 9999999.
    sid = None
    with (open(stninfo, 'r') as f):
        # skip header
        f.readline()
        f.readline()
        for line in f.readlines():
            s_id = line[0:5]
            s_ele = float(line[31:40])
            s_lat = float(line[41:50])
            s_lon = float(line[51:60])
            s_nam = (line[61:102]).strip()
            if sstr is not None:
                if  line[0:5] == sstr:
                    ele = s_ele
                    lat = s_lat
                    lon = s_lon
                    nam = s_nam
                    sid = station
                    break
            else:
                sdist = _tools.spheric_distance(s_lat, s_lon, pos_lat, pos_lon)
                if sdist < min_sdist:
                    sid = s_id
                    ele = s_ele
                    lat = s_lat
                    lon = s_lon
                    nam = s_nam
                    min_sdist = sdist
    if sid is None:
        raise ValueError('station not found: %s' % station)
    logger.debug("station name: %s" % nam)
    if station is None:
        return lat, lon, ele, nam, int(sid)
    else:
        return lat, lon, ele, nam


def dwd_data_from_download(product_files: list, path_to_files: str) \
        -> pd.DataFrame:
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
        dat['V_S%i_CSA' % i] = \
            dat['V_S%i_CSA' % i].str.replace('-999', '')

    if dat.index[0] < OLDEST:
        logging.info('remove values before ' + OLDEST.strftime('%Y-%m-%d'))
        dat = dat[dat.index >= OLDEST]

    return dat


def dwd_meta_from_download(metadata_files, station, path_to_files):
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
        re_generated = re.compile("\s*(generated|generiert).*")
        re_blankline = re.compile("^\s*$")
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
        logging.debug('merging metadata')
        if meta is None:
            meta = df
        else:
            # no duplicate columns (https://stackoverflow.com/a/19125531)
            cols_to_use = (list(df.columns.difference(meta.columns))
                           + ['von_datum', 'bis_datum'])
            meta = meta.merge(df[cols_to_use],
                              on=['von_datum', 'bis_datum'],
                              how='outer',
                              suffixes=('', ' (doppel)'))
        logging.debug(meta.columns)
    #
    # convert dates
    meta['time'] = pd.to_datetime(meta['von_datum'],
                                  format="%Y%m%d", utc=True)
    meta = meta.set_index('time')
    #
    logging.debug("fill blank metadata values")
    meta = meta.ffill()
    meta = meta.drop_duplicates()
    #
    return meta
