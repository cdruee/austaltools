#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Feb  3 19:20:42 2022

@author: clemens
"""
import os
import unicodedata
import re
import argparse
import pandas as pd
import logging

try:
    from . import _tools
except ImportError:
    import _tools

LOGGING_DEFAULT = logging.WARNING
_PATH = '/localdata/druee/datensaetze/dwd_opendata/observations_germany/'


def dwd_metadata(station, time1, time2, param, path=_PATH):
    time1 = pd.to_datetime(time1, utc=True)
    time2 = pd.to_datetime(time2, utc=True)
    if time2 < time1:
        raise ValueError('time2 mut be equal or after time1')
    sstr = '{:05d}'.format(station)
    stninfo = os.path.join(path, 'metadata_' + sstr + '.csv')
    logging.info("read station info from: %s" % stninfo)
    md = pd.read_csv(stninfo, header=0)
    md.index = pd.to_datetime(md['time'])
    if param not in md.columns:
        raise ValueError('parameter not found: %s' % param)
    # get all info in time range:
    value = pd.Series()
    for i, v in md[param].iteritems():
        if i < time1:
            value[time1] = v
        elif time1 <= i < time2:
            value[i] = v
        else:
            value[time2] = v
            break
    # reduce lines giving no new info:
    new = []
    for i, v in value.iteritems():
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


def dwd_stationinfo(station, path=_PATH, pos_lat=None, pos_lon=None):
    if station is not None:
        sstr = '{:05d}'.format(station)
        if pos_lat is not None and pos_lon is not None:
            raise ValueError('lat and lon must be None ' +
                             'unless station is None')
    else:
        sstr = None
    stninfo = os.path.join(path, 'TU_Stundenwerte_Beschreibung_Stationen.txt')
    logging.info("read station info from: %s" % stninfo)
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
    logging.debug("station name: %s" % nam)
    if station is None:
        return lat, lon, ele, nam, int(sid)
    else:
        return lat, lon, ele, nam


def slugify(value, allow_unicode=False):
    """
    Taken from
    https://github.com/django/django/blob/master/django/utils/text.py
    Convert to ASCII if 'allow_unicode' is False. Convert spaces or
    repeated dashes to single dashes. Remove characters that aren't
    alphanumerics, underscores, or hyphens. Convert to lowercase.
    Also strip leading and trailing whitespace, dashes, and underscores.
    """
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize('NFKC', value)
    else:
        value = unicodedata.normalize('NFKD', value).encode(
            'ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    return re.sub(r'[-\s]+', '-', value).strip('-_')

# -------------------------------------------------------------------------

def pressure_reduction_dwd(p,h,fastred=FALSE)
        #
        # DWD-Formel Druckreduktion
        #
        # p = ps *EXP(gn*h/(R*(t+m.Tzero+C*e+gam*h/2)))
        #
        # t momentane Stationstemperatur in °C
        # e momentaner Stationsdampfdruck in hPa (evtl. zu vernachlässigen)
        # ps momentaner Stationsluftdruck in hPa (=QFE)
        # h Stationshöhe in Metern (oder besser geopotentiellen Metern)
        #
        gam = 0.0065  # K/gpm
        C = 0.11  # K/hPa DWD-Beiwert für die Berücksichtigung der Feuchte,
        #           etwas stationsabhängig aber irrelevant
        h = stationinfo['ele']
        #
        if not fastred:
            for i in range(0, len(dat)):
                if (~np.isnan(dat['P'][i]) or np.isnan(dat['P0'][i])):
                    continue
                t = dat['TT_TU'][i]
                e = (
                    m.humidity.esat_w(dat['TT_TU'][i],
                                      Kelvin=False, hPa=True) *
                    dat['RF_TU'][i] / 100.
                    )
                dat.iloc[i, dat.columns.get_loc('P')] = (
                    dat['P0'][i]/np.exp(
                        m.constants.gn * h / (
                            m.constants.R * (t + m.constants.Tzero +
                                             C * e + gam*h/2)))
                    )
        else:
            t = np.nanmean(dat['TT_TU'])
            e = m.humidity.esat_w(t, Kelvin=False, hPa=True) * \
                np.nanmean(dat['RF_TU']) / 100.
            redfact = np.exp(m.constants.gn*h/(m.constants.R *
                             (t+m.constants.Tzero+C*e+gam*h/2)))
            dat['P'] = dat['P'].where(np.isnan(dat['P0']), dat['P0']/redfact)


# ----------------------------------------------------
# initalize: call main routine
if __name__ == '__main__':
    #
    # command line args
    #
    parser = argparse.ArgumentParser(description='Get DWD station info')
    verb = parser.add_mutually_exclusive_group()
    verb.add_argument('--debug', dest='verb', action='store_const',
                      const=logging.DEBUG, help='show informative output')
    verb.add_argument('-v', '--verbose', dest='verb', action='store_const',
                      const=logging.INFO, help='show detailed output')
    parser.add_argument('-f', '--slugify', action='store_true',
                        help='return station name as file name component')
    parser.add_argument('station', metavar='NUMBER',
                        help='position by DWD station code')
    parser.add_argument('-p', '--path', metavar='PATH',
                        help='path to the data files')
    args = parser.parse_args()
    #
    # logging level
    #
    if args.verb is not None:
        logging.root.setLevel(args.verb)
    else:
        logging.root.setLevel(LOGGING_DEFAULT)
    if args.station is not None:
        station = int(args.station)
    if args.path is not None:
        path = args.path
    out = dwd_stationinfo(station, path=_PATH)
    if args.slugify:
        print(slugify(out[3]))
    else:
        print(*out)
