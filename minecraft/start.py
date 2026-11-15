# start.py - one click to play MarsCuff in Minecraft (uses the mcmcp mod).
#
#   python minecraft/start.py      (or double-click "Start MarsCuff Minecraft.bat")
#
# Before you run it: open Minecraft with the mcmcp mod (any world or the title screen).
#
# First time only, it makes the Jezero world:
#   1. mcmcp creates an empty flat world "MarsCuff Jezero" and closes it again
#   2. make_world.py writes the real Jezero ground into it (~2 min, ~1.5 GB)
#   3. mcmcp opens it: you spawn at Perseverance's landing site
# Every time: starts the website bridge at http://localhost:8770.

import os
import subprocess
import sys
import time
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge
import jezero_map as jm

MARKER = os.path.join(bridge.SAVE_DIR, "marscuff_terrain.json")    # "the Jezero ground is in this save"


def say(text):
    print("\n" + text)


def wait_until_in_world(mcp, seconds=180):
    """A big world can still be loading when the mod answers, so try a harmless command until it works."""
    for _ in range(seconds // 3):
        time.sleep(3)
        try:
            if mcp.cmd("time query gametime")[0]:
                return
        except OSError:
            pass                              # the mod is busy loading: try again
    sys.exit("  The world didn't finish opening in Minecraft. Open 'MarsCuff Jezero' yourself, then run this again.")


def main():
    mcp = bridge.Mcp()
    try:
        mcp.call("server_info", {}, timeout=10)
    except OSError:
        sys.exit("Can't reach the mcmcp mod. Open Minecraft (with mcmcp) first, then run this again.")

    if not os.path.exists(MARKER):
        say("First time: making the Jezero world (about 3 minutes) ...")
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
        subprocess.run([sys.executable, os.path.join(jm.HERE, "make_world.py"), "--save", bridge.SAVE_DIR], check=True)
        open(MARKER, "w").write('{"terrain": "Jezero, 1 block = 1 m, made by make_world.py"}\n')
        print("  load_world:", mcp.call("load_world", {"name": bridge.SAVE_NAME}, timeout=600)[1])
        wait_until_in_world(mcp)
        info = jm.describe()
        lat, lon = jm.landing_site()
        x, z = jm.block_of_latlon(lat, lon)
        y = jm.ground_y(bridge.ELEV, x, z) + 1
        for c in [f"setworldspawn {x} {y} {z}", f"tp @s {x + 0.5} {y} {z + 0.5}", f"spawnpoint @s {x} {y} {z}"]:
            print(" ", c, "->", mcp.cmd(c)[1])
        bridge.mars_rules(mcp)
        print("  World ready:", info["area"])
    else:
        say(f"Jezero world already made. In Minecraft, open the '{bridge.SAVE_NAME}' world.")

    say("=" * 60 + f"\n  READY! Website: http://localhost:{bridge.PORT}\n"
        "  Plan a walk inside the yellow square, press 'Send to Minecraft'.\n"
        "  Close this window to stop the website bridge.\n" + "=" * 60)
    webbrowser.open(f"http://localhost:{bridge.PORT}")
    bridge.MCP = mcp
    bridge.serve()


if __name__ == "__main__":
    main()
