#!/bin/env python3
# -*- coding: utf-8 -*-
"""
This module allows to create time-dependent source strenght
timeseries as input for simulations with the
German regulatory dispersion model AUSTAL [AST31]_

"""
import os
import logging
import shutil
import warnings

import pandas as pd
if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import readmet
    import yaml

try:
    from . import _tools
    from ._metadata import __version__
except ImportError:
    import _tools
    from _version import __version__

# ----------------------------------------------------

logging.basicConfig()
logger = logging.getLogger(__name__)
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
    count = _tools.expand_sequence(format(info['time']))
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

def expand_cycles(yinfo):
    """
    Processes a dictionary of cycle information,
    applying templates to cycles as needed.

    This function validates the provided `yinfo`
    dictionary to ensure it contains
    the correct data structure, extracts templates,
    and applies them to the cycles.
    If a cycle specifies a template, the template is applied,
    including any emission
    factor calculations based on specified substances.

    :param dict yinfo: A dictionary containing cycle information.
      The keys represent cycle IDs and the values are dictionaries
      with specific cycle information, which can include
      'column', 'source', 'template', and 'factors'.

    :raises ValueError:

      - If `yinfo` is not a dictionary, or
      - if it contains invalid structure such as null at the top level,
      - missing template definitions for requested cycles,
      - missing emission factors for specified substances, or
      - if emission factors are present without a selected substance.

    :returns: A dictionary of processed cycles where each cycle has
      necessary attributes set such as 'multiplier', 'emissionfactor',
      and 'substance'. The keys are cycle IDs and the values are
      dictionaries containing the expanded cycle information.

    :rtype: dict

    :example:

    Consider a set of cycle information with one defined template and two cycles:

    >>> yinfo = {
    ...     'template1': {'column': None, 'source': None, 'factors': {'NOX': 1.0}},
    ...     'cycle1': {'column': '01.nox', 'template': {'name': 'template1', 'substance': 'NOX'}},
    ...     'cycle2': {'column': '01.xx'},
    ...     'cycle3': {'column': '02.nox', 'multiplier': 2.5}
    ... }
    >>> expand_cycles(yinfo)
    {
        'cycle1': {'column': '01.nox', 'source': None, 'substance': 'NOX', 'emissionfactor': 1.0, 'multiplier': 1.0},
        'cycle2': {'column': '01.xx', 'multiplier': 1.0, 'emissionfactor': 1.0, 'substance': None},
        'cycle3': {'column': '02.nox', 'multiplier': 2.5, 'emissionfactor': 1.0, 'substance': None}}

    This example demonstrates how the specified template is applied to cycle1 and cycle2
    is processed without a template.
    """
    # check if yinfo is in the right format at all
    if not isinstance(yinfo, dict):
        raise ValueError('cyclefile top-level is not associative list')
    if None in yinfo.keys():
        raise ValueError('cyclefile top-level names contain null')

    templates = {}
    # collect templates
    for c_id, c_info in yinfo.items():
        if (('column' not in c_info.keys() or c_info['column'] is None)
            # the following condition must be dropped,
            # when the support for the deprecated keyword `source` is removed
            and
            ('source' not in c_info.keys() or c_info['source'] is None)):
            logger.debug(f"found template: {c_id}")
            templates[c_id] = c_info

    cycles = {}
    # collect cycles and apply template where needed
    for c_id, c_info in yinfo.items():
        if c_id in templates.keys():
            continue
        else:
            logger.debug(f"found cycle: {c_id}")
        if "template" not in c_info.keys() or c_info['template'] is None:
            # no template
            logger.debug(f"... no template requested")
            cycle = c_info
            cycle['multiplier'] = 1.
            cycle['emissionfactor'] = 1.
            cycle['substance'] = None
        else:
            # get template
            t_info = c_info['template']
            t_name = t_info.get('name', None)
            if t_name not in templates.keys():
                raise ValueError(f'requested template {t_name}'
                                 f'is not defined in cycle {c_id}')
            else:
                logger.debug(f'... applying template {t_name}')
                template = templates[t_name]
                cycle = template.copy()
                cycle['column'] = c_info['column']

            # get substance
            # defaults to column name suffix (e.g. `02.so2` -> `so2`)
            # if not given under keyword 'substance'
            if '.' in cycle['column']:
                suffix = cycle['column'].split('.')[-1]
            else:
                suffix = None
            substance = t_info.get('substance', suffix)
            # get emission factor
            if substance is not None and 'factors' in template:
                if t_info['substance'] in template['factors'].keys():
                    logger.debug(f'... selecting emission factor '
                                 f"for: {t_info['substance']}")
                    cycle['substance'] = t_info['substance']
                    cycle['emissionfactor'] = float(
                        template['factors'][t_info['substance']])
                    del cycle['factors']
                else:
                    raise ValueError(
                        f'requested substance {substance}'
                        f'is not defined in template {t_name} '
                        f'in cycle {c_id}')
            elif substance is None and 'factors' not in template:
                logger.debug(f'... no emission factor')
                cycle['substance'] = None
                cycle['emissionfactor'] = 1.
            elif substance is not None and 'factors' not in template:
                raise ValueError(
                    f'no emssion factor for {substance} '
                    f'defined in template: {t_name}')
            else: # 'substance' not in t_info and 'factors' in template
                raise ValueError(
                    f'emssion factors defined in template: {t_name}'
                    f' but no substance selected in cycle: {c_id}')

            # if 'multiplier' in t_info:
            #     logger.debug(f'... applying additional multiplier: '
            #                  f"{t_info['multiplier']}")
            #     cycle['multiplier'] = float(t_info['multiplier'])
            # else:
            #     cycle['multiplier'] = 1.
            # logger.debug(f'... applying additional multiplier:'
            #              f' {cycle["multiplier"]}')
        cycles[c_id] = cycle
    return cycles

