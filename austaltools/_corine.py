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
import sys
import urllib

import austaltools._geo

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import numpy as np

    import readmet

try:
    from ._metadata import __title__
    from . import _storage
except ImportError:
    from _version import __title__
    import _storage

logging.basicConfig()
logger = logging.getLogger(__name__)

# ----------------------------------------------------
LANDCOVER_CLASSES_Z0_LBM_DE = {
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
Dictionary mapping LBM-DE (Digitales Landbedeckungsmodell für Deutschland)
class codes to roughness lengths [TAL2021]_ (in meters).

:meta hide-value:
"""
LANDCOVER_CLASSES_Z0_CORINE = {
    331: 0.01, 512: 0.01,
    132: 0.02, 231: 0.02, 321: 0.02, 333: 0.02, 421: 0.02,
    423: 0.02, 511: 0.02, 522: 0.02,
    131: 0.05, 142: 0.05, 211: 0.05, 335: 0.05, 521: 0.05,
    124: 0.10, 411: 0.10, 412: 0.10, 523: 0.10,
    122: 0.20, 141: 0.20, 221: 0.20, 242: 0.20, 243: 0.20,
    322: 0.20, 332: 0.20,
    123: 0.50, 222: 0.50, 324: 0.50,
    112: 1.00, 121: 1.00, 133: 1.00, 312: 1.00,
    311: 1.50, 313: 1.50,
    111: 2.00,
}
"""
Dictionary mapping CORINE class codes [JCR07]_ 
to roughness lengths [TAL2002]_ (in meters).

:meta hide-value:
"""
REST_API_URL = ('https://image.discomap.eea.europa.eu/' +
                'arcgis/rest/services/Corine/CLC2018_WM/MapServer/0/')
"""
URL for the REST API endpoint to query CORINE land cover classes.

:meta hide-value:
"""

CORINE_GERMANY = None

# ----------------------------------------------------

def corine_file_help():
    print(f"To use AUSTALs built-in CORINE landuse file, "
          f"you must tell {__title__} where to find the "
          f"AUSTAL installation.")
    print(f"Run `{__title__} austal` to tell austaltools "
          f"the location.")
    print(f"{__title__} uses the Gauss-Krüger version of "
          f"the land use file, i.e. you need the file "
          f"'z0-gk.dmna' in the directory, where the"
          f"AUSTAL executable ist stored.")

# ----------------------------------------------------

def corine_file_load():
    conf = _storage.read_config()
    austaldir = conf.get('austaldir', '')
    if austaldir in [None, '']:
        
        corine_file_help()
        raise RuntimeError(f"`austaldir` not defined in config.")
    corine_file = os.path.join(austaldir, 'z0-gk.dmna')
    if not os.path.exists(corine_file):
        corine_file_help()
        raise RuntimeError(f"z0-gk.dmna not found in {austaldir}.")
    z0gk = readmet.dmna.DataFile(corine_file)
    return z0gk

# ----------------------------------------------------

def roughness_austal(xg: float, yg: float, h: float,
                        fac: int = None) -> int:
    """
    Looks up the CORINE land cover class for a given latitude and longitude
    in the corine data file distributed along with AUSTAL.

    :param xg: X-coordinate of the center point.
    :type xg: float
    :param yg: Y-coordinate of the center point.
    :type yg: float
    :param h: Radius of the area to sample points.
    :type h: float
    :param fac: Factor to determine the density of sample points
               (default is 10).
    :type fac: float, optional
    :return: CORINE land cover class code for the specified location.
    :rtype: int
    """
    logger.debug('querying CORINE inventory')
    global CORINE_GERMANY
    if CORINE_GERMANY is None:
        logger.debug('loading AUSTALs local CORINE inventory')
        CORINE_GERMANY = corine_file_load()

    xmin = float(CORINE_GERMANY.header['xmin'])
    ymin = float(CORINE_GERMANY.header['ymin'])
    delta = float(CORINE_GERMANY.header['delta'])
    nx = len(CORINE_GERMANY.data['Classes'][0,0])
    ny = CORINE_GERMANY.data['Classes'].shape[1]

    z0_classes = {k:v for k, v in zip(
        CORINE_GERMANY.header['clsi'].split(),
        [float(x)
         for x in CORINE_GERMANY.header['clsd'].replace(' m','').split()]
    )}

    logger.debug(f"... for position: {xg}, {yg}")
    if not xmin <= xg <= xg + delta * nx and ymin <= yg <= yg + delta * ny:
        logger.warning('position outside region')
        return None

    sample = sample_points(xg, yg, h, fac)
    values = []
    for xx, yy in sample:
        ix = int(np.floor( (xx - xmin) / delta))
        iy = int(np.floor( (yy - ymin) / delta))
        logger.debug(f"... grid position: {ix} {iy}")
        digit = CORINE_GERMANY.data['Classes'][0,iy][ix]
        if digit not in z0_classes:
            logger.warning(f"Corine land cover class {digit} not defined")
        z0 = z0_classes.get(digit, np.nan)
        if z0 in [-999, np.nan]:
            logger.debug(f"... roughness length: (no data)")
            continue
        else:
            logger.debug(f"... roughness length: {z0} m")
        values.append(z0)
    result = np.nanmean(values, axis=0)
    return result

# ----------------------------------------------------

def query_corine_class(lat: float, lon: float) -> int:
    """
    Queries the CORINE land cover class for a given latitude and longitude
    from the EEA web API.

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
    try:
        response = urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as e:
        logger.error(f"could not look up CORINE class online: the server "
                     f"returned the error code: {e.code} ('{e.reason}')")
        features = None
    except urllib.error.URLError as e:
        logger.error(f"could not look up CORINE class online "
                     f"due to a communication error: {e.reason}")
        features = None
    else:
        res_text = response.read().decode()
        res_data = json.loads(res_text)
        features = res_data['features']
    if features is None:
        result = 0
    else:
        if len(features) == 1:
            result = features[0]['attributes']['Code_18']
            logger.debug('... CORINE class: ' + result)
        else:
            logger.error("looking up CORINE class online did not return "
                        "one single feature: %" % str(features))
            result = 0
    return int(result)

# ----------------------------------------------------

def sample_points(xg: float, yg: float, h: float, fac: int = None) -> list:
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
    if fac is None:
        fac = 10
    points = []
    for xm in np.arange(np.floor(-fac), np.ceil(fac + 1)) * h:
        for ym in np.arange(np.floor(-fac), np.ceil(fac + 1)) * h:
            if np.sqrt(xm * xm + ym * ym) <= h * fac:
                x = xm + xg
                y = ym + yg
                points.append((x, y))
    return points

# ----------------------------------------------------

def roughness_web(xg: float, yg: float, h: float, fac=10.) -> float:
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
        lat, lon = austaltools._geo.gk2ll(x, y)
        code = query_corine_class(lat, lon)
        if code in LANDCOVER_CLASSES_Z0_CORINE.keys():
            z0 = LANDCOVER_CLASSES_Z0_CORINE[code]
            z0_values.append(z0)
        else:
            logger.error("Unknown corine class %s" % code)
    average = np.nanmean(z0_values)
    return average

# ----------------------------------------------------

def mean_roughness(source: str,
                   xg: float, yg: float, h: float, fac=10.) -> float:
    """
    returns the mean roughness of an area based
    on CORINE land cover classes from either source
    - `web` for eea web API or
    - `austal` for CORINE inventory from local austal installation

    :param source: source of CORINE land cover classes.
    :type source: str
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

    if source == 'web':
        return roughness_web(xg, yg, h, fac)
    elif source == 'austal':
        return roughness_austal(xg, yg, h, fac)
    else:
        raise ValueError("Source must be either 'web' or 'austal'")
