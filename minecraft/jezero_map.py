# jezero_map.py - how the real Jezero Crater maps onto Minecraft blocks.
#
# Used by BOTH make_world.py (builds the terrain) and bridge.py (puts the route
# arrows on it), so they always agree on where everything is.
#
# The rule is simple and TRUE TO SCALE:
#   1 Minecraft block = 1 m of Mars, sideways AND up (the Minecraft player is
#   1.8 blocks tall = a 1.8 m astronaut).
#   +X = east, +Z = south (that is how Minecraft's compass works).
# At 1 m per block the whole 30 km elevation grid would be a 60 GB world, so we
# build a 10 km x 10 km square centred on Perseverance's landing site. That
# square is the "Minecraft area" the website outlines on its map.
# Ground height comes from the same USGS CTX elevation grid the website uses
# (web/data/grid.bin, 40 m cells), smoothed between cells (bilinear).

import json
import math
import os
from array import array

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "web", "data")
WEB = os.path.join(HERE, "..", "web")
# The Minecraft server lives OUTSIDE OneDrive (OneDrive locks world files while syncing).
SERVER_DIR = os.path.join(os.path.expanduser("~"), "MarsCuffMinecraft", "server")

M_PER_BLOCK = 1.0           # 1 block = 1 m, sideways and up
AREA_M = 10000              # the Minecraft area is 10 km x 10 km
Y_BASE = -44                # the lowest ground in the area sits at this y

META = json.load(open(os.path.join(DATA, "grid.json")))
ROWS, COLS = META["rows"], META["cols"]
B = META["bounds_deg"]
LAT_MID = (B["north"] + B["south"]) / 2
# A 40 m "projected" cell is 40 m north-south but only 40 x cos(latitude) east-west.
DX_CELL = META["cell_size_m_projected"] * math.cos(math.radians(LAT_MID))
DZ_CELL = META["cell_size_m_projected"]

# World size in blocks (whole 16-block chunks), centred near x = 0, z = 0.
WIDTH = HEIGHT = int(AREA_M / M_PER_BLOCK) // 16 * 16
X_MIN = Z_MIN = -(WIDTH // 32) * 16


def load_elevation():
    """Elevation grid (metres) as a flat list, row 0 = north."""
    a = array("h")
    with open(os.path.join(DATA, "grid.bin"), "rb") as f:
        a.frombytes(f.read(ROWS * COLS * 2))
    return a


def landing_site():
    """Perseverance landing site = first point of the earliest traverse segment (MMGIS data)."""
    t = json.load(open(os.path.join(DATA, "traverse.geojson")))
    first = min(t["features"], key=lambda f: f["properties"].get("sol", 1e9))
    coords = first["geometry"]["coordinates"]
    if first["geometry"]["type"] == "MultiLineString":
        coords = coords[0]
    lon, lat = coords[0][:2]
    return lat, lon


def metres_of_latlon(lat, lon):
    """Lat/lon -> metres east of the grid's west edge, metres south of its north edge."""
    col_f = (lon - B["west"]) / (B["east"] - B["west"]) * COLS
    row_f = (B["north"] - lat) / (B["north"] - B["south"]) * ROWS
    return col_f * DX_CELL, row_f * DZ_CELL


# Where the Minecraft area starts, in metres from the grid's west / north edges:
# the landing site lands at about block 0, 0 (kept inside the elevation grid).
_ls_e, _ls_s = metres_of_latlon(*landing_site())
E0 = min(max(_ls_e + X_MIN * M_PER_BLOCK, 0.0), COLS * DX_CELL - WIDTH * M_PER_BLOCK)
S0 = min(max(_ls_s + Z_MIN * M_PER_BLOCK, 0.0), ROWS * DZ_CELL - HEIGHT * M_PER_BLOCK)


def cell_coords(x, z):
    """Block x,z -> fractional grid position (col_f, row_f). Cell c covers [c, c+1)."""
    col_f = (E0 + (x - X_MIN + 0.5) * M_PER_BLOCK) / DX_CELL
    row_f = (S0 + (z - Z_MIN + 0.5) * M_PER_BLOCK) / DZ_CELL
    return col_f, row_f


def _area_min_elevation():
    elev = load_elevation()
    c0, c1 = int(E0 / DX_CELL), min(COLS, int((E0 + WIDTH * M_PER_BLOCK) / DX_CELL) + 2)
    r0, r1 = int(S0 / DZ_CELL), min(ROWS, int((S0 + HEIGHT * M_PER_BLOCK) / DZ_CELL) + 2)
    return min(elev[r * COLS + c] for r in range(r0, r1) for c in range(c0, c1))


ELEV_BASE_M = float(_area_min_elevation())     # this elevation sits at Y_BASE


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


def block_of_metres(e, s):
    return (X_MIN + math.floor((e - E0) / M_PER_BLOCK), Z_MIN + math.floor((s - S0) / M_PER_BLOCK))


def block_of_cell(row, col):
    """Website grid cell (row, col) -> block x,z at the cell's centre."""
    return block_of_metres((col + 0.5) * DX_CELL, (row + 0.5) * DZ_CELL)


def block_of_latlon(lat, lon):
    """Latitude/longitude (degrees) -> block x,z."""
    return block_of_metres(*metres_of_latlon(lat, lon))


def inside(x, z, margin=0):
    """Is block x,z inside the Minecraft area?"""
    return (X_MIN + margin <= x < X_MIN + WIDTH - margin) and (Z_MIN + margin <= z < Z_MIN + HEIGHT - margin)


def area_bounds_deg():
    """The Minecraft area as latitude/longitude, for the website's outline."""
    lon = lambda e: B["west"] + e / DX_CELL / COLS * (B["east"] - B["west"])
    lat = lambda s: B["north"] - s / DZ_CELL / ROWS * (B["north"] - B["south"])
    return {"west": lon(E0), "east": lon(E0 + WIDTH * M_PER_BLOCK),
            "north": lat(S0), "south": lat(S0 + HEIGHT * M_PER_BLOCK)}


def describe():
    return {
        "scale": "1 block = 1 m of Mars, sideways and up (true scale, no exaggeration)",
        "area": f"{WIDTH * M_PER_BLOCK / 1000:.0f} km x {HEIGHT * M_PER_BLOCK / 1000:.0f} km around Perseverance's landing site",
        "x_min": X_MIN, "z_min": Z_MIN, "width": WIDTH, "height": HEIGHT,
        "y_base": Y_BASE, "elev_base_m": ELEV_BASE_M, "bounds_deg": area_bounds_deg(),
        "axes": "+X = east, +Z = south",
        "source": META["source"]["name"],
    }


if __name__ == "__main__":
    print(json.dumps(describe(), indent=1))
    lat, lon = landing_site()
    x, z = block_of_latlon(lat, lon)
    print("landing site", lat, lon, "-> block", x, z, "ground y", ground_y(load_elevation(), x, z))
