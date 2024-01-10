#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Mar 20 09:57:48 2022

@author: clemens
"""
import logging
import argparse
import os
import re
import shlex
import json

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import numpy as np

try:
    from ._version import __version__
except ImportError:
    from _version import __version__

logging.basicConfig()
logger = logging.getLogger()

# -------------------------------------------------------------------------

def find_austxt(wdir='.'):
    xnames = [os.path.join(wdir, x) for x in ["austal.txt",
                                              "austal2000.txt"]]
    for x in xnames:
        if os.path.exists(x):
            ausname = x
            break
    else:
        raise IOError('austal.txt or austal200.txt not found')
    logger.debug('austal argsig: %s' % ausname)
    return ausname

# -------------------------------------------------------------------------

def get_austxt(path="austal.txt"):
    logger.info('reading: %s' % path)
    # return argsig as dict
    args = {}
    with open(path, 'r') as file:
        for line in file:
            # In jeder Zeile Kommentare entfernen
            text = re.sub("^[ ]*-.*", "", line)
            text = re.sub("'.*", "", text).strip()
            # wenn Zeile danach leer: nächste Zeile
            if text == "":
                continue
            logger.debug('%s - %s' % (os.path.basename(path), text))
            # Zeile in Einzelwerte zerlegen
            key, val = text.split(maxsplit=1)
            # in Zahlen umwandeln
            try:
                values = [float(x) for x in val.split()]
            except ValueError:
                values = shlex.split(val)
            # in Liste abspeichern (Zahlen als Zahlen, Strings als Strings)
            args[key] = values
    # fehlende Werte mit default 0 setzen
    for x in ['xq', 'yq', 'aq', 'bq', 'cq', 'wq',
              'xb', 'yb', 'ab', 'bb', 'cb', 'wb',
              'cb']:
        if x not in args:
            args[x] = [0.]
    # fehlende Werte mit anderen defaults setzen
    if 'hq' not in args:
        args['hq'] = [20.]
    # liste zurückgeben
    return args

# -------------------------------------------------------------------------

def put_austxt(path="austal.txt", data={}):
    # get argsig as text
    logger.debug('reading: %s' % path)
    with open(path, 'r') as file:
        lines = file.readlines()
    # backup
    logger.debug('writing backup: %s' % path+'~')
    with open(path+'~', 'w') as file:
        for line in lines:
            file.write(line)
    # rewrite old file
    logger.info('rewriting file: %s' % path)
    with open(path, 'w') as file:
        last_line_was_empty = False
        for line in lines:
            keep = True
            # In jeder Zeile Kommentare entfernen
            stripped = re.sub("^[ ]*-.*", "", line)
            stripped = re.sub("'.*", "", stripped).strip()
            # wenn Zeile Daten enthält
            if stripped != "":
                # Zeile in Einzelwerte zerlegen
                key, val = stripped.split(maxsplit=1)
                # Soll der Wert ersetzt werden?
                if key in data.keys():
                    keep = False
            # no repeated empty lines
            if keep and last_line_was_empty and line.strip() == "":
                keep = False
            if keep:
                logger.debug('%s + %s' %
                             (os.path.basename(path), line.strip()))
                file.write(line)
                if line.strip() == "":
                    last_line_was_empty = True
                else:
                    last_line_was_empty = False
            else:
                logger.debug('%s - %s' %
                             (os.path.basename(path), line.strip()))
        file.write("\n")
        for k, v in data.items():
            line = "{:s}  {:s}\n".format(k, v)
            logger.debug('%s + %s' %
                         (os.path.basename(path), line.strip()))
            file.write(line)


def building_new():
    return {'xb': 0,
            'yb': 0,
            'ab': 0,
            'bb': 0,
            'cb': 0,
            'wb': 0,
            }

# -------------------------------------------------------------------------

def dist(p1, p2):
    return np.sqrt(np.square(p2[0] - p1[0]) + np.square(p2[1] - p1[1]))

# -------------------------------------------------------------------------


def cli_parser():
    # defaults
    default = {'wdir': '.',
               'zvalue': 'height',
               'file': 'haeuser.geojson'
               }
    parser = argparse.ArgumentParser(description='get buildings from geojson ' +
                                                 'and convert to "austal.txt"')
    verb = parser.add_mutually_exclusive_group()
    verb.add_argument('--debug', dest='verb', action='store_const',
                      const=logging.DEBUG, help='show informative output')
    verb.add_argument('-v', '--verbose', dest='verb', action='store_const',
                      const=logging.INFO, help='show detailed output')
    parser.add_argument('-f', '--file', nargs=1,
                        help='file containing building info' +
                             '[%s]' % default['file'],
                        default=default['file'])
    parser.add_argument('-z', '--zvalue', nargs=1,
                        help='name of property that gives building height' +
                             '[%s]' % default['zvalue'],
                        default=default['zvalue'])
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

    
    zvalue = args['zvalue']

    ausfile = find_austxt(args['wdir'])
    austxt = get_austxt(ausfile)
    gx = austxt['gx'][0]  # gx = 3333401
    gy = austxt['gy'][0]  # gy = 5514280
    pg = np.array((gx, gy))

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
    for i, o in enumerate(data['features']):
        if o['type'] != 'Feature':
            logger.error('feature #%i is not Feature but: %s'
                          % (i, o['type']))
            continue
        if o['geometry']['type'] != 'MultiPolygon':
            logger.error('feature #%i is not defined as MultiPolygon ' +
                          'but: %s' % (i, o['geometry']['type']))
            continue
        points = [np.array(x[0:2])
                  for x in o['geometry']['coordinates'][0][0]]
        if len(points) != 5:
            logger.error('feature #%i is not a quadrangle' % i)
            continue
        if dist(points[0], points[4]) > 0.5:
            logger.error('feature #%i is not a closed line' % i)
            continue
        #
        logger.info('feature #%i is processed as a building' % i )
        build = building_new()
        # make positions relative, drop last (update) position
        points = [p-pg for p in points[0:4]]
        # make most westerly point the anchor position
        xmin = np.amin([p[0] for p in points])
        iwest = [i for i, p in enumerate(points) if p[0] == xmin]
        if len(iwest) == 1:
            pb = points[iwest[0]]
            iref = iwest[0]
        else:
            isouth = np.argmin(points[iwest])
            pb = points[iwest][isouth]
            iref = iwest[isouth]
        pl = points[(iref - 1) % len(points)]
        pr = points[(iref + 1) % len(points)]
        logger.debug(pl-pb, pr-pb)
        angl = np.rad2deg(np.arctan2(*np.flip(pl-pb)))
        angr = np.rad2deg(np.arctan2(*np.flip(pr-pb)))
        logger.debug(np.round((angr-angl) % 360, decimals=-1))
        if np.round((angr-angl) % 360, decimals=-1) == -90:
            build['wb'] = angr
            build['ab'] = dist(pr, pb)
            build['bb'] = dist(pl, pb)
        else:
            build['wb'] = angl
            build['ab'] = dist(pl, pb)
            build['bb'] = dist(pr, pb)
        build['cb'] = round(float(o['properties'][zvalue]))
        build['xb'], build['yb'] = pb

        logger.debug('%s' % format(build))

        buildings.append(build)

    data = {}
    for k in building_new().keys():
        data[k] = ' '.join(['{:7.1f}'.format(x[k]) for x in buildings])

    put_austxt(ausfile, data=data)
# -------------------------------------------------------------------------


if __name__ == "__main__":
    main()
