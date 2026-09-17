"""
link_plz_nuts3.py
=================
Links German postal code (PLZ) data from pseudonymised FHIR clinical records
to NUTS3 regional boundaries using an area-weighted spatial overlay.

Overview
--------
1. Reads three FHIR-derived CSV files (Patient, Condition, Encounter) and
   merges them into a single dataset of interest (dOI).
2. Loads PLZ polygon geometries (GeoPackage) and NUTS3 boundary polygons
   (shapefile, extracted from a ZIP archive if necessary).
3. Reprojects both layers to EPSG:3035 (ETRS89-LAEA) for metric area
   calculations.
4. For each distinct PLZ digit-length present in dOI, dissolves the 5-digit
   PLZ polygons to the appropriate coarseness and assigns each zone to the
   NUTS3 region with the largest intersection area.
5. Computes patient ages (in full years) at three clinical event dates.
6. Replaces exact dates with ISO calendar-week strings (YYYY_WW) to reduce
   re-identification risk.
7. Writes the result to result.csv.

Refer to test_data_merge.ipynb for a fully annotated, step-by-step walkthrough
of this pipeline with intermediate outputs and design notes.

Dependencies
------------
    pip install geopandas pandas

Required input files (relative to the working directory)
---------------------------------------------------------
    PLZ_Gebiete.gpkg               5-digit PLZ polygon GeoPackage
    nuts250_12-31.gk3.shape.zip    NUTS3 boundary shapefile (ZIP archive)
    test_data_filled/
        Diagnose.csv
        KontaktGesundheitseinrichtung.csv
        PatientPseudonymisiert.csv

Usage
-----
    python link_plz_nuts3.py

Output
------
    result.csv   Merged table with NUTS3 assignment, calendar-week timestamps,
                 and derived patient ages. No index column.
"""

import pandas as pd
import geopandas as gpd
import zipfile
import numpy as np


# ===========================================================================
# Main Pipeline Part 1
# ===========================================================================

# ---------------------------------------------------------------------------
# Step 1: 
#   Load clinical CSV files
#   Change paths according to you input data    
# ---------------------------------------------------------------------------

# PLZ (postal code) must be read as a string to preserve leading zeros.
diagnose = pd.read_csv("test_data_filled/Diagnose.csv")
kontaktGesundheitseinrichtung = pd.read_csv("test_data_filled/KontaktGesundheitseinrichtung.csv")
patientPseudonymisiert = pd.read_csv(
    "test_data_filled/PatientPseudonymisiert.csv",
    dtype={"Patient_addressStrassenanschrift_postalCode": str}
)
# set path tp resultfile
result_file_path = 'result.csv'

# ===========================================================================
# Main Pipeline End Part 1
# ===========================================================================

# ---------------------------------------------------------------------------
# Helper: Date Parsing
# ---------------------------------------------------------------------------

def parse_datum(val):
    """Parse a FHIR date/datetime string to a timezone-naive midnight datetime.

    FHIR resources use multiple date formats depending on precision. This
    function tries each format in descending order of specificity and returns
    the first successful parse as a tz-naive, time-stripped Timestamp.

    Parameters
    ----------
    val : any
        Raw cell value from the CSV. May be NaN, an empty string, or a date
        string in one of the supported formats.

    Returns
    -------
    pd.Timestamp or pd.NaT
        Timezone-naive date (time set to midnight), or NaT if the value is
        missing or cannot be parsed.

    Supported formats
    -----------------
    - ``%Y-%m-%dT%H:%M:%S%z``  e.g. 2023-01-15T10:30:00+02:00
    - ``%Y-%m-%d``             e.g. 2023-01-15
    - ``%Y-%m``                e.g. 2023-01
    - ``%Y``                   e.g. 2023
    """
    if pd.isna(val) or str(val).strip() == "":
        return pd.NaT

    val = str(val).strip()

    for fmt in [
        "%Y-%m-%dT%H:%M:%S%z",  # full ISO-8601 with timezone
        "%Y-%m-%d",              # date only
        "%Y-%m",                 # year-month only
        "%Y",                    # year only
    ]:
        try:
            dt = pd.to_datetime(val, format=fmt)
            # Strip time component and timezone; return a plain date
            return (
                dt.normalize().tz_localize(None)
                if dt.tzinfo is None
                else dt.tz_convert(None).normalize()
            )
        except ValueError:
            continue

    return pd.NaT


# ---------------------------------------------------------------------------
# Helper: PLZ Precision Reduction
# ---------------------------------------------------------------------------

