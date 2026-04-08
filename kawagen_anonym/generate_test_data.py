import csv
import random
import datetime
from datetime import timedelta
import geopandas as gpd
import os


def random_date(start, end):
    """Return a random date between start and end (inclusive)."""
    delta = end - start
    int_delta = delta.days
    random_day = random.randrange(int_delta + 1)
    return start + timedelta(days=random_day)


# load postal codes from the geopackage; assume column 'plz' contains numeric codes
plz_gpkg = r'PLZ_Gebiete.gpkg'
gdf = gpd.read_file(plz_gpkg)
# some entries might be strings already, ensure they are zero-padded 5-digit strings
valid_plzs = gdf['plz'].astype(str).str.zfill(5).unique().tolist()

start = datetime.date(2000, 1, 1)
end = datetime.date(2025, 12, 31)

start_birth = datetime.date(1990, 1, 1)
end_birth = datetime.date(2020, 12, 31)

with open(r'test_data.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['plz', 'Diagnosis_Feststellungsdatum','Diagnose_Dokumentationsdatum','Beginn_Einrichtungskontakt','Geburtsdatum','Sex'])
    for _ in range(1000):
        plz = random.choice(valid_plzs)
        d1 = random_date(start, end)
        d2 = random_date(start, end)
        d3 = random_date(start, end)
        birth_date = random_date(start_birth, end_birth)
        sex = random.choice(['M', 'F'])
        writer.writerow([plz, d1, d2, d3, birth_date, sex])

print(f'done, wrote 1000 rows using {len(valid_plzs)} distinct PLZ values')


def create_prefix_variants(input_csv):
    """Read a CSV with a 'PLZ' column and write versions truncated to
    prefixes of length 4,3,2.

    The output files will be named test_data_plz4.csv, test_data_plz3.csv,
    test_data_plz2.csv in the given directory.
    """
    import pandas as pd
    df = pd.read_csv(input_csv, dtype={'plz': str})
    df['plz'] = df['plz'].str.zfill(5)
    for length in (4,3,2):
        out = df.copy()
        out['plz'] = out['plz'].str[:length]
        fname = os.path.join(f'test_data_plz{length}.csv')
        out.to_csv(fname, index=False)
        print(f'written {fname} ({len(out)} rows)')


if __name__ == '__main__':
    # when invoked directly, also create prefix variants
    create_prefix_variants(r'test_data.csv')
