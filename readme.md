# PLZ → NUTS3 Linkage — User Guide

This guide explains how to run `link_plz_nuts3.py`, which assigns German postal code (PLZ) areas in pseudonymised FHIR clinical records to NUTS3 regional boundaries. For a step-by-step walkthrough of every processing stage — including intermediate outputs and design rationale — refer to the companion notebook [[`test_data_merge.ipynb`](test_data_merge.ipynb](https://github.com/BIH-DMBS/kawagen/blob/master/kawagen_anonym/test_data_merge.ipynb)).

---

## Prerequisites

Install the required Python packages:

```shell
pip install geopandas pandas
```

Place the following files in your working directory before running the script:

| File | Description |
|---|---|
| `PLZ_Gebiete.gpkg` | GeoPackage of 5-digit PLZ polygons with a `plz` column |
| `nuts250_12-31.gk3.shape.zip` | ZIP archive containing the NUTS3 boundary shapefile from BKG |
| `test_data_filled/Diagnose.csv` | FHIR Condition resources (CSV export) |
| `test_data_filled/KontaktGesundheitseinrichtung.csv` | FHIR Encounter resources (CSV export) |
| `test_data_filled/PatientPseudonymisiert.csv` | Pseudonymised FHIR Patient resources (CSV export) |

In the `folder test_data_ori_fdpg` you find the inital files to send by the FDPG to us to develop the script. 

The script extracts the NUTS3 shapefile from the ZIP archive automatically on first run.

---

## Running the script

For a first test just run:
```shell
python link_plz_nuts3.py
```

If real data is availablealter the paths to the input files and aoutput file at the top of the script.

The script runs non-interactively and prints progress messages to the console. On completion it writes per default `result.csv` to the working directory.

---

## What the script does

The pipeline runs in eleven steps. See `test_data_merge.ipynb` for annotated code and sample outputs for each step.

**Steps 1–5 — Load and merge clinical data**

The three FHIR CSV files are read, normalised, and merged into a single dataset of interest (`dOI`). FHIR reference prefixes such as `Patient/` and `Encounter/` are stripped so that IDs can be joined directly. Original patient IDs are replaced with a numeric surrogate key. All date columns are parsed to a uniform, timezone-naive datetime format that handles full ISO-8601 timestamps, date-only strings, year-month strings, and year-only strings.

**Steps 6–7 — Load and reproject geospatial layers**

The PLZ polygon layer and the NUTS3 boundary layer are loaded into GeoDataFrames. Both are reprojected to EPSG:3035 (ETRS89-LAEA Europe), a metric equal-area projection suitable for area comparisons across Germany.

**Step 8 — Spatial join: PLZ → NUTS3**

Each PLZ zone is assigned to the NUTS3 region that covers the largest portion of its area. Because PLZ boundaries do not align with NUTS3 boundaries, a geometric intersection overlay is computed first, and the dominant NUTS3 region is selected per PLZ zone. This is handled automatically for all PLZ digit lengths present in the data (2–5 digits), allowing mixed-precision datasets to be processed in a single pass. See the *PLZ precision* section below for details.

**Step 9 — Age computation**

Patient ages (in complete years) are calculated at three clinical event dates: encounter start, condition documentation date, and diagnosis confirmation date (`Feststellungsdatum`). Ages are computed before dates are converted in the next step.

**Step 10 — Date anonymisation**

Exact dates are replaced with ISO calendar-week strings of the form `YYYY_WW` (e.g. `2023_04` for the fourth week of 2023). Missing dates become empty strings.

**Step 11 — Remove identifying columns and save**

Birth date and PLZ are dropped from the output. The final table is written to `result.csv` without a row index.

---

## Output file

`result.csv` contains one row per diagnosis record with the following columns:

| Column | Type | Description |
|---|---|---|
| `id` | int | Surrogate patient identifier |
| `Patient_gender` | str | Gender as recorded in FHIR |
| `Encounter_period_start` | str | Encounter start, as `YYYY_WW` |
| `Condition_recordedDate` | str | Condition documentation date, as `YYYY_WW` |
| `Feststellungsdatum` | str | Diagnosis confirmation date, as `YYYY_WW` |
| `NUTS_CODE` | str | NUTS3 region code (e.g. `DE300`) |
| `NUTS_NAME` | str | NUTS3 region name (e.g. `Berlin`) |
| `age_encounter_start` | Int64 | Patient age in years at encounter start |
| `age_recordedDate` | Int64 | Patient age in years at condition documentation |
| `age_Feststellungsdatum` | Int64 | Patient age in years at diagnosis confirmation |

Rows where a date or birth date was missing will show `NA` in the corresponding age column.

---

## PLZ precision

The script automatically detects the digit length of PLZ values in the input data. When a PLZ has fewer than five digits (because it was truncated before pseudonymisation), the script dissolves the 5-digit reference polygons to the same digit length before computing intersections. This ensures that the spatial match operates at the correct level of granularity.

| PLZ digits | Behaviour |
|---|---|
| 5 | Original fine-grained PLZ polygons are used directly |
| 4 | All PLZ zones sharing the first four digits are dissolved into one polygon |
| 3 | Dissolved to three-digit postal districts (coarser regions) |
| 2 | Very coarse aggregation; multiple NUTS3 regions may be spanned |

If your data contains PLZ values of mixed lengths (e.g. some patients with 5-digit codes and others with 2-digit codes), the script processes each length separately and merges the results correctly.

A warning is printed for any PLZ digit length outside the supported range of 2–5.

---

## Console output

During a successful run you will see messages similar to the following:

```
  Building NUTS3 mapping for 3-digit PLZ...
  Building NUTS3 mapping for 5-digit PLZ...
Matched 28 / 29 rows to NUTS3
Saving result...
Done. 29 rows written to result.csv
```

An unmatched row (NUTS3 columns will be empty) typically indicates a PLZ value that does not appear in the reference GeoPackage — for example, a malformed code or a value that genuinely falls outside Germany.

---

## Troubleshooting

**Missing packages** — Install with `pip install geopandas pandas`. If `geopandas` installation fails, ensure that `GDAL` system libraries are present; on Debian/Ubuntu: `apt install gdal-bin libgdal-dev`.

**No NUTS3 matches** — Verify that the `plz` column in the patient file uses the correct number of digits and that leading zeros are preserved. Check that `PLZ_Gebiete.gpkg` covers the geographic area of interest.

**Shapefile extraction fails** — Ensure that `nuts250_12-31.gk3.shape.zip` is present in the working directory and is not corrupted. The script will attempt extraction on first run and reuse the extracted files on subsequent runs.

---

## Reference implementation

`test_data_merge.ipynb` contains the same pipeline in notebook form with:

- Markdown documentation for every processing stage
- Sample DataFrames displayed after each merge and transformation step
- Design notes explaining why area-based NUTS3 assignment is used and how mixed-precision PLZ data is handled
- The full output table before and after date anonymisation

Run the notebook interactively to inspect intermediate results or to adapt the pipeline to a different data schema.
