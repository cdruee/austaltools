austaltools
===========

This module conatins tools for use with Langrangian dispersion 
model AUSTAL (AUSbreitungsmodell nach TA Luft)

### Full documentation:
https://druee.gitlab-pages.uni-trier.de/austaltools/

Installation:
=============

Essential requirements:

     gdal meteolib numpy pandas readmet requests

Optional requirements (deneding upon intended use) 

    matplotlib netCDF4 tqdm 

AustalTools can be installed from PyPi:

    pip install austaltools

Please find detailed instructions - in particular
concerning Ubuntu / Debian Linux - in the full documentation.

The module contains the following scripts : 
===========================================

``austaltools``
    The main application. I suports subcommands like
    ``eap``, ``fill-timeseries``, ``widfield``, ...

``configure-austaltools``
    Application to prepare local datasources for ``austaltools``.

``austal-input``
    Convenience command for easy creation of AUSTAL input data

Licenses
========

This package is licensed under the EUROPEAN UNION PUBLIC LICENCE v. 1.2.
See ``LICENSE`` for the license text or navigate to https://eupl.eu/1.2/en/

Some auxiliary files in the folder ``data`` are licensed under
various other licenses:

| file                  | provider                                                                        | license               |
|-----------------------|---------------------------------------------------------------------------------|-----------------------|
| DGM10-HE.LICENSE.txt  | Hessian state law (https://www.rv.hessenrecht.hessen.de/perma?a=VermGeoInfG_HE) | none (PD)             |
| dwd_stationlist.json  | Deutscher Wetterdienst (DWD) open data portal                                   | CC BY 4.0             |
| wmo_stationlist.json  | World Meteorological Organization (WMO) and its members                         | CC BY 4.0             |


<!-- note to self: &#8209; = non-breaking hyphen -->

See files containing "LICENSE" in the name for the individual licence texts.
