# MarsCuff in Minecraft: walk your planned route in a true-scale Jezero Crater

The website plans a Marswalk. This folder lets you **walk it in Minecraft**:

1. **Spawn** at Perseverance's real landing site. The brown line on the ground is the rover's real tracks.
2. On the website (opened from this computer), **plan a walk** and press **⛏ Send to Minecraft**.
3. You're **teleported into your habitat** (base). From there:
   - **big glowing arrows** float 20 blocks (200 m) up, every 160 m along the route; red arrows mean you're past the Point of No Return;
   - a **white beam** marks home, **purple beams** mark stations (each with a sign: rock type, arrive / leave-by time), and a **red beam** marks the Point of No Return;
   - your **cuff is a book** in your hotbar (right-click to open it), and the chat link opens the full printable cuff.

## The world (built from the same NASA data as the website)

| What you see | Where it comes from |
|---|---|
| Ground height, 1 block = **10 m sideways and up** (true scale, no exaggeration) | USGS Mars 2020 CTX DTM (MRO), via `web/data/grid.bin` |
| Surface colour = bedrock unit (red sand = not mapped) | Stack et al. 2020 geologic map (`web/data/units.bin`) |
| Bare rock on slopes over 15° | Same slope grid the website uses to block routes |
| Brown line | Perseverance traverse to sol 2022, NASA/JPL MMGIS |
| Butterscotch sky, no rain, no mobs | Data pack in the world |
| **Mars gravity: 0.378 × Earth** (jumps 2.6 × higher, falls are gentler) | NASA Mars Fact Sheet (3.71 m/s²) |

The world is 3,024 × 3,024 blocks, about 30 km × 30 km of real Mars. The crater floor is near y = −49 and the highest ground is at y = 70. A world border stops you at the edge of the data.

## Start it (on the computer that has Minecraft)

Double-click **`Start MarsCuff Minecraft.bat`**. The first time it:
1. builds the world (about 1 minute; needs Python with `numpy`);
2. finds Java 21. The normal Minecraft Launcher already installs it once you've played 1.21.1;
3. downloads the **official** Minecraft 1.21.1 server from Mojang and checks its SHA-1 fingerprint;
4. asks **you** to agree to the Minecraft EULA. It never agrees for you.

Then, in **Minecraft 1.21.1**, go to Multiplayer → Direct Connection → `localhost`. The website opens at http://localhost:8770.
To stop, type `stop` in the window and press Enter. This saves the world.

The server and the bridge only listen on this computer (127.0.0.1). The remote-command password is random and stays in `server.properties` on this PC. It is never put in the repo.
The world is saved in `%USERPROFILE%\MarsCuffMinecraft\server`, outside OneDrive, because OneDrive locks world files while it syncs.

## Files
- `jezero_map.py`: how Mars coordinates turn into blocks (shared by everything below)
- `make_world.py`: writes the Minecraft region files directly from the NASA grids
- `bridge.py`: serves the website and builds the route through RCON and a data-pack function
- `start.py`: the one-click setup above
- `web/js/minecraft.js`: the website's "Send to Minecraft" button (shown only at localhost:8770)
