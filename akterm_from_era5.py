#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Dec 17 13:36:08 2021

@author: clemens
"""
import numpy as np
import pandas as pd
import datetime as dt
from sklearn import metrics as skm
import logging

import readmet
import metlib as m
kappa = m.constants.kappa
gn = m.constants.gn
_check = m._utils._check

from dispersion import klug_manier_scheme, pasquill_taylor_scheme
from dispersion import stabilty_class, obukhov_length

# ----------------------------------------------------

def spheric_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    Reference:
        https://stackoverflow.com/a/29546836/7657658
    """
    rlat1 = np.radians(lat1)   # deg -> rad
    rlon1 = np.radians(lon1)   # deg -> rad
    rlat2 = np.radians(lat2)   # deg -> rad
    rlon2 = np.radians(lon2)   # deg -> rad

    dlon = rlon2 - rlon1       # rad
    dlat = rlat2 - rlat1       # rad
    a = ( np.sin(dlat / 2.0)**2
        + np.cos(rlat1) * np.cos(rlat2) * np.sin(dlon / 2.0)**2 )
    c = 2 * np.arcsin(np.sqrt(a))
    km = 6371 * c              # km

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

    dims = {}
    dims['lat'] = lp['latitude'][:].data
    dims['lon'] = lp['longitude'][:].data


    # target position in grid coordinates:
    idx = {'lat':-1, 'lon':-1}
    tgt = {'lat':lat, 'lon':lon}
    for l in ['lat', 'lon']:
        dl = np.sort(dims[l])
        for i,v in enumerate(dl):
            ii = i
            if v >= tgt[l]:
                break
        else:
            raise ValueError('target position out of grid')
        idx[l] = ii + (tgt[l]-dl[ii])/(dl[ii+1]-dl[ii])
    logging.info(idx)
    pos=[None,None,None]
    if np.modf(idx['lon'])[0] <= 0.5:
        if np.modf(idx['lat'])[0] <= 0.5:
            # SW corner
            pos[0]=(np.int(idx['lon']    ), np.int(idx['lat']    ))
            pos[1]=(np.int(idx['lon'] + 1), np.int(idx['lat']    ))
            pos[2]=(np.int(idx['lon']    ), np.int(idx['lat'] + 1))
        else:
            # NW corner
            pos[0]=(np.int(idx['lon']    ), np.int(idx['lat']    ))
            pos[1]=(np.int(idx['lon'] + 1), np.int(idx['lat'] + 1))
            pos[2]=(np.int(idx['lon']    ), np.int(idx['lat'] + 1))
    else:
        if np.modf(idx['lat'])[0] <= 0.5:
            # SE corner
            pos[0]=(np.int(idx['lon']    ), np.int(idx['lat']    ))
            pos[1]=(np.int(idx['lon'] + 1), np.int(idx['lat']    ))
            pos[2]=(np.int(idx['lon'] + 1), np.int(idx['lat'] + 1))
        else:
            # NE corner
            pos[0]=(np.int(idx['lon'] + 1), np.int(idx['lat']    ))
            pos[1]=(np.int(idx['lon'] + 1), np.int(idx['lat'] + 1))
            pos[2]=(np.int(idx['lon']    ), np.int(idx['lat'] + 1))


    x=[]
    y=[]
    for pp in pos:
        pi, pj = pp
        plat = dims['lat'][pi]
        plon = dims['lon'][pj]
        logging.info(str((pi,pj,plon,plat)))
        x.append(plon)
        y.append(plat)
    # calculate barycentric weights so that
    # val(x,y) = w1*val(x1,y1) + w2*val(x2,y2) + w3*val(x3,y3)
    # https://en.wikipedia.org/wiki/Barycentric_coordinate_system
    #
    w0 = (((y[1]-y[2])*(lon-x[2]) + (x[2]-x[1])*(lat-y[2])) /
          ((y[1]-y[2])*(x[0]-x[2]) + (x[2]-x[1])*(y[0]-y[2])))
    w1 = (((y[2]-y[0])*(lon-x[2]) + (x[0]-x[2])*(lat-y[2])) /
          ((y[1]-y[2])*(x[0]-x[2]) + (x[2]-x[1])*(y[0]-y[2])))
    w2 = 1 - (w0 + w1)

    values = pd.DataFrame()
    epoch = dt.datetime(1900, 1, 1, 0, 0, tzinfo=dt.timezone.utc)
    values['time'] = pd.to_datetime(
            [epoch + dt.timedelta(hours=int(x)) for x in lp['time']])
    for val in ['u10', 'v10', 'sp', 'zust', 'fsr',
                't2m', 'd2m', 'cbh', 'sshf', 'slhf',
                'lcc', 'mcc', 'tcc']:
        logging.info('interpolating value: %s'%val)
        v=[None,None,None]
        for i in range(3):
            v[i] = pd.Series(lp[val][:, pi, pj].data)
        values[val] = w0*v[0] + w1*v[1] + w2*v[2]