def reduce_plz_precision(gdf: gpd.GeoDataFrame, digits: int) -> gpd.GeoDataFrame:
    """Truncate 5-digit PLZ codes to a coarser prefix and dissolve geometries.

    All PLZ zones that share the same ``digits``-length prefix are unioned
    into a single polygon. This produces the reference geometry layer needed
    when input data contains abbreviated PLZ codes (e.g. only 3 digits).

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        Full 5-digit PLZ GeoDataFrame with a ``plz`` column.
    digits : int
        Target number of digits. Must be one of {2, 3, 4, 5}.

    Returns
    -------
    gpd.GeoDataFrame
        Dissolved GeoDataFrame with one row per unique ``digits``-digit PLZ
        prefix and a ``geometry`` column containing the unioned polygon.

    Raises
    ------
    ValueError
        If ``digits`` is not in {2, 3, 4, 5}.
    """
    if digits not in (2, 3, 4, 5):
        raise ValueError("digits must be 2, 3, 4 or 5")

    result = gdf.copy()
    # Zero-pad to ensure consistent 5-digit strings, then truncate
    result["plz"] = result["plz"].astype(str).str.zfill(5).str[:digits]
    # Union all geometries sharing the same truncated code
    return result.dissolve(by="plz", as_index=False)


# ---------------------------------------------------------------------------
# Helper: NUTS3 Assignment by Largest Intersection Area
# ---------------------------------------------------------------------------

def assign_nuts3_by_area(gdf_plz_reduced, gdf_nuts3):
    """Assign each PLZ zone to the NUTS3 region with the largest overlap.

    Computes a geometric intersection overlay between ``gdf_plz_reduced`` and
    ``gdf_nuts3``, measures the area of each intersection piece, and for every
    PLZ zone selects the NUTS3 polygon that contributes the most area.

    Both GeoDataFrames must share the same CRS (EPSG:3035 recommended).

    Parameters
    ----------
    gdf_plz_reduced : gpd.GeoDataFrame
        (Possibly dissolved) PLZ zones with columns [``plz``, ``geometry``].
    gdf_nuts3 : gpd.GeoDataFrame
        NUTS3 boundary layer with columns [``NUTS_CODE``, ``NUTS_NAME``,
        ``geometry``].

    Returns
    -------
    pd.DataFrame
        Lookup table with columns [``plz``, ``NUTS_CODE``, ``NUTS_NAME``],
        one row per unique PLZ zone.
    """
    # Intersect PLZ zones with NUTS3 polygons; each piece gets both attributes
    overlay = gpd.overlay(
        gdf_plz_reduced[['plz', 'geometry']],
        gdf_nuts3[['NUTS_CODE', 'NUTS_NAME', 'geometry']],
        how='intersection'
    )

    # Compute area for each intersection fragment in the projected CRS
    overlay['intersection_area'] = overlay.geometry.area

    # For each PLZ zone, keep the NUTS3 region with the largest fragment
    idx = overlay.groupby('plz')['intersection_area'].idxmax()
    return overlay.loc[idx, ['plz', 'NUTS_CODE', 'NUTS_NAME']].copy()


# ---------------------------------------------------------------------------
# Helper: Build Mapping for All PLZ Precisions in dOI
# ---------------------------------------------------------------------------

def build_flexible_mapping(dOI, gdf_plz, gdf_nuts3):
    """Build a PLZ → NUTS3 lookup table covering all digit lengths in dOI.

    Inspects the ``plz`` column of ``dOI`` to find all distinct string lengths
    (e.g. 2, 3, 5). For each valid length it calls ``reduce_plz_precision``
    and ``assign_nuts3_by_area`` to create a precision-specific sub-mapping,
    then concatenates them. The combined table is keyed on (``plz``,
    ``_plz_len``) so a mixed-precision dataset can be joined in one pass.

    Parameters
    ----------
    dOI : pd.DataFrame
        Dataset of interest with a ``plz`` column (string type).
    gdf_plz : gpd.GeoDataFrame
        Full 5-digit PLZ reference layer.
    gdf_nuts3 : gpd.GeoDataFrame
        NUTS3 boundary layer.

    Returns
    -------
    pd.DataFrame
        Concatenated mapping with columns [``plz``, ``NUTS_CODE``,
        ``NUTS_NAME``, ``_plz_len``].
    """
    plz_lengths = dOI['plz'].dropna().str.len().unique()
    mappings = []

    for length in sorted(plz_lengths):
        if length not in (2, 3, 4, 5):
            print(f"  Warning: skipping PLZ length {length} (not in 2-5)")
            continue

        print(f"  Building NUTS3 mapping for {length}-digit PLZ...")
        reduced = reduce_plz_precision(gdf_plz, digits=length)
        mapping = assign_nuts3_by_area(reduced, gdf_nuts3)
        mapping['_plz_len'] = length
        mappings.append(mapping)

    return pd.concat(mappings, ignore_index=True)


