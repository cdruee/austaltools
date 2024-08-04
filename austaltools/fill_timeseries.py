#!/bin/env python3
# -*- coding: utf-8 -*-
"""
This module allows to create time-dependent source strenght
timeseries as input for simulations with the
German regulatory dispersion model AUSTAL [AST31]_

"""
import os
import logging
import sys

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import pandas as pd
    import readmet
    import yaml

try:
    from . import _tools
    from ._version import __version__
except ImportError:
    import _tools
    from _version import __version__

# ----------------------------------------------------

logging.basicConfig()
logger = logging.getLogger()
# ----------------------------------------------------

DEFAULT_BEGIN = 8
"""
Default staring hour for a workday 
(first hour during which emsssions are created)
"""

DEFAULT_END = 17
"""
Default end hour for a workday
(last hour during which emsssions are created)
"""


# ----------------------------------------------------

def parse_time_unit(string):
    """
    Parse a string and determine which time unit it describes:
    - 'month', 'months', 'mon' for months
    - 'day', 'days', 'd' for days
    - 'hour', 'hours', 'hr', 'hrs', 'h' for hours

    :param string: the string to parse
    :type string: str
    :return: the parsed time unit
    :rtype: str
    """
    if string.lower() in ['month', 'months', 'mon']:
        period = 'months'
    elif string.lower() in ['week', 'weeks', 'w']:
        period = 'weeks'
    elif string.lower() in ['day', 'days', 'd']:
        period = 'days'
    elif string.lower() in ['hour', 'hours', 'hr', 'hrs', 'h']:
        period = 'hours'
    else:
        raise ValueError('parse unit: unknown: %s' % string)
    return period
# ----------------------------------------------------


def parse_time(info, name='', multi=True):
    """
    Parse time information from a given dictionary.

    The dictionary `info` must contain the following keys:
    - 'time': A string representing the time information.
    - 'unit': A string representing the unit of time.

    :param info: Dictionary containing time information.
    :type info: dict
    :param name: Optional name for the time info, used in error messages.
    :type name: str
    :param multi: Flag indicating whether multiple times are allowed.
    :type multi: bool
    :raises ValueError:
      If 'time' or 'unit' keys are missing in the info dictionary.
    :raises ValueError:
      If multiple times are defined when multi is False.
    :return: A tuple containing the parsed time count and unit.
    :rtype: tuple
    """
    if "time" not in info.keys():
        raise ValueError('no time info: %s' % name)
    count = _tools.parse_sequence_string(format(info['time']))
    logger.debug('count: ' + format(count))
    if "unit" not in info.keys():
        raise ValueError('no unit info: %s' % name)
    unit = parse_time_unit(info['unit'])
    logger.debug('unit: ' + format(unit))
    if not multi:
        if len(count) > 1:
            raise ValueError('multiple times defined: %s' % name)
        else:
            count = count[0]
    return count, unit
# ----------------------------------------------------


