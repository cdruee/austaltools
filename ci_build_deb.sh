#!/bin/bash

BUILD_VERSION=$1

FULLNAME=${BUILD_VERSION%.tar.gz}
VERSION=${FULLNAME##*-}
NAME=${FULLNAME%%-*}
CODENAME=$(cat /etc/os-release | grep VERSION_CODENAME | sed s/.*=// | tr -d '"')

# Function to extract metadata from pyproject.toml or _metadata.py
function get_project_info() {
    local FIELD=$1

    # First try to read from pyproject.toml using python
    if command -v python3 >/dev/null 2>&1; then
      python3 -c "
import sys
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        sys.exit(1)

try:
    with open('pyproject.toml', 'rb') as f:
        data = tomllib.load(f)
    if $FIELD in ['author', 'email']:
        authors = data.get('project', {}).get('authors')
        if $FIELD == 'author'
          res = authors[0].get('name')
        else:
          res = authors[0].get('email')
    elif $FIELD == 'description'
        res = data.get('project', {}).get('description')
    else:
        res = 'Unknown'
except:
    res = 'Unknown'

print(res)
        " 2>/dev/null || echo "Unknown"

    else
        echo "Unknown"
    fi
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

# Get metadata - try pyproject.toml first, then fallback methods
AUTHOR=$(get_project_info "author")
EMAIL=$(get_project_info "email")
DESCRIPTION=$(get_project_info "description")


echo "Using metadata: AUTHOR='$AUTHOR', EMAIL='$EMAIL', DESCRIPTION='$DESCRIPTION'"

rm -r debian/ 2>/dev/null || true

export DEBFULLNAME="$AUTHOR"
dh_make --python -p ${NAME}_${VERSION}-1${CODENAME}1 \
  -f ../${FULLNAME}.tar.gz \
  -c custom \
  --copyrightfile ../../LICENSE.txt \
  --email "$EMAIL" \
  --yes

ls -l debian

# Edit the control file - add description
echo " " >> debian/control
mv debian/control debian/control.old
awk '
BEGIN{tgt=0; dsc=0}
/^[[:space:]]*$/{if (tgt==1) {print "Description: '"$DESCRIPTION"'"}; tgt=0}
/^Package: python.*'$NAME'/{tgt=1}
/^Description: / && tgt==1 {dsc=1; next}
/^ [^[:space:]]/ && dsc==1 {next}
{print $0; dsc=0}
' debian/control.old | tee debian/control

# Remove doc package
echo " " >> debian/control
mv debian/control debian/control.old
awk '
BEGIN{doc=0}
/^Package: python.*'$NAME-doc'/{doc=1}
/^[[:space:]]*$/{doc=0}
(doc==0){print $0}
' debian/control.old | tee debian/control

# Add setuptools_scm to build dependencies
echo " " >> debian/control
mv debian/control debian/control.old
awk '
/^Build-Depends:/ {
  # Check if setuptools-scm is already there
  if (index($0, "python3-setuptools-scm") == 0) {
    # Also ensure we have build and other modern dependencies
    if (index($0, "python3-build") == 0) {
      print $0 ", python3-setuptools-scm, python3-build"
    } else {
      print $0 ", python3-setuptools-scm"
    }
  } else {
    print $0
  }
  next
}
{print $0}
' debian/control.old | tee debian/control

# Handle Raspberry Pi architecture if needed
RASPBIAN_CODENAMES=("wheezy" "jessie" "stretch" "buster" "bullseye" "bookworm" "trixie" "forky")
if [[ $(echo "${RASPBIAN_CODENAMES[@]}" | fgrep -w $CODENAME) ]]; then
  #ARCH_OPTS="--host-arch armhf -d"
  cat << EOF > ~/tmp.sh
#!/bin/bash
sed -i 's/Build-Architecture: .*/Build-Architecture: armhf/' ../*.buildinfo
EOF
  chmod +x ~/tmp.sh
  ARCH_OPTS=--hook-changes=~/tmp.sh
fi

# Disable tests during package build (they may need special setup)
export PYBUILD_DISABLE=test

# Build the package
dpkg-buildpackage -us -uc $ARCH_OPTS -b

popd

# Make reprepro happy - set correct distribution
for X in *.changes; do
  sed -i "s/Distribution: .*/Distribution: ${CODENAME}/" $X
done

# Optional: clean up source directory
# rm -rv $FULLNAME

popd
echo "Debian packages built successfully:"
ls -l deb_dist/$CODENAME