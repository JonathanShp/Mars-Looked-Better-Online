"""
check_point.py  -  M0 check: does the web app show the same numbers as the GeoTIFF?

Usage (from the project folder):
    python prep/check_point.py 77.45 18.44

It goes straight back to the ORIGINAL USGS file (not our grid), finds the
2 x 2 block of 20 m pixels that makes up the 40 m cell at that spot, and prints:
  - the 4 raw elevations and their average (should match "Elevation" in the app)
  - the steepest slope among those 4 pixels (should match "Slope" in the app)

The slope here is computed with a separate, simple method (each pixel vs. its
neighbours, one at a time) so it is an independent check of make_grid.py.
"""

import math
import sys

import rasterio

DTM_FILE = "data/raw/JEZ_ctx_B_soc_008_DTM_MOLAtopography_DeltaGeoid_20m_Eqc_latTs0_lon0.tif"
R = 3396190.0   # Mars sphere radius used by the map projection (metres)


def pixel_slope(elev, r, c, dx, dy):
    """Slope in degrees at pixel (r, c) using its 4 neighbours (one-sided at the edge)."""
    h, w = elev.shape
    left, right = max(c - 1, 0), min(c + 1, w - 1)
    up, down = max(r - 1, 0), min(r + 1, h - 1)
    dz_dx = (elev[r, right] - elev[r, left]) / ((right - left) * dx)
    dz_dy = (elev[down, c] - elev[up, c]) / ((down - up) * dy)
    return math.degrees(math.atan(math.hypot(dz_dx, dz_dy)))


def main():
    lon, lat = float(sys.argv[1]), float(sys.argv[2])
    x = math.radians(lon) * R      # equirectangular: x = R * longitude (radians)
    y = math.radians(lat) * R
    with rasterio.open(DTM_FILE) as src:
        elev = src.read(1).astype(float)
        row, col = src.index(x, y)          # which 20 m pixel is this?
        res = src.res[0]
        t = src.transform

    # The 40 m cell starts at the even pixel at or before this one.
    r0, c0 = (row // 2) * 2, (col // 2) * 2
    print(f"lon {lon}, lat {lat}  ->  20 m pixel (row {row}, col {col}), "
          f"40 m cell (row {r0 // 2}, col {c0 // 2})")

    values, slopes = [], []
    for r in (r0, r0 + 1):
        lat_row = math.degrees((t.f + (r + 0.5) * t.e) / R)
        dx = res * math.cos(math.radians(lat_row))   # true east-west ground spacing
        for c in (c0, c0 + 1):
            values.append(elev[r, c])
            slopes.append(pixel_slope(elev, r, c, dx, res))
    print("raw elevations (m):", ", ".join(f"{v:.1f}" for v in values))
    print(f"Elevation (mean of 4)  = {sum(values) / 4:.0f} m")
    print(f"Slope (steepest of 4)  = {max(slopes):.1f} deg")


if __name__ == "__main__":
    main()
