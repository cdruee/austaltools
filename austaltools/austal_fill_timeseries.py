#!/bin/env python3

import argparse
import os
import logging
import sys

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import pandas as pd
    import readmet
    import yaml

try:
    from . import _tools
except ImportError:
    import _tools

try:
    from ._version import __version__
except ImportError:
    from _version import __version__
# ----------------------------------------------------

logging.basicConfig()
logger = logging.getLogger()
# ----------------------------------------------------


def parse_time_string(string):
    logger.debug('parse_time_string: %s' % string)
    for x in string:
        if x not in ['-', ',', '/'] and not x.isdigit():
            raise ValueError('parse time: illegal character in string: %s' % x)
    if '/' in string and ',' in string:
        raise ValueError('parse time: list and step are mutually exclusive')
    if '-' in string and ',' in string:
        raise ValueError('parse time: list and range are mutually exclusive')
    if '/' in string:
        rang, step = string.split('/', 1)
        step = int(step)
    else:
        rang = string
        step = 1
    if '-' in rang:
        start_stop = [int(x) for x in rang.split('-', 1)]
        discrete = None
    elif ',' in rang:
        start_stop = None
        discrete = [int(x) for x in rang.split(',')]
        if not sorted(discrete) == discrete:
            raise ValueError('parse time: discrete list is not sorted')
    else:
        start_stop = None
        discrete = [int(rang)]
    if start_stop:
        res = []
        x = start_stop[0]
        while x <= start_stop[1]:
            res.append(x)
            x = x + step
    else:
        res = discrete
    return res
# ----------------------------------------------------


def parse_time_unit(string):
    if string.lower() in ['month', 'months']:
        period = 'months'
    elif string.lower() in ['week', 'weeks']:
        period = 'weeks'
    elif string.lower() in ['day', 'days']:
        period = 'days'
    elif string.lower() in ['hour', 'hours']:
        period = 'hours'
    else:
        raise ValueError('parse unit: unknown: %s' % string)
    return period
# ----------------------------------------------------


def parse_time(info, name='', multi=True):
    if "time" not in info.keys():
        raise ValueError('no time info: %s' % name)
    count = parse_time_string(format(info['time']))
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


def parse_cycle(c_id, c_info, time, dt):
    if "source" not in c_info.keys():
        raise ValueError('cycle has no start info: %s' % c_id)
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

    if any([x < sequence.index[-1] for x in start.diff()[1:]]):
        logger.warning('sequence longer than start interval: %s' % c_id)
    if (start.values[-1] + sequence.index[-1]) > time.values[-1]:
        logger.warning('total length > time period to fill: %s' % c_id)

    # generate cycle:
    # copy sequence to each start time
    cycle = pd.Series(0, index=time, name=c_id, dtype=float)
    for x in start:
        for dx, y in sequence.items():
            cycle[x + dx] = y

    return source, cycle
# ----------------------------------------------------


# noinspection SpellCheckingInspection
def get_cycle(file, time):
    # test and evaluate time
    if not type(time) in [list, pd.Series]:
        raise ValueError('time is not list-like')
    time = pd.to_datetime(time)
    dt = time.diff()[1:].unique()
    if len(dt) > 1:
        raise ValueError('time intervals are not uniform')
    dt = pd.Timedelta(dt[0])

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
        source, cycle = parse_cycle(c_id, c_info, time, dt)

        # add cyle as column or add values to existing column
        if source not in res.columns:
            res[source] = 0.
        res = res.join(cycle)
        res[source] = res[source] + res[c_id]
        res = res.drop(c_id, axis=1)

    return res
# ----------------------------------------------------


