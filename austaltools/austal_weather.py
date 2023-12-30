#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Dec 17 13:36:08 2021

@author: clemens
"""
import argparse
import datetime as dt
from html.parser import HTMLParser
import logging
import os
import re
import shutil
import sys
import tempfile
import zipfile
from urllib.request import urlretrieve

import meteolib as m
import numpy as np
import pandas as pd
import readmet

try:
    from ._dwd_stationinfo import dwd_stationinfo, slugify
except ImportError:
    from _dwd_stationinfo import dwd_stationinfo, slugify

try:
    from ._dispersion import klug_manier_scheme, pasquill_taylor_scheme
    from ._dispersion import stabilty_class, obukhov_length
    from ._dispersion import vdi_3872_6_standard_wind
except ImportError:
    from _dispersion import klug_manier_scheme, pasquill_taylor_scheme
    from _dispersion import stabilty_class, obukhov_length
    from _dispersion import vdi_3872_6_standard_wind

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

# ----------------------------------------------------
KNOWN_SOURCES = ["ERA5", "DWD"]
STORAGE_LOCATIONS = _tools.DEFAULT_DATA_DIRS
STORAGE_DIR = "weather"
STORAGE_PATH = None  # will be filled lazy

# possible defaults: fixed_057 fixed_010 model_mean model_uv10 model_fsr
WIND_VARIANT = os.environ.get('WIND_VARIANT', 'model_uv10')
# possible defaults: barycentric nearest mean
INTER_VARIANT = os.environ.get('INTER_VARIANT', 'barycentric')
# possible values: empty or non-empty string:
OUTPUT_RAW = os.environ.get('OUTPUT_RAW', '')
# possible values: all kms kmc pts pgc empty or non-empty string:
CLASS_SCHEME = os.environ.get('CLASS_SCHEME', 'kms')

# remove observations before ...
# (to avoid problems with odd observation timing in the very manual era)
OLDEST = pd.to_datetime('1970-01-01', utc=True)
# filename pattern for cached DWD observations
OBSFILE_DWD = 'observations_hourly_%05i.csv'
METAFILE_DWD = 'metadata_%05i.csv'

# ----------------------------------------------------

kappa = m.constants.kappa
gn = m.constants.gn
_check = m._utils._check


# ----------------------------------------------------

def provide_storage(storage_path=None):
    """
    find a working data storage directory
    :param storage_path: (optional) user selected path
    :return: data storage directory
    :rtype str:
    """
    if storage_path is not None:
        # path is prescribed
        if not os.path.isdir(storage_path):
            raise ValueError("weather storage not found at: %s" %
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
    if storage_path is None:
        # no location was found, we must create one:
        logger.warning("no preexisting weather data storage found")
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
            raise OSError("Could not create weather storage dir")
    return storage_path


def provide_dwd_station(storage_path, force=False):
    server = "https://opendata.dwd.de"
    path_aux = "climate_environment/CDC/help"
    files_aux = ["FF_Stundenwerte_Beschreibung_Stationen.txt"]

    for aux in files_aux:
        if not os.path.exists(os.path.join(storage_path, aux)):
            urlretrieve("/".join(server, path_aux, aux),
                        os.path(storage_path, aux))



# ----------------------------------------------------
def h_eff(has, z0s):
    z0_vals = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1., 1.5, 2]
    href = 250
    d0s = m.wind.DISPLACEMENT_FACTOR * z0s
    ps = np.log((has - d0s) / z0s) / np.log((href - d0s) / z0s)
    ha = []
    for z0 in z0_vals:
        d0 = m.wind.DISPLACEMENT_FACTOR * z0
        ha.append(d0 + z0 * ((href - d0) / z0) ** ps)
    return ha

# ----------------------------------------------------
def read_era5_nc(ncfile, lat, lon):
    """
    read ERA5 nc file and interpolate values to position (lat, lon)
        and recalculate 10 wind speed anddirection (ff/dd) using
        actual surface roughness
        values: 'time',
                'u10', 'v10', 'sp', 'zust', 'fsr',
                 't2m', 'd2m', 'cbh', 'sshf', 'slhf',
                 'lcc', 'tcc'
        optional: 'mcc', 'tp'
    """
    import netCDF4

    _VAR_NEEDED = ['u10', 'v10', 'sp', 'zust', 'fsr',
                   't2m', 'd2m', 'cbh', 'sshf', 'slhf',
                   'lcc', 'tcc']
    _VAR_OPTIONAL = ['mcc', 'tp']

    lp = netCDF4.Dataset(ncfile)

    for x in _VAR_NEEDED:
        if x not in lp.variables:
            raise ValueError('needed variable not in input data: %s' % x)
    all_variables = _VAR_NEEDED
    for x in _VAR_OPTIONAL:
        if x not in lp.variables:
            logging.warning('optional variable not in input data: %s' % x)
        else:
            all_variables.append(x)

    dims = {'lat': lp['latitude'][:].data,
            'lon': lp['longitude'][:].data}

    # make sure dims are ascending:
    flip = {'lon': False, 'lat': False}
    for ll in 'lat', 'lon':
        if not np.all(np.diff(dims[ll]) >= 0):
            dims[ll] = np.flip(dims[ll])
            flip[ll] = True

    idx = {'lat': -1, 'lon': -1}
    tgt = {'lat': lat, 'lon': lon}
    for ll in ['lat', 'lon']:
        # position of largest dims value smaller than tgt
        ii = np.argmax(np.where(dims[ll] <= tgt[ll], dims[ll], -999))
        # add fraction
        if ii < len(dims[ll]):
            idx[ll] = ii + ((tgt[ll] - dims[ll][ii]) /
                            (dims[ll][ii + 1] - dims[ll][ii]))

    logging.info('idx: %s' % str(idx))
    pos = [None, None, None]
    if np.modf(idx['lon'])[0] <= 0.5:
        if np.modf(idx['lat'])[0] <= 0.5:
            # SW corner
            pos[0] = (np.int(idx['lon']), np.int(idx['lat']))
            pos[1] = (np.int(idx['lon'] + 1), np.int(idx['lat']))
            pos[2] = (np.int(idx['lon']), np.int(idx['lat'] + 1))
        else:
            # NW corner
            pos[0] = (np.int(idx['lon']), np.int(idx['lat'] + 1))
            pos[1] = (np.int(idx['lon'] + 1), np.int(idx['lat'] + 1))
            pos[2] = (np.int(idx['lon']), np.int(idx['lat']))
    else:
        if np.modf(idx['lat'])[0] <= 0.5:
            # SE corner
            pos[0] = (np.int(idx['lon'] + 1), np.int(idx['lat']))
            pos[1] = (np.int(idx['lon'] + 1), np.int(idx['lat'] + 1))
            pos[2] = (np.int(idx['lon']), np.int(idx['lat']))
        else:
            # NE corner
            pos[0] = (np.int(idx['lon'] + 1), np.int(idx['lat'] + 1))
            pos[1] = (np.int(idx['lon']), np.int(idx['lat'] + 1))
            pos[2] = (np.int(idx['lon'] + 1), np.int(idx['lat']))

    pi, pj = pos[0]
    logging.info(str((pi, pj, dims['lon'][pi], dims['lat'][pj])))

    if INTER_VARIANT == 'barycentric':
        # calculate barycentric weights so that
        # val(x,y) = w1*val(x1,y1) + w2*val(x2,y2) + w3*val(x3,y3)
        # https://en.wikipedia.org/wiki/Barycentric_coordinate_system
        #
        x = []
        y = []
        for pp in pos:
            pi, pj = pp
            x.append(dims['lon'][pi])
            y.append(dims['lat'][pj])
        w0 = (((y[1] - y[2]) * (lon - x[2]) +
               (x[2] - x[1]) * (lat - y[2])) /
              ((y[1] - y[2]) * (x[0] - x[2]) +
               (x[2] - x[1]) * (y[0] - y[2])))
        w1 = (((y[2] - y[0]) * (lon - x[2]) +
               (x[0] - x[2]) * (lat - y[2])) /
              ((y[1] - y[2]) * (x[0] - x[2]) +
               (x[2] - x[1]) * (y[0] - y[2])))
        w2 = 1 - (w0 + w1)
    elif INTER_VARIANT == 'mean':
        w0 = 1. / 3.
        w1 = 1. / 3.
        w2 = 1. / 3.
    elif INTER_VARIANT == 'nearest':
        w0 = 1.
        w1 = 0.
        w2 = 0.
        logging.debug("extracting position %.4f / %.4f " %
                      (dims['lon'][pos[0][0]], dims['lat'][pos[0][1]]))
    else:
        raise ValueError('unknown interpolation variant: %s' %
                         INTER_VARIANT)
    logging.info('interpolation variant: %s' % INTER_VARIANT)
    logging.debug('weights: %6.2f %6.2f %6.2f' % (w0, w1, w2))

    values = pd.DataFrame()
    epoch = dt.datetime(1900, 1, 1, 0, 0, tzinfo=dt.timezone.utc)
    values['time'] = pd.to_datetime(
        [epoch + dt.timedelta(hours=int(x)) for x in lp['time']])
    for val in all_variables:
        logging.info('interpolating value: %s' % val)
        v = [None, None, None]
        for i, pp in enumerate(pos):
            pi, pj = pp
            if flip['lon']:
                pi = len(dims['lon']) - 1 - pi
            if flip['lat']:
                pj = len(dims['lat']) - 1 - pj
            v[i] = pd.Series(lp[val][:, pj, pi].data)
        values[val] = w0 * v[0] + w1 * v[1] + w2 * v[2]
    #
    #   surface fluxes are in J/hm² down, convert to W/m² up:
    for val in ['sshf', 'slhf']:
        if val in all_variables:
            values[val] = values[val] / (-3600.)
    #   total precipitation is m (per hour) , convert to mm:
    for val in ['tp']:
        if val in all_variables:
            values[val] = values[val] * 1000
    #
    #    values['ff'] = np.sqrt(values['u10']*values['u10'] +
    #                           values['v10']*values['v10'])
    #
    #   BUT:
    #   These '10m wind components' are diagnostic quantities generally
    #   computed not by using the roughness length of the tile itself,
    #   but instead assuming a roughness length for short grass (=0.03m),
    #   the surface over which (by WMO convention) winds should be measured
    #   https://confluence.ecmwf.int/display/FUG/Section+9.3+Surface+Wind
    #
    #   Therefore: u10 = u*/k * ln(z/z0)
    if WIND_VARIANT == 'fixed_057':
        z0 = 0.57
        values['fsr'] = z0
        values['ff'] = (values['zust'] / kappa *
                        np.log((10. + 7. * z0) / z0))
    elif WIND_VARIANT == 'fixed_010':
        z0 = 0.10
        values['fsr'] = z0
        values['ff'] = (values['zust'] / kappa *
                        np.log((10. + 7. * z0) / z0))
    elif WIND_VARIANT == 'model_mean':
        z0 = np.nanmean(values['zust'])
        values['fsr'] = z0
        values['ff'] = (values['zust'] / kappa *
                        np.log((10. + 7. * z0) / z0))
    elif WIND_VARIANT == 'model_uv10':
        values['ff'] = np.sqrt(values['u10'] ** 2 + values['v10'] ** 2)
    elif WIND_VARIANT == 'model_fsr':
        values['ff'] = (values['zust'] / kappa *
                        np.log((10. + 7. * values['fsr']) / values['fsr']))
    else:
        raise ValueError('unknown wind variant: %s' % WIND_VARIANT)
    logging.info('wind variant: %s' % WIND_VARIANT)
    values['dd'] = np.rad2deg(np.arctan2((-values['u10']),
                                         (-values['v10'])))

    return values

# ----------------------------------------------------

def get_ERA5_weather(lat, lon, year, storage_path='.'):
    ncfile = os.path.join(storage_path, 'era5_ak_eu_%04i.nc' % year)
    logging.info('reading data from; %s' % ncfile)

    v = read_era5_nc(ncfile, lat, lon)
    v.index = v['time']
    v.sort_index(inplace=True)

    logging.debug('lmcc')
    if 'mcc' in v.keys():
        v['lmcc'] = np.maximum(v['lcc'], v['mcc'])
    else:
        v['lmcc'] = v['lcc']

    res = v.filter(['time', 'ff', 'sp', 't2m','lmcc','tcc', 'sshf', 'slhf', 'fsr'])
    return res

# ----------------------------------------------------

def provide_DWD_weather(station, storage_path='.'):
    http_addr = "https://opendata.dwd.de"
    http_path = "climate_environment/CDC/observations_germany/climate/hourly"
    # for each file to collect:
    # 1. subdir where it resides: .../<subdir>/hourly/*.zip
    # 2. ID of the zip archive:
    #       stundenwerte_<ID>_<station>_<date-from>_<date-to>_hist.zip
    # 3. ID of the data file inside the zip archive:
    #       produkt_<ID>_stunde_<from>_<to>_<station>.txt
    to_collect = [
        ['air_temperature', 'TU', 'tu'],
        ['cloudiness', 'N', 'n'],
        ['cloud_type', 'CS', 'cs'],
        ['extreme_wind', 'FX', 'fx'],
        ['precipitation', 'RR', 'rr'],
        ['pressure', 'P0', 'p0'],
        ['soil_temperature', 'EB', 'eb'],
        ['visibility', 'VV', 'vv'],
        ['wind', 'FF', 'ff'],
    ]
    logger.info('getting data from %s' % http_addr)
    #
    # create temp dir and change into it
    cwd = os.getcwd()
    tempdir = tempfile.mkdtemp()
    os.chdir(tempdir)
    #
    # make empty result and loop files to collect
    res = None
    product_files = []
    metadata_files = []
    for (dnam, zid, tid) in to_collect:
        #
        # construct url of the data directory and get file list
        list_link = "/".join([http_addr,http_path,dnam,'historical'])
        logger.debug('getting dirlist: %s' % list_link)
        list_file = os.path.join(tempdir, "temp.html")
        urlretrieve(list_link, list_file)
        #
        # find the filename of the archive we want
        with open(list_file, 'r') as list_handle:
            html = list_handle.read()
            http_links = re.findall(r'href="(.*?)"', html)
        for link in http_links:
            pattern = 'stundenwerte_%s_%05i_[0-9_]*_hist.zip' % (zid, station)
            if re.match(pattern, link):
                break
        else:
            raise ValueError("Could not find matching archive file")
        #
        # construct url of the archive we want and get zip file
        zip_link = "/".join([http_addr,http_path,dnam,'historical',link])
        logger.debug('getting archive: %s' % zip_link)
        zip_file = os.path.join(tempdir, "temp.zip")
        urlretrieve(zip_link, zip_file)
        #
        # find the name of the data file inside the zip archive
        # and extract the product as well as the Metadata files
        product = "produkt_%s_stunde_[0-9_]*%05i.txt" % (tid, station)
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
            zip_ref.extractall(members=to_extract,path=tempdir)
    #
    # parse data files and store data locally
    dat = data_DWD_to_csv(product_files, tempdir)
    outname = os.path.join(storage_path, OBSFILE_DWD % station)
    logging.info('storing data locally in: %s' % outname)
    dat.to_csv(outname, sep=',',na_rep='NA')
    #
    meta = meta_DWD_to_csv(metadata_files, station, tempdir)
    outname = os.path.join(storage_path, METAFILE_DWD % station)
    logging.info('storing metadata in   : %s' % outname)
    meta.to_csv(outname, sep=',', na_rep='NA')
    #
    # clean up tempdir
    os.chdir(cwd)
    shutil.rmtree(tempdir)


def data_DWD_to_csv(product_files: list, path_to_files: str):
    dat = None
    for name in product_files:
        # read it into DataFrame
        logger.debug('extracting product: %s' % name)
        prodata = pd.read_csv(os.path.join(path_to_files, name),
                              sep=';', skipinitialspace=True)
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
            dat = dat.merge(prodata, on='time', how='outer')
    #
    logger.debug("setting blank values to nan")
    #
    for i,col in enumerate(dat.columns):
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

def meta_DWD_to_csv(metadata_files, station, path_to_files):
    #
    # deduplicate list
    files = list(set(metadata_files))
    #
    # loop files
    meta = None
    for file in files:
        logging.debug('reading metadata file: %s' % (file))

        df = pd.read_csv(os.path.join(path_to_files, file),
                         sep=';', skipinitialspace=True,
                         engine='python', header=0,
                         dtype=np.dtype(str),
                         encoding='iso-8859-1')
        df.columns = [x.lower() for x in df.columns]
        logging.debug('... contains: ' + '|'.join(df.columns))
        #
        # filter bad lines
        df = df[df['stations_id'] == str(station)]
        #
        # drop unneeded columns
        if 'eor' in df.columns:
            df = df.drop(['eor'], axis=1)
        if 'Geographie' in file:
            suffix = ''
            df = df.drop(['stations_id', 'stationsname'], axis=1)
        elif 'Geraete' in file:
            suffix = file.split('_')[2].lower()
            for c in df.columns:
                if (c in ['stations_id', 'stationsname',
                          'geo. laenge [grad]', 'geo. breite [grad]',
                          'stationshoehe [m]'] or
                        'unnamed' in c):
                    df = df.drop(c, axis=1)
        elif 'Stationsname' in file:
            suffix = ''
            df = df.drop(['stations_id'], axis=1)
        else:
            suffix='unknown'
        # rename columns
        cols = []
        for c in df.columns:
            if c in ['von_datum', 'bis_datum'] or suffix == '':
                cols.append(c)
            else:
                cols.append('_'.join((suffix,c)))
        df.columns = cols
        logging.debug('merging metadata')
        if meta is None:
            meta = df
        else:
            # remove duplicate columns
            for c in df.columns:
                if c in ['von_datum', 'bis_datum']:
                    pass
                elif c in meta.columns:
                    df = df.drop(c, axis=1)
            logging.debug(df.columns)
            meta = meta.merge(df, on=['von_datum', 'bis_datum'],
                            how='outer', suffixes=('', ' (doppel)'))
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

def get_DWD_weather(lat, lon, year, station=None, storage_path='.'):
    if station is None:
        lat, lon, ele, nam, station = dwd_stationinfo(None, storage_path,
                                                      lat, lon)
    else:
        lat, lon, ele, nam = dwd_stationinfo(station, storage_path)
    obsfile = OBSFILE_DWD % station
    metafile = METAFILE_DWD % station
    if not (os.path.exists(os.path.join(storage_path,obsfile)) and
            os.path.exists(os.path.join(storage_path,metafile))):
        logger.info('data from station %05i not in storage' % station)
        provide_DWD_weather(station, storage_path)
    else:
        logger.info('data from station %05i found in storage' % station)



# =======================================================================

def cli() -> dict:
    """
    command line interface

    :return: conf (dict)
    """
    #
    # defaults
    #
    default_source = KNOWN_SOURCES[0]
    default_year = 2020
    default_position = 5100
    path = '/usr/share/austaltools/data/era'
    #
    # command line args
    #
    parser = argparse.ArgumentParser(
        description='get AUSTAL meteorlogical timeseries',
        epilog='one of -L, -G, -U, -D, or -W and NAME' +
               ' are required unless ' +
               '--list-sources or --force-download is selected')
    parser.add_argument(dest="output", metavar="NAME",
                        help="file name to store data in."
                        )
    cspars = parser.add_mutually_exclusive_group()
    cspars.add_argument('-L', '--ll',
                        metavar=("LON", "LAT"),
                        dest="ll",
                        nargs=2,
                        default=None,
                        help='Center position given as Longitude and ' +
                             'Latitude, respectively. ' +
                             'This is the default.')
    cspars.add_argument('-G', '--gk',
                        metavar=("X", "Y"),
                        dest="gk",
                        nargs=2,
                        default=None,
                        help='Center position given in Gauß-Krüger zone 3' +
                             'coordinates: X = `Rechtswert`, ' +
                             'Y = `Hochwert`. ')
    cspars.add_argument('-U', '--utm',
                        metavar=("X", "Y"),
                        dest="ut",
                        nargs=2,
                        default=None,
                        help='Center position given in UTM Zone 32N' +
                             'coordinates: X = `easting`, ' +
                             'Y = `northing`.')
    cspars.add_argument('-D', '--dwd',
                        metavar=["NUMBER"],
                        dest="dwd",
                        nargs=1,
                        help='Postion of weather station with ' +
                             'German weather service (DWD) ID `NUMBER`')
    cspars.add_argument('-W', '--wmo',
                        metavar=["NUMBER"],
                        dest="wmo",
                        nargs=1,
                        help='Postion of weather station with ' +
                             'World Meteorological Organization (WMO)' +
                             'station ID `NUMBER`')

    parser.add_argument('-s', '--source',
                        metavar="CODE",
                        nargs=1,
                        choices=KNOWN_SOURCES,
                        default=default_source,
                        help='code for the source digital elevation ' +
                             'model (DEM). Known DEMs are: ' +
                             ' '.join(KNOWN_SOURCES) + ' ' +
                             'Defaults to ' + default_source)
    parser.add_argument('-y', '--year', dest='year',
                        metavar='YEAR',
                        nargs=1,
                        help='year of interest [%04i]' % default_year)

    parser.add_argument('-e', '--elevation', dest='ele',
                        metavar='METERS',
                        help='surface elevation. ' +
                             'only allowed with -L, -G, -U.')

    parser.add_argument('-w', '--station', dest='station',
                        metavar='ID',
                        default=None,
                        help='weather station ID. ' +
                             'only allowed with -D, -W.')

    parser.add_argument('-p', '--precip', dest='prec',
                        action='store_true',
                        help='add precipitation columns to output file')

    verb = parser.add_mutually_exclusive_group()
    verb.add_argument('--debug', dest='verb', action='store_const',
                      const=logging.DEBUG, help='show informative output')
    verb.add_argument('-v', '--verbose', dest='verb', action='store_const',
                      const=logging.INFO, help='show detailed output')
    args = parser.parse_args()
    #
    # logging level
    #
    if args.verb is not None:
        logging.root.setLevel(args.verb)
    else:
        logging.root.setLevel(logging.WARNING)

    if ((args.dwd is not None or args.wmo is not None)
            and args.ele is not None):
        parser.print_help()
        logger.critical('-D and -W are mutually exclusive with -e')
        sys.exit(1)
    if ((args.dwd is None and args.wmo is None)
            and args.station is not None):
        parser.print_help()
        logger.critical('-w is only valid with -D or -W')
        sys.exit(1)

    logger.info(os.path.basename(__file__) + ' version: ' + __version__)
    logger.debug(format(args))
    return vars(args)


# -------------------------------------------------------------------------

def main():
    """
    main routine
    """
    args = cli()
    logger.debug("args: %s" % format(args))

    global STORAGE_PATH
    STORAGE_PATH = provide_storage()
    logger.debug("STORAGE_PATH: %s" % STORAGE_PATH)

    ele = None
    if args["dwd"] is not None:
        lat, lon, ele, nam = dwd_stationinfo(args["dwd"], STORAGE_PATH)
    # elif args["wmo"] is not None:
    #     lat, lon, ele, nam = wmo_stationinfo(args["wmo"], path=path)
    elif args["gk"] is not None:
        rechts, hoch = [float(x) for x in args['gk']]
        lon, lat, _ = _tools.gk2ll(rechts, hoch)
    elif args["ut"] is not None:
        rechts, hoch = _tools.ut2gk(*[float(x) for x in args['ut']])
        lon, lat, _ = _tools.gk2ll(rechts, hoch)
    elif args["ll"] is not None:
        lon, lat = [float(x) for x in args['ll']]
        rechts, hoch, _ = _tools.ll2gk(lat, lon)
    else:
        rechts = hoch = lat = lon = 0
    if ele is None and args["ele"] is not None:
        ele = float(args["ele"])
    nam = args['output']
    logger.debug("rechts: %s, hoch: %s" % (rechts, hoch))
    logger.debug("lon: %s, lat: %s" % (lon, lat))
    logging.info('selected position: %.2f %.2f %.0f (%s)' %
                 (lat, lon, ele, format(nam)))
    year = int(args['year'][0])
    logger.debug("year: %s" % year)
    station = args["station"]

    source = args['source'][0]
    if source == "ERA5":
        obs = get_ERA5_weather(lat, lon, year, STORAGE_PATH)
    elif source == "DWD":
        obs = get_DWD_weather(lat, lon, year, station, STORAGE_PATH)
    else:
        raise ValueError("unknown source: %s" % source)

    if OUTPUT_RAW != '':
        raw_name = 'extracted_{:05d}_{:04d}.csv'.format(nam, year)
        logging.info('writing raw data to: %s' % raw_name)
        obs.to_csv(raw_name, float_format='%.2f', index=False, na_rep='-999')


    z0 = obs['fsr'].mean()
    logging.info("roughness length: %6f m" % z0)

    logging.debug('v10')
    obs['v10'] = vdi_3872_6_standard_wind(obs['ff'],
                                        hap=10.0 + 7. * z0,
                                        z0p=z0)

    logging.debug('kms')
    obs['kms'] = klug_manier_scheme(obs['time'], obs['v10'], obs['tcc'],
                                  lat, lon, ele, obs['lmcc'])

    logging.debug('rho')
    obs['rho'] = m.humidity.gas_rho(p=obs['sp'], T=obs['t2m'])
    logging.debug('Tv')
    obs['Tv'] = [m.humidity.Humidity(t=obs['t2m'][i],
                                   p=obs['sp'][i],
                                   td=obs['d2m'][i]).tvirt()
               for i in range(obs['t2m'].size)]
    logging.debug('Lo')
    # calculate u* from "ff" and roughness instead of model-provided "zust"
    obs['ust'] = obs['ff'] * kappa / (np.log((10 + 7 * obs['fsr']) / obs['fsr']))
    obs['Lo'] = obukhov_length(ust=obs['ust'],
                             rho=obs['rho'],
                             Tv=obs['Tv'],
                             H=obs['sshf'],
                             E=obs['slhf'])
    if OUTPUT_RAW != '':
        obs[['time', 'v10', 'rho', 'Tv', 'Lo', 'ust']].to_csv(
            'calculated_era5_{:05d}_{:04d}.csv'.format(station, year),
            float_format='%.2f', index=False, na_rep='-999')

    logging.debug('pts')
    obs['pts'] = pasquill_taylor_scheme(
        obs['time'], obs['ff'], obs['tcc'], lat, lon, obs['cbh'])

    logging.debug('kmc')
    obs['kmc'] = stabilty_class(
        'KM', obs['time'], obs['fsr'], obs['Lo'].copy())

    logging.debug('pgc')
    pg = stabilty_class(
        'PG', obs['time'], obs['fsr'], obs['Lo'])
    # convert to corresponding AK number (class F&G->1)
    obs['pgc'] = [max((1, 7 - x)) for x in pg]

    logging.debug('w')
    w = pd.DataFrame(index=pd.date_range(start=obs.index[0],
                                         end=obs.index[-1],
                                         freq='1h'))

    logging.debug('v')
    obs = obs.drop(columns='time')
    w['time'] = w.index.to_series
    data = w.join(obs, how='left')
    #    print(pd.crosstab(data['kmc'],
    #                      data['pgc'],
    #                      margins = True))
    #
    #    print(skm.classification_report(data['kmc'], data['pgc']))

    for x in ['kms', 'kmc', 'pts', 'pgc']:
        if x in ['all', CLASS_SCHEME]:
            logging.info('writing output file for: ' + x)
            if args.prec:
                df = pd.DataFrame({'FF': data['ff'],
                                   'DD': data['dd'],
                                   'KM': data[x],
                                   'PP': data['tp']},
                                  index=data.index)
                ak = readmet.akterm.DataFile(data=df, z0=obs['fsr'].mean(),
                                             prec=True)
            else:
                df = pd.DataFrame({'FF': data['ff'],
                                   'DD': data['dd'],
                                   'KM': data[x]},
                                  index=data.index)
                ak = readmet.akterm.DataFile(data=df, z0=obs['fsr'].mean())
            outname = ('era5_{:s}_{:04d}_'.format(slugify(nam), year) +
                       x + '.akterm')
            logging.info('writing putput file: %s' % outname)
            ak.write(outname)


# ----------------------------------------------------
# initalize: call main routine
if __name__ == '__main__':
    main()
