#!/usr/bin/env python3
"""
create basic plot for austal result files
"""
import argparse
import logging
import os
import re

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import numpy as np
    import readmet

try:
    from . import _tools
except ImportError:
    import _tools
try:
    from ._version import __version__
except ImportError:
    from _version import __version__

logger = logging.getLogger()
logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
logging.getLogger('readmet.dmna').setLevel(logging.WARNING)

# -------------------------------------------------------------------------
def parse_austal_outputname(filename: str):
    """
    analyze name of austal output file

    :param filename: str

    :return: information about file contents:
      - substance: name of pollutant (xx for unknown/not specified)
      - averaging: duration of averaging interval
        (accumulation, year, day or hour)
      - rank: rank of output value in list of all averages
        of the same length
      - kind: type of output (load, stdev or index)
      - grid: number of grid. 0 if not given / no staggered grids.
    :rtype: dict

    """
    # strip path and extension
    name = os.path.splitext(os.path.basename(filename))[0]

    res = {"name": name}
    # name of substance
    if "-" not in name:
        raise ValueError("not a valid output name: %s" % name)
    res["substance"], what = name.split('-')
    #
    avg_char = what[0]
    if what.startswith('dep'):
        res["averaging"] = 'accumulation'
    elif avg_char in ['y', 'j']:
        res["averaging"] = 'year'
    elif avg_char in ['d', 't']:
        res["averaging"] = 'day'
    elif avg_char in ['h', 's']:
        res["averaging"] = 'hour'
    else:
        raise ValueError("unknown averaging in name: %s" % name)

    if res["averaging"] in ['accumulation']:
        res["rank"] = 0
    else:
        try:
            res["rank"] = int(what[1:3])
        except ValueError:
            raise ValueError("unknown rank in name: %s" % name)

    sel_char = what[3]
    if sel_char in ['a', 'z']:
        res["kind"] = 'load'
    elif sel_char in ['s']:
        res["kind"] = 'stdv'
    elif sel_char in ['i']:
        res["kind"] = 'index'
    else:
        raise ValueError("unknown kind of output in name: %s" % name)

    if len(what) <= 4:
        res["grid"] = 0
    else:
        try:
            res["grid"] = int(what[5:7])
        except ValueError:
            raise ValueError("unknown grid number in name: %s" % name)

    return res


# -------------------------------------------------------------------------
def cli_parser() -> argparse.ArgumentParser:
    """
    command line interface

    :return: parser
    :rtype: argparse.ArgumentParser
    """

    parser = argparse.ArgumentParser(
        description='create AUSTAL windlibrary using METRAS')
    parser = _tools.add_arguents_common_plot(parser)
    parser.add_argument(dest="file", metavar="DATA",
                        help="data file to plot."
                        )
    parser.add_argument('-s', '--stdvs',
                        metavar="STDVs",
                        nargs='?',
                        default=0.,
                        const=1.,
                        help='hash areas where the data are not ' +
                             'significant. Sigingicant is defined as ' +
                             'larder than `STDVs` times the standard ' +
                             'deviation caculated by austal. ' +
                             'If missing, `STDVs` defaults to 1.0.')

    verb = parser.add_mutually_exclusive_group()
    verb.add_argument('--debug', dest='verb', action='store_const',
                      const=logging.DEBUG, help='show informative output')
    verb.add_argument('-v', '--verbose', dest='verb', action='store_const',
                      const=logging.INFO, help='show detailed output')
    return parser


# -------------------------------------------------------------------------


def main():
    parser = cli_parser()
    args = vars(parser.parse_args())

    # set logging level
    if args["verb"] is not None:
        logger.setLevel(args["verb"])
    else:
        logger.setLevel(logging.WARNING)
    logger.info(os.path.basename(__file__) + ' version: ' + __version__)

    logger.debug("args: %s" % format(args))

    # get the model configuration, if the file is present
    try:
        austxt = _tools.find_austxt(args['working_dir'])
        logger.info("reading configuration file: %s" % austxt)
        conf = _tools.get_austxt(austxt)
    except OSError:
        conf = None
    logger.debug("conf: %s" % format(conf))


    infile = args['file']
    # make sure infile has an extension
    if not infile.endswith('.dmna'):
        infile = infile + '.dmna'
    # analyze file name:
    info = parse_austal_outputname(infile)
    logger.debug("info: %s" % format(info))

    if args['buildings']:
        buildings = None
        if conf:
            buildings = _tools.get_buildings(conf)
            logging.info('buildings in config: %d' % len(buildings))

    # warn, if not a file containing "additional load"
    if info["kind"] != "load":
        logger.warning(
            'file does not contain load distribution: %s' % infile)

    infile_path = os.path.join(args['working_dir'], infile)
    logger.info('reading data from %s' % infile_path)
    datafile = readmet.dmna.DataFile(infile_path)
    dat = datafile.data[datafile.variables[0]]
    datx = datafile.axes(ax="x")
    daty = datafile.axes(ax="y")
    try:
        dd = float(datafile.header['delta'][0])
    except ValueError:
        dd = datx[1] - datx[0]
        logger.warning('grid spacing "delta" not in data file, ' +
                       'guessing: %fm ' % dd)

    if len(dat.shape) == 3:
        datz = dat[:, :, 0]
    elif len(dat.shape) == 2:
        datz = dat
    else:
        raise ValueError('data shape %s not understood' % format(dat.shape))

    unit = bytes(datafile.header["unit"], "latin-1").decode()

    stdvs = float(args["stdvs"])
    if stdvs > 0:
        stdfile = re.sub(r'(.+-...)[sz]([0-9]{0,2}\.dmna)',
                         r'\1s\2', infile)
        stdfile_path = os.path.join(args['working_dir'], stdfile)
        logger.info('reading stdev from %s' % infile_path)
        errorfile = readmet.dmna.DataFile(stdfile_path)
        std = errorfile.data[errorfile.variables[0]]
        if len(std.shape) == 3:
            std = std[:, :, 0]
        if datz.shape != std.shape:
            raise ValueError('stdv shape does not match data shape')
        std[std==0] = 1.E-19
        dots = datz / (stdvs * std)
    else:
        dots = None


    # try to load topography
    topo_path = os.path.join(args['working_dir'],
                             "zg0%01d.dmna" % info["grid"])
    if os.path.exists(topo_path):
        logger.info('reading terrain from %s' % infile_path)
        topo = topo_path
    else:
        if conf and "gh" in conf:
            logging.warning('file not found: %s' % topo_path)
        topo = None

    if args['plot'] is None or args['plot'] == '-':
        args['plot'] = '__show__'
    elif args['plot'] == '__default__':
        args['plot'] = os.path.splitext(os.path.basename(infile_path))[0]

    scale = 10 ** (np.ceil(np.log10(np.percentile(datz, 97.5))) )
    # for all-zero fields or bad data, make a dummy scale
    if scale <= 0.:
        scale = 1.
    logging.debug('scale: %f' % scale)
    levels = np.array([10, 20, 50, 100, 200, 500, 1000]
                      ) / 1000 * scale

    dat_dict = {'x': datx, 'y': daty, 'z': datz}
    _tools.common_plot(args, dat=dat_dict, unit=unit, topo=topo,
                       dots=dots, buildings=buildings, scale=levels)

# ------------------------------------------------------------------------


if __name__ == "__main__":
    main()
