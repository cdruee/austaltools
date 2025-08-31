import argparse
import os
import re
import shlex
import logging
import select
import sys
import typing
import unicodedata
import urllib.parse
from xml.etree import ElementTree

import pandas as pd
import requests

if os.getenv('BUILDING_SPHINX', 'false') == 'false':
    import numpy as np

    try:
        from tqdm import tqdm
    except ImportError:
        tqdm = None

    import readmet

try:
    from ._metadata import __version__, __title__
except ImportError:
    from _version import __version__, __title__

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------

DEFAULT_WORKING_DIR = "."
"""
Default location for input and output
"""
DEFAULT_COLORMAP = "YlOrRd"
"""Default colors used for the commpon plot type"""
MAX_RETRY = 3
""" number of tries made to download a ceratin file """

# -------------------------------------------------------------------------

AUSTAL_POLLUTANTS_GAS = ["so2", "nox", "no", "no2", "nh3", "hg0",
                         "hg", "bzl", "f", "xx", "odor",
                         "odor_050", "odor_065", "odor_075",
                         "odor_100", "odor_150"]
"""
Pollutant gases that are defined by austal: 
    "so2", "nox", "no", "no2", "nh3", "hg0",
    "hg", "bzl", "f", "xx", "odor",
    "odor_050", "odor_065", "odor_075",
    "odor_100", "odor_150"

:meta hide-value:
"""
AUSTAL_POLLUTANTS_DUST = ["pm", "as", "cd", "hg", "ni", "pb", "tl",
                          "ba", "dx", "xx"]
"""
Pollutant dust substances that are defined by austal:
    "pm", "as", "cd", "hg", "ni", "pb", "tl", "ba", "dx", "xx"

:meta hide-value:
"""
AUSTAL_POLLUTANTS_DUST_CLASSES = ["%s_%s" % (x, y)
                                  for y in ["x", "1", "2", "3", "4"]
                                  for x in AUSTAL_POLLUTANTS_DUST]
"""
Pollutant dusts that are defined by austal, 
each composed of a substance and grain-size class 1-4 or `x`

:meta hide-value:
"""
Z0_CLASSES = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 1.5, 2.0]
"""Surface roughness values corresponding to the roughness classes
defined by austal"""


# -------------------------------------------------------------------------

ELEVATION_API = "https://api.open-elevation.com/api/v1/lookup"
"""api used for estimation of elevation"""

# =========================================================================


class SmartFormatter(argparse.HelpFormatter):
    """
    Custom Help Formatter that maintains '\\\\n' in argument help.

    """
    def _split_lines(self, text, width):
        r = []
        for t in text.splitlines():
            r.extend(argparse.HelpFormatter._split_lines(self, t, width))
        return r

# =========================================================================

class GridASCII(object):
    """
    Class that represents a grid in ASCII format.


    Example:
        >>> grid = GridASCII("my_grid.asc")
        >>> print(grid.header["ncols"])  # Access header values
        >>> grid.write("output_grid.asc")  # Write grid data to a new file
    """
    file = None
    """Path to the ASCII file."""
    data = None
    """ grided data """
    _keys = ["ncols", "nrows", "xllcorner", "yllcorner", "cellsize",
             "NODATA_value"]
    header = {x: None for x in _keys}
    """Dictionary containing header information."""

    def __init__(self, file=None):
        """

        :param file:
            Path to the ASCII file (default: None).
        :type file:
            str (optional)
        """
        if file is not None:
            self.read(file)

    def read(self, file):
        """
        Reads the data from a GridASCII file in to the object.

        :param file: file name (optionally including path)
        :type file: str

        :raises: ValueError if file is not a GridASCII file
        """
        self.file = file
        self.data = np.rot90(np.loadtxt(file, skiprows=6), k=3)
        with open(file, "r") as f:
            for ln in f:
                k, v = re.split(r"\s+", ln.strip(), 1)
                if re.match(r'[0-9-.E]+', k):
                    # if fist field is a number the header is over
                    break
                elif k in self._keys:
                    self.header[k] = v
                else:
                    raise ValueError(
                        'unknown header value in file: %s' % k)

    def write(self, file=None):
        """
        Writes the data the object into a GridASCII file.

        :param file: file name (optionally including path).
          If missing, the name contained in the attribute `name` is used.
        :type file: str, optional

        :raises: ValueError if file is not a GridASCII file
        """
        if file is None:
            file = self.file
        ascii_header = "\n".join(["%-12s %s" % (k, self.header[k])
                                  for k in self._keys])

        np.savetxt(file, self.data, header=ascii_header,
                   comments='', fmt="%4.0f", delimiter="")

# =========================================================================

