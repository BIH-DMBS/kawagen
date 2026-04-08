### Anleitung anonymisierungsskript `link_plz_nuts3.py` für das kawagen project
 
- (1) create virtual environment and install dependicies using requirements.txt
- (1) go to folder '/kawagen_anonym/'
- (2) unzip 'nuts250_12-31.gk3.shape.zip' to folder named '/extracted_shapefile'
- (3) create files for testing
  - python generate_test_data.py
  - check test files
  - run test: *python link_plz_nuts3.py test_data_plz4.csv -l 3 -o result_test_data_plz3_nuts3.csv*
  - check manual.md for more details
- (4) use test files as templates to create the real data, the input table should look similar to this depending on the plz precision

 PLZ | Diagnosis_Feststellungsdatum | Diagnose_Dokumentationsdatum | Beginn_Einrichtungskontakt | Geburtsdatum | Sex |
 |-----|-------------------------------|-------------------------------|-----------------------------|--------------|-----|
 | 61  | 2007-11-10                    | 2004-09-03                    | 2011-05-23                  | 2006-09-24   | F   |
 | 94  | 2003-11-27                    | 2018-03-22                    | 2018-09-01                  | 1994-06-02   | M   |
 | 46  | 2017-09-08                    | 2008-07-18                    | 2012-11-05                  | 2003-12-19   | M   |


- (5) link plz to nuts3



