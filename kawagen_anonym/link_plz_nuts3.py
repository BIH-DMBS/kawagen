import geopandas as gpd
import pandas as pd
import argparse
import os
import numpy as np

# default paths
#base = r'c:\code\plz'
#plz_gpkg = base + r'\PLZ_Gebiete.gpkg'
#nuts3_shp = base + r'\extracted_shapefile\nuts250_12-31.gk3.shape\nuts250_1231\NUTS250_N3.shp'

plz_gpkg = r'PLZ_Gebiete.gpkg'
nuts3_shp = r'extracted_shapefile\nuts250_12-31.gk3.shape\nuts250_1231\NUTS250_N3.shp'

# command-line arguments will override test_csv and PLZ length

parser = argparse.ArgumentParser(
    description='Link a PLZ-based CSV to NUTS3 areas.')
parser.add_argument('input_csv', nargs='?', default=r'\test_data.csv',
                    help='path to csv file containing PLZ column')
parser.add_argument('-l', '--length', type=int, default=5,
                    help='number of leading digits of PLZ to use for matching (2-5)')
parser.add_argument('-o', '--output', default=None,
                    help='output csv path (default derives from input)')
args = parser.parse_args()

# python link_plz_nuts3.py test_data_plz2.csv -l 2 -o test_data_plz2_nuts3.csv

def reduce_plz_precision(gdf: gpd.GeoDataFrame, digits: int) -> gpd.GeoDataFrame:
    """
    Reduce PLZ precision and dissolve geometries with the same reduced PLZ.
    
    Parameters
    ----------
    gdf    : GeoDataFrame with at least 'PLZ' (str) and 'geometry' columns
    digits : target number of PLZ digits (5, 4, 3, or 2)
    
    Returns
    -------
    GeoDataFrame dissolved on the reduced PLZ
    """
    if digits not in (2, 3, 4, 5):
        raise ValueError("plz must be 2, 3, 4 or 5")

    result = gdf.copy()

    # Ensure PLZ is a zero-padded string (5 chars)
    result["plz"] = result["plz"].astype(str).str.zfill(5)

    # Truncate to desired precision
    result["plz"] = result["plz"].str[:digits]

    # Dissolve: union all geometries sharing the same reduced PLZ
    result = result.dissolve(by="plz", as_index=False)

    return result


input_csv = args.input_csv
plz_length = args.length

# read input CSV
df = pd.read_csv(input_csv, dtype={'plz': str})
if len(df['plz'][0])< plz_length:
    raise ValueError(f'PLZ in input CSV has length {len(df["plz"][0])}, but --length is set to {plz_length}')
df['plz'] = df['plz'].str[:plz_length]
print(df.head())
#plz_length = len(df['PLZ'][0])

if args.output:
    out_csv = args.output
else:
    # create output filename from input name
    stem = os.path.splitext(os.path.basename(input_csv))[0]
    out_csv = os.path.join(os.path.dirname(input_csv), f'{stem}_nuts3_linked.csv')

# validate length
if not (2 <= plz_length <= 5):
    raise ValueError('PLZ length must be between 2 and 5')

print('################')
print(plz_length)

gdf_plz = gpd.read_file(plz_gpkg)
reduced_gdf_plz = reduce_plz_precision(gdf_plz, digits=plz_length)

print(reduced_gdf_plz.head())

# read polygons
nuts3_gdf = gpd.read_file(nuts3_shp)


# ensure consistent CRS (use EPSG:3035 as in notebook template)
target_crs = 'EPSG:3035'
if reduced_gdf_plz.crs != target_crs:
    reduced_gdf_plz = reduced_gdf_plz.to_crs(target_crs)
if nuts3_gdf.crs != target_crs:
    nuts3_gdf = nuts3_gdf.to_crs(target_crs)


# function to assign each PLZ to the NUTS3 polygon with largest intersection area
def assign_nuts3_by_area(gdf_plz, gdf_nuts3):
    # compute intersection overlay
    overlay = gpd.overlay(gdf_plz[['plz','geometry','note']],
                          gdf_nuts3[['NUTS_CODE','NUTS_NAME','geometry']],
                          how='intersection')
    # compute area
    overlay['intersection_area'] = overlay.geometry.area
    # for each plz, pick the row with the largest area
    idx = overlay.groupby('plz')['intersection_area'].idxmax()
    best = overlay.loc[idx].copy()
    # keep only necessary columns
    return best[['plz','NUTS_CODE','NUTS_NAME','note']]

# create mapping
mapping = assign_nuts3_by_area(reduced_gdf_plz, nuts3_gdf)
print(mapping.head())

# merge with data
df_merged = df.merge(mapping, left_on='plz', right_on='plz', how='left')

print(df_merged.head())
# select and rename columns for output
      
df_out = df_merged[['Diagnosis_Feststellungsdatum',
                    'Diagnose_Dokumentationsdatum',
                    'Beginn_Einrichtungskontakt',
                    'Geburtsdatum',
                    'Sex',
                    'plz',
                    'NUTS_CODE',
                    'note',
                    'NUTS_NAME']]

# Alter in Jahren zum Diagnosis_Feststellungsdatum
parsed = pd.to_datetime(df_out["Geburtsdatum"], format="%Y-%m-%d")
df_out["Alter_Feststellungsdatum"] = ((pd.to_datetime(df_out["Diagnosis_Feststellungsdatum"], format="%Y-%m-%d") - parsed).dt.days / 365.25).astype(int)
df_out["Alter_Dokumentationsdatum"] = ((pd.to_datetime(df_out["Diagnose_Dokumentationsdatum"], format="%Y-%m-%d") - parsed).dt.days / 365.25).astype(int)
df_out["Alter_Beginn_Einrichtungskontakt"] = ((pd.to_datetime(df_out["Beginn_Einrichtungskontakt"], format="%Y-%m-%d") - parsed).dt.days / 365.25).astype(int)
# drop original birthdate column
df_out = df_out.drop(columns=['Geburtsdatum'])

# cover data to year and calendar week format (e.g. 2020_05 for 5th week of 2020)
parsed = pd.to_datetime(df_out["Diagnosis_Feststellungsdatum"], format="%Y-%m-%d")
df_out["Diagnosis_Feststellungsdatum"] = parsed.dt.year.astype(str) + '_' + parsed.dt.isocalendar().week.astype(str).str.zfill(2)
parsed = pd.to_datetime(df_out["Diagnose_Dokumentationsdatum"], format="%Y-%m-%d")
df_out["Diagnose_Dokumentationsdatum"] = parsed.dt.year.astype(str) + '_' + parsed.dt.isocalendar().week.astype(str).str.zfill(2)
parsed = pd.to_datetime(df_out["Beginn_Einrichtungskontakt"], format="%Y-%m-%d")
df_out["Beginn_Einrichtungskontakt"] = parsed.dt.year.astype(str) + '_' + parsed.dt.isocalendar().week.astype(str).str.zfill(2)

# assign random ID
df_out['unique_id'] = np.random.randint(10**11, 10**12, size=len(df), dtype=np.int64)

# drop columns not needed for output
df_out = df_out.drop(columns=['plz', 'note'])

df_out.to_csv(out_csv, index=False)

print(f'created {out_csv} with {len(df_out)} rows ({df_out["NUTS_CODE"].notna().sum()} matched to NUTS3)')