class Geometry(object):
    """
    A class that defines a geometric shape of the form
    that austal uses for sources and buildings.
    It is a cuboid of given widht, depth, and height,
    that may be rotated around its southwest corner.

    :param x: x position of the south-west corner
    :type x: float (optional), default 0.
    :param y: y position of the south-west corner
    :type y: float (optional), default 0.
    :param a: width (along x-axis) of the cuboid
    :type a: float (optional), default 0.
    :param b: depth (along y-axis) of cuboid
    :type b: float (optional), default 0.
    :param c: height (along z-axis) of cuboid
    :type c: float (optional), default 0.
    :param w: rotation angle anticlockwise around the south-west corner
    :type w: float (optional), default 0.
    """
    x = 0.
    y = 0.
    a = 0.
    b = 0.
    c = 0.
    w = 0.

    # -------------------------------------------------------------------------

    def __init__(self, x: float = 0, y: float = 0,
                 a: float = 0, b: float = 0, c: float = 0, w: float = 0):
        self.x = x
        self.y = y
        self.a = a
        self.b = b
        self.c = c
        self.w = w
        self.keys = ["x", "y", "a", "b", "c", "w"]

    def __format__(self, spec: str = "") -> str:
        """
        return a string representing the properties of a Geometry
        """
        if spec != "":
            fmt = spec
        else:
            fmt = "%s: %f"
        return " ".join([fmt % (k, getattr(self, k)) for k in self.keys])


# =========================================================================

class Building(Geometry):
    """
    A class representing the :class:`Geometry` of building
    """

    def __init__(self, *args, **kwargs):
        Geometry.__init__(self, *args, **kwargs)


# -------------------------------------------------------------------------

class Source(Geometry):
    """
    A class representing the :class:`Geometry` of pollutant source
    """

    def __init__(self, *args, **kwargs):
        Geometry.__init__(self, *args, **kwargs)

# ----------------------------------------------------

def estimate_elevation(lat, lon):
    """
    Quick estimation of elevation at a postion (for simple cli use)

    :param lat: position latitude
    :type lat: float|str
    :param lon: position longitude
    :type lon: float|str
    :return: elevation in m
    :rtype: float
    """
    logger.debug(f"querying elevation from API")
    latitude = float(lat)
    longitude = float(lon)
    data = f"locations={latitude},{longitude}"
    url = "?".join([ELEVATION_API, data])
    with requests.get(url) as req:
        ele = req.json()['results'][0]['elevation']
    elevation = float(ele)
    logger.debug(f"API returned elevation {elevation}")
    return elevation

# -------------------------------------------------------------------------

def expand_sequence(string):
    """
    Parse a string representing a sequence of values

    :param string: The string to parse. The string can take the form
        of a comma-seperated list `<value>, <value>, ..., <value>`
        or the form `<start>-<stop>/<step>` (in which step is optional).
    :type string: str
    :return: The sequence of values as describe by the string
    :rtype: list[int]

    :example:

    >>> expand_sequence("1,2,3,4,5")
    [1, 2, 3, 4, 5]
    >>> expand_sequence("1-9/2")
    [1, 3, 5, 7, 9]

    :note:

    If the string is a comma-seperated list of integers,
    the values must in increasing order.

    List form and start-stop form are mutually exclusive

    :raises: ValueError if the string contains any characters other than
        digits, ",", "-", or "/"
    :raises: ValueError if the string contains "," and "-" or "/"
    :raises: ValueError if the string is comma-seperated list of integers,
        but is not ordered.

    """
    logger.debug('parse_time_string: %s' % string)
    for x in string:
        if x not in ['-', ',', '/'] and not x.isdigit():
            raise ValueError('expand_series: illegal character in string: %s' % x)
    if '/' in string and ',' in string:
        raise ValueError(
            'expand_series: list and step are mutually exclusive')
    if ',' in string:
        # list
        res = [int(x) for x in string.split(',')]
        if not sorted(res) == res:
            raise ValueError('expand_series: discrete list is not sorted')
    elif ('-' not in string or
          (string.startswith('-') and '-' not in string[1:])):
        if '/' in string:
            raise ValueError('expand_series: step reqires `start-stop`')
        # scalar value
        res = [int(string)]
    else:
        if '/' in string:
            rang, step = string.split('/', 1)
            step = int(step)
        else:
            rang = string
            step = 1
        if not '-' in rang:
            raise ValueError("expand_series: range does not conatin `-`")
        r1 = re.sub('([-]*[0-9.]+)-[-0-9]*', r'\1', rang)
        r2 = re.sub('[-]*[0-9.]+-([-0-9]*)', r'\1', rang)
        start_stop = [int(r1), int(r2)]
        res = []
        x = int(r1)
        while x <= int(r2):
            res.append(x)
            x = x + step
    return res

# -------------------------------------------------------------------------

def overlap(first: tuple[int|float,int|float],
            second: tuple[int|float,int|float]) -> bool:
    wid =  min(first[1], second[1]) - max(first[0], second[0])
    if wid > 0.:
        return True
    else:
        return False

# -------------------------------------------------------------------------

def get_buildings(conf):
    """
    read the buildings defined in ``austal.txt`` and rerurn a list
    of :class:`Building` objects.

    :param conf: austal configuration as dict
    :type conf: dict
    :return: list of :class:`Building` objects
    :rtype: list[::class:`Building`]

    :raises: ValueError if the lists in each of the
      building-related configuration values are not all
      the same length.
    """
    pars = ["xb", "yb", "ab", "bb", "cb", "wb"]
    res = []
    if "xb" in conf and "yb" in conf:
        number = len(conf["xb"])
        val = {}
        for par in pars:
            if par in conf:
                if number != len(conf[par]):
                    
                    raise ValueError('different numbers of ' +
                                     'building-definig parameters')
                val[par] = conf[par]
            else:
                val = [0] * len(conf.keys())
        for i in range(number):
            res.append(Building(*[val[p][i] for p in pars]))
    else:
        logger.debug('no buildings in config')
    return res


