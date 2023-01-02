#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Dec 17 13:36:08 2021

@author: clemens
"""
import os
import argparse

import numpy as np
import pandas as pd
import datetime as dt
import logging

import readmet
import meteolib as m

from ._dwd_stationinfo import dwd_stationinfo, slugify

from ._dispersion import klug_manier_scheme, pasquill_taylor_scheme
from ._dispersion import stabilty_class, obukhov_length
from ._dispersion import vdi_3872_6_standard_wind

from ._version import __version__

kappa = m.constants.kappa
gn = m.constants.gn
_check = m._utils._check

# ----------------------------------------------------
# possible defaults: fixed_057 fixed_010 model_mean model_uv10 model_fsr
WIND_VARIANT = os.environ.get('WIND_VARIANT', 'model_uv10')
# possible defaults: barycentric nearest mean
INTER_VARIANT = os.environ.get('INTER_VARIANT', 'barycentric')
# possible values: empty or non-empty string:
OUTPUT_RAW = os.environ.get('OUTPUT_RAW', '')


# ----------------------------------------------------


def spheric_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    Reference:
        https://stackoverflow.com/a/29546836/7657658
    """
    rlat1 = np.radians(lat1)  # deg -> rad
    rlon1 = np.radians(lon1)  # deg -> rad
    rlat2 = np.radians(lat2)  # deg -> rad
    rlon2 = np.radians(lon2)  # deg -> rad

    dlon = rlon2 - rlon1  # rad
    dlat = rlat2 - rlat1  # rad
    a = (np.sin(dlat / 2.0) ** 2 +
         np.cos(rlat1) * np.cos(rlat2) * np.sin(dlon / 2.0) ** 2)
    c = 2 * np.arcsin(np.sqrt(a))
    km = 6371 * c  # km

    return km


# ----------------------------------------------------
def read_nc(ncfile, lat, lon):
    '''
    read ERA5 nc file and interpolate values to position (lat, lon)
        and recalculate 10 wind speed anddirection (ff/dd) using
        actual surface roughness
        values: 'time',
                'u10', 'v10', 'sp', 'zust', 'fsr',
                't2m', 'd2m', 'cbh', 'sshf', 'slhf',
                'lcc', 'mcc', 'tcc',
                'sshf', 'slhf',
                'ff', 'dd'
    '''
    import netCDF4

    lp = netCDF4.Dataset(ncfile)

    dims = {'lat': lp['latitude'][:].data,
            'lon': lp['longitude'][:].data}

    # make sure dims are ascending:
    flip = {'lon': False, 'lat': False}
    for ll in 'lat', 'lon':
        if not np.all(np.diff(dims[ll]) >= 0):
            dims[ll] = np.flip(dims[ll])
            flip[ll] = True

    # target position in grid coordinates:
    #    idx = {'lat':-1, 'lon':-1}
    #    tgt = {'lat':lat, 'lon':lon}
    #    for l in ['lat', 'lon']:
    #        dl = np.sort(dims[l])
    #        for i,v in enumerate(dl):
    #            print(i,v)
    #            ii = i
    #            if v >= tgt[l]:
    #                break
    #        else:
    #            raise ValueError('target position out of grid')
    #        idx[l] = ii + (tgt[l]-dl[ii])/(dl[ii+1]-dl[ii])

    idx = {'lat': -1, 'lon': -1}
    tgt = {'lat': lat, 'lon': lon}
    for ll in ['lat', 'lon']:
        # position of largest dims value smaller than tgt
        ii = np.argmax(np.where(dims[ll] <= tgt[ll], dims[ll], -999))
        # add fraction
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
    logging.info('weights: %6.2f %6.2f %6.2f' % (w0, w1, w2))

    values = pd.DataFrame()
    epoch = dt.datetime(1900, 1, 1, 0, 0, tzinfo=dt.timezone.utc)
    values['time'] = pd.to_datetime(
        [epoch + dt.timedelta(hours=int(x)) for x in lp['time']])
    for val in ['u10', 'v10', 'sp', 'zust', 'fsr',
                't2m', 'd2m', 'cbh', 'sshf', 'slhf',
                'lcc', 'mcc', 'tcc']:
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
        values[val] = values[val] / (-3600.)
    #
    #    values['ff'] = np.sqrt(values['u10']*values['u10'] +
    #                           values['v10']*values['v10'])
    #
    #   BUT:
    #   These '10m wind components' are diagnostic quantities generally
    #   computed not by using the roughness length of the tile itself,
    #   but instead assuming a roughness length for short grass (=0.03m),
    #   the surface over which (by WMO convention) winds should be measured
    #   https://confluence.ecmwf.int/display/FUG/9.3+Surface+Wind
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
def h_eff(has, z0s):
    z0_vals = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1., 1.5, 2]
    href = 250
    d0s = m.wind.displacement_factor * z0s
    ps = np.log((has - d0s) / z0s) / np.log((href - d0s) / z0s)
    ha = []
    for z0 in z0_vals:
        d0 = m.wind.displacement_factor * z0
        ha.append(d0 + z0 * ((href - d0) / z0) ** ps)
    return ha


# =======================================================================

