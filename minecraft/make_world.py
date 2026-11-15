# make_world.py - builds a Minecraft (Java 1.21.1) world of Jezero Crater
# from the SAME NASA data the website uses.
#
#   python minecraft/make_world.py     -> %USERPROFILE%/MarsCuffMinecraft/server/world/
#
# What it makes (true scale: 1 block = 10 m, see jezero_map.py):
#   * ground height  : USGS CTX DTM (web/data/grid.bin), smoothed between 40 m cells
#   * surface colour : bedrock unit from Stack et al. 2020 (web/data/units.bin);
#                      outside their map = red sand (rock type unknown)
#   * steep ground   : > 15 deg (the website's "blocked" slope) shows bare rock
#   * rover tracks   : Perseverance traverse (web/data/traverse.geojson)
#   * Mars sky       : a data pack makes the sky butterscotch, no rain, no mobs
#
# How a Minecraft world file works (short version): the world is cut into
# 16x16 "chunks"; 32x32 chunks are stored in one ".mca" region file; each chunk
# is a small tree of named values ("NBT"), zipped. We write those files directly.

import io
import json
import math
import os
import struct
import sys
import time
import zlib

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jezero_map as jm

OUT = os.path.join(jm.SERVER_DIR, "world")
DATA_VERSION = 3955          # Minecraft 1.21.1
PACK_FORMAT = 48             # data pack format for 1.21.1

# ---------------------------------------------------------------- blocks
BLOCKS = ["air", "bedrock", "smooth_basalt", "red_sandstone", "red_sand",
          "terracotta", "brown_terracotta", "orange_terracotta", "white_terracotta",
          "light_gray_terracotta", "yellow_terracotta", "red_terracotta", "packed_mud"]
ID = {name: i for i, name in enumerate(BLOCKS)}

# Surface block for each Stack et al. 2020 unit id (see web/data/units.json).
# The colours are OUR choice so the units can be told apart; Mars is dusty
# red-brown everywhere, so we stay in red/orange/brown tones.
UNIT_TOP = {
    0: "red_sand",                                            # not mapped
    1: "brown_terracotta", 2: "brown_terracotta",             # crater floor fractured 1, 2 (darker)
    3: "terracotta",                                          # crater floor fractured rough
    4: "orange_terracotta", 5: "orange_terracotta",           # crater rim
    6: "orange_terracotta", 7: "orange_terracotta",
    8: "brown_terracotta",                                    # delta blocky
    9: "yellow_terracotta",                                   # delta layered rough
    10: "white_terracotta", 11: "white_terracotta",           # delta thickly / thinly layered
    12: "light_gray_terracotta",                              # delta truncated curvilinear
    13: "yellow_terracotta",                                  # margin fractured
    14: "red_terracotta",                                     # Neretva Vallis layered
    15: "orange_terracotta",                                  # Nili Planum fractured
}
LAYERED_UNITS = {9, 10, 11, 12, 14}   # "layered" units show stripes in their cliffs
LAYER_STRIPES = ["white_terracotta", "orange_terracotta", "light_gray_terracotta", "terracotta"]
STEEP_TENTHS = 150                    # 15.0 deg = the website's "blocked" slope


