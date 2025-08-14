#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Convenience script to provide a simple-to-use interface
to the most basic funtionality of `austaltools`,
the creation of input files for simulations with the
German regulatory dispersion model AUSTAL [AST31]_
"""
import logging
import argparse
import os

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    try:
        from . import command_line
    except ImportError:
        import command_line

try:
    from ._metadata import __version__, __title__
except ImportError:
    from _version import __version__, __title__


logging.basicConfig()
logger = logging.getLogger()


# -------------------------------------------------------------------------

def cli_parser():
    """
    funtion to parse command line arguments
    :return: parser object
    :rtype: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        description='Convenience command to produce AUSTAL input')
    parser.add_argument(dest="lat", metavar="LAT",
                        help='Center position latitude',
                        nargs=None
                        )
    parser.add_argument(dest="lon", metavar="LON",
                        help='Center position longitude',
                        nargs=None
                        )
    parser.add_argument(dest="output", metavar="NAME",
                        help="Stem for file names.",
                        nargs=None
                        )
    parser.add_argument("--version",
                        version=f"{parser.prog} {__version__}",
                        action="version")
    verb = parser.add_mutually_exclusive_group()
    verb.add_argument('--debug', dest='verb', action='store_const',
                      const=logging.DEBUG, help='show informative output')
    verb.add_argument('-v', '--verbose', dest='verb', action='store_const',
                      const=logging.INFO, help='show detailed output')
    return parser

# -------------------------------------------------------------------------
# main routine
def main():
    parser = cli_parser()
    args = vars(parser.parse_args())
    args['command'] = 'simple'
    args['working_dir'] = '.'
    command_line.main(args)

# -------------------------------------------------------------------------
# call main routine
if __name__ == "__main__":
    main()
