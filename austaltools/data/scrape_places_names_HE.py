#!/usr/bin/env python
"""
Helper script to retrieve names of counties (Kreise)
and places (Gemeinden) needed to construct the download
filelist using the "generate" option.
Copy the output of this script as list into
datasets_definitons.jsun under key:
'DGM10-HE' >> 'arguments' >> 'values'.
"""
import requests
from austaltools._tools import jsonpath

host = 'https://gds.hessen.de'
nav_uri = 'INTERSHOP/rest/WFS/HLBG-Geodaten-Site/-/downloadcenter?path=3D-Daten/Digitales%20Gel%C3%A4ndemodell%20(DGM1)'
url = '/'.join([host, nav_uri])
with requests.get(url) as response:
    response.raise_for_status()
    subnavs = jsonpath(response.json(), '/navigation/*/uri')

dl_uris = []
for subnav in subnavs:
    url = '/'.join([host, subnav])
    with requests.get(url) as response:
        response.raise_for_status()
        dl_uris += jsonpath(response.json(), '/searchresult/downloads/*/downloadLink/uri')

downloads = ['/'.join([host, x]) for x in dl_uris]

kreise = []
gemeinden = []
for i,x in enumerate(downloads):
    kreis, file = x.split('/')[8:10]
    gemeinde,_ = file.split(' -',1)
    print(i,x)
    if kreis not in kreise:
        kreise.append(kreis)
    if gemeinde not in gemeinden:
        gemeinden.append(gemeinde)

print(str(kreise))
#print(str(gemeinden))



