# make_world.py - builds a Minecraft world of Jezero Crater from the SAME NASA
# data the website uses, but ONLY along the walk the user planned.
#
# Why a corridor and not a big square: the full CTX map is 30 x 30 km. Writing
# all of it is ~14 GB and most of it is ground nobody will ever walk on. So we
# take the planned route, draw a 500 m band either side of it (800 m around the
# habitat and each station), and build only the chunks that fall in that band.
# A typical 8 km EVA comes out around 30 region files instead of 400.
#
# Three ways to run it:
#   python minecraft/make_world.py --route plan.json --save "<game dir>/saves/MarsCuff Jezero"
#       terrain for that route, written into an existing CLOSED save (this is what the bridge does)
#   python minecraft/make_world.py --route plan.json --zip "MarsCuff-Jezero.zip"
#       a finished world folder zipped up, with HOW-TO-USE.txt inside, to hand to someone
#   python minecraft/make_world.py
#       no route: a 1.5 km demo disc around Perseverance's landing site
#
# What the terrain is made of (true scale: 1 block = 1 m, see jezero_map.py):
#   * ground height  : USGS CTX DTM (web/data/grid.bin), smoothed between 40 m cells,
#                      plus the procedural detail in surface.py (the DTM has nothing
#                      finer than 40 m, so without it the ground is glassy smooth)
#   * surface rock   : bedrock unit from Stack et al. 2020 (web/data/units.bin)
#   * loose rocks    : boulder field density per unit (surface.py)
#   * rover tracks   : Perseverance traverse (web/data/traverse.geojson)
#   * Mars sky       : a data pack makes the sky butterscotch, no rain, no mobs
#
# How a Minecraft world file works (short version): the world is cut into
# 16x16 "chunks"; 32x32 chunks are stored in one ".mca" region file; each chunk
# is a small tree of named values ("NBT"), zipped. We write those files directly.
# That can only be done while the world is CLOSED.

import argparse
import io
import json
import math
import os
import struct
import sys
import time
import zipfile
import zlib

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jezero_map as jm
import surface
from surface import BLOCKS, ID, LAYER_STRIPES

OUT = os.path.join(jm.SERVER_DIR, "world")
REGION = os.path.join(OUT, "region")        # where the .mca files go (see region_dir)
DATA_VERSION = 3955          # Minecraft 1.21.1
PACK_FORMAT = 121            # data pack format for Minecraft 26.3
                             # (SharedConstants.DATA_PACK_FORMAT_MAJOR). Packs past
                             # format 81 must say min_format/max_format.

CORRIDOR_RADIUS_M = 500.0    # how far either side of the walking line we build
STATION_RADIUS_M = 800.0     # a wider bubble around the habitat, each station and the PNR
DEMO_RADIUS_M = 1500.0       # no route given: a disc this big around the landing site
SAMPLE_STEP_M = 60.0         # the route line is sampled this often before drawing discs
STEEP_TENTHS = 150           # 15.0 deg = the website's "blocked" slope
MARKER = "marscuff_terrain.json"   # records which route a save was built for


# ---------------------------------------------------------------- 1. block columns for one piece of the map
_G = {}         # NASA grids, loaded once per worker process
_TRACKS = None  # rover-track block positions, shared with every worker


def _grids():
    if not _G:
        n = jm.ROWS * jm.COLS
        raw = np.fromfile(os.path.join(jm.DATA, "grid.bin"), dtype="<i2", count=2 * n)
        _G["elev"] = raw[:n].reshape(jm.ROWS, jm.COLS).astype(np.float64)
        _G["slope"] = raw[n:].reshape(jm.ROWS, jm.COLS).astype(np.float64) / 10.0
        _G["units"] = np.fromfile(os.path.join(jm.DATA, "units.bin"),
                                  dtype=np.uint8).reshape(jm.ROWS, jm.COLS)
    return _G


def grid_at(xs, zs):
    """NASA elevation (smoothed), slope in degrees and unit id for a block grid."""
    g = _grids()
    col_f, row_f = jm.cell_coords(np.asarray(xs, dtype=np.float64),
                                  np.asarray(zs, dtype=np.float64))

    # Bilinear smoothing between cell centres (same order of operations as jm.elevation_at).
    u = np.clip(col_f - 0.5, 0.0, jm.COLS - 1.0)
    v = np.clip(row_f - 0.5, 0.0, jm.ROWS - 1.0)
    c0 = np.minimum(u.astype(int), jm.COLS - 2); tu = u - c0
    r0 = np.minimum(v.astype(int), jm.ROWS - 2); tv = v - r0
    elev = g["elev"]
    e00 = elev[np.ix_(r0, c0)]; e01 = elev[np.ix_(r0, c0 + 1)]
    e10 = elev[np.ix_(r0 + 1, c0)]; e11 = elev[np.ix_(r0 + 1, c0 + 1)]
    upper = e00 * (1 - tu) + e01 * tu
    lower = e10 * (1 - tu) + e11 * tu
    e = upper * (1 - tv[:, None]) + lower * tv[:, None]

    # Nearest cell for slope + geology (no smoothing: a unit is a unit).
    ci = np.minimum(col_f.astype(int), jm.COLS - 1)
    ri = np.minimum(row_f.astype(int), jm.ROWS - 1)
    return e, g["slope"][np.ix_(ri, ci)], g["units"][np.ix_(ri, ci)]


