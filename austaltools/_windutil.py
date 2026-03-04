"""
Wind measurement utility functions for AUSTAL dispersion modelling.

Provides routines to retrieve, correct, and standardise wind observations
for use with the AUSTAL / AUSTAL2000 atmospheric dispersion model:

- Roughness length z0: read from configuration, log files, or CORINE data
- Effective anemometer height: derived from z0 class and AKTERM file
- Weather time series: load from DMNA or AKTERM files
- Roughness correction: convert anemometer readings to standardised open-terrain
  wind speed at 10 m using WMO, Eurocode 1, or DIN EN 1991-1-4 methods

"""
import logging
import os
import re

import pandas as pd
import numpy as np

if os.getenv('BUILDING_SPHINX', 'false') == 'false':
    import readmet

from ._metadata import __version__, __title__
from . import _corine
from . import _dispersion
from . import _geo
from . import _tools

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------------

def get_roughness_length(working_dir=None, conf=None):
    """
    Get roughness length z0 for the AUSTAL simulation area.

    Attempts to determine z0 in the following priority order:
    1. Read from austal.txt configuration file
    2. Extract from AUSTAL log files (austal.log, austal2000.log, taldia.log)
    3. Calculate from CORINE land use data based on simulation position

    :param working_dir: The working directory of austal(2000), where austal.txt
                        resides. If None, uses DEFAULT_WORKING_DIR
    :type working_dir: str, optional
    :param conf: AUSTAL configuration file contents as dict. If None, the
                 configuration will be read from working_dir
    :type conf: dict, optional

    :return: Roughness length z0 in meters
    :rtype: float

    :raises ValueError: If z0 cannot be determined from any source and position
                        is not defined in configuration

    The function attempts to determine z0 from multiple sources:

    - If z0 is explicitly defined in austal.txt, that value is used
    - If not defined, searches log files for z0 values that AUSTAL rounded
    - If still not found, calculates mean z0 from CORINE land use data:

      - Requires position (xg/yg or xu/yu) in configuration
      - Optionally uses source height (hq) from configuration, defaults to 10m
      - First tries local CORINE inventory
      - Falls back to EEA Web API if local data unavailable

    If `conf` is provided, this configuration is evaluated; otherwise the
    configuration file is read from `working_dir`. This option is intended
    for situations where `conf` has already been read into memory for other
    purposes.
    """
    if working_dir is None:
        working_dir = _tools.DEFAULT_WORKING_DIR
    z0 = read_z0(working_dir, conf)
    if z0 is None:
        logger.info("no z0 defined, searching logfiles for z0")
        z0 = search_logs_for_z0(working_dir)
    if z0 is None:
        logger.info("no z0 found, re-calculating mean z0")
        if conf is None:
            austxt = _tools.find_austxt(working_dir)
            conf = _tools.get_austxt(austxt)
        if 'xg' in conf and 'yg' in conf:
            xg = conf['xg']
            yg = conf['yg']
        elif 'xu' in conf and 'yu' in conf:
            xu = conf['xu']
            yu = conf['yu']
            xg, yg = _geo.ut2gk(xu, yu)
        else:

            raise ValueError("neither z0 nor position defined, "
                             "cannot determine z0")
        if 'hq' in conf:
            hq = conf['hq']
        else:
            logger.warning("no source height defined, assuming 10m")
            hq = 10.
        logger.debug('averaging z0 from local corine inventory')
        z0 = _corine.roughness_austal(xg, yg, hq)
        if z0 is None:
            logger.debug('averaging z0 from EEA Web API')
            z0 = _corine.roughness_web(xg, yg, hq)
        logger.info(f"z0 at position of wind measurement: {z0}")

    return z0

# -------------------------------------------------------------------------

