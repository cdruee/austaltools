import os
import re
import shlex
import logging

logger = logging.getLogger()


class Geometry():
    x = 0.
    y = 0.
    a = 0.
    b = 0.
    c = 0.
    w = 0.

    def __init__(self, x=0, y=0, a=0, b=0, c=0, w=0):
        self.x = x
        self.y = y
        self.a = a
        self.b = b
        self.c = c
        self.w = w


class Building(Geometry):
    def __init__(self, *args, **kwargs):
        Geometry.__init__(self, *args, **kwargs)


class Source(Geometry):
    def __init__(self, *args, **kwargs):
        Geometry.__init__(self, *args, **kwargs)

def get_buildings(conf):
    pars = ["xb", "yb", "ab", "bb", "cb", "wb"]
    res = []
    if "xb" in conf and "yb" in conf:
        number = len(conf["xb"])
        lb = {}
        val={}
        for par in pars:
            if par in conf:
                if number != len(conf[par]):
                    raise ValueError('different numbers of ' +
                                     'building-definig parameters')
                val[par] = conf[par]
            else:
                val = [0] * len(conf())
        for i in range(number):
            res.append(Building(*[val[p][i] for p in pars]))
    else:
        logging.warning('no buildings in cofig')
    return res


def find_austxt(wdir='.'):
    if wdir == '':
        wdir = '.'
    xnames = [os.path.join(wdir, x) for x in ["austal.txt",
                                              "austal2000.txt"]]
    for x in xnames:
        if os.path.exists(x):
            ausname = x
            break
    else:
        raise IOError('austal.txt or austal200.txt not found')
    logger.debug('austal config: %s' % ausname)
    return ausname


def get_austxt(path="austal.txt"):
    logger.info('reading: %s' % path)
    # return config as dict
    conf = {}
    with open(path, 'r') as file:
        for line in file:
            # remove comments in each line
            text = re.sub("^[ ]*-.*", "", line)
            text = re.sub("'.*", "", text).strip()
            # if empty line remains: skip
            if text == "":
                continue
            logger.debug('%s - %s' % (os.path.basename(path), text))
            # split line into key / value pair
            key, val = text.split(maxsplit=1)
            # make numbers numeric
            try:
                values = [float(x) for x in val.split()]
            except ValueError:
                values = shlex.split(val)
            # in Liste abspeichern (Zahlen als Zahlen, Strings als Strings)
            conf[key] = values
    # fill missing values with default 0
    for x in ['xq', 'yq', 'aq', 'bq', 'cq', 'wq',
              'xb', 'yb', 'ab', 'bb', 'cb', 'wb',
              'cb']:
        if x not in conf:
            conf[x] = [0.]
    # fill other missing values with defaults
    if 'hq' not in conf:
        conf['hq'] = [20.]
    # liste zurückgeben
    return conf


def put_austxt(path="austal.txt", data={}):
    # get config as text
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


