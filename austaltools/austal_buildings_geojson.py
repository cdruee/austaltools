#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Mar 20 09:57:48 2022

@author: clemens
"""
import logging
import argparse
import os
import sys
import json

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import numpy as np

try:
    from . import _tools
except ImportError:
    import _tools

try:
    from ._version import __version__
except ImportError:
    from _version import __version__

logging.basicConfig()
logger = logging.getLogger()

# -------------------------------------------------------------------------

"""
allowed difference between geojson polygon cornersand fiited rectangle in m
"""
DEFAULT_TOLERANCE = 0.5
# -------------------------------------------------------------------------


def building_new():
    return _tools.Building()
# -------------------------------------------------------------------------


def extract_polygons(features):
    polygons = []

    for i, feature in enumerate(features):
        if feature['type'] != 'Feature':
            logger.error('feature #%i is not "Feature" but: %s'
                          % (i, feature['type']))
            continue
        if not 'geometry' in feature:
            logger.error('feature #%i does not have a geometry' % i)
            continue
        geometry = feature['geometry']
        if not 'type' in geometry:
            logger.error('geometry in feature #%i has no type' % i)
            continue
        if geometry['type'] == 'Polygon':
            if len(geometry['coordinates']) > 1:
                logger.warning('ignoring holes in feature #%i Polygon' % i)
            coords = [geometry['coordinates'][0]]
        elif geometry['type'] == 'MultyPolygon':
            coords=[]
            for j,c in enumerate(geometry['coordinates']):
                if len(c) > 1:
                    logger.warning('ignoring holes in feature ' +
                                   '#%i MultiPolygon #%i' % (i,j))
                coords.append(c[0])
        else:
            logger.error('geometry in feature #%i is unsopported type %s' %
                         (i,geometry['type']))
            continue
        for j,coord in enumerate(coords):
            points = [np.array(x[0:2]) for x in coord]
            if len(points) != 5:
                logger.error('feature #%i Polygon %i is not a quadrangle' %
                             (i,j))
                continue
            if dist_points(points[0], points[4]) > 0.5:
                logger.error('feature #%i Polygon %i is not closed' %
                             (i,j))
                continue
            polygons.append((i,j,points[0:4]))

    return polygons
# -------------------------------------------------------------------------


def is_rectangle(points, tolerance=0.1):
    xx = [i[0] for i in points]
    yy = [i[1] for i in points]
    diag1 = np.sqrt((xx[2]-xx[0])**2+(yy[2]-yy[0])**2)
    diag2 = np.sqrt((xx[3]-xx[1])**2+(yy[3]-yy[1])**2)
    if abs(diag1 - diag2) > tolerance:
        re = False
    else:
        re = True
    return re
# -------------------------------------------------------------------------


def dist_points(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """ distance between two points
    :param p1: point 1
    :type p1: tuple[float, float]
    :param p2: point 2
    :type p2: tuple[float, float]
    :return: distance
    :rtype: float
    """
    return np.sqrt(np.square(p2[0] - p1[0]) + np.square(p2[1] - p1[1]))
# -------------------------------------------------------------------------


def check_tolerances(tolerance: float, build: _tools.Building,
                     points: list[tuple[float, float]]) -> bool:
    corners = building_corners(build)
    corn = list()
    dist = list()
    for i,p in enumerate(points):
        alldist = [dist_points(p, x) for x in corners]
        dist.append(min(alldist))
        corn.append(np.argmin(alldist))
        logger.debug('distance #%i: %.2f' %(i,dist[-1]))
    logger.info('maximum corner distance: {}'.format(max(dist)))
    if (any([x > tolerance for x in dist]) or
            len(set(corn)) != 4):
        re = False
    else:
        re = True
    return re
# -------------------------------------------------------------------------


def find_building_around(points: list[tuple[float, float]]) -> \
        _tools.Building:
    """
    Find the minimal rectagle encircling the ``points``.
    Returns lower left corner as ``x`` and ``y`` coordinate,
    the exetensions of the rectangle, ``width`` in x-direction
    and ``depth`` in y-direction and its rotation ``angle``
    in degrees counterclockwise from the x-axis.

    :param points: list of the points positions
    :type points: list[tuple[float, float]]
    :return: Building object defining x, y, width, depth and angle
    :rtype: _tools.Building
    """
    a, b, s, ldist, pbase = rotating_caliper(points)
    projected_points = [nearest_point_on_line(a, b, x) for x in points]
    all_pairs = [(p1, p2) for i, p1 in enumerate(projected_points)
                       for p2 in projected_points[i + 1:]]
    width = np.abs(max([dist_points(*i) for i in all_pairs]))
    depth = np.abs(ldist)
    x, y = pbase
    if b in [np.Inf, np.Infinity]:
        angle = 90. * s
    else:
        angle = np.rad2deg(np.arctan2(b*s, s))
    build = _tools.Building(x=x, y=y, a=width, b=depth, w=angle)
    return build
# -------------------------------------------------------------------------


def building_corners(build: _tools.Building) -> \
        list[tuple[float, float]]:
    """
    returns the four corner positions of a rectangle with the properties:

    :param build: Building object defining lower-left corner,
    rectangle extensions and rotation in degrees
    counterclockwise from the x-axis.
    :type angle: _tools.Building
    :return: list of corner positions
    :rtype: list[tuple[float, float]]
    """
    x, y, width, depth, angle = (
        getattr(build,g) for g in ['x', 'y', 'a', 'b', 'w'])
    lower_left = (x,y)
    lower_right = (x + width * np.cos(np.deg2rad(angle)),
                   y + width * np.sin(np.deg2rad(angle)))
    upper_left = (x - depth * np.sin(np.deg2rad(angle)),
                  y + depth * np.cos(np.deg2rad(angle)))
    upper_right = (x
                   - depth * np.sin(np.deg2rad(angle))
                   + width * np.cos(np.deg2rad(angle)),
                   y
                   + depth * np.cos(np.deg2rad(angle))
                   + width * np.sin(np.deg2rad(angle)))

    return [lower_left, lower_right, upper_right, upper_left]
# -------------------------------------------------------------------------


def rotating_caliper(points: list[tuple[float, float]]) -> \
        (float, float, float, tuple[float, float]):
    """
    Return the equation of the one of all lines through two adjacent points,
    for which all other points are closest to the line,
    as well as dististance to and postion of the most distant point
    :param points: point positions
    :type points: tuple[float, float]
    :return: offset and slope of the line, most distant point
    distance and position of the first base point
    :rtype: float, float, float, tuple[float, float]
    """
    n = len(points)
    if n <= 2:
        raise ValueError('at least two points are required')
    max_dist_value = []
    max_dist_base = []
    ahs = []
    bes = []
    ses = []
    for i in range(n-1):
        base_points = [points[j] for j in range(n) if j in [i, i+1]]
        other_points = [points[j] for j in range(n) if j not in [i, i+1]]
        a, b, s = line_through(*base_points)
        distances = [dist_to_line(a, b, s, x) for x in other_points]
        ahs.append(a)
        bes.append(b)
        ses.append(s)
        imax = np.argmax([np.abs(x) for x in distances])
        max_dist_value.append(distances[imax])
        max_dist_base.append(base_points[0])
    imin = np.argmin(max_dist_value)
    return ahs[imin], bes[imin], ses[imin], \
        max_dist_value[imin], max_dist_base[imin]
# -------------------------------------------------------------------------


def dist_to_line(a: float, b:float, s:float, p: tuple[float, float]) -> \
        float:
    """
    returns distance of point ``p`` to
    line with slope ``b`` ant offset ``a``

    :param a: offset
    :type a: float
    :param b: slope
    :type b: float
    :param s: (rotation) sense
    (see :func:`austaltools.austal_buildings_geojson.line_through`)
    :type a: float
    :param p: point
    :type p: tuple[float, float]
    :return: distance
    :rtype: float
    """
    n = nearest_point_on_line(a, b, p)
    res = np.sqrt((p[0] - n[0])**2 + (p[1] - n[1])**2)
    if p[1] != n[1]:
        res = res * np.sign(p[1] - n[1]) * np.sign(s)
    else:
        res = res * np.sign(s)
    return res
# -------------------------------------------------------------------------


def nearest_point_on_line(a: float, b:float, p: tuple[float, float]) -> \
        tuple[float, float]:
    """
    returns position of the point on the
    line of slope ``b`` ant offset ``a``
    that is closest to point ``p``.

    :param a: offset
    :type a: float
    :param b: slope
    :type b: float
    :param p: point
    :type p: tuple[float, float]
    :return: distance
    :rtype: tuple[float, float]
    """
    if b in [np.Inf, np.Infinity]:
        # vertical line:
        res0 = a
        res1 = p[1]
    elif b == 0:
        res0 = p[0]
        res1 = a
    else:
        # slope and offset of normal line
        bn = -1. / b
        an = p[1] - bn * p[0]
        res0 = (a - an) / (bn - b)
        res1 = a + b * res0
    return res0, res1
# -------------------------------------------------------------------------


def line_through(p1: tuple[float, float], p2: tuple[float, float]) -> \
        (float, float):
    """
    returns parameters of the line through two points:
    slope and offset of the linear equation and
    (rotation) sense:
      - +1 if p2 is to the right (positive x axis) of p1
      - -1 if p2 is to the left (negative x axis) of p1

    :param p1: first point
    :type p1: tuple[float, float]
    :param p2: second point
    :type p2: tuple[float, float]

    :return: intercept and slope of the line
    :rtype: float, float
    """
    if p2[0] == p1[0]:
        # vertical line
        b = np.Inf
        a = p1[0]
    else:
        # non-vertical line
        b = (p2[1] - p1[1]) / (p2[0] - p1[0])
        a = p1[1] - b * p1[0]
    #
    # sense of the line
    # +1 if positive end is to positive x
    # -1 if positive end is to negative x
    if p2[0] != p1[0]:
        sense = np.sign(p2[0] - p1[0])
    else:
        sense = np.sign(p2[1] - p1[1])

    return a, b, sense
# -------------------------------------------------------------------------


def cli_parser():
    # defaults
    default = {'wdir': '.',
               'zvalue': 'height',
               'file': 'haeuser.geojson',
               'tolerance': DEFAULT_TOLERANCE,
               }
    parser = argparse.ArgumentParser(description='get buildings from geojson ' +
                                                 'and convert to "austal.txt"')
    verb = parser.add_mutually_exclusive_group()
    verb.add_argument('--debug', dest='verb', action='store_const',
                      const=logging.DEBUG, help='show informative output')
    verb.add_argument('-v', '--verbose', dest='verb', action='store_const',
                      const=logging.INFO, help='show detailed output')
    parser.add_argument('-f', '--file',
                        help='file containing building info' +
                             '[%s]' % default['file'],
                        default=default['file'])
    parser.add_argument('-n', '--dry-run',
                        action="store_true",
                        help='do not change austal.txt, ' +
                             'show changes instead.')
    parser.add_argument('-t', '--tolerance',
                        help='limit for accepting a polygon as rectangle' +
                             ' (max difference of the lenght of the' +
                             ' diagonals)' +
                             ' [%.2f]' % default['tolerance'],
                        default=default['tolerance'])
    height = parser.add_mutually_exclusive_group()
    height.add_argument('-z', '--zvalue',
                        help='name of property that gives building height' +
                             '[%s]' % default['zvalue'],
                        default=default['zvalue'])
    height.add_argument('-c', '--height',
                        help='height of all buildings')
    parser.add_argument('wdir', metavar='PATH', nargs='?',
                        help='directory where "zeitreihe.dmna" is stored '
                             '[%s]' % default['wdir'],
                        default=default['wdir'])
    return parser
# -------------------------------------------------------------------------


def main():
    """
    Main entry point
    """
    parser = cli_parser()
    args = vars(parser.parse_args())
    #
    # logging level
    #
    if args["verb"] is not None:
        logger.setLevel(args["verb"])
    else:
        logger.setLevel(logging.WARNING)
    logger.info(os.path.basename(__file__) + ' version: ' + __version__)

    # name of the json variable denoting building height
    if 'zvalue' in args:
        zvalue = args['zvalue']
    else:
        zvalue = None
    if 'height' in args:
        height = args['height']
    else:
        height = None
    rect_tolerance = float(args['tolerance'])

    #
    # read austal config and get gauss-krüger position of model origin
    ausfile = _tools.find_austxt(args['wdir'])
    austxt = _tools.get_austxt(ausfile)
    if 'gx' in austxt and 'gy' in austxt:
        gx = austxt['gx'][0]
        gy = austxt['gy'][0]
    elif 'ux' in austxt and 'uy' in austxt:
        gx, gy = _tools.ut2gk(austxt['ux'][0], austxt['uy'][0])
    else:
        raise ValueError('neither GaussKrueger nor UTM in config')
    origin = np.array((gx, gy))

    if os.path.sep in args['file']:
        buildings_file = args['file']
    else:
        buildings_file = os.path.join(args['wdir'], args['file'])
    logger.info('reading: %s' % buildings_file)
    with open(buildings_file) as f:
        data = json.load(f)
        # test if we got the right type of data:
    if data['type'] != 'FeatureCollection':
        raise ValueError('GeoJSON is not of type FeatureCollection')
    if data['crs']['properties']['name'] != 'urn:ogc:def:crs:EPSG::31463':
        raise ValueError('GeoJSON crs is not EPSG:31463')

    buildings = []
    polygons = extract_polygons(data['features'])
    for i,j,gk_points in polygons:
            if len(gk_points) < 4:
                logger.error('feature #%i Polygon %i is ' % (i,j) +
                             'has less than four points')
                continue
            else:
                logger.info('processing feature #%i Polygon %i:' % (i, j))
            #
            # convert coordinates to model coordinate system
            points = [(x[0] - origin[0], x[1] - origin[1])
                      for x in gk_points]
            #
            # create building object and insert data of outer rectangle
            build = find_building_around(points)
            #
            # check if corner points of building object
            # match the original points inside tolerance
            if not check_tolerances(rect_tolerance, build, points):
                logger.error('feature #%i Polygon %i is ' % (i,j) +
                             'not a rectangle')
                continue
            #
            # get building height, raise error if none available
            build.c = -1.
            if zvalue is not None:
                if zvalue in data['features'][i]['properties']:
                    build.c = round(float(data['features'][i]['properties'][zvalue]))
            if height is not None:
                build.c = float(height)
            if build.c < 0:
                sys.tracebacklimit = 0
                raise ValueError('no height information for ' +
                                 'feature #%i Polygon %i is ' % (i, j))
            #
            # show what we got
            logger.debug('%s' % format(build))
            #
            # put it in list
            buildings.append(build)
    #
    # make formatted output for austal.txt
    data = {}
    for k in building_new().keys:
        key = "%sb" % k
        data[key] = ' '.join(['{:7.1f}'.format(getattr(x,k)) for x in buildings])
    #
    # output
    if args["dry_run"]:
        for k,v in data.items():
            print("%s %s" % (k,v))
    else:
        _tools.put_austxt(ausfile, data=data)

# -------------------------------------------------------------------------


if __name__ == "__main__":
    main()
