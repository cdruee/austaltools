#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module for querying CORINE land cover classes and calculating mean
roughness.

This module provides functions to query CORINE land cover
classes based on geographic coordinates
and calculate the mean roughness of a specified area.

"""
import json
import logging
import os
import urllib

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import numpy as np

try:
    from . import _tools
except ImportError:
    import _tools

logging.basicConfig()
logger = logging.getLogger()

# ----------------------------------------------------

CORINE_CLASSES_ROUGHNESS_LBM_DE = {
    331: 0.01, 512: 0.01,
    333: 0.02, 421: 0.02, 423: 0.02, 511: 0.02, 522: 0.02,
    131: 0.05, 132: 0.05, 142: 0.05, 335: 0.05, 521: 0.05,
    124: 0.10, 211: 0.10, 231: 0.10, 334: 0.10, 411: 0.10,
    412: 0.10, 523: 0.10,
    122: 0.20, 141: 0.20, 221: 0.20, 321: 0.20, 322: 0.20,
    332: 0.20,
    123: 0.50, 222: 0.50, 324: 0.50,
    112: 1.00, 121: 1.00, 133: 1.00,
    312: 1.50, 313: 1.50,
    111: 2.00, 311: 2.00,
}
"""
Dictionary mapping CORINE class codes to roughness lengths [JCR07]_ 
(in meters).

:meta hide-value:
"""
REST_API_URL = ('https://image.discomap.eea.europa.eu/' +
                'arcgis/rest/services/Corine/CLC2018_WM/MapServer/0/')
"""
URL for the REST API endpoint to query CORINE land cover classes.

:meta hide-value:
"""


# ----------------------------------------------------


def query_corine_class(lat: float, lon: float) -> int:
    """
    Queries the CORINE land cover class for a given latitude and longitude.

    :param lat: Latitude of the location to query.
    :type lat: float
    :param lon: Longitude of the location to query.
    :type lon: float
    :return: CORINE land cover class code for the specified location.
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
    req = urllib.request.Request(url='/'.join((REST_API_URL, 'query')),
                                 data=data, method='POST')
    response = urllib.request.urlopen(req, timeout=5)

    res_text = response.read().decode()
    res_data = json.loads(res_text)
    features = res_data['features']
    if features is not None and len(features) > 0:
        result = features[0]['attributes']['Code_18']
    else:
        result = 0
    logger.debug('... CORINE class: ' + result)
    return int(result)


# ----------------------------------------------------
def sample_points(xg: float, yg: float, h: float, fac=10.) -> list:
    """
    Generates a list of sample points within a specified radius.

    :param xg: X-coordinate of the center point.
    :type xg: float
    :param yg: Y-coordinate of the center point.
    :type yg: float
    :param h: Radius of the area to sample points.
    :type h: float
    :param fac: Factor to determine the density of sample points
               (default is 10).
    :type fac: float, optional
    :return: List of tuples representing the sample points (x, y).
    :rtype: list
    """
    points = []
    for xm in np.arange(np.floor(-fac), np.ceil(fac + 1)) * h:
        for ym in np.arange(np.floor(-fac), np.ceil(fac + 1)) * h:
            if np.sqrt(xm * xm + ym * ym) <= h * fac:
                x = xm + xg
                y = ym + yg
                points.append((x, y))
    return points


def mean_roughness(xg: float, yg: float, h: float, fac=10.) -> float:
    """
    Calculates the mean roughness of an area based
    on CORINE land cover classes.

    :param xg: X-coordinate of the center point.
    :type xg: float
    :param yg: Y-coordinate of the center point.
    :type yg: float
    :param h: Radius of the area to calculate mean roughness.
    :type h: float
    :param fac: Factor to determine the density of sample points
                (default is 10).
    :type fac: float, optional
    :return: Mean roughness of the specified area.
    :rtype: float
    """
    points = sample_points(xg, yg, h, fac)
    z0_values = []
    for x, y in points:
        lat, lon, _ = _tools.gk2ll(x, y)
        code = query_corine_class(lat, lon)
        if code in CORINE_CLASSES_ROUGHNESS_LBM_DE.keys():
            z0 = CORINE_CLASSES_ROUGHNESS_LBM_DE[code]
            z0_values.append(z0)
        else:
            logger.error("Unknown corine class %s" % code)
    average = np.mean(z0_values)
    return average
