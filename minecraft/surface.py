"""What the ground actually looks like, below the 40 m NASA grid.

The elevation grid has one number every 40 m. If you build straight from it the
world is a smooth, rubbery plain: nothing to trip over, no rocks, no craters.
Mars isn't like that, so this module adds the detail that is TOO SMALL for the
grid to see, in a way that is deterministic (same route = same ground, every time)
and physically motivated. Nothing here invents science: the grid still decides the
shape of the land, and the Stack et al. 2020 unit map still decides the rock type.
The detail below is clearly a MODEL - a texture, not a measurement.

What gets added, and why:
  1. Fractal roughness - real slopes are rough at every scale. Amplitude grows with
     the local slope, because steep ground on Mars is blockier and more broken.
  2. Aeolian ripples - wind-made sand ripples a few metres apart, only on flat dusty
     ground. (Perseverance drives over these constantly; they are in every Navcam.)
  3. Small impact craters - bowl plus raised rim plus an ejecta skirt, scattered on a
     jittered grid. Fresh ones are sharp, old ones are nearly filled in.
  4. Boulders - single blocks and 2-block stacks, commonest on the crater-rim and
     delta-blocky units and on steep ground.
  5. Surface material - dust-covered regolith on flats, bedrock showing through where
     it is steep or where the dust cover thins out (patchy, not a clean line).
"""

import numpy as np

# Every block type this generator can place. The index into this list is the id we
# use everywhere else, so the order must not change without rebuilding the palette.
BLOCKS = [
    "air", "bedrock",
    "red_sand", "red_sandstone", "smooth_red_sandstone", "cut_red_sandstone",
    "terracotta", "brown_terracotta", "orange_terracotta", "white_terracotta",
    "light_gray_terracotta", "yellow_terracotta", "red_terracotta", "gray_terracotta",
    "packed_mud", "smooth_basalt", "basalt", "blackstone", "tuff", "granite",
    "andesite", "cobbled_deepslate",
    # Route markers (not Mars: these are the signposts for the walk). Added at the
    # END of the list so every block index above keeps the value it already had.
    "glowstone", "white_concrete", "purple_concrete", "red_concrete",
]
ID = {name: i for i, name in enumerate(BLOCKS)}

# Bedrock colour per Stack et al. 2020 unit (see web/data/units.json for the names).
# 0 = unmapped, which is most of the map; there we use dusty regolith.
UNIT_TOP = {
    0: "red_sand",
    1: "brown_terracotta", 2: "brown_terracotta", 3: "terracotta",          # crater floor
    4: "gray_terracotta", 5: "orange_terracotta",                           # crater rim
    6: "orange_terracotta", 7: "orange_terracotta",
    8: "brown_terracotta",                                                  # delta blocky
    9: "yellow_terracotta", 10: "white_terracotta", 11: "white_terracotta",  # delta layered
    12: "light_gray_terracotta",
    13: "yellow_terracotta",                                                # margin fractured
    14: "red_terracotta",                                                   # Neretva Vallis
    15: "orange_terracotta",                                                # Nili Planum
}
# Units described as layered: these get visible strata in any cut or cliff.
LAYERED_UNITS = {6, 9, 10, 11, 12, 14}
LAYER_STRIPES = ["white_terracotta", "orange_terracotta", "light_gray_terracotta", "terracotta"]

# How bouldery each unit is (fraction of 1 m columns with a rock on top). A MODEL
# number, ranked to match the unit descriptions: "blocky" and "breccia" > "fractured".
BOULDER_BASE = {0: 0.002, 1: 0.004, 2: 0.004, 3: 0.006, 4: 0.020, 5: 0.016,
                6: 0.008, 7: 0.014, 8: 0.018, 9: 0.006, 10: 0.005, 11: 0.005,
                12: 0.006, 13: 0.007, 14: 0.006, 15: 0.007}
BOULDER_BLOCKS = ["smooth_basalt", "basalt", "blackstone", "tuff", "andesite", "cobbled_deepslate"]

CRATER_SPACING_M = 155.0    # one candidate crater per 155 m cell (about half of them are empty)
RIPPLE_WAVELENGTH_M = 13.0  # metres crest to crest
RIPPLE_AMPLITUDE_M = 0.65
RIPPLE_BEARING_DEG = 35.0   # ripple crests run across the dominant wind


