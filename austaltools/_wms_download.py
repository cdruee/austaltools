#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
module for extracting information from an WMAS service
"""
import itertools
import logging
import os
from osgeo import osr
from osgeo import ogr
from osgeo import gdal

from owslib.wms import WebMapService

try:
    from . import _tools
except ImportError:
    import _tools

logger = logging.getLogger(__name__)

NX_DEFAULT = 1024
NY_DEFAULT = 1024

def get_projection(epsgstring):
    _, epsg = epsgstring.split(':', 1)
    proj = osr.SpatialReference()
    proj.ImportFromEPSG(int(epsg))
    return proj


def set_projection(self, epsg_code):
    epsg = epsg_code
    proj = get_projection(epsg)
    return proj


def download_raster(wms, epsg, layer, resolution=1, nx=None, ny=None,
                    boundingbox=None):
    """Download a raster dataset by downloading different tiles and merging
    them. Reclassify unique RGB value if necessary."""
    logger.info('Downloading data ...')
    if nx is None:
        nx = NX_DEFAULT
    else:
        nx = int(nx)
    if ny is None:
        ny = NY_DEFAULT
    else:
        ny = int(ny)
    proj = get_projection(epsg)
    # calculate the number and bounds of the tiles to download
    if boundingbox is None:
        boundingbox = wms.contents[layer].boundingBox
        boundingbox = reproject_boundingbox(boundingbox, proj)
    else:
        boundingbox = boundingbox
    minx = boundingbox[0]
    miny = boundingbox[1]
    maxx = boundingbox[2]
    maxy = boundingbox[3]
    x_extent = maxx - minx
    y_extent = maxy - miny
    x_npix = x_extent / resolution
    y_npix = y_extent / resolution
    x_ntiles = int(x_npix // nx)  # number of tiles in x direction
    if x_npix % nx > 0:
        x_ntiles += 1
    y_ntiles = int(y_npix // ny)  # number of tiles in y direction
    if y_npix % ny > 0:
        y_ntiles += 1

    x_tile_bounds = []
    for xt in range(x_ntiles):
        x_tile_bounds.append(minx + xt * nx * resolution)
    x_tile_bounds.append(maxx)

    y_tile_bounds = []
    for yt in range(y_ntiles):
        y_tile_bounds.append(miny + yt * ny * resolution)
    y_tile_bounds.append(maxy)

    tottiles = x_ntiles * y_ntiles
    datafiles = []
    for i, j in _tools.progress(itertools.product(
            range(x_ntiles), range(y_ntiles))):
        xbounds = (x_tile_bounds[i], x_tile_bounds[i + 1])
        x_size = (xbounds[1] - xbounds[0]) / resolution
        ybounds = (y_tile_bounds[j], y_tile_bounds[j + 1])
        y_size = (ybounds[1] - ybounds[0]) / resolution
        filename = download_tile(wms,
                                 name='tile_%03d_%03d' % (i,j),
                                 layer=layer,
                                 epsg=epsg,
                                 bbox=(xbounds[0], ybounds[0],
                                       xbounds[1], ybounds[1]),
                                 size=(x_size, y_size))
        datafiles.append(filename)
    return datafiles


def download_tile(wms, name, layer, epsg, bbox, size):
    img = wms.getmap(layers=[layer],
                     styles=['default'],
                     srs=epsg,
                     bbox=bbox,
                     size=size,
                     format='image/tiff',
                     transparent=True)
    geotiffname = f'{name}.tif'
    imagename = f'{name}.tiff'
    with open(imagename, 'wb') as f:
        f.write(img.read())
    ullr = (bbox[0], bbox[3], bbox[2], bbox[1])
    scalehint = {k: float(v) for k,v in wms.contents[layer].scaleHint.items()}
    ds = gdal.Open(imagename)
    typerange={
        gdal.GDT_Byte: {'min':0, 'max': 255},
        # only GDAL >=3.7 :
        # gdal.GDT_Int8: {'min': -128, 'max': 127},
        gdal.GDT_Int16: {'min': -32768, 'max': 32767},
        gdal.GDT_UInt16: {'min': -32768, 'max': 32767},
        gdal.GDT_Int32:  {'min':  -2147483648, 'max': 2147483647},
    }
    imghint = typerange[ds.GetRasterBand(1).DataType]
    gdal.Translate(destName=geotiffname,
                   srcDS=imagename,
                   outputSRS=epsg,
                   outputBounds=ullr,
                   outputType= gdal.GDT_Float32,
                   scaleParams=[[imghint['min'], imghint['max'],
                                scalehint['min'], scalehint['max']]],
                   )
    os.remove(imagename)
    return geotiffname


def get_projection(epsgstring):
    _, epsg = epsgstring.split(':', 1)
    proj = osr.SpatialReference()
    proj.ImportFromEPSG(int(epsg))
    return proj


def reproject_boundingbox(bbox, target_proj):
    if len(bbox) != 5:
        raise ValueError('invalid bounding box tuple')
    source_proj = get_projection(bbox[4])
    source_proj.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    target_proj.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    transform = osr.CoordinateTransformation(source_proj, target_proj)
    point1 = ogr.CreateGeometryFromWkt("POINT (%s %s)" %
                                       (bbox[0], bbox[1]))
    point2 = ogr.CreateGeometryFromWkt("POINT (%s %s)" %
                                       (bbox[2], bbox[3]))
    point1.Transform(transform)
    point2.Transform(transform)

    return (point1.GetX(), point1.GetY(), point2.GetX(), point2.GetY())


def download_wms(url, layer, res=None, data_format=None, epsg=None, boundingbox=None):
    wms = WebMapService(url)

    if data_format is None:
        data_format = 'raster'

    if res is None:
        res = 25.
    else:
        res = float(res)

    if epsg is None:
        epsg = 'EPSG:4326'

    if boundingbox is not None:
        boundingbox = \
            tuple([float(i) for i in boundingbox.split(',')])

    datafiles = download_raster(wms, epsg, layer,
                                resolution=res , boundingbox=boundingbox)
    return datafiles
