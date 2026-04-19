#!/bin/bash -x
set -euo pipefail

# ensure we are in the sources dir
TLDIR=$( dirname $( readlink -f $0 ) )
cd $TLDIR/austaltools

# ensure vendor dir exists
mkdir -p _vendor
cd _vendor

# get latest release tag and commit hash
LATEST=$(basename $(curl -Ls -o /dev/null -w %{url_effective} \
  https://github.com/ecmwf/ecmwf-datastores-client/releases/latest))
COMMIT=$( git ls-remote https://github.com/ecmwf/ecmwf-datastores-client \
  refs/tags/${LATEST} | cut -f1 )
DATE=$(date +%Y-%m-%d)

echo "Vendoring ecmwf-datastores-client ${LATEST} ..."

# put existing version aside
if [ -e "ecmwf" ]; then
  rm -rf ecmwf~
  mv ecmwf ecmwf~
fi

# download and extract
wget -q https://github.com/ecmwf/ecmwf-datastores-client/archive/refs/tags/${LATEST}.zip
unzip -q ${LATEST}.zip

# copy only what we need
SRCDIR="ecmwf-datastores-client-${LATEST#v}"
mkdir -p ecmwf
cp -r ${SRCDIR}/ecmwf/datastores ecmwf/
cp ${SRCDIR}/LICENSE ecmwf/datastores/

# create README — note quoted 'EOF' to prevent variable/backtick expansion
cat << 'TEMPLATE' | sed \
  -e "s/__LATEST__/${LATEST#v}/g" \
  -e "s/__TAG__/${LATEST}/g" \
  -e "s/__COMMIT__/${COMMIT}/g" \
  -e "s/__DATE__/${DATE}/g" \
  > README.md
# _vendor/ecmwf_datastores

## Vendored dependency

This directory contains a vendored copy of the `ecmwf-datastores-client` package,
included here because it is not yet available as a Debian/Ubuntu system package
(`python3-ecmwf-datastores-client`).

## Source

| Field              | Value                                                      |
|--------------------|------------------------------------------------------------|
| Upstream name      | ecmwf-datastores-client                                    |
| PyPI               | https://pypi.org/project/ecmwf-datastores-client/          |
| Repository         | https://github.com/ecmwf/ecmwf-datastores-client           |
| Vendored version   | __LATEST__                                                      |
| Upstream tag       | __TAG__                                                     |
| Commit hash        | __COMMIT__                   |
| Date vendored      | __DATE__                                                 |
| Vendored by        | Clemens Drüe, Universität Trier                            |

## What was copied

Only the importable package source was copied — no tests, docs, CI, or build files:

    ecmwf/datastores/   ← from ecmwf-datastores-client/ecmwf/datastores/
    LICENSE             ← required by Apache License 2.0

Note: this package uses a namespace package layout (`ecmwf/` is a PEP 420
implicit namespace package, not a regular package). No `__init__.py` exists
at the `ecmwf/` level upstream, and none has been added here.

## License

Licensed under the Apache License, Version 2.0.
Copyright 2022, European Union.
Full license text: see `LICENSE` in this directory.

## Updating this vendored copy

When a new release is available upstream:

1. Check the release notes at https://github.com/ecmwf/ecmwf-datastores-client/releases
2. Re-run `vendor_ecmwf-datastores.sh` from the project root
3. Check whether `LICENSE` has changed and update if so
4. Verify the `try/import` fallback in `austaltools/__init__.py` still works
5. Check whether the package has landed in Debian/Ubuntu yet — if so, drop
   this vendored copy and declare a proper `Depends: python3-ecmwf-datastores-client`
   in `debian/control` instead

## Debian packaging status

As of __DATE__ this package is not available in Debian or Ubuntu.
Track status at: https://bugs.debian.org/wnpp (search: ecmwf-datastores-client)
TEMPLATE

# clean up
rm -rf ${SRCDIR} ${LATEST}.zip
rm -rf ecmwf~

echo "Done. Vendored ${LATEST} into _vendor/ecmwf/datastores/"