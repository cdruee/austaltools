#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This module provides funtions to processes a GeoJSON file
containing building data, extracts the corner points,
fit rectangles to corner points, plot the buildings
and to write building inforamtion the 'austal.txt' configuration file.
"""
import json
import logging
import os
import sys

import austaltools._geo

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import numpy as np

try:
    from . import _tools
    from . import _plotting
except ImportError:
    import _tools
    import _plotting

try:
    from ._metadata import __version__
except ImportError:
    from _version import __version__

logging.basicConfig()
logger = logging.getLogger()

# -------------------------------------------------------------------------
"""default name of the geojson file that contains building data"""
DEFAULT_FILE = 'haeuser.geojson'
"""default name of the geojson value that indicates building height"""
DEFAULT_ZVALUE = 'height'
"""
allowed difference between geojson polygon corners 
and the rectangle fitted to them in m
"""
DEFT_TOLRANCE = 0.5


# -------------------------------------------------------------------------


def building_new():
    """
    return a new Building object
    :return: empty building object
    :rtype: `_tools.Building()`
    """
    return _tools.Building()


# -------------------------------------------------------------------------


def extract_polygons(features, origin):
    """
    Extracts polygons from a list of features.

    This function processes a list of features and extracts polygons from them.
    It checks the type of each feature, validates the geometry, and converts
    coordinates to a model coordinate system based on the specified origin.

    :param features: A list of feature dictionaries.
    :type features: list[dict]

    :param origin: The origin point for coordinate conversion.
    :type origin: tuple[float, float]

    :return: A list of polygons, where each polygon is represented
      by a tuple containing:
      - Feature index
      - Polygon index within the feature
      - List of points (x, y) in the model coordinate system
    :rtype: list[tuple[int, int, list[tuple[float, float]]]]

    :note:

        - If a feature has unsupported geometry type, it will be skipped.
        - For MultiPolygon features, only the exterior ring (first set of coordinates) is considered.
        - Holes in polygons are ignored.
        - The logger is used to report errors and warnings.

    :example:

        >>> features = [
        ...     {'type': 'Feature', 'geometry': {
        ...         'type': 'Polygon',
        ...         'coordinates': [[(0, 0), (1, 0), (1, 1), (0, 1)]]}
        ...     },
        ...     {'type': 'Feature', 'geometry': {
        ...         'type': 'MultiPolygon',
        ...         'coordinates': [[[(2, 2), (3, 2), (3, 3), (2, 3)]]]}
        ...     },
        ... ]
        >>> origin = (0, 0)
        >>> extract_polygons(features, origin)
        [(0, 0, [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]),
         (1, 0, [(2.0, 2.0), (3.0, 2.0), (3.0, 3.0), (2.0, 3.0)])]
    """
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
            coords = []
            for j, c in enumerate(geometry['coordinates']):
                if len(c) > 1:
                    logger.warning('ignoring holes in feature ' +
                                   '#%i MultiPolygon #%i' % (i, j))
                coords.append(c[0])
        else:
            logger.error('geometry in feature #%i is unsopported type %s' %
                         (i, geometry['type']))
            continue
        for j, coord in enumerate(coords):
            gk_points = [np.array(x[0:2]) for x in coord]
            #
            # convert coordinates to model coordinate system
            points = [(x[0] - origin[0], x[1] - origin[1])
                      for x in gk_points]

            polygons.append((i, j, points[0:4]))

    return polygons


# -------------------------------------------------------------------------
def is_rectangle(points, tolerance=0.1):
    """
    Check if the given points form a rectangle within
    the specified tolerance.

    This function calculates the diagonals of the quadrilateral formed
    by the points and checks if the difference between the diagonals is
    within the specified tolerance value.

    :param points: A list of tuples representing the points.
    :type points: list[tuple[float, float]]
    :param tolerance: The maximum allowed difference between the diagonals.
    :type tolerance: float, optional
    :return: True if the points form a rectangle within the tolerance,
      False otherwise.
    :rtype: bool

    :example:

    >>> points = [(0, 0), (0, 2), (2, 0), (2, 2)]
    >>> is_rectangle(points)
    True
    """
    xx = [i[0] for i in points]
    yy = [i[1] for i in points]
    diag1 = np.sqrt((xx[2] - xx[0]) ** 2 + (yy[2] - yy[0]) ** 2)
    diag2 = np.sqrt((xx[3] - xx[1]) ** 2 + (yy[3] - yy[1]) ** 2)
    if abs(diag1 - diag2) > tolerance:
        re = False
    else:
        re = True
    return re


# -------------------------------------------------------------------------


def dist_points(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """
    Calulate distance between two points
    in a 2D a cartesian coordinate system

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
    """
    Check if the given points are within the specified tolerance from the building corners.

    This function calculates the minimum distance from each point to the building corners
    and checks if all distances are within the specified tolerance. It also ensures that
    all four corners of the building are represented by the closest points.

    :param tolerance: The maximum allowable distance from the points to the building corners.
    :type tolerance: float
    :param build: The building object containing the corner coordinates.
    :type build: _tools.Building
    :param points: A list of tuples representing the coordinates of the points to be checked.
    :type points: list[tuple[float, float]]
    :return: True if all points are within the tolerance and all corners are represented, False otherwise.
    :rtype: bool

    :example:
        >>> building = _tools.Building(corners=[(0, 0), (0, 10), (10, 0), (10, 10)])
        >>> points = [(1, 1), (1, 9), (9, 1), (9, 9)]
        >>> check_tolerances(2.0, building, points)
        True
    """
    corners = building_corners(build)
    corn = list()
    dist = list()
    for i, p in enumerate(points):
        alldist = [dist_points(p, x) for x in corners]
        dist.append(min(alldist))
        corn.append(np.argmin(alldist))
        logger.debug('distance #%i: %.2f' % (i, dist[-1]))
    logger.info('maximum corner distance: {}'.format(max(dist)))
    if (any([x > tolerance for x in dist]) or
            len(set(corn)) != 4):
        re = False
    else:
        re = True
    return re


