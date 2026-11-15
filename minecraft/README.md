# MarsCuff in Minecraft: walk your planned route in a true-scale Jezero Crater

The website plans a Marswalk. This folder lets you **walk it in Minecraft**:

1. **Spawn** at Perseverance's real landing site. The brown line on the ground is the rover's real tracks.
2. On the website (opened from this computer), **plan a walk** and press **⛏ Send to Minecraft**.
3. You're **teleported into your habitat** (base). From there:
   - **big glowing arrows** float 25 m up, every 40 m along the route; red arrows mean you're past the Point of No Return;
   - a **white beam** marks home, **purple beams** mark stations (each with a sign: rock type, arrive / leave-by time), and a **red beam** marks the Point of No Return;
   - your **cuff is a book** in your hotbar (right-click to open it), and the chat link opens the full printable cuff.

## The world (built from the same NASA data as the website)

| What you see | Where it comes from |
|---|---|
| Ground height, 1 block = **1 m sideways and up** (true scale: the player is a 1.8 m astronaut) | USGS Mars 2020 CTX DTM (MRO), via `web/data/grid.bin`, smoothed between 40 m cells |
| Surface colour = bedrock unit (red sand = not mapped) | Stack et al. 2020 geologic map (`web/data/units.bin`) |
| Bare rock on slopes over 15° | Same slope grid the website uses to block routes |
| Brown line | Perseverance traverse to sol 2022, NASA/JPL MMGIS |
| Desert biome, no rain, no mobs, always noon | Game rules set by the bridge |
| **Mars gravity: 0.378 × Earth** (jumps 2.6 × higher, falls are gentler) | NASA Mars Fact Sheet (3.71 m/s²) |

The world is **10,000 × 10,000 blocks = 10 km × 10 km** of real Mars, centred on Perseverance's landing site (about 1.5 GB, built in about 1.5 minutes).
The whole 30 km map at 1 m per block would be about 60 GB, so the website draws a dashed yellow square showing which part exists in Minecraft.
A world border stops you at the edge.

**Speed:** Minecraft walking is 4.3 m/s, but a suited astronaut in our model walks about 1 m/s. So in the game you cover ground about 4 times faster than real.
The times in the cuff book are always the real (modelled) ones.

## Start it (on the computer that has Minecraft)

You need: Minecraft with the **mcmcp** mod, and Python with `numpy`.

1. Open Minecraft (the title screen is fine).
2. Double-click **`Start MarsCuff Minecraft.bat`**.
   - **First time only:** the mod makes an empty world called **MarsCuff Jezero**, closes it, and the real Jezero ground is written into it (about 2 minutes, about 1.5 GB). Then the mod opens it and you're standing at Perseverance's landing site.
   - **Later:** just open the **MarsCuff Jezero** world in Minecraft.
3. The website opens at http://localhost:8770. Plan a walk inside the yellow square and press **⛏ Send to Minecraft**.

To stop, close the black window.

Nothing is downloaded and there is no server to install. The mod's secret key is read from `.minecraft\config\mcmcp.json` on that PC only. It is never put in the repo or the website.
The website bridge only listens on this computer (127.0.0.1).

## Files
- `jezero_map.py`: how Mars coordinates turn into blocks (shared by everything below)
- `make_world.py`: writes the Minecraft region files directly from the NASA grids (`--save <world folder>`)
- `bridge.py`: serves the website and builds the route through the mcmcp mod (`build_structure` + commands)
- `start.py`: the one-click setup above
- `web/js/minecraft.js`: the website's "Send to Minecraft" button (shown only at localhost:8770)
