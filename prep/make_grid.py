"""
make_grid.py  -  MarsCuff data prep (milestone M0)

What it does, in plain words:
  1. Opens the USGS Mars 2020 TRN CTX elevation model of Jezero Crater
     (20 m per pixel, made from MRO CTX stereo images tied to MGS MOLA).
  2. Works out the slope (how steep the ground is, in degrees) at every pixel.
  3. Shrinks the grid from 20 m to 40 m cells so the browser can route on it fast.
       - elevation of a 40 m cell = AVERAGE of its 4 small pixels
       - slope of a 40 m cell     = STEEPEST of its 4 small pixels
         (we round toward caution: a steep patch can never be averaged away)
       - if ANY of the 4 pixels has no data, the whole cell is "no data"
         (unknown ground is never shown as safe)
  4. Saves two small files the web app loads:
       web/data/grid.bin   - the numbers (16-bit integers, see grid.json)
       web/data/grid.json  - size, position on Mars, units, and the data source

Run it from the project folder:
    python prep/make_grid.py
"""

import json
import math
import os

import numpy as np
import rasterio

# ---- Input file (downloaded from USGS Astrogeology) -------------------------
DTM_FILE = "data/raw/JEZ_ctx_B_soc_008_DTM_MOLAtopography_DeltaGeoid_20m_Eqc_latTs0_lon0.tif"
DTM_URL = ("https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/"
           "JEZ_ctx_B_soc_008_DTM_MOLAtopography_DeltaGeoid_20m_Eqc_latTs0_lon0.tif")

OUT_DIR = "web/data"
BLOCK = 2            # 2 x 2 pixels of 20 m  ->  one 40 m cell
NODATA_OUT = -32768  # the "no data" marker we write into grid.bin


def load_dtm(path):
    """Read the elevation grid. Returns (elevation array with NaN for no-data, file info)."""
    with rasterio.open(path) as src:
        elev = src.read(1).astype(np.float64)
        # Mark the file's own "no data" value (and any absurd value) as NaN.
        if src.nodata is not None:
            elev[elev == src.nodata] = np.nan
        elev[(elev < -10000) | (elev > 30000)] = np.nan   # Mars is -8 km to +22 km
        info = {
            "transform": src.transform,
            "width": src.width,
            "height": src.height,
            "res_m": src.res[0],
            # Mars sphere radius used by this map projection (from the file's CRS)
            "radius_m": src.crs.to_dict().get("R", 3396190.0) if src.crs else 3396190.0,
        }
    return elev, info


def compute_slope_degrees(elev, info):
    """
    Slope at each pixel, in degrees.

    Map projection note (important for honest numbers): this DTM uses an
    "equirectangular" projection whose true scale is at the EQUATOR. Jezero is
    at about 18.5 deg N, so one pixel's EAST-WEST width on the ground is
    20 m x cos(latitude) (about 19.0 m), while NORTH-SOUTH it really is 20 m.
    We use the real ground distances so slopes are not under-estimated.
    """
    res = info["res_m"]
    R = 3396190.0
    t = info["transform"]
    # Latitude of the centre of every row (y in metres -> latitude in degrees).
    rows = np.arange(info["height"])
    y_centres = t.f + (rows + 0.5) * t.e          # t.e is negative (rows go south)
    lat_rad = y_centres / R                       # equirectangular: y = R * lat
    dx_ground = res * np.cos(lat_rad)             # east-west metres per pixel, per row
    dy_ground = res                               # north-south metres per pixel

    # np.gradient = "rise over run" between neighbouring pixels.
    d_rows, d_cols = np.gradient(elev)            # change in metres per pixel step
    dz_dx = d_cols / dx_ground[:, None]           # metres up per metre east
    dz_dy = d_rows / dy_ground                    # metres up per metre south
    rise_over_run = np.sqrt(dz_dx ** 2 + dz_dy ** 2)   # Pythagoras
    return np.degrees(np.arctan(rise_over_run))        # turn the ratio into an angle


def shrink(grid, how):
    """Combine each 2x2 block into one cell. how = 'mean' or 'max'. NaN anywhere -> NaN."""
    h = (grid.shape[0] // BLOCK) * BLOCK
    w = (grid.shape[1] // BLOCK) * BLOCK
    blocks = grid[:h, :w].reshape(h // BLOCK, BLOCK, w // BLOCK, BLOCK)
    # np.mean / np.max return NaN if any pixel in the block is NaN - that is what we want.
    return blocks.mean(axis=(1, 3)) if how == "mean" else blocks.max(axis=(1, 3))


def main():
    elev, info = load_dtm(DTM_FILE)
    slope = compute_slope_degrees(elev, info)

    elev40 = shrink(elev, "mean")
    slope40 = shrink(slope, "max")
    rows, cols = elev40.shape

    # Pack as 16-bit integers: elevation in whole metres, slope in tenths of a degree.
    elev_i16 = np.where(np.isnan(elev40), NODATA_OUT, np.round(elev40)).astype("<i2")
    slope_i16 = np.where(np.isnan(slope40), NODATA_OUT, np.round(slope40 * 10)).astype("<i2")

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "grid.bin"), "wb") as f:
        f.write(elev_i16.tobytes())   # first block: elevation, row by row from the north
        f.write(slope_i16.tobytes())  # second block: slope x 10, same order

    # Where the grid sits on Mars, in degrees (equirectangular: lon = x / R, lat = y / R).
    t = info["transform"]
    R = 3396190.0
    cell_m = info["res_m"] * BLOCK
    west_m, north_m = t.c, t.f
    east_m = west_m + cols * cell_m
    south_m = north_m - rows * cell_m
    to_deg = lambda m: math.degrees(m / R)

    meta = {
        "rows": rows,
        "cols": cols,
        "cell_size_m_projected": cell_m,
        "bounds_deg": {"west": to_deg(west_m), "east": to_deg(east_m),
                       "south": to_deg(south_m), "north": to_deg(north_m)},
        "bounds_m": {"west": west_m, "east": east_m, "south": south_m, "north": north_m},
        "mars_radius_m": R,
        "layout": "int16 little-endian; first rows*cols = elevation (m), "
                  "next rows*cols = slope (tenths of a degree); row 0 = north",
        "nodata": NODATA_OUT,
        "elevation_range_m": [float(np.nanmin(elev40)), float(np.nanmax(elev40))],
        "nodata_cells": int(np.isnan(elev40).sum()),
        "method": "Slope from 20 m pixels (central differences, true ground spacing "
                  "with cos(latitude)); 40 m cell = mean elevation, MAX slope of 2x2 block.",
        "source": {
            "name": "Mars 2020 Terrain Relative Navigation CTX DTM mosaic (20 m/px)",
            "mission": "MRO CTX (stereo), tied to MGS MOLA",
            "publisher": "USGS Astrogeology Science Center",
            "url": DTM_URL,
        },
    }
    with open(os.path.join(OUT_DIR, "grid.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print(f"Wrote {rows} x {cols} grid ({rows * cols:,} cells of 40 m)")
    print(f"Elevation {meta['elevation_range_m'][0]:.0f} to {meta['elevation_range_m'][1]:.0f} m, "
          f"no-data cells: {meta['nodata_cells']}")
    print(f"Slope: median {np.nanmedian(slope40):.1f} deg, "
          f"{(slope40 > 15).mean() * 100:.1f}% of cells above 15 deg")


if __name__ == "__main__":
    main()
