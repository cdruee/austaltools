#!/bin/bash

BUILD_VERSION=$1

FULLNAME=${BUILD_VERSION%.tar.gz}
VERSION=${FULLNAME##*-}
NAME=${FULLNAME%%-*}
CODENAME=$(cat /etc/os-release | grep VERSION_CODENAME | sed s/.*=// | tr -d '"')

function version () {
  grep $1 ${NAME}/_version.py | sed 's/.*'\''\(.*\)'\''.*/\1/'
}

if [ -e deb_dist/$CODENAME ]; then
  rm -r deb_dist/$CODENAME
else
  mkdir -p deb_dist/$CODENAME
fi
pushd deb_dist/$CODENAME



cp ../../dist/${FULLNAME}.tar.gz .
tar -xzvf ${FULLNAME}.tar.gz
pushd ${FULLNAME}

AUTHOR=`version '__author__'`
EMAIL=`version '__author_email__'`
DESCRIPTION=`version '__description__'`

rm -r debian/

export DEBFULLNAME=$AUTHOR
dh_make --python -p ${NAME}_${VERSION}-1${CODENAME}1 \
  -f ../${FULLNAME}.tar.gz \
  -c custom \
  --copyrightfile ../LICENSE.txt \
  --email $EMAIL \
  --yes

ls -l debian

# "edit" the files

# add description
echo " " >> debian/control
mv debian/control debian/control.old
awk '
BEGIN{tgt=0; dsc=0}
/^[[:space:]]*$/{if (tgt==1) {print "Description: '"$DESCRIPTION"'"}; tgt=0}
/^Package: python.*'$NAME'/{tgt=1}
/^Description: / && tgt==1 {dsc=1; next}
/^ [^[:space:]]/ && dsc==1 {next}
{print $0; dsc=0}
' debian/control.old |tee debian/control

# de-select doc package
echo " " >> debian/control
mv debian/control debian/control.old
awk '
BEGIN{doc=0}
/^Package: python.*'$NAME-doc'/{doc=1}
/^[[:space:]]*$/{doc=0}
(doc==0){print $0}
' debian/control.old |tee debian/control

#touch README.Debian
#touch README.source


# build the packages
RASPBIAN_CODENAMES=("wheezy" "jessie" "stretch" "buster" "bullseye" "bookworm" "trixie" "forky")
if [[ $(echo ${RASPBIAN_CODENAMES[@]} | fgrep -w $CODENAME) ]]; then
  #ARCH_OPTS="--host-arch armhf -d"
  cat << EOF > ~/tmp.sh
#!/bin/bash
sed -i 's/Build-Architecture: .*/Build-Architecture: armhf/' ../*.buildinfo
EOF
  chmod +x ~/tmp.sh
  ARCH_OPTS=--hook-changes=~/tmp.sh
fi

export PYBUILD_DISABLE=test
dpkg-buildpackage -us -uc $ARCH_OPTS -b

popd

# make reprepro happy

for X in $( ls *.changes ); do
  sed -i s/Distribution:\ .\*/Distribution:\ "${CODENAME}"/ $X
done

# clean up

#rm -rv $FULLNAME

popd
ls -l deb_dist/$CODENAME
