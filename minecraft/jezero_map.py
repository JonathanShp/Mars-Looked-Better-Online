"""Shared Mars <-> Minecraft coordinates for the whole Jezero map.

TRUE SCALE: 1 block = 1 m of Mars, sideways AND up. The player is 1.8 blocks tall,
so walking in the world feels exactly like walking on Mars in a suit.

THE WHOLE MAP, NOT A BOX
------------------------
The NASA elevation grid is 756 x 798 cells of 40 m, which is about 30 km x 30 km.
At 1 m per block that is ~916 million block columns: a 60 GB world if we built all
of it. So we DON'T build a box. `make_world.py` builds only a corridor around the
route the user planned on the website (see CORRIDOR_RADIUS_M there). These functions
work anywhere on the map; nothing here limits how far you can go.

Block (0, 0) is Perseverance's landing site, so the habitat sits near the origin
and coordinates stay small and readable. +X is east, +Z is south (Minecraft's own
axes), which matches the grid's columns (west->east) and rows (north->south).

HEIGHT
------
Minecraft worlds are only 384 blocks tall (y -64 .. 319) but the whole map has
1195 m of relief, so no single world can hold the entire map at true vertical
scale. Instead each world gets its OWN vertical anchor: `set_elevation_base(m)`
says which Mars elevation sits at y = Y_BASE. `make_world.py` picks it from the
lowest ground in the corridor and stores it in the save, so every route added to
that save lines up.
"""

import array
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "web", "data")
WEB = os.path.join(HERE, "..", "web")
# The Minecraft server lives OUTSIDE OneDrive (OneDrive locks world files while syncing).
SERVER_DIR = os.path.join(os.path.expanduser("~"), "MarsCuffMinecraft", "server")

M_PER_BLOCK = 1.0  # 1 block = 1 m, sideways and up
Y_BASE = -56       # the lowest ground we build sits at this y (room for caves/basement below)
Y_MAX = 319        # Minecraft's build limit
USABLE_HEIGHT = Y_MAX - Y_BASE - 8   # relief a single world can hold, with headroom

META = json.load(open(os.path.join(DATA, "grid.json")))
ROWS, COLS = META["rows"], META["cols"]
B = META["bounds_deg"]
LAT_MID = (B["north"] + B["south"]) / 2
# One degree of longitude is shorter than one of latitude, by cos(latitude).
DX_CELL = META["cell_size_m_projected"] * math.cos(math.radians(LAT_MID))
DZ_CELL = META["cell_size_m_projected"]

MAP_WIDTH_M = COLS * DX_CELL
MAP_HEIGHT_M = ROWS * DZ_CELL


def load_elevation():
    """The whole elevation grid, metres, row 0 = north."""
    a = array.array("h")
    with open(os.path.join(DATA, "grid.bin"), "rb") as f:
        a.fromfile(f, ROWS * COLS)
    return a


def landing_site():
    """Perseverance's landing site = first point of the earliest-sol traverse."""
    gj = json.load(open(os.path.join(DATA, "traverse.geojson")))
    best = None
    for feat in gj["features"]:
        sol = feat["properties"].get("sol_start", feat["properties"].get("sol", 0)) or 0
        if best is None or sol < best[0]:
            coords = feat["geometry"]["coordinates"]
            while isinstance(coords[0], list):
                coords = coords[0]
            best = (sol, coords)
    lon, lat = best[1][0], best[1][1]
    return lat, lon


def metres_of_latlon(lat, lon):
    """Metres east and south of the grid's north-west corner."""
    col_f = (lon - B["west"]) / (B["east"] - B["west"]) * COLS
    row_f = (B["north"] - lat) / (B["north"] - B["south"]) * ROWS
    return col_f * DX_CELL, row_f * DZ_CELL


# Block (0, 0) = the landing site, so x/z are metres east/south of Perseverance.
E0, S0 = metres_of_latlon(*landing_site())


