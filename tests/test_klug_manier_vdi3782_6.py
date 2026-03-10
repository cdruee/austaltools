#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for austaltools._dispersion.klug_manier_scheme_2017()
against the official VDI 3782 Part 6 test dataset.

Test-dataset station parameters (VDI 3782-6:2017/2023, Annex B)
----------------------------------------------------------------
  Station ID           : 9999   (anonymised)
  Year                 : 2010   (365 days × 24 h = 8 760 rows)
  Geographic longitude : λ = 14.11780 °E
  Geographic latitude  : φ = 52.20830 °N
  Station altitude     : H_S = 98 m amsl
  Measurement height   : h'_a = 10.4 m
  Station roughness    : z'_0 = 0.487 m

Expected class counts (VDI 3782-6, Table B3 — identical in 2017 and 2023)
--------------------------------------------------------------------------
  KM I    :  287 h  ( 3.28 %)
  KM II   : 1232 h  (14.06 %)
  KM III1 : 5247 h  (59.90 %)
  KM III2 : 1253 h  (14.30 %)
  KM IV   :  494 h  ( 5.64 %)
  KM V    :  247 h  ( 2.82 %)
  Undef.  :    0 h  ( 0.00 %)
  Total   : 8760 h  (100.00 %)

Input-file columns (AKtest_CDCfmt_ein.asc, semicolon-separated)
----------------------------------------------------------------
  1  STATIONS_ID               – always 9999
  2  MESS_DATUM                – YYYYMMDDhh  (UTC, start-of-hour label)
  3  GESAMT_BEDECKUNGSGRAD     – total cloud cover [0…8 oktas, -1=missing]
  4  WINDRICHTUNG              – wind direction [°, 10°-steps]  (not used)
  5  WINDGESCHWINDIGKEIT       – wind speed at h'_a, z'_0  [m/s]
  6  WOLKENART_C1              – lowest cloud layer type, WMO code 0500
                                 (0=CI, 1=CC, 2=CS, 3=AC, …, -9=missing)
  7  HOEHE_WOLKENUNTERGRENZE_H1– cloud-base height  [m amsl, -9999=missing]

WMO cloud-type codes 0, 1, 2 correspond to CI, CC, CS (cirrus family) and
trigger the cirrus correction (−3/8 from N) defined in VDI 3782-6, Sec. 4.2.

Output-file columns (AKtest_akzr.asc, space-separated data lines)
------------------------------------------------------------------
  AK <station> <YYYY> <MM> <DD> <hh> <mm> <wdir_sector> <wdir_class>
     <wdir_10deg> <ff_10_scaled> <N_oktas> <AK_numeric> <cirrus_flag>
     <cbh_m_or_-999> <something>
  Column 13 (1-based): AK_numeric stability class (1=I … 6=V)

Verification-file columns (AKtest_KM.asc, space-separated, CET times)
----------------------------------------------------------------------
  1  datetime        – YYYY-MM-DD.HH:MM:SS  CET (01:00–24:00)
  2  sunrise         – HH:MM:SS CET
  3  sunset          – HH:MM:SS CET
  4  v10             – wind speed converted to standard (10 m, z0=0.1 m)
  5  N               – cloud cover in oktas after cirrus correction (-9=missing)
  6  C               – cirrus flag (0/1)
  7  AK              – stability class numeric (1=I … 6=V)

Directory layout
----------------
  <project>/
    austaltools/        ← source package (contains _dispersion.py)
    tests/              ← this file lives here
      test_klug_manier_vdi3782_6.py

Environment variables
---------------------
  DISPERSION_PATH   Directory containing _dispersion.py.
                    Defaults to ../austaltools relative to this file.

  TESTDATA_PATH     Directory containing the three AKtest_*.asc files.
                    Defaults to "." (current working directory).
                    If the files are absent, the script downloads and unpacks
                    https://www.vdi.de/fileadmin/pages/vdi_de/redakteure/
                      ueber_uns/fachgesellschaften/KRdL/dateien/AKtest-Dateien.zip
                    into a temporary directory and uses that instead.

Run:
  python tests/test_klug_manier_vdi3782_6.py -v
  # or from the tests/ directory:
  python test_klug_manier_vdi3782_6.py -v