# -------------------------------------------------------------------------


def find_building_around(points: list[tuple[float, float]],
                         tolerance: float) -> _tools.Building | None:
    """
    Find the minimal rectagle encircling the ``points``.
    Returns lower left corner as ``x`` and ``y`` coordinate,
    the exetensions of the rectangle, ``width`` in x-direction
    and ``depth`` in y-direction and its rotation ``angle``
    in degrees counterclockwise from the x-axis.

    :param points: list of the points positions
    :type points: list[tuple[float, float]]
    :param tolerance: minimum distance between points to consider
      them as different positions
    :type tolerance: float
    :return: Building object defining x, y, width, depth and angle
      or none if finding fails
    :rtype: _tools.Building or None
    """
    if len(points) > 4:
        points = deduplicate(points, tolerance / 2.)
    if len(points) < 2:
        logger.error('... polygon has less than two points')
        return None
    elif len(points) < 4:
        logger.warning('... polygon has less than four points')
    elif len(points) > 4:
        logger.warning('... polygon has more than four points')
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
        angle = np.rad2deg(np.arctan2(b * s, s))
    build = _tools.Building(x=x, y=y, a=width, b=depth, w=angle)
    return build


# -------------------------------------------------------------------------


def building_corners(build: _tools.Building) -> \
        list[tuple[float, float]]:
    """
    Return the four corner positions of a rectangle with the properties:

    :param build: Building object defining lower-left corner,
      rectangle extensions and rotation in degrees
      counterclockwise from the x-axis.
    :type angle: _tools.Building
    :return: list of corner positions
    :rtype: list[tuple[float, float]]
    """
    x, y, width, depth, angle = (
        getattr(build, g) for g in ['x', 'y', 'a', 'b', 'w'])
    lower_left = (x, y)
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


