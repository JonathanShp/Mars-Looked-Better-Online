"""
make_question.py  -  The Question layer: "where can't orbit answer the science?"

Every 40 m cell gets 0 to 3 points, one per signal (MarsCuff playbook table):

  Signal (bit)            Rule                                     Dataset
  1  Rover never went     more than 500 m from Perseverance's path  Mars 2020 traverse (JPL MMGIS)
  2  Only coarse terrain  outside the 1 m HiRISE DTM footprint      USGS HiRISE DTM vs CTX DTM
  4  Geologic contact     within 100 m of a boundary between        Stack et al. 2020 map
                          two different bedrock units

We store WHICH signals are on (as bits: 1 + 2 + 4), so the app can say why a
cell scored what it did. Score = how many bits are on.

Honesty note: the contact signal can only be tested where Stack et al. mapped
(about a quarter of our grid). Outside that, contact = 0 and the app says
"unit not mapped" instead of pretending there is no contact.

Needs: web/data/grid.json, web/data/units.bin (make_geology.py),
       data/raw/M20_traverse.json, data/interim/hirise_footprint.npy
Output: web/data/question.bin (1 byte per cell) + web/data/question.json
"""

import json
import math

import numpy as np
from affine import Affine
from rasterio.features import rasterize
from scipy import ndimage
from shapely.geometry import LineString

R = 3396190.0
FAR_FROM_ROVER_M = 500      # playbook: "more than 500 m from the traverse"
CONTACT_M = 100             # playbook: "within 100 m of a boundary"


def main():
    g = json.load(open("web/data/grid.json"))
    rows, cols, cell = g["rows"], g["cols"], g["cell_size_m_projected"]
    b = g["bounds_m"]
    to_grid = Affine(cell, 0, b["west"], 0, -cell, b["north"])

    # Real ground size of a cell: east-west shrinks with cos(latitude).
    mid_lat = math.radians((g["bounds_deg"]["north"] + g["bounds_deg"]["south"]) / 2)
    dx, dy = cell * math.cos(mid_lat), cell

    # ---- Signal 1: far from the rover's path ----------------------------------
    trav = json.load(open("data/raw/M20_traverse.json"))
    lines = []
    for f in trav["features"]:
        pts = [(math.radians(p[0]) * R, math.radians(p[1]) * R) for p in f["geometry"]["coordinates"]]
        if len(set(pts)) >= 2:
            lines.append(LineString(pts))
    on_path = rasterize([(ln, 1) for ln in lines], out_shape=(rows, cols),
                        transform=to_grid, fill=0, all_touched=True, dtype="uint8")
    # Distance (metres) from every cell to the nearest path cell.
    dist_m = ndimage.distance_transform_edt(on_path == 0, sampling=(dy, dx))
    far = dist_m > FAR_FROM_ROVER_M

    # ---- Signal 2: outside the HiRISE 1 m terrain model -----------------------
    hirise = np.load("data/interim/hirise_footprint.npy")
    coarse_only = hirise == 0

    # ---- Signal 3: near a geologic contact ------------------------------------
    units = np.fromfile("web/data/units.bin", dtype=np.uint8).reshape(rows, cols)
    radius_cells = CONTACT_M / cell                          # 2.5 cells
    k = int(math.ceil(radius_cells))
    yy, xx = np.mgrid[-k:k + 1, -k:k + 1]
    disk = (yy * dy) ** 2 + (xx * dx) ** 2 <= CONTACT_M ** 2   # cells within 100 m
    biggest = ndimage.maximum_filter(units, footprint=disk, mode="nearest")
    # For the smallest, treat "not mapped" (0) as 255 so it never counts as a unit.
    smallest = ndimage.minimum_filter(np.where(units == 0, 255, units), footprint=disk,
                                      mode="nearest")
    contact = (units > 0) & (smallest != 255) & (biggest != smallest)

    bits = far * 1 + coarse_only * 2 + contact * 4
    bits.astype(np.uint8).tofile("web/data/question.bin")
    score = far.astype(int) + coarse_only + contact

    summary = {
        "bits": {"1": "Rover never went there (>500 m from Perseverance traverse)",
                 "2": "Only coarse terrain (outside HiRISE 1 m DTM; only 20 m CTX DTM)",
                 "4": "Geologic contact (within 100 m of a bedrock-unit boundary)"},
        "score_percent": {str(s): round(float((score == s).mean() * 100), 1) for s in range(4)},
        "signal_percent": {"far_from_rover": round(float(far.mean() * 100), 1),
                           "outside_hirise_dtm": round(float(coarse_only.mean() * 100), 1),
                           "near_contact": round(float(contact.mean() * 100), 1)},
        "sources": [
            "Mars 2020 traverse to sol 2022, NASA/JPL MMGIS (M20_traverse.json)",
            "USGS Mars 2020 TRN HiRISE DTM 1 m (JEZ_hirise_soc_006 ... blend40)",
            "Stack et al. 2020 photogeologic map, doi:10.1007/s11214-020-00739-x",
        ],
        "rules": "Team-written thresholds from the MarsCuff playbook: 500 m, outside footprint, 100 m.",
    }
    json.dump(summary, open("web/data/question.json", "w"), indent=2)
    print(json.dumps(summary["score_percent"]), json.dumps(summary["signal_percent"]))


if __name__ == "__main__":
    main()