# ---------------------------------------------------------------- 1. the whole map as arrays
def build_columns():
    """For every block column: ground y, top block id, 'layered' flag."""
    elev = np.fromfile(os.path.join(jm.DATA, "grid.bin"), dtype="<i2",
                       count=jm.ROWS * jm.COLS).reshape(jm.ROWS, jm.COLS).astype(np.float64)
    slope = np.fromfile(os.path.join(jm.DATA, "grid.bin"), dtype="<i2",
                        count=jm.ROWS * jm.COLS, offset=jm.ROWS * jm.COLS * 2).reshape(jm.ROWS, jm.COLS)
    units = np.fromfile(os.path.join(jm.DATA, "units.bin"), dtype=np.uint8).reshape(jm.ROWS, jm.COLS)

    xs = np.arange(jm.X_MIN, jm.X_MIN + jm.WIDTH)
    zs = np.arange(jm.Z_MIN, jm.Z_MIN + jm.HEIGHT)
    col_f = (xs - jm.X_MIN + 0.5) * jm.M_PER_BLOCK / jm.DX_CELL     # same maths as jezero_map.cell_coords
    row_f = (zs - jm.Z_MIN + 0.5) * jm.M_PER_BLOCK / jm.DZ_CELL

    # Bilinear smoothing between cell centres (same order of operations as ground_y()).
    u = np.clip(col_f - 0.5, 0.0, jm.COLS - 1.0)
    v = np.clip(row_f - 0.5, 0.0, jm.ROWS - 1.0)
    c0 = np.minimum(u.astype(int), jm.COLS - 2); tu = u - c0
    r0 = np.minimum(v.astype(int), jm.ROWS - 2); tv = v - r0
    e00 = elev[np.ix_(r0, c0)]; e01 = elev[np.ix_(r0, c0 + 1)]
    e10 = elev[np.ix_(r0 + 1, c0)]; e11 = elev[np.ix_(r0 + 1, c0 + 1)]
    top = e00 * (1 - tu) + e01 * tu
    bot = e10 * (1 - tu) + e11 * tu
    e = top * (1 - tv[:, None]) + bot * tv[:, None]
    ground = (jm.Y_BASE + np.floor((e - jm.ELEV_BASE_M) / jm.M_PER_BLOCK + 0.5)).astype(np.int16)

    # Nearest cell for slope + geology (no smoothing: a unit is a unit).
    ci = np.minimum(col_f.astype(int), jm.COLS - 1)
    ri = np.minimum(row_f.astype(int), jm.ROWS - 1)
    unit = units[np.ix_(ri, ci)]
    steep = slope[np.ix_(ri, ci)] > STEEP_TENTHS

    lut = np.array([ID[UNIT_TOP.get(k, "red_sand")] for k in range(256)], dtype=np.uint8)
    top_block = lut[unit]
    top_block[steep & (unit == 0)] = ID["terracotta"]          # bare rock on steep unmapped slopes
    layered = np.isin(unit, list(LAYERED_UNITS))

    draw_rover_tracks(top_block)
    return ground, top_block, layered


def draw_rover_tracks(top_block):
    """Paint the Perseverance traverse onto the surface, 2 blocks wide."""
    t = json.load(open(os.path.join(jm.DATA, "traverse.geojson")))
    n = 0
    for f in t["features"]:
        g = f["geometry"]
        lines = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
        for line in lines:
            pts = [jm.block_of_latlon(lat, lon) for lon, lat, *_ in line]
            for (x0, z0), (x1, z1) in zip(pts, pts[1:]):
                steps = max(abs(x1 - x0), abs(z1 - z0), 1)
                for s in range(steps + 1):
                    x = round(x0 + (x1 - x0) * s / steps) - jm.X_MIN
                    z = round(z0 + (z1 - z0) * s / steps) - jm.Z_MIN
                    if 0 <= x < jm.WIDTH - 1 and 0 <= z < jm.HEIGHT - 1:
                        top_block[z:z + 2, x:x + 2] = ID["packed_mud"]
                        n += 1
    print(f"  rover tracks: {n} points")


# ---------------------------------------------------------------- 2. tiny NBT writer
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


# ---------------------------------------------------------------- 3. one chunk
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

