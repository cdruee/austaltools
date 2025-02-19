#!/bin/env python3
# -*- coding: utf-8 -*-
"""
This contains functions that provide metadata about weather stations
extracted from the WMO OSCAR/surface database
https://oscar.wmo.int/surface
"""
import json
import os

try:
    from ._version import __version__, __title__
    from . import _tools
except ImportError:
    from _version import __version__, __title__
    import _tools

OSCARFILE = os.path.join(_tools.DIST_AUX_FILES, 'wmo_stationlist.json')
STATIONLIST = {}

def _lazy_load_list(file: str = None):
    if file is None:
        file = OSCARFILE
    global STATIONLIST
    if not STATIONLIST:
        with open(file, 'r') as f:
            STATIONLIST = json.load(f)

def _get_float(station: dict, field: str) -> float:
    if field in station:
        try:
            res = float(station[field])
        except ValueError:
            res = None
    else:
        res = None
    return res

def _wigos_from_wmo(nr: (str, int)) -> str:
    return "0-20000-0-%05d" % int(nr)

def by_wmo_id(id: (str, int)) -> dict:
    _lazy_load_list()
    return by_wigos_id(_wigos_from_wmo(id))

def by_wigos_id(id: str) -> dict:
    _lazy_load_list()
    res = None
    for station in STATIONLIST:
        for wid in wigos_ids(station):
            if wid == id:
                res = station
            break
    return res

def position(station: dict) -> list:
    lat = _get_float(station, 'latitude')
    lon = _get_float(station, 'longitude')
    ele = _get_float(station, 'elevation')
    return lat, lon, ele

def wigos_ids(station: dict) -> list:
    res = []
    wis = station.get("wigosStationIdentifiers", [])
    for wi in wis:
        wid = wi["wigosStationIdentifier"]
        pri = wi["primary"]
        if pri == True:
            res.insert(0, wid)
        else:
            res.append(wid)
    return res

def wmo_stationinfo(wmoid: (str,int)) -> (float, float, float, str):
    station = by_wmo_id(wmoid)
    lat, lon, ele = position(station)
    name = station['name'].title()
    return lat, lon, ele, name