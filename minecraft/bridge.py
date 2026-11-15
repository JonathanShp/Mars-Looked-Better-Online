# bridge.py - connects the MarsCuff website to the Minecraft server.
#
# It does two jobs, only on THIS computer (127.0.0.1, nothing is opened to the network):
#   1. serves the website at http://localhost:8770 (with a "Send to Minecraft" button)
#   2. when that button is pressed, it receives the planned walk and builds it in
#      Minecraft through RCON (the server's remote-command line):
#        * a white beacon + habitat at the base, where you respawn
#        * purple beacons at each station, a red beacon at the Point of No Return
#        * big glowing arrows 20 blocks (200 m) up, every 160 m along the route
#        * the cuff as a written book in your hotbar + a chat link to the full cuff
#
# Usage: python minecraft/bridge.py      (start.py runs it for you)

import json
import math
import os
import random
import socket
import struct
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jezero_map as jm

PORT = 8770
STATE = os.path.join(jm.SERVER_DIR, "marscuff_state.json")     # what we built last time
FUNC_DIR = os.path.join(jm.SERVER_DIR, "world", "datapacks", "marscuff", "data", "marscuff", "function")
ELEV = jm.load_elevation()

ARROW_SPACING = 16        # blocks between arrows (= 160 m)
ARROW_HEIGHT = 20         # blocks above the highest nearby ground (= 200 m)
OUR_BLOCKS = ["iron_block", "beacon", "purple_stained_glass", "red_stained_glass", "sea_lantern",
              "redstone_block", "smooth_stone", "white_concrete", "light_blue_stained_glass", "glowstone"]
# None of OUR_BLOCKS is used by the terrain, so "clear" can never eat real ground.


# ------------------------------------------------------------------ RCON (Minecraft remote commands)
class Rcon:
    """Minimal RCON client: log in once, then send one command at a time."""

    def __init__(self):
        props = read_properties()
        self.port = int(props.get("rcon.port", 25575))
        self.password = props.get("rcon.password", "")
        self.sock = None
        self.lock = threading.Lock()

    def _send(self, kind, body):
        rid = random.randint(1, 2**31 - 1)
        data = struct.pack("<ii", rid, kind) + body.encode("utf-8") + b"\x00\x00"
        self.sock.sendall(struct.pack("<i", len(data)) + data)
        size = struct.unpack("<i", self._read(4))[0]
        resp = self._read(size)
        got_id = struct.unpack("<i", resp[:4])[0]
        return got_id, resp[8:-2].decode("utf-8", "replace")

    def _read(self, n):
        buf = b""
        while len(buf) < n:
            part = self.sock.recv(n - len(buf))
            if not part:
                raise ConnectionError("server closed the connection")
            buf += part
        return buf

    def connect(self):
        self.sock = socket.create_connection(("127.0.0.1", self.port), timeout=10)
        got_id, _ = self._send(3, self.password)
        if got_id == -1:
            raise PermissionError("RCON password rejected")

    def cmd(self, command):
        with self.lock:
            for attempt in range(2):
                try:
                    if self.sock is None:
                        self.connect()
                    return self._send(2, command)[1]
                except (OSError, ConnectionError):
                    self.sock = None
                    if attempt:
                        raise


def read_properties():
    props = {}
    path = os.path.join(jm.SERVER_DIR, "server.properties")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if "=" in line and not line.startswith("#"):
                k, v = line.rstrip("\n").split("=", 1)
                props[k.strip()] = v.strip()
    return props


# ------------------------------------------------------------------ text helpers
def text_json(text, color="white", bold=False):
    """Minecraft text as JSON, ASCII only (\\u escapes) so RCON never garbles symbols."""
    return json.dumps({"text": text, "color": color, "bold": bold}, ensure_ascii=True)


def snbt_quote(s):
    """Put a string inside single quotes for Minecraft's NBT syntax."""
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def wrap_pages(sections, width=19, lines_per_page=13):
    """Book pages hold about 14 lines of 19 characters. Wrap each section and cut into pages."""
    pages = []
    for sec in sections:
        lines = []
        for para in sec.split("\n"):
            words, cur = para.split(" "), ""
            for w in words:
                if len(cur) + len(w) + (1 if cur else 0) > width and cur:
                    lines.append(cur)
                    cur = w
                else:
                    cur = f"{cur} {w}" if cur else w
            lines.append(cur)
        for i in range(0, len(lines), lines_per_page):
            pages.append("\n".join(lines[i:i + lines_per_page]))
    return pages[:100]


