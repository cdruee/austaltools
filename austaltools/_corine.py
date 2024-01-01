#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jan  1 17:58:29 2024
"""
import logging
import json
import urllib

import numpy as np

try:
    from . import _tools
except ImportError:
    import _tools

logging.basicConfig()
logger = logging.getLogger()

# ----------------------------------------------------

CORINE_CLASSES_ROUGHNESS_LBM_DE={
        331: 0.01, 512: 0.01,
        333: 0.02, 421: 0.02, 423: 0.02, 511: 0.02, 522: 0.02,
        131: 0.05, 132: 0.05, 142: 0.05, 335: 0.05, 521: 0.05,
        124: 0.10, 211: 0.10, 231: 0.10, 334: 0.10, 411: 0.10,
        412: 0.10, 523: 0.10,
        122: 0.20, 141: 0.20, 221: 0.20, 321: 0.20, 322: 0.20,
        332: 0.20,
        123: 0.50,  222: 0.50, 324: 0.50,
        112: 1.00, 121: 1.00, 133: 1.00,
        312: 1.50, 313: 1.50,
        111: 2.00, 311: 2.00,
        }
REST_API_URL = ('https://image.discomap.eea.europa.eu/' +
                'arcgis/rest/services/Corine/CLC2018_WM/MapServer/0/')
# ----------------------------------------------------

def query_corine_class(lon: float, lat: float) -> int:
    """
    query CORINE class number for single position

    :return: CORINE class number
    :rtype: int
    """
    logger.debug('querying position: ' + str(lon) + ', ' + str(lat))
    info = {
        'geometry': '%.5f,%.5f' % (lon, lat),
        'geometryType': 'esriGeometryPoint',
        'inSR': '4326',
        'spatialRel': 'esriSpatialRelIntersects',
        'returnGeometry': 'false',
        'f': 'json'
    }
    data = urllib.parse.urlencode(info).encode('ascii')
    # print(data)
    req = urllib.request.Request(url='/'.join((REST_API_URL,'query')),
                                 data=data, method='POST')
    response = urllib.request.urlopen(req, timeout=5)

    #print(res.status)
    #print(res.reason)

    res_text = response.read().decode()
    # print(res_text)
    res_data = json.loads(res_text)
    result = res_data['features'][0]['attributes']['Code_18']
    logger.debug('... CORINE class: ' + result)
    return int(result)


# ----------------------------------------------------
def sample_points(xg: float, yg: float, h: float, fac=10.) -> list:
    """
    generate set of positions auround position xg,yg
    to query the CORINE class
    :param xg: x coordinate
    :param yg: y coordinate
    :param h: height
    :param fac: factor to sampel over
    :return: CORINE class number
    :rtype: int
    """
    points = []
    for xm in np.arange(np.floor(-fac),np.ceil(fac+1))*h:
        for ym in np.arange(np.floor(-fac),np.ceil(fac+1))*h:
            if np.sqrt(xm*xm+ym*ym) <= h*fac:
                x = xm + xg
                y = ym + yg
                points.append((x,y))
    return points

def mean_roughness(xg: float, yg: float, h: float, fac=10.) -> float:
    """
    return mean roughness length around a source at height h above
     the ground, sampling an area fac times its height around it.

    :param xg: poisition Gauss-Kruger rechtswert (eastward position)
    :param yg: poisition Gauss-Kruger hochwert (eastward position)
    :param h:  source / sensor height above ground
    :param fac: (otional) factor to sample. Defaults to 10.
    :return: roughness length in m
    :rtype: float
    """
    points = sample_points(xg, yg, h, fac)
    z0_values = []
    for x,y in points:
        lat, lon, _ = _tools.gk2ll(x,y)
        code = query_corine_class(lon, lat)
        if code in CORINE_CLASSES_ROUGHNESS_LBM_DE.keys():
            z0 = CORINE_CLASSES_ROUGHNESS_LBM_DE[code]
            z0_values.append(z0)
        else:
            logger.error("Unknown corine class %s" % code)
    average = np.mean(z0_values)
    return average


logger.setLevel(logging.DEBUG)

# info = {
#     'geometry': '6.76,49.76',
#     'geometryType': 'esriGeometryPoint',
#     'inSR': '4326',
#     'f': 'json'
# }
# data = urllib.parse.urlencode(info).encode('ascii')
# req = urllib.request.Request(url='https://image.discomap.eea.europa.eu/arcgis/rest/services/Corine/CLC2018_WM/MapServer/0/query',
#                              data=data, method='POST')
# res = urllib.request.urlopen(req, timeout=5)
#
# #print(res.status)
# print(res.reason)
#
# res = json.loads(res.read().decode())
# #res = res.read().decode()
# print(res)