# -------------------------------------------------------------------------

class Spinner:
    _pointer = 0
    spinner = r'|/-\\'
    step = 1
    text = 'Working ...'

    def __init__(self, text:str=None, step:int=None):
        if text is not None:
            self.text = text
        if step is not None:
            self.step = step
        self._show()

    def __del__(self):
        if logger.getEffectiveLevel() <= logging.DEBUG:
            return
        print("")

    def _show(self):
        if logger.getEffectiveLevel() <= logging.DEBUG:
            return
        char = self.spinner[self._pointer % len(self.spinner)]
        print ("{} {}".format(self.text, char), end='\r')

    def spin(self):
        self._pointer += 1
        self._show()

    def end(self):
        del self


# -------------------------------------------------------------------------

def progress(itr: typing.Iterable | None = None,
             desc: str = "", *args, **kwargs):
    """
    A progress bar that shows if :class:`tqdm.tqdm` is available and
    the log level is below :class:`logging.DEBUG`

    :param itr: iterator
    :type itr: list or iterable
    :param desc: string displayed in the progress bar
    :type desc: str (optional)
    :param args: arguments to `tqdm.tqdm`
    :param kwargs: keyword arguments to `tqdm.tqdm`
    :return: decorated iterator or `itr`, depending on the conditions
    :rtype: iterator
    """

    class Itr(list):
        """ Helper class """
        def __init__(self, iterable, *args, **kwargs):
            list.__init__(self, iterable)
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            return None
        def update(self, x):
            pass

    if itr is None:
        itr = Itr([])
    if tqdm is not None and 10 < logger.getEffectiveLevel() <= 30:
        return tqdm(itr, desc,
                    bar_format="{l_bar}{bar}|{remaining}",
                    *args, **kwargs)
    else:
        return Itr(itr)

# -------------------------------------------------------------------------

def find_z0_class(z0):
    """
    return index of roughness-length class that matches z0 best

    :param z0: actual roughness length
    :return: index of matching roughness-length class
    """
    if z0 in Z0_CLASSES:
        i = Z0_CLASSES.index(z0)
    else:
        lz0 = np.log(z0)
        lclasses = np.log(Z0_CLASSES)
        i = np.argmin(np.abs(lclasses - lz0))
    return i

# -------------------------------------------------------------------------

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
        
        raise IOError('austal.txt or austal2000.txt not found')
    logger.debug('austal config: %s' % ausname)
    return ausname

# -------------------------------------------------------------------------

def get_austxt(path=None):
    """
    Get AUSTAL configuration fron the file 'austal.txt' as dictionary

    :param path: Configuration file. Defaults to
    :type: str, optional
    :return: configuration
    :rtype: dict
    """
    if path is None:
        path = "austal.txt"
    logger.info('reading: %s' % path)
    # return config as dict
    conf = {}
    if not os.path.exists(path):
        
        raise FileNotFoundError('austal.txt not found')
    with open(path, 'r') as file:
        for line in file:
            # remove comments in each line
            text = re.sub("^ *-.*", "", line)
            text = re.sub("'.*", "", text).strip()
            # if empty line remains: skip
            if text == "":
                continue
            logger.debug('%s - %s' % (os.path.basename(path), text))
            # split line into key / value pair
            try:
                key, val = text.split(maxsplit=1)
            except ValueError:
                
                raise ValueError('no keyword/value pair ' +
                                 'in line "%s"' % text)
            # make numbers numeric
            try:
                values = [float(x) for x in val.split()]
            except ValueError:
                values = shlex.split(val)
            # in Liste abspeichern (Zahlen als Zahlen, Strings als Strings)
            conf[key] = values
    # fill missing values with default 0
    for x in ['xq', 'yq', 'aq', 'bq', 'cq', 'wq',
              #              'xb', 'yb', 'ab', 'bb', 'cb', 'wb',
              #              'cb'
              ]:
        if x not in conf:
            conf[x] = [0.]
    # fill other missing values with defaults
    if 'hq' not in conf:
        conf['hq'] = [20.]
    # liste zurückgeben
    return conf

# -------------------------------------------------------------------------

def put_austxt(path="austal.txt", data=None):
    """
    Write AUSTAL configuration file 'austal.txt'.

    If the file exists, it will be rewritten.
    Configuration values in the file are kept unless
    data contains new values.

    A Backup file is created wit a tilde appended to the filename.

    :param path: File name. Defaults to 'austal.txt'
    :type: str, optional
    :param data: Dictionary of configuration data.
        The keys are the AUSTAL configuration codes,
        the values are the configuration values as strings or
        space-separated lists
    :return: configuration
    :rtype: dict
    """
    # get config as text
    if data is None:
        data = {}
    logger.debug('reading: %s' % path)
    with open(path, 'r') as file:
        lines = file.readlines()
    # backup
    logger.debug('writing backup: %s' % path + '~')
    with open(path + '~', 'w') as file:
        for line in lines:
            file.write(line)
    # rewrite old file
    logger.info('rewriting file: %s' % path)
    with open(path, 'w') as file:
        last_line_was_empty = False
        for line in lines:
            keep = True
            # In jeder Zeile Kommentare entfernen
            stripped = re.sub("^ *-.*", "", line)
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

