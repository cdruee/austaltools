#!/usr/bin/env python3
"""
create basic plot for austal result files
"""
import logging
import os


if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import numpy as np

try:
    from . import _plotting
    from . import _tools
except ImportError:
    import _plotting
    import _tools

logger = logging.getLogger(__name__)
# -------------------------------------------------------------------------

def main(args):
    #
    # logging level
    #
    logger.debug("args: %s" % format(args))


    # try to load AUSTAL topography
    if args.get('topo', None) is not None:
        topo_path = args['topo']
    else:
        topo_path = os.path.join(args['working_dir'],
                                 "zg%02d.dmna" % args["grid"])
    if os.path.exists(topo_path):
        logger.info('reading topography from %s' % topo_path)

    topx, topy, topz, dd = _plotting.read_topography(topo_path)

    dzdx = np.diff(topz, axis=0, prepend=np.nan) / dd
    dzdy = np.diff(topz, axis=1, prepend=np.nan) / dd
    gammax = [ x  - dd / 2 for x in topx[1:]]
    gammay = [ y  - dd / 2 for y in topy[1:]]
    gammaz = np.sqrt(dzdx ** 2 + dzdy ** 2)[1:, 1:] * 100.

    gamma = {'x': gammax, 'y':gammay, 'z': gammaz}
    logging.info('max: 1:%f' % (1 / np.nanmax(gammaz)))

    dots = np.full(np.shape(gammaz), 2.5)
    dots[gammaz > 100. / 20.] = 1.
    dots[gammaz > 100. / 5.] = -0.5

    if args['plot'] is None or args['plot'] == '-':
        args['plot'] = '__show__'
    elif args['plot'] == '__default__':
        args['plot'] = "steepness0%01d" % args["grid"]

    _plotting.common_plot(args, gamma, unit="%", topo=topo_path, dots=dots)


# ------------------------------------------------------------------------

def add_options(subparsers):

    pars_ste = subparsers.add_parser(
        name="steepness",
        help='Plot AUSTAL topography steepness'
    )
    pars_ste_what = pars_ste.add_mutually_exclusive_group()
    pars_ste_what.add_argument('-g', '--grid',
                          metavar='ID',
                          default=0,
                          help='ID (number) of the grid to evaluate. '
                               'Defaults to 0')
    pars_ste_what.add_argument('-t', '--topo',
                          metavar='FILE',
                          default=None,
                          help='Topography file to read instead of '
                               'the AUSTAL topography files.')
    pars_ste = _tools.add_arguents_common_plot(pars_ste)

    return pars_ste