"""

import os
import sys
import tempfile
import unittest
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Locate _dispersion.py
# Default: ../austaltools relative to this file, i.e. the sibling package
# directory when the test lives in tests/.
# ---------------------------------------------------------------------------
DISPERSION_PATH = os.environ.get(
    "DISPERSION_PATH",
    str(Path(__file__).resolve().parent.parent / "austaltools"),
)
sys.path.insert(0, DISPERSION_PATH)

os.environ.setdefault("BUILDING_SPHINX", "false")

try:
    import _dispersion as dis
except ImportError as exc:
    raise ImportError(
        "_dispersion.py could not be imported.\n"
        f"Tried: {DISPERSION_PATH}\n"
        f"Override with the DISPERSION_PATH environment variable.\n"
        f"Original error: {exc}"
    ) from exc

# ---------------------------------------------------------------------------
# Locate / download test-data files
# ---------------------------------------------------------------------------
_ZIP_URL = (
    "https://www.vdi.de/fileadmin/pages/vdi_de/redakteure/"
    "ueber_uns/fachgesellschaften/KRdL/dateien/AKtest-Dateien.zip"
)
_REQUIRED_FILES = (
    "AKtest_CDCfmt_ein.asc",
    "AKtest_akzr.asc",
    "AKtest_KM.asc",
)

# Module-level tempdir that persists for the lifetime of the process.
# unittest does not guarantee tearDownModule is called before the process
# exits, so we register cleanup with atexit instead.
_tmpdir_obj: tempfile.TemporaryDirectory | None = None


def _resolve_testdata_dir() -> Path:
    """
    Return the directory that contains the three AKtest_*.asc files.

    Resolution order:
      1. TESTDATA_PATH env-var (if set and all files present there).
      2. TESTDATA_PATH env-var default "." (current working directory).
      3. If files are missing: download the VDI zip into a fresh temp
         directory, unpack it there, and return that directory.
    """
    global _tmpdir_obj

    candidate = Path(os.environ.get("TESTDATA_PATH", ".")).resolve()
    if all((candidate / f).exists() for f in _REQUIRED_FILES):
        return candidate

    # Files not found — download the zip into a temporary directory.
    _tmpdir_obj = tempfile.TemporaryDirectory(prefix="vdi3782_testdata_")
    tmpdir = Path(_tmpdir_obj.name)

    zip_path = tmpdir / "AKtest-Dateien.zip"
    print(f"  Test data not found in '{candidate}'.")
    print(f"  Downloading {_ZIP_URL} …", flush=True)
    try:
        urllib.request.urlretrieve(_ZIP_URL, zip_path)
    except Exception as exc:
        _tmpdir_obj.cleanup()
        _tmpdir_obj = None
        raise unittest.SkipTest(
            f"Could not download test data from {_ZIP_URL}: {exc}\n"
            f"Place the three AKtest_*.asc files in TESTDATA_PATH (currently "
            f"'{candidate}') and re-run."
        ) from exc

    print(f"  Unpacking into {tmpdir} …", flush=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(tmpdir)

    # The zip may place files in a subdirectory; search recursively.
    for required in _REQUIRED_FILES:
        matches = list(tmpdir.rglob(required))
        if not matches:
            _tmpdir_obj.cleanup()
            _tmpdir_obj = None
            raise unittest.SkipTest(
                f"'{required}' not found inside the downloaded zip.\n"
                f"Check the archive at {_ZIP_URL}."
            )
        # Move each file to the top level of tmpdir for uniform access.
        target = tmpdir / required
        if matches[0] != target:
            matches[0].rename(target)

    return tmpdir


# Resolve once at import time so all path constants are ready before any
# test class is instantiated.
TESTDATA_DIR = _resolve_testdata_dir()

INPUT_FILE  = TESTDATA_DIR / "AKtest_CDCfmt_ein.asc"
OUTPUT_FILE = TESTDATA_DIR / "AKtest_akzr.asc"
KM_FILE     = TESTDATA_DIR / "AKtest_KM.asc"

# ---------------------------------------------------------------------------
# Station constants (VDI 3782-6, Annex B)
# ---------------------------------------------------------------------------
LAT = 52.20830   # °N
LON = 14.11780   # °E
ELE = 98.0       # m amsl
HAP = 10.4       # measurement height h'_a [m]
Z0P = 0.487      # roughness length    z'_0 [m]

# Expected annual class counts (Table B3)
EXPECTED_COUNTS = {
    "I":    287,
    "II":   1232,
    "III1": 5247,
    "III2": 1253,
    "IV":   494,
    "V":    247,
}
EXPECTED_TOTAL = 8760

# WMO code 0500 numeric → cloud type string used by klug_manier_scheme_2017
# codes 0=CI, 1=CC, 2=CS → cirrus family; all others → non-cirrus
_WMO_CIRRUS = {0: "CI", 1: "CC", 2: "CS"}


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_cdc_input(path: Path) -> pd.DataFrame:
    """
    Parse AKtest_CDCfmt_ein.asc.

    Returns a DataFrame indexed by UTC timestamps with columns:
      ff_raw  – measured wind speed [m/s]
      ff10    – wind speed converted to standard 10 m / z0=0.1 m [m/s]
      tcc     – total cloud cover as fraction [0…1], NaN if missing
      cty     – cloud type string ('CI','CC','CS', or 'OTHER'), NaN if unknown
      cbh     – cloud-base height [m], NaN if missing
    """
    # The header line starts with "* " so comment="*" would drop it.
    # Parse it manually, then read the data rows.
    with open(path, encoding="latin-1") as fh:
        raw_header = fh.readline().lstrip("* ").strip()
    col_names = [c.strip() for c in raw_header.split(";")
                 if c.strip() not in ("", "eor")]

    df = pd.read_csv(
        path,
        sep=r"\s*;\s*",
        engine="python",
        skiprows=1,
        header=None,
        names=col_names + ["eor"],
        na_values=["-9999", "eor"],
        dtype=str,
    )

    # Parse UTC timestamp (YYYYMMDDhh)
    ts = pd.to_datetime(
        df["MESS_DATUM"].str.strip(), format="%Y%m%d%H", utc=True
    )

    # Wind speed: convert measured (HAP, Z0P) → standard (10 m, z0 = 0.1 m)
    ff_raw = pd.to_numeric(df["WINDGESCHWINDIGKEIT"].str.strip(), errors="coerce")
    ff10 = pd.Series(
        dis.vdi_3872_6_standard_wind(ff_raw.values, HAP, Z0P),
        index=ts,
        dtype=float,
    )

    # Total cloud cover: 0…8 oktas → fraction; -1 = missing → NaN
    tcc_raw = pd.to_numeric(df["GESAMT_BEDECKUNGSGRAD"].str.strip(), errors="coerce")
    tcc = tcc_raw.copy()
    tcc[tcc_raw < 0] = np.nan      # -1 = missing
    tcc = (tcc / 8.0).values       # oktas → fraction 0…1
    tcc = pd.Series(tcc, index=ts)

    # Cloud type (WMO 0500 integer): 0=CI, 1=CC, 2=CS → cirrus; -9 = missing
    cty_raw = pd.to_numeric(df["WOLKENART_C1"].str.strip(), errors="coerce")
    cty = cty_raw.map(lambda x: _WMO_CIRRUS.get(int(x), "OTHER")
                      if pd.notna(x) and x >= 0 else np.nan)
    cty = pd.Series(cty.values, index=ts)

    # Cloud-base height [m]; -9999 already mapped to NaN by read_csv
    cbh_raw = pd.to_numeric(df["HOEHE_WOLKENUNTERGRENZE_H1"].str.strip(), errors="coerce")
    cbh = cbh_raw.copy()
    cbh[cbh_raw < 0] = np.nan
    cbh = pd.Series(cbh.values, index=ts)

    return pd.DataFrame({
        "ff_raw": pd.Series(ff_raw.values, index=ts),
        "ff10":   ff10,
        "tcc":    tcc,
        "cty":    cty,
        "cbh":    cbh,
    })


def parse_akzr_output(path: Path) -> pd.Series:
    """
    Parse AKtest_akzr.asc (AUSTAL AKS format).

    Data lines start with 'AK'. Space-separated fields:
      AK <stn> <YYYY> <MM> <DD> <hh> <mm> ... <col13=AK_numeric> ...

    Returns a Series of integer stability classes (1–6)
    indexed by UTC timestamps.
    """
    rows = []
    with open(path, encoding="latin-1") as f:
        for line in f:
            if not line.startswith("AK "):
                continue
            parts = line.split()
            # parts[2]=YYYY, [3]=MM, [4]=DD, [5]=hh, [6]=mm (always 00)
            ts = pd.Timestamp(
                year=int(parts[2]), month=int(parts[3]), day=int(parts[4]),
                hour=int(parts[5]), minute=int(parts[6]),
                tz="UTC",
            )
            ak = int(parts[12])   # column 13 (1-based) = stability class
            rows.append((ts, ak))

    idx, vals = zip(*rows)
    return pd.Series(list(vals), index=list(idx), dtype=int, name="ak_expected")


def parse_km_verification(path: Path) -> pd.DataFrame:
    """
    Parse AKtest_KM.asc (detailed verification file, CET times).

    Data line format (space-separated, no header on data lines):
      YYYY-MM-DD.HH:MM:SS  HH:MM:SS  HH:MM:SS  v10  N  C  AK

    CET timestamps use hours 01–24; hour 24 of day D = hour 00 of day D+1.
    We convert to UTC for alignment with the other files.

    Returns a DataFrame with columns: v10, N, C (cirrus flag), AK.
    """
    rows = []
    with open(path, encoding="latin-1") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) < 7:
                continue

            # Parse "YYYY-MM-DD.HH:MM:SS" – hour 24 means next day 00:00
            date_str, time_str = parts[0].split(".")
            hh, mm, ss = (int(x) for x in time_str.split(":"))
            date = pd.Timestamp(date_str)
            if hh == 24:
                cet_ts = date + pd.Timedelta(days=1)
            else:
                cet_ts = date + pd.Timedelta(hours=hh, minutes=mm, seconds=ss)
            # CET = UTC+1 (fixed offset, no DST used in standard)
            utc_ts = cet_ts - pd.Timedelta(hours=1)
            utc_ts = utc_ts.tz_localize("UTC")

            v10 = float(parts[3])
            n   = int(parts[4])     # oktas after cirrus correction; -9 = missing
            c   = int(parts[5])     # cirrus flag
            ak  = int(parts[6])     # stability class

            rows.append((utc_ts, v10, n, c, ak))

    idx, v10s, ns, cs, aks = zip(*rows)
    return pd.DataFrame(
        {"v10": v10s, "N": ns, "C": cs, "AK": aks},
        index=list(idx),
    )


# ---------------------------------------------------------------------------
# Helper: run klug_manier_scheme_2017 on the parsed input DataFrame
# ---------------------------------------------------------------------------

def run_scheme(inp: pd.DataFrame) -> pd.Series:
    """
    Call klug_manier_scheme_2017() for the full year in one vectorised call.

    The CDC input index is UTC-aware.  The function converts tz-aware
    timestamps to CET internally, so UTC input is passed directly.

    Returns a pd.Series of stability-class names ('I', 'II', 'III1', …)
    indexed by the UTC timestamps from *inp*.
    """
    return dis.klug_manier_scheme_2017(
        time=inp.index,
        ff=inp["ff10"],
        tcc=inp["tcc"],
        lat=LAT,
        lon=LON,
        ele=ELE,
        cty=inp["cty"],
        cbh=inp["cbh"],
    )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestKlugManierScheme2017(unittest.TestCase):
    """Tests against the official VDI 3782-6 test dataset."""

    @classmethod
    def setUpClass(cls):
        """Parse all three reference files once for all tests."""
        cls.inp    = parse_cdc_input(INPUT_FILE)
        cls.akzr   = parse_akzr_output(OUTPUT_FILE)
        cls.km     = parse_km_verification(KM_FILE)
        cls.result = run_scheme(cls.inp)

    # ------------------------------------------------------------------
    # 1. Sanity checks on the parsed input
    # ------------------------------------------------------------------

    def test_input_row_count(self):
        """CDC input file must contain exactly 8760 hourly rows."""
        self.assertEqual(len(self.inp), EXPECTED_TOTAL)

    def test_input_date_range(self):
        """CDC input must span 2010-01-01 00:00 UTC – 2010-12-31 23:00 UTC."""
        self.assertEqual(self.inp.index[0],
                         pd.Timestamp("2010-01-01 00:00:00", tz="UTC"))
        self.assertEqual(self.inp.index[-1],
                         pd.Timestamp("2010-12-31 23:00:00", tz="UTC"))

    def test_no_duplicate_timestamps(self):
        """CDC input must have no duplicate timestamps."""
        self.assertTrue(self.inp.index.is_unique)

    def test_wind_speed_conversion(self):
        """
        Converted wind speed (ff10) must be ≥ 0 everywhere and the
        conversion factor f must differ from 1.0 (HAP ≠ 10 m, Z0P ≠ 0.1 m).
        """
        self.assertTrue((self.inp["ff10"].dropna() >= 0).all())
        f = float(np.asarray(dis.vdi_3872_6_standard_wind(1.0, HAP, Z0P)).flat[0])
        self.assertNotAlmostEqual(f, 1.0, places=3,
                                  msg="Wind-speed conversion factor should differ from 1")

    # ------------------------------------------------------------------
    # 2. Sanity checks on the reference output
    # ------------------------------------------------------------------

    def test_akzr_row_count(self):
        """AUSTAL output file must contain exactly 8760 rows."""
        self.assertEqual(len(self.akzr), EXPECTED_TOTAL)

    def test_km_row_count(self):
        """KM verification file must contain exactly 8760 rows."""
        self.assertEqual(len(self.km), EXPECTED_TOTAL)

    def test_akzr_expected_counts(self):
        """
        Reference AUSTAL output (AKtest_akzr.asc) must reproduce Table B3
        exactly — validates our parser before testing our own output.
        """
        num_to_name = {1: "I", 2: "II", 3: "III1", 4: "III2", 5: "IV", 6: "V"}
        counts = self.akzr.map(num_to_name).value_counts().to_dict()
        for cls_name, expected in EXPECTED_COUNTS.items():
            with self.subTest(cls=cls_name):
                self.assertEqual(
                    counts.get(cls_name, 0), expected,
                    msg=f"Reference file count mismatch for class {cls_name}"
                )

    # ------------------------------------------------------------------
    # 3. Core test: annual class-count totals (Table B3)
    # ------------------------------------------------------------------

    def test_annual_class_counts(self):
        """
        Annual stability-class counts must match VDI 3782-6, Table B3 exactly.
        This is the primary acceptance criterion stated in the standard.
        """
        counts = self.result.value_counts().to_dict()
        for cls_name, expected in EXPECTED_COUNTS.items():
            with self.subTest(cls=cls_name):
                actual = counts.get(cls_name, 0)
                self.assertEqual(
                    actual, expected,
                    msg=(
                        f"Class {cls_name}: got {actual}, expected {expected} "
                        f"(diff {actual - expected:+d})"
                    ),
                )

    def test_total_hours(self):
        """All 8760 hours must receive a valid stability class (no undefined)."""
        self.assertEqual(len(self.result), EXPECTED_TOTAL)
        undefined = self.result.isna().sum()
        self.assertEqual(
            undefined, 0,
            msg=f"{undefined} hours returned NaN / undefined class"
        )

    # ------------------------------------------------------------------
    # 4. Hour-by-hour agreement with AKtest_akzr.asc
    # ------------------------------------------------------------------

    def test_hourly_agreement_with_akzr(self):
        """
        The computed stability class must match AKtest_akzr.asc for every
        single hour of 2010 (8760 individual comparisons).
        """
        name_to_num = {"I": 1, "II": 2, "III1": 3, "III2": 4, "IV": 5, "V": 6}
        computed_num = self.result.map(name_to_num)

        shared = computed_num.index.intersection(self.akzr.index)
        self.assertEqual(len(shared), EXPECTED_TOTAL,
                         msg="Timestamp alignment failed between computed result and akzr")

        computed_aligned = computed_num.loc[shared]
        expected_aligned = self.akzr.loc[shared]

        mismatches = (computed_aligned != expected_aligned).sum()
        if mismatches > 0:
            diff_idx = shared[computed_aligned.values != expected_aligned.values]
            details = []
            for ts in diff_idx[:10]:
                details.append(
                    f"  {ts}  computed={computed_aligned[ts]}  "
                    f"expected={expected_aligned[ts]}"
                )
            self.fail(
                f"{mismatches} hour(s) differ from AKtest_akzr.asc:\n"
                + "\n".join(details)
            )

    # ------------------------------------------------------------------
    # 5. Intermediate-value agreement with AKtest_KM.asc
    # ------------------------------------------------------------------

    def test_wind_speed_matches_km_file(self):
        """
        Converted wind speed (v10) must match AKtest_KM.asc to within
        0.05 m/s (half the stated rounding precision of 0.1 m/s) for
        all hours with valid observations.
        """
        shared = self.inp.index.intersection(self.km.index)
        ff_computed  = self.inp["ff10"].loc[shared]
        ff_reference = pd.Series(self.km["v10"].values,
                                 index=self.km.index).loc[shared]

        valid    = ff_reference > 0  # skip rows where reference marks missing
        abs_diff = (ff_computed[valid] - ff_reference[valid]).abs()
        n_exceed = (abs_diff > 0.05).sum()

        self.assertEqual(
            n_exceed, 0,
            msg=(
                f"{n_exceed} hour(s) exceed 0.05 m/s wind-speed tolerance "
                f"(max diff = {abs_diff.max():.3f} m/s)"
            ),
        )

    def test_cirrus_flag_matches_km_file(self):
        """
        Cirrus detection (C column in KM file) must match our WMO cloud-type
        parsing for all hours where a cloud-type observation is present.
        """
        shared = self.inp.index.intersection(self.km.index)
        cty_inp = self.inp["cty"].loc[shared]
        c_ref   = pd.Series(self.km["C"].values, index=self.km.index).loc[shared]

        cirrus_computed = cty_inp.isin(["CI", "CC", "CS"]).astype(int)
        known           = cty_inp.notna()  # only compare definite observations

        mismatches = (cirrus_computed[known] != c_ref[known]).sum()
        self.assertEqual(
            mismatches, 0,
            msg=f"{mismatches} hour(s): cirrus flag mismatch with KM file"
        )

    # ------------------------------------------------------------------
    # 6. Rule d): IV → III/2 in December, January, February
    # ------------------------------------------------------------------

    def test_winter_rule_no_class_IV_in_DJF(self):
        """
        VDI 3782-6, Section 4.4 d): Class IV must not appear in December,
        January, or February — it is replaced by III/2.

        The month check is done in CET (the zone used by the correction
        rules), not in the UTC timezone of the index.  A UTC timestamp of
        e.g. 2010-01-31 23:00 is 2010-02-01 00:00 CET; checking only
        index.month would assign it to January and could miss a rule-d
        violation that the function correctly caught in February.
        """
        cet_months = self.result.index.tz_convert("Etc/GMT-1").month
        djf_mask   = pd.Series(cet_months).isin([12, 1, 2]).values
        iv_in_djf  = (self.result[djf_mask] == "IV").sum()
        self.assertEqual(
            iv_in_djf, 0,
            msg=f"Rule d) violated: Class IV appeared {iv_in_djf} time(s) in DJF"
        )

    # ------------------------------------------------------------------
    # 7. Timezone invariance: UTC and CET inputs must give identical output
    # ------------------------------------------------------------------

    def test_timezone_invariance(self):
        """
        klug_manier_scheme_2017 converts any tz-aware input to CET internally
        before extracting hours and months.  Passing the same physical instants
        as UTC vs. CET must therefore produce identical results.

        Uses the full test-dataset index so that all correction-rule boundaries
        (rule a 10:00/16:00 CET, rule b 11:00/15:00 CET, and UTC≠CET months
        at midnight on month boundaries) are exercised.
        """
        inp = self.inp
        utc_index = inp.index                          # already UTC-aware
        cet_index = utc_index.tz_convert("Etc/GMT-1")

        result_utc = dis.klug_manier_scheme_2017(
            time=utc_index,
            ff=inp["ff10"],
            tcc=inp["tcc"],
            lat=LAT, lon=LON, ele=ELE,
            cty=inp["cty"], cbh=inp["cbh"],
        )

        result_cet = dis.klug_manier_scheme_2017(
            time=cet_index,
            ff=pd.Series(inp["ff10"].values, index=cet_index),
            tcc=pd.Series(inp["tcc"].values,  index=cet_index),
            lat=LAT, lon=LON, ele=ELE,
            cty=pd.Series(inp["cty"].values,  index=cet_index),
            cbh=pd.Series(inp["cbh"].values,  index=cet_index),
        )

        mismatches = (result_utc.values != result_cet.values).sum()
        self.assertEqual(
            mismatches, 0,
            msg=(
                f"{mismatches} hour(s) differ between UTC and CET input — "
                f"timezone-invariance fix is not working correctly"
            ),
        )

    # ------------------------------------------------------------------
    # 8. Class V is produced exclusively by seasonal corrections
    # ------------------------------------------------------------------

    def test_class_v_only_in_seasonal_correction_months(self):
        """
        Class V can only arise from seasonal corrections (rules a and b):
          - Rule a: June, July, August (JJA)
          - Rule b: May, September
        Any Class V in other months indicates a logic error.
        """
        correction_months = {5, 6, 7, 8, 9}
        non_correction_mask = ~pd.Series(self.result.index.month).isin(correction_months).values
        v_outside_corrections = (self.result[non_correction_mask] == "V").sum()
        self.assertEqual(
            v_outside_corrections, 0,
            msg=(f"Class V appeared {v_outside_corrections} time(s) outside "
                 f"seasonal-correction months (May–Sep)")
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
