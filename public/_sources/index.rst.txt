.. -*- coding: utf-8 -*-

*************************************
Welcome to austaltools documentation!
*************************************

This documentation is currently being built up.
Please do not expect it to be complete.

*******
General
*******

This module contains tools for use with Langrangian dispersion model
AUSTAL (AUSbreitungsmodell nach TA Luft)

Installation:
-------------

Austaltools can be installed by

    pip install austaltools

in principle. For more detailed instructions, see :doc:`install`

Command-line scripts:
---------------------

The module contains the following scripts

:doc:`austaltools`
    The main comand that provides all user-facing functionality.

    Additional, more detailed user guides:

    :doc:`fill-timeseries`
        explains the Syntax of the cycle file ``cycle.yaml``
    :doc:`heating`
        explains the Syntax of the cycle file ``heating.yaml``




:doc:`configure-austaltools`
    Download dataset for use with austaltools (or assemble them from the original sources)

`austal-input`_
    Convenience command for easy creation of AUSTAL input data

Licenses
--------

This package is licensed under the EUROPEAN UNION PUBLIC LICENCE v. 1.2.
See `LICENSE` for the license text or navugate to https://eupl.eu/1.2/en/

The topography data that can be downloaded are licensed by the original providers
under various other licenses:

+------------+-----------------------------------------------------------------------------------+
| code       | license                                                                           |
+============+===================================================================================+
| GLO-30     | Licence for Copernicus DEM instance COP-DEM-GLO-30-F Global 30m Full, Free & Open |
+------------+-----------------------------------------------------------------------------------+
| GTOPO30    | Creative Commons Attribution 4.0 International License.                           |
+------------+-----------------------------------------------------------------------------------+
| DGM25-RP   | Datenlizenz Deutschland – Namensnennung – Version 2.0                             |
+------------+-----------------------------------------------------------------------------------+
| DGM10-BB   | Datenlizenz Deutschland – Namensnennung – Version 2.0                             |
| DGM10-BE   |                                                                                   |
| DGM10-BW   |                                                                                   |
| DGM10-RP   |                                                                                   |
| DGM10-SL   |                                                                                   |
| DGM10-SN   |                                                                                   |
| DGM10-ST   |                                                                                   |
| DGM10-TH   |                                                                                   |
+------------+-----------------------------------------------------------------------------------+
| DGM10-BY   | Creative Commons Attribution 4.0 International License.                           |
| DGM10-HB   |                                                                                   |
| DGM10-MV   |                                                                                   |
| DGM10-NI   |                                                                                   |
| DGM10-SH   |                                                                                   |
+------------+-----------------------------------------------------------------------------------+
| DGM10-HE   | Public domain (no explicit licencse)                                              |
+------------+-----------------------------------------------------------------------------------+
| DGM10-HH   | Creative Commons zero 1.0                                                         |
+------------+-----------------------------------------------------------------------------------+
| DGM10-NW   | Datenlizenz Deutschland – Zero – Version 2.0                                      |
+------------+-----------------------------------------------------------------------------------+

See files containing `LICENSE.*` for the individual licence texts.

****************************************
Provide input for AUSTAL (or AUSTAL2000)
****************************************

austal-input
------------

This is the most simple way to create input data for AUSTAL.
For example::

  austal-input 49.75 6.75 Kundelbach

will produce the files ``Kundelbach.gird`` and  ``Kundelbach.akterm``.
It calls ``austal-weather`` and ``austal-terrain`` internally,
selcting standard options (year 2000, default sources).

Its full command-line options are as the following:

.. argparse::
   :module: austaltools.austal_input
   :func: cli_parser
   :prog: austal-input

**************
Detailed info
**************


.. toctree::
   :maxdepth: 1

   install
   api_commands
   api_internal
   references

******************
Indices and tables
******************

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