# ----------------------------------------------------

def parse_cycle(c_id: str, c_info : dict,
                time: pd.DatetimeIndex) -> pd.Series:
    """
    Parse cycle information and
    generate an emission time series.

    :param c_id: Cycle identifier
    :type c_id: str
    :param c_info: Cycle information dictionary.
         Must contain the keys:

         - "column": str, column identifier (must not be equal to c_id)
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
        - if ``c_info`` does not contain the referred column name
        - if the cycle name ``c_id`` is equal to the column name
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
    :return: Column identifier and generated cycle series
    :rtype: tuple (str, pandas.Series)

    :example:

        >>> import pandas as pd
        >>> c_id = "foo"
        >>> c_info = {'column': '01.so2',
        ...   'start': {'at': {'time': '1-11/2', 'unit': 'month'},
        ...   'offset': {'time': '1,3', 'unit': 'week'}},
        ...   'sequence': [
        ...     {'ramp': {'time': 1, 'unit': 'day', 'value': 9.0}
        ...    },
        ...    {'const': {'time': 36, 'unit': 'hour', 'value': 1.1}}]}
        >>> time = pd.date_range("2000-01-01 00:00",
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
    if not isinstance(time, pd.DatetimeIndex):
        time = pd.DatetimeIndex(pd.to_datetime(time))
    if time.tz is None:
        logger.info("time passed without time zone, assuming UTC")
        time = time.tz_localize("UTC")
    dt = time.to_series().diff()[1:].unique()
    if len(dt) > 1:
        raise ValueError('time intervals are not uniform')
    dt = pd.Timedelta(dt[0])

    if 'source' in c_info.keys():
        #
        # when removing this, also remove reference to "source"
        # in expand_cycles where templates are collected
        #
        c_info['column'] = c_info['source']
        del c_info['source']
        warnings.warn('key "source" is accepted for now,'
                      'but is deprecated, '
                      'use "column" instead',
                      category=DeprecationWarning)
    if 'column' not in c_info.keys():
        raise ValueError('cycle has no column info: %s' % c_id)
    column = c_info['column']
    if column == c_id:
        raise ValueError('cycle name equal to column name: %s' % c_id)

    if 'factors' in c_info.keys():
        raise ValueError('cycle has illegal factors key: %s' % c_id)
    if 'template' in c_info.keys():
        raise ValueError('cycle has illegal template key: %s' % c_id)

    ts_data = None
    if "timeseries" in c_info.keys():
        ts_info = c_info['timeseries']
        if 'file' in ts_info.keys():
            ts_file_name = ts_info['file']
            tf_file_format = ts_info.get('format', 'csv')
            ts_var = ts_info.get('var')
            if tf_file_format == 'csv':
                ts_data = pd.read_csv(ts_file_name,
                                      index_col=0,
                                      parse_dates=True
                                      )
            else:
                
                raise ValueError(f"unsupported format {tf_file_format} "
                                 f"in file: {ts_file_name}")
            if ts_data.index.tz is None:
                logger.info("time in file has not time zone, assuming UTC")
                ts_data.index = ts_data.index.tz_localize("UTC")
            ts_columns = ts_data.columns
            if not ts_var in ts_columns:
                
                raise ValueError(f"no var named `{ts_var}` "
                                 f"in: {ts_file_name}")

        elif 'table' in ts_info.keys():
            if 'columns' in ts_info.keys():
                ts_columns = ts_info['columns']
            else:
                ts_columns = None
            ts_var = ts_info.get('var')
            ts_data = pd.DataFrame(
                [x.strip().split(',') for x in ts_info['data']],
                columns=ts_columns
            )
    else:
        ts_data = None
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
        num_keys = any([x in c_info.keys() for x in
                    ["sequence", "list"]])
        if num_keys < 1:
            raise ValueError('cycle has no sequence info: %s' % c_id)
        elif num_keys > 1:
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
                    raise ValueError(f'sequence item entry #{i} '
                                     f'not unique: {c_id}')
                for s_type, s_info in s_item.items():
                    if "value" not in s_info.keys():
                        raise ValueError(f'sequence no value info: '
                                         f'{c_id}')
                    s_value = s_info['value']
                    s_count, s_unit = parse_time(
                        s_info,name='sequence', multi=False)
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
                            raise ValueError(f'unknown sequence '
                                             f'element: {s_type}')
                        time_pointer = time_pointer + dt

                    time_last = time_pointer
                    value_last = s_value
            sequence = pd.Series(sequ_value, index=sequ_time)
        elif "list" in c_info.keys():
            if not isinstance(c_info['list'], list):
                raise ValueError('list does not contain list: %s' % c_id)
            sequ_value = [float(x) for x in c_info['list']]
            sequ_time = [i * dt for i in range(len(sequ_value))]
            sequence = pd.Series(sequ_value, index=sequ_time)



    if 'emissionfactor' in c_info.keys():
        emissionfactor = c_info['emissionfactor']
        unit_info = c_info.get("unit", "---")
        logger.info(f'cycle {c_id} given in {unit_info}, ' +
                f'applying emission factor: {emissionfactor}')
    else:
        emissionfactor = 1.

    if "unit" in c_info.keys():
        factor_w = factor_t = None
        unit_info = c_info["unit"]
        if "/" in unit_info:
            # split unit into mass and time interval
            try:
                unit_w, unit_t = unit_info.split("/")
            except ValueError:
                
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
                
                raise ValueError('invalid time unit: %s' % unit_t)
        unitfactor = factor_w * factor_t
    else:
        unit_info = "g/s"
        unitfactor = 1.
    logger.info(f'cycle {c_id} given in {unit_info}, ' +
                f'applying conversion factor: {unitfactor}')

    if 'multiplier' in c_info.keys():
        multiplier = c_info['multiplier']
        logger.info(f"cycle {c_id} given in {unit_info}, " +
                    f"applying cycle multiplier: {multiplier}")
    else:
        multiplier = 1.
        logger.info(f"cycle {c_id} given in {unit_info}, " +
                    f"no cycle multiplier (applying 1.0)")

    effective_factor = unitfactor * emissionfactor * multiplier
    logger.debug(f"effective factor: {effective_factor}")
    # generate cycle:
    if ts_data is None:
        # check start times
        if (len(start) > 1 and
                any([x < sequence.index[-1] for x in start.diff()[1:]])):
            logger.warning(
                'sequence longer than start interval: %s' % c_id)
        if (start.values[-1] + sequence.index[-1]) > time.values[-1]:
            logger.warning('total length > time period to fill: %s' % c_id)

        # copy sequence to each start time
        # covert units in the process
        cycle = pd.Series(0, index=time, name=c_id, dtype=float)
        for x in start:
            for dx, y in sequence.items():
                cycle[x + dx] = (
                        y * effective_factor
                )
    else:
        cycle = ts_data[ts_var].resample(dt, origin=time[0]).mean()
        cycle = cycle * effective_factor
        cycle.name = c_id
    return column, cycle
# ----------------------------------------------------


# noinspection SpellCheckingInspection
def get_timeseries(file: str, time: pd.DatetimeIndex):
    """
    Parse yaml file containing cycle(s) information and
    generate an emission time series.

    This funtion is essentially a wrapper that applies
    for :py:func:`parse_cycle` to a yaml file.

    :param file: filename (optionally containing a path)
    :type file: str
    :param time: Time series
    :type time: pandas.Series

    :return: time series of emssions of all emissions descrcibed in file
    :rtype: pandas.Dataframe with `time` as index and column-ids as colums

    :example:

        >>> yaml_text = '''
        ... meinname:
        ...   column: 01.so2
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

    # test and prepare time
    if not type(time) in [list, pd.Series, pd.DatetimeIndex]:
        raise ValueError('time is not list-like')
    if not isinstance(time, pd.DatetimeIndex):
        time = pd.DatetimeIndex(pd.to_datetime(time))
    if time.tz is None:
        logger.info("time passed without time zone, assuming UTC")
        time = time.tz_localize("UTC")

    # prepare output
    res = pd.DataFrame(index=time)

    # get cycle info
    cycles = expand_cycles(yinfo)
    for c_id, c_info in cycles.items():
        logger.info('working on cycle: %s' % c_id)
        column, cycle = parse_cycle(c_id, c_info, time)

        # add cyle as / to column
        # if column does not yet exist yet:
        if column not in res.columns:
            # make new all-zero column
            res[column] = 0.
        # temporarily add cycle as column `c_id`
        res = res.join(cycle)
        # add temporary column `c_id` to column
        res[column] = res[column] + res[c_id]
        # drop temporary column `c_id`
        res = res.drop(c_id, axis=1)

    return res

# ----------------------------------------------------


# noinspection SpellCheckingInspection
def main(args):
    r"""
    Process the data file based on the provided arguments.

    :param args: Dictionary containing the following keys:
    :type args: dict
    :param args["action"]: (str) -- The action to perform.
      Possible values are 'list', 'week-5', 'week-6', or 'cycle'.
    :param args["cycle_file"]: (str) -- The name of the cycle file
     (required for 'cycle' action).
    :param args["holiday_month"]: (\*list, optional) --
      List of months (1-12) considered as holidays.
    :param args["holiday_week"]: (\*list, optional) -- List of weeks
      (1-52) considered as holidays.
    :param args["hour_begin"]: (int, optional) --
      The daily start of the working time,
      i.e. the first hour of each working day
      the source emits pollutants
      (evaluated for 'week-5' and 'week-6' actions).
      Defaults to :py:const:`DEFAULT__BEGIN`.
    :param args["hour_end"]: (int, optional) --
      The daily end of the working time,
      i.e. the last hour of each working day
      the source emits pollutants
      (evaluated for 'week-5' and 'week-6' actions).
      Defaults to :py:const:`DEFAULT_END` .
    :param args["column_id"]: (str) -- The column ID to process
      (required for 'week-5' and 'week-6' actions).
    :param args["output"]: (list) -- The source strength (in g/s)
      when the source is emitting
      (required for 'week-5' and 'week-6' actions).
    :param args["working_dir"]: (str) -- The path
      to the directory containing the data file.
      The datafile is named ``zeitreihe.dmna`` or
      ``timeseries.dmna``, depending on the language setting
      of the AUSTAL model.

    :raises ValueError: If the data file is not in DMNA timeseries format.
    :raises ValueError: If the action is unknown.
    :raises ValueError: If required arguments are missing or invalid.

    :note: the datafile ``zeitreihe.dmna``/``timeseries.dmna`` must be
      created by invoking AUSTAL with paramter ``-z``
    """
    #
    logger.debug('args: %s' % args)
    #
    name = os.path.join(args["working_dir"], 'zeitreihe.dmna')
    bck = name + '~'
    logger.info(f"creating backup copy {bck}")
    shutil.copyfile(name, bck)
    #
    logger.info(f"reading new file {name}")
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
        logger.info('listing columns in file')
        print('column IDs: ' + ' '.join(sids))
        return
    elif args["action"] in ['week-5', 'week-6']:
        logger.info('filling work weeks for column: %s' % args["column_id"])
        if args["output"] is None:
            
            raise ValueError('-o is required with -w or -W')
        if args["column_id"] not in sids:
            if len(sids) == 1:
                args["column_id"] = sids[0]
            else:
                
                raise ValueError('column ID not in file: %s' % args["column_id"])
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
                    values.loc[i, args["column_id"]] = float(
                        args["output"][0])
    elif args["action"] in ['cycle']:
        cyclefile = os.path.join(args["working_dir"], args["cycle_file"])
        logger.info('filling cycles from: %s' % cyclefile)
        tss = get_timeseries(cyclefile, zeitreihe.data['te'])
        for c in _tools.progress(tss.columns, desc="applying cycle"):
            if c in values.columns:
                values[c] = tss[c].values
            else:
                raise ValueError('column not in zeitreihe: %s' % c)
    else:
        raise ValueError('unknown action: %s' % args["action"])
    zeitreihe.data = values

    logger.info(f"writing new file {name}")
    zeitreihe.write(name)

# ----------------------------------------------------

def add_options(subparsers):
    pars_fts = subparsers.add_parser(
        name='fill-timeseries',
        aliases=['ft'],
        help='fill source-strength columns in "zeitreihe.dmna"'
    )
    default = {'hour-begin': 8,
               'hour-end': 16,
               'cycle-file': 'cycle.yaml',
               'holiday-week': [25, 26, 27, 28, 29, 30, 52],
               'holiday-month': [7],
               }
    sched = pars_fts.add_mutually_exclusive_group(required=True)
    sched.add_argument('-l', '--list',
                       action='store_const', dest='action', const='list',
                       help='list column column IDs in file' +
                            'and exit without modifying ' +
                            '"zeitreihe.dmna". [default]')
    sched.add_argument('-c', '--cycle',
                       action='store_const', dest='action', const='cycle',
                       help='use production cycle from file')
    sched.add_argument('-w', '--week-5',
                       action='store_const', dest='action', const='week-5',
                       help='source active Mon-Fri')
    sched.add_argument('-W', '--week-6',
                       action='store_const', dest='action', const='week-6',
                       help='source active Mon-Sat')
    pars_fts.add_argument('-b', '--hour-begin', metavar='HOUR',
                          nargs=1,
                          help='daily work begin time in hours 0-23. ' +
                               'Only relevant with -w or -W. ' +
                               '[%02i]' % DEFAULT_BEGIN,
                          default=DEFAULT_BEGIN)
    pars_fts.add_argument('-e', '--hour-end', metavar='HOUR',
                          nargs=1,
                          help='daily work end time in hours, ' +
                               '0-23. Only relevant with -w or -W .' +
                               '[%02i]' % DEFAULT_END,
                          default=DEFAULT_END)
    hold = pars_fts.add_mutually_exclusive_group()
    hold.add_argument('-u', '--holiday-week', nargs="+",
                      help='work-free weeks 1-52 as space-delimited list. ' +
                           'Only relevant with -w or -W. [' +
                           ' '.join(['%d' % x
                                     for x in default['holiday-week']]) +
                           ']',
                      default=default['holiday-week'])
    hold.add_argument('-U', '--holiday-month', nargs="+",
                      help='work-free months as space-delimited list' +
                           '(1-12). Only relevant with -w or -W. ' +
                           ' '.join(['%d' % x
                                     for x in default['holiday-month']]) +
                           ']',
                      default=default['holiday-month'])
    pars_fts.add_argument('-f', '--cycle-file',
                          help='emission-cycle description file. ' +
                               'only relevant with -c. ' +
                               '[%s]' % default['cycle-file'],
                          default=default['cycle-file'])
    pars_fts.add_argument('-s', '--column-id',
                          help='column ID. ' +
                               'Required if more than one column. ' +
                               'list IDs in file with -l.',
                          default=None)
    pars_fts.add_argument('-o', '--output', nargs=1,
                          help='output for the column in g/s. ' +
                               '-o is relevant with -w or -W. ',
                          default=None)

    return pars_fts