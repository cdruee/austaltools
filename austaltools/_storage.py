#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module that provides funtions to manage the storage locations for
configuration and datasets that serve as input for austaltools
"""
import os
import tempfile
import logging
from importlib import resources

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import yaml

try:
    from ._metadata import __title__
except ImportError:
    from _version import __title__

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------

CONFIG_FILE = f'{__title__}.yaml'
""" Name of the optional austaltools config file """
DIST_AUX_FILES = resources.files(__title__ + '.data')
""" path to the auxiliary data files distributes alongside the code """

STORAGE_LOCATIONS = ["/opt/%s" % __title__,
                     os.path.expanduser("~/.local/share/%s" % __title__),
                     os.path.expanduser("~/.%s" % __title__),
                         "."
                     ]
""" Default locations where downloaded or cashed data are expected """
STORAGE_TERRAIN = "terrain"
"""
storage directory that holds terrain data inside the storage locations
"""
STORAGE_WAETHER = "weather"
"""
storage directory that holds weather data inside the storage locations
"""
STORAGES = [STORAGE_TERRAIN, STORAGE_WAETHER]
"""
storage directories that hold data inside the storage locations
"""
TEMP = tempfile.gettempdir()
""" default path for temp files/dierctories """
SIMPLE_DEFAULT_WEATHER = 'CERRA'
""" default weather source in austaltools simple """
SIMPLE_DEFAULT_YEAR = 2003
""" default weather year in austaltools simple """
SIMPLE_DEFAULT_TERRAIN = 'DGM25-DE'
""" default terrain source in austaltools simple """
SIMPLE_DEFAULT_EXTENT = 10.
""" default terrain extent in austaltools simple """


# =========================================================================

def locations_available(locs: list[str]) -> list[str]:
    """
    Check whether locations exist
    :param locs: paths of storage location directories
    :type locs: list[str]
    :return: locations that exist
    :rtype: list[str]
    """
    return [x for x in locs if os.path.isdir(x)]

# -------------------------------------------------------------------------

def locations_writable(locs: list[str]) -> list[str]:
    """
    Check whether locations are writable
    :param locs: paths of storage location directories
    :type locs: list[str]
    :return: locations that are writable
    :rtype: list[str]
    """
    return [x for x in locs if os.access(x, os.W_OK)]

# -------------------------------------------------------------------------

def location_has_storage(location, storage):
    """
    Check if location has storage
    :param location: path to storage location
    :type location: str
    :param storage: name of storage
    :type storage: str
    :return: True if location has storage
    :rtype: bool
    """
    return os.path.exists(os.path.join(location, storage))


# -------------------------------------------------------------------------

def find_writeable_storage(locs: str = None,
                           stor: str = None) -> str or None:
    """
    Finds a viable data storage directory and returns its path.
    If `storage_path` is provided, only this path is checked
    for existance.

    :param locs: Candidate locations
    :type locs: str
    :param stor: Storage directory expected at location
    :type stor: str
    :return: path to a writable data storage directory
    :rtype: str
    """
    if stor is None:
        raise ValueError('stor must be provided')
    if locs is None:
        locs = STORAGE_LOCATIONS
    loc_exist = locations_available(locs)
    if len(loc_exist) == 0:
        return None
    loc_write = locations_writable(loc_exist)
    if len(loc_write) == 0:
        return None
    for loc in loc_write:
        if location_has_storage(loc, stor):
            location = loc
            break
    else:
        for loc in loc_write:
            try:
                os.makedirs(os.path.join(loc, stor))
            except IOError:
                continue
            if os.path.isdir(os.path.join(loc, stor)):
                location = loc
                break
        else:
            raise Exception('Could not create data storage directory')
    return os.path.join(location, stor)

# -------------------------------------------------------------------------

def read_config(locs: str = None) -> dict:
    if locs is None:
        # user files override centrally installed files -> reversed
        locs = reversed(STORAGE_LOCATIONS)
    config = {}
    for loc in locs:
        if os.path.exists(os.path.join(loc, CONFIG_FILE)):
            logger.debug(f"found config file at {loc}")
            with open(os.path.join(loc, CONFIG_FILE), 'r') as f:
                file_contents = yaml.safe_load(f)
            config.update(file_contents)
    return config

# -------------------------------------------------------------------------

def write_config(config: dict, locs: str = None) -> bool:
    if locs is None:
        # try central directories before user directories
        locs = STORAGE_LOCATIONS
    loc_to_write = None
    for loc in locs:
        # if dir is writable:
        if os.access(loc, os.W_OK):
            # remember highest-level writable dir
            if loc_to_write is None:
                loc_to_write = loc
            # if there is config a lower-level dir
            # (that overrides config in higher level dirs)
            # remember its location
            if os.path.exists(os.path.join(loc, CONFIG_FILE)):
                logger.debug(f"found existing writable config at {loc}")
                loc_to_write = loc
    # raise in case we did not find any location to write
    if loc_to_write is None:
        raise RuntimeError(f"could not write config file")
    # no try to (over) write the config
    try:
        with open(os.path.join(loc_to_write, CONFIG_FILE), 'w') as f:
            yaml.safe_dump(config, f)
        logger.debug(f"wrote config file at {loc_to_write}")
    except IOError:
        logger.warning(f"writing config file failed at {loc_to_write}")
    return True