def load_weather(working_dir: str, conf: dict = None,
                 file: str = None) -> pd.DataFrame:
    """
    Get the weather time series height `working_dir`.
    Files are evaluated in the same order as by AUSTAL:
    `zeitreihe.dmna` or `timeseries.dmna` are tried to read first,
    then the AKTERM file spezified in the config file under
    parameter 'az'

    :param working_dir: the working directory of austal(2000),
      where austal.txt resides. If path is a file, this file is read,
      ignoring the AUSTAL configuration.
    :type working_dir: str
    :param conf: (optional) AUSTAL configuration file contents as dict
    :type conf: dict

    :return: effective anemometer height
    :rtype: float

    If `conf` is provided, this configuration is evaluated,
    else the configuration file from `working_dir` is read.
    This option is indended for situation in which `conf`
    has already been read into memory for other purposes.
    """
    if file is not None:
        # filename given: determine type
        if file.endswith('.dmna'):
            ts_file = file
            az_file = None
        else:
            ts_file = None
            az_file = file
    else:
        az_file = None
        # dir name given: search file
        if conf is None:
            austxt = _tools.find_austxt(working_dir)
            conf = _tools.get_austxt(austxt)
        working_dir_files = os.listdir(working_dir)
        for x in ['zeitreihe.dmna', 'timeseries.dmna']:
            if x in working_dir_files:
                ts_file = os.path.join(working_dir, x)
                break
        else:
            ts_file = None
    # load file: switch file type
    if ts_file is not None:
        # zeitreihe(timeseries).dmna generated by AUSTAL
        zr = readmet.dmna.DataFile(os.path.join(working_dir, ts_file)).data
        res = pd.DataFrame(index=pd.to_datetime(zr['te']))
        res['FF'] = zr['ua'].values
        res['DD'] = zr['ra'].values
        z0 = get_roughness_length(working_dir=working_dir, conf=conf)
        res['KM'] = [_dispersion.KM2021.get_index(z0, x)
                     for x in zr['ra'].values]
    else:
        if az_file is None:
            # akterm file for AUSTAL
            if 'az' in conf:
                az_file = conf['az'][0]
            else:
                raise ValueError('no az defined, cannot weather')
        az = readmet.akterm.DataFile(
            file=os.path.join(working_dir, az_file))
        res = az.data[['FF', 'DD', 'KM']]
    return res



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
        austxt = _tools.find_austxt(working_dir)
        conf = _tools.get_austxt(austxt)
    if 'az' in conf:
        az_file = conf['az'][0]
    else:
        raise ValueError('no az defined, cannot read h_eff')
    if z0:
        # use supplied z0
        z0 = float(z0)
    else:
        # try to get z0 from austal.txt etc
        z0 = get_roughness_length(working_dir, conf)
    if z0 is None:
        raise ValueError('no z0 defined, cannot read h_eff')
    logger.debug(f"using z0={z0}")
    z0_class = _tools.find_z0_class(z0)
    az = readmet.akterm.DataFile(file=os.path.join(working_dir, az_file))
    heff = float(az.heights[z0_class])
    return heff

# -------------------------------------------------------------------------

def _to_series(value, name: str, ref_index=None) -> pd.Series:
    """
    Convert a scalar, list-like, or :class:`pandas.Series` to a
    :class:`pandas.Series`, optionally validating its length or index
    against a reference index.

    :param value: The value to convert. Accepted types are:

      - ``int`` or ``float``: broadcast to a constant Series aligned to
        *ref_index*
      - list-like (but not Series): wrapped in a Series with *ref_index*;
        must have the same length as *ref_index*, or length 1
      - :class:`pandas.Series`: returned as-is if its index matches
        *ref_index* (when provided)

    :type value: int | float | list-like | pandas.Series
    :param name: Human-readable parameter name used in error messages.
    :type name: str
    :param ref_index: Index to assign to the resulting Series and to
      validate length/alignment against. If ``None``, no alignment check
      is performed and scalars produce a length-1 Series.
    :type ref_index: pandas.Index, optional

    :return: *value* represented as a :class:`pandas.Series`.
    :rtype: pandas.Series

    :raises ValueError: If a list-like *value* has a length that is
      neither 1 nor ``len(ref_index)``.
    :raises ValueError: If a Series *value* has an index that does not
      match *ref_index*.
    :raises TypeError: If *value* is none of the accepted types.

    .. note::
       ``isinstance(value, pd.Series)`` is tested *before*
       ``pd.api.types.is_list_like``, because a Series is also list-like
       and must be handled separately to preserve its index.
    """
    if isinstance(value, pd.Series):
        if ref_index is not None and not value.index.equals(ref_index):
            raise ValueError(f"'{name}' index does not match reference index")
        return value
    if isinstance(value, (int, float)):
        return pd.Series(value, index=ref_index)
    if pd.api.types.is_list_like(value):
        if ref_index is not None and len(value) != len(ref_index) and len(value) != 1:
            raise ValueError(f"'{name}' is neither scalar nor the same length as 'u'")
        return pd.Series(value, index=ref_index)
    raise ValueError(f"'{name}' must be a number, list, or pd.Series")


