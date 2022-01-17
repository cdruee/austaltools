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

#kappa = 0.4
#gn = 9.81
#def _to_K(Tv, Kelvin=None):
#  if Kelvin is None :
#    if Tv < 200:
#      return Tv + 273.15
#    else:
#      return Tv
#  elif Kelvin == True:
#    return Tv
#  else:
#    return Tv + 273.15
import metlib as m
#from m.constants import kappa, gn
kappa = m.constants.kappa
gn = m.constants.gn
#from m.temperature import _to_K
_check = m._utils._check

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
    read nc file and return:
        dimensions:
            lat
            lon
        values:
            temperature in °C
            pressure-level height in gpdm
            u in m/s
            v in m/s
    '''
    import netCDF4

    lp = netCDF4.Dataset(ncfile)

    dims = {}
    dims['lat'] = lp['latitude'][:].data
    dims['lon'] = lp['longitude'][:].data

    arr={}
    arr['lat'] =  np.repeat(
            np.expand_dims(dims['lat'],axis=1),
            dims['lat'].size,
            axis=1)
    arr['lon'] =  np.repeat(
            np.expand_dims(dims['lon'],axis=0),
            dims['lat'].size,
            axis=0)

    arr['dist'] = np.empty(arr['lat'].shape)
    ni, nj = arr['dist'].shape
    for i in range(ni):
        for j in range(nj):
              arr['dist'][i][j] = spheric_distance(
                    lat,
                    lon,
                    arr['lat'][i][j],
                    arr['lon'][i][j])

    pos = np.unravel_index(np.argmin(arr['dist'], axis=None),
                           arr['dist'].shape)
    print(pos)
    pi, pj = pos
    plat = dims['lat'][pi]
    plon = dims['lon'][pj]
    print((pi,pj),(plon,plat))

#    from matplotlib import pyplot as plt
#    plt.imshow(arr['dist'])

    values = pd.DataFrame()
    epoch = dt.datetime(1900, 1, 1, 0, 0, tzinfo=dt.timezone.utc)
    values['time'] = pd.to_datetime(
            [epoch + dt.timedelta(hours=int(x)) for x in lp['time']])
    for val in ['lcc', 'mcc', 'tcc']:
        values[val] = lp[val][:, pi, pj].data * 8.           # 1 -> octa
    for val in ['sshf', 'slhf']:
        values[val] = lp[val][:, pi, pj].data / -3600.       # -J/hm² -> W/m²
    for val in ['u10', 'v10', 'sp', 'zust', 'fsr',
                't2m', 'd2m']:
        values[val] = lp[val][:, pi, pj].data

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

    return values

# ----------------------------------------------------

def sun_rise_set(time: dt.datetime, lat):
    # if arguments are scalars, convert to arrays
    try:
        _ = len(time)
        scalar = False
    except TypeError:
        time = np.array([time])
        scalar = True
     #
    # Sonnenstand
    B = np.pi*lat/180.
    T = np.array([x.timetuple()[7] for x in time])      # day of year
    deklination = 0.4095 * np.sin(0.016906 * (T - 80.086))
    zeitdifferenz = 12 * np.arccos((np.sin(-0.0145)
        - np.sin(B) * np.sin(deklination))/
                                        (np.cos(B)*np.cos(deklination)))/np.pi
    zeitgleichung = -0.171 * np.sin(0.0337 * np.sin((0.0337 * T + 0.465)
        - 0.1299 * np.sin(0.01787 * T - 0.168)))
    #
    # auf/unter UTC
    s_rise = 12. - zeitdifferenz - zeitgleichung
    s_set  = 12. + zeitdifferenz - zeitgleichung

    if scalar:
        s_rise = s_rise[0]
        s_set = s_set[0]
    return s_rise,s_set

# ----------------------------------------------------

def klug_manier_scheme(time: dt.datetime, ff, N_tot, lat, lon, N_low=None):
    # Einlesen
    monat = np.array([x.month for x in time])
    stund = np.array([x.hour for x in time])
    tcc  = N_tot/8.                               # octa -> 1
    if N_low is None:
        lcc = tcc                             # 1
    else:
        lcc = N_low/8.                        # octa -> 1

    # auf/unter UTC
    print(dt.datetime.now())
    s_auf,_,s_unter = m.radiation.fast_rise_transit_set(time, lat, lon)
    print(dt.datetime.now())
    #
    # Ausbreitungsklassen
    #
    k = {'I': 1,
         'II': 2,
         'III1': 3,
         'III2': 4,
         'IV': 5,
         'V': 6}
    #
    # Tabelle A.1
    #
    # Wind-          |  Gesamtbedeckung in Achten  |
    # geschwindigkeit| für Nacht |     für Tages   |
    # in 10m Höhe    | stunden**)|     stunden**)  |
    # in m/s         | 0/8 | 7/8 | 0/8 | 3/8 | 6/8 |
    #                | bis | bis | bis | bis | bis |
    #                | 6/8 | 8/8 | 2/8 | 5/8 | 8/8 |
    # 1 und darunter |  I  | II  | IV  | IV  | IV  |
    # 1,5 und 2      |  I  | II  | IV  | IV  |III2 |
    # 2,5 und 3      | II  |III1 | IV  | IV  |III2 |
    # 3,5 und 4      |III1 |III1 | IV  |III2 |III2 |
    # 4,5 und darüber|III1 |III1 |III2 |III1 |III1 |
    #
    # *) Bei den Fällen mit einer Gesamtbedeckung, die ausschließ-
    # lich aus hohen Wolken (Cirren) besteht, ist von einer um 3/8
    # erniedrigten Gesamtbedeckung auszugehen.
    for i,_ in enumerate(time):
        if lcc[i] < 0.125:
            tcc[i] = np.max((0., tcc[i] - 0.375))
    #
    # K_N for night conditions
    kn = np.zeros(stund.shape)
    # K_T for day conditions
    kt = np.zeros(stund.shape)
    for i,_ in enumerate(time):
        # K_N for night conditions
        if tcc[i] <= 0.75:
           if ff[i] <= 2.:
               kn[i] = k['I']
           elif ff[i] <= 3:
               kn[i] = k['II']
           else:  # ff[i] > 3
               kn[i] = k['III1']
        else:
           if ff[i] <= 2.:
               kn[i] = k['II']
           else: # ff[i] > 2)
               kn[i] = k['III1']
        # K_T for day conditions
        if tcc[i] <= 0.25:
           if ff[i] <= 4:
               kt[i] = k['IV']
           else: # ff[i] > 4:
               kt[i] = k['III2']
        elif tcc[i] < 0.75:
           if ff[i] <= 3:
               kt[i] = k['IV']
           elif ff[i] <= 4:
               kt[i] = k['III2']
           else: # ff[i] > 4
               kt[i] = k['III1']
        else: # tcc[i] >= 0.75
           if ff[i] <= 1:
               kt[i] = k['IV']
           elif ff[i] <= 4:
               kt[i] = k['III2']
           else: # ff[i] > 4:
               kt[i] = k['III1']
    #
    # **)  Für die Abgrenzung sind Sonnenaufgang und -untergang
    #      {MEZ) maßgebend. Die Ausbreitungsklasse für Nachtstunden
    #      wird noch für die auf den Sonnenaufgang folgende volle Stunde
    #      eingesetzt.
    #
    km = np.zeros(stund.shape)
    for i,_ in enumerate(time):
        if stund[i] <= np.ceil(s_auf[i]):
            km[i] = kn[i]
        elif stund[i] <= s_unter[i]:
            km[i] = kt[i]
        else:
            km[i] = kn[i]
    #
    # besondere Ausbreitungsverhaeltnisse
    #
    for i,_ in enumerate(time):
        #
        # Teil a)
        # Ergeben sich für die Monate Juni bis August und
        # die Stunden von 10.00 bis 16.00 MEZ  Ausbrei-
        # tungsklassen unter V, so ist für eine Gesamtbedek-
        # kung von nicht mehr als °/, oder eine Gesamtbe-
        # deckung von 6/8 und Windgeschwindigkeiten
        # unter 2,5 m/s die nächsthöhere Ausbreitungs-
        # klasse  einzusetzen. Für die Stunden von 12.00 bis
        # 15.00 MEZ bei Bedeckung von nicht mehr als 5/8
        # ist, unter Beachtung von Satz 1, die nächsthöhere
        # Ausbreitungsklasse - im Fall der Klasse IV die
        # Klasse V - einzusetzen.
        #
        if monat[i] in [6, 7, 8]:
            if stund[i] >=  10 and stund[i] < 16 and km[i] < k['V']:
                if tcc[i] <= 0.75:
                    km[i] = km[i] + 1
                elif tcc[i] <= 0.875 and ff[i] < 2.5:
                    km[i] = km[i] + 1
            if stund[i] >= 12 and stund[i] < 15 and km[i] < k['V']:
                if tcc[i] <= 0.625:
                    km[i] = km[i] + 1
        #
        # Teil b)
        # Für die Monate Mai und September ist für die
        # Stunden von 11.00 bis 15.00 MEZ und eine Be-
        # deckung von nicht mehr als 6/8 die nächsthöhere
        # Ausbreitungsklasse - im Fall der Klasse IV die
        # Klasse V - einzusetzen.
        #
        elif monat[i] in [5, 9]:
            if stund[i] >= 11 and stund[i] < 15:
                if tcc[i] <= 0.75:
                    km[i] = km[i] + 1
        #
        # Teil c)
        # Für jede volle Stunde der Zeiträume von 1 Stunde
        # bis 3 Stunden nach Sonnenaufgang (SA+1 bis
        # SA+3) und von 2 Stunden vor bis 1 Stunde nach
        # Sonnenuntergang (SU—2 bis SU+1) werden die
        # Ausbreitungsklassen nach Tabelle A2 sowohl
        # nach den Spalten für Nachtstunden (K_N) als auch
        # nach den Spalten für Tagstunden (K) bestimnt.
        # Tabelle A2 enthält alle möglichen Kombinatio-
        # nen der Ausbreitungsklassen K_N und K_T und gibt
        # welche statt dessen für diean, Ausbreitungsklasse
        # Ausbreitungsrechnung zu verwenden ist. Geht
        # z.B. die Sonne um 6.25 MEZ auf, dann ist für
        # SA+1 bis SA+2 der Wert für die Stunden von
        # 7.25 bis 8.25 MEZ einzusetzen. Bei stündlicher
        # Zeitfolge mit Beobachtungen zur vollen Stunde
        # ist die Bestimmung der Ausbreitungsklasse für
        # 8.00 MEZ gültig
        #
        # Tabelle A2. Ausbreitungsklassen
        # | KN | KT | SA+1 | SA+2 | SU-2 | SU-1 | SU   |
        # | KN | KT | bis  | bis  | bis  | bis  | bis  |
        # |    |    | SA+2 | SA+3 | SU-1 | SU   | SU+1 |
        # | I  | IV |I(II)*|  II  |  II |II(I)**|I(II)*|
        # | I  |III2|  II  |  II  | III1 | III1 |I(II)*|
        # | II | IV |  II  | III1 | III1 |  II  |  II  |
        # | II |III2| III2 | III1 | III1 | III1 |  II  |
        # |III1| IV | III1 | III2 | III2 | III1 | III1 |
        # |III1|III2| III1 | III1 | III2 | III2 | III1 |
        # |III1|III1| III1 | III1 | III1 | III1 | III1 |
        #
        # *) Für die Monate  März bis November und Windgeschwindig-
        #    keiten über 1 m/s ist der Wert in der Klammer einzusetzen.
        # **) Für die Monate Januar, Februar und Dezember, Windge-
        #    schwindigkeiten bis 1 m/s und Gesamtbedeckung bis 6/8 ist
        #    der Wert in der Klammer einzusetzen.
        #
        if kn[i] == k['I'] and kt[i] == k['IV']:
            if stund[i] >= s_auf[i] + 1. and stund[i] < s_auf[i] + 2.:
                # Fussnote *)
                if (monat[i] in [3,4,5,6,7,8,9,10,11] and ff[i] > 1):
                        km[i]= k['II']
                else:
                    km[i]= k['I']
            elif stund[i] >= s_auf[i] + 2. and stund[i] < s_auf[i] + 3.:
                km[i]= k['II']
            elif stund[i] >= s_unter[i] - 2. and stund[i] < s_unter[i] -1.:
                km[i]= k['II']
            elif stund[i] >= s_unter[i] - 1. and stund[i] < s_unter[i] :
                # Fussnote **)
                if monat[i] in [1,2,12] and ff[i] <= 1 and tcc[i] <= 0.75:
                    km[i]= k['I']
                else:
                    km[i]= k['II']
            elif stund[i] >= s_unter[i] and stund[i] < s_unter[i] + 1.:
                # Fussnote *)
                if (monat[i] in [3,4,5,6,7,8,9,10,11] and ff[i] > 1):
                        km[i]= k['II']
                else:
                    km[i] = k['I']
        elif kn[i] == k['I'] and kt[i] == k['III2']:
            if stund[i] >= s_auf[i] + 1. and stund[i] < s_auf[i] + 2.:
                km[i]= k['II']
            elif stund[i] >= s_auf[i] + 2. and stund[i] < s_auf[i] + 3.:
                km[i]= k['II']
            elif stund[i] >= s_unter[i] - 2. and stund[i] < s_unter[i] -1.:
                km[i]= k['III1']
            elif stund[i] >= s_unter[i] - 1. and stund[i] < s_unter[i] :
                km[i]= k['III1']
            elif stund[i] >= s_unter[i] and stund[i] < s_unter[i] + 1.:
                # Fussnote *)
                if (monat[i] in [3,4,5,6,7,8,9,10,11] and ff[i] > 1):
                        km[i]= k['II']
                else:
                    km[i]= k['I']
        elif kn[i] == k['II'] and kt[i] == k['IV']:
            if stund[i] >= s_auf[i] + 1. and stund[i] < s_auf[i] + 2.:
                km[i]= k['II']
            elif stund[i] >= s_auf[i] + 2. and stund[i] < s_auf[i] + 3.:
                km[i]= k['III1']
            elif stund[i] >= s_unter[i] - 2. and stund[i] < s_unter[i] -1.:
                km[i]= k['III1']
            elif stund[i] >= s_unter[i] - 1. and stund[i] < s_unter[i] :
                km[i]= k['II']
            elif stund[i] >= s_unter[i] and stund[i] < s_unter[i] + 1.:
                km[i]= k['II']
        elif kn[i] == k['II'] and kt[i] == k['III2']:
            if stund[i] >= s_auf[i] + 1. and stund[i] < s_auf[i] + 2.:
                km[i]= k['III1']
            elif stund[i] >= s_auf[i] + 2. and stund[i] < s_auf[i] + 3.:
                km[i]= k['III1']
            elif stund[i] >= s_unter[i] - 2. and stund[i] < s_unter[i] -1.:
                km[i]= k['III1']
            elif stund[i] >= s_unter[i] - 1. and stund[i] < s_unter[i] :
                km[i]= k['III1']
            elif stund[i] >= s_unter[i] and stund[i] < s_unter[i] + 1.:
                km[i]= k['II']
        elif kn[i] == k['III1'] and kt[i] == k['IV']:
            if stund[i] >= s_auf[i] + 1. and stund[i] < s_auf[i] + 2.:
                km[i]= k['III1']
            elif stund[i] >= s_auf[i] + 2. and stund[i] < s_auf[i] + 3.:
                km[i]= k['III2']
            elif stund[i] >= s_unter[i] - 2. and stund[i] < s_unter[i] -1.:
                km[i]= k['III2']
            elif stund[i] >= s_unter[i] - 1. and stund[i] < s_unter[i] :
                km[i]= k['III1']
            elif stund[i] >= s_unter[i] and stund[i] < s_unter[i] + 1.:
                km[i]= k['III1']
        elif kn[i] == k['III1'] and kt[i] == k['III2']:
            if stund[i] >= s_auf[i] + 1. and stund[i] < s_auf[i] + 2.:
                km[i]= k['III1']
            elif stund[i] >= s_auf[i] + 2. and stund[i] < s_auf[i] + 3.:
                km[i]= k['III1']
            elif stund[i] >= s_unter[i] - 2. and stund[i] < s_unter[i] -1.:
                km[i]= k['III2']
            elif stund[i] >= s_unter[i] - 1. and stund[i] < s_unter[i] :
                km[i]= k['III2']
            elif stund[i] >= s_unter[i] and stund[i] < s_unter[i] + 1.:
                km[i]= k['III1']
        elif kn[i] == k['III1'] and kt[i] == k['III1']:
            if stund[i] >= s_auf[i] + 1. and stund[i] < s_auf[i] + 2.:
                km[i]= k['III1']
            elif stund[i] >= s_auf[i] + 2. and stund[i] < s_auf[i] + 3.:
                km[i]= k['III1']
            elif stund[i] >= s_unter[i] - 2. and stund[i] < s_unter[i] -1.:
                km[i]= k['III1']
            elif stund[i] >= s_unter[i] - 1. and stund[i] < s_unter[i] :
                km[i]= k['III1']
            elif stund[i] >= s_unter[i] and stund[i] < s_unter[i] + 1.:
                km[i]= k['III1']
        #
        #Teil d)
        #  Für die Monate Dezember, Januar und Februar
        # ist die Ausbreitungsklasse IV durch die Ausbrei-
        # tungsklasse III2 zu ersetzen.
        #
        if monat[i] in [1, 2, 12]:
            if km[i] == k['IV']:
                km[i] = k['III1']
    #
    # Fälle, bei denen keine Ausbreitungsklasse bestimmt
    # werden kann, werden bei Windgeschwindigkeiten
    # unter 2 m/s der Ausbreitungsklasse I, von 2,5 bis
    # 3 m/s der Klasse II und von mehr als 3,5 m/s der
    # Klasse III1 zugeordnet.
    for i,_ in enumerate(time):
        if km[i] == 0:
            if ff[i] < 2.0:
                km[i] = k['I']
            elif ff[i] <= 3.5:
                # here we include 2.0 ... 2.5 m/s as
                # else it would remain undefinded
                km[i] = k['II']
            else:
                km[i] = k['III1']

    return km

# ----------------------------------------------------

def obukhov_length(ust, rho, Tv, H, E, Kelvin=True):
  '''
  The class LogWind represents a logarithmic wind profile that
  my be described and requested in any possible compination of
  parameters.

  :param ust: friction velocity in m/s (float).
  :param rho: density of air kg/m^3 (float).
  :param Tv:  virtual temperature in K of C, depending on `Kelvin`.
  :param H:   surface sensible heat flux density in W/m^2 (float).
  :param E:   surface latent heat flux density in W/m^2 (float).
  :param Kelvin: (optional) if ``False``, all temperatures are assumed to
    be Kelvin. If ``False``, all temperatures are assumed to be Celsius.
    If missing of ``None``, unit  temperatures are autodetected. Defaults to
    ``None``.

  '''
  L = - (ust**3 * Tv * rho * 1004.) / (kappa * gn * (H+0.06*E))

  return L

# ----------------------------------------------------

def klug_manier_stability_class(time,z0,L):

    # if arguments are scalars, convert to arrays
    try:
        n = len(time)
        scalar = False
    except TypeError:
        time = np.array([time])
        z0 = np.array([z0])
        L =  np.array([L])
        n = len(time)
        scalar = True
    KM_class = np.zeros(time.shape)
    for i in range(n):

        # Technische Anleitung zur Reinhaltung der Luft – TA Luft)
        # Vom 24. Juli 2002
        # S. 224
        #
        # Tabelle 17: Bestimmung der Monin–Obukhov–Länge LM
        # | Ausbreitungsklasse | Rauhigkeitslänge z0 in m
        # | nach Klug/Manier   | 0,01 0,02 0,05 0,10 0,20 0,50 1,00 1,50 2,00
        # | I (sehr stabil)    |    7    9   13   17   24   40   65   90  118
        # | II (stabil)        |   25   31   44   60   83  139  223  310  406
        # | III/1 (indifferent)|99999 99999 99999 99999 99999 99999 99999 99999 99999
        # | III/2 (indifferent)|  -25  -32  -45  -60  -81 -130 -196 -260 -326
        # | IV (labil)         |  -10  -13  -19  -25  -34  -55  -83 -110 -137
        # | V (sehr labil)     |  -4    -5  -7   -10  -14  -22  -34  -45  -56
        #
        if z0[i] <= 0.013:
            divs = [ -14.3,  -5.7, 0.,  10.9,  50.0]
        elif z0[i] <= 0.028:
            divs = [ -18.5,  -7.2, 0.,  14.0,  62.0]
        elif z0[i] <= 0.066:
            divs = [ -26.7, -10.2, 0.,  20.0,  88.0]
        elif z0[i] <= 0.133:
            divs = [ -35.3, -14.3, 0.,  26.5, 119.9]
        elif z0[i] <= 0.28:
            divs = [ -47.7, -19.8, 0.,  37.2, 165.9]
        elif z0[i] <= 0.66:
            divs = [ -77.3, -31.4, 0.,  62.1, 277.6]
        elif z0[i] <= 1.20:
            divs = [-116.6, -48.2, 0., 100.7, 445.0]
        elif z0[i] <= 1.71:
            divs = [-154.6, -63.9, 0., 139.5, 618.1]
        else:
            divs = [-192.9, -79.5, 0., 182.9, 808.7]
        #
        k = [4, 5, 6, 1, 2]
        for j,d in enumerate(divs):
           if L[i] <= d:
               KM_class[i] = k[j]
               break
        else:
            KM_class[i] = 3

    if scalar:
        if len(time)>1: raise ValueError
        KM_class = KM_class[0]
    return KM_class

# ----------------------------------------------------

def pasquill_turner_scheme(time: dt.datetime, ff, N_tot, lat, N_low=None):
    # if arguments are scalars, convert to arrays
    try:
        n = len(time)
        scalar = False
    except TypeError:
        time = np.array([time])
        ff = np.array([ff])
        N_tot =  np.array([N_tot])
        if N_low is not None:
            N_low =  np.array([N_low])
        n = len(time)
        scalar = True

    # auf/unter UTC
    s_rise,s_set = sun_rise_set(time,lat)
    hour = np.array([x.hour for x in time])
    class_number={'A': 1,
                  'B': 2,
                  'C': 3,
                  'D': 4,
                  'E': 5,
                  'F': 6,}
    pt = np.zeros(time.shape)
    for i in range(n):
        rad_index = None
        #
        #1. If the total cloud1 cover is 10/10 and the ceiling is less than
        #   7000 feet, use net radiation index equal to 0 (whether day or night).
        if N_tot > 0.9 and N_low >= 0.125:
            rad_index = 0

        #2. For nighttime: (from one hour before sunset to one hour after sunrise):
        #  (a) If total cloud cover < 4/10, use net radiation index equal to -2.
        #  (b) If total cloud cover > 4/10, use net radiation index equal to -1.
        elif hour[i] >= sun_rise[i] - 1 and hour[i] >= sun_rise[i] + 1:
            if N <= 0.4:
                rad_index = -2
            else:
                rad_index = -1
        #
        #3. For daytime:
        else:

        #  (a) Determine the insolation class number as a function of solar
        #      altitude from Table 6-5.

        #  (b) If total cloud cover <5/10, use the net radiation index in
        #      Table 6-4 corresponding to the isolation class number.
        #  (c) If cloud cover >5/10, modify the insolation class number using
        #      the following six steps.
        #     (1) Ceiling <7000 ft, subtract 2.
        #     (2) Ceiling >7000 ft but <16000 ft, subtract 1.
        #     (3) total cloud cover equal 10/10, subtract 1.
        #         (This will only apply to ceilings >7000 ft
        #          since cases with 10/10 coverage below 7000 ft
        #          are considered in item 1 above.)
        #     (4) If insolation class number has not been modified by
        #         steps (1), (2), or (3) above, assume modified
        #         class number equal to insolation class number.
        #     (5) If modified insolation class number is less than 1,
        #         let it equal 1.
        #     (6) Use the net radiation index in Table 6-4 corresponding
        #         to the modified insolation class number.
            pass
    return pt

def turners_key(ff,NRI):
    ff = _check('ff', ff, 'float', ge=0.)
    NRI = _check('NRI', NRI, 'int', ge=-2, le=4)
    #                 Table 6-4
    #
    #  Turner's Key to the P-G Stability Categories
    #  Wind Speed      Net Radiation Index
    #  (knots) (m/s)    4   3   2   1   0  -1  -2
    #  0,1    0 - 0.7   1   1   2   3   4   6   7
    #  2,3  0.8 - 1.8   1   2   2   3   4   6   7
    #  4,5  1.9 - 2.8   1   2   3   4   4   5   6
    #  6    2.9 - 3.3   2   2   3   4   4   5   6
    #  7    3.4 - 3.8   2   2   3   4   4   4   5
    #  8,9  3.9 - 4.8   2   3   3   4   4   4   5
    #  10   4.9 - 5.4   3   3   4   4   4   4   5
    #  11   5.5 - 5.9   3   3   4   4   4   4   4
    # >12   6.0 -       3   4   4   4   4   4   4
    #
    # 1) select wind-speed class:
    if ff <= 0.7:
        vals = [1, 1, 2, 3, 4, 6, 7]
    elif ff <= 1.8:
        vals = [1, 2, 2, 3, 4, 6, 7]
    elif ff <= 2.8:
        vals = [1, 2, 3, 4, 4, 5, 6]
    elif ff <= 3.3:
        vals = [2, 2, 3, 4, 4, 5, 6]
    elif ff <= 3.8:
        vals = [2, 2, 3, 4, 4, 4, 5]
    elif ff <= 4.8:
        vals = [2, 3, 3, 4, 4, 4, 5]
    elif ff <= 5.4:
        vals = [3, 3, 4, 4, 4, 4, 5]
    elif ff <= 5.9:
        vals = [3, 3, 4, 4, 4, 4, 4]
    else:
        vals = [3, 4, 4, 4, 4, 4, 4]
    #
    # 2) select net-radiation index:
    ri = [4, 3, 2, 1, 0, -1 ,-2]
    for i,ri in enumerate(ri):
        if NRI == ri:
            key = vals[i]
            break
    else:
        raise ValueError('illegal NRI value: %i'%NRI)
    return key

#def taylor_insolation_class(time, lat, lon)

        #                 Table 6-5
        #  Insolation Class as a Function of Solar Altitude
        #  Solar Altitude X (degrees)   Insolation   Insolation Class Number
        #    60 < X                      strong       4
        #    35 < X <= 60                moderate     3
        #    15 < X <= 35                slight       2
        #         X <= 15                weak         1


# ----------------------------------------------------

def main():
    '''
    main routine
    '''
    lat = 49.9
    lon = 6.07
    v = read_nc('era5_cc_eu_2018.nc', lat, lon)
    v['lmcc'] = np.maximum(v['lcc'], v['mcc'])
    v['kms'] = klug_manier_scheme(v['time'], v['ff'], v['tcc'], lat, lon, v['lmcc'])

    v['rho'] = v['sp']/(287*v['t2m'])
    v['Tv'] = [m.Humidity(t=v['t2m'][i],
                          p=v['sp'][i],
                          td=v['d2m'][i]).tvirt() for i in range(v['t2m'].size)]
    v['Lo'] = obukhov_length(ust=v['zust'],
                             rho=v['rho'],
                             Tv = v['Tv'],
                             H = v['sshf'],
                             E = v['slhf'])
    v['kmc'] = klug_manier_stability_class(v['time'], v['fsr'], v['Lo'])

    import pandas as pd
    data = pd.DataFrame(v)
    print(pd.crosstab(data['kms'],
                      data['kmc'],
                      margins = True))

    print(skm.classification_report(data['kmc'], data['kms']))

    from matplotlib import pyplot as plt
    fig, ax = plt.subplots()
    ax.plot(v['time'], v['kmc'], label='MOL class')
    ax.plot(v['time'], v['kms'], label='K/M')
#
#    ax.plot(v['time'], v['t2m'], label='dry')
#    ax.plot(v['time'], v['d2m'], label='wet')
#    ax.plot(v['time'], v['Tv'], label='virt')
#
#    ax.plot(v['time'], v['rho'], label='rho')
#
#    ax.plot(v['time'], v['sp'], label='p_sfc')
#
#    ax.plot(v['time'], v['zust'], label='u*')
#
#    ax.plot(v['time'], v['ff'], label='ff')
#    ax.plot(v['time'], v['zust']/0.4*np.log(10./v['fsr']) , label='u_neutral')
#
#    ax.plot(v['time'], v['sshf'], label='H')
#    ax.plot(v['time'], v['slhf'], label='E')
#    ax.plot(v['time'], (v['sshf']+0.06*v['slhf']), label='H_v')
#
#    ax.plot(v['time'], 2/v['Lm'], label='zeta')
#    ax.set_ylim(-2,3)
#
#    ax.plot(v['time'], v['Lm'], label='L*')
#    ax.set_ylim(-300,200)
#    plt.hlines([ -77.3, -31.4, 0.,  62.1, 277.6],
#               dt.datetime(2018, 6, 1),
#               dt.datetime(2018, 6, 6))
#
#    ax.plot(v['time'], v['fsr'], label='z_0')
#
#    ax.plot(v['time'], v['tcc'], label='cloud total')
#    ax.plot(v['time'], v['lmcc'], label='cloud med/low')
#
#    ax.set_xlim(dt.datetime(2018, 6, 1),
#                dt.datetime(2018, 6, 6))
#    ax.set_xlim(dt.datetime(2018, 6, 24),
#                dt.datetime(2018, 6, 30))
    ax.set_xlim(dt.datetime(2018, 10, 1),
                dt.datetime(2018, 10, 6))
    plt.legend(loc="upper left")
    plt.show()

#    from datetime import datetime as dt
#    tupl = tuple('era_eu_2018' %H:%M').timetuple())[0:5]
#
#    dims, values = read_nc(tupl, pp)
#    plot_ztw(dims, values, tupl, arrow_dist, file)


# ----------------------------------------------------
# initalize: call main routine
if __name__ == '__main__':
    logging.getLogger().setLevel(logging.INFO)
    main()
