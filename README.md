# India Rail Route Map

Interactive map of the Indian Railways network. Search any train by name or number to draw its route in its own colour, search stations to see which trains stop there, and switch between a street map and satellite imagery. A track speed view colours each section by the fastest scheduled train.

**Live map:** https://deepdesai003.github.io/india-rail-map/

## How it is built

On every push to `main`, the GitHub Actions workflow in `.github/workflows/pages.yml`:

1. downloads the [DataMeet Indian Railways dataset](https://github.com/datameet/railways),
2. runs `scripts/build_data.py` to produce the map's data files (network, trains, stops, station index, speed estimates),
3. adds `web/index.html` and Leaflet, and publishes the result to GitHub Pages.

## Data and limits

- Trains, stations and timetables come from the DataMeet dataset (2016). Timetables may have changed since.
- Route lines join consecutive stops in straight lines, so curves are simplified.
- Track speeds are estimates from timetables (fastest scheduled train between stops), not official sectional speed limits.
- Map tiles: © OpenStreetMap contributors, © CARTO. Satellite imagery: © Esri, Maxar, Earthstar Geographics.