def roughness_correction(ua, ha, z0a, method=None):
    """
    Correct wind speed readings for local surface roughness exposure.

    Converts anemometer measurements taken over terrain with roughness
    length *z0a* to the equivalent wind speed over open, level terrain
    with standardised roughness at 10 m height, following one of three
    established methods.

    Scalar inputs are accepted and return a scalar; array-like or Series
    inputs return a :class:`pandas.Series`.  Mixed scalar / array inputs
    are supported: scalars are broadcast to the length of the array
    argument.

    :param ua: Wind speed measured by the anemometer [m/s].
    :type ua: int | float | list | pandas.Series
    :param ha: Height of the anemometer above ground [m].
    :type ha: int | float | list | pandas.Series
    :param z0a: Roughness length of the terrain at (or upstream from)
      the anemometer location [m].
    :type z0a: int | float | list | pandas.Series
    :param method: Correction method to apply:

      - ``'wmo'`` *(default)*: WMO-No. 8 logarithmic profile with
        extrapolation to 60 m and back [WMO8]_, equation (5.3).
        Standard roughness z0 = 0.03 m (cut grass), standard height
        z_std = 10 m, extrapolation height z_ext = 60 m.
        Flow-distortion factor *cf* = 1 and topographic factor *ct* = 1
        are assumed (free-standing mast, flat terrain).
      - ``'en'``: Eurocode 1 EN 1991-1-4:2005 [EN1991]_, equations
        (4.4) and (4.5). Reference roughness z0 = 0.05 m
        (terrain category II). Topographic correction *co* = 1.
      - ``'din'``: DIN EN 1991-1-4/NA:2010 [DIN1991]_, equation (NA.1).
        Assigns each *z0a* value to the nearest terrain category
        (I–IV) by minimising ``|log(z0_cat / z0a)|``, then applies the
        corresponding power-law exponent *alpha*.

    :type method: str, optional

    :return: Corrected wind speed at 10 m over standard open terrain [m/s].
      Returns a scalar ``float`` when all inputs are scalar, otherwise a
      :class:`pandas.Series` aligned to the index of *ua*.
    :rtype: float | pandas.Series

    :raises ValueError: If *method* is not one of the accepted values.
    :raises ValueError: If array-like arguments have incompatible lengths.

    """
    if method is None:
        method = 'wmo'

    scalar = isinstance(ua, (int, float))
    ua  = _to_series(ua, "u")
    ha = _to_series(ha, "ha", ua.index)
    z0a = _to_series(z0a, "z0", ua.index)

    # calculation...
    if method == 'wmo':
        # standard values (WM=-No. 8, Pt. I, Ch 5.9)
        #
        # standard roughness length (cut grass)
        z0_std = 0.03  # m
        # standard wind measurement height
        z_std = 10  # m
        # extrapolation height (40-80m)
        z_ext = 60  # m
        # flow distortion correction
        # "on top of a free-standing mast,
        #  flow distortion is negligible (cf=1)"
        cf = 1
        # correction factor due to topographic effects
        # "ct equals 1 for flat terrain"
        # but we dont have better info, so:
        ct = 1
        # equation (5.3)
        u10 = (ua * cf * ct *
               (np.log(z_std / z0a) / np.log(ha / z0a)) *
               ((np.log(z_ext / z0a) * np.log(z_std / z0_std)) /
                (np.log(z_std / z0a) * np.log(z_ext / z0_std)))
               )
    elif method == 'en':
        # Eurocode 1: EN 1991-1-4:2005

        # standard roughness
        z0h = 0.05  # m (terrain category II, table 4.1)
        # roughness factor
        kr = 0.19 * (z0a / z0h) ** 0.07  # eqn (4.5)
        # roughness correction
        cr = kr * np.log(ha / z0a) # eqn (4.4)
        # topography correction
        co = 1
        # corrected wind speed
        u10 = cr * co * ua
    elif method == 'din':
        # DIN EN 1991-1-4:2005
        # standard height
        zh = 10  # m
        # standard roughness
        z0h = 0.05  # m (terrain category II, table NA.B.1
        # terrain categories:
        tc = pd.DataFrame.from_records([
            ('I',0.01,0.12),
            ('II',0.05,0.16),
            ('III',0.30,0.22),
            ('IV',1.05,0.30),
        ], column=['cat', 'z0', 'alpha'])
        # get the matching (factor z0/zoa closest to 1) category
        log_z0 = np.log(tc['z0'].values)   # shape (4,)
        log_z0a = np.log(z0a.values)       # shape (n,)
        idx = np.abs(log_z0a[:, None] - log_z0[None, :]).argmin(axis=1)
        # lookup exponent alpha
        alpha = pd.Series(tc['alpha'].values[idx], index=z0a.index)
        # roughness correction (equation NA.1)
        cr = (0.19 *
              (z0a / z0h) ** 0.07 *
              np.log(zh / z0a) *
              (ha / zh) ** alpha)  # m/s
        # topography correction
        co = 1
        # corrected wind speed
        u10 = cr * co * ua
    else:
        ValueError(f"Not a valid method '{method}'")

    if scalar:
        return u10.iloc[0]
    else:
        return u10

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
        austxt = _tools.find_austxt(working_dir)
        conf = _tools.get_austxt(austxt)
    if 'z0' in conf:
        z0 = float(conf['z0'][0])
    else:
        logger.warning("no z0 defined in austal.txt")
        z0 = None
    return z0

