austaltools
======

This module conatins tools for use with Langrangian dispersion model AUSLTA (AUSbreitungsmodell nach TA Luft)

### Requirements:

    pip install numpy pandas meteolib readmet 

### Installation:

    python3 setup.py install

### Full documentation:
https://druee.gitlab-pages.uni-trier.de/austaltools/

### The module contains the following scripts : 
===============================================

``austaltools``
    The main application. I suports subcommands like
    ``eap``, ``fill-timeseries``, 

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
