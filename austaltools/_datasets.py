#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Mar 20 09:57:48 2022

@author: clemens
"""
import datetime as dt
import glob
import gzip
import itertools
import logging
import os
import re
import shutil
import sys
import tarfile
import tempfile
import zipfile
from importlib import resources
from pathlib import PurePath
from xml.etree import ElementTree

import numpy as np
import pandas as pd
import pip
import requests

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    from osgeo import gdal
    from osgeo_utils import gdal_merge
    from multiprocessing import Pool
    import cdo

try:
    import cdsapi
except ImportError:
    pip.main(['install', 'cdsapi'])
    import cdsapi

try:
    import cdo
except ImportError:
    pip.main(['install', 'cdo'])
    import cdo

try:
    from . import _tools
except ImportError:
    import _tools

try:
    from ._version import __version__, __title__
except ImportError:
    from _version import __version__, __title__

logging.basicConfig()
logger = logging.getLogger()

# -------------------------------------------------------------------------

DEM_FMT = '%s.elevation.nc'  # '%s.lzw.tif'
WEA_FMT = '%s_ak_eu_%04i.nc'
DIST_AUX_FILES = resources.files(__title__ + '.data')
TEMP = None
MAX_RETRY = 3
DATASET_DEFINITIONS = {
    'DGM25-RP': {
        'storage': 'terrain',
        'assemble': 'assemble_DGM25_RP',
        'doi': '10.5281/zenodo.12740424',
        'license': 'spdx:DL-DE-BY-2.0',
        'notice': 'Generated from DGM1 data ' +
                  '"© GeoBasis-DE / LVermGeoRP 2024, ' +
                  ' www.lvermgeo.rlp.de", ' +
                  'licensed under DL-DE-BY-2.0',
    },
    'DGM10-BB': {
        'storage': 'terrain',
        'assemble': 'assemble_DGMxx',
        'arguments': {
            'resolution': 10,
            'host': 'https://data.geobasis-bb.de',
            'path': 'geobasis/daten/dgm/tif',
            'filelist': '::html',
            'links': 'dgm.*zip',
            'unpack': 'zip://*.tif',
            'CRS': 'EPSG:25832'
        },
        'license': 'spdx:DL-DE-BY-2.0',
        'notice': 'Generated from DGM1 data '
                  'by "GeoBasis-DE / LGB (Landesvermessung und '
                  'Geobasisinformation Brandenburg)", www.lgl-bw.de", '
                  'licensed under DL-DE-BY-2.0',
    },
    'DGM10-BE': {
        'storage': 'terrain',
        'assemble': 'assemble_DGMxx',
        'arguments': {
            'resolution': 10,
            'host': 'https://fbinter.stadt-berlin.de',
            'path': 'fb/feed/senstadt/a_dgm',
            'filelist': '0::xml',
            'xmlpath': '/entry/link[@href=.*zip]::href',
            'unpack': 'zip://*.xyz',
            'CRS': 'EPSG:25832'
        },
        'license': 'spdx:DL-DE-BY-2.0',
        'notice': 'Generated from DGM1 data '
                  'by "Senatsverwaltung für Stadtentwicklung, '
                  'Bauen und Wohnen Berlin", 2023, '
                  'licensed under DL-DE-BY-2.0',
    },
    'DGM10-BW': {
        'storage': 'terrain',
        'assemble': 'assemble_DGMxx',
        'arguments': {
            'resolution': 10,
            'host': 'https://opengeodata.lgl-bw.de',
            #  re: 387-609/2  ho:5264-5514/2
            'path': 'data/dgm',
            'filelist': 'generate',
            'format': 'dgm1_32_%i_%i_2_bw.zip',
            'values': ['387-609/2', '5264-5514/2'],
            'missing': 'ignore',
            'unpack': 'zip://*/*.xyz',
            'CRS': 'EPSG:25832'
        },
        'license': 'spdx:DL-DE-BY-2.0',
        'notice': 'Generated from DGM1 data '
                  'by "Landesamt für Geoinformation und Landentwicklung '
                  'Baden-Württemberg (LGL), www.lgl-bw.de", '
                  'licensed under DL-DE-BY-2.0',
    },
    'DGM10-BY': {
        'storage': 'terrain',
        'assemble': 'assemble_DGMxx',
        'arguments': {
            'resolution': 10,
            'host': 'https://geodaten.bayern.de',
            'path': '/odd/a/dgm/dgm1',
            'filelist': '/meta/metalink/09.meta4',
            'xmlpath': '/file[@name=.tif$]/url[0]',
            'CRS': 'EPSG:25832'
        },
        'license': 'spdx:CC-BY-4.0',
        'notice': 'Generated from DGM1 data '
                  'by "Bayerische Vermessungsverwaltung – '
                  'www.geodaten.bayern.de", '
                  'licensed under CC-BY-4.0',
    },
    'DGM10-HB': {
        'storage': 'terrain',
        'assemble': 'assemble_DGMxx',
        'arguments': {
            'resolution': 10,
            'host': 'https://gdi2.geo.bremen.de',
            'path': 'inspire/download/DGM/data',
            'filelist': [
                'Gitternetz_DGM1_2017_HB_ASCII_XYZ.zip',
                'Gitternetz_DGM1_2015_BHV_ASCII_XYZ.zip',
            ],
            'unpack': 'zip://*/*.xyz',
            'CRS': 'EPSG:25832',
            'utm_remove_zone': 'true'
        },
        'license': 'spdx:CC-BY-4.0',
        'notice': 'Generated from DGM1 data '
                  'by "Landesamt GeoInformation Bremen" (2015/17), '
                  'licensed under CC-BY-4.0'
    },
    'DGM10-HE': {
        'storage': 'terrain',
        'assemble': 'assemble_DGMxx',
        'arguments': {
            'resolution': 10,
            'host': 'https://gds.hessen.de',
            'path': '/downloadcenter/20240726/3D-Daten/Digitales Geländemodell (DGM1)',
            'filelist': 'generate',
            'format': '%s/%s - DGM1.zip',
            'values': [['Hochtaunuskreis', 'Lahn-Dill-Kreis', 'Landkreis Bergstraße', 'Landkreis Darmstadt-Dieburg',
                        'Landkreis Fulda', 'Landkreis Gießen', 'Landkreis Groß-Gerau', 'Landkreis Hersfeld-Rotenburg',
                        'Landkreis Kassel', 'Landkreis Limburg-Weilburg', 'Landkreis Marburg-Biedenkopf',
                        'Landkreis Offenbach', 'Landkreis Waldeck-Frankenberg', 'Main-Kinzig-Kreis',
                        'Main-Taunus-Kreis', 'Odenwaldkreis', 'Rheingau-Taunus-Kreis', 'Schwalm-Eder-Kreis',
                        'Stadt Darmstadt', 'Stadt Frankfurt am Main', 'Stadt Kassel', 'Stadt Offenbach am Main',
                        'Stadt Wiesbaden', 'Vogelsbergkreis', 'Werra-Meißner-Kreis', 'Wetteraukreis'],
                       ['Bad Homburg v.d.Höhe', 'Friedrichsdorf', 'Glashütten', 'Grävenwiesbach',
                        'Königstein im Taunus', 'Kronberg im Taunus', 'Neu-Anspach', 'Oberursel (Taunus)', 'Schmitten',
                        'Steinbach (Taunus)', 'Usingen', 'Wehrheim', 'Weilrod', 'Aßlar', 'Bischoffen', 'Braunfels',
                        'Breitscheid', 'Dietzhölztal', 'Dillenburg', 'Driedorf', 'Ehringshausen', 'Eschenburg',
                        'Greifenstein', 'Haiger', 'Herborn', 'Hohenahr', 'Hüttenberg', 'Lahnau', 'Leun', 'Mittenaar',
                        'Schöffengrund', 'Siegbach', 'Sinn', 'Abtsteinach', 'Bensheim', 'Biblis', 'Birkenau',
                        'Bürstadt', 'Einhausen', 'Fürth', 'Gemarkung Michelbuch (gemeindefrei)', 'Gorxheimertal',
                        'Grasellenbach', 'Groß-Rohrheim', 'Heppenheim (Bergstraße)', 'Hirschhorn (Neckar)',
                        'Lampertheim', 'Lautertal (Odenwald)', 'Lindenfels', 'Lorsch', 'Mörlenbach', 'Neckarsteinach',
                        'Rimbach', 'Alsbach-Hähnlein', 'Babenhausen', 'Bickenbach', 'Dieburg', 'Eppertshausen',
                        'Erzhausen', 'Fischbachtal', 'Griesheim', 'Groß-Bieberau', 'Groß-Umstadt', 'Groß-Zimmern',
                        'Messel', 'Modautal', 'Mühltal', 'Münster (Hessen)', 'Ober-Ramstadt', 'Otzberg', 'Pfungstadt',
                        'Reinheim', 'Roßdorf', 'Bad Salzschlirf', 'Burghaun', 'Dipperz', 'Ebersburg',
                        'Ehrenberg (Rhön)', 'Eichenzell', 'Eiterfeld', 'Flieden', 'Fulda', 'Gersfeld (Rhön)',
                        'Großenlüder', 'Hilders', 'Hofbieber', 'Hosenfeld', 'Hünfeld', 'Kalbach', 'Künzell', 'Neuhof',
                        'Nüsttal', 'Petersberg', 'Allendorf (Lumda)', 'Biebertal', 'Buseck', 'Fernwald', 'Gießen',
                        'Grünberg', 'Heuchelheim a.d. Lahn', 'Hungen', 'Langgöns', 'Laubach', 'Lich', 'Linden',
                        'Lollar', 'Pohlheim', 'Rabenau', 'Reiskirchen', 'Staufenberg', 'Wettenberg',
                        'Biebesheim am Rhein', 'Bischofsheim', 'Büttelborn', 'Gernsheim', 'Ginsheim-Gustavsburg',
                        'Groß-Gerau', 'Kelsterbach', 'Mörfelden-Walldorf', 'Nauheim', 'Raunheim', 'Riedstadt',
                        'Rüsselsheim am Main', 'Stockstadt am Rhein', 'Trebur', 'Alheim', 'Bad Hersfeld', 'Bebra',
                        'Breitenbach am Herzberg', 'Cornberg', 'Friedewald', 'Hauneck', 'Haunetal', 'Heringen (Werra)',
                        'Hohenroda', 'Kirchheim', 'Ludwigsau', 'Nentershausen', 'Neuenstein', 'Niederaula',
                        'Philippsthal (Werra)', 'Ronshausen', 'Rotenburg a. d. Fulda', 'Schenklengsfeld', 'Wildeck',
                        'Ahnatal', 'Bad Emstal', 'Bad Karlshafen', 'Baunatal', 'Breuna', 'Calden', 'Espenau',
                        'Fuldabrück', 'Fuldatal', 'Grebenstein', 'Gutsbezirk Reinhardswald', 'Habichtswald', 'Helsa',
                        'Hofgeismar', 'Immenhausen', 'Kaufungen', 'Liebenau', 'Lohfelden', 'Naumburg', 'Nieste',
                        'Bad Camberg', 'Beselich', 'Brechen', 'Dornburg', 'Elbtal', 'Elz', 'Hadamar', 'Hünfelden',
                        'Limburg a. d. Lahn', 'Löhnberg', 'Mengerskirchen', 'Merenberg', 'Runkel', 'Selters (Taunus)',
                        'Villmar', 'Waldbrunn (Westerwald)', 'Weilburg', 'Weilmünster', 'Weinbach', 'Amöneburg',
                        'Angelburg', 'Bad Endbach', 'Biedenkopf', 'Breidenbach', 'Cölbe', 'Dautphetal',
                        'Ebsdorfergrund', 'Fronhausen', 'Gladenbach', 'Kirchhain', 'Lahntal', 'Lohra', 'Marburg',
                        'Münchhausen', 'Neustadt (Hessen)', 'Rauschenberg', 'Stadtallendorf', 'Steffenberg',
                        'Weimar (Lahn)', 'Dietzenbach', 'Dreieich', 'Egelsbach', 'Hainburg', 'Heusenstamm',
                        'Langen (Hessen)', 'Mainhausen', 'Mühlheim am Main', 'Neu-Isenburg', 'Obertshausen',
                        'Rödermark', 'Rodgau', 'Seligenstadt', 'Allendorf (Eder)', 'Bad Arolsen', 'Bad Wildungen',
                        'Battenberg (Eder)', 'Burgwald', 'Diemelsee', 'Diemelstadt', 'Edertal', 'Frankenau',
                        'Frankenberg (Eder)', 'Gemünden (Wohra)', 'Haina (Kloster)', 'Hatzfeld (Eder)', 'Korbach',
                        'Lichtenfels', 'Rosenthal', 'Twistetal', 'Vöhl', 'Volkmarsen', 'Waldeck', 'Bad Orb',
                        'Bad Soden-Salmünster', 'Biebergemünd', 'Birstein', 'Brachttal', 'Bruchköbel', 'Erlensee',
                        'Flörsbachtal', 'Freigericht', 'Gelnhausen', 'Großkrotzenburg', 'Gründau',
                        'Gutsbezirk Spessart', 'Hammersbach', 'Hanau', 'Hasselroth', 'Jossgrund', 'Langenselbold',
                        'Linsengericht', 'Maintal', 'Bad Soden am Taunus', 'Eppstein', 'Eschborn', 'Flörsheim am Main',
                        'Hattersheim am Main', 'Hochheim am Main', 'Hofheim am Taunus', 'Kelkheim (Taunus)', 'Kriftel',
                        'Liederbach am Taunus', 'Schwalbach am Taunus', 'Sulzbach (Taunus)', 'Bad König', 'Brensbach',
                        'Breuberg', 'Brombachtal', 'Erbach (Odenwald)', 'Fränkisch-Crumbach', 'Höchst i. Odw',
                        'Lützelbach', 'Michelstadt', 'Mossautal', 'Oberzent', 'Reichelsheim (Odenwald)', 'Aarbergen',
                        'Bad Schwalbach', 'Eltville am Rhein', 'Geisenheim', 'Heidenrod', 'Hohenstein', 'Hünstetten',
                        'Idstein', 'Kiedrich', 'Lorch', 'Niedernhausen', 'Oestrich-Winkel', 'Rüdesheim am Rhein',
                        'Schlangenbad', 'Taunusstein', 'Waldems', 'Walluf', 'Bad Zwesten', 'Borken (Hessen)',
                        'Edermünde', 'Felsberg', 'Frielendorf', 'Fritzlar', 'Gilserberg', 'Gudensberg', 'Guxhagen',
                        'Homberg (Efze)', 'Jesberg', 'Knüllwald', 'Körle', 'Malsfeld', 'Melsungen', 'Morschen',
                        'Neuental', 'Neukirchen (Knüllgebirge)', 'Niedenstein', 'Oberaula', 'Darmstadt',
                        'Frankfurt am Main', 'Kassel', 'Offenbach am Main', 'Wiesbaden', 'Alsfeld', 'Antrifttal',
                        'Feldatal', 'Freiensteinau', 'Gemünden (Felda)', 'Grebenau', 'Grebenhain', 'Herbstein',
                        'Homberg (Ohm)', 'Kirtorf', 'Lauterbach (Hessen)', 'Lautertal (Vogelsberg)', 'Mücke', 'Romrod',
                        'Schlitz', 'Schotten', 'Schwalmtal', 'Ulrichstein', 'Wartenberg', 'Bad Sooden-Allendorf',
                        'Berkatal', 'Eschwege', 'Großalmerode', 'Gutsbezirk Kaufunger Wald', 'Herleshausen',
                        'Hessisch Lichtenau', 'Meinhard', 'Meißner', 'Neu-Eichenberg', 'Ringgau', 'Sontra',
                        'Waldkappel', 'Wanfried', 'Wehretal', 'Weißenborn', 'Witzenhausen', 'Altenstadt', 'Bad Nauheim',
                        'Bad Vilbel', 'Büdingen', 'Butzbach', 'Echzell', 'Florstadt', 'Friedberg (Hessen)', 'Gedern',
                        'Glauburg', 'Hirzenhain', 'Karben', 'Kefenrod', 'Limeshain', 'Münzenberg', 'Nidda', 'Niddatal',
                        'Ober-Mörlen', 'Ortenberg', 'Ranstadt']
                       ],
            'missing': 'ignore',
            'unpack': 'zip://*.tif',
            'CRS': 'EPSG:25832'
        },
        'license': None,  # PD
        'notice': None
    },
    'DGM10-HH': {
        'storage': 'terrain',
        'assemble': 'assemble_DGMxx',
        'arguments': {
            'resolution': 10,
            'host': 'https://daten-hamburg.de',
            'path': 'geographie_geologie_geobasisdaten/'
                    'Digitales_Hoehenmodell/DGM1',
            'filelist': [
                'dgm1_2x2km_XYZ_hh_2021_04_01.zip',
            ],
            'unpack': 'zip://*/*/*.xyz',
            'CRS': 'EPSG:25832'
        },
        'license': 'spdx:CC-0',
        'notice': 'Generated from DGM1 data '
                  'by "Freie und Hansestadt Hamburg, '
                  'Landesbetrieb Geoinformation und Vermessung '
                  '(LGV)", 2021, licensed under '
                  'Datenlizenz Deutschland Namensnennung 2.0'
    },
    'DGM10-MV': {
        'storage': 'terrain',
        'assemble': 'assemble_DGMxx',
        'arguments': {
            'resolution': 10,
            'host': 'https://www.geodaten-mv.de',
            'path': 'dienste',
            'filelist': 'dgm_atom?type=dataset&id=ca268792-s2q1-4a39-b34c-9ec5bf9a4469::xml',
            'xmlpath': '/entry/link[@title=.*Gtiff.*]::href',
            'CRS': 'EPSG:25832'
        },
        'license': 'spdx:CC-BY-4.0',
        'notice': 'Generated from DGM1 data '
                  'by "© GeoBasis-DE/M-V", 2024, '
                  'licensed under CC-BY-4.0',
    },
    'DGM10-NI': {
        'storage': 'terrain',
        'assemble': 'assemble_DGMxx',
        'arguments': {
            'resolution': 10,
            'host': 'https://arcgis-geojson.s3.eu-de.'
                    'cloud-object-storage.appdomain.cloud',
            'path': 'dgm1',
            'filelist': 'lgln-opengeodata-dgm1.geojson',
            'jsonpath': '/features/*/properties/dgm1',
            'datapath': '',
            'CRS': 'EPSG:25832'
        },
        'license': 'spdx:CC-BY-4.0',
        'notice': 'Generated from DGM1 data '
                  'by "Landesbetrieb Landesvermessung und '
                  'Geobasisinformation Niedersachsen - LGLN" (2024), '
                  'licensed under CC-BY-4.0'
    },
    'DGM10-NW': {
        'storage': 'terrain',
        'assemble': 'assemble_DGMxx',
        'arguments': {
            'resolution': 10,
            'host': 'https://www.opengeodata.nrw.de',
            'path': 'produkte/geobasis/hm/dgm1_tiff/dgm1_tiff',
            'filelist': 'index.xml',
            'xmlpath': '/datasets/dataset[0]/files/file::name',
            'datapath': '',
            'CRS': 'EPSG:25832'
        },
        'license': 'spdx:DL-DE-ZERO-2.0',
        'notice': None
    },
    'DGM10-RP': {
        'storage': 'terrain',
        'assemble': 'assemble_DGMxx',
        'arguments': {
            'resolution': 10,
            'check_cert': False,
            'host': 'https://geobasis-rlp.de',
            'path': '/data/dgm1/current',
            'filelist': '/meta4/dgm1_tif_07.meta4',
            'xmlpath': '/file[@name=.tif$]/url',
            'CRS': 'EPSG:25832'
        },
        'license': 'spdx:DL-DE-BY-2.0',
        'notice': 'Generated from DGM1 data ' +
                  '"© GeoBasis-DE / LVermGeoRP 2024, ' +
                  ' www.lvermgeo.rlp.de", ' +
                  'licensed under DL-DE-BY-2.0',
    },
    'DGM10-SL': {
        'storage': 'terrain',
        'assemble': 'assemble_DGMxx',
        'arguments': {
            'resolution': 10,
            'host': 'file://',
            'path': 'localdata/opt/DGM1_SL',
            'filelist': ['DGM1_tif_MZG_25832.zip',
                         'DGM1_tif_SB_25832.zip',
                         'DGM1_tif_SLS_25832.zip',
                         'DGM1_tif_SPK_25832.zip',
                         'DGM1_tif_WND_25832.zip'],
            'unpack': 'zip://*.tif',
            'CRS': 'EPSG:25832'
        },
        'license': 'spdx:DL-DE-BY-2.0',
        'notice': 'Generated from DGM1 data ' +
                  '""© GeoBasis DE/LVGL-SL (2024)", '
                  ', https://lvgl.saarland.de, 2024, ' +
                  'licensed under DL-DE-BY-2.0',
    },
    'DGM10-SN': {
        'storage': 'terrain',
        'assemble': 'assemble_DGMxx',
        'arguments': {
            'resolution': 10,
            'host': 'https://geodownload.sachsen.de',
            'path': 'inspire/el_atom',
            'filelist': 'Dataset_el_dgm1.xml',
            'xmlpath': '/entry/link::href',
            'unpack': 'zip://*.xyz',
            'CRS': 'EPSG:25832'
        },
        'license': 'spdx:DL-DE-BY-2.0',
        'notice': 'Generated from DGM1 data ' +
                  '""Landesamt für Geobasisinformation Sachsen (GeoSN)", '
                  ', https://www.landesvermessung.sachsen.de, 2024, ' +
                  'licensed under DL-DE-BY-2.0',
    },
    'DGM10-ST': {
        'storage': 'terrain',
        'assemble': 'assemble_DGMxx',
        'arguments': {
            'resolution': 10,
            'host': 'https://www.geodatenportal.sachsen-anhalt.de',
            'path': 'gfds_webshare/download/LVermGeo/Geodatenportal/Online-Bereitstellung-LVermGeo/DGM',
            'filelist': ['DGM2_1.zip', 'DGM2_2.zip', 'DGM2_3.zip', 'DGM2_4.zip'],
            'unpack': 'zip://*/*.tif',
            'CRS': 'EPSG:25832'
        },
        'license': 'spdx:DL-DE-BY-2.0',
        'notice': 'Generated from DGM1 data ' +
                  '"© GeoBasis-DE / LVermGeo ST" '
                  ', https://www.lvermgeo.sachsen-anhalt.de, 2024, ' +
                  'licensed under DL-DE-BY-2.0',
    },
    'DGM10-TH': {
        'storage': 'terrain',
        'assemble': 'assemble_DGMxx',
        'arguments': {
            'resolution': 10,
            'host': 'https://geoportal.geoportal-th.de',
            'path': 'dienste',
            'filelist': 'atom_th_hoehendaten_dgm?type=dataset&id=14418d25-fcd7-4a3f-99a9-e3059a2772af&crs=EPSG:25832::xml',
            'xmlpath': '/entry/link::href',
            'unpack': 'zip://*.tif',
            'CRS': 'EPSG:25832'
        },
        'license': 'spdx:DL-DE-BY-2.0',
        'notice': 'Generated from DGM1 data ' +
                  '"© GeoBasis-DE / LVermGeoRP 2024, ' +
                  ' www.lvermgeo.rlp.de", ' +
                  'licensed under DL-DE-BY-2.0',
    },
    'GLO-30': {
        'storage': 'terrain',
        'assemble': 'assemble_GLO_30',
        'license': 'file:',
        'notice': '(C) DLR e.V. 2010-2014 and © Airbus Defence and Space '
                  'GmbH 2014-2018 provided under COPERNICUS by the '
                  'European Union and ESA; all rights reserved.\n'
                  'EU users who use the Copernicus DEM in their research '
                  'are requested to use the following DOI when citing '
                  'the data source in their publications: '
                  'https://doi.org/10.5270/ESA-c5d3d65',
    },
    'GTOPO30': {
        'storage': 'terrain',
        'assemble': 'assebmle_GTOPO30'
    },
    'ERA5': {
        'storage': 'weather',
        'assemble': 'assemble_ERA5'
    },
    'CERRA': {
        'storage': 'weather',
        'assemble': 'assemble_CERRA'
    },
}

KNOWN_DEMS = [k for k, v in DATASET_DEFINITIONS.items()
              if v['storage'] == _tools.STORAGE_TERRAIN]
KNOWN_WEATHER = [k for k, v in DATASET_DEFINITIONS.items()
                 if v['storage'] == _tools.STORAGE_WAETHER]


# =========================================================================


class DataSet:
    name = str()
    available = False
    path = None
    storage = None
    file_license = None
    file_notice = None
    file_data = None
    uri = None
    years = []
    arguments = None

    # ----------------------------------------------------

    def assemble(self):
        """Placeholder for download function"""
        pass

    # ----------------------------------------------------

    def download(self, path=None, uri=None):
        """Download assembled dataset from reopository"""
        if path is None:
            path = self.path
        else:
            self.path = path
        if uri is None:
            if self.uri is not None:
                uri = self.uri
            else:
                raise ValueError("No uri defined or provided")
        if uri.startswith('doi'):
            doi = re.sub('^doi[:/]*', '', uri)
            doi_url = f"https://doi.org/{doi}"
            logger.debug(f"resolving {doi_url}")
            for i in range(MAX_RETRY):
                try:
                    with requests.head(doi_url) as resolver:
                        redirect = resolver.url
                    break
                except requests.HTTPError:
                    continue
            else:
                raise Exception("Could not resolve DOI")
            if "zenodo" in redirect:
                url = f"{redirect}/files/{self.file_data}?download=1"
            else:
                raise ValueError(f"Dont know how to hande redirect " +
                                 "URL: {URL}")
        elif uri.startswith('http'):
            url = uri
        else:
            raise ValueError(f'cannot handle URI: {uri}')
        with open(os.path.join(path, self.file_data), 'wb') as f:
            with requests.get(url, allow_redirects=True) as req:
                f.write(req.content)

    # ----------------------------------------------------

    def __init__(self, **kwargs):
        if 'name' not in kwargs:
            raise ValueError('no name given')
        if 'storage' not in kwargs:
            raise ValueError('no storage given')
        for x in kwargs:
            if x == "assemble":
                self.assemble = getattr(sys.modules[__name__], kwargs[x])
            elif hasattr(self, x):
                setattr(self, x, kwargs[x])
        if self.file_license is None:
            self.file_license = f"{self.name}.LICENSE.txt"
        if self.file_notice is None:
            self.file_notice = f"{self.name}.NOTICE.txt"
        if self.file_data is None:
            if self.storage == 'terrain':
                self.file_data = DEM_FMT % self.name
            elif self.storage == 'weather':
                self.file_data = WEA_FMT % (self.name, 0)


# =========================================================================


def locations_available(locs):
    return [x for x in locs if os.path.isdir(x)]


# -------------------------------------------------------------------------


def locations_writable(locs):
    return [x for x in locs if os.access(x, os.W_OK)]


# -------------------------------------------------------------------------


def location_has_storage(location, storage):
    return os.path.exists(os.path.join(location, storage))


# -------------------------------------------------------------------------


def dataset_get(name):
    for x in DATASETS:
        if x.name == name:
            return x
    else:
        raise ValueError(f"Dataset {name} not found")


# -------------------------------------------------------------------------


def dataset_available(name):
    return dataset_get(name).available


# -------------------------------------------------------------------------

def dataset_scan(locs=None):
    if locs is None:
        locs = _tools.STORAGE_LOCATIONS
    loc_avail = locations_available(locs)
    if len(loc_avail) == 0:
        raise ValueError("No locations available")
    for ds in DATASETS:
        for loc in reversed(loc_avail):
            if ds.storage is None:
                raise ValueError(f'storage not defined in: {ds.name}')
            if location_has_storage(loc, ds.storage):
                path = os.path.join(loc, str(ds.storage))
                datafile = os.path.join(path, ds.file_data)
                if os.path.exists(datafile):
                    ds.available = True
                    ds.path = path


# -------------------------------------------------------------------------


def find_writeable_storage(locs: str = None, stor: str = None) -> str or None:
    """
    Finds a viable data storage directory and returns its path.
    If `storage_path` is provided, only this path is checked
    for existance.

    :param locs: Candidate locations
    :type locs: str
    :param stor: Storage directory expected at location
    :type stor: str
    :return: path to a writable data storage directory
    :rtype: str
    """
    if stor is None:
        raise ValueError('stor must be provided')
    if locs is None:
        locs = _tools.STORAGE_LOCATIONS
    loc_exist = locations_available(locs)
    if len(loc_exist) == 0:
        return None
    loc_write = locations_writable(loc_exist)
    if len(loc_write) == 0:
        return None
    for loc in loc_write:
        if location_has_storage(loc, stor):
            location = loc
            break
    else:
        for loc in loc_write:
            try:
                os.makedirs(os.path.join(loc, stor))
            except IOError:
                continue
            if os.path.isdir(os.path.join(loc, stor)):
                location = loc
                break
        else:
            raise Exception('Could not create data storage directory')
    return os.path.join(location, stor)


# -------------------------------------------------------------------------


def download(url, file):
    """
    Downloads a file from a specified URL and saves it to a given local file path.

    :param url: The URL of the file to download.
    :type url: str
    :param file: The local path, including the filename, where the downloaded file will be saved.
    :type file: str
    :returns: The name of the file saved locally.
    :rtype: str
    :raises Exception: An exception is raised if the download fails (HTTP status code is not 200).

    This function sends a GET request to the specified URL. If the request is successful (HTTP status code 200),
    it writes the content of the response to a file specified by the 'file' parameter. If the request fails,
    it raises an exception with information about the failure.

    Example usage:

    .. code-block:: python

        try:
            file_name = download('http://example.com/file.jpg', '/path/to/local/file.jpg')
            print(f"Downloaded file saved as {file_name}")
        except Exception as e:
            print(str(e))

    """
    with requests.get(url, allow_redirects=True) as req:
        if req.status_code == 200:
            with open(file, 'wb') as f:
                f.write(req.content)
        else:
            raise Exception(f"Download failed: status code {req.status_code}")
    return os.path.basename(file)


# -------------------------------------------------------------------------


def xyz2csv(inputfile, output, utm_remove_zone=False):
    # test if file has a header line
    with open(inputfile, 'r') as fd:
        line1 = fd.readline()
    if bool(re.search('[a-zA-Z]', line1)) > 0:
        header = 0
    else:
        header = None
    df = pd.read_csv(inputfile,
                     sep=r'\s+', header=header, names=['x', 'y', 'z'])
    if len(df.index) < 4:
        # skip empty files
        return False

    if utm_remove_zone:
        df['x'] = np.sign(df['x']) * (np.abs(df['x']) % 1000000)
    # get full grid axes
    x_res = np.mean(np.diff(sorted(set(df['x']))))
    x_vals = set(np.arange(df['x'].min(), df['x'].max() + x_res, x_res))
    y_res = np.mean(np.diff(sorted(set(df['y']))))
    y_vals = set(np.arange(df['y'].min(), df['y'].max() + y_res, y_res))

    # create full dataframe
    ff = pd.DataFrame.from_records(itertools.product(x_vals, y_vals),
                                   columns=['x', 'y'])
    of = pd.merge(ff, df, how='left', left_on=['x', 'y'], right_on=['x', 'y'])
    del [ff, df]
    of = of.replace(np.nan, -9999.)

    # sort it so gdal doesnt complain
    of = of.sort_values(['y', 'x'])

    of.to_csv(output, index=False, header=False)

    return True


# -------------------------------------------------------------------------


def xmlpath(xml, path):
    """
    Extracts text or attribute values from specified elements within an XML string based on a given path.
    The function implements only a small subset of the XPath syntax.


    :param xml: The XML document as a str.
    :param path: A string representing the hierarchical path to the desired elements. This path may include element names,
                 indexes in square brackets for direct child selection, and an optional attribute filter or attribute name
                 preceded by ``::`` for final value extraction.

    Path Syntax

    * ``'element'``: Selects all children named ``element`` from the current node.
    * ``'element[index]'``: Selects the n-th ``element`` among its siblings (0-based index).
    * ``'element[@attribute="value"]'``: Selects all ``element`` nodes where the attribute matches the specified value.
    * ``'element::attribute'``: Retrieves the value of an attribute named ``attribute`` from the selected elements.
    * Any combination of the above, separated by '/' to navigate through child elements.

    :return: A list containing the extracted data from the XML, either the text content of selected elements or the values of
             specified attributes, depending on the input path.

    :Example:

    .. code-block:: python

        xml_string = '''<data>
                            <item id="1">Item 1</item>
                            <item id="2" extra="yes">Item 2</item>
                        </data>'''

        pathtotext = 'item'
        textresult = xmlpath(xmlstring, pathtotext)

    Returns: ['Item 1', 'Item 2']


        pathtoattribute = 'item::id'
        attributeresult = xmlpath(xmlstring, pathtoattribute)

    Returns: ['1', '2']


    Notes

    - This function is designed to operate on well-formed XML strings. Malformed XML might lead to unexpected results.
    - The function uses Python's built-in XML handling capabilities and regular expressions for parsing and navigating the XML.
    - Namespace handling: If the XML contains namespaces, they are automatically recognized and handled for tag matching.

    :raises: The function itself does not explicitly raise exceptions, but misuse (e.g., incorrect XML or path syntax) can
             lead to exceptions thrown by the underlying XML or regex processing libraries.

    Dependencies

    - Requires the `ElementTree` module from the Python standard library and `re` for regular expression support.

      Ensure to import these before using the function:

    .. code-block:: python

        import re
        from xml.etree import ElementTree

    """

    if '::' in path:
        getpath, getatt = path.split("::")
    else:
        getpath = path
        getatt = None
    levels = getpath.split('/')
    if levels[0] == '':
        levels.pop(0)
    root = ElementTree.fromstring(xml)
    m = re.search('{.*}', root.tag)
    if m:
        ns = '%s' % m.group(0)
    else:
        ns = ''
    nodes = [root]
    for level in levels:
        if "[" in level:
            name = re.sub(r'\[.*]', '', level)
            spec = re.sub(r'.*\[(.*)].*', r'\1', level)
            try:
                sel = int(spec)
                enti = None
            except ValueError:
                if '=' in spec:
                    enti, sel = [x.strip() for x in spec.split('=')]
                else:
                    enti = spec
                    sel = None
        else:
            name = level
            spec = enti = sel = None
        tag = ''.join((ns, name))
        print(name, spec, enti, sel)
        next_nodes = []
        for node in nodes:
            # iterate over children
            tag_counter = {}
            i = 0
            for ele in node:
                # count identical tags
                if ele.tag in tag_counter:
                    tag_counter[ele.tag] += 1
                else:
                    tag_counter[ele.tag] = 0
                if not ele.tag == tag:
                    continue
                if sel is None and enti is None:
                    next_nodes.append(ele)
                elif sel == tag_counter[ele.tag]:
                    next_nodes.append(ele)
                elif enti is not None:
                    if enti.startswith('@'):
                        attr = enti.replace('@', '')
                        if (attr in ele.attrib and
                                bool(re.search(sel, ele.attrib[attr]))):
                            next_nodes.append(ele)
                    else:
                        if len(node.findall(enti)) > 0:
                            next_nodes.append(ele)
        nodes = next_nodes
    if getatt is None:
        res = [x.text for x in nodes]
    else:
        res = [x.get(getatt, default='') for x in nodes]
    return res


# -------------------------------------------------------------------------

def jsonpath(json_obj, path):
    """
    Extracts values from specified keys or indices within a JSON object based on a given path.

    :param json_obj: The JSON object (dict or list). This can be the result of json.loads() if using a JSON string.
    :param path: A string representing the hierarchical path to the desired keys or indices. This path may include dictionary keys,
                 list indices, and an optional filtering condition for dictionaries with specific key-value pairs.

    Path Syntax

    * 'key': Selects the value associated with 'key' in a dictionary.
    * '[index]': Selects the n-th element in a list (0-based index).
    * 'key=value': Selects dictionaries from a list of dictionaries where 'key' matches 'value'.
    * Any combination of the above, separated by '/' to navigate through nested structures.
    * an asterisk (`*`) may be specified instead of 'key' to match any key.

    :return: A list containing the extracted values from the JSON object based on the input path.

    :Example:

    .. code-block:: python

        json_obj = {
            "items": [
                {"id": 1, "name": "Item 1"},
                {"id": 2, "name": "Item 2", "extra": "yes"}
            ]
        }

        path_to_name = 'items/name'
        names = jsonpath(json_obj, path_to_name)
        # Returns: ['Item 1', 'Item 2']

        path_to_extra = 'items/extra'
        extras = jsonpath(json_obj, path_to_extra)
        # Returns: ['yes']

    Notes

    - This function simplifies direct navigation and filtering in
      JSON objects but does not offer the full querying capabilities
      of more complex JSON querying libraries such as `jsonpath-rw`.

    """

    nodes = path.split('/')
    if nodes[0] == '':
        nodes.pop(0)
    # Start with a list for uniform processing
    obj = [json_obj]
    for node in nodes:
        children = []
        for oj in obj:
            if isinstance(oj, list):
                if node.isdigit():
                    # Indexing into a list
                    children += [oj[int(node)]]
                elif node == '*':
                    children += [oj]
                elif "=" in node:
                    key, value = node.split("=")
                    children += [o for o in oj if o.get(key) == value]
                else:
                    # Collecting items by key from each dictionary in a list
                    children += [o[node] for o in oj if node in o]
            elif isinstance(oj, dict):
                if node in oj or node == '*':
                    children += [oj[node]]
        obj = children
    return obj


# -------------------------------------------------------------------------


def ass_process_input(args):
    inp, base_url, verify, provider = args
    tile_files = []
    if re.match('^http[s]*://', inp):
        url = inp
    else:
        url = f"{base_url}/{inp}"
    dl_file = os.path.basename(url)
    failure_ok = False
    if re.match('^http[s]*://', url):
        logger.debug(f"downloading ... {url}")
        for i in range(MAX_RETRY):
            with requests.get(url, verify=verify) as req:
                if req.status_code == requests.codes.ok:
                    with open(dl_file, 'wb') as f:
                        f.write(req.content)
                    break
                elif (req.status_code == 404 and
                      'missing' in provider and
                      provider['missing'] in ['ok', 'ignore']):
                    failure_ok = True
                    # break retry loop
                    break
        else:
            raise Exception("failed to download tile files")
    elif re.match('^file://', url):
        logger.debug(f"copying file... {url}")
        url = re.sub('^file:/+','/', url)
        try:
            shutil.copy(url, dl_file)
        except IOError:
            if ('missing' in provider and
                 provider['missing'] in ['ok', 'ignore']):
                failure_ok = True
    if failure_ok:
        # skip rest of inp loop
        return tile_files

    if ('unpack' not in provider or
        provider['unpack'] in ['', 'tif', 'false']) and \
            dl_file.endswith('tif'):
        inputfiles = [dl_file]
    elif ('unpack' in provider and
          provider['unpack'].startswith(('zip', 'unzip'))):
        with zipfile.ZipFile(dl_file, 'r') as zf:
            pattern = re.sub('^(un|)zip[:/]*', '', provider['unpack'])
            unpack = [x for x in zf.namelist()
                      if PurePath(x).match(pattern)]
            inputfiles = []
            for un in unpack:
                with zf.open(un) as fz:
                    with open(os.path.basename(un), 'wb') as fu:
                        fu.write(fz.read())
                inputfiles.append(os.path.basename(un))
        if len(inputfiles) == 0:
            logger.warning(f"no data unpacked from {dl_file}")
    else:
        logger.error(f"dont know how to handle download: {dl_file}")

    if 'resolution' in provider:
        out_res = provider['resolution']
    else:
        out_res = 25
    if 'CRS' in provider:
        srcsrs = provider['CRS']
    else:
        srcsrs = None
    if 'utm_remove_zone' in provider and \
            provider['utm_remove_zone'] in ['True', 'true', 'yes']:
        utm_remove_zone = True
    else:
        utm_remove_zone = False
    for inputfile in inputfiles:
        if inputfile.endswith('tif'):
            tf1 = inputfile
        elif inputfile.endswith('xyz'):
            if os.stat(inputfile).st_size == 0:
                logger.debug(f"skipping empty  ... {inputfile}")
                os.remove(inputfile)
                continue
            tf1 = re.sub(r'\.xyz$', '.tif', inputfile)
            logger.debug(f"converting tile ... {inputfile} -> {tf1}")
            # returns a tuple containing file handle and the abs pathname!
            csvhdl, csvfile = tempfile.mkstemp(
                prefix='dgm', suffix='.csv', dir=TEMP)
            got_csv = xyz2csv(inputfile, csvfile,
                              utm_remove_zone=utm_remove_zone)
            os.remove(inputfile)
            if not got_csv:
                logger.warning(f"did not convert ... {inputfile}")
                os.close(csvhdl)
                os.remove(csvfile)
                continue
            gdal.Translate(destName=tf1,
                           srcDS=csvfile,
                           outputSRS=srcsrs,
                           noData=-9999,
                           )
            os.close(csvhdl)
            os.remove(csvfile)
        else:
            raise Exception(f'cannot handle {inputfile}')
        tfxx = os.path.splitext(tf1)[0] + ".reduced.tif"
        logger.debug(f"resampling tile ... {tf1} -> {tfxx}")
        try:
            gdal.Warp(destNameOrDestDS=tfxx,
                      xRes=out_res,
                      yRes=out_res,
                      dstSRS="EPSG:5677",
                      srcDSOrSrcDSTab=tf1,
                      format="GTiff")
            tile_files.append(tfxx)
        except Exception as e:
            logger.error(str(e))
        os.remove(tf1)
    if os.path.exists(dl_file):
        os.remove(dl_file)
    return tile_files


# -------------------------------------------------------------------------


def ass_merge_tiles(target, tile_files):
    # merge the GeoTiff Files from all tiles into one file
    if os.path.exists(target):
        logger.info("removing old source file")
        os.remove(target)
    logger.debug("merging tiles ...")
    if DEM_FMT.endswith('.tif'):
        gdal_merge.main(["", "-co", "compress=lzw",
                         "-o", target,
                         ] + tile_files)
    elif DEM_FMT.endswith('.nc'):
        gdal_merge.main(["",
                         "-of", "netCDF",
                         "-co", "FORMAT=NC4C",
                         "-co", "COMPRESS=DEFLATE",
                         "-co", "ZLEVEL=9",
                         "-o", target,
                         ] + tile_files)
    else:
        raise Exception(f'cannot handle DEM_FMT: {DEM_FMT}')
    logger.debug(f"... written {target}")


# -------------------------------------------------------------------------


def assemble_DGMxx(path: str, name: str, replace: bool,
                   provider: dict):
    target = os.path.join(path, DEM_FMT % name)
    logger.debug(f'data file path: {target}')
    if os.path.exists(target) and not replace:
        logger.info("skipping because dataset exists: %s" % name)
        return False

    base_url = '/'.join((provider['host'], provider['path']))
    if 'check_cert' in provider:
        verify = provider['check_cert']
    else:
        verify = True
    filelist = provider['filelist']
    # switch formats:
    method = input_files = capabilities = layer = None
    if isinstance(filelist, list):
        input_files = filelist
        method = 'http'
    elif isinstance(filelist, str):
        filelist_name = re.sub(r'::.*$', '', filelist)
        url = '/'.join((base_url, filelist_name))
        if filelist.endswith(('xml', 'meta4')):
            # xml
            logger.debug("downloading xml metadata: %s" % url)
            with requests.get(url, allow_redirects=True, verify=verify) as rsp:
                input_files = xmlpath(xml=rsp.content.decode(),
                                      path=provider['xmlpath'])
            method = 'http'
        elif filelist.endswith(('json', 'geojson')):
            # xml
            logger.debug("downloading json metadata: %s" % url)
            with requests.get(url, allow_redirects=True, verify=verify) as rsp:
                input_files = jsonpath(json_obj=rsp.json(),
                                       path=provider['jsonpath'])
                method = 'http'
        elif filelist.endswith(('html')):
            # html
            logger.debug("downloading html metadata: %s" % url)
            with requests.get(url, allow_redirects=True, verify=verify) as rsp:
                text = rsp.content.decode()
                links = [x for x in re.findall(r'href="(.+?)"', text)]
                patt = provider['links']
                input_files = [x for x in links if bool(re.match(patt,x))]
                method = 'http'
        elif filelist == 'generate':
            exp_val = []
            for x in provider['values']:
                if isinstance(x, list):
                    exp_val.append(x)
                else:
                    exp_val.append(_tools.parse_time_string(x))
            combval = itertools.product(*exp_val)
            input_files = [provider['format'] % x for x in combval]
            method = 'http'
        elif filelist == 'wms':
            capabilities = '/'.join((provider['host'], provider['path']))
            if 'layer' in provider:
                layer = provider['layer']
            else:
                layer = 'default'
            method = 'wms'
        else:
            raise NotImplementedError(f'can`t handle filelist: {filelist}')
    else:
        raise TypeError('filelist muste be list or str')

    if method == 'http':
        # parallel processing of input_files:
        thread_args = []
        for inp in input_files:
            thread_args.append((inp, base_url, verify, provider))
        tile_files = []
        if logger.getEffectiveLevel() <= logging.DEBUG:
            procs = 1
        else:
            procs = None
        i = 0
        with Pool(procs) as pool:
            for tfs in _tools.progress(pool.imap_unordered(
                    ass_process_input, thread_args),
                    total=len(thread_args)):
                i = i + 1
                logger.debug("file %5d / %5d" % (i, len(thread_args)))
                tile_files += tfs
    elif method == 'wms':
        import _wms_download
        tile_files = _wms_download.download_wms(
            url=capabilities, layer=layer, epsg=provider['CRS'],
            res=provider['resolution'])
    else:
        raise ValueError(f'method {method} not implemented')

    # merge the GeoTiff Files from all tiles into one file
    ass_merge_tiles(target, tile_files)

    return True


# -------------------------------------------------------------------------


def assemble_GLO_30(path, name="GLO_30", replace=False, args: dict = {}):
    target = os.path.join(path, DEM_FMT % name)
    logger.debug(f'data file path: {target}')
    if os.path.exists(target) and not replace:
        logger.info("dataset exists ... %s" % name)
        return False

    download_dir = ("https://prism-dem-open.copernicus.eu/" +
                    "pd-desk-open-access/prismDownload/" +
                    "COP-DEM_GLO-30-DGED__2022_1/")
    file_fmt = "Copernicus_DSM_10_N%02i_00_E%03i_00.tar"

    for lat in range(47, 54):
        for lon in range(5, 16):
            url = download_dir + file_fmt % (lat, lon)
            logger.debug("downloading ... %s" % url)
            tar_file, _ = download(url, os.path.basename(url))
            name_root = tar_file.replace(".tar", "")
            with tarfile.open(tar_file) as tf:
                to_extract = [x for x in tf.getmembers()
                              if name_root + "/DEM/" in x.name]
                for x in to_extract:
                    # remove path from name of tar member to extract
                    x.name = os.path.basename(x.name)
                    logger.debug("... extracting %s" % x.name)
                    # now extract tar member to current dir
                    tf.extract(x, '.')
    # merge the GeoTiff Files from all tiles into one file
    target = os.path.join(path, DEM_FMT % "GLO-30")
    tile_files = glob.glob("Copernicus_*.tif")
    ass_merge_tiles(target, tile_files)

    return


# -------------------------------------------------------------------------


def assebmle_GTOPO30(path: str, name="GTOPO30",
                     replace=False, args: dict = {}):
    support_url = ("https://data.rda.ucar.edu/ds758.0/support/"
                   + "GTOPO30support.tar.gz")
    download_fmt = ("https://data.rda.ucar.edu/ds758.0/elevtiles/" +
                    "%s.DEM.gz")
    tiles = ["W020N90"]
    # known_tiles = \
    # "W180N90 W140N90 W100N90 W060N90 W020N90 E020N90 E060N90 E100N90"\
    # "E140N90 W180N40 W140N40 W100N40 W060N40 W020N40 E020N40 E060N40"\
    # "E100N40 E140N40 W180S10 W140S10 W100S10 W060S10 W020S10 E020S10"\
    # "E060S10 E100S10 E140S10 W180S60 W120S60 W060S60 W000S60 E060S60"\
    # "E120S60 ".split()
    # get the single archive that holds the supportive
    # files for all tiles
    target = os.path.join(path, DEM_FMT % "GTOPO30")
    logger.debug(f'data file path: {target}')
    if os.path.exists(target) and not replace:
        logger.info("dataset exists ... %s" % name)
        return False
    logger.debug("downloading ... %s" % support_url)
    support_file, _ = download(
        support_url, os.path.basename(support_url))
    with tarfile.open(support_file) as support_tar:
        # no get every tile we want
        for tile in tiles:
            # extract the matching supportive files
            to_extract = [x.name for x in support_tar.getmembers()
                          if tile in x.name]
            support_tar.extractall(members=to_extract)
            # now download the actual data file for the tile
            download_url = download_fmt % tile
            logger.debug("downloading ... %s" % download_url)
            tile_file, _ = download(
                download_url, os.path.basename(download_url))
            # expand the terrain data holding file *.DEM
            # and convert it to a GeoTiff file
            tile_dem = tile_file.replace(".gz", "")
            tile_tif = tile_dem.replace(".DEM", ".tif")
            logger.debug("... decompressing %s" % tile_dem)
            with gzip.open(tile_file, 'rb') as tf:
                with open(tile_dem, 'wb') as td:
                    shutil.copyfileobj(tf, td, length=16 * 1024)
            logger.debug("... converting to %s" % tile_tif)
            gdal.Warp(destNameOrDestDS=tile_tif,
                      srcDSOrSrcDSTab=tile_dem,
                      format="GTiff")
    # merge the GeoTiff Files from all tiles into one file
    tile_files = glob.glob("*.tif")
    ass_merge_tiles(target, tile_files)

    return


# -------------------------------------------------------------------------


def assemble_DGM25_RP(path, name="DGM25-RP", replace=False):
    target = os.path.join(path, DEM_FMT % name)
    logger.debug(f'data file path: {target}')
    if os.path.exists(target) and not replace:
        logger.info("dataset exists ... %s" % name)
        return False

    url = "https://vermkv.service24.rlp.de/opendat/dgm25/dgm25.zip"
    logger.debug("downloading ... %s" % url)
    zip_file, _ = download(url, os.path.basename(url))
    logger.debug("extracting ... %s" % zip_file)
    shutil.unpack_archive(zip_file)
    for tile_xyz in glob.glob("*.xyz"):
        logger.debug("converting tile ... %s" % tile_xyz)
        tile_tif = tile_xyz.replace(".xyz", ".tif")
        try:
            gdal.Warp(destNameOrDestDS=tile_tif,
                      dstSRS="EPSG:5677",
                      srcDSOrSrcDSTab=tile_xyz,
                      srcSRS="EPSG:25832",
                      format="GTiff")
        except Exception as e:
            logger.error(str(e))
    # merge the GeoTiff Files from all tiles into one file
    tile_files = glob.glob("DGM25_*.tif")
    ass_merge_tiles(target, tile_files)

    return True


# -------------------------------------------------------------------------


def provide_dem(source: str, path: str = None,
                force: bool = False, method: str = 'download'):
    if path is None:
        path = find_writeable_storage(path, _tools.STORAGE_TERRAIN)
    dataset = dataset_get(source)
    logger.info("downloading terrain source %s" % source)
    if method == 'download':
        if dataset.uri is None:
            raise Exception("Dataset has no download uri, assemble it.")
        dataset.download(path)
    elif method == 'assemble':
        # change to temp directory
        pwd = os.getcwd()
        with tempfile.TemporaryDirectory(dir=TEMP) as temp_dir:
            os.chdir(temp_dir)
            logger.debug('calling %s' % str(dataset.assemble))
            dataset.assemble(path, source, force, dataset.arguments)
            # return before clean up
            os.chdir(pwd)
    else:
        raise ValueError("method must be either 'download' or 'assemble'")

    # auxiliary files:
    if 'licence' in DATASET_DEFINITIONS[source] and \
            DATASET_DEFINITIONS[source]['license'] is not None:
        lic_file = os.path.join(path, dataset.file_license)
        lic_src, lic_id = DATASET_DEFINITIONS[source]['licence'].split(':')
        if lic_src == 'spdx':
            lic_url = ("https://spdx.org/licenses/%s.json" %
                       DATASET_DEFINITIONS[source]['licence'])
            with requests.get(lic_url).json() as lic_json:
                with open(lic_file, 'wb') as f:
                    f.write(lic_json['licenseText'])
        elif lic_src == 'file':
            if lic_id in [None, '']:
                lic_aux = os.path.join(str(DIST_AUX_FILES), lic_file)
            else:
                lic_aux = os.path.join(str(DIST_AUX_FILES), lic_id)
            shutil.copy(lic_aux, lic_file)
    if 'notice' in DATASET_DEFINITIONS[source] and \
            DATASET_DEFINITIONS[source]['notice'] is not None:
        not_file = os.path.join(path, dataset.file_license)
        with open(not_file, 'w') as f:
            f.write(DATASET_DEFINITIONS[source]['notice'])
    return


# -------------------------------------------------------------------------


def show_notice(storage_path, source):
    print('data copyright notice:')
    with open(os.path.join(storage_path,
                           "%s.NOTICE.txt" % source), "r") as f:
        for x in f.readlines():
            print(x)


# -------------------------------------------------------------------------
# -------------------------------------------------------------------------


def era5_getyear(opts):
    """
    Downloads ERA5 reanalysis data for a specific year and saves it as a NetCDF file.

    The function calls the Climate Data Store (CDS) API to retrieve a specific set of meteorological variables for
    the entire year specified by the user. It requests data in NetCDF format, covering a predefined geographic
    extent focusing on Alaska and Europe. This function is specifically designed to automate the retrieval process
    for ERA5 weather variables, saving the data in a structured format that's easier to work with for further analysis.

    :param opts: A tuple containing two elements:
                 - `y`: The year for which to download the data (integer).
                 - `path`: The directory path where the NetCDF file should be saved (string).
    :type opts: tuple

    :returns: None. The function saves a NetCDF file to the specified path but does not return any value.

    **Example usage**:

    .. code-block:: python

        # To download ERA5 data for the year 2020 and save it to the specified directory
        era5_getyear((2020, '/path/to/directory'))

    The function crafts a filename based on the year, prefixing it with `era5_ak_eu_` to denote the region and
    type of data retrieved. Ensure that the specified directory exists and is writable. The CDS API key must also
    be configured as per the `cdsapi` package documentation.

    Note:
    The retrieval of data from the CDS API may incur charges or require acceptance of license terms depending
    on your use case and the volume of data requested. Please consult the Copernicus Climate Data Store's
    documentation and licensing agreements for more information.
    """

    yy, path = opts
    year = '{:04d}'.format(yy)
    ncname = 'era5_ak_eu_' + year + '.nc'
    target = os.path.join(path, ncname)
    c = cdsapi.Client()
    c.retrieve(
        'reanalysis-era5-single-levels',
        {
            'product_type': 'reanalysis',
            'variable': [
                '10m_u_component_of_wind', '10m_v_component_of_wind', '2m_dewpoint_temperature',
                '2m_temperature', 'forecast_surface_roughness', 'friction_velocity',
                'surface_latent_heat_flux', 'surface_pressure', 'surface_sensible_heat_flux',
                'low_cloud_cover', 'total_cloud_cover',
                'cloud_base_height', 'total_precipitation',
            ],
            'year': year,
            'month': [
                '01', '02', '03',
                '04', '05', '06',
                '07', '08', '09',
                '10', '11', '12',
            ],
            'day': [
                '01', '02', '03',
                '04', '05', '06',
                '07', '08', '09',
                '10', '11', '12',
                '13', '14', '15',
                '16', '17', '18',
                '19', '20', '21',
                '22', '23', '24',
                '25', '26', '27',
                '28', '29', '30',
                '31',
            ],
            'time': [
                '00:00', '01:00', '02:00',
                '03:00', '04:00', '05:00',
                '06:00', '07:00', '08:00',
                '09:00', '10:00', '11:00',
                '12:00', '13:00', '14:00',
                '15:00', '16:00', '17:00',
                '18:00', '19:00', '20:00',
                '21:00', '22:00', '23:00',
            ],
            'area': [
                71, -12, 33,
                36,
            ],
            'format': 'netcdf',
        },
        target)


# -------------------------------------------------------------------------


def assemble_ERA5(path: str, years: list):
    """
    Downloads and assembles ERA5 reanalysis data for a list of specified years, saving the data to a designated path.

    This function serves as a wrapper around the `era5_getyear` function, facilitating the batch retrieval of ERA5
    data for multiple years. It utilizes multiprocessing to download data in parallel, thereby significantly reducing
    the overall time required for downloading large datasets. Each year's data is saved as a separate NetCDF file within
    the specified directory path.

    :param path: The file system path where the downloaded NetCDF files will be saved.
    :type path: str
    :param years: A list of years for which ERA5 data should be downloaded. Each year should be an integer within the
                  valid range (1940 to the current year).
    :type years: list

    :raises ValueError: If any year in the `years` list is outside the allowable range of 1940 to the current year.

    **Example usage**:

    .. code-block:: python

        # To download ERA5 data for the years 2018 to 2020 and save to '/data/ERA5'
        assemble_ERA5('/data/ERA5', [2018, 2019, 2020])

    Note:
    - The function assumes that the `era5_getyear` function is defined and correctly set up to retrieve ERA5 data.
    - The parallel downloading process is set to use 10 worker processes. Adjust this value in the `Pool` initialization
      as needed based on system resources and desired performance.
    - Ensure that sufficient disk space is available at the specified path to accommodate the downloaded data files.

    Ensure that the necessary libraries are installed and configured, including `cdsapi` for data retrieval and `multiprocessing`
    for parallel processing. Also, verify that your CDS API key is set up correctly as per the CDS API documentation.
    """

    # create option tuples
    combi = []
    for y in years:
        if not 1940 <= y <= dt.datetime.now().year:
            raise ValueError(f"year is out of range (1940-today): {y}")
        combi.append((y, path))
    # get data in parallel directly to storage
    with Pool(10) as pool:
        pool.map(era5_getyear, combi)


# -------------------------------------------------------------------------


def cerraname(y, lt=None):
    name = 'cerra_ak_eu_%04i' % y
    if lt is not None:
        name += '_%01i' % lt
    return name


# -------------------------------------------------------------------------


def cerra_getyear(opts):
    """
    Downloads and processes a year's worth of CERRA dataset as GRIB files,
    then converts them to NetCDF format for easier use.

    This function takes a tuple containing the year (`y`) and lead time (`lt`) for the forecast data.
    It builds the filename for the GRIB file from these parameters and checks if it exists locally.
    If not, it uses the CDS API to retrieve the data for all specified variables over the entire year, saving it as a GRIB file.
    After downloading, the function processes the GRIB file, converting it to a NetCDF file for more convenient analysis and removes
    the original GRIB file to conserve space.

    Requires the `cdsapi` and `cdo` (Climate Data Operators) packages, as well as an active Copernicus account for data retrieval.

    :param opts: A tuple containing two elements:
                 - `y` (int): The year of the dataset to retrieve.
                 - `lt` (int): The lead time in hours for the forecast data.
    :type opts: tuple

    A sample of expected parameter format: `(2023, 48)`

    :returns: None. The function's primary purpose is file I/O (downloading and converting data).
              It does not return a value but will print status messages regarding its progress.

    :raises FileNotFoundError: If the CDO command fails to find the downloaded GRIB file for conversion.

    **Example usage**:

    .. code-block:: python

        # To download and process the CERRA data for the year 2023 with a lead time of 48 hours
        cerra_getyear((2023, 48))

    Ensure the `cerraname` function is defined globally and properly constructs the filename based on the year and lead time.
    This function assumes `cerraname` returns a base filename to which `.grib` or `.nc` is appended for output files.

    Note: The 'cdsapi' Client is used for data retrieval, requiring appropriate credentials set up as per the
    CDS API's documentation. The 'cdo' tool is called for data processing, necessitating its installation and
    availability in the system's PATH.
    """
    y, lt = opts
    gribname = cerraname(y, lt) + '.grib'
    c = cdsapi.Client()
    if not os.path.exists(gribname):
        print("cds getting: " + gribname)
        opts = (
            'reanalysis-cerra-single-levels',
            {
                'data_type': 'reanalysis',
                'product_type': 'forecast',
                'variable': [
                    '10m_wind_direction', '10m_wind_speed', '2m_relative_humidity',
                    '2m_temperature', 'low_cloud_cover', 'medium_cloud_cover',
                    'momentum_flux_at_the_surface_u_component',
                    'momentum_flux_at_the_surface_v_component', 'surface_latent_heat_flux',
                    'surface_pressure', 'surface_roughness', 'surface_sensible_heat_flux',
                    'total_cloud_cover', 'total_precipitation',
                ],
                'level_type': 'surface_or_atmosphere',
                'year': '%04i' % y,
                'month': [
                    '01', '02', '03',
                    '04', '05', '06',
                    '07', '08', '09',
                    '10', '11', '12',
                ],
                'day': [
                    '01', '02', '03',
                    '04', '05', '06',
                    '07', '08', '09',
                    '10', '11', '12',
                    '13', '14', '15',
                    '16', '17', '18',
                    '19', '20', '21',
                    '22', '23', '24',
                    '25', '26', '27',
                    '28', '29', '30',
                    '31',
                ],
                'time': [
                    '00:00', '03:00', '06:00',
                    '09:00', '12:00', '15:00',
                    '18:00', '21:00',
                ],
                'leadtime_hour': '%i' % lt,
                'format': 'grib',
            },
            gribname
        )
        c.retrieve(*opts)
        ncname = cerraname(y, lt) + '.nc'
        print("cdo processing: " + ncname)
        cdo.selindexbox('489,649,479,659', options='-f nc',
                        input=gribname, output=ncname)
        os.remove(gribname)


# -------------------------------------------------------------------------


def assemble_CERRA(path: str, years: list):
    """
    Downloads, extracts, and merges CERRA dataset forecasts for specified years into single NetCDF files per year.

    This function orchestrates the retrieval and processing of CERRA forecast datasets for a list of years.
    For each year, it fetches data for multiple lead times, extracts a specific region from the datasets, and then merges
    the forecast data into a single NetCDF file per year. The operation utilizes the Climate Data Operators (CDO) for data
    manipulation and assumes a temporary directory is defined for intermediate data storage.

    :param path: The directory path where the final merged NetCDF files will be stored.
    :type path: str
    :param years: A list of years (integer) for which CERRA data should be downloaded and processed. The years should fall
                  within the range of 1940 to the current year.
    :type years: list

    :raises ValueError: If any of the years specified is outside the valid range (1940 to the current year).

    Example usage:

    .. code-block:: python


    To process CERRA data for the years 2015 to 2017

        assemble_CERRA('/path/to/final/storage', [2015, 2016, 2017])

    Notes:
    - The function utilizes `cdo.Cdo` for data manipulation tasks such as merging time steps. Make sure that python-cdo is
      installed and properly configured along with the actual CDO command-line tools.
    - A temporary directory for storing intermediate data files is required. This directory is assumed to be configured before
      the function call.
    - After processing, intermediate data files are removed to free up space.

    This function assumes the presence and configurability of the `cerra_getyear` and `cerraname` functions, which are responsible
    for retrieving yearly datasets and generating filenames based on the year and lead time, respectively. It also assumes that
    a global `TEMP` variable is defined and points to a valid temporary directory for intermediate files.
    """
    temp_path = TEMP
    data = cdo.Cdo(tempdir=temp_path)
    print("python-cdo version: %s" % data.__version__())
    print("cdo        version: %s" % data.version())
    data.debug = True
    data.cleanTempDir()

    # get sets of bunches to retrieve
    combi = []
    for y in years:
        if not 1940 <= y <= dt.datetime.now().year:
            raise ValueError(f"year is out of range (1941-2019): {y}")
        for lt in range(1, 4):
            combi.append((y, lt))

    # get data and extract region
    with Pool(10) as pool:
        p = pool.map(cerra_getyear, combi)

    # combine forecasts
    for yr in set([x for x, _ in combi]):
        lts = set([y for x, y in combi if x == yr])
        infiles = [cerraname(yr, lt) + '.nc' for lt in lts]
        target = os.path.join(path, cerraname(yr, None) + '.nc')
        data.mergetime(
            input=" ".join([
                data.setgridtype('curvilinear', input=x)
                for x in infiles
            ]),
            output=target,
            options='-f nc4 -z zip_6 --reduce_dim'
        )
        for x in infiles:
            os.remove(x)


# -------------------------------------------------------------------------


def provide_weather(source: str, path: str = None,
                    years: list = None, method: str = 'download'):
    """
    Manages the downloading and organizing of weather data from specified sources for given years into a target directory.

    This function serves as a high-level interface for downloading weather datasets (for example, ERA5 or CERRA) for a specified
    set of years and organizing them into a specified directory. The function currently supports the 'download' method with potential
    for future expansion.

    :param source: The name of the weather dataset source. Currently supports "ERA5" or "CERRA".
    :type source: str
    :param path: Optional; the file system path where the downloaded data will be saved. If not specified, the function
                 attempts to find a writable storage location using `find_writeable_storage`.
    :type path: str, optional
    :param years: Optional; a list of integer years for which to download the data. If not specified, no year-specific
                  data fetching is performed, which may depend on the implementation details of the dataset handling functions.
    :type years: list, optional
    :param method: Optional; the method to use for obtaining the data. Currently, only "download" is implemented, but the parameter
                   is designed to accommodate future methods like "cache" or "stream".
    :type method: str, optional

    :returns: A boolean value indicating the success (`True`) or failure (`False`) of the data downloading and organization process.

    Example usage:

    .. code-block:: python

        # To download ERA5 data for the years 2020 and 2021 into the default storage location
        success = provide_weather("ERA5", years=[2020, 2021])

    Note:
    - This function logs its operations, including informational messages on progress and errors encountered.
    - The actual implementation for finding writable storage or the setup for the logger is not defined in this function, and
      should be provided in the surrounding context.

    Raises:
    - This function may raise exceptions internally but catches them to return a boolean success status. Detailed error
      information is logged.
    """

    # param method is implemented for future use
    if path is None:
        path = find_writeable_storage(path, _tools.STORAGE_TERRAIN)
    logger.info("downloading weather source %s" % source)
    success = True
    pwd = os.getcwd()
    with tempfile.TemporaryDirectory() as temp_dir:
        os.chdir(temp_dir)
        try:
            if source == "ERA5":
                assemble_ERA5(path, years)
            elif source == "CERRA":
                assemble_CERRA(path, years)
            else:
                logger.error("unknown dataset to download %s" % source)
                success = False
        except Exception as e:
            logger.error(str(e))
            success = False
    # return before clean up
    os.chdir(pwd)
    return success


# -------------------------------------------------------------------------


# initialize
DATASETS = [DataSet(name=k, **v) for k, v in DATASET_DEFINITIONS.items()]
dataset_scan()

# https://geodaten.schleswig-holstein.de/gaialight-sh/_apps/dladownload/dl-dgm1.html
# https://geodaten.schleswig-holstein.de/gaialight-sh/_apps/dladownload/multi.php?action=start&type=dgm1&id=513
# {"success":true,"id":"cKdXn8","statusUrl":"https:\/\/geodaten.schleswig-holstein.de\/gaialight-sh\/_apps\/dladownload\/multi.php"}
# https://geodaten.schleswig-holstein.de/gaialight-sh/_apps/dladownload/multi.php?action=status&job=cKdXn8
# https://geodaten.schleswig-holstein.de/gaialight-sh/_apps/dladownload/multi.php?action=download&job=mBeZ3T