def sort_anticlock(points: list[tuple[float, float]]) -> \
        list[tuple[float, float]]:
    """
    Sort points anticlockwise around the center point

    :param points: point positions to sort
    :type points:  list[tuple[float,float]]
    :return: sorted point positions
    :rtype: list[tuple[float,float]]
    """
    n = len(points)
    center = (sum([x[0] / n for x in points]),
              sum([x[1] / n for x in points]))
    angles = [((np.rad2deg(np.arctan2(x[1] - center[1], x[0] - center[0]))
                + 180) % 360.)
              for x in points]
    order = np.argsort(angles)
    return [points[i] for i in order]


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
    points = sort_anticlock(points)
    max_dist_value = []
    max_dist_base = []
    ahs = []
    bes = []
    ses = []
    for i in range(n - 1):
        base_points = [points[j] for j in range(n) if j in [i, i + 1]]
        other_points = [points[j] for j in range(n) if j not in [i, i + 1]]
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


def dist_to_line(a: float, b: float, s: float, p: tuple[float, float]) -> \
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
    res = np.sqrt((p[0] - n[0]) ** 2 + (p[1] - n[1]) ** 2)
    if p[1] != n[1]:
        res = res * np.sign(p[1] - n[1]) * np.sign(s)
    else:
        res = res * np.sign(s)
    return res


# -------------------------------------------------------------------------


