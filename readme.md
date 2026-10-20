# PLZ → NUTS3 Linkage

This guide explains how to run `link_plz_nuts3.py`, which assigns German postal code (PLZ) areas in pseudonymised FHIR clinical records to NUTS3 regional boundaries. For a step-by-step walkthrough of every processing stage — including intermediate outputs and design rationale — refer to the companion notebook [test_data_merge.ipynb](https://github.com/BIH-DMBS/kawagen/blob/master/kawagen_anonym/test_data_merge.ipynb).

---

## Quick start (step by step)

You need Python 3.10 or newer and Git. Run the following commands in a terminal (Windows: PowerShell or cmd).

```shell
# 1. Download the repository
git clone https://github.com/BIH-DMBS/kawagen.git

# 2. Change into the script folder
cd kawagen
cd kawagen_anonym

# 3. Create a virtual Python environment (only once)
python -m venv myvenv

# 4. Activate the environment
#    Windows:
myvenv\Scripts\activate
#    Linux / macOS:
#    source myvenv/bin/activate

# 5. Install the required packages (only once)
pip install -r requirements.txt
```

**6. Provide the input data** — either

- **copy** the three CSV files from the FDPG into the folder `kawagen_anonym/input_data/`, **or**
- **set the path** to the folder containing the files in [`config.ini`](kawagen_anonym/config.ini) (`input_dir = ...`).

The expected file names are the ones delivered by the FDPG:

```
MII PR Person Patient (Pseudonymisiert).csv
MII PR Diagnose Condition.csv
MII PR Fall Kontakt mit einer Gesundheitseinrichtung.csv
```

If your files are named differently, adjust the file names in `config.ini`.

```shell
# 7. Run the script
python link_plz_nuts3.py
```

The result is written to `kawagen_anonym/result.csv`.

When running the script again later, only steps 2, 4 and 7 are needed.

---

## Configuration (`config.ini`)

All paths are set in [`kawagen_anonym/config.ini`](kawagen_anonym/config.ini). Relative paths are resolved relative to the `kawagen_anonym` folder, absolute paths (e.g. `C:\Daten\FDPG`) are used as given.

```ini
[input]
input_dir = input_data
patient_file = MII PR Person Patient (Pseudonymisiert).csv
diagnose_file = MII PR Diagnose Condition.csv
kontakt_file = MII PR Fall Kontakt mit einer Gesundheitseinrichtung.csv

[output]
result_file = result.csv
```

The geodata files `PLZ_Gebiete.gpkg` and `nuts250_12-31.gk3.shape.zip` are part of the repository and need no configuration. The NUTS3 shapefile is extracted from the ZIP archive automatically on the first run.

Input data and `result.csv` are excluded from Git via `.gitignore`, so patient data cannot be committed by accident.

---

## What the script does

The pipeline runs in eleven steps. The notebook [test_data_merge.ipynb](kawagen_anonym/test_data_merge.ipynb) contains the same pipeline with annotated code and sample outputs for each step.

**Steps 1–5 — Load and merge clinical data.** The three FHIR CSV files are read, normalised and merged into a single dataset. FHIR reference prefixes such as `Patient/` and `Encounter/` are stripped so that IDs can be joined directly. Original patient IDs are replaced with a numeric surrogate key. All date columns are parsed to a uniform, timezone-naive format (full ISO-8601 timestamps, date-only, year-month and year-only strings are supported).

**Steps 6–7 — Load and reproject geodata.** The PLZ polygons and the NUTS3 boundaries are loaded and reprojected to EPSG:3035 (ETRS89-LAEA Europe), a metric equal-area projection suitable for area comparisons.

**Step 8 — Spatial join PLZ → NUTS3.** Each PLZ zone is assigned to the NUTS3 region that covers the largest part of its area. This works for all PLZ digit lengths present in the data (2–5 digits), see *PLZ precision* below.

**Step 9 — Age computation.** The patient's age in full years is calculated at encounter start (`Encounter.period.start`), condition documentation date (`Condition.recordedDate`) and diagnosis confirmation date (`Feststellungsdatum`; `Condition.extension:Feststellungsdatum`).

**Step 10 — Date anonymisation.** Exact dates are replaced with ISO calendar-week strings `YYYY_WW` (e.g. `2023_04`). Missing dates become empty strings.

**Step 11 — Remove identifying columns and save.** Birth date and PLZ are dropped, the table is written without a row index.

---

## Output file

`result.csv` contains one row per diagnosis record:

| Column | Type | Description |
|---|---|---|
| `id` | int | Surrogate patient identifier |
| `Patient_gender` | str | Gender as recorded in FHIR |
| `Encounter_period_start` | str | Encounter start, as `YYYY_WW` |
| `Condition_recordedDate` | str | Condition documentation date, as `YYYY_WW` |
| `Feststellungsdatum` | str | Diagnosis confirmation date, as `YYYY_WW` |
| `NUTS_CODE` | str | NUTS3 region code (e.g. `DE300`) |
| `NUTS_NAME` | str | NUTS3 region name (e.g. `Berlin`) |
| `age_encounter_start` | Int64 | Age in years at encounter start |
| `age_recordedDate` | Int64 | Age in years at condition documentation |
| `age_Feststellungsdatum` | Int64 | Age in years at diagnosis confirmation |

Rows with a missing date or birth date show `NA` in the corresponding age column.

---

## PLZ precision

The script detects the digit length of the PLZ values automatically. If a PLZ has fewer than five digits, the 5-digit reference polygons are merged to the same length before the spatial join.

| PLZ digits | Behaviour |
|---|---|
| 5 | Original PLZ polygons are used directly |
| 4 | PLZ zones sharing the first four digits are merged |
| 3 | Merged to three-digit postal districts |
| 2 | Very coarse; a zone may span several NUTS3 regions |

Mixed lengths in one dataset are handled in a single run. A warning is printed for lengths outside 2–5.

---

## Console output

A successful run prints something like:

```
  Building NUTS3 mapping for 3-digit PLZ...
  Building NUTS3 mapping for 5-digit PLZ...
Matched 28 / 29 rows to NUTS3
Saving result...
Done. 29 rows written to ...\kawagen_anonym\result.csv
```

An unmatched row (empty NUTS3 columns) usually means a PLZ that does not exist in `PLZ_Gebiete.gpkg`, e.g. a malformed code or a location outside Germany.

---

## Troubleshooting

**`Input file not found: ...`** — The CSV files are not in the input folder or are named differently. Check `input_dir` and the file names in `config.ini`.

**`ModuleNotFoundError`** — The virtual environment is not active or the packages are not installed. Repeat steps 4 and 5.

**`myvenv\Scripts\activate` is blocked in PowerShell** — Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or use cmd instead.

**No NUTS3 matches** — Check that the PLZ column in the patient file keeps leading zeros and has the expected number of digits.
