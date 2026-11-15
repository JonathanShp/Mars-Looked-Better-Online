# start.py - one click to play MarsCuff in Minecraft (uses the mcmcp mod).
#
#   python minecraft/start.py      (or double-click "Start MarsCuff Minecraft.bat")
#
# Before you run it: open Minecraft with the mcmcp mod (any world or the title screen).
#
# First time only, it makes the Jezero world:
#   1. mcmcp creates an empty flat world "MarsCuff Jezero" and closes it again
#   2. make_world.py writes real Jezero ground into it: a 3 km circle around the
#      landing site to start with (about 15 s, about 110 MB)
#   3. mcmcp opens it: you spawn at Perseverance's landing site
# After that, every walk you send from the website rebuilds the ground along THAT
# route (about 100 MB), so you never have to wait for the whole 900 km2 map.
#
# Every time: starts the website bridge at http://localhost:8770.

import os
import subprocess
import sys
import time
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge
import jezero_map as jm
import make_world as mw

MARKER = os.path.join(bridge.SAVE_DIR, mw.MARKER)    # "the Jezero ground is in this save"


def say(text):
    print("\n" + text)


def wait_until_in_world(mcp, seconds=240):
    """A big world can still be loading when the mod answers, so wait until the player is really in it."""
    if not bridge.wait_until_in_world(mcp, seconds):
        sys.exit("  The world didn't finish opening in Minecraft. "
                 f"Open '{bridge.SAVE_NAME}' yourself, then run this again.")


def main():
    mcp = bridge.Mcp()
    try:
        mcp.call("server_info", {}, timeout=10)
    except OSError:
        sys.exit("Can't reach the mcmcp mod. Open Minecraft (with mcmcp) first, then run this again.")

    if not os.path.exists(MARKER):
        say("First time: making the Jezero world (about a minute) ...")
        mcp.call("leave_world", {}, timeout=120)          # the mod can only create/open a world from the title screen
        time.sleep(3)
        if not os.path.exists(os.path.join(bridge.SAVE_DIR, "level.dat")):
            ok, out = mcp.call("create_world", {"name": bridge.SAVE_NAME, "gamemode": "creative",
                                                "difficulty": "peaceful", "type": "flat", "structures": False,
                                                "bonus_chest": False, "allow_commands": True}, timeout=300)
            print("  create_world:", out)
            if not ok:
                sys.exit("  Could not create the world (see above).")
        else:
            print("  load_world:", mcp.call("load_world", {"name": bridge.SAVE_NAME}, timeout=300)[1])
        wait_until_in_world(mcp)
        mcp.cmd("tp @s 0 200 0")              # so you don't wake up inside the new ground
        print("  leave_world:", mcp.call("leave_world", {}, timeout=120)[1])
        time.sleep(5)                         # let Minecraft finish saving and let go of the files
        if not os.path.exists(os.path.join(bridge.SAVE_DIR, "level.dat")):
            # The mod never overwrites a folder: if one was in the way it adds a number to the name.
            sys.exit(f"  The new world isn't in '{bridge.SAVE_DIR}'. A folder with that name was probably "
                     "already there, so Minecraft picked another name. Rename or move that folder, then run this again.")
        # No --route yet, so this builds the starter circle around the landing site.
        # make_world.py writes the marker file itself (it holds the height the ground
        # was lined up with), so we must NOT write over it here.
        subprocess.run([sys.executable, os.path.join(jm.HERE, "make_world.py"), "--save", bridge.SAVE_DIR], check=True)
        print("  load_world:", mcp.call("load_world", {"name": bridge.SAVE_NAME}, timeout=600)[1])
        wait_until_in_world(mcp)
        bridge.use_save_elevation()           # use the same heights the ground was built with
        lat, lon = jm.landing_site()
        x, z = jm.block_of_latlon(lat, lon)
        y = bridge.ground(x, z) + 1
        for c in [f"setworldspawn {x} {y} {z}", f"tp @s {x + 0.5} {y} {z + 0.5}", f"spawnpoint @s {x} {y} {z}"]:
            print(" ", c, "->", mcp.cmd(c)[1])
        bridge.mars_rules(mcp)
        built = bridge.world_info().get("corridor") or {}
        print(f"  World ready: {built.get('area_km2', '?')} km2 of Jezero ground around the landing site "
              f"(1 block = 1 m). Send a walk from the website to build the ground along it.")
    else:
        say(f"Jezero world already made. In Minecraft, open the '{bridge.SAVE_NAME}' world.")

    say("=" * 60 + f"\n  READY! Website: http://localhost:{bridge.PORT}\n"
        "  Plan a walk anywhere on the Jezero map, press 'Send to Minecraft'.\n"
        "  It closes the world, builds the ground along your walk, and opens it again.\n"
        "  Close this window to stop the website bridge.\n" + "=" * 60)
    webbrowser.open(f"http://localhost:{bridge.PORT}")
    bridge.MCP = mcp
    bridge.serve()


if __name__ == "__main__":
    main()