def parse_cycle(c_id, c_info, time):
    """
    Parse cycle information and
    generate an emission time series.

    :param c_id: Cycle identifier
    :type c_id: str
    :param c_info: Cycle information dictionary.
         Must contain the keys:

         - "source": str, source identifier (must not be equal to c_id)
         - "start": dict, must contain:
           - "at": str, start time information
           - "offset" (optional): str, offset time information
         - "sequence" or "list": list, sequence or list of values
         - "unit" (optional): str, unit information in the
           format "<mass unit>/<time interval>"
    :type c_info: dict
    :param time: Time series
    :type time: pandas.Series

    :raises ValueError: If required keys are missing or invalid values are
        found in c_info. Possible errors include:

        - if time is an invalid type or time series
          does not have a unique interval
        - if ``c_info`` does not contain the referred source name
        - if the cycle name ``c_id`` is equal to the source name
        - if ``c_info`` has neithert none or both of
          a ``cycle`` or ``list`` entry
        - if ``c_info`` has not ``start`` entry
        - if the ``start`` entry is not a dict or
          does not contain an ``at`` entry
        - 'sequence' item contains more or less than one entry
          or the entry cannot be parsed
        - ``c_info['list']`` does not contain a list
        - the unit info in ``c_info['unit']s`` cannot be parsed
        - the mass unit in ``c_info['unit']`` is not al valid weight unit
        - the time interval in ``c_info['unit']`` is not a valid time unit
    :return: Source identifier and generated cycle series
    :rtype: tuple (str, pandas.Series)

    :example:

        >>> c_id = "foo"
        >>> c_info = {'source': '01.so2',
        ...   'start': {'at': {'time': '1-11/2', 'unit': 'month'},
        ...   'offset': {'time': '1,3', 'unit': 'week'}},
        ...   'sequence': [
        ...     {'ramp': {'time': 1, 'unit': 'day', 'value': 9.0}
        ...    },
        ...    {'const': {'time': 36, 'unit': 'hour', 'value': 1.1}}]}
        >>> time = pandas.date_range("2000-01-01 00:00",
        ...                          "2000-01-02 00:00", freq="1h")
        >>> fill_timeseries.parse_cycle(c_id, c_info, time)
            ('01.so2',
             2000-01-01 00:00:00    0.0
             2000-01-01 01:00:00    0.0
             2000-01-01 02:00:00    0.0
             2000-01-01 03:00:00    0.0
             2000-01-01 04:00:00    0.0
                                   ...
             2000-12-24 07:00:00    1.1
             2000-12-24 08:00:00    1.1
             2000-12-24 09:00:00    1.1
             2000-12-24 10:00:00    1.1
             2000-12-24 11:00:00    1.1
             Name: foo, Length: 745, dtype: float64)

    """
    # test and evaluate time
    if not type(time) in [list, pd.Series, pd.DatetimeIndex]:
        raise ValueError('time is not list-like')
    time = pd.to_datetime(time)
    dt = time.diff()[1:].unique()
    if len(dt) > 1:
        raise ValueError('time intervals are not uniform')
    dt = pd.Timedelta(dt[0])

    # parse source
    if "source" not in c_info.keys():
        raise ValueError('cycle has no source info: %s' % c_id)
    source = c_info['source']
    if source == c_id:
        raise ValueError('cycle name equal to source name: %s' % c_id)
    if "start" not in c_info.keys():
        raise ValueError('cycle has no start info: %s' % c_id)
    s_info = c_info['start']
    if "at" not in s_info.keys():
        raise ValueError('start has no at info: %s' % c_id)
    a_count, a_unit = parse_time(s_info['at'], name='at', multi=True)
    a_time = [time[0] + pd.DateOffset(**{a_unit: x}) for x in a_count]
    logger.debug('a_time: ' + format(a_time))

    if "offset" not in s_info.keys():
        logger.info('cycle start has no offset info: %s' % c_id)
        o_time = [pd.DateOffset(0)]
    else:
        o_count, o_unit = parse_time(s_info['offset'],
                                     name='offset', multi=True)
        o_time = [pd.DateOffset(**{o_unit: x}) for x in o_count]
    logger.debug('o_time: ' + format(o_time))
    start = pd.Series([x + y for x in a_time for y in o_time])
    logger.debug('start: ' + format(start))

    sequence = None
    if "sequence" not in c_info.keys() and "list" not in c_info.keys():
        raise ValueError('cycle has no sequence info: %s' % c_id)
    if "sequence" in c_info.keys() and "list" in c_info.keys():
        raise ValueError('cycle list and sequence are ' +
                         'mutually exclusive: %s' % c_id)
    if "sequence" in c_info.keys():
        sequ_time = []
        sequ_value = []
        time_pointer = pd.Timedelta(0)
        time_last = time_pointer
        value_last = 0
        for i, s_item in enumerate(c_info['sequence']):
            logger.debug(format(s_item))
            if len(s_item) > 1:
                raise ValueError('sequence item entry #%d not unique: %s' %
                                 (i, c_id))
            for s_type, s_info in s_item.items():
                if "value" not in s_info.keys():
                    raise ValueError('sequence no value info: %s' % c_id)
                s_value = s_info['value']
                s_count, s_unit = parse_time(s_info,
                                             name='sequence', multi=False)
                s_delta = pd.Timedelta(value=s_count, unit=s_unit)
                while time_pointer < time_last + s_delta:
                    sequ_time.append(time_pointer)
                    if s_type == 'const':
                        sequ_value.append(s_value)
                    elif s_type == 'ramp':
                        x = (value_last +
                             (s_value - value_last) *
                             (time_pointer - time_last) / s_delta)
                        sequ_value.append(x)
                    else:
                        raise ValueError('unknown sequence element: %s' %
                                         s_type)
                    time_pointer = time_pointer + dt

                time_last = time_pointer
                value_last = s_value
        sequence = pd.Series(sequ_value, index=sequ_time)
    if "list" in c_info.keys():
        if not isinstance(c_info['list'], list):
            raise ValueError('list does not contain list: %s' % c_id)
        sequ_value = [float(x) for x in c_info['list']]
        sequ_time = [i * dt for i in range(len(sequ_value))]
        sequence = pd.Series(sequ_value, index=sequ_time)
    logger.debug(format(sequence))

    if "unit" in c_info.keys():
        factor_w = factor_t = None
        unit_info = c_info["unit"]
        if "/" in unit_info:
            # split unit into mass and time interval
            try:
                unit_w, unit_t = unit_info.split("/")
            except ValueError:
                sys.tracebacklimit = 0
                raise ValueError('invalid unit info: %s' % unit_info)
            # parse mass
            if unit_w == "t":
                factor_w = 1.E+6
            elif unit_w == "kg":
                factor_w = 1.E+3
            elif unit_w == "g":
                factor_w = 1.
            elif unit_w == "mg":
                factor_w = 1.E-3
            elif unit_w in ["ug", "µg"]:
                factor_w = 1.E-6
            else:
                sys.tracebacklimit = 0
                raise ValueError('invalid weight unit: %s' % unit_w)
            # parse time interval
            if unit_t == "total":
                factor_t = 1./float(len(time)*3600)
            elif unit_t == "d":
                factor_t = 1./(24.*3600.)
            elif unit_t == "h":
                factor_t = 1./3600.
            elif unit_t == ["m", "min"]:
                factor_t = 1./60.
            elif unit_t in ["s", "sec"]:
                factor_t = 1.
            else:
                sys.tracebacklimit = 0
                raise ValueError('invalid time unit: %s' % unit_t)
        factor = factor_w * factor_t
    else:
        unit_info = "g/s"
        factor = 1.
    logger.info(f'cycle {c_id} given in {unit_info}, ' +
                f'applying conversion factor: {factor}')

    if any([x < sequence.index[-1] for x in start.diff()[1:]]):
        logger.warning('sequence longer than start interval: %s' % c_id)
    if (start.values[-1] + sequence.index[-1]) > time.values[-1]:
        logger.warning('total length > time period to fill: %s' % c_id)

    # generate cycle:
    # copy sequence to each start time
    # covert units in the process
    cycle = pd.Series(0, index=time, name=c_id, dtype=float)
    for x in start:
        for dx, y in sequence.items():
            cycle[x + dx] = y * factor

    return source, cycle