def columns(x0, z0, w, h, tracks=None):
    """For each block column in [x0, x0+w) x [z0, z0+h):
    ground y, surface block, block just under it, boulder block (0 = none), layered flag."""
    xs = np.arange(x0, x0 + w)
    zs = np.arange(z0, z0 + h)
    e, slope, unit = grid_at(xs, zs)
    e, top, under, boulder, layered = surface.detail(xs, zs, e, slope, unit)

    ground = (jm.Y_BASE + np.floor((e - jm.ELEV_BASE_M) / jm.M_PER_BLOCK + 0.5)).astype(np.int16)
    # Keep everything inside the world: nothing below bedrock, nothing above the build limit.
    ground = np.clip(ground, jm.Y_BASE - 8, jm.Y_MAX - 4).astype(np.int16)

    if tracks is not None and len(tracks):
        sel = (tracks[:, 0] >= x0) & (tracks[:, 0] < x0 + w) & \
              (tracks[:, 1] >= z0) & (tracks[:, 1] < z0 + h)
        tz = tracks[sel, 1] - z0
        tx = tracks[sel, 0] - x0
        top[tz, tx] = ID["packed_mud"]      # the wheels pressed the dust flat
        boulder[tz, tx] = 0                 # and crushed the small rocks
    return ground, top, under, boulder, layered


# ---------------------------------------------------------------- 2. the corridor
def route_points(plan):
    """Centres of the discs that make up the corridor: (x, z, radius_m).

    plan is the JSON the website posts (see web/js/minecraft.js): a path of
    [row, col, clockSeconds] grid cells, plus the habitat, stations and the PNR.
    """
    pts = []

    def add(row, col, radius):
        x, z = jm.block_of_cell(row, col)
        pts.append((float(x), float(z), float(radius)))

    path = plan.get("path") or []
    cells = [(p[0], p[1]) for p in path]
    if len(cells) >= 2:
        # Walk the line and drop a disc every SAMPLE_STEP_M, so bends stay covered.
        blocks = [jm.block_of_cell(r, c) for r, c in cells]
        carry = SAMPLE_STEP_M      # always place one at the very start
        for (x0, z0), (x1, z1) in zip(blocks, blocks[1:]):
            seg = math.hypot(x1 - x0, z1 - z0)
            if seg < 1e-6:
                continue
            while carry <= seg:
                t = carry / seg
                pts.append((x0 + (x1 - x0) * t, z0 + (z1 - z0) * t, CORRIDOR_RADIUS_M))
                carry += SAMPLE_STEP_M
            carry -= seg
        pts.append((float(blocks[-1][0]), float(blocks[-1][1]), CORRIDOR_RADIUS_M))
    elif len(cells) == 1:
        add(cells[0][0], cells[0][1], STATION_RADIUS_M)

    hab = plan.get("habitat")
    if hab:
        add(hab["row"], hab["col"], STATION_RADIUS_M)
    for st in plan.get("stations") or []:
        add(st["row"], st["col"], STATION_RADIUS_M)
    pnr = plan.get("pnr")
    if pnr:
        add(pnr["row"], pnr["col"], STATION_RADIUS_M)

    if not pts:
        return demo_points()
    return pts


def demo_points():
    """No route: one disc around the landing site, so there is something to walk in."""
    return [(0.0, 0.0, DEMO_RADIUS_M)]


def corridor_chunks(points):
    """Chunk coordinates (cx, cz) whose centre falls inside any of the discs."""
    keep = set()
    for x, z, radius in points:
        reach = radius + 12.0        # a chunk centre can be ~11.3 m from its nearest corner
        cx0 = int(math.floor((x - reach) / 16.0)); cx1 = int(math.ceil((x + reach) / 16.0))
        cz0 = int(math.floor((z - reach) / 16.0)); cz1 = int(math.ceil((z + reach) / 16.0))
        cxs = np.arange(cx0, cx1 + 1)
        czs = np.arange(cz0, cz1 + 1)
        # Chunk centre in blocks, then distance to this disc centre.
        dx = cxs * 16.0 + 8.0 - x
        dz = czs * 16.0 + 8.0 - z
        hit = (dx[None, :] ** 2 + dz[:, None] ** 2) <= reach ** 2
        for iz, ix in zip(*np.nonzero(hit)):
            cx, cz = int(cxs[ix]), int(czs[iz])
            # Outside the NASA grid we have no data, so do not build there.
            if jm.on_map(cx * 16 + 8, cz * 16 + 8, margin_m=12.0):
                keep.add((cx, cz))
    return sorted(keep)


