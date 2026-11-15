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


def main():
    mcp = bridge.Mcp()
    try:
        mcp.call("server_info", {}, timeout=10)
    except OSError:
        sys.exit("Can't reach the mcmcp mod. Open Minecraft (with mcmcp) first, then run this again.")

    if not os.path.exists(MARKER):
        say("First time: making the Jezero world (about 3 minutes) ...")
        if not os.path.exists(os.path.join(bridge.SAVE_DIR, "level.dat")):
            ok, out = mcp.call("create_world", {"name": bridge.SAVE_NAME, "gamemode": "creative",
                                                "difficulty": "peaceful", "type": "flat", "structures": False,
                                                "bonus_chest": False, "allow_commands": True}, timeout=300)
            print("  create_world:", out)
            if not ok:
                sys.exit("  Could not create the world (see above).")
            time.sleep(5)
            mcp.cmd("tp @s 0 200 0")          # so you don't wake up inside the new ground
        else:
            mcp.call("load_world", {"name": bridge.SAVE_NAME}, timeout=300)
            time.sleep(5)
            mcp.cmd("tp @s 0 200 0")
        print("  leave_world:", mcp.call("leave_world", {}, timeout=120)[1])
        time.sleep(5)                         # let Minecraft finish saving and let go of the files
        subprocess.run([sys.executable, os.path.join(jm.HERE, "make_world.py"), "--save", bridge.SAVE_DIR], check=True)
        open(MARKER, "w").write('{"terrain": "Jezero, 1 block = 1 m, made by make_world.py"}\n')
        print("  load_world:", mcp.call("load_world", {"name": bridge.SAVE_NAME}, timeout=600)[1])
        time.sleep(10)
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