# ----------------------------------------------------


# noinspection SpellCheckingInspection
def get_cycle(file, time):
    """
    Parse yaml file containing cycle(s) information and
    generate an emission time series.

    This funtion is essentially a wrapper that applies
    for :py:func:`parse_cycle` to a yaml file.

    :param file: filename (optionally containing a path)
    :type file: str
    :param time: Time series
    :type time: pandas.Series

    :return: time series of emssions of all sources descrcibed in file
    :rtype: pandas.Dataframe with `time` as index and sources as colums

    :example:

        >>> yaml_text = '''
        ... meinname:
        ...   source: 01.so2
        ...   start:
        ...     at:
        ...       time: 1-11/2
        ...       unit: month
        ...     offset:
        ...       time: 1,3
        ...       unit: week
        ...   sequence:
        ...   - ramp:
        ...       time: 1
        ...       unit: day
        ...       value: 9.0
        ...   - const:
        ...       time: 36
        ...       unit: hour
        ...       value: 1.1
        ...'''
        >>> with open("cycle.yaml, "w") as f:
        >>>     f.write(yaml_text)
        >>> time = pandas.date_range("2000-01-01 00:00",
        ...                          "2000-01-02 00:00", freq="1h")
        >>> get_cycle(file, time)
            ('01.so2',
             2000-01-01 00:00:00    0.0
             2000-01-01 01:00:00    0.0
             2000-01-01 02:00:00    0.0
             2000-01-01 03:00:00    0.0
             2000-01-01 04:00:00    0.0
                                   ...
             2000-12-24 07:00:00    1.1
             2000-12-24 08:00:00    1.1
             2000-12-24 09:00:00    1.1
             2000-12-24 10:00:00    1.1
             2000-12-24 11:00:00    1.1
             Name: foo, Length: 745, dtype: float64)

    :note:

    The format of the yaml file is described
    under :ref:`variable values`

    """

    # read cycle file
    with open(file, 'r') as f:
        yinfo = yaml.safe_load(f)
    logger.debug(format(yinfo))

    # prepare output
    res = pd.DataFrame(index=time)

    # get cycle info
    if not isinstance(yinfo, dict):
        raise ValueError('cyclefile top-level is not associative list')
    for c_id, c_info in yinfo.items():
        logger.info('working on cycle: %s' % c_id)
        source, cycle = parse_cycle(c_id, c_info, time)

        # add cyle as column or add values to existing column
        if source not in res.columns:
            res[source] = 0.
        res = res.join(cycle)
        res[source] = res[source] + res[c_id]
        res = res.drop(c_id, axis=1)

    return res

