# Data sources and attribution

Actual scientific inputs are downloaded from **NASA FIRMS**, with original bytes, retrieval metadata and SHA-256 hashes retained under `data/raw`, `data/manifests` and the warehouse manifest.

- [FIRMS annual country downloads](https://firms.modaps.eosdis.nasa.gov/country/): the official [file index](https://firms.modaps.eosdis.nasa.gov/data/country/yearly_summary_files.txt) drives availability rather than assumed URLs.
- [Annual product attribute README](https://firms.modaps.eosdis.nasa.gov/data/country/AttributesReadme.txt): processing version distinguishes standard and NRT. Files contain individual hotspot records, despite the site's “yearly summaries” label.
- Example [Portugal MODIS 2024 CSV](https://firms.modaps.eosdis.nasa.gov/data/country/modis/2024/modis_2024_Portugal.csv) and [Portugal S-NPP 2024 CSV](https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp/2024/viirs-snpp_2024_Portugal.csv).
- [FIRMS area API contract](https://firms.modaps.eosdis.nasa.gov/api/area/): MAP_KEY authentication, supported sources, UTC dates and bounded request windows. Keys are not persisted in request provenance or errors.
- [FIRMS archive](https://firms.modaps.eosdis.nasa.gov/download/) and [NASA FIRMS information/disclaimer](https://www.earthdata.nasa.gov/data/tools/firms).

Pilot acquisition: 26 annual MODIS and 14 annual S-NPP Portugal files, plus four of each for Uruguay. S-NPP files before 2012 are absent in the official index and are not fabricated. Live global MODIS, NOAA-20 and NOAA-21 feeds are separate NRT inputs. A current S-NPP feed returned only its header; that empty result was preserved.

Use NASA's requested source acknowledgment: data distributed through the Fire Information for Resource Management System (FIRMS), part of NASA's Earth Science Data and Information System. The application is not NASA-endorsed. NASA's data disclaimer remains applicable.

The bundled low-resolution world geography is from [Natural Earth](https://www.naturalearthdata.com/about/terms-of-use/), public-domain cartographic data, acquired from the [Natural Earth vector repository](https://github.com/nvkelso/natural-earth-vector). It is a display basemap, not the analytical country mask or fire truth. Country names in these data do not imply a position on boundaries or sovereignty.

React, Leaflet, FastAPI, DuckDB, H3 and the other dependencies retain their own licenses. `package-lock.json` and `requirements.lock.txt` record the installed dependency versions. NASA data are separate from source-code licensing.
