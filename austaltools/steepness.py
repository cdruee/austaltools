#!/usr/bin/env python3
"""
create basic plot for austal result files
"""
import logging
import os

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import numpy as np

from . import _plotting
from . import _tools

logger = logging.getLogger(__name__)
DEFAULT_GRID = 0
""" default ID (number) of the grid to evaluate """
# -------------------------------------------------------------------------

def main(args):
    """
    This is the main working function.

    :param args: The command line arguments as a dictionary, with keys:

      - ``working_dir``: The working directory where files are located
        (i.e. where ``austal.txt`` is stored). Defaults to
        ``_tools.DEFAULT_WORKING_DIR`` if missing or ``None``.
      - ``grid``: ID (number) of the grid to evaluate. Mutually
        exclusive with ``topo``. Defaults to ``DEFAULT_GRID`` if
        missing or ``None``.
      - ``topo``: Topography file to read instead of the AUSTAL
        topography files. Mutually exclusive with ``grid``. Defaults
        to ``None`` if missing.
      - ``plot`` and the other keys added by
        :func:`austaltools._tools.add_arguents_common_plot`: control
        whether/where the plot is produced, see
        :func:`austaltools._plotting.common_plot`.

    :type args: dict
    """
    #
    # logging level
    #
    logger.debug("args: %s" % format(args))

    working_dir = args.get('working_dir', None)
    if working_dir is None:
        working_dir = _tools.DEFAULT_WORKING_DIR

    grid = args.get('grid', None)
    if grid is None:
        grid = DEFAULT_GRID

    args['plot'] = _plotting.consolidate_plotname(
        args.get('plot', None), "steepness_0%01d" % grid)

    # try to load AUSTAL topography
    topo = args.get('topo', None)
    if topo is not None:
        topo_path = topo
    else:
        topo_path = os.path.join(working_dir, "zg%02d.dmna" % grid)
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
                          default=DEFAULT_GRID,
                          help='ID (number) of the grid to evaluate. '
                               'Defaults to %(default)s')
    pars_ste_what.add_argument('-t', '--topo',
                          metavar='FILE',
                          default=None,
                          help='Topography file to read instead of '
                               'the AUSTAL topography files.')
    pars_ste = _tools.add_arguents_common_plot(pars_ste)

    return pars_ste