# -------------------------------------------------------------------------

def search_logs_for_z0(working_dir) -> float | None:
    """
    Search for z0 value in AUSTAL log files.

    Searches for files 'austal.log', 'austal2000.log', or 'taldia.log'
    in working_dir and scans for lines containing z0 rounding
    information in German or English.

    :param working_dir: Directory to search for log files

    :return: z0 value as float, or None if not found
    :rtype: float | None

    :raises: UserWarning: If multiple different z0 values are found
    """

    # Define log files in priority order (reverse: highest priority first)
    log_files = ['austal2000.log', 'austal.log', 'taldia.log']

    # Regex patterns for both German and English messages
    patterns = [
        re.compile(
            r'Der Wert von z0 wird auf\s+([0-9]+\.?[0-9]*)\s+m gerundet'),
        re.compile(
            r'The value of z0 is rounded to\s+([0-9]+\.?[0-9]*)\s+m\.?')
    ]

    # Store found values with their sources
    found_values = {}  # {filename: [list of z0 values]}

    # Search through each log file
    for log_file in log_files:
        log_path = os.path.join(working_dir,log_file)

        if not os.path.exists(log_path):
            continue

        try:
            with open(log_path, 'r', encoding='utf-8',
                      errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    for pattern in patterns:
                        match = pattern.search(line)
                        if match:
                            z0_value = float(match.group(1))
                            if log_file not in found_values:
                                found_values[log_file] = []
                            found_values[log_file].append(
                                (z0_value, line_num))
        except Exception as e:
            logger.warning(f"Could not read {log_file}: {e}")
            continue

    # If nothing found
    if not found_values:
        return None

    # Collect all unique z0 values across all files
    all_z0_values = {}  # {z0_value: [(filename, line_num), ...]}

    for filename, values in found_values.items():
        for z0_value, line_num in values:
            if z0_value not in all_z0_values:
                all_z0_values[z0_value] = []
            all_z0_values[z0_value].append((filename, line_num))

    # Check for consistency
    if len(all_z0_values) > 1:
        # Multiple different values found - emit warning
        details = []
        for z0_val, sources in all_z0_values.items():
            source_str = ", ".join(
                [f"{fname}:{line}" for fname, line in sources])
            details.append(f"z0={z0_val} m found in {source_str}")

        warning_msg = (
                f"Multiple different z0 values found:\n" + "\n".join(
            details) +
                f"\nReturning value from highest priority file."
        )
        logger.warning(warning_msg, UserWarning)

    # Return value from highest priority file
    for log_file in reversed(log_files):  # Check in priority order
        if log_file in found_values:
            # Return the first value found in this file
            z0 = found_values[log_file][0][0]
            break
    else:
        return None

    return z0

