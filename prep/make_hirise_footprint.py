"""
make_hirise_footprint.py  -  Where does the 1 m HiRISE terrain model exist?

Used by the Question layer, signal "Only coarse terrain": a cell OUTSIDE the
HiRISE DTM footprint only has 20 m CTX elevation, so boulders and small scarps
there are unknown until an astronaut looks.

The HiRISE DTM (USGS Mars 2020 TRN, 1 m/px) is 1.8 GB. We do NOT download it.
Instead GDAL reads just ONE row of pixels for each row of our 40 m grid, over
the internet (HTTP range requests), and checks the pixel at each cell centre:
  has a real elevation  ->  1 (inside the HiRISE footprint)
  "no data" value       ->  0 (outside)

Output: data/interim/hirise_footprint.npy  (same rows x cols as web/data/grid.json)
Takes a few minutes. Run from the project folder:
    python prep/make_hirise_footprint.py
"""

import json
import os

import numpy as np
import rasterio
from rasterio.windows import Window

HIRISE_URL = ("https://planetarymaps.usgs.gov/mosaic/mars2020_trn/HiRISE/"
              "JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40.tif")


def main():
    meta = json.load(open("web/data/grid.json"))
    rows, cols, cell = meta["rows"], meta["cols"], meta["cell_size_m_projected"]
    west, north = meta["bounds_m"]["west"], meta["bounds_m"]["north"]

    footprint = np.zeros((rows, cols), dtype=np.uint8)
    with rasterio.open("/vsicurl/" + HIRISE_URL) as src:
        nodata = src.nodata
        for r in range(rows):
            y = north - (r + 0.5) * cell                    # centre of this grid row (metres)
            if not (src.bounds.bottom < y < src.bounds.top):
                continue                                    # row is outside HiRISE: stays 0
            hr_row, _ = src.index(src.bounds.left + 0.5, y)
            line = src.read(1, window=Window(0, hr_row, src.width, 1))[0]
            for c in range(cols):
                x = west + (c + 0.5) * cell                 # centre of this grid cell
                if not (src.bounds.left < x < src.bounds.right):
                    continue
                _, hr_col = src.index(x, y)
                v = line[hr_col]
                if v != nodata and -10000 < v < 30000:      # a real elevation value
                    footprint[r, c] = 1
            if r % 50 == 0:
                print(f"row {r}/{rows}", flush=True)

    os.makedirs("data/interim", exist_ok=True)
    np.save("data/interim/hirise_footprint.npy", footprint)
    print(f"Inside HiRISE DTM footprint: {footprint.mean() * 100:.1f}% of cells")


if __name__ == "__main__":
    main()