def corridor_bounds(chunks):
    """Block box [x_min, z_min, x_max, z_max] that holds every chunk we build."""
    cx = [c[0] for c in chunks]; cz = [c[1] for c in chunks]
    return [min(cx) * 16, min(cz) * 16, max(cx) * 16 + 15, max(cz) * 16 + 15]


def corridor_relief(chunks):
    """Lowest and highest NASA elevation (metres) in the corridor, sampled at chunk centres."""
    xs = np.array([c[0] * 16 + 8 for c in chunks], dtype=np.float64)
    zs = np.array([c[1] * 16 + 8 for c in chunks], dtype=np.float64)
    g = _grids()
    col_f, row_f = jm.cell_coords(xs, zs)
    ci = np.minimum(col_f.astype(int), jm.COLS - 1)
    ri = np.minimum(row_f.astype(int), jm.ROWS - 1)
    e = g["elev"][ri, ci]
    return float(e.min()), float(e.max())


def rover_track_blocks(chunks, width=3):
    """Block positions of the Perseverance traverse that fall inside the corridor."""
    want = set(chunks)
    t = json.load(open(os.path.join(jm.DATA, "traverse.geojson")))
    centres = []
    for f in t["features"]:
        g = f["geometry"]
        lines = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
        for line in lines:
            pts = [jm.block_of_latlon(lat, lon) for lon, lat, *_ in line]
            for (x0, z0), (x1, z1) in zip(pts, pts[1:]):
                steps = max(abs(x1 - x0), abs(z1 - z0), 1)
                if steps > 4000:          # a jump across the map: not a real drive segment
                    continue
                s = np.arange(steps + 1)
                centres.append(np.stack([np.round(x0 + (x1 - x0) * s / steps),
                                         np.round(z0 + (z1 - z0) * s / steps)], 1).astype(np.int32))
    if not centres:
        return np.zeros((0, 2), np.int32)
    c = np.concatenate(centres)
    r = range(-(width // 2), width - width // 2)
    off = np.array([(dx, dz) for dx in r for dz in r], np.int32)
    pts = np.unique((c[:, None, :] + off[None]).reshape(-1, 2), axis=0)
    # Keep only the track blocks in chunks we are actually writing.
    in_corridor = np.array([((int(x) >> 4), (int(z) >> 4)) in want for x, z in pts], dtype=bool)
    return pts[in_corridor]


# ---------------------------------------------------------------- 2b. route markers
# A world handed to someone who has no mod has no arrows, beams or book, so the
# route has to be IN the ground: glowing pillars at the habitat, the stations and
# the Point of No Return, and a line of glowstone on the ground to follow.
MARK_PATH = ("glowstone", 1)            # one block on the ground, every path point
MARK_HABITAT = ("white_concrete", 40)   # tallest, visible from a long way off
MARK_STATION = ("purple_concrete", 30)
MARK_PNR = ("red_concrete", 30)

def route_marker_blocks(plan, chunks):
    """{(x, z): (block id, how many blocks tall)} for the markers inside the corridor.

    A pillar is a glowstone core (so it glows at night) wearing a coloured shell,
    which is how you tell a station from home from a distance.
    """
    if not plan:
        return {}
    want = set(chunks)
    marks = {}

    def put(x, z, name, height):
        if ((int(x) >> 4), (int(z) >> 4)) in want:
            marks[(int(x), int(z))] = (ID[name], height)

    for p in plan.get("path") or []:
        x, z = jm.block_of_cell(p[0], p[1])
        put(x, z, *MARK_PATH)

    def pillar(cell, shell_height, shell):
        x, z = jm.block_of_cell(cell["row"], cell["col"])
        put(x, z, "glowstone", shell_height + 6)        # core, sticking out of the top
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            put(x + dx, z + dz, shell, shell_height)

    hab = plan.get("habitat")
    if hab:
        pillar(hab, MARK_HABITAT[1], MARK_HABITAT[0])
    for st in plan.get("stations") or []:
        pillar(st, MARK_STATION[1], MARK_STATION[0])
    pnr = plan.get("pnr")
    if pnr:
        pillar(pnr, MARK_PNR[1], MARK_PNR[0])
    return marks


# ---------------------------------------------------------------- 3. tiny NBT writer
# Each value is written as (tag type, value). Only the types a chunk needs.
def _str(s):
    b = s.encode("utf-8")
    return struct.pack(">H", len(b)) + b

def nbt_payload(t, v):
    if t == "byte":   return struct.pack(">b", v)
    if t == "int":    return struct.pack(">i", v)
    if t == "long":   return struct.pack(">q", v)
    if t == "string": return _str(v)
    if t == "long_array":
        return struct.pack(">i", len(v)) + v.astype(">i8").tobytes()
    if t == "list":
        item_type, items = v
        if not items:
            return bytes([0]) + struct.pack(">i", 0)
        return bytes([TAG_ID[item_type]]) + struct.pack(">i", len(items)) + \
            b"".join(nbt_payload(item_type, i) for i in items)
    if t == "compound":
        out = b""
        for name, (ct, cv) in v.items():
            out += bytes([TAG_ID[ct]]) + _str(name) + nbt_payload(ct, cv)
        return out + b"\x00"
    raise ValueError(t)

TAG_ID = {"byte": 1, "int": 3, "long": 4, "string": 8, "list": 9, "compound": 10, "long_array": 12}

def nbt_root(compound):
    return bytes([10]) + _str("") + nbt_payload("compound", compound)


# ---------------------------------------------------------------- 4. one chunk
def pack_indices(idx, bits):
    """Pack 4096 palette indices into 64-bit longs (Minecraft 1.16+ layout: no index spans two longs)."""
    per = 64 // bits
    n = -(-4096 // per)
    padded = np.zeros(n * per, dtype=np.uint64)
    padded[:4096] = idx
    shifts = (np.arange(per, dtype=np.uint64) * np.uint64(bits))
    longs = (padded.reshape(n, per) << shifts).sum(axis=1, dtype=np.uint64)
    return longs.view(np.int64)

DESERT = ("compound", {"palette": ("list", ("string", ["minecraft:desert"]))})

def chunk_nbt(cx, cz, ground, top_block, under, boulder, layered, marks=None):
    """All arguments except cx/cz and marks are 16x16 arrays [z, x] for this chunk.

    marks: {(local x, local z): (block id, height)} route pillars to stand on the
    ground here (see route_marker_blocks).
    """
    tallest = max([h for _b, h in (marks or {}).values()] or [0])
    max_y = int(ground.max()) + 1 + tallest                           # +1 leaves room for boulders
    ys = np.arange(-64, (max_y // 16 + 1) * 16)[:, None, None]        # y, z, x
    depth = ground[None] - ys                                         # 0 = surface block, -1 = just above
    blocks = np.full(depth.shape, ID["smooth_basalt"], dtype=np.uint8)

    # Broken rock under the surface, then strata in the layered units, then the surface itself.
    shallow = (depth >= 1) & (depth <= 3)
    blocks[shallow] = np.broadcast_to(under[None], depth.shape)[shallow]
    stripe = np.array([ID[s] for s in LAYER_STRIPES], dtype=np.uint8)[(ys % 4).repeat(16, 1).repeat(16, 2)]
    lay = layered[None] & (depth >= 1) & (depth <= 12)
    blocks[lay] = stripe[lay]
    blocks[depth == 0] = np.broadcast_to(top_block[None], depth.shape)[depth == 0]

    # Loose rocks sitting ON the ground (one block up), then air above everything.
    blocks[depth < 0] = ID["air"]
    rocks = (depth == -1) & (np.broadcast_to(boulder[None], depth.shape) > 0)
    blocks[rocks] = np.broadcast_to(boulder[None], depth.shape)[rocks]
    blocks[ys[:, 0, 0] == -64] = ID["bedrock"]

    # Route markers last, so nothing else overwrites them.
    for (lx, lz), (block_id, height) in (marks or {}).items():
        y0 = int(ground[lz, lx]) + 1
        blocks[y0 + 64:y0 + 64 + height, lz, lx] = block_id

    sections = []
    deep_below = int(ground.min()) - 13          # every block at or below this y is plain deep rock
    for s in range(blocks.shape[0] // 16):
        y0 = -64 + s * 16
        if y0 > -64 and y0 + 15 <= deep_below:   # fast path: the whole section is one block type
            sections.append({"Y": ("byte", s - 4), "block_states": ("compound", {"palette": ("list", (
                "compound", [{"Name": ("string", "minecraft:smooth_basalt")}]))}), "biomes": DESERT})
            continue
        sec = blocks[s * 16:(s + 1) * 16].reshape(-1)                  # index = y*256 + z*16 + x
        pal, inv = np.unique(sec, return_inverse=True)
        bs = {"palette": ("list", ("compound",
                                   [{"Name": ("string", "minecraft:" + BLOCKS[p])} for p in pal]))}
        if len(pal) > 1:
            bits = max(4, math.ceil(math.log2(len(pal))))
            bs["data"] = ("long_array", pack_indices(inv.astype(np.uint64), bits))
        sections.append({"Y": ("byte", s - 4), "block_states": ("compound", bs), "biomes": DESERT})
    # Empty air sections up to the build limit are left out: Minecraft treats them as air.

    return nbt_root({
        "DataVersion": ("int", DATA_VERSION),
        "xPos": ("int", cx), "zPos": ("int", cz), "yPos": ("int", -4),
        "Status": ("string", "minecraft:full"),
        "LastUpdate": ("long", 0), "InhabitedTime": ("long", 0),
        "isLightOn": ("byte", 0),                 # 0 = "please work out the lighting yourself"
        "sections": ("list", ("compound", sections)),
        "block_entities": ("list", ("compound", [])),
        "structures": ("compound", {"starts": ("compound", {}), "References": ("compound", {})}),
    })


# ---------------------------------------------------------------- 5. region files
def write_region(path, chunks):
    """chunks: {(local_x, local_z): nbt_bytes}. Region file = 8 KB table + 4 KB sectors."""
    locations = bytearray(4096)
    stamps = bytearray(4096)
    body = io.BytesIO()
    sector = 2
    now = int(time.time())
    for (lx, lz), raw in chunks.items():
        data = zlib.compress(raw)
        blob = struct.pack(">IB", len(data) + 1, 2) + data       # 2 = zlib
        blob += b"\x00" * (-len(blob) % 4096)
        count = len(blob) // 4096
        i = 4 * (lx + lz * 32)
        locations[i:i + 4] = struct.pack(">I", (sector << 8) | count)
        stamps[i:i + 4] = struct.pack(">I", now)
        body.write(blob)
        sector += count
    with open(path, "wb") as f:
        f.write(locations + stamps + body.getvalue())


# ---------------------------------------------------------------- 6. data pack (Mars sky, gravity, no rain)
def write_datapack(root, plan=None):
    pack = os.path.join(root, "datapacks", "marscuff")
    os.makedirs(os.path.join(pack, "data", "minecraft", "worldgen", "biome"), exist_ok=True)
    os.makedirs(os.path.join(pack, "data", "marscuff", "function"), exist_ok=True)
    json.dump({"pack": {"min_format": PACK_FORMAT, "max_format": PACK_FORMAT,
                        "description": "MarsCuff: Jezero Crater sky and rules"}},
              open(os.path.join(pack, "pack.mcmeta"), "w"), indent=1)
    # We change the vanilla "desert" biome, so if this pack ever fails to load
    # the world simply looks like a desert instead of breaking.
    #
    # Minecraft 26.3 moved the sky and fog colours out of the biome's "effects"
    # and into "attributes" (the new environment-attribute system); colours are
    # "#RRGGBB" strings there, and "carvers" has to be a list.
    json.dump({
        "has_precipitation": False, "temperature": 2.0, "downfall": 0.0,
        "attributes": {
            "minecraft:visual/sky_color": "#C9A27E",      # butterscotch Mars daytime sky
            "minecraft:visual/fog_color": "#D8B48C",      # dusty haze (colours picked by eye
            "minecraft:visual/fog_end_distance": 2048.0,  # from rover photos); see far, thin air
        },
        "effects": {"water_color": "#3F76E4"},
        "carvers": [], "features": [],
    }, open(os.path.join(pack, "data", "minecraft", "worldgen", "biome", "desert.json"), "w"), indent=1)

    # Mars gravity, checked every game tick for everyone online. A tick function runs
    # as the server, not as a player, so each line needs "execute as @a run".
    # Mars g = 3.71 m/s^2 = 0.378 x Earth (NASA Mars Fact Sheet). Minecraft's normal
    # gravity value is 0.08, so Mars = 0.08 x 0.378 = 0.0302. Falls are gentler too:
    # the safe fall height (3 blocks) is divided by the same 0.378.
    os.makedirs(os.path.join(pack, "data", "minecraft", "tags", "function"), exist_ok=True)
    json.dump({"values": ["marscuff:tick"]},
              open(os.path.join(pack, "data", "minecraft", "tags", "function", "tick.json"), "w"))
    with open(os.path.join(pack, "data", "marscuff", "function", "tick.mcfunction"), "w") as f:
        f.write("# Mars gravity (0.378 x Earth) for every player\n"
                "execute as @a run attribute @s minecraft:gravity base set 0.0302\n"
                "execute as @a run attribute @s minecraft:safe_fall_distance base set 7.9\n")

    # Where you start, and a way back if you ever lose the pillars. The "load" tag
    # runs once when the world opens, before anyone has spawned, so setworldspawn
    # here is what puts a first-time player at the habitat.
    hab = (plan or {}).get("habitat")
    if hab:
        hx, hz = jm.block_of_cell(hab["row"], hab["col"])
        hy = jm.ground_y(hx, hz) + 1
        json.dump({"values": ["marscuff:load"]},
                  open(os.path.join(pack, "data", "minecraft", "tags", "function", "load.json"), "w"))
        with open(os.path.join(pack, "data", "marscuff", "function", "load.mcfunction"), "w") as f:
            f.write("# Start the walk at the habitat\n"
                    "setworldspawn %d %d %d\n" % (hx, hy, hz))
        with open(os.path.join(pack, "data", "marscuff", "function", "home.mcfunction"), "w") as f:
            f.write("# /function marscuff:home - back to the habitat\n"
                    "teleport @s %d %d %d\n" % (hx, hy, hz))


# ---------------------------------------------------------------- 7. building
def region_dir(save):
    """Minecraft 26.x keeps the overworld in dimensions/minecraft/overworld/region; 1.21 uses region/."""
    new = os.path.join(save, "dimensions", "minecraft", "overworld")
    return os.path.join(new, "region") if os.path.isdir(new) else os.path.join(save, "region")


def _init_worker(tracks, region, base, marks=None):
    global _TRACKS, REGION, _MARKS
    _TRACKS, REGION, _MARKS = tracks, region, marks or {}
    jm.set_elevation_base(base)


def make_region(job):
    """Build one region file from a list of chunk coordinates. Runs in a worker process."""
    (rx, rz), chunk_list = job
    cxs = [c[0] for c in chunk_list]; czs = [c[1] for c in chunk_list]
    x0, z0 = min(cxs) * 16, min(czs) * 16
    w = (max(cxs) - min(cxs) + 1) * 16
    h = (max(czs) - min(czs) + 1) * 16
    ground, top, under, boulder, layered = columns(x0, z0, w, h, _TRACKS)
    out = {}
    for cx, cz in chunk_list:
        x, z = cx * 16 - x0, cz * 16 - z0
        here = {(mx & 15, mz & 15): m for (mx, mz), m in _MARKS.items()
                if (mx >> 4) == cx and (mz >> 4) == cz}
        out[(cx & 31, cz & 31)] = chunk_nbt(
            cx, cz, ground[z:z + 16, x:x + 16], top[z:z + 16, x:x + 16],
            under[z:z + 16, x:x + 16], boulder[z:z + 16, x:x + 16], layered[z:z + 16, x:x + 16],
            here)
    write_region(os.path.join(REGION, "r.%d.%d.mca" % (rx, rz)), out)
    return len(out)


def stored_base(root):
    """The elevation anchor a save was built with, if it has one.

    Every world pins one Mars elevation to y = Y_BASE. If a second route were
    anchored differently, the two pieces of terrain would not line up, so the
    first build wins and later ones reuse its number.
    """
    path = os.path.join(root, MARKER)
    if os.path.exists(path):
        try:
            return json.load(open(path)).get("elevation_base_m")
        except (ValueError, OSError):
            return None
    return None


def build(chunks, root, region, write_pack=True, label="", base=None, plan=None):
    """Write the terrain for `chunks` into `region`. Returns the info dict."""
    from multiprocessing import Pool, cpu_count
    t0 = time.time()
    lo, hi = corridor_relief(chunks)
    if base is None:
        base = lo - 24.0                       # 24 m of rock under the lowest ground
    if hi - base > jm.USABLE_HEIGHT:
        sys.exit("This route climbs %d m above the height this world is anchored at, and a\n"
                 "Minecraft world only holds %d m. Make a new world for this route."
                 % (round(hi - base), jm.USABLE_HEIGHT))
    jm.set_elevation_base(base)

    os.makedirs(region, exist_ok=True)
    print("1/3 %s: %d chunks = %.2f km2 of Mars (1 block = 1 m)"
          % (label or "corridor", len(chunks), len(chunks) * 256 / 1e6))
    tracks = rover_track_blocks(chunks)
    print("  rover tracks in view: %d blocks" % len(tracks))

    # Group the chunks by the region file they belong to (32 x 32 chunks each).
    groups = {}
    for cx, cz in chunks:
        groups.setdefault((cx >> 5, cz >> 5), []).append((cx, cz))
    jobs = sorted(groups.items())
    workers = max(1, min(len(jobs), cpu_count() - 2))
    print("2/3 writing %d region files with %d workers ..." % (len(jobs), workers))
    marks = route_marker_blocks(plan, chunks)
    with Pool(workers, initializer=_init_worker, initargs=(tracks, region, base, marks)) as pool:
        done = 0
        for k, n in enumerate(pool.imap_unordered(make_region, jobs), 1):
            done += n
            if k % 10 == 0 or k == len(jobs):
                print("  %d/%d region files, %d chunks (%.0f s)"
                      % (k, len(jobs), done, time.time() - t0), flush=True)

    print("3/3 data pack + map info ...")
    if write_pack:
        write_datapack(root, plan)
    info = jm.describe()
    box = corridor_bounds(chunks)
    info["corridor"] = {
        "chunks": len(chunks), "blocks_box": box,
        "area_km2": round(len(chunks) * 256 / 1e6, 3),
        "corridor_radius_m": CORRIDOR_RADIUS_M, "station_radius_m": STATION_RADIUS_M,
        "note": "only the ground near the planned walk exists; everywhere else is empty",
    }
    info["elevation_base_m"] = base
    info["elevation_in_corridor_m"] = [round(lo, 1), round(hi, 1)]
    lat, lon = jm.landing_site()
    lx, lz = jm.block_of_latlon(lat, lon)
    info["landing_site"] = {"lat": lat, "lon": lon, "x": lx, "z": lz, "y": jm.ground_y(lx, lz) + 1}
    json.dump(info, open(os.path.join(root, "world_info.json"), "w"), indent=1)
    json.dump({"elevation_base_m": base, "built": time.strftime("%Y-%m-%d %H:%M:%S"),
               "corridor": info["corridor"]},
              open(os.path.join(root, MARKER), "w"), indent=1)
    print("done in %.0f s -> %s" % (time.time() - t0, root))
    return info


# ---------------------------------------------------------------- 8. handing the world to someone
SETUP = """MARSCUFF - JEZERO CRATER, FOR REAL
==================================

This is a Minecraft world made from NASA/USGS maps of Jezero Crater, the place
Perseverance landed in February 2021. One Minecraft block is one metre of Mars,
sideways AND up, so the hills are the real hills and the climbs are the real
climbs. Block 0, 0 is the landing site.

You do NOT need any mod, any add-on or Python to walk this. It is an ordinary
Minecraft Java Edition save.

HOW TO SET IT UP
1. Unzip this folder.
2. Put the folder "%(save)s" inside your Minecraft saves folder:
     Windows  %%APPDATA%%\\.minecraft\\saves
     macOS    ~/Library/Application Support/minecraft/saves
     Linux    ~/.minecraft/saves
3. Start Minecraft Java Edition 26.3 (the version this world was built for), open
   Singleplayer, and the world is in the list. It says "Experimental Settings"
   when you open it, because the world carries its own data pack - that is
   expected, so choose to load it anyway.
4. The data pack "MarsCuff" is already switched on. It is what gives you the
   butterscotch sky, no rain, and Mars gravity (0.378 x Earth, so you jump about
   two and a half times as high and fall gently). If the sky ever looks like
   Earth, open Options -> Data Packs from the world list and switch it back on.
5. You start at the habitat. Press F3 to see your coordinates: the numbers below
   are block X and Z, and the world is 1 block = 1 metre.

WHAT YOU ARE LOOKING AT
  * the ground            USGS CTX digital terrain model, 40 m cells, smoothed
  * the rock colours      bedrock units mapped by Stack et al. 2020
  * the dark grey strip   Perseverance's real driving track
  * the loose rocks       boulder fields, denser on the crater rim units
  * the small craters     added by us: real Mars has them at this size, the
                          40 m map cannot see them (labelled MODEL, not data)

HOW TO FOLLOW THE WALK
  * a line of glowing yellow blocks on the ground is your route - follow it
  * a tall WHITE pillar with a glowing top is the habitat: home
  * a tall PURPLE pillar is a science station: stop and work it
  * a tall RED pillar, if there is one, is the Point of No Return: past it you
    no longer have the air to walk home, so it is the hard turn-around
  * lost? Open to LAN / enable cheats and run  /function marscuff:home

WHY THE WORLD JUST STOPS
Only the ground near your planned walk was built: %(area)s km2 of it. Building
all 900 km2 of the map would be about 14 GB. The empty edge is the edge of what
was generated, not a cliff on Mars. Plan a different walk on the website and
generate again to get a different strip.
"""

WHY_SCIENCE = """WHY THESE EXPERIMENTS, AND WHAT THE RESULTS WOULD BE FOR
Every station sits where the orbital maps are least sure of themselves: ground
nobody has driven, ground only ever seen at 20 m per pixel, or a mapped boundary
between two rock units that has never been checked from the surface. That is the
whole point of walking there instead of somewhere pretty.

The tasks on the cuff are the ones that turn a guess into a measurement:
  * a close-up photo and one sample give the first ground truth for a unit that
    until now is only a colour on a map
  * photographing a contact from two sides, with a sample on each side, is what
    tells you which rock came first - that is how the order of events in Jezero
    gets settled, and Jezero is where the Mars Sample Return samples come from
  * a footing note (how the surface takes a boot) feeds the engineering models
    that decide where crews and rovers can actually go
  * the weather log at the habitat is the boring one that matters: repeated
    local readings are what turn one day of data into a climate record

So the results help in two real ways: they correct the maps that everything else
is planned from, and they say whether the ground is safe to work on.

HONESTY ABOUT THE NUMBERS
The ground, the rock units and the rover track are real data (sources at the end
of the cuff). The walking speed, the 30 minutes of work per station and the air
budget are a MODEL - the Tobler hiking function slowed to 0.6 for a suit, plus
our own team assumptions. They are labelled that way on the website too. Nothing
here is a NASA timeline.
"""

def how_to_use(save_name, info, plan):
    """The whole HOW-TO-USE.txt: setup, then the walk, then the cuff, then why."""
    area = (info.get("corridor") or {}).get("area_km2", "?")
    out = [SETUP % {"save": save_name, "area": area}]

    if not plan:
        out.append("YOUR WALK\nThis world was built without a route (a plain disc of ground around the\n"
                   "landing site), so there are no stations in it. Plan a walk on the website\n"
                   "and generate again.\n")
        out.append(WHY_SCIENCE)
        return "\n".join(out)

    rows = ["YOUR WALK - WHERE TO GO (block coordinates, press F3 in game)", ""]

    def place(label, cell, extra=""):
        x, z = jm.block_of_cell(cell["row"], cell["col"])
        rows.append("  %-22s X %6d   Z %6d   %s" % (label, x, z, extra))

    hab = plan.get("habitat")
    if hab:
        place("habitat (white)", hab, "start and finish here")
    for i, st in enumerate(plan.get("stations") or [], 1):
        note = st.get("unit") or ""
        if st.get("neverDriven"):
            note += " - never driven"
        place("station %d (purple)" % i, st, note.strip(" -"))
    pnr = plan.get("pnr")
    if pnr:
        place("Point of No Return", pnr, "do not pass this after your leave-by time")
    summary = plan.get("summary") or {}
    if summary:
        rows += ["", "  %s km on foot, %s of walking and working, %s of air."
                 % (summary.get("km", "?"), summary.get("total", "?"), summary.get("usable", "?"))]
    out.append("\n".join(rows) + "\n")

    book = plan.get("book") or []
    if book:
        cuff = ["YOUR CUFF - THE SAME TEXT AS THE PRINTED PAPER CUFF",
                "(on the website: Preview cuff / Print cuff)", ""]
        for page in book:
            cuff.append("  " + "\n  ".join(str(page).splitlines()))
            cuff.append("  " + "-" * 46)
        out.append("\n".join(cuff) + "\n")

    out.append(WHY_SCIENCE)
    return "\n".join(out)

def export_zip(save, dest, plan=None):
    """Zip a finished save folder with a HOW-TO-USE.txt beside it."""
    name = os.path.basename(os.path.normpath(save))
    info = {}
    path = os.path.join(save, "world_info.json")
    if os.path.exists(path):
        info = json.load(open(path))
    # The bridge drops the last plan in the save; use it if we were not handed one.
    if plan is None:
        last = os.path.join(save, "marscuff_last_plan.json")
        if os.path.exists(last):
            plan = json.load(open(last))
    # Block coordinates need the same anchor the terrain was built at.
    if (info.get("elevation_base_m") or 0):
        jm.set_elevation_base(info["elevation_base_m"])
    readme = how_to_use(name, info, plan)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("HOW-TO-USE.txt", readme)
        for folder, _dirs, files in os.walk(save):
            for f in files:
                full = os.path.join(folder, f)
                z.write(full, os.path.join(name, os.path.relpath(full, save)))
    print("zipped -> %s (%.0f MB)" % (dest, os.path.getsize(dest) / 1e6))


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Build the Jezero terrain along one planned walk.")
    ap.add_argument("--route", help="plan JSON from the website (web/js/minecraft.js payload)")
    ap.add_argument("--save", help="an existing, CLOSED Minecraft save to write the terrain into")
    ap.add_argument("--zip", dest="zip_to", help="also zip the finished save to this file")
    args = ap.parse_args()

    root = args.save or OUT
    if args.save:
        if not os.path.exists(os.path.join(root, "level.dat")):
            sys.exit("%s is not a Minecraft save (no level.dat). Create the world first." % root)
    else:
        os.makedirs(root, exist_ok=True)

    plan = None
    if args.route:
        plan = json.load(open(args.route))
        points = route_points(plan)
        label = "route corridor (%.0f m band, %.0f m at stations)" % (CORRIDOR_RADIUS_M,
                                                                     STATION_RADIUS_M)
    else:
        points = demo_points()
        label = "demo disc, %.1f km across the landing site" % (DEMO_RADIUS_M * 2 / 1000.0)

    chunks = corridor_chunks(points)
    if not chunks:
        sys.exit("That route is not inside the NASA map, so there is no data to build from.")
    build(chunks, root, region_dir(root), write_pack=True, label=label,
          base=stored_base(root), plan=plan)
    if plan:
        json.dump(plan, open(os.path.join(root, "marscuff_last_plan.json"), "w"))

    if args.zip_to:
        export_zip(root, args.zip_to, plan)


if __name__ == "__main__":
    main()
