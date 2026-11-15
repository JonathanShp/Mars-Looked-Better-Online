# jezero_map.py - how the real Jezero Crater maps onto Minecraft blocks.
#
# Used by BOTH make_world.py (builds the terrain) and bridge.py (puts the route
# arrows on it), so they always agree on where everything is.
#
# The rule is simple and TRUE TO SCALE:
#   1 Minecraft block = 10 m of Mars, sideways AND up.
#   +X = east, +Z = south (that is how Minecraft's compass works), row 0 = north.
# Ground height comes from the same USGS CTX elevation grid the website uses
# (web/data/grid.bin, 40 m cells), smoothed between cells (bilinear) so the
# ground has no 4-block steps.

import json
import math
import os
from array import array

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "web", "data")
WEB = os.path.join(HERE, "..", "web")
# The Minecraft server lives OUTSIDE OneDrive (OneDrive locks world files while syncing).
SERVER_DIR = os.path.join(os.path.expanduser("~"), "MarsCuffMinecraft", "server")

M_PER_BLOCK = 10.0          # 1 block = 10 m (both sideways and up)
ELEV_BASE_M = -2720.0       # this elevation sits at Y_BASE ...
Y_BASE = -50                # ... so the crater floor is near y -49 and the rim near y 70

META = json.load(open(os.path.join(DATA, "grid.json")))
ROWS, COLS = META["rows"], META["cols"]
B = META["bounds_deg"]
LAT_MID = (B["north"] + B["south"]) / 2
# A 40 m "projected" cell is 40 m north-south but only 40 x cos(latitude) east-west.
DX_CELL = META["cell_size_m_projected"] * math.cos(math.radians(LAT_MID))
DZ_CELL = META["cell_size_m_projected"]

# World size in blocks, rounded down to whole 16-block chunks.
WIDTH = int(COLS * DX_CELL / M_PER_BLOCK) // 16 * 16
HEIGHT = int(ROWS * DZ_CELL / M_PER_BLOCK) // 16 * 16
X_MIN = -(WIDTH // 32) * 16       # chunk-aligned, map roughly centred on 0,0
Z_MIN = -(HEIGHT // 32) * 16


def load_elevation():
    """Elevation grid (metres) as a flat list, row 0 = north."""
    a = array("h")
    with open(os.path.join(DATA, "grid.bin"), "rb") as f:
        a.frombytes(f.read(ROWS * COLS * 2))
    return a


def cell_coords(x, z):
    """Block x,z -> fractional grid position (col_f, row_f). Cell c covers [c, c+1)."""
    col_f = (x - X_MIN + 0.5) * M_PER_BLOCK / DX_CELL
    row_f = (z - Z_MIN + 0.5) * M_PER_BLOCK / DZ_CELL
    return col_f, row_f


def y_of_elevation(elev_m):
    """Metres -> block y (rounded). Same formula as the numpy version in make_world.py."""
    return Y_BASE + math.floor((elev_m - ELEV_BASE_M) / M_PER_BLOCK + 0.5)


def ground_y(elev, x, z):
    """Top solid block y at block column x,z (pure Python, for the bridge)."""
    col_f, row_f = cell_coords(x, z)
    u = min(max(col_f - 0.5, 0.0), COLS - 1.0)
    v = min(max(row_f - 0.5, 0.0), ROWS - 1.0)
    c0, r0 = min(int(u), COLS - 2), min(int(v), ROWS - 2)
    tu, tv = u - c0, v - r0
    e00 = elev[r0 * COLS + c0]
    e01 = elev[r0 * COLS + c0 + 1]
    e10 = elev[(r0 + 1) * COLS + c0]
    e11 = elev[(r0 + 1) * COLS + c0 + 1]
    top = e00 * (1 - tu) + e01 * tu
    bot = e10 * (1 - tu) + e11 * tu
    return y_of_elevation(top * (1 - tv) + bot * tv)


def block_of_cell(row, col):
    """Website grid cell (row, col) -> block x,z at the cell's centre."""
    x = X_MIN + math.floor((col + 0.5) * DX_CELL / M_PER_BLOCK)
    z = Z_MIN + math.floor((row + 0.5) * DZ_CELL / M_PER_BLOCK)
    return x, z


def block_of_latlon(lat, lon):
    """Latitude/longitude (degrees) -> block x,z."""
    col_f = (lon - B["west"]) / (B["east"] - B["west"]) * COLS
    row_f = (B["north"] - lat) / (B["north"] - B["south"]) * ROWS
    return (X_MIN + math.floor(col_f * DX_CELL / M_PER_BLOCK),
            Z_MIN + math.floor(row_f * DZ_CELL / M_PER_BLOCK))


def landing_site():
    """Perseverance landing site = first point of the earliest traverse segment (MMGIS data)."""
    t = json.load(open(os.path.join(DATA, "traverse.geojson")))
    def sol(f):
        p = f.get("properties", {})
        for k in ("sol", "Sol", "SOL", "startSol", "fromSol"):
            if k in p and p[k] is not None:
                return float(p[k])
        return 1e9
    first = min(t["features"], key=sol)
    coords = first["geometry"]["coordinates"]
    if first["geometry"]["type"] == "MultiLineString":
        coords = coords[0]
    lon, lat = coords[0][:2]
    return lat, lon


def describe():
    return {
        "scale": "1 block = 10 m of Mars, sideways and up (true scale, no exaggeration)",
        "x_min": X_MIN, "z_min": Z_MIN, "width": WIDTH, "height": HEIGHT,
        "y_base": Y_BASE, "elev_base_m": ELEV_BASE_M,
        "axes": "+X = east, +Z = south",
        "source": META["source"]["name"],
    }


if __name__ == "__main__":
    print(json.dumps(describe(), indent=1))
    lat, lon = landing_site()
    x, z = block_of_latlon(lat, lon)
    print("landing site", lat, lon, "-> block", x, z, "ground y", ground_y(load_elevation(), x, z))