def cli_parser():
    """
    funtion to parse command line arguments
    :return: parser object
    :rtype: argparse.ArgumentParser
    """
    default = {'hour-begin': 8,
               'hour-end': 16,
               'cycle-file': 'cycle.yaml',
               'holiday-week': [25, 26, 27, 28, 29, 30, 52],
               'holiday-month': [7],
               'path': '.'
               }
    parser = argparse.ArgumentParser(description='fill source-strength ' +
                                                 'columns in "zeitreihe.dmna"')
    parser.add_argument("--version",
                        version="%(prog)s " + str(__version__),
                        action="version")
    verb = parser.add_mutually_exclusive_group()
    verb.add_argument('--debug', dest='verb', action='store_const',
                      const=logging.DEBUG, help='show informative output')
    verb.add_argument('-v', '--verbose', dest='verb', action='store_const',
                      const=logging.INFO, help='show detailed output')
    sched = parser.add_mutually_exclusive_group(required=True)
    sched.add_argument('-l', '--list',
                       action='store_const', dest='action', const='list',
                       help='list source column IDs in file' +
                            'and exit without modifying "zeitreihe.dmna".' +
                            '[default]')
    sched.add_argument('-c', '--cycle',
                       action='store_const', dest='action', const='cycle',
                       help='use production cycle from file')
    sched.add_argument('-w', '--week-5',
                       action='store_const', dest='action', const='week-5',
                       help='source active Mon-Fri')
    sched.add_argument('-W', '--week-6',
                       action='store_const', dest='action', const='week-6',
                       help='source active Mon-Sat')
    parser.add_argument('-b', '--hour-begin', metavar='HOUR',
                        nargs=1,
                        help='daily work begin time in hours 0-23. ' +
                             'Only relevant with -w or -W. ' +
                             '[%02i]' % default['hour-begin'],
                        default=default['hour-begin'])
    parser.add_argument('-e', '--hour-end', metavar='HOUR',
                        nargs=1,
                        help='daily work end time in hours, ' +
                             '0-23. Only relevant with -w or -W .' +
                             '[%02i]' % default['hour-end'],
                        default=default['hour-end'])
    hold = parser.add_mutually_exclusive_group()
    hold.add_argument('-u', '--holiday-week', nargs="+",
                      help='work-free weeks 1-52 as space-delimited list. ' +
                           'Only relevant with -w or -W. [' +
                           ' '.join(['%d' % x
                                     for x in default['holiday-week']]) +
                           ']',
                      default=default['holiday-week'])
    hold.add_argument('-U', '--holiday-month', nargs="+",
                      help='work-free months 1-12 as space-delimited list. ' +
                           'Only relevant with -w or -W. ' +
                           ' '.join(['%d' % x
                                     for x in default['holiday-month']]) +
                           ']',
                      default=default['holiday-month'])
    parser.add_argument('-f', '--cycle-file',
                        help='emission-cycle description file. ' +
                             'only relevant with -c. ' +
                             '[%s]' % default['cycle-file'],
                        default=default['cycle-file'])
    parser.add_argument('-s', '--source-id', nargs=1,
                        help='source ID. Required if more than one source. ' +
                             'list IDs in file with -l.',
                        default=None)
    parser.add_argument('-o', '--output', nargs=1,
                        help='output of the source in g/s. ' +
                             '-o is relevant with -w or -W. ',
                        default=None)
    parser.add_argument('path', metavar='PATH', nargs='?',
                        help='directory where "zeitreihe.dmna" is stored '
                             '[%s]' % default['path'],
                        default=default['path'])
    return parser
# ----------------------------------------------------


# noinspection SpellCheckingInspection
def main():
    # defaults
    parser=cli_parser()
    args = vars(parser.parse_args())
    logger.debug('args: %s' % args)
    #
    # logging level
    #
    if args["verb"] is not None:
        logger.setLevel(args["verb"])
    else:
        logger.setLevel(logging.WARNING)
    logger.info(os.path.basename(__file__) + ' version: ' + __version__)


    if args["path"] is None:
        raise ValueError('PATH not given')
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
# ----------------------------------------------------


if __name__ == "__main__":
    main()