def chunk_nbt(cx, cz, ground, top_block, layered):
    """ground/top_block/layered: 16x16 arrays [z, x] for this chunk."""
    max_y = int(ground.max())
    ys = np.arange(-64, (max_y // 16 + 1) * 16)[:, None, None]       # y, z, x
    depth = ground[None] - ys                                         # 0 = surface block
    blocks = np.full(depth.shape, ID["smooth_basalt"], dtype=np.uint8)
    blocks[(depth >= 1) & (depth <= 3)] = ID["red_sandstone"]
    stripe = np.array([ID[s] for s in LAYER_STRIPES], dtype=np.uint8)[(ys % 4).repeat(16, 1).repeat(16, 2)]
    lay = layered[None] & (depth >= 1) & (depth <= 12)
    blocks[lay] = stripe[lay]
    blocks[depth == 0] = np.broadcast_to(top_block[None], depth.shape)[depth == 0]
    blocks[depth < 0] = ID["air"]
    blocks[ys[:, 0, 0] == -64] = ID["bedrock"]

    sections = []
    for s in range(blocks.shape[0] // 16):
        sec = blocks[s * 16:(s + 1) * 16].reshape(-1)                  # index = y*256 + z*16 + x
        pal, inv = np.unique(sec, return_inverse=True)
        bs = {"palette": ("list", ("compound", [{"Name": ("string", "minecraft:" + BLOCKS[p])} for p in pal]))}
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


# ---------------------------------------------------------------- 4. region files
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


# ---------------------------------------------------------------- 5. data pack (Mars sky, no rain)
def write_datapack():
    root = os.path.join(OUT, "datapacks", "marscuff")
    os.makedirs(os.path.join(root, "data", "minecraft", "worldgen", "biome"), exist_ok=True)
    os.makedirs(os.path.join(root, "data", "marscuff", "function"), exist_ok=True)
    json.dump({"pack": {"pack_format": PACK_FORMAT,
                        "description": "MarsCuff: Jezero Crater sky and rules"}},
              open(os.path.join(root, "pack.mcmeta"), "w"), indent=1)
    # We change the vanilla "desert" biome, so if this pack ever fails to load
    # the world simply looks like a desert instead of breaking.
    sky = 0xC9A27E   # butterscotch daytime Mars sky (colour picked by eye from rover photos)
    json.dump({
        "has_precipitation": False, "temperature": 2.0, "downfall": 0.0,
        "effects": {"sky_color": sky, "fog_color": 0xD8B48C,
                    "water_color": 0x3F76E4, "water_fog_color": 0x050533},
        "spawners": {}, "spawn_costs": {}, "carvers": {}, "features": [],
    }, open(os.path.join(root, "data", "minecraft", "worldgen", "biome", "desert.json"), "w"), indent=1)

    # Mars gravity, checked every game tick for everyone online.
    # Mars g = 3.71 m/s^2 = 0.378 x Earth (NASA Mars Fact Sheet). Minecraft's normal
    # gravity value is 0.08, so Mars = 0.08 x 0.378 = 0.0302. Falls are gentler too:
    # the safe fall height (3 blocks) is divided by the same 0.378.
    os.makedirs(os.path.join(root, "data", "minecraft", "tags", "function"), exist_ok=True)
    json.dump({"values": ["marscuff:tick"]},
              open(os.path.join(root, "data", "minecraft", "tags", "function", "tick.json"), "w"))
    with open(os.path.join(root, "data", "marscuff", "function", "tick.mcfunction"), "w") as f:
        f.write("# Mars gravity (0.378 x Earth) for every player\n"
                "execute as @a run attribute @s minecraft:generic.gravity base set 0.0302\n"
                "execute as @a run attribute @s minecraft:generic.safe_fall_distance base set 7.9\n")


# ---------------------------------------------------------------- main
def main():
    t0 = time.time()
    if os.path.exists(os.path.join(OUT, "level.dat")):
        sys.exit(f"{OUT} already has a world (level.dat). Move it away first if you want a fresh one.")
    os.makedirs(os.path.join(OUT, "region"), exist_ok=True)
    print("1/3 reading NASA grids ...")
    ground, top_block, layered = build_columns()
    print(f"  world {jm.WIDTH} x {jm.HEIGHT} blocks, ground y {ground.min()} .. {ground.max()}")

    print("2/3 writing region files ...")
    cx0, cz0 = jm.X_MIN // 16, jm.Z_MIN // 16
    ncx, ncz = jm.WIDTH // 16, jm.HEIGHT // 16
    regions = {}
    for cz in range(cz0, cz0 + ncz):
        for cx in range(cx0, cx0 + ncx):
            regions.setdefault((cx >> 5, cz >> 5), []).append((cx, cz))
    for k, ((rx, rz), clist) in enumerate(sorted(regions.items())):
        chunks = {}
        for cx, cz in clist:
            x = (cx - cx0) * 16; z = (cz - cz0) * 16
            chunks[(cx & 31, cz & 31)] = chunk_nbt(cx, cz, ground[z:z + 16, x:x + 16],
                                                   top_block[z:z + 16, x:x + 16], layered[z:z + 16, x:x + 16])
        write_region(os.path.join(OUT, "region", f"r.{rx}.{rz}.mca"), chunks)
        print(f"  region {k + 1}/{len(regions)}  r.{rx}.{rz}.mca  ({len(chunks)} chunks)", flush=True)

    print("3/3 data pack + map info ...")
    write_datapack()
    info = jm.describe()
    lat, lon = jm.landing_site()
    lx, lz = jm.block_of_latlon(lat, lon)
    info["landing_site"] = {"lat": lat, "lon": lon, "x": lx, "z": lz,
                            "y": int(ground[lz - jm.Z_MIN, lx - jm.X_MIN]) + 1}
    json.dump(info, open(os.path.join(jm.SERVER_DIR, "world_info.json"), "w"), indent=1)
    print(f"done in {time.time() - t0:.0f} s -> {OUT}")


if __name__ == "__main__":
    main()