# ----------------------------------------------------------------- random helpers

def _mix(h):
    """A standard integer hash (splitmix-style), so 'random' is the same every run."""
    h = h.astype(np.uint64)
    h ^= h >> np.uint64(30)
    h *= np.uint64(0xBF58476D1CE4E5B9)
    h ^= h >> np.uint64(27)
    h *= np.uint64(0x94D049BB133111EB)
    h ^= h >> np.uint64(31)
    return h


def rand2(ix, iz, seed):
    """Deterministic value in [0, 1) for integer lattice point (ix, iz). Broadcasts."""
    base = (ix.astype(np.int64) * np.int64(0x9E3779B1)
            + iz.astype(np.int64) * np.int64(0x85EBCA77)
            + np.int64(seed) * np.int64(0xC2B2AE3D))
    return (_mix(base) >> np.uint64(11)).astype(np.float64) / float(1 << 53)


def rand1(ix, iz, seed):
    """Same hash for single numbers (used for one crater at a time)."""
    return float(rand2(np.array([ix]), np.array([iz]), seed)[0])


def _smooth(t):
    """Smoothstep: makes the noise curve instead of forming diamonds."""
    return t * t * (3.0 - 2.0 * t)


def noise(xs, zs, wavelength, seed):
    """Value noise on a square lattice. xs, zs are 1-D block coords -> (len(zs), len(xs))."""
    fx = xs / wavelength
    fz = zs / wavelength
    ix = np.floor(fx).astype(np.int64)
    iz = np.floor(fz).astype(np.int64)
    tx = _smooth(fx - ix)[None, :]
    tz = _smooth(fz - iz)[:, None]
    IX, IZ = ix[None, :], iz[:, None]
    n00 = rand2(IX, IZ, seed)
    n10 = rand2(IX + 1, IZ, seed)
    n01 = rand2(IX, IZ + 1, seed)
    n11 = rand2(IX + 1, IZ + 1, seed)
    a = n00 * (1 - tx) + n10 * tx
    b = n01 * (1 - tx) + n11 * tx
    return a * (1 - tz) + b * tz          # 0..1


def fractal(xs, zs, seed, octaves=(160.0, 70.0, 28.0, 11.0, 4.0)):
    """Sum of noise at halving wavelengths and halving strength -> rough but not spiky.
    Returns roughly -1..+1."""
    total = np.zeros((len(zs), len(xs)))
    weight = 0.0
    amp = 1.0
    for k, wl in enumerate(octaves):
        total += amp * (noise(xs, zs, wl, seed + 31 * k) - 0.5) * 2.0
        weight += amp
        amp *= 0.55
    return total / weight


# ---------------------------------------------------------------------- craters

def crater_relief(xs, zs, seed=1917):
    """Height change (metres) from small impact craters covering this patch."""
    out = np.zeros((len(zs), len(xs)))
    S = CRATER_SPACING_M
    gx0, gx1 = int(np.floor(xs[0] / S)) - 1, int(np.floor(xs[-1] / S)) + 1
    gz0, gz1 = int(np.floor(zs[0] / S)) - 1, int(np.floor(zs[-1] / S)) + 1
    for gx in range(gx0, gx1 + 1):
        for gz in range(gz0, gz1 + 1):
            if rand1(gx, gz, seed) > 0.55:
                continue                                   # most cells have no crater
            cx = (gx + rand1(gx, gz, seed + 1)) * S
            cz = (gz + rand1(gx, gz, seed + 2)) * S
            # Small craters are far commoner than big ones, hence the cube.
            radius = 5.0 + 45.0 * rand1(gx, gz, seed + 3) ** 3
            fresh = 0.25 + 0.75 * rand1(gx, gz, seed + 4)   # 1 = sharp, 0.25 = filled in
            reach = radius * 1.6
            if cx + reach < xs[0] or cx - reach > xs[-1]:
                continue
            if cz + reach < zs[0] or cz - reach > zs[-1]:
                continue
            dx = xs[None, :] - cx
            dz = zs[:, None] - cz
            d = np.sqrt(dx * dx + dz * dz)
            depth = 0.17 * radius * fresh       # fresh craters are ~1/5 as deep as wide
            rim = 0.045 * radius * fresh
            bowl = -depth * (1.0 - (d / radius) ** 2)
            bowl[d > radius] = 0.0
            skirt = rim * np.clip(1.0 - (d - radius) / (0.6 * radius), 0.0, 1.0)
            inside = d < radius
            skirt[inside] = rim * (d[inside] / radius) ** 4   # rim crest right at the edge
            skirt[d > reach] = 0.0
            out += bowl + skirt
    return out