# ---------------------------------------------------------------------------
# Helper: Calendar-Week Formatting
# ---------------------------------------------------------------------------

def to_year_week(dt_series):
    """Convert a datetime Series to ISO calendar-week strings (YYYY_WW).

    Uses ISO 8601 week numbering (week starts on Monday). Missing values
    become empty strings rather than NaN to ensure a clean CSV output.

    Parameters
    ----------
    dt_series : pd.Series
        Series of timezone-naive Timestamps (as produced by ``parse_datum``).

    Returns
    -------
    pd.Series
        String Series of the form ``'2023_04'`` for the 4th week of 2023.
        NaT entries become ``''``.
    """
    iso = dt_series.dt.isocalendar()
    result = (
        iso["year"].astype("Int64").astype(str) + "_" +
        iso["week"].astype("Int64").astype(str).str.zfill(2)
    )
    result[dt_series.isna()] = ""
    return result


# ---------------------------------------------------------------------------
# Helper: Age in Full Years
# ---------------------------------------------------------------------------

def age_in_years(event_series, birth_series):
    """Compute patient age in full years at a given event date.

    Age is calculated as ``floor((event_date - birth_date).days / 365.25)``.
    Dividing by 365.25 (rather than 365) accounts for leap years and produces
    the correct completed-year count for the vast majority of date pairs.

    Parameters
    ----------
    event_series : pd.Series
        Datetime Series for the event (encounter start, recorded date, etc.).
    birth_series : pd.Series
        Datetime Series of patient birth dates.

    Returns
    -------
    pd.Series
        Nullable integer Series (``Int64``). Rows where either input is NaT
        are set to ``pd.NA``.
    """
    days = (event_series - birth_series).dt.days
    age = np.floor(days / 365.25).astype("Int64")
    # Propagate missingness from either input
    age[event_series.isna() | birth_series.isna()] = pd.NA
    return age


# ===========================================================================
# Main Pipeline Part 2
# ===========================================================================


# ---------------------------------------------------------------------------
# Step 2: Normalise PatientPseudonymisiert
# ---------------------------------------------------------------------------
# Retain only the columns needed downstream and rename for clarity.
patientPseudonymisiert = patientPseudonymisiert[[
    'id', 'Patient_gender', 'Patient_birthDate',
    'Patient_addressStrassenanschrift_postalCode'
]]
patientPseudonymisiert.rename(columns={
    'Patient_addressStrassenanschrift_postalCode': 'plz',
    'id': 'patient_id'
}, inplace=True)

# ---------------------------------------------------------------------------
# Step 3: Normalise Diagnose
# ---------------------------------------------------------------------------
# FHIR references include resource type prefixes (e.g. "Patient/abc123").
# Strip them so we can join on bare IDs.
diagnose['patient'] = diagnose['patient'].str.replace('Patient/', '')
diagnose['Condition_encounter_reference'] = (
    diagnose['Condition_encounter_reference'].str.replace('Encounter/', '')
)
diagnose = diagnose[[
    'id', 'patient', 'Condition_recordedDate',
    'Condition_encounter_reference',
    'Condition_extensionFeststellungsdatum_value_X_Valuedatetime'
]]
diagnose.rename(columns={
    'patient': 'patient_id',
    'id': 'condition_id',
    'Condition_encounter_reference': 'encounter_id',
    'Condition_extensionFeststellungsdatum_value_X_Valuedatetime': 'Feststellungsdatum'
}, inplace=True)

# ---------------------------------------------------------------------------
# Step 4: Normalise KontaktGesundheitseinrichtung (Encounter)
# ---------------------------------------------------------------------------
kontaktGesundheitseinrichtung['patient'] = (
    kontaktGesundheitseinrichtung['patient'].str.replace('Patient/', '')
)
kontaktGesundheitseinrichtung['Encounter_diagnosis_condition_reference'] = (
    kontaktGesundheitseinrichtung['Encounter_diagnosis_condition_reference']
    .str.replace('Condition/', '')
)
kontaktGesundheitseinrichtung = kontaktGesundheitseinrichtung[[
    'id', 'patient', 'Encounter_period_start',
    'Encounter_diagnosis_condition_reference'
]]
kontaktGesundheitseinrichtung.rename(columns={
    'patient': 'patient_id',
    'id': 'encounter_id',
    'Encounter_diagnosis_condition_reference': 'condition_id'
}, inplace=True)