# ------------------------------------------------------------------ building plan -> commands
class Build:
    """Collects everything to place, so we can load the chunks first, then place, then remember it."""

    def __init__(self):
        self.setblocks = []     # (x, y, z, block)
        self.fills = []         # (x1, y1, z1, x2, y2, z2, block, mode)
        self.entities = []      # summon commands
        self.columns = set()    # (x, z) of everything, to know which chunks to load

    def setblock(self, x, y, z, block):
        self.setblocks.append((x, y, z, block))
        self.columns.add((x, z))

    def fill(self, x1, y1, z1, x2, y2, z2, block, mode="replace air"):
        self.fills.append((x1, y1, z1, x2, y2, z2, block, mode))
        self.columns.update({(x1, z1), (x2, z2), (x1, z2), (x2, z1)})

    def label(self, x, y, z, lines, color="white", scale=4):
        parts = [{"text": lines[0] + "\n", "color": color, "bold": True}] + \
                [{"text": ln + ("\n" if i < len(lines) - 2 else ""), "color": "white", "bold": False} for i, ln in enumerate(lines[1:])]
        text = json.dumps(parts, ensure_ascii=True)
        self.entities.append(
            f"summon minecraft:text_display {x + 0.5} {y} {z + 0.5} "
            "{Tags:[\"marscuff_route\"],billboard:\"center\",view_range:16f,line_width:220,"
            "brightness:{sky:15,block:15},background:-1610612736,"
            "transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],"
            f"translation:[0f,0f,0f],scale:[{scale}f,{scale}f,{scale}f]}},text:{snbt_quote(text)}}}")
        self.columns.add((x, z))


def max_ground(x, z, r):
    return max(jm.ground_y(ELEV, x + dx, z + dz) for dx in range(-r, r + 1, max(1, r)) for dz in range(-r, r + 1, max(1, r)))


def build_beacon(b, x, z, glass, label_lines, label_color):
    """3x3 iron pyramid + beacon + coloured glass: a tall coloured light beam you can see from far away."""
    ground = [jm.ground_y(ELEV, x + dx, z + dz) for dx in (-1, 0, 1) for dz in (-1, 0, 1)]
    base = max(ground) + 1
    b.fill(x - 1, min(ground) + 1, z - 1, x + 1, base, z + 1, "iron_block")
    b.setblock(x, base + 1, z, "beacon")
    if glass:
        b.setblock(x, base + 2, z, glass)
    b.label(x, base + 9, z, label_lines, label_color)
    return base


def build_habitat(b, x, z):
    """A small white base with blue windows, a light, and a white beacon on the roof."""
    ground = [jm.ground_y(ELEV, x + dx, z + dz) for dx in range(-5, 6) for dz in range(-5, 6)]
    base = max(ground) + 1
    b.fill(x - 5, min(ground) + 1, z - 5, x + 5, base, z + 5, "smooth_stone")           # foundation
    b.fill(x - 4, base + 1, z - 4, x + 4, base + 5, z + 4, "white_concrete", "hollow")   # walls + roof
    for (x1, z1, x2, z2) in [(x - 4, z - 4, x + 4, z - 4), (x - 4, z + 4, x + 4, z + 4),
                             (x - 4, z - 4, x - 4, z + 4), (x + 4, z - 4, x + 4, z + 4)]:
        b.fill(x1, base + 3, z1, x2, base + 3, z2, "light_blue_stained_glass", "replace white_concrete")
    b.fill(x, base + 1, z + 4, x, base + 2, z + 4, "air", "replace white_concrete")      # door, south side
    b.fill(x - 1, base + 5, z - 1, x + 1, base + 5, z + 1, "iron_block", "replace white_concrete")
    b.setblock(x, base + 6, z, "beacon")                                                 # white beam home
    b.setblock(x - 2, base + 5, z - 2, "glowstone")
    b.setblock(x + 2, base + 5, z + 2, "glowstone")
    b.label(x, base + 14, z, ["HABITAT", "MarsCuff base - white beam = home"], "aqua")
    return base


