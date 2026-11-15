# bridge.py - connects the MarsCuff website to Minecraft through the mcmcp mod.
#
# It runs on the computer that has Minecraft (with the mcmcp mod) and only
# listens on this computer (127.0.0.1):
#   1. serves the website at http://localhost:8770 (with a "Send to Minecraft" button)
#   2. when that button is pressed it does two things, in this order:
#        a. GROUND: closes the world, runs make_world.py for THIS route, and opens
#           the world again. Only the ground within ~500 m of the planned walk is
#           built (800 m around the habitat and the stations), so a walk costs about
#           100 MB instead of the 14 GB the whole 900 km2 map would need.
#           Minecraft locks the region files while a world is open, which is why
#           the world has to be closed for this step.
#        b. MARKERS: builds the walk itself in that fresh ground:
#             * a habitat with a white beacon (home), where you respawn
#             * purple beacons + signs at each station, a red beacon at the Point of No Return
#             * big glowing arrows 25 m up, every 40 m along the route (red past the PNR)
#             * the cuff as a written book in your hand + a chat link to the full cuff
#
# How it talks to Minecraft: mcmcp is an MCP server inside the game at
# http://127.0.0.1:25599/mcp. We call four of its tools:
#   build_structure  - places thousands of blocks in one call (boxes and lines)
#   run_command      - one game command (max 256 characters)
#   leave_world      - back to the title screen (so the region files are free)
#   load_world       - open a save by name
# The access token is read from mcmcp's own config file on this PC and never
# leaves it.

import json
import math
import os
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jezero_map as jm
import make_world as mw

PORT = 8770
MC_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), ".minecraft")
SAVE_NAME = "MarsCuff Jezero"
SAVE_DIR = os.environ.get("MARSCUFF_SAVE_DIR") or os.path.join(MC_DIR, "saves", SAVE_NAME)
STATE = os.path.join(SAVE_DIR, "marscuff_route.json")         # what we built last time
LAST_PLAN = os.path.join(SAVE_DIR, "marscuff_last_plan.json")
PLAN_FILE = os.path.join(SAVE_DIR, "marscuff_plan_in.json")   # the plan we hand to make_world.py
INFO_FILE = os.path.join(SAVE_DIR, "world_info.json")         # what make_world.py built last

ARROW_SPACING = 40        # blocks between arrows (= 40 m, since 1 block = 1 m)
ARROW_HEIGHT = 25         # blocks above the highest nearby ground (= 25 m)


