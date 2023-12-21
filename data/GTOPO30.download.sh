#!/bin/bash

SUPPORT="https://data.rda.ucar.edu/ds758.0/support/GTOPO30support.tar.gz"
DOWNLOAD="https://data.rda.ucar.edu/ds758.0/elevtiles/%s.DEM.gz"
TILES="W020N90"
#TILES=""\
#"W180N90 "\
#"W140N90 "\
#"W100N90 "\
#"W060N90 "\
#"W020N90 "\
#"E020N90 "\
#"E060N90 "\
#"E100N90 "\
#"E140N90 "\
#"W180N40 "\
#"W140N40 "\
#"W100N40 "\
#"W060N40 "\
#"W020N40 "\
#"E020N40 "\
#"E060N40 "\
#"E100N40 "\
#"E140N40 "\
#"W180S10 "\
#"W140S10 "\
#"W100S10 "\
#"W060S10 "\
#"W020S10 "\
#"E020S10 "\
#"E060S10 "\
#"E100S10 "\
#"E140S10 "\
#"W180S60 "\
#"W120S60 "\
#"W060S60 "\
#"W000S60 "\
#"E060S60 "\
#"E120S60 "\
#""

WORKING_DIR=$( pwd )

# create temp directory
TEMP_DIR=$( mktemp -d --tmpdir=$WORKING_DIR )
pushd $TEMP_DIR

# get and  unpack download archive
echo "downloading $SUPPORT"
wget -nv $SUPPORT

for TILE in $TILES
do
  URL=$( printf $DOWNLOAD $TILE )
  echo "downloading $URL"
  wget -nv $URL
  GZFILE=$( basename $URL )
  echo "unpacking $GZFILE"
  gzip -dq $GZFILE
  FILE=${GZFILE%.gz}
  echo "exctracting suppotive files"
  tar -zxvf $( basename $SUPPORT ) --wildcards '*'$TILE'*'

  gdalwarp -of GTiff $FILE ${FILE%.DEM}.tif

done

# combine to single compressed file
gdal_merge.py -co compress=lzw -o $WORKING_DIR/GTOPO30.lzw.tif *.tif

## clean up
#popd
#rm -rf $TEMP_DIR
