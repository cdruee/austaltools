#!/bin/env python3
# -*- coding: utf-8 -*-
"""
This module implements a new sub-command that compares two weather
timeseries used as input for the German regulatory dispersion model
AUSTAL [AST31]_.

Each of the two timeseries may be given either as a AUSTAL-generated
``zeitreihe.dmna`` / ``timeseries.dmna`` file, or as an AKTERM file
(the classical format used as input to AUSTAL, configured via the
``az`` keyword in ``austal.txt``). File-format detection is done the
same way AUSTAL itself does it (see :func:`austaltools._windutil.load_weather`):
a file name ending in ``.dmna`` is read as a DMNA timeseries, anything
else is read as AKTERM.

The **first** file given on the command line is the *reference*
timeseries, the **second** one is the *comparison* timeseries. If only
one filename is given, it is taken as the *comparison* timeseries, and
the reference timeseries is determined the same way AUSTAL determines
it from the working directory:

1. a ``zeitreihe.dmna`` or ``timeseries.dmna`` file in the working
   directory, if present (this takes precedence and a notice is
   printed, since it silently overrides the ``az`` keyword),
2. otherwise the AKTERM file configured via ``az`` in ``austal.txt``.

For each of the two (reference and comparison) timeseries, AUSTAL is
then run on a synthetic, flat-terrain domain built just for that
single timeseries (see :func:`run_austal`, modelled after
:func:`austaltools.eap.run_austal`). The per-position result file this
run produces (matching :data:`EXTRACT_PATTERN`) is extracted into a
third, shared temporary directory before the per-run temporary
directory is discarded, since that is what the comparison actually
works on -- the wind library / wind profile itself is not needed here.

The two extracted fields are read with :mod:`readmet.dmna` and
compared by :func:`compute_overlap`: both are thresholded at ``thx``
(a value, or by default the :data:`DEFAULT_PERCENTILE`\ th
percentile of the reference field),
and the ratio of the intersection to the union of the two
above-threshold areas is returned. :func:`compute_overlap` also
reports, for each field, whether its above-threshold area reaches the
edge of the modelled domain -- i.e. whether its isoline is clipped by
the domain boundary rather than closed -- since that can mean the
domain is too small for the given ``thx``.

The extracted result files (see :data:`EXTRACT_FILENAMES`) are
discarded once the overlap has been computed, unless ``--keep-files``
is given, in which case they are copied to the working directory (or
the directory given as its argument) before being discarded. A plot
of the two fields and their overlap area can optionally be produced
via ``-p/--plot`` (and the other plot options added by
:func:`austaltools._tools.add_arguents_common_plot`) -- see
:func:`austaltools._plotting.overlap_plot`.
"""
import argparse
import logging
import os
import re
import shutil
import subprocess
import tempfile

try:
    # unix-only stdlib module; used to give austal's stdout a
    # pseudo-terminal so it keeps emitting "Fertig berechnet: N %"
    # progress -- austal suppresses that output when stdout is a plain
    # pipe (as subprocess.PIPE would be), since it checks isatty().
    import pty
except ImportError:
    pty = None

if os.environ.get('BUILDING_SPHINX', 'false') == 'false':
    import numpy as np
    import readmet

from . import _plotting
from . import _tools
from . import _windutil
from ._metadata import __version__

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------

EXTRACT_FILENAMES = ('xx-j00z.dmna', 'xx-y00a.dmna')
"""tuple(str): The two possible names of the per-position result file
produced by an AUSTAL run for a single timeseries (see
:func:`run_austal`), depending on whether AUSTAL is installed with
German (``xx-j00z.dmna``) or English (``xx-y00a.dmna``) messages. Both
name the same field; exactly one of them is expected to be present in
a given run.
"""

EXTRACT_PATTERN = re.compile(
    r"^(?:%s)$" % '|'.join(re.escape(x) for x in EXTRACT_FILENAMES))
"""re.Pattern: Matches either of :data:`EXTRACT_FILENAMES`. Files
matching this pattern are extracted from each per-timeseries AUSTAL
run (see :func:`run_austal`) before its temporary directory is
discarded. This is what the comparison actually works on -- the wind
library itself is not needed.
"""

AUSTAL_TEMPLATE = """\
xa 0
ya 0
z0 0.1

xq 0
yq 0
xx {throw}
hq {height}

dd {delta}
nx {nodes}
ny {nodes}
x0 {x0}
y0 {y0}

qs -4
"""
"""str: Fixed ``austal.txt`` template used by :func:`run_austal` for the
synthetic, flat-terrain, single-timeseries AUSTAL run. Placeholders are
filled in from the corresponding parameters of :func:`run_austal`.
"""

DEFAULT_NODES = 141
"""int: Default number of grid nodes in x and y direction (``nx``/``ny``)
for :func:`run_austal`."""