# ------------------------------------------------------------------ the main call

def detail(xs, zs, elev, slope_deg, unit, seed=20260215):
    """Add the small-scale detail to one patch of ground.

    xs, zs    1-D block coordinates (x east, z south)
    elev      (len(zs), len(xs)) Mars elevation in metres from the NASA grid
    slope_deg same shape, slope in degrees from the NASA grid
    unit      same shape, Stack et al. 2020 unit id (0 = unmapped)

    Returns (elev, top, under, boulder, layered):
      elev     elevation with roughness, ripples and craters mixed in
      top      block id of the surface block
      under    block id of the 1-3 m of broken rock under the surface
      boulder  block id of a rock sitting ON the surface (0 = nothing)
      layered  True where strata should show in the rock below
    """
    steep = np.clip(slope_deg / 20.0, 0.0, 1.0)           # 0 flat .. 1 very steep

    # 1. Fractal roughness: a few cm on flats, a couple of metres on broken slopes.
    rough = fractal(xs, zs, seed)
    elev = elev + rough * (0.35 + 2.6 * steep)

    # 2. Wind ripples, on flat dusty ground only.
    th = np.radians(RIPPLE_BEARING_DEG)
    along = xs[None, :] * np.cos(th) + zs[:, None] * np.sin(th)
    # The ripple field drifts, so crests are not perfectly straight lines.
    drift = fractal(xs, zs, seed + 7, octaves=(220.0, 90.0)) * 4.0
    ripple = np.sin((along + drift) / RIPPLE_WAVELENGTH_M * 2.0 * np.pi)
    dusty_flat = np.clip(1.0 - slope_deg / 6.0, 0.0, 1.0)
    elev = elev + ripple * RIPPLE_AMPLITUDE_M * dusty_flat

    # 3. Small impact craters.
    elev = elev + crater_relief(xs, zs)

    # 4. Surface material. Dust covers the flats; bedrock shows through on slopes.
    #    `cover` is a patchy dust map so the change is ragged, like the real thing.
    cover = noise(xs, zs, 55.0, seed + 11) * 0.5 + noise(xs, zs, 17.0, seed + 12) * 0.5
    bare = (steep * 1.5 + cover - 0.75) > 0.0
    lut = np.array([ID[UNIT_TOP.get(k, "red_sand")] for k in range(256)], dtype=np.uint8)
    rock = lut[unit]
    # Unmapped ground has no named rock type, so use a plain dusty hardpan.
    rock = np.where(unit == 0, np.uint8(ID["terracotta"]), rock).astype(np.uint8)
    top = np.where(bare, rock, np.uint8(ID["red_sand"])).astype(np.uint8)
    # Dark basaltic sand collects in the lowest, flattest patches (like Jezero's dunes).
    dune = (cover > 0.80) & (slope_deg < 3.0)
    top[dune] = ID["packed_mud"]

    under = np.where(bare, np.uint8(ID["red_sandstone"]), np.uint8(ID["red_sand"])).astype(np.uint8)
    under[(~bare) & (cover > 0.5)] = ID["red_sandstone"]

    # 5. Boulders.
    base = np.array([BOULDER_BASE.get(k, 0.004) for k in range(256)], dtype=np.float64)
    chance = base[unit] * (1.0 + 3.0 * steep)
    r = rand2(xs[None, :].astype(np.int64), zs[:, None].astype(np.int64), seed + 99)
    hit = r < chance
    pick = (r / np.maximum(chance, 1e-9) * len(BOULDER_BLOCKS)).astype(np.int64) % len(BOULDER_BLOCKS)
    bl = np.array([ID[b] for b in BOULDER_BLOCKS], dtype=np.uint8)[pick]
    boulder = np.where(hit, bl, np.uint8(0)).astype(np.uint8)

    layered = np.isin(unit, list(LAYERED_UNITS))
    return elev, top, under, boulder, layered