#
#   surface fluxes are in J/hm² down, convert to W/m² up:
    for val in ['sshf', 'slhf']:
        values[val] = values[val] / (-3600.)
#
#    values['ff'] = np.sqrt(values['u10']*values['u10'] +
#                           values['v10']*values['v10'])
#
#   BUT:
#   These '10m wind components' are diagnostic quantities generally computed
#   not by using the roughness length of the tile itself, but instead
#   assuming a roughness length for short grass (=0.03m), the surface over
#   which (by WMO convention) winds should be measured
#   https://confluence.ecmwf.int/display/FUG/9.3+Surface+Wind
#
#   Therefore: u10 = u*/k * ln(z/z0)
    values['ff'] = values['zust']/kappa*np.log(10./values['fsr'])
    values['dd'] = np.rad2deg(np.arctan2((-values['v10']),(-values['u10'])))

    return values

# ----------------------------------------------------
def h_eff(has,z0s):
    z0_vals=[0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1., 1.5, 2]
    href = 250
    d0s = m.wind.displacement_factor*z0s
    ps = np.log((has-d0s)/z0s)/np.log((href-d0s)/z0s)
    ha=[]
    for z0 in z0_vals:
        d0 = m.wind.displacement_factor*z0
        ha.append(d0 + z0*(( href - d0)/z0)**ps)
    return ha

# =======================================================================

def main():
    '''
    main routine
    '''
    lat = 49.75
    lon = 6.66
    ele = 260
    v = read_nc('../data/era5_ak_eu_2018.nc', lat, lon)

#    v = pd.DataFrame(v)
    v.index = v['time']
    v.sort_index(inplace=True)

    v['lmcc'] = np.maximum(v['lcc'], v['mcc'])
    v['kms'] = klug_manier_scheme(v['time'], v['ff'], v['tcc'],
                                  lat, lon, ele, v['lmcc'])

    v['rho'] = v['sp']/(287*v['t2m'])
    v['Tv'] = [m.Humidity(t=v['t2m'][i],
                          p=v['sp'][i],
                          td=v['d2m'][i]).tvirt() for i in range(v['t2m'].size)]
    v['Lo'] = obukhov_length(ust=v['zust'],
                             rho=v['rho'],
                             Tv = v['Tv'],
                             H = v['sshf'],
                             E = v['slhf'])
    v['pts'] = pasquill_taylor_scheme(v['time'], v['ff'], v['tcc'], lat, lon, v['cbh'])

    v['kmc'] = stabilty_class('KM',v['time'], v['fsr'], v['Lo'].copy())

    PG = stabilty_class('PG',v['time'], v['fsr']*0+0.52, v['Lo'])
    # convert to corresponding AK number (class F&G->1)
    v['pgc'] = [max((1,7-x)) for x in PG]

    w = pd.DataFrame(index=pd.date_range(start=v.index[0],
                                         end=v.index[-1],
                                         freq='1h'))


    v = v.drop(columns='time')
    w['time'] = pd.Series(w.index)
    data = w.join(v, how='left')
    print(pd.crosstab(data['kmc'],
                      data['pgc'],
                      margins = True))

    print(skm.classification_report(data['kmc'], data['pgc']))


    for x in ['kms', 'kmc', 'pts', 'pgc']:
        logging.info('writing output file for: '+x)
        df = pd.DataFrame({'FF': data['ff'], 'DD': data['dd'], 'KM': data[x]},
                           index=data.index)
        ak = readmet.akterm.DataFile(data=df, z0=v['fsr'].mean())
        ak.write('out_'+x+'.akterm')

# ----------------------------------------------------
# initalize: call main routine
if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    main()
