# Space Apps submission text (copy and paste into the form)

How to submit: log in at spaceappschallenge.org (team owner) -> your team page -> Submit Project ->
paste the parts below -> Submit before 10 PM. Slides link: open the slides, press Share, set
"anyone with the link", copy it, test it in a private window, and paste it as the Project Demo.

**Project name:** MarsCuff

**Challenge:** Interplanetary Survival Guide: Martian Map

**Project Demo (slides, 7 max):** paste your Share link of the slides here

**Final Project:**
- Live app: https://jonathanshp.github.io/Mars-Looked-Better-Online/
- Code: https://github.com/JonathanShp/Mars-Looked-Better-Online
- Ready-made Minecraft worlds: https://jonathanshp.github.io/Mars-Looked-Better-Online/web/downloads.html

---

## High-level summary

On Mars, a radio message to Earth takes 3 to 22 minutes each way, so astronauts on a moonwalk-style EVA can't wait for Mission Control to tell them where to go or when to turn back. MarsCuff is a free web map of Jezero Crater, built from real NASA terrain and geology data, that plans a Marswalk for them. You place the habitat, add 2 to 5 science stations (or press Suggest to pick the best ones in reach), and MarsCuff walks the safest route around steep slopes, builds the timeline, and marks the Point of No Return: the last spot where the crew can still get home with a safety reserve. It then prints the plan as a wrist checklist, like the cuffs Apollo astronauts wore. A "science glow" shows where only a person can find answers: rock no rover has touched, ground too fine for orbit to see, and contacts that show which rock is older. Every number comes from a NASA dataset or a clearly labelled model.

## Project details

**What it does:** route planning across real Jezero terrain (slopes over the limit are blocked), an EVA timeline with a 20% safety reserve, a Point of No Return, science tasks at each station from the geologic map and Mars 2020 instrument methods, and a printable wrist cuff. A ▶ Demo button tells the whole story in about 30 seconds.

**Benefits:** mission planners can try a Marswalk in minutes; analog field teams on Earth can print a cuff, walk it, and check our walking model; classrooms get a free site with no login.

**Minecraft:** the plan can be built as a true-scale Minecraft (Java Edition) world of Jezero, 1 block = 1 metre, with glowing arrows along the route, the stations, the Point of No Return, and the cuff as a book in your hand. Students can walk the walk they planned, or download one of three ready-made Marswalk worlds (no mod needed). It could help kids learn about Mars and find out if they'd like to be an astronaut. A Minecraft Education version is a possible next step (not built yet).

**Tools:** Python (rasterio, numpy) to process the data once; Leaflet in the browser; a Minecraft mod bridge for the world builder.

**Next:** the same pipeline could run on NASA Moon Trek data to plan Artemis Moon walks.

## NASA data used (seven datasets, three missions: MGS, MRO, Mars 2020)

- CTX DTM mosaic of Jezero, 20 m/px (MRO CTX, tied to MGS MOLA; USGS Astrogeology): elevation, slope, every route
- HiRISE DTM mosaic, 1 m/px (MRO HiRISE; USGS): where fine detail is missing
- CTX 6 m and HiRISE 25 cm image mosaics (MRO; NASA Mars Trek): base maps
- MOLA colour hillshade, 463 m (MGS; NASA Mars Trek): base map
- Photogeologic map of the Perseverance field site (Mars 2020 team, Stack et al. 2020, CC BY 4.0): rock units, contacts, science tasks
- Perseverance traverse to sol 2022 (Mars 2020; NASA/JPL MMGIS): where the rover has and hasn't driven

## Use of AI

We used Claude (Anthropic) as a coding assistant to help write and test the code, process the data, and make the slides. All data comes from the NASA sources above; models (walking speed, station time, reserve) are labelled in the app with their sources.
