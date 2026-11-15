# MarsCuff — the Apollo cuff checklist, rebuilt for Mars

NASA Space Apps 2026 · Challenge: *Interplanetary Survival Guide: Martian Map* · Started Nov 14, 2026

MarsCuff is a layered map of Jezero Crater. It sends astronauts where orbiters can't answer the
science, plans a safe Marswalk from four NASA missions' data, and prints the astronaut's wrist
checklist.

## Run it

```bash
python -m http.server 8765 --directory web
```
Then open http://localhost:8765. Click **1 · Habitat**, click the map, then click 2–5 stations.
Click a station pin to see its card: which rock, why go there, what to do.
**Preview cuff** shows the pages; **Print cuff** prints them on 3 × 5 inch paper.
**▶ Demo** plays the whole story by itself in about 29 s (used for the video, see `docs/video-script.md`).
Works on phones too (panels fold; tap the map for the readout).

## Rebuild the data (only needed if you change the prep scripts)

```bash
pip install rasterio numpy scipy shapely pyogrio
python prep/make_grid.py              # elevation + slope grid (M0)
python prep/check_point.py 77.45 18.44   # M0 check against the original GeoTIFF
python prep/make_geology.py           # Stack et al. 2020 units
python prep/make_traverse.py          # Perseverance path
python prep/make_hirise_footprint.py  # reads the remote HiRISE DTM row by row (a few minutes)
python prep/make_question.py          # Question layer
```
Raw downloads go in `data/raw/` (see the sources below).

## NASA data used (four missions: MGS, MRO, Mars 2020, + MSL planned for weather)

| Dataset | Mission / instrument | Used for | Source |
|---|---|---|---|
| Mars 2020 TRN CTX DTM mosaic, 20 m/px | MRO CTX, tied to MGS MOLA | Elevation, slope, routing, cuff map | [USGS Astrogeology](https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/JEZ_ctx_B_soc_008_DTM_MOLAtopography_DeltaGeoid_20m_Eqc_latTs0_lon0.tif) |
| Mars 2020 TRN HiRISE DTM mosaic, 1 m/px (footprint only) | MRO HiRISE | Question layer "only coarse terrain" | [USGS Astrogeology](https://planetarymaps.usgs.gov/mosaic/mars2020_trn/HiRISE/) |
| Jezero CTX ortho-mosaic 6 m, HiRISE ortho-mosaic 25 cm | MRO CTX / HiRISE | Basemap layers | NASA Mars Trek tiles |
| MOLA colour hillshade 463 m | MGS MOLA | Basemap layer | NASA Mars Trek tiles |
| Photogeologic map of the Perseverance field site (CC BY 4.0) | Mars 2020 Science Team | Geologic units, contacts, science tasks | Stack et al. 2020, *Space Sci. Rev.* 216:127, [doi:10.1007/s11214-020-00739-x](https://doi.org/10.1007/s11214-020-00739-x) (ESM 3 shapefile) |
| Perseverance traverse to sol 2022 | Mars 2020 | Rover path layer, "never driven" flag, Question layer | NASA/JPL MMGIS `M20_traverse.json` |

## Models and assumptions (shown in the app next to every modelled number)

- **Walking speed:** Tobler's hiking function × 0.6 suit penalty (team assumption).
- **Slope limits:** caution > 8°, blocked > 15° (team assumptions). No-data cells are blocked.
- **EVA budget:** 8 h (NASA Human Mars surface concept of operations) with 20% reserve (team assumption).
- **Station work time:** 30 min (team assumption).
- **Point of No Return:** first point on the route where elapsed time + walking time straight home > budget − reserve.
- **Slope grid:** computed from 20 m pixels using true ground spacing (east–west × cos latitude); a 40 m cell keeps the *steepest* of its 4 pixels, so we round toward caution.
- **Question score (0–3), the purple "science glow":** one point each for > 500 m from the rover path;
  outside the HiRISE 1 m DTM; < 100 m from a bedrock-unit contact. It glows **only where Stack et al. 2020
  mapped the rocks**: outside that map we don't know the rock type, so we don't claim science there.
  (In practice the top score is 2: the rock map lies almost entirely inside the HiRISE 1 m DTM.)
- **Shaded relief layer:** drawn by MarsCuff from the CTX DTM, used when Mars Trek tiles can't load.
- **Science value:** Question score + 1 for a unit not yet visited on this walk.
- We model **time, not litres of oxygen**: an O2 figure for a Mars suit that doesn't exist yet would be invented.

## Software
Leaflet 1.9.4 (BSD-2), rasterio, numpy, scipy, shapely, pyogrio (Python). AI tool: Claude (Anthropic) helped write and debug code.