def arrow_blocks(cx, y, cz, dx, dz):
    """Blocks of a flat arrow centred on (cx, cz), pointing along (dx, dz).
    dx, dz are -1, 0 or 1 (8 compass directions), so every line is a clean block line."""
    sign = lambda v: (v > 0) - (v < 0)
    cx, cz = round(cx), round(cz)
    n = 3 if dx and dz else 4                 # diagonal steps are longer, so use fewer
    px, pz = -dz, dx                          # perpendicular direction
    pts = {(cx + dx * s, cz + dz * s) for s in range(-n, n + 1)}       # shaft
    tipx, tipz = cx + dx * n, cz + dz * n
    for side in (1, -1):                      # two head arms going back at 45 degrees
        ax, az = sign(-dx + side * px), sign(-dz + side * pz)
        pts |= {(tipx + ax * k, tipz + az * k) for k in range(1, n + 1)}
    return [(x, y, z) for x, z in pts]


def build_route(plan):
    b = Build()
    hx, hz = jm.block_of_cell(plan["habitat"]["row"], plan["habitat"]["col"])
    hbase = build_habitat(b, hx, hz)
    avoid = [(hx, hz)]

    for k, st in enumerate(plan["stations"]):
        sx, sz = jm.block_of_cell(st["row"], st["col"])
        lines = [f"STATION {k + 1}", st.get("unit") or "unit not mapped",
                 f"arrive {st['arrive']} - leave by {st['leaveBy']}"]
        if st.get("neverDriven"):
            lines.append("* rock Perseverance never drove on")
        if st.get("beyondPnr"):
            lines.append("BEYOND POINT OF NO RETURN - SKIP")
        build_beacon(b, sx, sz, "purple_stained_glass", lines, "light_purple")
        avoid.append((sx, sz))

    pnr = plan.get("pnr")
    if pnr:
        px_, pz_ = jm.block_of_cell(pnr["row"], pnr["col"])
        build_beacon(b, px_, pz_, "red_stained_glass",
                     ["POINT OF NO RETURN", f"EVA {pnr['label']}: past here you can't",
                      "get home with the 20% reserve"], "red")
        avoid.append((px_, pz_))

    # Route polyline in blocks, with "past the PNR?" for each point.
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
        """Position along the route at distance d (blocks)."""
        i = max(0, min(len(pts) - 2, next((j for j in range(1, len(dist)) if dist[j] >= d), len(dist) - 1) - 1))
        seg = dist[i + 1] - dist[i] or 1
        t = min(1, max(0, (d - dist[i]) / seg))
        return (pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t, pts[i][2])

    arrows = 0
    d = ARROW_SPACING / 2
    while len(pts) > 1 and d < dist[-1]:
        x, z, late = point_at(d)
        ax, az, _ = point_at(min(dist[-1], d + 6))
        bx, bz, _ = point_at(max(0, d - 6))
        ang = math.atan2(az - bz, ax - bx)
        ang = round(ang / (math.pi / 4)) * (math.pi / 4)          # snap to 8 compass directions
        dx, dz = round(math.cos(ang)), round(math.sin(ang))
        if all(math.hypot(x - ox, z - oz) > 7 for ox, oz in avoid):  # keep beacon beams clear
            y = max_ground(round(x), round(z), 6) + ARROW_HEIGHT
            for (bx_, by_, bz_) in arrow_blocks(x, y, z, dx, dz):
                b.setblock(bx_, by_, bz_, "redstone_block" if late else "sea_lantern")
            arrows += 1
        d += ARROW_SPACING
    return b, (hx, hbase + 2, hz), arrows


# ------------------------------------------------------------------ running it in Minecraft
# Thousands of blocks are placed per route. Sending them one by one over RCON is
# slow, so we write them into a data-pack "function" (a text file of commands),
# tell Minecraft to reload, and run that function once. Minecraft also checks
# every line of the file when it loads it, so a typo can't half-build a route.

