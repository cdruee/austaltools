#!/bin/bash

DOWNLOAD="https://vermkv.service24.rlp.de/opendat/dgm25/dgm25.zip"

WORKING_DIR=$( pwd )

# create temp directory
TEMP_DIR=$( mktemp -d --tmpdir=$WORKING_DIR )
pushd $TEMP_DIR

# get and unpack download archive
echo "downloading $DOWNLOAD"
wget -nv $DOWNLOAD
FILE=$( basename $DOWNLOAD )
echo "unpacking $FILE"
unzip -q $FILE

# convert to SRS that includes false easting (plus zone number * 100000)
for XYZ in *.xyz
do
  gdalwarp -s_srs EPSG:25832 -t_srs EPSG:5677 $XYZ ${XYZ%.xyz}.tif
done
# combine to single compressed file
gdal_merge.py -co compress=lzw -o $WORKING_DIR/DGM25-RP.lzw.tif DGM25_*.tif

# clean up
popd
rm -rf $TEMP_DIR