def nearest_point_on_line(a: float, b: float, p: tuple[float, float]) -> \
        tuple[float, float]:
    """
    Returns position of the point on the
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
    Returns parameters of the line through two points:
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

    :example:

        >>> p1 = (1, 2)
        >>> p2 = (3, 4)
        >>> line_through(p1, p2)
        (1.0, 1.0, 1)
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


def deduplicate(points, tolerance=None):
    """
    Removes duplicate points from a list of points.

    :param points: A list of (x, y) coordinate tuples.
        tolerance (float, optional): Maximum distance for considering points as duplicates.
        If provided, points within this distance are considered duplicates.
    :type points: list[tuple[float, float]]:

    :return: A list of unique points after removing duplicates.
    :rtype: list[tuple[float, float]]:

    :note:
        - If `tolerance` is specified, points within the tolerance distance are considered duplicates.
        - The `dist_points` function (not defined here) calculates the distance between two points.

    :example:
        >>> points = [(1.0, 2.0), (3.0, 4.0), (1.0, 2.0), (5.0, 6.0)]
        >>> deduplicate(points)
        [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)]


    """
    is_duplicate = [False] * len(points)
    for i, p1 in enumerate(points):
        for j, p2 in enumerate(points[i:]):
            if p1 == p2:
                is_duplicate[j] = True
            elif (tolerance is not None and
                  dist_points(p1, p2) < tolerance):
                is_duplicate[j] = True
    return [x for i, x in enumerate(points) if not is_duplicate[i]]


# -------------------------------------------------------------------------


def plot_building_shapes(args: dict, polygons: list[tuple],
                         buildings: list[_tools.Building],
                         topo: str = None):
    r"""
    Plot buildings and polygon shapes from geojson file

    :param args: command line arguments
    :type args: dict
    :param polygons:  list of tuple (#feature, # polygon, list of points)
    :type polygons: list[tuple]
    :param buildings: Building objects
    :type buildings:  list[_tools.Building]
    :param topo: Name of topography file (\*.grid)
    :type topo: str (optional)

    """
    import matplotlib
    import matplotlib.pyplot as plt
    import readmet

    matplotlib.rcParams.update({'font.size': 16})
    fig, ax = plt.subplots()
    fig.set_size_inches(11, 8)

    # ---------------------------
    # overlay topography as isolines
    #
    if topo is not None:
        logger.debug('adding topography')
        logger.debug('... from file: %s' % topo)
        if os.path.exists(topo):
            topo_path = topo
        elif os.path.exists(os.path.join(args['working_dir'], topo)):
            topo_path = os.path.join(args['working_dir'], topo)
        else:
            raise ValueError('topography file not found: %s' % topo)
        logger.info('reading topography from %s' % topo_path)
        topofile = readmet.dmna.DataFile(topo_path)
        topz = topofile.data[""]
        topx = topofile.axes(ax="x")
        topy = topofile.axes(ax="y")

        con = plt.contour(topx, topy, topz.T, origin="lower",
                          colors='black',
                          linewidths=0.75
                          )
        ax.clabel(con, con.levels, inline=True, fontsize=10)

    xrange = [np.Inf, -np.Inf]
    yrange = [np.Inf, -np.Inf]
    # ---------------------------
    # show input points
    #
    if polygons is not None:
        sym = "o"
        for i, j, points in polygons:
            for x, y in points:
                # ax.plot(x, y, sym, markersize=10, color="blue")
                xrange[0] = min([x, xrange[0]])
                xrange[1] = max([x, xrange[1]])
                yrange[0] = min([y, yrange[0]])
                yrange[1] = max([y, yrange[1]])
            for k, p1 in enumerate(points):
                p2 = points[(k + 1) % len(points)]
                ax.plot([p1[0], p2[0]], [p1[1], p2[1]], ":", color="blue")
    # ---------------------------
    # show buildings
    #
    if buildings is not None:
        for bb in buildings:
            ax.add_patch(
                matplotlib.patches.Rectangle(
                    xy=(bb.x, bb.y),
                    width=bb.a,
                    height=bb.b,
                    angle=bb.w,
                    fill=False,
                    color="black",
                )
            )
            xrange[0] = min([bb.x - (bb.a + bb.b), xrange[0]])
            xrange[1] = max([bb.x + (bb.a + bb.b), xrange[1]])
            yrange[0] = min([bb.y - (bb.a + bb.b), yrange[0]])
            yrange[1] = max([bb.y + (bb.a + bb.b), yrange[1]])

    spread = max([xrange[1] - xrange[0], yrange[1] - yrange[0]])
    ax.set_xlim([np.mean(xrange) - spread / 2, np.mean(xrange) + spread / 2])
    ax.set_ylim([np.mean(yrange) - spread / 2, np.mean(yrange) + spread / 2])

    if args["plot"] == "-":
        logger.info('showing plot')
        plt.show()
    elif args["plot"] not in [None, ""]:
        if os.path.sep in args["plot"]:
            outname = args["plot"]
        else:
            outname = os.path.join(args["wdir"], args["plot"])
        if not outname.endswith('.png'):
            outname = outname + '.png'
        logger.info('writing plot: %s' % outname)
        plt.savefig(outname, dpi=180)


# -------------------------------------------------------------------------


def main(args):
    """
    Main entry point: extract buildings from a GeoJSON file and write them to the config file 'austal.txt'.

    This function processes a GeoJSON file containing building data, extracts the relevant information,
    and writes it to a configuration file for further use. The function also supports optional plotting
    of building shapes.

    :param args: A dictionary containing the following keys:
        - 'zvalue': (optional) The name of the JSON variable denoting building height.
        - 'height': (optional) A fixed height value for all buildings.
        - 'tolerance': The tolerance value for checking if the points form a rectangle.
        - 'wdir': The working directory where the 'austal.txt' file is located.
        - 'file': The name of the GeoJSON file containing building data.
        - 'dry_run': A boolean flag indicating whether to perform a dry run (no file output).
        - 'plot': A boolean flag indicating whether to plot the building shapes.

    :type args: dict

    :raises ValueError: If the GeoJSON file is not of type 'FeatureCollection' or if the CRS is not 'EPSG:31463'.
    :raises ValueError: If neither GaussKrueger nor UTM coordinates are found in the configuration.
    :raises ValueError: If no height information is available for a building.

    :example:
        >>> args = {
        >>>     'zvalue': 'height',
        >>>     'height': None,
        >>>     'tolerance': 0.1,
        >>>     'wdir': '/path/to/working/directory',
        >>>     'file': 'buildings.geojson',
        >>>     'dry_run': True,
        >>>     'plot': False
        >>> }
        >>> main(args)
    """

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
    ausfile = _tools.find_austxt(args['working_dir'])
    austxt = _tools.get_austxt(ausfile)
    if 'gx' in austxt and 'gy' in austxt:
        gx = austxt['gx'][0]
        gy = austxt['gy'][0]
    elif 'ux' in austxt and 'uy' in austxt:
        gx, gy = austaltools._geo.ut2gk(austxt['ux'][0], austxt['uy'][0])
    else:
        raise ValueError('neither GaussKrueger nor UTM in config')
    origin = np.array((gx, gy))

    if os.path.sep in args['file']:
        buildings_file = args['file']
    else:
        buildings_file = os.path.join(args['working_dir'], args['file'])
    if not os.path.exists(buildings_file):
        raise IOError(f"file not found: {buildings_file}")
    logger.info('reading: %s' % buildings_file)
    with open(buildings_file) as f:
        data = json.load(f)
        # test if we got the right type of data:
    if data['type'] != 'FeatureCollection':
        raise ValueError('GeoJSON is not of type FeatureCollection')
    if data['crs']['properties']['name'] != 'urn:ogc:def:crs:EPSG::31463':
        raise ValueError('GeoJSON crs is not EPSG:31463')

    buildings = []
    polygons = extract_polygons(data['features'], origin)
    for i, j, points in polygons:
        logger.info('processing feature #%i Polygon %i:' % (i, j))
        #
        # create building object and insert data of outer rectangle
        build = find_building_around(points, rect_tolerance)
        # if error abort processing polygon
        if build is None:
            continue
        #
        # check if corner points of building object
        # match the original points inside tolerance
        if not check_tolerances(rect_tolerance, build, points):
            logger.error('feature #%i Polygon %i is ' % (i, j) +
                         'not a rectangle')
            continue
        #
        # get building height, raise error if none available
        build.c = -1.
        if zvalue is not None:
            if zvalue in data['features'][i]['properties']:
                build.c = round(float(
                    data['features'][i]['properties'][zvalue]))
        if height is not None:
            build.c = float(height)
        if build.c < 0:
            
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
        data[key] = ' '.join(['{:7.1f}'.format(getattr(x, k))
                              for x in buildings])
    #
    # output
    if args["dry_run"]:
        for k, v in data.items():
            print("%s %s" % (k, v))
    else:
        _tools.put_austxt(ausfile, data=data)

    if args["plot"]:
        if ('gh' in austxt):
            topo = austxt['gh']
        else:
            topo = None
        plot_building_shapes(args, polygons, buildings)
# -------------------------------------------------------------------------

def add_options(subparsers):
    pars_bldg = subparsers.add_parser(
        name='import-buildings',
        aliases=['bg'],
        help="get buildings from geojson and write to `austal.txt`")
    pars_bldg.add_argument('-g', '--geojson',
                           dest='file',
                           help='file containing building info' +
                                '[%s]' % DEFAULT_FILE,
                           default=DEFAULT_FILE)
    pars_bldg.add_argument('-n', '--dry-run',
                           action="store_true",
                           help='do not change austal.txt, ' +
                                'show changes instead.')
    pars_bldg.add_argument('-t', '--tolerance',
                           help='limit for accepting a polygon '
                                'as rectangle (max difference of the '
                                'lenght of the diagonals) ' +
                                '[%.2f]' % DEFT_TOLRANCE,
                           default=DEFT_TOLRANCE)
    pars_bldg_hgt = pars_bldg.add_mutually_exclusive_group()
    pars_bldg_hgt.add_argument('-z', '--zvalue',
                        help='name of property that gives building height' +
                             '[%s]' % DEFAULT_ZVALUE,
                        default=DEFAULT_ZVALUE)
    pars_bldg_hgt.add_argument('-Z', '--height',
                        help='height of all buildings')
    pars_bldg = _tools.add_arguents_common_plot(pars_bldg)

    return pars_bldg