# ----------------------------------------------------


# noinspection SpellCheckingInspection
def main(args):
    """
    Process the data file based on the provided arguments.

    :param args: Dictionary containing the following keys:
    :type args: dict
    :param args["path"]: (str) -- The path
      to the directory containing the data file.
      The datafile is named ``zeitreihe.dmna`` or
      ``timeseries.dmna``, defending on the language setting
      of the AUSTAL model.
    :param args["action"]: (str) -- The action to perform.
      Possible values are 'list', 'week-5', 'week-6', or 'cycle'.
    :param args["source_id"]: (str) -- The source ID to process
      (required for 'week-5' and 'week-6' actions).
    :param args["output"]: (list) -- The source strength (in g/s)
      when the source is emitting
      (required for 'week-5' and 'week-6' actions).
    :param args["hour_begin"]: (*int, optional) --
      The daily start of the working time,
      i.e. the first hour of each working day
      the source emits pollutants
      (evaluated for 'week-5' and 'week-6' actions).
      Defaults to :py:const:`DEFAULT__BEGIN`.
    :param args["hour_end"]: (*int, optional) --
      The daily end of the working time,
      i.e. the last hour of each working day
      the source emits pollutants
      (evaluated for 'week-5' and 'week-6' actions).
      Defaults to :py:const:`DEFAULT_END` .
    :param args["holiday_month"]: (*list, optional) --
      List of months (1-12) considered as holidays.
    :param args["holiday_week"]: (*list, optional) -- List of weeks
      (1-52) considered as holidays.
    :param args["cycle_file"]: (str) -- The name of the cycle file
     (required for 'cycle' action).

    :raises ValueError: If the data file is not in DMNA timeseries format.
    :raises ValueError: If the action is unknown.
    :raises ValueError: If required arguments are missing or invalid.

    :note: the datafile ``zeitreihe.dmna``/``timeseries.dmna`` must be
      created by invoking AUSTAL with paramter ``-z``
    """
    #
    logger.debug('args: %s' % args)
    #
    name = os.path.join(args["path"], 'zeitreihe.dmna')
    zeitreihe = readmet.dmna.DataFile(file=name)
    if zeitreihe.filetype != 'timeseries':
        raise ValueError('is not dmna timeseries format: %s' % name)
    logger.info('working on file: %s' % name)
    variables = zeitreihe.variables
    sids = []
    for x in variables:
        if x not in ['te', 'ra', 'ua', 'lm']:
            sids.append(x)
    values = zeitreihe.data
    if args["action"] == 'list':
        logger.info('listing sources in file')
        print('source IDs: ' + ' '.join(sids))
        return
    elif args["action"] in ['week-5', 'week-6']:
        logger.info('filling work weeks for source: %s' % args["source_id"])
        if args["output"] is None:
            sys.tracebacklimit = 0
            raise ValueError('-o is required with -w or -W')
        if args["source_id"] not in sids:
            if len(sids) == 1:
                args["source_id"] = sids[0]
            else:
                sys.tracebacklimit = 0
                raise ValueError('source ID not in file: %s' % args["source_id"])
        if None in [args["hour_begin"], args["hour_end"], args["output"]]:
            raise ValueError('hour_begin, hour_end, or output is None')
        if args["holiday_month"] is None:
            args["holiday_month"] = []
        if args["holiday_week"] is None:
            args["holiday_week"] = []
        time = pd.to_datetime(values['te'])
        for i, t in enumerate(_tools.progress(time, desc="work weeks")):
            if t.month in args["holiday_month"]:
                continue
            if t.week in args["holiday_week"]:
                continue
            if ((args["action"] == 'week-5' and 0 <= t.weekday() < 5) or
                    (args["action"] == 'week-6' and 0 <= t.weekday() < 6)):
                if args["hour_begin"] <= t.hour <= args["hour_end"]:
                    values.loc[i, args["source_id"]] = float(args["output"][0])
    elif args["action"] in ['cycle']:
        cyclefile = os.path.join(args["path"], args["cycle_file"])
        logger.info('filling cycles from: %s' % cyclefile)
        cycle = get_cycle(cyclefile, zeitreihe.data['te'])
        for c in _tools.progress(cycle.columns, desc="applying cycle"):
            if c in values.columns:
                values[c] = cycle[c].values
            else:
                raise ValueError('source not in zeitreihe: %s' % c)
    else:
        raise ValueError('unknown action: %s' % args["action"])
    zeitreihe.data = values
    zeitreihe.write(name)
