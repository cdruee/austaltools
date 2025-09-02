#!/usr/bin/env python3
"""
Module containing functions to
create a basic plot from austal result data

Plots can be shon interactively if the user operates
on a terminal that has an X-server running.
For example Linux with a running desktop environment,
an Anaconda environment or a ssh connection with
active X-forwarding and a local X-server running.
"""
import logging
import os
import re

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import numpy as np
    import readmet

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

logger = logging.getLogger(__name__)
if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
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


def main(args):
    """
    This is the main working function

    :param args: The command line arguments as a dictionary.
    :type args: dict
    :param args['working_dir']: The working directory where
      files are located (i.e. where ``austal.txt`` is stored).
    :type args['working_dir']: str
    :param args['file']: The input file name. If it doesn't have a '.dmna'
      extension, it will be added.
    :type args['file']: str
    :param args['buildings']: A flag indicating whether to plot
      buildings from the configuration.
    :type args['buildings']: bool
    :param args['stdvs']: The standard deviation value to mark (additional)
      concentrations as significant by overlaying dots..
    :type args['stdvs']: float
    :param args['plot']: The plot file name.
      If None or '-', the plot will be shown interactively.
      If '__default__', the name of the displayed data file with
      extension `.png` will beused.
    :type args['plot']: str or None

    :raises OSError: If the configuration file cannot be found or read.
    :raises ValueError: If the data shape is not understood or if the
      standard deviation shape does not match the data shape.
    """
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

    buildings = None
    if args['buildings'] and conf:
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

    if len(dat.shape) == 3:
        datz = dat[:, :, 0]
    elif len(dat.shape) == 2:
        datz = dat
    else:
        raise ValueError('data shape %s not understood' % format(dat.shape))

    unit = bytes(datafile.header["unit"], "latin-1").decode()

    stdvs = float(args["stdvs"])
    if stdvs > 0:
        stdfile = re.sub(r'(.+-...)[az]([0-9]{0,2}\.dmna)',
                         r'\1s\2', infile)
        stdfile_path = os.path.join(args['working_dir'], stdfile)
        logger.info('reading stdev from %s' % infile_path)
        errorfile = readmet.dmna.DataFile(stdfile_path)
        std = errorfile.data[errorfile.variables[0]]
        if len(std.shape) == 3:
            std = std[:, :, 0]
        if datz.shape != std.shape:
            raise ValueError('stdv shape does not match data shape')
        std[std == 0] = 1.E-19
        dots = 1. + datz / (stdvs * std)
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


    if args.get('scale', None):
        scale = float(args['scale'])
    else:
        # austoscale
        # # scale = 10 ** (np.ceil(np.log10(np.percentile(datz, 97.5))))
        scale = float('%.2g' % np.percentile(datz, 97.5))
        # for all-zero fields or bad data, make a dummy scale
        if scale <= 0.:
            scale = 1.
    logging.debug('scale: %f' % scale)
    levels = np.array([10, 60, 120, 240, 360, 680, 1000]
                      ) / 1000 * scale

    dat_dict = {'x': datx, 'y': daty, 'z': datz}
    _plotting.common_plot(args, dat=dat_dict, unit=unit, topo=topo,
                                    dots=dots, buildings=buildings, scale=levels)

# ------------------------------------------------------------------------

def add_options(subparsers):

    pars_plot = subparsers.add_parser(
        name=f'plot',
        help='plot AUSTAL output data')
    pars_plot.add_argument(dest="file", metavar="DATA",
                      help="data file to plot."
                      )
    pars_plot.add_argument('-s', '--stdvs',
                      metavar="STDVs",
                      nargs='?',
                      default=0.,
                      const=1.,
                      help='hash areas where the data are not ' +
                           'significant. Sigingicant is defined as ' +
                           'larder than `STDVs` times the standard ' +
                           'deviation caculated by austal. ' +
                           'If missing, `STDVs` defaults to 1.0.')

    adv_plot = pars_plot.add_argument_group('advanced options')
    adv_plot.add_argument('--scale',
                      metavar="VALUE",
                      nargs='?',
                      default=None,
                      help='Max value of the colour scale in '
                           'plotted value units. '
                           'Default is autoscale.')

    pars_plot = _tools.add_arguents_common_plot(pars_plot)

    return pars_plot