def load_chunks(rcon, columns):
    """Keep the chunks we build in loaded (blocks can only be placed in loaded chunks)."""
    chunks = sorted({(x >> 4, z >> 4) for x, z in columns})
    for cx, cz in chunks:
        rcon.cmd(f"forceload add {cx * 16} {cz * 16}")
    deadline = time.time() + 90
    waiting = list(chunks)
    while waiting and time.time() < deadline:
        waiting = [c for c in waiting if "passed" not in rcon.cmd(f"execute if loaded {c[0] * 16} 0 {c[1] * 16}")]
        if waiting:
            time.sleep(0.5)
    return len(chunks), len(waiting)


def clear_commands(old):
    """Commands that remove only what MarsCuff built last time (recorded in marscuff_state.json)."""
    cmds = ["kill @e[type=minecraft:text_display,tag=marscuff_route]"]
    for x, y, z, blk in old.get("setblocks", []):
        cmds.append(f"fill {x} {y} {z} {x} {y} {z} air replace {blk}")
    for x1, y1, z1, x2, y2, z2, *_ in old.get("fills", []):
        for blk in OUR_BLOCKS:
            cmds.append(f"fill {x1} {y1} {z1} {x2} {y2 + 2} {z2} air replace {blk}")
    return cmds


def old_columns(old):
    cols = [(x, z) for x, _, z, _ in old.get("setblocks", [])]
    for f in old.get("fills", []):
        cols += [(f[0], f[2]), (f[3], f[5]), (f[0], f[5]), (f[3], f[2])]
    return cols


