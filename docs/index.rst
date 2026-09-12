.. -*- coding: utf-8 -*-

:tocdepth: 2

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
    The main comand that provides all user-facing functionality,
    including the ``simple`` sub-command for the quickest way to
    create input data for AUSTAL (see `Provide input for AUSTAL
    (or AUSTAL2000)`_ below).

    Additional, more detailed user guides:

    :doc:`fill-timeseries`
        explains the Syntax of the cycle file ``cycle.yaml``
    :doc:`heating`
        explains the Syntax of the cycle file ``heating.yaml``

:doc:`configure-austaltools`
    Download dataset for use with austaltools (or assemble them from the original sources)

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

austaltools simple
-------------------

This is the most simple way to create input data for AUSTAL.
For example::

  austaltools simple 49.75 6.75 Kundelbach

will produce the files ``Kundelbach.grid``, ``Kundelbach.akterm``,
and ``Kundelbach.txt`` (reference coordinates and surface roughness).
It calls the ``weather`` and ``terrain`` sub-commands internally,
selecting standard options (year and data sources configured in the
``simple`` section of the configuration file, see
:doc:`configure-austaltools`).

Its full command-line options are documented as part of the
``simple`` sub-command in :doc:`austaltools`.

*****
Links
*****

- `GitHub <https://github.com/cdruee/austaltools>`_
- `Documentation (GitLab Pages) <https://TODO-fill-in-gitlab-pages-url>`_
- `PyPI <https://pypi.org/project/austaltools/>`_
- `GitLab (University Trier internal) <https://TODO-fill-in-internal-gitlab-url>`_

**************
Detailed info
**************

.. toctree::
   :maxdepth: 2

   austaltools
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