# ------------------------------------------------------------------ talking to mcmcp
class Mcp:
    """Calls mcmcp's tools over plain HTTP JSON-RPC (no session needed)."""

    def __init__(self):
        self.url = "http://127.0.0.1:25599/mcp"
        self.token = os.environ.get("MCMCP_TOKEN") or self._read_token()
        self.n = 0

    def _read_token(self):
        cfg_path = os.path.join(MC_DIR, "config", "mcmcp.json")
        cfg = json.load(open(cfg_path, encoding="utf-8"))
        if "port" in cfg:
            self.url = f"http://127.0.0.1:{cfg['port']}/mcp"
        for k, v in cfg.items():
            if "token" in k.lower() and isinstance(v, str):
                return v
        raise RuntimeError(f"no token found in {cfg_path}")

    def call(self, tool, arguments, timeout=120):
        """Run one tool; returns (ok, text)."""
        self.n += 1
        body = json.dumps({"jsonrpc": "2.0", "id": self.n, "method": "tools/call",
                           "params": {"name": tool, "arguments": arguments}}).encode()
        req = urllib.request.Request(self.url, data=body, method="POST", headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"})
        resp = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        if "error" in resp:
            return False, json.dumps(resp["error"])
        res = resp["result"]
        text = " ".join(c.get("text", "") for c in res.get("content", []))
        return not res.get("isError", False), text

    def cmd(self, command):
        """One game command. Returns (ok, Minecraft's answer)."""
        command = command.lstrip("/")
        if len(command) > 256:
            return False, f"command too long ({len(command)} > 256): {command[:60]}..."
        ok, text = self.call("run_command", {"command": command})
        bad = any(w in text for w in ("Unknown", "Incorrect", "Expected", "Invalid", "Can't", "No entity", "not loaded",
                                       "Failed to parse", "No key", "<--[HERE]"))
        return ok and not bad, text


# ------------------------------------------------------------------ text helpers
def snbt_str(s):
    """A Minecraft NBT string in double quotes (escapes \\ " and new lines)."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def wrap_pages(sections, width=19, lines_per_page=5):
    """Wrap each section into lines of ~19 characters and cut into short pages.
    (Pages are short because every page goes into one 256-character command.)"""
    pages = []
    for sec in sections:
        lines = []
        for para in sec.split("\n"):
            cur = ""
            for w in para.split(" "):
                if cur and len(cur) + 1 + len(w) > width:
                    lines.append(cur)
                    cur = w
                else:
                    cur = f"{cur} {w}" if cur else w
            lines.append(cur)
        for i in range(0, len(lines), lines_per_page):
            pages.append("\n".join(lines[i:i + lines_per_page]))
    return pages[:100]


# ------------------------------------------------------------------ what to build
class Build:
    """Collects block parts (for build_structure) and floating signs (for run_command)."""

    def __init__(self):
        self.parts = []     # {"shape": "box"|"line", "from": [x,y,z], "to": [x,y,z], "block": ...}
        self.labels = []    # (x, y, z, title, [lines], colour)

    def box(self, a, b, block, hollow=False):
        p = {"shape": "box", "from": list(a), "to": list(b), "block": block}
        if hollow:
            p["hollow"] = True
        self.parts.append(p)

    def line(self, a, b, block):
        self.parts.append({"shape": "line", "from": list(a), "to": list(b), "block": block})

    def label(self, x, y, z, title, lines, colour):
        self.labels.append((x, y, z, title, lines, colour))


# ------------------------------------------------------------------ how high is the ground?
# The markers (habitat, beacons, arrows) have to sit on the ground that make_world.py
# actually built, which is the NASA elevation PLUS the small craters, sand ripples and
# boulders that surface.py adds. So we ask make_world.py for the very same block heights
# it wrote, instead of guessing from the elevation grid. mw.columns() works on whole
# patches, so we fetch a 24x24 patch at a time and remember it.
_GROUND = {}            # (x, z) -> block y of the ground surface


def use_save_elevation(root=SAVE_DIR):
    """Line our heights up with the save: every world pins one Mars elevation to y = Y_BASE."""
    base = mw.stored_base(root)
    if base is not None:
        jm.set_elevation_base(base)
    _GROUND.clear()
    return base


def ground(x, z):
    """Block y of the ground at this block, the same number make_world.py wrote."""
    x, z = int(round(x)), int(round(z))
    if (x, z) not in _GROUND:
        x0, z0 = x - 8, z - 8
        g = mw.columns(x0, z0, 24, 24)[0]
        for dz in range(24):
            for dx in range(24):
                _GROUND[(x0 + dx, z0 + dz)] = int(g[dz, dx])
    return _GROUND[(x, z)]


def max_ground(x, z, r):
    return max(ground(x + dx, z + dz) for dx in (-r, 0, r) for dz in (-r, 0, r))


def build_beacon(b, x, z, glass, title, lines, colour):
    """3x3 iron base + beacon + coloured glass = a tall coloured light beam."""
    base = max(ground(x + dx, z + dz) for dx in (-1, 0, 1) for dz in (-1, 0, 1)) + 1
    for dx in (-1, 0, 1):                      # fill under each column (only air, never the ground)
        for dz in (-1, 0, 1):
            g = ground(x + dx, z + dz)
            if g + 1 <= base:
                b.box((x + dx, g + 1, z + dz), (x + dx, base, z + dz), "iron_block")
    b.box((x, base + 1, z), (x, base + 1, z), "beacon")
    if glass:
        b.box((x, base + 2, z), (x, base + 2, z), glass)
    b.label(x, base + 9, z, title, lines, colour)


def build_habitat(b, x, z):
    """A small white base with blue windows, lights and a white beacon on the roof."""
    base = max(ground(x + dx, z + dz) for dx in range(-5, 6) for dz in range(-5, 6)) + 1
    for dx in range(-5, 6):                    # foundation, only where there is air
        for dz in range(-5, 6):
            g = ground(x + dx, z + dz)
            if g + 1 <= base:
                b.box((x + dx, g + 1, z + dz), (x + dx, base, z + dz), "smooth_stone")
    b.box((x - 4, base + 1, z - 4), (x + 4, base + 5, z + 4), "white_concrete", hollow=True)
    b.box((x - 4, base + 3, z - 4), (x + 4, base + 3, z - 4), "light_blue_stained_glass")   # windows
    b.box((x - 4, base + 3, z + 4), (x + 4, base + 3, z + 4), "light_blue_stained_glass")
    b.box((x - 4, base + 3, z - 4), (x - 4, base + 3, z + 4), "light_blue_stained_glass")
    b.box((x + 4, base + 3, z - 4), (x + 4, base + 3, z + 4), "light_blue_stained_glass")
    b.box((x, base + 1, z + 4), (x, base + 2, z + 4), "air")                                # door (south)
    b.box((x - 1, base + 5, z - 1), (x + 1, base + 5, z + 1), "iron_block")                 # beacon base
    b.box((x, base + 6, z), (x, base + 6, z), "beacon")                                     # white beam
    b.box((x - 2, base + 5, z - 2), (x - 2, base + 5, z - 2), "glowstone")
    b.box((x + 2, base + 5, z + 2), (x + 2, base + 5, z + 2), "glowstone")
    b.label(x, base + 14, z, "HABITAT", ["white beam = home"], "aqua")
    return base


def arrow_lines(cx, y, cz, dx, dz):
    """Three straight lines (shaft + 2 head arms) of a flat arrow pointing along (dx, dz).
    dx, dz are -1, 0 or 1 (8 compass directions)."""
    sign = lambda v: (v > 0) - (v < 0)
    cx, cz = round(cx), round(cz)
    n = 3 if dx and dz else 4                  # diagonal steps are longer, so use fewer
    px, pz = -dz, dx                           # perpendicular
    tip = (cx + dx * n, y, cz + dz * n)
    lines = [((cx - dx * n, y, cz - dz * n), tip)]
    for side in (1, -1):
        ax, az = sign(-dx + side * px), sign(-dz + side * pz)
        lines.append((tip, (tip[0] + ax * n, y, tip[2] + az * n)))
    return lines


class OutsideArea(Exception):
    pass


def build_route(plan):
    spots = [("The habitat", plan["habitat"])] + [(f"Station {k + 1}", s) for k, s in enumerate(plan["stations"])]
    # The whole NASA map is available now, so the only way to be "outside" is to be off
    # the map itself (the ground data simply stops there).
    outside = [name for name, c in spots if not jm.on_map(*jm.block_of_cell(c["row"], c["col"]), margin_m=8)]
    if outside:
        one = len(outside) == 1
        raise OutsideArea(f"{', '.join(outside)} {'is' if one else 'are'} off the edge of the Jezero map "
                          f"(there is no NASA terrain data past it). Move {'it' if one else 'them'} back "
                          f"onto the map and send again.")
    b = Build()
    hx, hz = jm.block_of_cell(plan["habitat"]["row"], plan["habitat"]["col"])
    hbase = build_habitat(b, hx, hz)
    avoid = [(hx, hz)]

    for k, st in enumerate(plan["stations"]):
        sx, sz = jm.block_of_cell(st["row"], st["col"])
        lines = [st.get("unit") or "rock not mapped", f"arrive {st['arrive']}, leave by {st['leaveBy']}"]
        if st.get("neverDriven"):
            lines.append("* Perseverance never drove here")
        if st.get("beyondPnr"):
            lines.append("BEYOND PNR - SKIP")
        build_beacon(b, sx, sz, "purple_stained_glass", f"STATION {k + 1}", lines, "light_purple")
        avoid.append((sx, sz))

    pnr = plan.get("pnr")
    if pnr and jm.on_map(*jm.block_of_cell(pnr["row"], pnr["col"]), margin_m=8):
        px_, pz_ = jm.block_of_cell(pnr["row"], pnr["col"])
        build_beacon(b, px_, pz_, "red_stained_glass", "POINT OF NO RETURN",
                     [f"EVA {pnr['label']}: past here you", "can't get home with the reserve"], "red")
        avoid.append((px_, pz_))

    # Route as a line of block points, each marked "past the PNR?" or not.
    pts = []
    for row, col, clock in plan["path"]:
        x, z = jm.block_of_cell(row, col)
        late = pnr is not None and clock > pnr["clock"]
        if not pts or (x, z) != pts[-1][:2]:
            pts.append((x, z, late))
    dist = [0.0]
    for (x0, z0, _), (x1, z1, _) in zip(pts, pts[1:]):
        dist.append(dist[-1] + math.hypot(x1 - x0, z1 - z0))

    def point_at(d):
        i = max(0, min(len(pts) - 2, next((j for j in range(1, len(dist)) if dist[j] >= d), len(dist) - 1) - 1))
        t = min(1, max(0, (d - dist[i]) / ((dist[i + 1] - dist[i]) or 1)))
        return (pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t, pts[i][2])

    arrows = 0
    d = ARROW_SPACING / 2
    while len(pts) > 1 and d < dist[-1]:
        x, z, late = point_at(d)
        ax, az, _ = point_at(min(dist[-1], d + 6))
        bx, bz, _ = point_at(max(0, d - 6))
        ang = round(math.atan2(az - bz, ax - bx) / (math.pi / 4)) * (math.pi / 4)   # 8 directions
        dx, dz = round(math.cos(ang)), round(math.sin(ang))
        if jm.on_map(round(x), round(z), margin_m=6) and all(math.hypot(x - ox, z - oz) > 7 for ox, oz in avoid):
            y = max_ground(round(x), round(z), 6) + ARROW_HEIGHT
            for a, c in arrow_lines(x, y, z, dx, dz):
                b.line(a, c, "redstone_block" if late else "sea_lantern")
            arrows += 1
        d += ARROW_SPACING
    return b, (hx, hbase + 2, hz), arrows


# ------------------------------------------------------------------ doing it in Minecraft
def load_chunks(mcp, spots):
    """Signs (entities) can only be added/removed where the world is loaded, so load those chunks."""
    chunks = sorted({(x >> 4, z >> 4) for x, z in spots})
    for cx, cz in chunks:
        mcp.cmd(f"forceload add {cx * 16} {cz * 16}")
    waiting, deadline = list(chunks), time.time() + 30
    while waiting and time.time() < deadline:
        waiting = [c for c in waiting if "passed" not in mcp.cmd(f"execute if loaded {c[0] * 16} 0 {c[1] * 16}")[1]]
        if waiting:
            time.sleep(0.5)


def summon_label(mcp, x, y, z, title, lines, colour, errors):
    """A floating sign, in 4 short commands (each must fit in 256 characters)."""
    sel = "@n[type=minecraft:text_display,tag=mc_new]"       # @n = nearest one (tested in 26.3)
    steps = [
        f"summon minecraft:text_display {x + 0.5} {y} {z + 0.5} {{Tags:[\"marscuff_route\",\"mc_new\"],"
        "billboard:\"center\",view_range:16f,brightness:{sky:15,block:15},background:-1610612736}",
        f"data merge entity {sel} {{line_width:240,transformation:{{scale:[4f,4f,4f]}}}}",   # 4x bigger
    ]
    body = "\n".join(lines)
    while True:
        text = (f"data merge entity {sel} {{text:[{{text:{snbt_str(title + chr(10))},color:\"{colour}\",bold:true}},"
                f"{{text:{snbt_str(body)},color:\"white\",bold:false}}]}}")
        if len(text) <= 256 or not body:
            break
        body = body[:-8]                                  # too long: shorten the small print
    steps += [text, "tag @e[type=minecraft:text_display,tag=mc_new] remove mc_new"]
    for c in steps:
        ok, out = mcp.cmd(c)
        if not ok:
            errors.append(f"{c[:40]}... -> {out}")


def give_cuff_book(mcp, pages, errors):
    """The cuff as a written book in your hand: first page with the book, then one page per command."""
    first = (f"item replace entity @s weapon.mainhand with minecraft:written_book[minecraft:written_book_content="
             f"{{title:\"MarsCuff EVA cuff\",author:\"MarsCuff\",pages:[{{text:{snbt_str(pages[0])}}}]}}]")
    ok, out = mcp.cmd(first)
    if not ok:
        errors.append(f"book -> {out}")
        return 0
    n = 1
    for p in pages[1:]:
        ok, out = mcp.cmd(f"item modify entity @s weapon.mainhand {{type:\"minecraft:set_written_book_pages\","
                          f"pages:[{{text:{snbt_str(p)}}}],mode:\"append\"}}")
        if not ok:
            errors.append(f"book page -> {out}")
            break
        n += 1
    return n


def world_info():
    """What make_world.py built last time (corridor size, elevation anchor, ...)."""
    try:
        return json.load(open(INFO_FILE, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def corridor_border():
    """worldborder commands that fence you into the ground that actually exists.

    make_world.py writes the corridor's block box into world_info.json. The border
    is the box, so walking out of the built ground is impossible instead of a
    surprise cliff into the void. If we have no box, leave the border alone.
    """
    box = (world_info().get("corridor") or {}).get("blocks_box")
    if not box:
        return []
    x0, z0, x1, z1 = box
    return [f"worldborder center {(x0 + x1) // 2} {(z0 + z1) // 2}",
            f"worldborder set {max(64, min(x1 - x0, z1 - z0))}"]


def mars_rules(mcp):
    """Always day, clear sky, no mobs, Mars gravity. (Names checked live in Minecraft 26.3.)"""
    # Mars g = 3.71 m/s^2 = 0.378 x Earth (NASA Mars Fact Sheet). Minecraft's gravity 0.08 x 0.378 = 0.0302.
    for c in ["gamerule advance_time false", "gamerule advance_weather false",
              "gamerule spawn_mobs false", "gamerule respawn_radius 0",
              "attribute @s minecraft:gravity base set 0.0302",
              "attribute @s minecraft:safe_fall_distance base set 7.9",
              "time set noon", "weather clear", "difficulty peaceful"] + corridor_border():
        mcp.cmd(c)


# ------------------------------------------------------------------ phase a: the ground
def wait_until_in_world(mcp, seconds=240):
    """Wait for the world to finish opening (the title screen counts as 'paused')."""
    for _ in range(max(1, seconds // 3)):
        time.sleep(3)
        try:
            ok, text = mcp.call("get_player_state", {}, timeout=30)
        except OSError:
            continue                       # the game is busy loading; ask again
        if ok and "game is paused" not in text:
            return True
    return False


def route_signature(plan):
    """The part of a plan that decides which ground has to exist."""
    return {"habitat": [plan["habitat"]["row"], plan["habitat"]["col"]],
            "stations": [[s["row"], s["col"]] for s in plan["stations"]],
            "pnr": [plan["pnr"]["row"], plan["pnr"]["col"]] if plan.get("pnr") else None,
            "path": [[row, col] for row, col, _ in plan["path"]]}


def ground_is_current(plan):
    """True if the ground in the save was already built for exactly this walk."""
    if not os.path.exists(os.path.join(SAVE_DIR, mw.MARKER)):
        return False
    try:
        return json.load(open(PLAN_FILE, encoding="utf-8")).get("_signature") == route_signature(plan)
    except (OSError, ValueError):
        return False


def generate_ground(mcp, plan):
    """Build the Mars ground around THIS walk, and nothing else.

    Minecraft keeps the region files open while a world is loaded, so the only way
    to write new ground is: leave the world -> write it -> load the world again.
    Takes about 20-30 s for a normal walk (about 100 MB of chunks).
    """
    if ground_is_current(plan):
        print("  ground: already built for this walk, keeping it")
        return False

    print("  ground: closing the world so the chunk files are free ...")
    mcp.call("leave_world", {}, timeout=120)
    time.sleep(5)                          # let Minecraft finish saving and let go

    os.makedirs(SAVE_DIR, exist_ok=True)
    payload = dict(plan)
    payload["_signature"] = route_signature(plan)
    json.dump(payload, open(PLAN_FILE, "w", encoding="utf-8"))

    print("  ground: writing the terrain around the route ...")
    subprocess.run([sys.executable, os.path.join(jm.HERE, "make_world.py"),
                    "--route", PLAN_FILE, "--save", SAVE_DIR], check=True)

    print("  ground: opening the world again ...")
    ok, out = mcp.call("load_world", {"name": SAVE_NAME}, timeout=600)
    if not ok:
        raise RuntimeError(f"could not re-open the world: {out}")
    if not wait_until_in_world(mcp):
        raise RuntimeError(f"the world did not finish opening - open '{SAVE_NAME}' yourself and send again")

    # The new chunk files replaced the old ones, so last route's markers are gone too.
    use_save_elevation()
    if os.path.exists(STATE):
        os.remove(STATE)
    info = world_info().get("corridor") or {}
    print("  ground: %s chunks, %s km2" % (info.get("chunks", "?"), info.get("area_km2", "?")))
    return True


# ------------------------------------------------------------------ phase b: the markers
def send_route(mcp, plan):
    errors = []
    os.makedirs(SAVE_DIR, exist_ok=True)
    rebuilt = generate_ground(mcp, plan)
    old = {} if rebuilt else (json.load(open(STATE)) if os.path.exists(STATE) else {})
    b, spawn, arrows = build_route(plan)

    # 1. Blocks: first turn last route's blocks back into air, then build the new ones. One call.
    parts = [{**p, "block": "air", "hollow": False} for p in old.get("parts", []) if p["block"] != "air"]
    parts += b.parts
    ok, out = mcp.call("build_structure", {"name": "MarsCuff route", "origin": [0, 0, 0], "parts": parts})
    if not ok:
        raise RuntimeError(f"build_structure failed: {out}")
    print("  blocks:", out)

    # 2. Floating signs: remove the old ones, add the new ones (their chunks must be loaded).
    load_chunks(mcp, [(l[0], l[2]) for l in old.get("labels", [])] + [(l[0], l[2]) for l in b.labels])
    mcp.cmd("kill @e[type=minecraft:text_display,tag=marscuff_route]")
    for lab in b.labels:
        summon_label(mcp, *lab, errors)
    mcp.cmd("forceload remove all")
    json.dump({"parts": b.parts, "labels": b.labels}, open(STATE, "w"))

    # 3. You: Mars rules, into the habitat, respawn there, cuff book in hand.
    mars_rules(mcp)
    sx, sy, sz = spawn
    for c in ["gamemode creative @s", f"tp @s {sx + 0.5} {sy} {sz + 0.5} 0 0", f"spawnpoint @s {sx} {sy} {sz}"]:
        ok, out = mcp.cmd(c)
        if not ok:
            errors.append(f"{c} -> {out}")
    pages = wrap_pages(plan["book"])
    n_pages = give_cuff_book(mcp, pages, errors)
    s = plan["summary"]
    mcp.cmd("title @s times 10 80 20")
    mcp.cmd("title @s subtitle {text:\"Follow the glowing arrows. Your cuff is the book.\"}")
    mcp.cmd("title @s title {text:\"Welcome to Jezero Crater\",color:\"gold\"}")
    mcp.cmd(f"tellraw @s [{{text:\"MarsCuff: \",color:\"gold\"}},{{text:\"{s['km']} km, {s['total']} of "
            f"{s['usable']} usable. {'Fits.' if s['fits'] else 'TOO LONG.'}\"}}]")
    mcp.cmd("tellraw @s {text:\"White beam = home, purple = stations, red = Point of No Return.\"}")
    mcp.cmd(f"tellraw @s {{text:\"[Open the full cuff]\",color:\"aqua\",underlined:true,"
            f"click_event:{{action:\"open_url\",url:\"http://localhost:{PORT}/#cuff\"}}}}")
    json.dump(plan, open(LAST_PLAN, "w"))

    msg = (f"Built in Minecraft: habitat, {len(plan['stations'])} station beacons, {arrows} arrows"
           f"{', PNR beacon' if b.labels and b.labels[-1][3].startswith('POINT') else ''}; "
           f"cuff book in your hand ({n_pages} pages). You are now in the habitat.")
    if errors:
        msg += f" {len(errors)} step(s) failed - see the bridge window."
        print("  FAILED STEPS:", *errors, sep="\n   ")
    return msg


# ------------------------------------------------------------------ web server
MCP = None
BUSY = threading.Lock()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=jm.WEB, **k)

    def log_message(self, fmt, *args):
        pass                                    # keep the window quiet

    def reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/area":
            # The whole map can be played now, so the website no longer draws a box.
            # It just needs the scale, the corridor widths, and what was built last time.
            d = jm.describe()
            return self.reply(200, {"bounds_deg": d["bounds_deg"], "scale": d["scale"],
                                    "whole_map": True,
                                    "corridor_radius_m": mw.CORRIDOR_RADIUS_M,
                                    "station_radius_m": mw.STATION_RADIUS_M,
                                    "built": world_info().get("corridor") or {}})
        if self.path == "/api/last-plan":
            return self.reply(200, json.load(open(LAST_PLAN)) if os.path.exists(LAST_PLAN) else {})
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/route":
            return self.reply(404, {"ok": False})
        plan = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        if not BUSY.acquire(blocking=False):
            return self.reply(409, {"ok": False, "message": "Still building the last route, wait a moment."})
        try:
            msg = send_route(MCP, plan)
            print(msg)
            return self.reply(200, {"ok": True, "message": msg})
        except OutsideArea as e:
            return self.reply(200, {"ok": False, "message": str(e)})
        except Exception as e:
            print("ERROR:", e)
            return self.reply(500, {"ok": False, "message": f"Could not build it in Minecraft: {e}. "
                                                            f"Is Minecraft open in the '{SAVE_NAME}' world?"})
        finally:
            BUSY.release()


def serve():
    global MCP
    MCP = MCP or Mcp()
    print(f"MarsCuff bridge ready: http://localhost:{PORT}  (plan a walk, press 'Send to Minecraft')")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    serve()
