.. You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

*************************************
Welcome to austaltools documentation!
*************************************

This documentation is currently being built up.
Please do not expect it to be complete.

=======
General
=======

This module conatins tools for use with Langrangian dispersion model
AUSTAL (AUSbreitungsmodell nach TA Luft)

Installation:
-------------
::

    python3 setup.py install

Command-line scripts:
---------------------

The module contains the following scripts

:doc:`austal-buildings-geojson`
    Read buildings from a Geojson file and put them into ``austal.txt``

:doc:`austal-eap`
    Determine EAP ("Ersatz-AnemometerPosition") accoring to VDI norm

`austal-input`_
    Convenience command for easy creation of AUSTAL input data

:doc:`austal-fill-time-series`
    Fill source-strength columns in "zeitreihe.dmna"

:doc:`austal-steepness`
    Determine steepness of the model area

:doc:`austal-terrain`
    Extract surface topography for AUSTAL from various sources

:doc:`austal-plot`
    Simple baseline data plot

:doc:`austal-weather`
    Extract amospheric time series for AUSTAL from various sources

Licenses
--------

This package is licensed under the EUROPEAN UNION PUBLIC LICENCE v. 1.2.
See `LICENSE` for the license text or navugate to https://eupl.eu/1.2/en/

The topography data files in the folder `data` are licensed under
various other licenses:

+----------+-----------------------------------------------------------------------------------+
| code     | license                                                                           |
+==========+===================================================================================+
| GLO-30   | Licence for Copernicus DEM instance COP-DEM-GLO-30-F Global 30m Full, Free & Open |
+----------+-----------------------------------------------------------------------------------+
| GTOPO30  | Creative Commons Attribution 4.0 International License.                           |
+----------+-----------------------------------------------------------------------------------+
| DGM25-RP | Datenlizenz Deutschland – Namensnennung – Version 2.0                             |
+----------+-----------------------------------------------------------------------------------+

See files containing `LICENSE.*` for the individual licence texts.

****************************************
Provide input for AUSTAL (or AUSTAL2000)
****************************************

============
austal-input
============

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

==============
Developer info
==============


 :doc:`apidoc`


==================
Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