DEFAULT_DELTA = 25
"""float: Default grid spacing in m (``dd``) for :func:`run_austal`."""

DEFAULT_THROW = 0.278
"""float: Default source emission of an unknown substance (``xx``)
in g/s (equals 1 kg/h)  for :func:`run_austal`."""

DEFAULT_HEIGHT = 20
"""float: Default source height in m (``hq``) for :func:`run_austal`."""

DEFAULT_PERCENTILE = 80
"""float: Default percentile of the reference field used as the
overlap threshold ``thx`` in :func:`compute_overlap`, when no explicit
threshold is given."""


# -------------------------------------------------------------------------

def _resolve_files(files: list):
    """
    Split the ``files`` positional argument (1 or 2 filenames) into a
    reference and a comparison filename.

    :param files: list of one or two filenames, as given on the
        command line (first = reference, second = comparison; if only
        one is given, it is the comparison and the reference is
        ``None``, meaning "determine from the working directory /
        austal.txt").
    :type files: list[str]
    :return: tuple ``(reference_file, comparison_file)``, where
        ``reference_file`` may be ``None``.
    :rtype: tuple(str or None, str)
    :raises ValueError: if not exactly one or two filenames are given.
    """
    if len(files) == 1:
        reference_file = None
        comparison_file = files[0]
    elif len(files) == 2:
        reference_file, comparison_file = files
    else:
        raise ValueError(
            'compare-weather takes one or two timeseries filenames '
            '(reference and comparison), got %d' % len(files)
        )
    return reference_file, comparison_file


# -------------------------------------------------------------------------

def _resolve_reference_file(working_dir: str, conf: dict,
                            reference_file):
    """
    Resolve the path of the reference weather-timeseries file.

    If ``reference_file`` is given explicitly, it is returned as-is.
    Otherwise, the reference is determined from the working directory
    / ``austal.txt``, following the same precedence AUSTAL itself
    uses: a ``zeitreihe.dmna`` / ``timeseries.dmna`` file, if present,
    supersedes the AKTERM file configured via ``az``. Since this
    override happens silently when AUSTAL (and
    :func:`austaltools._windutil.load_weather`) reads the timeseries,
    a notice is logged here whenever it applies.

    :param working_dir: AUSTAL working directory (where ``austal.txt``
        resides).
    :type working_dir: str
    :param conf: parsed ``austal.txt`` configuration, as returned by
        :func:`austaltools._tools.get_austxt`.
    :type conf: dict
    :param reference_file: explicit reference filename, or ``None`` to
        determine it from ``working_dir`` / ``conf``.
    :type reference_file: str or None
    :return: path to the reference timeseries file.
    :rtype: str
    :raises ValueError: if no reference file is given and none can be
        determined from ``working_dir`` / ``conf``.
    """
    if reference_file is not None:
        return reference_file

    # no reference file given explicitly: determine it the same way
    # AUSTAL does, but tell the user when the dmna file silently wins
    # over the akterm file configured in austal.txt
    working_dir_files = os.listdir(working_dir)
    for x in ['zeitreihe.dmna', 'timeseries.dmna']:
        if x in working_dir_files:
            if 'az' in conf:
                logger.warning(
                    "notice: '%s' found in the working directory -- "
                    "it supersedes the akterm timeseries ('%s') "
                    "configured as reference via 'az' in austal.txt" %
                    (x, conf['az'][0])
                )
            return os.path.join(working_dir, x)

    if 'az' not in conf:
        raise ValueError(
            'no reference timeseries given, and no zeitreihe/'
            'timeseries.dmna or az timeseries configured in austal.txt'
        )
    return os.path.join(working_dir, conf['az'][0])


# -------------------------------------------------------------------------

def _find_austal():
    """
    Locate the ``austal`` executable, the same way
    :func:`austaltools.eap.run_austal` does: first on ``PATH``, then
    in a few common install locations.

    :return: path to the ``austal`` executable.
    :rtype: str
    :raises OSError: if no ``austal`` executable can be found.
    """
    austal = shutil.which('austal')
    if austal is None:
        for x in ['~/bin', '.local/bin', '~/ast', '~/a2k']:
            k = os.path.join(os.path.expanduser(x), 'austal')
            if os.path.exists(k):
                austal = k
                break
        else:
            raise OSError('austal executable not found')
    return austal


# -------------------------------------------------------------------------

