austaltools
======

This module conatins tools for use with Langrangian dispersion model AUSLTA (AUSbreitungsmodell nach TA Luft)

### Requirements:

    pip install numpy pandas meteolib

### Installation:

    python3 setup.py install

### Full documentation:
https://druee.gitlab-pages.uni-trier.de/austaltools/

### The module contains the following scripts : 
===============================================

## Time dependent simulation

``austal-buildings-geojson``
    Read buildings from a Geojson file and put them into ``austal.txt``

``austal-eap``
    Determine EAP ("Ersatz-AnemometerPosition") accoring to VDI norm

``austal-input``
    Convenience command for easy creation of AUSTAL input data

``austal-fill-time-series``
    Fill source-strength columns in "zeitreihe.dmna"

``austal-steepness``
    Determine steepness of the model area

``austal-terrain``
    Extract surface topography for AUSTAL from various sources

``austal-plot``
    Simple baseline data plot

``austal-weather``
    Extract amospheric time series for AUSTAL from various sources

Licenses
========

This package is licensed under the EUROPEAN UNION PUBLIC LICENCE v. 1.2.
See ``LICENSE`` for the license text or navigate to https://eupl.eu/1.2/en/

The topography data files in the folder ``data`` are licensed under
various other licenses:

| code           | license |
|----------------|---------|
| GLO&#8209;30   | Licence for Copernicus DEM instance COP-DEM-GLO-30-F Global 30m Full, Free & Open |
| GTOPO30        | Creative Commons Attribution 4.0 International License.
| DGM25&#8209;RP | Datenlizenz Deutschland – Namensnennung – Version 2.0 |


<!-- note to self: &#8209; = non-breaking hyphen -->

See files containing "LICENSE" in the name for the individual licence texts.
