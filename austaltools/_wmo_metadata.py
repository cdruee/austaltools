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
    from ._metadata import __version__, __title__
    from . import _storage
except ImportError:
    from _version import __version__, __title__
    import _storage

OSCARFILE = os.path.join(_storage.DIST_AUX_FILES, 'wmo_stationlist.json')
""" File holding the WMO station data retrieved from WMO OSCAR database """
STATIONLIST = {}
""" dictionary holding the WMO station data.
Empty stub to be filled later when needed """


def _lazy_load_list(file: str = None):
    """
    Fill the tempy STATIONLIST stub by reading data from file

    :param file: flie to read
    :type file: str
    """
    if file is None:
        file = OSCARFILE
    global STATIONLIST
    if not STATIONLIST:
        with open(file, 'r') as f:
            STATIONLIST = json.load(f)


def _get_float(station: dict, field: str) -> float|None:
    """
    Get a value from the STATIONLIST dict and return it as float,
    or None if the value cannot be converted into a float.

    :param station: station dataset entry
    :type station: dict
    :param field: name of the field to retrieve
    :type field: str
    :return: value of the field
    :rtype: float|None
    """
    if field in station:
        try:
            res = float(station[field])
        except ValueError:
            res = None
    else:
        res = None
    return res


def _wigos_from_wmo(nr: (str, int)) -> str:
    """
    Form the WIGOS ID of a weather station from its WMO station number.

    :param nr: station number
    :type nr: int|str
    :return: WIGOS ID
    :rtype: str
    """
    return "0-20000-0-%05d" % int(nr)


def by_wmo_id(id: (str, int)) -> dict:
    """
    Return station data entry of station identified by its WMO number.

    Fills STATIONLIST stub if not yet filled.

    :param id: WMO station number
    :type id: int|str
    :return: station dataset
    :rtype: dict
    """
    _lazy_load_list()
    return by_wigos_id(_wigos_from_wmo(id))


def by_wigos_id(id: str) -> dict:
    """
    Return station data entry of station identified by ist WIGOS ID.

    Fills STATIONLIST stub if not yet filled.

    :param id: WIGOS ID
    :type id: str
    :return: station dataset
    :rtype: dict
    """
    _lazy_load_list()
    res = None
    for station in STATIONLIST:
        for wid in wigos_ids(station):
            if wid == id:
                res = station
            break
    return res


def position(station: dict) -> tuple[float, float, float]:
    """
    Return position of a station

    :param station: station dataset
    :type station:  dict
    :return: Latitude, longitude and elevation
    :rtype: (float, float, float)
    """
    lat = _get_float(station, 'latitude')
    lon = _get_float(station, 'longitude')
    ele = _get_float(station, 'elevation')
    return lat, lon, ele


def wigos_ids(station: dict) -> list[str]:
    """
    Get the WIGOS IDs of a station

    :param station: station dataset
    :type station: dict
    :return: List of the WIGOS IDs
    :rtype: list[str]
    """
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


def wmo_stationinfo(wmoid: (str, int)) -> (float, float, float, str):
    """
    Return information about a station identified by its WMO number.

    :param station: station dataset
    :type station:  dict
    :return: Latitude, longitude, elevation and name
    :rtype: (float, float, float, str)
    """
    station = by_wmo_id(wmoid)
    lat, lon, ele = position(station)
    name = station['name'].title()
    return lat, lon, ele, name
