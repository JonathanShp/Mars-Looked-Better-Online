# start.py - one click to play MarsCuff in Minecraft.
#
#   python minecraft/start.py      (or double-click "Start MarsCuff Minecraft.bat")
#
# Steps (each one is skipped if it was already done):
#   1. build the Jezero world from the NASA data      (make_world.py, ~1 min)
#   2. find Java 21 (Minecraft's own copy is fine)
#   3. download the OFFICIAL Minecraft 1.21.1 server from Mojang and check its fingerprint (SHA-1)
#   4. ask YOU to accept the Minecraft EULA (we never accept it for you)
#   5. start the server (only reachable from this computer) and the website bridge
# Then: Minecraft 1.21.1 -> Multiplayer -> Direct Connection -> localhost

import glob
import hashlib
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jezero_map as jm

MC_VERSION = "1.21.1"
MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"   # Mojang's official list
SERVER_JAR = os.path.join(jm.SERVER_DIR, f"minecraft_server_{MC_VERSION}.jar")

PROPERTIES = """# Written by MarsCuff start.py
server-ip=127.0.0.1
server-port=25565
enable-rcon=true
rcon.port=25575
rcon.password={password}
broadcast-rcon-to-ops=false
motd=MarsCuff - Jezero Crater, Mars (1 block = 10 m)
level-name=world
level-type=minecraft\\:flat
generator-settings={{"layers":[{{"block":"minecraft:bedrock","height":1}},{{"block":"minecraft:smooth_basalt","height":60}},{{"block":"minecraft:red_sandstone","height":3}},{{"block":"minecraft:red_sand","height":1}}],"biome":"minecraft:desert","structure_overrides":[]}}
generate-structures=false
gamemode=creative
difficulty=peaceful
spawn-monsters=false
allow-flight=true
spawn-protection=0
max-players=4
view-distance=16
simulation-distance=8
online-mode=true
enforce-secure-profile=false
initial-enabled-packs=vanilla
"""


def step(n, text):
    print(f"\n[{n}/5] {text}")


def find_java():
    """Java 21 or newer: on PATH, or the copy that the Minecraft / Lunar launchers already installed."""
    home = os.path.expanduser("~")
    appdata = os.environ.get("APPDATA", "")
    local = os.environ.get("LOCALAPPDATA", "")
    candidates = ["java"]
    for pattern in [os.path.join(appdata, ".minecraft", "runtime", "java-runtime-*", "*", "*", "bin", "java.exe"),
                    os.path.join(local, "Packages", "Microsoft.4297127D64EC6_*", "LocalCache", "Local", "runtime",
                                 "java-runtime-*", "*", "*", "bin", "java.exe"),
                    os.path.join(home, ".lunarclient", "jre", "*", "*", "bin", "java.exe"),
                    os.path.join(home, ".lunarclient", "jre", "*", "bin", "java.exe"),
                    os.path.join(home, "MarsCuffMinecraft", "java", "*", "bin", "java.exe"),
                    r"C:\Program Files\*\jdk-2*\bin\java.exe", r"C:\Program Files\Java\*\bin\java.exe"]:
        candidates += sorted(glob.glob(pattern), reverse=True)
    for java in candidates:
        try:
            out = subprocess.run([java, "-version"], capture_output=True, text=True, timeout=20).stderr
        except (OSError, subprocess.TimeoutExpired):
            continue
        # First line looks like: openjdk version "21.0.3" 2024-04-16
        try:
            major = int(out.split('"')[1].split(".")[0])
        except (IndexError, ValueError):
            continue
        if major >= 21:
            return java, out.splitlines()[0]
    return None, None


def download_server():
    print("  Asking Mojang (official) for the", MC_VERSION, "server ...")
    manifest = json.load(urllib.request.urlopen(MANIFEST))
    url = next(v["url"] for v in manifest["versions"] if v["id"] == MC_VERSION)
    server = json.load(urllib.request.urlopen(url))["downloads"]["server"]
    print(f"  Downloading {server['url']} ({server['size'] / 1e6:.0f} MB)")
    data = urllib.request.urlopen(server["url"]).read()
    if hashlib.sha1(data).hexdigest() != server["sha1"]:
        sys.exit("  STOP: the download's fingerprint does not match Mojang's. Not using it.")
    open(SERVER_JAR, "wb").write(data)
    print("  OK: fingerprint matches Mojang's official SHA-1", server["sha1"])


def main():
    os.makedirs(jm.SERVER_DIR, exist_ok=True)

    step(1, "Jezero world")
    if os.path.exists(os.path.join(jm.SERVER_DIR, "world_info.json")):
        print("  already built:", os.path.join(jm.SERVER_DIR, "world"))
    else:
        subprocess.run([sys.executable, os.path.join(jm.HERE, "make_world.py")], check=True)

    step(2, "Java 21")
    java, version = find_java()
    if not java:
        sys.exit("  Java 21 not found. Easiest fix: open the normal Minecraft Launcher once and play 1.21.1 "
                 "(it installs Java 21), or install 'Microsoft Build of OpenJDK 21'. Then run this again.")
    print("  using", java, "-", version)

    step(3, "Minecraft server " + MC_VERSION)
    if os.path.exists(SERVER_JAR):
        print("  already downloaded")
    else:
        download_server()

    step(4, "Minecraft EULA")
    eula = os.path.join(jm.SERVER_DIR, "eula.txt")
    if os.path.exists(eula) and "eula=true" in open(eula).read():
        print("  already accepted")
    else:
        print("  Running a Minecraft server needs YOU to agree to the Minecraft EULA:")
        print("  https://aka.ms/MinecraftEULA")
        if input("  Type yes to agree: ").strip().lower() != "yes":
            sys.exit("  Not agreed, so the server can't start.")
        open(eula, "w").write("# Accepted by the user in start.py\neula=true\n")

    props = os.path.join(jm.SERVER_DIR, "server.properties")
    if not os.path.exists(props):
        # Random password so only the bridge on this computer can send commands.
        open(props, "w", encoding="utf-8").write(PROPERTIES.format(password=secrets.token_hex(16)))

    step(5, "Starting the server and the website bridge")
    server = subprocess.Popen([java, "-Xms1G", "-Xmx4G", "-jar", SERVER_JAR, "nogui"],
                              cwd=jm.SERVER_DIR, stdin=subprocess.PIPE, text=True)
    import bridge
    threading.Thread(target=bridge.main, daemon=True).start()

    # Open the website once the bridge answers.
    for _ in range(180):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{bridge.PORT}/api/status", timeout=2)
            break
        except OSError:
            time.sleep(2)
    print("\n" + "=" * 60)
    print("  READY!")
    print("  1. Minecraft 1.21.1 -> Multiplayer -> Direct Connection -> localhost")
    print(f"  2. Website: http://localhost:{bridge.PORT}  -> plan a walk -> 'Send to Minecraft'")
    print("  To stop: type stop here and press Enter (saves the world).")
    print("=" * 60)
    webbrowser.open(f"http://localhost:{bridge.PORT}")
    try:
        while server.poll() is None:
            line = input()
            server.stdin.write(line + "\n")
            server.stdin.flush()
    except (EOFError, KeyboardInterrupt):
        server.stdin.write("stop\n")
        server.stdin.flush()
    server.wait()


if __name__ == "__main__":
    main()