# ---------------------------------------------------------------------------
# Step 5: Merge into dataset of interest (dOI)
# ---------------------------------------------------------------------------
# Join order: Condition → Patient (inner) → Encounter (left).
# A left join for Encounter preserves conditions without a recorded encounter.
dOI = pd.merge(
    pd.merge(diagnose, patientPseudonymisiert, on='patient_id'),
    kontaktGesundheitseinrichtung, how='left', on='encounter_id'
)

# Replace original patient IDs with a surrogate numeric key
dOI["id"] = pd.factorize(dOI["patient_id_x"])[0]
dOI = dOI[[
    'id', 'plz', 'Encounter_period_start', 'Condition_recordedDate',
    'Patient_gender', 'Patient_birthDate', 'Feststellungsdatum'
]]

# Parse all date columns to uniform timezone-naive datetimes
dOI["Patient_birthDate"]       = dOI["Patient_birthDate"].apply(parse_datum)
dOI["Encounter_period_start"]  = dOI["Encounter_period_start"].apply(parse_datum)
dOI["Condition_recordedDate"]  = dOI["Condition_recordedDate"].apply(parse_datum)
dOI["Feststellungsdatum"]      = dOI["Feststellungsdatum"].apply(parse_datum)

# ---------------------------------------------------------------------------
# Step 6: Load geospatial reference layers
# ---------------------------------------------------------------------------
plz_gpkg  = r'PLZ_Gebiete.gpkg'
zip_file  = r'nuts250_12-31.gk3.shape.zip'
nuts3_shp = r'extracted_shapefile\nuts250_12-31.gk3.shape\nuts250_1231\NUTS250_N3.shp'

# Load PLZ polygons
gdf_plz = gpd.read_file(plz_gpkg)

# Load NUTS3 polygons; extract from ZIP archive if the shapefile is not present
try:
    nuts3_gdf = gpd.read_file(nuts3_shp)
except Exception:
    print(f"Shapefile not found, extracting from {zip_file}...")
    extract_dir = "extracted_shapefile"
    with zipfile.ZipFile(zip_file, 'r') as z:
        z.extractall(extract_dir)
    nuts3_gdf = gpd.read_file(nuts3_shp)

# ---------------------------------------------------------------------------
# Step 7: Reproject to EPSG:3035 (ETRS89-LAEA Europe)
# ---------------------------------------------------------------------------
# Both layers must share a metric equal-area CRS for correct area comparisons.
target_crs = 'EPSG:3035'
if gdf_plz.crs != target_crs:
    gdf_plz = gdf_plz.to_crs(target_crs)
if nuts3_gdf.crs != target_crs:
    nuts3_gdf = nuts3_gdf.to_crs(target_crs)

# ---------------------------------------------------------------------------
# Step 8: Spatial join — assign each PLZ zone to a NUTS3 region
# ---------------------------------------------------------------------------
# A temporary helper column tracks PLZ string length so mixed-precision data
# (e.g. some rows with 3-digit PLZ, others with 5-digit) can be handled.
dOI['_plz_len'] = dOI['plz'].str.len()
mapping = build_flexible_mapping(dOI, gdf_plz, nuts3_gdf)

dOI = dOI.merge(
    mapping,
    on=['plz', '_plz_len'],
    how='left'
).drop(columns=['_plz_len'])

print(f"Matched {dOI['NUTS_CODE'].notna().sum()} / {len(dOI)} rows to NUTS3")

# ---------------------------------------------------------------------------
# Step 9: Compute patient ages at key clinical events
# ---------------------------------------------------------------------------
# Ages must be calculated before date columns are overwritten by to_year_week.
dOI["age_encounter_start"]    = age_in_years(dOI["Encounter_period_start"], dOI["Patient_birthDate"])
dOI["age_recordedDate"]       = age_in_years(dOI["Condition_recordedDate"],  dOI["Patient_birthDate"])
dOI["age_Feststellungsdatum"] = age_in_years(dOI["Feststellungsdatum"],      dOI["Patient_birthDate"])

# ---------------------------------------------------------------------------
# Step 10: Anonymise dates — replace with ISO calendar-week strings
# ---------------------------------------------------------------------------
dOI["Encounter_period_start"] = to_year_week(dOI["Encounter_period_start"])
dOI["Condition_recordedDate"] = to_year_week(dOI["Condition_recordedDate"])
dOI["Feststellungsdatum"]     = to_year_week(dOI["Feststellungsdatum"])

# ---------------------------------------------------------------------------
# Step 11: Remove identifying columns and save
# ---------------------------------------------------------------------------
# Birth date is no longer needed once ages have been derived.
# PLZ is dropped because NUTS3 provides sufficient regional granularity.
dOI = dOI.drop(columns=["Patient_birthDate", "plz"])

print('Saving result...')
dOI.to_csv(result_file_path, index=False)
print(f"Done. {len(dOI)} rows written to result.csv")
