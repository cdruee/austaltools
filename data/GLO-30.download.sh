#!/bin/bash

WORKING_DIR=$( pwd )
#create temp directory
TEMP_DIR=$( mktemp -d --tmpdir=$WORKING_DIR )

pushd $TEMP_DIR

DOWNLOAD_DIR="https://prism-dem-open.copernicus.eu/pd-desk-open-access/prismDownload/COP-DEM_GLO-30-DGED__2022_1/"
FILE_FMT="Copernicus_DSM_10_N%02i_00_E%03i_00.tar"

for ((LAT=47;LAT<=54;LAT++))
do
  for ((LON=5;LON<=15;LON++))
  do
    FILE=$( printf $FILE_FMT $LAT $LON )
    echo "downloading $FILE"
    wget -nv "$DOWNLOAD_DIR$FILE"
    tar --wildcards --strip-components 2 -xf $FILE ${FILE%.tar}/DEM/*
  done
done
gdal_merge.py -co compress=lzw -o $WORKING_DIR/GLO-30.lzw.tif Copernicus_*.tif

popd
rm -rf $TEMP_DIR
