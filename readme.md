### Anleitung anonymisierungsskript `link_plz_nuts3.py` für das kawagen project
 
- (1) create virtual environment and install dependicies using requirements.txt
- (1) go to folder '/kawagen_anonym/'
- (2) unzip 'nuts250_12-31.gk3.shape.zip' to folder named '/extracted_shapefile'
- (3) create files for testing
  - python generate_test_data.py
  - check test files
  - run test: *python link_plz_nuts3.py test_data_plz4.csv -l 3 -o result_test_data_plz3_nuts3.csv*
  - check manual.md for more details
- (4) use test files as templates to create the real data
- (5) link plz to nuts