def main():
    '''
    main routine
    '''
    #
    # defaults
    #
    logging_default = logging.INFO
    # defaults
    year = 2018
    station = 5100
    path = '/usr/share/austaltools/data/era'
    #
    # command line args
    #
    parser = argparse.ArgumentParser(description='Climate data aggregation')
    verb = parser.add_mutually_exclusive_group()
    verb.add_argument('--debug', dest='verb', action='store_const',
                      const=logging.DEBUG, help='show informative output')
    verb.add_argument('-v', '--verbose', dest='verb', action='store_const',
                      const=logging.INFO, help='show detailed output')
    parser.add_argument('-y', '--year', dest='year',
                        metavar='YEAR',
                        help='year of interest [%04i]' % year)
    parser.add_argument('-p', '--path',
                        metavar='PATH',
                        help='path to the data files')
    locpars = parser.add_mutually_exclusive_group()
    locpars.add_argument('-s', '--station', dest='station',
                         metavar='NR',
                         help='position by DWD station code [%05i]' % station)
    locpars.add_argument('-l', '--latlon', dest='latlon',
                         metavar='DEGRESS DEGREES',
                         help='position by geographic location')
    parser.add_argument('-n', '--name', dest='name',
                        metavar='NAME',
                        help='name for the position')
    parser.add_argument('-e', '--elevation', dest='ele',
                        metavar='METERS',
                        help='surface elevation only allowed with -l')
    args = parser.parse_args()
    #
    # logging level
    #
    if args.verb is not None:
        logging.root.setLevel(args.verb)
    else:
        logging.root.setLevel(logging_default)
    logging.info(os.path.basename(__file__) + ' version: ' + __version__)
    if args.path is not None:
        path = args.path
    if args.year is not None:
        year = int(args.year)
    if args.station is not None:
        station = int(args.station)
    if args.latlon is not None:
        station = None
    if args.latlon is not None and args.name is None:
        raise parser.error('-n is required if -l is specified')
    if station is not None and args.name is not None:
        logging.warning('-n is given along with -s and ' +
                        'will override station name')
    if args.station and args.ele:
        raise argparse.ArgumentError('-s and -e are mutually exclusive')

    if station is not None:
        lat, lon, ele, nam = dwd_stationinfo(station)
    else:
        lat, lon = [float(x) for x in args.latlon]
        if args.ele:
            ele = float(args.ele)
        else:
            ele = 232.
            logging.warning('-e not given with -l, ' +
                            'assuming median elevation: %f m' % ele)
        station = 0
    if args.name is not None:
        nam = args.name
    logging.info('selected position: %.2f %.2f %.0f (%s)' %
                 (lat, lon, ele, nam))

    ncfile = os.path.join(path, 'era5_ak_eu_%04i.nc' % year)

    v = read_nc(ncfile, lat, lon)
    v.index = v['time']
    v.sort_index(inplace=True)

    if OUTPUT_RAW != '':
        v.to_csv('extracted_era5_{:05d}_{:04d}.csv'.format(station, year),
                 float_format='%.2f', index=False, na_rep='-999')

    logging.debug('lmcc')
    v['lmcc'] = np.maximum(v['lcc'], v['mcc'])
    z0 = v['fsr'].mean()
    logging.info("roughness length: %6f m" % (z0))

    logging.debug('v10')
    v['v10'] = vdi_3872_6_standard_wind(v['ff'],
                                        hap=10.0 + 7. * z0,
                                        z0p=z0)

    logging.debug('kms')
    v['kms'] = klug_manier_scheme(v['time'], v['v10'], v['tcc'],
                                  lat, lon, ele, v['lmcc'])

    logging.debug('rho')
    v['rho'] = m.gas_rho(p=v['sp'], T=v['t2m'])
    logging.debug('Tv')
    v['Tv'] = [m.Humidity(t=v['t2m'][i],
                          p=v['sp'][i],
                          td=v['d2m'][i]).tvirt()
               for i in range(v['t2m'].size)]
    logging.debug('Lo')
    # calculate u* from "ff" and roughness instead of model-provided "zust"
    v['ust'] = v['ff'] * kappa / (np.log((10 + 7 * v['fsr']) / v['fsr']))
    v['Lo'] = obukhov_length(ust=v['ust'],
                             rho=v['rho'],
                             Tv=v['Tv'],
                             H=v['sshf'],
                             E=v['slhf'])
    if OUTPUT_RAW != '':
        v[['time', 'v10', 'rho', 'Tv', 'Lo', 'ust']].to_csv(
            'calculated_era5_{:05d}_{:04d}.csv'.format(station, year),
            float_format='%.2f', index=False, na_rep='-999')

    logging.debug('pts')
    v['pts'] = pasquill_taylor_scheme(
        v['time'], v['ff'], v['tcc'], lat, lon, v['cbh'])

    logging.debug('kmc')
    v['kmc'] = stabilty_class(
        'KM', v['time'], v['fsr'], v['Lo'].copy())

    logging.debug('pgc')
    PG = stabilty_class(
        'PG', v['time'], v['fsr'], v['Lo'])
    # convert to corresponding AK number (class F&G->1)
    v['pgc'] = [max((1, 7 - x)) for x in PG]

    logging.debug('w')
    w = pd.DataFrame(index=pd.date_range(start=v.index[0],
                                         end=v.index[-1],
                                         freq='1h'))

    logging.debug('v')
    v = v.drop(columns='time')
    w['time'] = w.index.to_series
    data = w.join(v, how='left')
    #    print(pd.crosstab(data['kmc'],
    #                      data['pgc'],
    #                      margins = True))
    #
    #    print(skm.classification_report(data['kmc'], data['pgc']))

    for x in ['kms', 'kmc', 'pts', 'pgc']:
        logging.info('writing output file for: ' + x)
        df = pd.DataFrame({'FF': data['ff'],
                           'DD': data['dd'],
                           'KM': data[x]},
                          index=data.index)
        ak = readmet.akterm.DataFile(data=df, z0=v['fsr'].mean())
        outname = ('era5_{:s}_{:04d}_'.format(slugify(nam), year) +
                   x + '.akterm')
        logging.info('writing putput file: %s' % outname)
        ak.write(outname)


# ----------------------------------------------------
# initalize: call main routine
if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    main()
