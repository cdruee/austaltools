#!/bin/bash
#
# automatic tagging if package version in setup.py is changed
#

PYTHON="/usr/bin/env python3"
SCRIPT=$( basename $0 )

NEWVER=$( $PYTHON setup.py --version )

OLDVERS=$( git tag | grep -E '^[0-9]*\.[0-9]*\.[0-9]*.*' | sort -V )

# check if current version is new
OLDVER=$( echo -e "$OLDVERS" | sort -V | tail -1 )
if [[ $OLDVER == $NEWVER ]];
then
    echo "$SCRIPT: version number unchanged"
    exit 0
fi

# check current version has increased
MAXVER=$( echo -e "$OLDVERS
$NEWVER" | sort -V | tail -1 )
if [[ $MAXVER == $NEWVER ]];
then
    echo "$SCRIPT: auto tagging commit as \"$NEWVER\""
    git tag $NEWVER
else
    echo "$SCRIPT: Warning: new Version number $NEWVER is not greater." >&2
fi