def _extract_results(tmpdir: str, extract_to: str, suffix: str):
    """
    Copy every file in ``tmpdir`` (searched recursively) whose name
    matches :data:`EXTRACT_PATTERN` into ``extract_to``, renaming it by
    inserting ``_<suffix>`` before the file extension.

    The rename is needed because the reference and comparison AUSTAL
    runs produce a file of the very same name (whichever of
    :data:`EXTRACT_FILENAMES` applies); without it, extracting both
    into the same directory would have the second overwrite the first.

    :param tmpdir: directory to search (typically a per-run AUSTAL
        temporary working directory, about to be discarded).
    :type tmpdir: str
    :param extract_to: destination directory; created if it does not
        exist yet.
    :type extract_to: str
    :param suffix: suffix identifying this run (e.g. ``'ref'`` or
        ``'cmp'``), inserted before the extension, e.g.
        ``xx-j00z.dmna`` -> ``xx-j00z_ref.dmna``.
    :type suffix: str
    :return: destination paths of the files that were extracted.
    :rtype: list[str]
    """
    os.makedirs(extract_to, exist_ok=True)
    extracted = []
    for root, _dirs, filenames in os.walk(tmpdir):
        for fname in filenames:
            if EXTRACT_PATTERN.match(fname):
                base, ext = os.path.splitext(fname)
                dst = os.path.join(extract_to, '%s_%s%s' %
                                   (base, suffix, ext))
                shutil.copy(os.path.join(root, fname), dst)
                extracted.append(dst)
    if extracted:
        logger.debug('extracted %d file(s) from %s to %s' %
                    (len(extracted), tmpdir, extract_to))
    else:
        logger.warning(
            'no files matching %s found in %s' %
            (EXTRACT_PATTERN.pattern, tmpdir)
        )
    return extracted


# -------------------------------------------------------------------------

