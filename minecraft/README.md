# MarsCuff in Minecraft: walk your planned route in a true-scale Jezero Crater

The website plans a Marswalk. This folder lets you **walk it in Minecraft**:

1. **Spawn** at Perseverance's real landing site. The dark strip on the ground is the rover's real driving track.
2. On the website (opened from this computer), **plan a walk** and press **⛏ Send to Minecraft**.
3. The bridge closes the world, **builds the Mars ground along that walk**, and opens it again (about 30–60 seconds).
4. You're **teleported into your habitat** (base). From there:
   - **big glowing arrows** float 25 m up, every 40 m along the route; red arrows mean you're past the Point of No Return;
   - a **white beam** marks home, **purple beams** mark stations (each with a sign: rock type, arrive / leave-by time), and a **red beam** marks the Point of No Return;
   - your **cuff is a book** in your hotbar (right-click to open it): route, timeline, and the experiments to do at each station. The chat link opens the full printable cuff.

## Only the ground along your walk is built

The whole Jezero map is **30 km × 30 km ≈ 900 km²**. At 1 block = 1 m that would be about **14 GB**, so the world is never built as one big box. Each walk builds a **corridor** instead:

| Where | How much ground |
|---|---|
| Along the route line | **500 m either side** (a 1 km-wide band) |
| Around the habitat, each station and the PNR | an **800 m radius** bubble, so there is room to look around |
| First run, before you have planned anything | a **3 km** disc around the landing site (about 15 s, about 110 MB) |

A typical walk is **about 100 MB and well under a minute**. You can plan anywhere on the map — nothing is out of bounds, because the ground is made to fit the route.

On the website the band that would be built is **shaded yellow along your route**. The two radii come straight from the bridge (`/api/area`), so the picture can never drift from what actually gets built. In the game a **world border** is set to the ground that exists, so you cannot walk out into the empty part. That edge is the edge of what was generated, not a cliff on Mars: plan a different walk and send it again to get different ground.

## The world (built from the same NASA data as the website)

| What you see | Where it comes from |
|---|---|
| Ground height, 1 block = **1 m sideways and up** (true scale: the player is a 1.8 m astronaut) | USGS Mars 2020 CTX DTM (MRO), via `web/data/grid.bin`, smoothed between 40 m cells |
| Surface colour = bedrock unit (red sand = not mapped) | Stack et al. 2020 geologic map (`web/data/units.bin`) |
| Bare rock on slopes over 15° | Same slope grid the website uses to block routes |
| Dark strip | Perseverance traverse to sol 2022, NASA/JPL MMGIS |
| Boulder fields and small craters | **MODEL**, not data: real Mars has rocks and craters at this size, but the 40 m map cannot see them. Denser on the crater rim units |
| Desert biome, no rain, no mobs, always noon | Game rules set by the bridge |
| **Mars gravity: 0.378 × Earth** (jumps 2.6 × higher, falls are gentler) | NASA Mars Fact Sheet (3.71 m/s²), applied by the world's "MarsCuff" data pack |

**Speed:** Minecraft walking is 4.3 m/s, but a suited astronaut in our model walks about 1 m/s. So in the game you cover ground about 4 times faster than real.
The times in the cuff book are always the real (modelled) ones.

## Start it (on the computer that has Minecraft)

You need: Minecraft Java Edition with the **mcmcp** mod, and Python with `numpy`.

1. Open Minecraft (the title screen is fine).
2. Double-click **`Start MarsCuff Minecraft.bat`**.
   - **First time only:** the mod makes an empty world called **MarsCuff Jezero**, closes it, writes the 3 km starter disc of real Jezero ground into it (about a minute), and opens it again. You are standing at Perseverance's landing site.
   - **Later:** just open the **MarsCuff Jezero** world in Minecraft.
3. The website opens at http://localhost:8770. Plan a walk anywhere on the map and press **⛏ Send to Minecraft**.

To stop, close the black window.

Nothing is downloaded and there is no server to install. The mod's secret key is read from `.minecraft\config\mcmcp.json` on that PC only. It is never put in the repo or the website.
The website bridge only listens on this computer (127.0.0.1).

## Giving the world to someone who has no mod

A built save is an ordinary Minecraft world, so it can simply be handed over:

```
python minecraft/make_world.py --route plan.json --save "<a closed, empty save>" --zip MarsCuff.zip
```

The zip holds the save plus a **HOW-TO-USE.txt** that explains unzipping it into the saves folder (Windows / macOS / Linux paths), switching the **MarsCuff** data pack on for the sky and Mars gravity, what the colours and strips mean, and why the world stops at the edge of the corridor. They need no mod and no Python — only Minecraft Java Edition.

## Files
- `jezero_map.py`: how Mars coordinates turn into blocks (shared by everything below)
- `surface.py`: the realism layer — boulders, small craters, rock and sand mixing
- `make_world.py`: writes the Minecraft region files directly from the NASA grids (`--route`, `--save`, `--zip`)
- `bridge.py`: serves the website and builds the route through the mcmcp mod (`build_structure` + commands)
- `start.py`: the one-click setup above
- `web/js/minecraft.js`: the website's "Send to Minecraft" button and the corridor shading (shown only at localhost:8770)
