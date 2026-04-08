# Manual for `link_plz_nuts3.py`

This document explains how to use the `link_plz_nuts3.py` script to join German postal code (PLZ) areas to NUTS3 regions. It also describes how to generate sample data with `generate_test_data.py` and how the script handles different PLZ precisions.

---

## Prerequisites

- Python 3.x with the following packages installed:
  - `geopandas`
  - `pandas`
  - their dependencies (e.g. `shapely`, `pyproj`, etc.)
- A working directory containing the following files (paths are relative to `final_scripts` but may be overridden by command-line arguments):
  - `PLZ_Gebiete.gpkg` – a GeoPackage of 5‑digit postal code polygons with a column named `plz`.
  - `extracted_shapefile\nuts250_12-31.gk3.shape\nuts250_1231\NUTS250_N3.shp` – the NUTS3 boundary shapefile. (Both files are bundled in this folder.)
  - `link_plz_nuts3.py` – the linking script.
  - `generate_test_data.py` – helper to create CSVs for testing.

The scripts assume a default CRS of EPSG:3035 for both datasets; they will reproject if necessary.

---

## Generating test data

To create a CSV of random PLZs and dates, run:

```shell
cd c:\code\plz\final_scripts
python generate_test_data.py
```

This will:

1. Read `PLZ_Gebiete.gpkg` and collect all unique 5‑digit PLZ strings (zero-padded).
2. The created `test_data.csv` contains 1000 rows of randomly selected PLZs and a random date between 2000‑01‑01 and 2025‑12‑31.
3. The script produces truncated variants with shorter PLZ prefixes:
   - `test_data_plz4.csv` (first 4 digits)
   - `test_data_plz3.csv` (first 3 digits)
   - `test_data_plz2.csv` (first 2 digits)

These variants are handy for exercising the different precision modes of the linking script.

The content of the test data csv files will look similar to this:

  PLZ | Diagnosis_Feststellungsdatum | Diagnose_Dokumentationsdatum | Beginn_Einrichtungskontakt | Geburtsdatum | Sex |
 |-----|-------------------------------|-------------------------------|-----------------------------|--------------|-----|
 | 61  | 2007-11-10                    | 2004-09-03                    | 2011-05-23                  | 2006-09-24   | F   |
 | 94  | 2003-11-27                    | 2018-03-22                    | 2018-09-01                  | 1994-06-02   | M   |
 | 46  | 2017-09-08                    | 2008-07-18                    | 2012-11-05                  | 2003-12-19   | M   |

---

## Using `link_plz_nuts3.py`

### Basic command-line usage

```powershell
python link_plz_nuts3.py [input_csv] [-l LENGTH] [-o OUTPUT]
```

- `input_csv` (optional) – path to a CSV file containing a column named `PLZ` (string). Defaults to `\test_data.csv` (relative to current working directory).
- `-o`, `--output` – path where the linked CSV will be written. If omitted, the script appends `_nuts3_linked.csv` to the base name of the input file; e.g. `test_data_plz3.csv` → `test_data_plz3_nuts3.csv`.

Example for 4‑digit precision:

```powershell
python link_plz_nuts3.py test_data_plz4.csv -l 4
```

### What the script does

1. **Read PLZ polygons** from the GeoPackage (`PLZ_Gebiete.gpkg`) into a GeoDataFrame `gdf_plz`.
2. **Reduce PLZ precision** if `-l` is less than 5. The helper function `reduce_plz_precision`:
   - Converts the `plz` column to a zero-padded 5-character string.
   - Truncates to the first `digits` characters (2–4).
   - Dissolves (unions) all geometries sharing the same truncated PLZ, yielding a coarser set of zones.
   - This step is skipped when `-l` is 5, meaning the original 5‑digit areas are used.
3. **Load NUTS3 polygons** from the shapefile (`NUTS250_N3.shp`) into `nuts3_gdf`.
4. **Reproject** both GeoDataFrames to EPSG:3035 if they are not already in that CRS.
5. **Assign each PLZ zone to a NUTS3 region** using the function `assign_nuts3_by_area`:
   - Compute a geometric intersection overlay between the (possibly reduced) PLZ zones and the NUTS3 polygons.
   - Calculate the area of each intersection.
   - For each PLZ zone, pick the NUTS3 polygon with the largest intersection area (this is the "best fit" by land area).
   - The result is a mapping table with columns `plz`, `NUTS_CODE`, and `NUTS_NAME`.
6. **Read the input CSV** into a pandas DataFrame, ensuring the `PLZ` column is treated as a string.
7. **Merge test data with the mapping** on the `PLZ` field, keeping all input rows (`left` join). Unmatched PLZs will have `NaN` for the NUTS fields.
8. **Date Field** `Diagnosis_Feststellungsdatum`,`Diagnose_Dokumentationsdatum`,`Beginn_Einrichtungskontakt` are rounded to calender week and year (2001-01-01 becomes 2001_1) using the `Geburtsdatum` the age in years will be computed for these fields and stored in
`Alter_Feststellungsdatum`,`Alter_Dokumentationsdatum`,`Alter_Beginn_Einrichtungskontakt` 
8. **Write output**: the merged table initially contains `Date`, `PLZ`, `NUTS_CODE`, and `NUTS_NAME`.
   - The output file therefore contains `Diagnosis_Feststellungsdatum`, `Diagnose_Dokumentationsdatum`, `Beginn_Einrichtungskontakt`, `Sex`,`PLZ`, `NUTS_CODE`, `NUTS_NAME`, `Alter_Feststellungsdatum`, `Alter_Dokumentationsdatum` and `Alter_Beginn_Einrichtungskontakt`.
   - The rest of the naming behavior (default output path) remains the same
   - fianlly random ID gets assigned.

The script prints diagnostic messages showing the chosen precision, the top rows of the reduced PLZ GeoDataFrame and the mapping, and a summary count of matched rows.

### Precision effects

- **5 digits**: uses the original, finest-grained PLZ polygons.
- **4 digits**: all PLZ zones sharing the same first four digits are merged into a single geometry before matching. Useful when your input PLZs were truncated or when you want to map to postal districts rather than individual codes.
- **3 or 2 digits**: further aggregation yields very coarse postal areas. The same `reduce_plz_precision` logic dissolves geometries by the truncated prefix, which may create multipolygon shapes covering large regions.

The mapping to NUTS3 always occurs on the resulting geometries; hence, a coarser PLZ precision will generally result in fewer unique PLZ → NUTS3 assignments and more ties resolved by largest area.

> ⚠️ If your input CSV already contains truncated PLZs (e.g. only two digits), be sure to pass the matching length with `-l` so the script truncates and aggregates the reference geometries at the same level. Otherwise, the merge may fail to match any rows.

---

## Troubleshooting

- **Missing packages**: install with `pip install geopandas pandas`.
- **Wrong CRS errors**: ensure both source layers have valid coordinate reference systems; the script will reproject but will raise errors if CRS metadata is missing.
- **No matches**: verify that the `PLZ` column in your CSV has the expected number of digits and that you supplied the correct `-l` value.

---

## Summary

`link_plz_nuts3.py` provides a simple way to associate postal code data with NUTS3 regions, accommodating varying levels of postal code precision by truncating and dissolving polygon geometries. Use `generate_test_data.py` to create representative inputs and quickly test the linking behaviour at different PLZ lengths.