def run_austal(weather_file: str,
              nodes: int = DEFAULT_NODES,
              delta: float = DEFAULT_DELTA,
              throw: float = DEFAULT_THROW,
              height: float = DEFAULT_HEIGHT,
              tmproot: str = None,
              extract_to: str = None,
              extract_suffix: str = None):
    """
    Run AUSTAL on a synthetic, flat-terrain domain built just for
    ``weather_file``.

    Modelled after :func:`austaltools.eap.run_austal`, but instead of
    adapting an *existing* ``austal.txt`` / terrain to flat terrain,
    this creates a self-contained AUSTAL run from scratch for a single
    timeseries file:

    A temporary working directory is created; ``weather_file`` is
    copied into it (as ``zeitreihe.dmna``, if given in DMNA format --
    AUSTAL then picks it up automatically, see
    :func:`austaltools._windutil.load_weather` -- or under its own
    name plus an ``az`` entry, if given in AKTERM format); an
    ``austal.txt`` is written from the following fixed template, with
    ``nodes``, ``delta``, ``throw`` and ``height`` filled in::

        xa 0
        ya 0
        z0 0.1

        xq 0
        yq 0
        xx <throw>
        hq <height>

        dd <delta>
        nx <nodes>
        ny <nodes>
        x0 <-delta * nodes // 2>
        y0 <-delta * nodes // 2>

        qs -4

    and ``austal .`` is run in that directory -- a full run, not just
    the wind-library-only ``-l`` mode, since the result file this
    looks for (see :data:`EXTRACT_FILENAMES`) is only produced by a
    complete run. The wind library itself is not needed here; instead,
    if ``extract_to`` is given, every output file matching
    :data:`EXTRACT_PATTERN` is copied there (renamed with
    ``extract_suffix``, see :func:`_extract_results`) before the
    per-run temporary directory is discarded.

    AUSTAL only prints its ``Fertig berechnet: N %`` progress lines
    when its stdout is a terminal (it checks ``isatty()``); attached to
    a plain ``subprocess.PIPE`` it stays silent on that front (though
    it still prints everything else, e.g. ``AUSTAL beendet.``). To get
    live progress, this function instead gives it a pseudo-terminal
    (:mod:`pty`, unix-only) to write to, and falls back to a plain pipe
    -- silently forgoing progress updates, everything else still works
    -- where :mod:`pty` is unavailable (e.g. on Windows).

    :param weather_file: path to the weather timeseries file, in
        zeitreihe/timeseries.dmna or akterm format (auto-detected from
        the file name).
    :type weather_file: str
    :param nodes: number of grid nodes in x and y direction (``nx``/
        ``ny``). Defaults to :data:`DEFAULT_NODES`.
    :type nodes: int, optional
    :param delta: grid spacing in m (``dd``). Defaults to
        :data:`DEFAULT_DELTA`.
    :type delta: float, optional
    :param throw: source emission of an unknown substance in g/s
        (``xx``). Defaults to :data:`DEFAULT_THROW`.
    :type throw: float, optional
    :param height: source height in m (``hq``). Defaults to
        :data:`DEFAULT_HEIGHT`.
    :type height: float, optional
    :param tmproot: directory in which to create the (per-run)
        temporary working directory. Defaults to the system temporary
        directory.
    :type tmproot: str or path-like, optional
    :param extract_to: directory to copy the files matching
        :data:`EXTRACT_PATTERN` into, before the per-run temporary
        directory is discarded. If ``None``, nothing is extracted.
    :type extract_to: str or path-like, optional
    :param extract_suffix: suffix identifying this run, inserted into
        the extracted file names to keep the reference and comparison
        run's (identically named) result files apart -- see
        :func:`_extract_results`. Required if ``extract_to`` is given.
    :type extract_suffix: str, optional
    :return: destination paths of the extracted files (empty if
        ``extract_to`` was ``None``).
    :rtype: list[str]
    :raises FileNotFoundError: if ``weather_file`` does not exist.
    :raises OSError: if no ``austal`` executable can be found.
    :raises ValueError: if AUSTAL does not finish successfully.

    .. seealso:: :func:`austaltools.eap.run_austal`
    """
    if not os.path.exists(weather_file):
        raise FileNotFoundError(
            'weather timeseries file not found: %s' % weather_file)

    tmpdir = tempfile.mkdtemp(prefix="cmpwx_", dir=tmproot)
    logger.debug('created temporary directory: %s' % tmpdir)

    #
    # copy the weather timeseries into the temp dir the way AUSTAL
    # expects it, and note the "az" line to add (akterm files only)
    #
    if weather_file.endswith('.dmna'):
        # AUSTAL auto-detects a file literally named zeitreihe.dmna
        # (or timeseries.dmna) in the working directory -- no "az"
        # entry needed in austal.txt
        shutil.copy(weather_file, os.path.join(tmpdir, 'zeitreihe.dmna'))
        az_line = ''
    else:
        az_name = os.path.basename(weather_file)
        shutil.copy(weather_file, os.path.join(tmpdir, az_name))
        az_line = 'az %s\n' % az_name

    #
    # write austal.txt from the fixed template
    #
    x0 = -delta * (nodes // 2)
    y0 = -delta * (nodes // 2)
    austal_txt = os.path.join(tmpdir, 'austal.txt')
    with open(austal_txt, 'w') as f:
        f.write(az_line)
        f.write(AUSTAL_TEMPLATE.format(
            throw=throw, height=height, delta=delta,
            nodes=nodes, x0=x0, y0=y0
        ))
    logger.debug('wrote %s' % austal_txt)

    #
    # start austal model
    #
    # austal only emits its "Fertig berechnet: N %" progress lines when
    # its stdout is a terminal (it checks isatty()); a plain
    # subprocess.PIPE looks like neither a terminal nor a regular file
    # to it, so it stays silent on that front (though it still prints
    # everything else, e.g. "AUSTAL beendet."). To get the progress
    # lines too, stdout is connected to a pseudo-terminal (pty) instead,
    # when the pty module is available (unix-only; falls back to a
    # plain pipe, e.g. on Windows -- austal still runs fine there, just
    # without live progress).
    #
    austal = _find_austal()
    use_pty = pty is not None
    if use_pty:
        master_fd, slave_fd = pty.openpty()
        p = subprocess.Popen([austal, "."], cwd=tmpdir,
                             stdout=slave_fd, stderr=subprocess.STDOUT,
                             close_fds=True)
        os.close(slave_fd)  # only austal needs the slave end open
    else:
        master_fd = None
        p = subprocess.Popen([austal, "."], cwd=tmpdir,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
    logger.info('started austal in: %s (progress via %s)' %
               (tmpdir, 'pty' if use_pty else 'pipe'))

    pbar = _tools.progress(total=100.0)
    percent = 0.0

    # regex to find the float value after "Fertig berechnet:"
    percent_regex = re.compile(r"Fertig berechnet:\s+([0-9.]+)\s*%")

    # buffer for the characters of the current (not yet terminated) line,
    # and the complete output collected so far -- read once, since the
    # stream can't be re-read/rewound once drained (needed below to check
    # for "AUSTAL beendet." even if austal exits with an error)
    buffer = b""
    output_lines = []

    while True:
        # read a single byte; blocks until a byte is available. EOF is
        # signalled as b'' on a plain pipe, but as an OSError (EIO) on
        # a pty once the far (slave) end has been closed by austal
        try:
            char = os.read(master_fd, 1) if use_pty else p.stdout.read(1)
        except OSError:
            break
        if not char:
            break

        # append every byte to the buffer
        buffer += char

        # once we find a carriage return (^M / \r) or newline (\n)
        if char in (b'\r', b'\n'):
            line = buffer.decode('utf-8', errors='ignore')
            buffer = b""  # clear the buffer again
            output_lines.append(line)
            match = percent_regex.search(line)
            if match:
                newpercent = float(match.group(1))
                if newpercent > percent:
                    if hasattr(pbar, 'update'):
                        pbar.update(newpercent - percent)
                    percent = newpercent
    if buffer:
        # capture a final, unterminated partial line, if any
        output_lines.append(buffer.decode('utf-8', errors='ignore'))
    if use_pty:
        os.close(master_fd)
    del pbar

    # stdout is now fully drained; make sure the process has actually
    # exited too, so that p.returncode is available below
    p.wait()

    if p.returncode == 0:
        austal_ok = True
    else:
        austal_ok = False
        for line in output_lines:
            if "AUSTAL beendet." in line:
                austal_ok = True
                break
    if not austal_ok:
        # leave tmpdir in place so the failure can be inspected
        raise ValueError('austal finished with an error, see: %s' % tmpdir)

    #
    # extract the files we actually need before discarding this run's
    # temporary directory -- we don't need the wind library/profile
    #
    extracted = []
    if extract_to is not None:
        if not extract_suffix:
            raise ValueError('extract_suffix is required if extract_to '
                             'is given')
        extracted = _extract_results(tmpdir, extract_to, extract_suffix)

    shutil.rmtree(tmpdir)
    logger.debug('removed temporary directory: %s' % tmpdir)

    return extracted


# -------------------------------------------------------------------------

def _find_extracted_file(extract_dir: str, suffix: str):
    """
    Find the single result file extracted (with :func:`run_austal` /
    :func:`_extract_results`) for one run, identified by ``suffix``.

    Exactly one of the two possible names in :data:`EXTRACT_FILENAMES`
    is expected to exist for a given ``suffix`` (which one, depends on
    whether AUSTAL is installed with German or English messages).

    :param extract_dir: shared extraction directory (see :func:`main`).
    :type extract_dir: str
    :param suffix: suffix identifying the run (e.g. ``'ref'`` or
        ``'cmp'``), as passed to :func:`run_austal` as
        ``extract_suffix``.
    :type suffix: str
    :return: path of the single matching file.
    :rtype: str
    :raises FileNotFoundError: if neither candidate file exists.
    :raises ValueError: if both candidate files exist (unexpected).
    """
    candidates = []
    for base in EXTRACT_FILENAMES:
        name, ext = os.path.splitext(base)
        candidates.append(os.path.join(extract_dir, '%s_%s%s' %
                                       (name, suffix, ext)))
    found = [c for c in candidates if os.path.exists(c)]
    if not found:
        raise FileNotFoundError(
            'none of the expected result files (%s) were found in %s' %
            (', '.join(os.path.basename(c) for c in candidates),
             extract_dir)
        )
    if len(found) > 1:
        raise ValueError(
            'both the german and english variant of the result file '
            'were found in %s for suffix %r: %s -- expected only one '
            'to be produced by a given austal installation' %
            (extract_dir, suffix, found)
        )
    return found[0]


# -------------------------------------------------------------------------

def _read_grid_file(path: str):
    """
    Read a single-variable 2D grid DMNA file with :mod:`readmet.dmna`.

    AUSTAL's per-position result files (see :data:`EXTRACT_FILENAMES`)
    are technically 3-dimensional (``dims == 3`` in the DMNA header,
    since the format supports multiple vertical levels), but only
    contain a single level -- :meth:`readmet.dmna.DataFile.axes`
    reports a length-1 ``z`` axis and the data array has a trailing
    dimension of size 1 accordingly. That trailing dimension is
    squeezed away here, so callers can rely on ``values`` being
    genuinely 2D and matching ``(len(x), len(y))``.

    :param path: path to the dmna file.
    :type path: str
    :return: tuple ``(values, x, y)``: the 2D data array, and the
        grid's x and y coordinate axes (1D each, in model coordinates).
    :rtype: tuple(numpy.ndarray, numpy.ndarray, numpy.ndarray)
    :raises ValueError: if the file does not contain exactly one
        variable, no x/y axes, or more than one vertical level.
    """
    df = readmet.dmna.DataFile(file=path)
    if not df.variables or len(df.variables) != 1:
        raise ValueError(
            'expected exactly one variable in %s, found: %s' %
            (path, df.variables)
        )
    values = np.asarray(df.data[df.variables[0]])
    axes = df.axes()
    if 'x' not in axes or 'y' not in axes:
        raise ValueError('%s does not contain x/y grid axes' % path)
    x = np.asarray(axes['x'])
    y = np.asarray(axes['y'])

    if values.ndim == 3:
        # single-level 3D field (dims == 3, one z level) -- squeeze
        # the trailing level dimension away
        if values.shape[2] != 1:
            raise ValueError(
                '%s contains %d vertical levels, expected exactly 1' %
                (path, values.shape[2])
            )
        values = values[:, :, 0]
    elif values.ndim != 2:
        raise ValueError(
            '%s: expected a 2D (or single-level 3D) grid, got shape %s' %
            (path, values.shape)
        )

    if values.shape != (len(x), len(y)):
        raise ValueError(
            '%s: data shape %s does not match x/y axes lengths (%d, %d)' %
            (path, values.shape, len(x), len(y))
        )
    return values, x, y


# -------------------------------------------------------------------------

def _touches_border(mask) -> bool:
    """
    Check whether any ``True`` cell of a 2D boolean ``mask`` lies on
    its outer border (first/last row or column).

    Used by :func:`compute_overlap` to detect that an above-threshold
    area extends all the way to the edge of the modelled domain: in
    that case its isoline (the boundary of the above-threshold area)
    is clipped by the domain boundary rather than being a closed
    contour, and the corresponding area (and hence the overlap ratio)
    may be an underestimate of the true above-threshold area outside
    the modelled domain.

    :param mask: 2D boolean array (e.g. ``values > thx``).
    :type mask: numpy.ndarray
    :return: ``True`` if the domain border is touched.
    :rtype: bool
    """
    if mask.ndim != 2 or mask.size == 0:
        return False
    return bool(
        mask[0, :].any() or mask[-1, :].any() or
        mask[:, 0].any() or mask[:, -1].any()
    )


# -------------------------------------------------------------------------

def compute_overlap(reference_file: str, comparison_file: str,
                    thx: float = None) -> dict:
    """
    Compute the overlap (intersection over union) of the areas where
    the reference and comparison field exceed a threshold ``thx``.

    Both files are read with :func:`_read_grid_file`. For safety, the
    two grids' x/y coordinates are checked to be identical before
    comparing the fields cell by cell.

    Binary fields are formed as ``inside_ref = ref > thx`` and
    ``inside_cmp = cmp > thx``. The *union* area is the count of cells
    where ``inside_ref OR inside_cmp`` is true, the *intersect* area
    the count of cells where ``inside_ref AND inside_cmp`` is true.
    The overlap ratio is ``intersect / union``. Each of the two binary
    fields is also checked, via :func:`_touches_border`, for whether it
    reaches the edge of the modelled domain -- if it does, its isoline
    is clipped there rather than closed, which is worth flagging since
    it means the domain may be too small for that threshold.

    :param reference_file: path to the reference grid dmna file.
    :type reference_file: str
    :param comparison_file: path to the comparison grid dmna file.
    :type comparison_file: str
    :param thx: threshold value. If ``None`` (default),
        :data:`DEFAULT_PERCENTILE` of all values in the reference
        field is used.
    :type thx: float, optional
    :return: dict with keys:

        - ``overlap``: intersect area / union area, in ``[0, 1]``;
          ``nan`` if the union area is empty (e.g. ``thx`` too high).
        - ``thx``: the threshold value actually used (``thx`` as
          given, or the computed :data:`DEFAULT_PERCENTILE` of the
          reference field).
        - ``x``, ``y``: the (shared) x/y coordinate axes of both
          fields.
        - ``reference``, ``comparison``: the two 2D data arrays, as
          read from ``reference_file`` / ``comparison_file``.
        - ``reference_touches_border``, ``comparison_touches_border``:
          ``True`` if the reference's / comparison's above-threshold
          area (``reference``/``comparison`` ``> thx``) reaches the
          edge of the modelled domain -- see :func:`_touches_border`.

      This is enough to plot the two fields and their overlap without
      re-reading the files -- see
      :func:`austaltools._plotting.overlap_plot`.
    :rtype: dict
    :raises ValueError: if the reference and comparison grids do not
        share the same shape / coordinates.
    """
    values_ref, x_ref, y_ref = _read_grid_file(reference_file)
    values_cmp, x_cmp, y_cmp = _read_grid_file(comparison_file)

    #
    # safety check: both fields must be on the same grid
    #
    if values_ref.shape != values_cmp.shape:
        raise ValueError(
            'reference and comparison grids have different shapes: '
            '%s vs %s' % (values_ref.shape, values_cmp.shape)
        )
    if not (np.array_equal(x_ref, x_cmp) and np.array_equal(y_ref, y_cmp)):
        raise ValueError(
            'reference and comparison grids do not share the same '
            'coordinates'
        )

    if thx is None:
        thx = float(np.nanpercentile(values_ref, DEFAULT_PERCENTILE))
        logger.info('no threshold given, using the %gth percentile of '
                   'the reference field: %.6g' % (DEFAULT_PERCENTILE, thx))

    inside_ref = values_ref > thx
    inside_cmp = values_cmp > thx

    union_area = int(np.count_nonzero(inside_ref | inside_cmp))
    intersect_area = int(np.count_nonzero(inside_ref & inside_cmp))
    logger.debug('union area: %d cells, intersect area: %d cells' %
                (union_area, intersect_area))

    if union_area == 0:
        logger.warning(
            'union area is empty (threshold %.6g too high?), '
            'returning nan' % thx
        )
        overlap = float('nan')
    else:
        overlap = float(intersect_area / union_area)

    reference_touches_border = _touches_border(inside_ref)
    comparison_touches_border = _touches_border(inside_cmp)
    touched = [name for name, flag in (
        ('reference', reference_touches_border),
        ('comparison', comparison_touches_border)) if flag]
    if touched:
        logger.warning(
            '%s above-threshold area reaches the domain border '
            '(isoline clipped there, not closed) at thx=%.6g -- '
            'results may depend on domain size; consider a larger '
            '--nodes/--delta' % (' and '.join(touched), thx)
        )

    return {
        'overlap': overlap,
        'thx': float(thx),
        'x': x_ref,
        'y': y_ref,
        'reference': values_ref,
        'comparison': values_cmp,
        'reference_touches_border': reference_touches_border,
        'comparison_touches_border': comparison_touches_border,
    }


# -------------------------------------------------------------------------

def main(args):
    """
    Main entry point for the weather-timeseries comparison.

    Resolves the reference and comparison timeseries files (see
    module docstring for the filename / precedence rules), runs AUSTAL
    on a synthetic flat-terrain domain for each of them (see
    :func:`run_austal`), collecting the per-position result file
    (matching :data:`EXTRACT_PATTERN`) from both runs into a third,
    shared temporary directory, and computes the overlap between the
    two fields (see :func:`compute_overlap`).

    :param args: Command line arguments dictionary with keys:

        - ``working_dir``: path to the AUSTAL working directory.
        - ``files``: list of one or two timeseries filenames.
        - ``nodes``, ``delta``, ``throw``, ``height``: parameters
          passed through to :func:`run_austal`.
        - ``thx``: threshold passed through to :func:`compute_overlap`.
        - ``keep_files``: if not ``None``, keep the extracted result
          files instead of discarding them -- ``'__default__'`` means
          the working directory, anything else is used as the
          destination directory.
        - ``plot`` and the other keys added by
          :func:`austaltools._tools.add_arguents_common_plot`: control
          whether/where a plot of the two fields is produced, see
          :func:`austaltools._plotting.overlap_plot`.

    :type args: dict

    .. seealso:: :func:`add_options`
    """
    logger.debug(format(args))

    working_dir = args['working_dir']
    reference_file, comparison_file = _resolve_files(args['files'])

    austxt = _tools.find_austxt(working_dir, fail=False)
    if austxt:
        conf = _tools.get_austxt(austxt)
    else:
        conf = {}

    reference_file = _resolve_reference_file(working_dir, conf,
                                             reference_file)

    run_kwargs = dict(nodes=args['nodes'], delta=args['delta'],
                      throw=args['throw'], height=args['height'])

    #
    # third, shared temporary directory that collects the extracted
    # result files from both (per-timeseries) austal runs below,
    # distinguished by a "_ref"/"_cmp" suffix since both runs produce
    # a file of the same name.
    #
    extract_dir = tempfile.mkdtemp(prefix="cmpwx_extract_")
    logger.debug('created extraction directory: %s' % extract_dir)

    #
    # run austal for each of the two timeseries; we don't need the
    # wind library/profile here, only the extracted result file
    #
    logger.info('running austal for reference timeseries: %s' %
               reference_file)
    run_austal(reference_file, extract_to=extract_dir,
              extract_suffix='ref', **run_kwargs)

    logger.info('running austal for comparison timeseries: %s' %
               comparison_file)
    run_austal(comparison_file, extract_to=extract_dir,
              extract_suffix='cmp', **run_kwargs)

    reference_grid_file = _find_extracted_file(extract_dir, 'ref')
    comparison_grid_file = _find_extracted_file(extract_dir, 'cmp')

    #
    # keep the extracted result files, if requested, before the
    # extraction directory (and its contents) is discarded below
    #
    keep_files = args.get('keep_files')
    if keep_files is not None:
        if keep_files == '__default__':
            keep_dir = working_dir
        elif os.path.sep in keep_files:
            # a path was given (absolute, or containing subdirs):
            # use as-is, same convention as -p/--plot (see
            # _plotting.finalize_plot)
            keep_dir = keep_files
        else:
            # a bare name was given: relative to the working directory
            keep_dir = os.path.join(working_dir, keep_files)
        os.makedirs(keep_dir, exist_ok=True)
        for src in (reference_grid_file, comparison_grid_file):
            dst = os.path.join(keep_dir, os.path.basename(src))
            shutil.copy(src, dst)
            logger.info('kept output file: %s' % dst)

    result = compute_overlap(reference_grid_file, comparison_grid_file,
                            thx=args.get('thx'))
    overlap = result['overlap']
    logger.info('overlap (intersection / union area): %.4f' % overlap)
    print('overlap (intersection / union area): %.4f' % overlap)

    # compute_overlap() already logs a warning if this is the case;
    # also surface it on stdout, next to the overlap ratio itself
    touched = [name for name, flag in (
        ('reference', result['reference_touches_border']),
        ('comparison', result['comparison_touches_border'])) if flag]
    if touched:
        print('note: %s isoline reaches the domain border (clipped, '
             'not closed)' % ' and '.join(touched))

    #
    # optionally plot the two fields and their overlap area
    #
    if args.get('plot') is not None:
        args['plot'] = _plotting.consolidate_plotname(
            args['plot'], 'compare-weather.png')
        _plotting.overlap_plot(
            args,
            reference={'x': result['x'], 'y': result['y'],
                      'z': result['reference']},
            comparison={'x': result['x'], 'y': result['y'],
                       'z': result['comparison']},
            thx=result['thx'],
            unit='a.u.',  # arbitrary units: throw/emission is arbitrary
        )

    shutil.rmtree(extract_dir)
    logger.debug('removed extraction directory: %s' % extract_dir)

    return overlap


# -------------------------------------------------------------------------

def add_options(subparsers):
    """
    Add the ``compare-weather`` sub-command and its arguments to
    ``subparsers``.

    :param subparsers: subparsers object as created by
        ``argparse.ArgumentParser.add_subparsers()``.
    :return: the newly created sub-parser.
    :rtype: argparse.ArgumentParser
    """
    pars_cmp = subparsers.add_parser(
        name='compare-weather',
        help='compare two weather timeseries',
        formatter_class=argparse.RawTextHelpFormatter
    )
    pars_cmp.add_argument('files',
                          metavar='FILE',
                          nargs='+',
                          help='filename(s) of the weather timeseries to\n'
                               'compare. Each file may be given in\n'
                               'zeitreihe/timeseries.dmna format or in\n'
                               'akterm format; the format is detected\n'
                               'automatically from the file name.\n'
                               '\n'
                               'If two filenames are given, the first is\n'
                               'the reference timeseries, the second is\n'
                               'the comparison timeseries.\n'
                               '\n'
                               'If only one filename is given, it is used\n'
                               'as the comparison timeseries, and the\n'
                               'reference timeseries is taken from the\n'
                               'current AUSTAL configuration: a\n'
                               'zeitreihe.dmna or timeseries.dmna file in\n'
                               'the working directory, if present\n'
                               '(superseding, with a notice, the akterm\n'
                               'file configured as "az" in austal.txt),\n'
                               'otherwise the akterm file configured as\n'
                               '"az" in austal.txt.')
    pars_adv_cmp = pars_cmp.add_argument_group(
        'options for the synthetic AUSTAL run')
    pars_adv_cmp.add_argument('--nodes',
                              type=int,
                              default=DEFAULT_NODES,
                              help='number of grid nodes in x and y '
                                   'direction. Defaults to %i' %
                                   DEFAULT_NODES)
    pars_adv_cmp.add_argument('--delta',
                              type=float,
                              default=DEFAULT_DELTA,
                              help='grid spacing in m. '
                                   'Defaults to %s' % DEFAULT_DELTA)
    pars_adv_cmp.add_argument('--throw',
                              type=float,
                              default=DEFAULT_THROW,
                              help='source emission of an unknown '
                                   'substance in g/s ("xx"). '
                                   'Defaults to %s (equals 1 kg/h)' %
                                   DEFAULT_THROW)
    pars_adv_cmp.add_argument('--height',
                              type=float,
                              default=DEFAULT_HEIGHT,
                              help='source height in m ("hq"). '
                                   'Defaults to %s' % DEFAULT_HEIGHT)
    pars_cmp.add_argument('--thx',
                          type=float,
                          default=None,
                          help='threshold value used to determine the '
                               'overlap area between the reference and '
                               'comparison field. Defaults to the %gth '
                               'percentile of the reference field.' %
                               DEFAULT_PERCENTILE)
    pars_cmp.add_argument('--keep-files',
                          dest='keep_files',
                          metavar='DIR',
                          nargs='?',
                          const='__default__',
                          default=None,
                          help='keep the AUSTAL result files extracted\n'
                               'for the reference and comparison run\n'
                               '(e.g. "xx-j00z_ref.dmna",\n'
                               '"xx-j00z_cmp.dmna"), instead of\n'
                               'discarding them after use. If DIR is\n'
                               'given, the files are copied there (a\n'
                               'bare name is taken relative to the\n'
                               'working directory); if missing, they\n'
                               'are copied to the working directory\n'
                               'itself.')

    pars_cmp = _tools.add_arguents_common_plot(pars_cmp)
    # note: -c/--colormap (added above) has no effect on this
    # sub-command's plot -- overlap_plot() uses a fixed pair of hues
    # (see austaltools._plotting.OVERLAP_REFERENCE_COLOR /
    # OVERLAP_COMPARISON_COLOR), since a single colormap cannot
    # represent the bivariate reference/comparison overlap.

    return pars_cmp
