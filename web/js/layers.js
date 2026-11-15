// layers.js - every picture layer on the map, each with its mission and source.
// The layer panel is built from the LAYERS list at the bottom, so a layer can
// never appear without its source label.

// Mars Trek tile address. Mars Trek uses lat/lon tiles: 2 x 1 tiles at zoom 0.
function trekTiles(layerId, ext, maxNativeZoom) {
  return L.tileLayer(
    `https://trek.nasa.gov/tiles/Mars/EQ/${layerId}/1.0.0/default/default028mm/{z}/{y}/{x}.${ext}`,
    { maxNativeZoom, maxZoom: 18, tileSize: 256, attribution: "NASA Mars Trek" }
  );
}

// Turn a grid into a picture: colourOf(row, col) returns [r, g, b, alpha] per cell.
function gridImage(colourOf) {
  const { rows, cols } = Grid.meta;
  const canvas = document.createElement("canvas");
  canvas.width = cols;
  canvas.height = rows;
  const ctx = canvas.getContext("2d");
  const img = ctx.createImageData(cols, rows);
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      img.data.set(colourOf(r, c), (r * cols + c) * 4);
    }
  }
  ctx.putImageData(img, 0, 0);
  return L.imageOverlay(canvas.toDataURL(), Grid.leafletBounds(), { className: "pixelated" });
}

// Shaded relief drawn by us from the CTX elevation grid (so the map still has a
// background when the Mars Trek tiles can't load, e.g. offline or on the phone link).
// Same light as the cuff map: from the north-west.
function reliefLayer() {
  const { rows, cols } = Grid.meta;
  const e = (r, c) => Grid.elev[r * cols + c];
  return gridImage((r, c) => {
    if (r === 0 || c === 0 || r === rows - 1 || c === cols - 1) return [0, 0, 0, 0];
    if (Grid.elevationAt(r, c) === null) return [0, 0, 0, 0];   // no data: leave empty
    const { dx, dy } = Grid.cellSizeMetres(r);
    const ex = (e(r, c + 1) - e(r, c - 1)) / (2 * dx);         // rise eastward
    const ey = (e(r + 1, c) - e(r - 1, c)) / (2 * dy);         // rise southward
    const shade = Math.max(0, Math.min(1, 0.55 + 1.5 * (ex + ey)));
    return [70 + 150 * shade, 45 + 105 * shade, 35 + 80 * shade, 255];  // rusty Mars tones
  });
}

// Slope: green = gentle, amber = caution, red = blocked, stripes = NO DATA.
function slopeLayer() {
  return gridImage((r, c) => {
    const s = Grid.slopeAt(r, c);
    if (s === null) return (r + c) % 6 < 3 ? [60, 60, 60, 220] : [200, 200, 200, 220];
    if (s > MODELS.slopeBlockedDeg) return [220, 30, 30, 190];
    if (s > MODELS.slopeCautionDeg) return [245, 170, 20, 150];
    return [40, 170, 80, 60];
  });
}

// Science glow (the "Question layer"): brighter = more things orbit can't tell us.
// It glows ONLY where Stack et al. 2020 mapped the rocks: outside that map we
// don't know the rock type, so we can't say what science is waiting there.
function questionLayer() {
  const glow = [[0, 0, 0, 0], [150, 110, 255, 90], [190, 130, 255, 175], [255, 235, 120, 230]];
  return gridImage((r, c) => (Grid.unitAt(r, c) === null ? [0, 0, 0, 0] : glow[Grid.questionAt(r, c).score]));
}

// Colours for the 15 bedrock units: delta = blues, crater floor = earth tones,
// rim = purples/greys, others = greens/teal.
const UNIT_COLOURS = {
  "Delta blocky": "#1f5fa8", "Delta layered rough": "#3a7fd0",
  "Delta thickly layered": "#5c9ee6", "Delta thinly layered": "#86bdf2",
  "Delta truncated curvilinear layered": "#2b4f8a",
  "Crater floor fractured 1": "#c98a4b", "Crater floor fractured 2": "#a8683a",
  "Crater floor fractured rough": "#e0b07a",
  "Crater rim blocky": "#7b5ea7", "Crater rim breccia": "#a07cc5",
  "Crater rim layered": "#5e4785", "Crater rim rough": "#9a8fb0",
  "Margin fractured": "#2fa39a", "Neretva Vallis layered": "#61c3e0",
  "Nili Planum fractured": "#8a9a3a",
};

function geologyLayer(geojson) {
  return L.geoJSON(geojson, {
    style: (f) => ({ color: UNIT_COLOURS[f.properties.unit] || "#999", weight: 0.5,
                     fillOpacity: 0.45 }),
    onEachFeature: (f, layer) => layer.bindTooltip(f.properties.unit, { sticky: true }),
  });
}