def cell_coords(x, z):
    """Block -> fractional grid cell (col, row). Works anywhere on the map."""
    col_f = (E0 + (x + 0.5) * M_PER_BLOCK) / DX_CELL
    row_f = (S0 + (z + 0.5) * M_PER_BLOCK) / DZ_CELL
    return col_f, row_f


def block_of_metres(e, s):
    return (int(math.floor((e - E0) / M_PER_BLOCK)), int(math.floor((s - S0) / M_PER_BLOCK)))


def block_of_cell(row, col):
    """Centre of grid cell (row, col) -> block (x, z)."""
    return block_of_metres((col + 0.5) * DX_CELL, (row + 0.5) * DZ_CELL)


def block_of_latlon(lat, lon):
    return block_of_metres(*metres_of_latlon(lat, lon))


def latlon_of_block(x, z):
    col_f, row_f = cell_coords(x, z)
    lon = B["west"] + col_f / COLS * (B["east"] - B["west"])
    lat = B["north"] - row_f / ROWS * (B["north"] - B["south"])
    return lat, lon


def on_map(x, z, margin_m=0.0):
    """Is this block inside the NASA elevation grid? (Outside it we have no data.)"""
    e = E0 + x * M_PER_BLOCK
    s = S0 + z * M_PER_BLOCK
    return margin_m <= e <= MAP_WIDTH_M - margin_m and margin_m <= s <= MAP_HEIGHT_M - margin_m


# ---------------------------------------------------------------- height anchor

_ELEV = None            # the grid, loaded on first use
ELEV_BASE_M = None      # the Mars elevation that sits at y = Y_BASE


def set_elevation_base(elev_m):
    """Pin this Mars elevation (metres) to y = Y_BASE for the rest of this run."""
    global ELEV_BASE_M
    ELEV_BASE_M = float(elev_m)
    return ELEV_BASE_M


def elevation_at(x, z):
    """Bilinear Mars elevation (metres) at a block, same maths as make_world.columns()."""
    global _ELEV
    if _ELEV is None:
        _ELEV = load_elevation()
    col_f, row_f = cell_coords(x, z)
    u = min(max(col_f - 0.5, 0.0), COLS - 1.0)
    v = min(max(row_f - 0.5, 0.0), ROWS - 1.0)
    c0 = min(int(u), COLS - 2)
    r0 = min(int(v), ROWS - 2)
    tu, tv = u - c0, v - r0
    e00 = _ELEV[r0 * COLS + c0]
    e01 = _ELEV[r0 * COLS + c0 + 1]
    e10 = _ELEV[(r0 + 1) * COLS + c0]
    e11 = _ELEV[(r0 + 1) * COLS + c0 + 1]
    top = e00 * (1 - tu) + e01 * tu
    bot = e10 * (1 - tu) + e11 * tu
    return top * (1 - tv) + bot * tv


def y_of_elevation(elev_m):
    if ELEV_BASE_M is None:
        raise RuntimeError("call set_elevation_base() first (it is per world)")
    return Y_BASE + int(math.floor((elev_m - ELEV_BASE_M) / M_PER_BLOCK + 0.5))


def ground_y(x, z):
    """Surface block y at a block column."""
    return y_of_elevation(elevation_at(x, z))


def describe():
    """What the website shows about the Minecraft side."""
    return {
        "scale": "1 block = %g m of Mars, sideways and up" % M_PER_BLOCK,
        "map_size_m": [round(MAP_WIDTH_M), round(MAP_HEIGHT_M)],
        "map_size_cells": [COLS, ROWS],
        "cell_size_m": META["cell_size_m_projected"],
        "origin": "block 0,0 = Perseverance's landing site",
        "axes": "+x east, +z south",
        "y_base": Y_BASE,
        "usable_height_m": USABLE_HEIGHT,
        "elevation_range_m": META["elevation_range_m"],
        "bounds_deg": B,
        "source": META["source"],
    }


if __name__ == "__main__":
    print(json.dumps(describe(), indent=2))
