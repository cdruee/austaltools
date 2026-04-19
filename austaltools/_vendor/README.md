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
| Vendored version   | 0.5.1                                                      |
| Upstream tag       | v0.5.1                                                     |
| Commit hash        | 8c5e0f2d4e08c9166bbef1698ec804ba64f0cc3f                   |
| Date vendored      | 2026-04-18                                                 |
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

As of 2026-04-18 this package is not available in Debian or Ubuntu.
Track status at: https://bugs.debian.org/wnpp (search: ecmwf-datastores-client)
