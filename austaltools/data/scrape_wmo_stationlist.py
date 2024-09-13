#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Helper script to retrieve the list of WMO station metadata
from the WMO OSCAR/surface database.
"""
import json

import pandas as pd
import requests

import pandas

"""https://oscar.wmo.int/surface/rest/api/search/download/stationSRs?data={"operation":"AND","nrt":false,"quickSearch":false,"variableIds":["10061","304","305","307","310","12005","12006"],"variableName":"Wind, Direction of cloud movement, Gust Speed, Wind (Z component, vertical), Upper wind (X, Y components, horizontal), Horizontal wind direction at specified distance from reference surface, Horizontal wind speed at specified distance from reference surface","operatingStatusId":10,"assessedStatusId":10,"wmoRaOrCountryId":"","tableParams":{"page":1,"count":10,"filter":{},"sorting":{"region":"asc","territory":"asc"},"group":{},"groupBy":null},"stationTypeIdList":[1,3,11,5],"stationClassIdList":[3,4,10,11],"filetype":"csv"}"""

FILE = 'wmo_stationlist.json'
#URL = 'https://oscar.wmo.int/surface/rest/api/search/download/stationSRs'
#DICT = {
#     'operation': 'AND',
#     'nrt': False,
#     'quickSearch': False,
#     'variableIds': ['10061', '304', '305', '307', '310', '12005', '12006'],
#     'variableName': 'Wind, Direction of cloud movement, '
#                     'Gust Speed, Wind (Z component, vertical), '
#                     'Upper wind (X, Y components, horizontal), '
#                     'Horizontal wind direction at specified '
#                     'distance from reference surface, '
#                     'Horizontal wind speed at specified '
#                     'distance from reference surface',
#     'operatingStatusId': 10,
#     'assessedStatusId': 10,
#     'wmoRaOrCountryId': '',
#     'tableParams': {'page': 1,
#                     'count': 10,
#                     'filter': {},
#                     'sorting': {'region': 'asc', 'territory': 'asc'},
#                     'group': {},
#                     'groupBy': None},
#     'stationTypeIdList': [1, 3, 11, 5],
#     'stationClassIdList': [3, 4, 10, 11],
#     'filetype': 'csv'
# }
URL = 'https://oscar.wmo.int/surface/rest/api/search/station'
DICT = {
    "stationClass":  "landFixed,landOnIce,seaFixed,lakeRiverFixed",
    "operatingStatus": "operational,closed",
    "variable": "12005,12006,180",
    'filetype': 'csv'
}
datastring = json.dumps(DICT, separators=(',', ':'))
print(datastring)
data = {'data': datastring}

print(f"sending download request to {URL}")
r = requests.get(URL, data=data)
print(f"download request returned code {r.status_code}")
jlist=json.loads(r.text)
stations = jlist['stationSearchResults']
print(f"returned list contains %i stations" % len(stations))

with open(FILE, 'w') as f:
    json.dump(jlist['stationSearchResults'], f)

print(f"saved list to {FILE}")