def run_function(rcon, name, lines):
    """Write marscuff:<name> as a data-pack function, reload, run it. Returns Minecraft's answer."""
    os.makedirs(FUNC_DIR, exist_ok=True)
    for f in os.listdir(FUNC_DIR):                       # remove only our own previous route files
        if f.startswith("route_") and f.endswith(".mcfunction"):
            os.remove(os.path.join(FUNC_DIR, f))
    with open(os.path.join(FUNC_DIR, name + ".mcfunction"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    rcon.cmd("reload")
    for _ in range(60):                                  # wait until the reload has finished
        time.sleep(0.5)
        out = rcon.cmd(f"function marscuff:{name}")
        if "nknown" not in out:
            return out
    raise RuntimeError("Minecraft did not accept the route file (see the server window for the line it rejected)")


def setup_world(rcon, info):
    """Mars rules: always day, no weather, no mobs, map-sized world border, spawn at Perseverance's landing site."""
    ls = info["landing_site"]
    for c in ["gamerule doDaylightCycle false", "time set 6000", "gamerule doWeatherCycle false",
              "weather clear", "gamerule doMobSpawning false", "difficulty peaceful",
              "gamerule doInsomnia false", "gamerule spawnRadius 0", "gamerule announceAdvancements false",
              f"setworldspawn {ls['x']} {ls['y']} {ls['z']}",
              f"worldborder center {jm.X_MIN + jm.WIDTH // 2} {jm.Z_MIN + jm.HEIGHT // 2}",
              f"worldborder set {min(jm.WIDTH, jm.HEIGHT)}"]:
        rcon.cmd(c)
    load_chunks(rcon, [(ls["x"], ls["z"])])
    rcon.cmd("kill @e[type=minecraft:text_display,tag=marscuff_landing]")
    rcon.cmd(f"summon minecraft:text_display {ls['x'] + 0.5} {ls['y'] + 6} {ls['z'] + 0.5} "
             "{Tags:[\"marscuff_landing\"],billboard:\"center\",view_range:16f,brightness:{sky:15,block:15},"
             "transformation:{left_rotation:[0f,0f,0f,1f],right_rotation:[0f,0f,0f,1f],translation:[0f,0f,0f],"
             "scale:[3f,3f,3f]},text:"
             + snbt_quote(text_json("Perseverance landing site (Feb 2021)\nThe brown line = its real tracks", "gold"))
             + "}")
    rcon.cmd("forceload remove all")


def send_route(rcon, plan):
    log = []
    old = json.load(open(STATE)) if os.path.exists(STATE) else {}
    b, spawn, arrows = build_route(plan)
    n_chunks, slow = load_chunks(rcon, set(b.columns) | set(old_columns(old)))
    log.append(f"loaded {n_chunks} chunks ({slow} still loading)")

    sx, sy, sz = spawn
    s = plan["summary"]
    pages = wrap_pages(plan["book"])
    page_list = ",".join(snbt_quote(json.dumps({"text": p}, ensure_ascii=True)) for p in pages)
    lines = ["# MarsCuff route, written by bridge.py"] + clear_commands(old)
    lines += [f"fill {x1} {y1} {z1} {x2} {y2} {z2} {blk} {mode}" for x1, y1, z1, x2, y2, z2, blk, mode in b.fills]
    lines += [f"setblock {x} {y} {z} {blk}" for x, y, z, blk in b.setblocks]
    lines += b.entities
    lines += [
        "gamemode creative @a",
        f"spawnpoint @a {sx} {sy} {sz}",
        f"tp @a {sx + 0.5} {sy} {sz + 0.5} 0 0",
        "clear @a minecraft:written_book",
        f"give @a minecraft:written_book[minecraft:written_book_content={{title:'MarsCuff EVA cuff',"
        f"author:\"MarsCuff\",pages:[{page_list}]}}] 1",
        "title @a times 10 80 20",
        "title @a subtitle " + text_json("Follow the glowing arrows. Your cuff is the book.", "white"),
        "title @a title " + text_json("Welcome to Jezero Crater", "gold", True),
        "tellraw @a " + json.dumps([
            {"text": "MarsCuff: ", "color": "gold", "bold": True},
            {"text": f"{s['km']} km walk, {s['total']} of {s['usable']} usable. "
                     f"{'Fits.' if s['fits'] else 'TOO LONG.'} "
                     "White beam = home, purple = stations, red = Point of No Return. ",
             "color": "white", "bold": False},
            {"text": "[Open the cuff in your browser]", "color": "aqua", "underlined": True, "bold": False,
             "clickEvent": {"action": "open_url", "value": f"http://localhost:{PORT}/#cuff"}}], ensure_ascii=True),
    ]
    log.append(run_function(rcon, f"route_{int(time.time())}", lines))
    rcon.cmd("forceload remove all")
    json.dump({"setblocks": b.setblocks, "fills": b.fills}, open(STATE, "w"))
    json.dump(plan, open(os.path.join(jm.SERVER_DIR, "marscuff_last_plan.json"), "w"))
    msg = (f"Built in Minecraft: habitat, {len(plan['stations'])} station beacons, {arrows} arrows"
           f"{', PNR beacon' if plan.get('pnr') else ''}; cuff book given ({len(pages)} pages). "
           "You are now in the habitat.")
    return msg, log


# ------------------------------------------------------------------ web server
RCON = None
INFO = None
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
        if self.path == "/api/status":
            try:
                players = RCON.cmd("list")
                return self.reply(200, {"ok": True, "players": players})
            except Exception as e:
                return self.reply(200, {"ok": False, "error": f"Minecraft server not reachable: {e}"})
        if self.path == "/api/last-plan":
            p = os.path.join(jm.SERVER_DIR, "marscuff_last_plan.json")
            return self.reply(200, json.load(open(p)) if os.path.exists(p) else {})
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/route":
            return self.reply(404, {"ok": False})
        plan = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        if not BUSY.acquire(blocking=False):
            return self.reply(409, {"ok": False, "message": "Still building the last route, wait a moment."})
        try:
            msg, log = send_route(RCON, plan)
            print(msg, *log, sep="\n  ")
            return self.reply(200, {"ok": True, "message": msg})
        except Exception as e:
            print("ERROR:", e)
            return self.reply(500, {"ok": False, "message": f"Could not build it in Minecraft: {e}"})
        finally:
            BUSY.release()


def main():
    global RCON, INFO
    INFO = json.load(open(os.path.join(jm.SERVER_DIR, "world_info.json")))
    RCON = Rcon()
    for _ in range(120):                         # the server may still be starting
        try:
            RCON.connect()
            break
        except OSError:
            time.sleep(2)
    setup_world(RCON, INFO)
    print(f"MarsCuff bridge ready: open http://localhost:{PORT} and press 'Send to Minecraft'.")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