# -------------------------------------------------------------------------


def slugify(value, allow_unicode=False):
    """
    Taken from
    https://github.com/django/django/blob/master/django/utils/text.py
    Convert to ASCII if 'allow_unicode' is False. Convert spaces or
    repeated dashes to single dashes. Remove characters that aren't
    alphanumerics, underscores, or hyphens. Convert to lowercase.
    Also strip leading and trailing whitespace, dashes, and underscores.
    """
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize('NFKC', value)
    else:
        value = unicodedata.normalize('NFKD', value).encode(
            'ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value.lower())
    return re.sub(r'[-\s]+', '-', value).strip('-_')

# -------------------------------------------------------------------------


def str2bool(inp):
    """
    Convert a string to a boolean value.

    accept the usual strings indicating the user's consent or refusal
    """
    if isinstance(inp, bool):
        # allow passtrough
        res = inp
    elif str(inp).lower() in ['yes', 'true', 'y', 't', '1']:
        res = True
    elif str(inp).lower() in ['no', 'false', 'n', 'f', '0']:
        res = False
    else:
        raise ValueError('value not understood as boolean: %s' % inp)
    return res

# -------------------------------------------------------------------------

def download(url, file, usr=None, pwd=None):
    """
    Downloads a file from a specified URL and saves it
    to a given local file path.

    :param url: The URL of the file to download.
    :type url: str
    :param file: The local path, including the filename,
      where the downloaded file will be saved.
    :type file: str
    :returns: The name of the file saved locally.
    :rtype: str
    :raises Exception: An exception is raised if the download
      fails (HTTP status code is not 200).

    This function sends a GET request to the specified URL. If the request
    is successful (HTTP status code 200),
    it writes the content of the response to a file specified by
    the 'file' parameter. If the request fails,
    it raises an exception with information about the failure.

    :example:

        >>> try:
        >>>     file_name = download('http://example.com/file.jpg', '/path/to/local/file.jpg')
        >>>     print(f"Downloaded file saved as {file_name}")
        >>> except Exception as e:
        >>>     print(str(e))

    """
    with requests.get(url, allow_redirects=True) as req:
        if req.status_code == 200:
            with open(file, 'wb') as f:
                f.write(req.content)
        else:
            raise Exception(
                f"Download failed: status code {req.status_code}")
    return os.path.basename(file)

# -------------------------------------------------------------------------

def download_earthdata(url, file, usr, pwd):
    """
    Downloads a file from a specified URL that needs authorization
    from earthdata.nasa.gov and saves it to a given local file path.

    :param url: The URL of the file to download.
    :type url: str
    :param file: The local path, including the filename,
      where the downloaded file will be saved.
    :type file: str
    :param usr: The username of the user to authenticate with.
    :type usr: str
    :param pwd: The password of the user to authenticate with.
    :type pwd: str
    :returns: The name of the file saved locally.
    :rtype: str
    :raises Exception: An exception is raised if the download
      fails (HTTP status code is not 200).


    This function sends a GET request to the specified URL. If the request
    is successful (HTTP status code 200),
    it writes the content of the response to a file specified by
    the 'file' parameter. If the request fails,
    it raises an exception with information about the failure.

    :example:

        >>> try:
        >>>     file_name = download('https://n5eil01u.ecs.nsidc.org/'
        >>>                          'MOST/MOD10A1.006/2016.12.31/'
        >>>                          'MOD10A1.A2016366.h14v03.006.'
        >>>                          '2017002110336.hdf.xml',
        >>>                          '/path/to/local/hdf.xml',
        >>>                          'sampleuser', 'verysecret')
        >>>     print(f"Downloaded file saved as {file_name}")
        >>> except Exception as e:
        >>>     print(str(e))

    """
    # following the example at
    # https://urs.earthdata.nasa.gov/documentation/for_users/data_access/python

    class SessionWithHeaderRedirection(requests.Session):
        AUTH_HOST = 'urs.earthdata.nasa.gov'

        def __init__(self, username, password):
            super().__init__()
            self.auth = (username, password)

        # Overrides from the library to keep headers when redirected to or from
        # the NASA auth host.
        def rebuild_auth(self, prepared_request, response):
            headers = prepared_request.headers
            url = prepared_request.url
            if 'Authorization' in headers:
                original_parsed = urllib.parse.urlparse(response.request.url)
                redirect_parsed = urllib.parse.urlparse(url)
                if (original_parsed.hostname != redirect_parsed.hostname) and \
                        redirect_parsed.hostname != self.AUTH_HOST and \
                        original_parsed.hostname != self.AUTH_HOST:
                    del headers['Authorization']
            return

    session = SessionWithHeaderRedirection(usr, pwd)

    with session.get(url, allow_redirects=True) as req:
        if req.status_code == 200:
            with open(file, 'wb') as f:
                f.write(req.content)
        else:
            raise Exception(
                f"Download failed: status code {req.status_code}")
    return os.path.basename(file)

# -------------------------------------------------------------------------

def xmlpath(xml, path):
    """
    Extracts text or attribute values from specified elements
    within an XML string based on a given path.
    The function implements only a small subset of the XPath syntax.


    :param xml: The XML document as a str.
    :param path: A string representing the hierarchical path to the
      desired elements. This path may include element names,
      indexes in square brackets for direct child selection,
      and an optional attribute filter or attribute name
      preceded by ``::`` for final value extraction.

    Path Syntax

    * ``'element'``: Selects all children named ``element``
      from the current node.
    * ``'element[index]'``: Selects the n-th ``element`` among its
      siblings (0-based index).
    * ``'element[@attribute="value"]'``: Selects all ``element`` nodes
      where the attribute matches the specified value.
    * ``'element::attribute'``: Retrieves the value of an attribute
      named ``attribute`` from the selected elements.
    * Any combination of the above, separated by '/' to navigate
      through child elements.

    :return: A list containing the extracted data from the XML, either
      the text content of selected elements or the values of
      specified attributes, depending on the input path.

    :example:

        >>> xmlstring = '''<data>
        ...                     <item id="1">Item 1</item>
        ...                     <item id="2" extra="yes">Item 2</item>
        ...                </data>'''
        ...
        >>> pathtotext = 'item'
        >>> textresult = xmlpath(xmlstring, pathtotext)
        ['Item 1', 'Item 2']
        ...
        >>> pathtoattribute = 'item::id'
        >>> attributeresult = xmlpath(xmlstring, pathtoattribute)
        ['1', '2']


    :note:

    - This function is designed to operate on well-formed XML strings.
      Malformed XML might lead to unexpected results.
    - The function uses Python's built-in XML handling capabilities and
      regular expressions for parsing and navigating the XML.
    - Namespace handling: If the XML contains namespaces, they are
      automatically recognized and handled for tag matching.

    :raises: The function itself does not explicitly raise exceptions,
      but misuse (e.g., incorrect XML or path syntax) can
      lead to exceptions thrown by the underlying XML or
      regex processing libraries.

    """

    if '::' in path:
        getpath, getatt = path.split("::")
    else:
        getpath = path
        getatt = None
    levels = getpath.split('/')
    if levels[0] == '':
        levels.pop(0)
    root = ElementTree.fromstring(xml)
    m = re.search('{.*}', root.tag)
    if m:
        ns = '%s' % m.group(0)
    else:
        ns = ''
    nodes = [root]
    for level in levels:
        if "[" in level:
            name = re.sub(r'\[.*]', '', level)
            spec = re.sub(r'.*\[(.*)].*', r'\1', level)
            try:
                sel = int(spec)
                enti = None
            except ValueError:
                if '=' in spec:
                    enti, sel = [x.strip() for x in spec.split('=')]
                else:
                    enti = spec
                    sel = None
        else:
            name = level
            spec = enti = sel = None
        tag = ''.join((ns, name))
        #print(name, spec, enti, sel)
        next_nodes = []
        for node in nodes:
            # iterate over children
            tag_counter = {}
            i = 0
            for ele in node:
                # count identical tags
                if ele.tag in tag_counter:
                    tag_counter[ele.tag] += 1
                else:
                    tag_counter[ele.tag] = 0
                if not ele.tag == tag:
                    continue
                if sel is None and enti is None:
                    next_nodes.append(ele)
                elif sel == tag_counter[ele.tag]:
                    next_nodes.append(ele)
                elif enti is not None:
                    if enti.startswith('@'):
                        attr = enti.replace('@', '')
                        if (attr in ele.attrib and
                                bool(re.search(sel, ele.attrib[attr]))):
                            next_nodes.append(ele)
                    else:
                        if len(node.findall(enti)) > 0:
                            next_nodes.append(ele)
        nodes = next_nodes
    if getatt is None:
        res = [x.text for x in nodes]
    else:
        res = [x.get(getatt, default='') for x in nodes]
    return res

# -------------------------------------------------------------------------

def jsonpath(json_obj, path):
    """
    Extracts values from specified keys or indices within a
    JSON object based on a given path.

    :param json_obj: The JSON object (dict or list). This can be the
      result of json.loads() if using a JSON string.
    :param path: A string representing the hierarchical path to
      the desired keys or indices. This path may include dictionary keys,
      list indices, and an optional filtering condition for
      dictionaries with specific key-value pairs.

    Path Syntax

    * 'key': Selects the value associated with 'key' in a dictionary.
    * '[index]': Selects the n-th element in a list (0-based index).
    * 'key=value': Selects dictionaries from a list of dictionaries
      where 'key' matches 'value'.
    * Any combination of the above, separated by '/' to navigate
      through nested structures.
    * an asterisk (`*`) may be specified instead of 'key' to match any key.

    :return: A list containing the extracted values from the
      JSON object based on the input path.

    :example:

    >>> json_obj = {
    >>>   "items": [
    >>>       {"id": 1, "name": "Item 1"},
    >>>       {"id": 2, "name": "Item 2", "extra": "yes"}
    >>>   ]
    >>>  }
    ...
    >>> path_to_name = 'items/name'
    >>> names = jsonpath(json_obj, path_to_name)
    ['Item 1', 'Item 2']
    ...
    >>> path_to_extra = 'items/extra'
    >>> extras = jsonpath(json_obj, path_to_extra)
    ['yes']

    :note:

    - This function simplifies direct navigation and filtering in
      JSON objects but does not offer the full querying capabilities
      of more complex JSON querying libraries such as `jsonpath-rw`.

    """

    nodes = path.split('/')
    if nodes[0] == '':
        nodes.pop(0)
    # Start with a list for uniform processing
    obj = [json_obj]
    for node in nodes:
        children = []
        for oj in obj:
            if isinstance(oj, list):
                if node.isdigit():
                    # Indexing into a list
                    children += [oj[int(node)]]
                elif node == '*':
                    children += [oj]
                elif "=" in node:
                    key, value = node.split("=")
                    children += [o for o in oj if o.get(key) == value]
                else:
                    # Collecting items by key from each dictionary in list
                    children += [o[node] for o in oj if node in o]
            elif isinstance(oj, dict):
                if node in oj or node == '*':
                    children += [oj[node]]
        obj = children
    return obj

# -------------------------------------------------------------------------

def wind_library(path):
    """
    Find the directory that contains the wind library

    :param path: user supplied path
    :type path: str
    :return: path to wind library
    :rtype: str
    """
    if os.path.basename(path) == "lib":
        # path ist the lib-dir:
        libpath = path
    elif os.path.isdir(os.path.join(path, 'lib')):
        # lib-dir is in path:
        libpath = os.path.join(path, 'lib')
    else:
        logger.info('Warning: directory is NOT named lib')
        libpath = path
    logger.info('reading from directory: %s' % libpath)
    return libpath

# -------------------------------------------------------------------------

def analyze_name(name):
    """
    determine wind direction, stability class and grid index
    from the filename of a file in the wind library

    :param name: filename
    :type name: str
    :return: grid ID, wind direction, snd stability class
    :rtype: tuple[int, int, int]
    """
    # grid index
    try:
        grid = int(name[6])
    except (ValueError, IndexError):
        raise ValueError("invalid filename (grid index): %s" % name)
    # wind direction
    try:
        adir = name[3:5]
        if adir == "sn":
            wdir = 18
        elif adir == "we":
            wdir = 27
        else:
            wdir = int(adir)
    except (ValueError, IndexError):
        raise ValueError("invalid filename (wind direction): %s" % name)
    # stability class
    try:
        ak = int(name[1:2])
    except (ValueError, IndexError):
        raise ValueError("invalid filename (stability class): %s" % name)
    return grid, wdir, ak

# -------------------------------------------------------------------------

def wind_files(path):
    """
    find wind library files

    :param path: path where to search. Wind library files are expected
      to be in this path or in the subdirectory 'lib' of this path.
    :type path: str

    :return: dict of lists containing names, stability classes,
      general wind directions, and grid indexes of all files.
    :rtype: dict[str, list]
    """
    wn = re.compile(r"w[0-9asnwe]{7}\.dmna")
    f_name = [x for x in os.listdir(path) if wn.match(x)]
    logger.debug('filenames: %s' % str(f_name))
    f_grid = []
    f_wdir = []
    f_stab = []
    for f in f_name:
        grid, wdir, ak = analyze_name(f)
        f_grid.append(grid)
        f_wdir.append(wdir)
        f_stab.append(ak)
    logger.debug('stabilty classes: %s' % str(f_stab))
    logger.debug('wind directions: %s' % str(f_wdir))
    logger.debug('grid indexes: %s' % str(f_grid))
    return {'name': f_name, 'stab': f_stab, "wdir": f_wdir, 'grid': f_grid}

# -------------------------------------------------------------------------

def prompt_timeout(prompt, timeout, default: str = None):
    """
    Ask the user a question, wait timeout seconds for an answer,
    then continue

    :param prompt: Text to show as prompt
    :type prompt: str
    :param timeout: Time to weit for an answer in seconds
    :type timeout: int
    :param default: Default answer
    :type default: str|None
    :return: The answer. If the user typed in someting, it is returned,
      else the default.
    :rtype: str|None

    """
    print (prompt)
    print ("Please answer in the next {} seconds.".format(timeout))
    x, _, _ = select.select( [sys.stdin], [], [],
                             timeout )
    if x:
        res = sys.stdin.readline().strip()
    else:
        res = default
    return res

# -------------------------------------------------------------------------

def read_wind(file_info: dict, path: str = '.', grid: int = 0,
              centers:bool = False):
    """
    read wind library files

    :param file_info: dict of lists containing names, stability classes,
      general wind directions, and grid indexes of all files.
    :type file_info: dict
    :param path: Wind library files are expected
      to be in this path
    :type path: str
    :param grid: index of the grid for which to read the wind data
    :type grid: int
    :return: u_grid, v_grid, axes
    :rtype: tuple of (np.ndarray, np,dnarray, dict of lists of float)

    """
    if not isinstance(grid, int):
        raise ValueError('grid number is not numeric')
    if grid not in file_info['grid']:
        raise ValueError('grid %i not available in data' % grid)
    else:
        logger.info('reading grid: %i' % grid)
    # extract info for the wanted grid:
    grid_info = {}
    for k, v in file_info.items():
        grid_info[k] = [
            x for i, x in enumerate(file_info[k])
            if file_info['grid'][i] == grid
        ]
    ndir = len(set(grid_info["wdir"]))
    dirs = sorted(list(set(grid_info["wdir"])))
    nstab = len(set(grid_info['stab']))
    stabs = sorted(list(set(grid_info['stab'])))

    axes = readmet.dmna.DataFile(
        os.path.join(path, grid_info['name'][0])).axes()
    nx = len(axes['x'])
    ny = len(axes['y'])
    nz = len(axes['z'])

    u_grid = np.full((nx, ny, nz, nstab, ndir), np.nan)
    v_grid = np.full((nx, ny, nz, nstab, ndir), np.nan)

    for i in progress(range(len(grid_info['name'])),
                             desc="reading wind fields"):
        igrd, wdir, stab = analyze_name(grid_info['name'][i])
        if grid == igrd:
            filename = os.path.join(path, grid_info['name'][i])
            logger.debug('loading file: %s' % filename)
            dmna = readmet.dmna.DataFile(filename)
            istab = stabs.index(stab)
            idir = dirs.index(wdir)
            u_grid[:, :, :, istab, idir] = dmna.data['Vx']
            v_grid[:, :, :, istab, idir] = dmna.data['Vy']
    axes['dir'] = [x * 10. for x in dirs]
    axes['ak'] = stabs
    if centers:
        for ax in ['x', 'y', 'z']:
            axes[ax] = list(np.convolve(axes[ax],[0.5,0.5])[1:-1])
        u_ctr= np.full((nx - 1, ny - 1, nz - 1, nstab, ndir), np.nan)
        v_ctr = np.full((nx - 1, ny - 1, nz - 1, nstab, ndir), np.nan)
        for ib in range(nstab):
            for ir in range(ndir):
                for ix in range(nx - 1):
                    for iy in range(ny - 1):
                        for iz in range(nz - 1):
                            oz = iz + 1
                            # move 1 layer lover and ...
                            # ... mean u in x-direction
                            u_ctr[ix, iy, iz, ib, ir] = (
                                    u_grid[ix + 1, iy + 1, oz, ib, ir] +
                                    u_grid[ix, iy + 1, oz, ib, ir]) / 2.
                            # ... mean u in v-direction
                            v_ctr[ix, iy, iz, ib, ir] = (
                                    v_grid[ix + 1, iy, oz, ib, ir] +
                                    v_grid[ix + 1, iy + 1, oz, ib, ir]) / 2.
        u_grid = u_ctr
        v_grid = v_ctr

    return u_grid, v_grid, axes

# -------------------------------------------------------------------------

def read_z0(working_dir, conf=None):
    """
    get roughness length z0 defined in austal.txt

    :param working_dir: the working directoty of austal(2000),
      where austal.txt resides
    :type working_dir: str
    :param conf: (optional) configuration file contents as dict
    :type conf: dict

    :return: effective anemometer height
    :rtype: float

    If `conf` is provided, this configuration is evaluated,
    else the configuration file from `working_dir` is read.
    This option is indended for situation in which `conf`
    has already been read into memory for other purposes.
    """
    if conf is None:
        austxt = find_austxt(working_dir)
        conf = get_austxt(austxt)
    if 'z0' in conf:
        z0 = float(conf['z0'][0])
    else:
        logger.warning("no z0 defined in austal.txt")
        z0 = None
    return z0

# -------------------------------------------------------------------------

def read_heff(working_dir, conf=None, z0=None):
    """
    get effective anemometer height from
    z0 defined in austal.txt and the heights
    given in the akterm file (weather timeseries) given
    as parameter 'az'

    :param working_dir: the working directory of austal(2000),
      where austal.txt resides
    :type working_dir: str
    :param conf: (optional) configuration file contents as dict
    :type conf: dict
    :param z0: (optional) override z0 defined in austal.txt
    :type z0: float

    :return: effective anemometer height
    :rtype: float

    If `conf` is provided, this configuration is evaluated,
    else the configuration file from `working_dir` is read.
    This option is indended for situation in which `conf`
    has already been read into memory for other purposes.
    """
    if conf is None:
        austxt = find_austxt(working_dir)
        conf = get_austxt(austxt)
    if 'az' in conf:
        az_file = conf['az'][0]
    else:
        raise ValueError('no az defined, cannot read h_eff')
    if z0:
        # use supplied z0
        z0 = float(z0)
    else:
        # default: get z= from austal.txt
        z0 = read_z0(working_dir, conf)

    if z0 is None:
        raise ValueError('no z0 defined, cannot read h_eff')
    logger.debug(f"using z0={z0}")
    z0_class = find_z0_class(z0)
    az = readmet.akterm.DataFile(file=os.path.join(working_dir, az_file))
    heff = float(az.heights[z0_class])
    return heff

# -------------------------------------------------------------------------

def add_arguents_common_plot(parser: argparse.ArgumentParser
                             ) -> argparse.ArgumentParser:
    """
    Add agruments to a parser

    :param parser: parser to add arguments to
    :type parser: argparse.ArgumentParser
    :return: parser with added arguments
    :rtype:  argparse.ArgumentParser

    """
    parser.add_argument('-b', '--no-buildings',
                        dest='buildings',
                        action='store_false',
                        help='do not show the buildings ' +
                             'defined in config file')
    parser.add_argument('-l', '--low-colors',
                        dest='fewcols',
                        action='store_true',
                        help='use only few discrete colors ' +
                             'for better print results')
    parser.add_argument('-c', '--colormap',
                        default=DEFAULT_COLORMAP,
                        help='name of colormap to use. Defaults to "%s"' %
                             DEFAULT_COLORMAP)
    parser.add_argument('-k', '--kind',
                        default='contour',
                        choices=['contour', 'grid'],
                        help='choose kind of display. ' +
                             '`contour` produces filled contours, ' +
                             '`grid` produces coloured grid cells. ' +
                             'Defaults to `contour`')
    parser.add_argument('-p', '--plot',
                        metavar="FILE",
                        nargs='?',
                        const='__default__',
                        help='save plot to a file. If `FILE` is "-" ' +
                             'the plot is shown on screen. If `FILE` is ' +
                             'missing, the file name defaults to ' +
                             'the data file name with extension `png`'
                        )
    parser.add_argument('-f', '--force',
                        action='store_true',
                        default=False,
                        help='force overwriting plotfile if it exists.')
    return parser


def add_location_opts(parser,
                      stations=False,
                      required=True):
    """
    This routine adds the input arguments defining a position:

    :param parser: the arguemnt parser to add the options to
    :type parser: argpargse.ArgumentParser
    :param stations: WMO or DWD station numbers are accepted as positions
    :type stations: bool
    :param required: if a location specification is required
      type required: bool

    Note:
        - dwd (str or None): DWD option, mutually exclusive with 'wmo' and required with 'ele'.
        - wmo (str or None): WMO option, mutually exclusive with 'dwd' and required with 'ele'.
        - ele (str or None): Element option, required with either 'dwd' or 'wmo'.
        - year (int or None): Year option, required with '-L', '-G', '-U', '-D', or '-W'.
        - output (str or None): Output name, required with '-L', '-G', '-U', '-D', or '-W'.
        - station (str or None): Station option, only valid with 'dwd' or 'wmo'.

    """
    loc_opt = parser.add_mutually_exclusive_group(required=required)
    loc_opt.add_argument('-L', '--ll',
                         metavar=("LAT", "LON"),
                         dest="ll",
                         nargs=2,
                         default=None,
                         help='Center position given as Latitude and ' +
                              'Longitude, respectively. ' +
                              'This is the default.')
    loc_opt.add_argument('-G', '--gk',
                         metavar=("X", "Y"),
                         dest="gk",
                         nargs=2,
                         default=None,
                         help='Center position given in Gauß-Krüger zone 3' +
                              'coordinates: X = `Rechtswert`, ' +
                              'Y = `Hochwert`. ')
    loc_opt.add_argument('-U', '--utm',
                         metavar=("X", "Y"),
                         dest="ut",
                         nargs=2,
                         default=None,
                         help='Center position given in UTM Zone 32N' +
                              'coordinates: X = `easting`, ' +
                              'Y = `northing`.')
    if stations:
        loc_opt.add_argument('-D', '--dwd',
                             metavar="NUMBER",
                             dest="dwd",
                             help='Weather station position with ' +
                                  'German weather service (DWD) ID `NUMBER`')
        loc_opt.add_argument('-W', '--wmo',
                             metavar="NUMBER",
                             dest="wmo",
                             help='Postion of weather station with ' +
                                  'World Meteorological Organization (WMO)' +
                                  'station ID `NUMBER`')

    return parser


def read_extracted_weather(csv_name: str) -> (
        float, float, float, str, str, pd.DataFrame):
    """
    read weather data that were previously extracted from a
    dataset and stored into a csv file with specially crafted header line

    :param csv_name: file name and path
    :type csv_name: str
    :return: latitude, longitude, elevation, roughness length z0,
      code of the original dataset, station name (if applicable),
      and the weather data
    :rtype: float, float, float, str, str, pd.DataFrame
    """
    # halt if file is not found
    if not os.path.exists(csv_name):
        raise IOError('weather data not found: %s' % csv_name)
    logger.info('reading weather data from: %s' % csv_name)

    # read position fom comment line
    with open(csv_name, 'r') as f:
        lat, lon, ele, z0, source, nam = f.readline(
        ).strip('# \n').split(maxsplit=6)
    stat_no = 0

    # read observation data from subsequent lines
    obs = pd.read_csv(csv_name, comment='#', index_col=0,
                      parse_dates=True, na_values='-999')

    return lat, lon, ele, z0, source, nam, obs