function traverseLayer(geojson) {
  const path = L.geoJSON(geojson, { style: { color: "#ffffff", weight: 2, opacity: 0.9 } });
  // The path's first point (earliest sol) is where Perseverance landed: it first drove on sol 14.
  const first = geojson.features.reduce((a, f) => (f.properties.sol < a.properties.sol ? f : a));
  const [lon, lat] = first.geometry.coordinates[0];
  const label = L.marker([lat, lon], { interactive: false,
    icon: L.divIcon({ className: "place-label", html: "▼ Perseverance landing site", iconSize: null }) });
  return L.featureGroup([path, label]);
}

// Build all layers. Each entry: the Leaflet layer + what to show in the panel.
async function buildLayers() {
  const geology = await (await fetch("data/geology.geojson")).json();
  const traverse = await (await fetch("data/traverse.geojson")).json();
  const lastSol = Math.max(...traverse.features.map((f) => f.properties.sol));
  Science.findDrivenUnits(traverse);   // which units the rover has driven on

  // The phone-link build sets window.NO_TREK, because that page can't load
  // pictures from other websites. Then we skip the Mars Trek layers.
  const trek = !window.NO_TREK;
  return [
    { id: "relief", on: !trek, layer: reliefLayer(),
      name: "Shaded relief (from elevation)", mission: "MRO CTX stereo, tied to MGS MOLA",
      source: "Drawn by MarsCuff from the USGS Mars 2020 TRN CTX DTM (20 m), light from the north-west" },
    ...(trek ? [
    { id: "mola", on: true, layer: trekTiles("Mars_MGS_MOLA_ClrShade_merge_global_463m", "jpg", 7),
      name: "Colour elevation (MOLA)", mission: "Mars Global Surveyor · MOLA",
      source: "NASA Mars Trek, Mars_MGS_MOLA_ClrShade_merge_global_463m" },
    { id: "ctx", on: true, layer: trekTiles("JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0", "png", 13),
      name: "CTX image mosaic, 6 m", mission: "Mars Reconnaissance Orbiter · CTX",
      source: "USGS Mars 2020 TRN CTX ortho-mosaic via NASA Mars Trek" },
    { id: "hirise", on: false, layer: trekTiles("JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd", "png", 17),
      name: "HiRISE image mosaic, 25 cm", mission: "Mars Reconnaissance Orbiter · HiRISE",
      source: "USGS Mars 2020 TRN HiRISE ortho-mosaic via NASA Mars Trek" },
    ] : []),
    { id: "slope", on: true, layer: slopeLayer(),
      name: `Slope (red > ${MODELS.slopeBlockedDeg}°, amber > ${MODELS.slopeCautionDeg}°)`,
      mission: "MRO CTX stereo, tied to MGS MOLA",
      source: "Computed by MarsCuff from the USGS Mars 2020 TRN CTX DTM (20 m); limits: " + MODELS.slopeSource },
    { id: "geology", on: false, layer: geologyLayer(geology),
      name: "Geologic units (bedrock)", mission: "Mars 2020 Science Team, on MRO HiRISE",
      source: Grid.unitsMeta.source.citation },
    { id: "traverse", on: true, layer: traverseLayer(traverse),
      name: `Perseverance path (to sol ${lastSol})`, mission: "Mars 2020 · Perseverance",
      source: "NASA/JPL Mars 2020 mission map (MMGIS), M20_traverse.json" },
    { id: "question", on: true, layer: questionLayer(),
      name: "Science glow: where only astronauts can find out", mission: "Mars 2020 + MRO HiRISE/CTX + Stack et al.",
      legend: '<span class="sw" style="background:rgb(150,110,255)"></span>1 reason ' +
              '<span class="sw" style="background:rgb(190,130,255)"></span>2 reasons ' +
              '<span class="sw" style="background:rgb(255,235,120)"></span>3',
      source: "Reasons: rover never came within 500 m · only blurry 20 m terrain data (no HiRISE 1 m) · " +
              "on a boundary between two rock types (<100 m). Shown only where Stack et al. 2020 mapped the rocks." },
  ];
}

// The panel: one checkbox per layer, with its mission and source under it.
function buildLayerPanel(map, layers) {
  const panel = document.getElementById("layers");
  // Tapping the title folds the panel away (handy on a phone screen).
  panel.innerHTML = '<b class="panel-title">Layers ▾</b>';
  panel.querySelector(".panel-title").onclick = () => panel.classList.toggle("folded");
  if (window.innerWidth < 700) panel.classList.add("folded");   // start folded on phones
  layers.forEach((entry) => {
    const row = document.createElement("label");
    row.className = "layer-row";
    row.innerHTML =
      `<input type="checkbox" data-layer="${entry.id}" ${entry.on ? "checked" : ""}>` +
      `<span><span class="layer-name">${entry.name}</span>` +
      (entry.legend ? `<span class="layer-legend">${entry.legend}</span>` : "") +
      `<span class="layer-src">${entry.mission}<br>${entry.source}</span></span>`;
    const box = row.querySelector("input");
    box.addEventListener("change", () => {
      if (box.checked) entry.layer.addTo(map); else map.removeLayer(entry.layer);
    });
    if (entry.on) entry.layer.addTo(map);
    panel.appendChild(row);
  });
}
