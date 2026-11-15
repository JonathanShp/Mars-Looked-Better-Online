// app.js - starts MarsCuff: makes the map, loads the data, wires up the mouse.

// Mars Trek serves its map tiles in plain latitude/longitude ("EPSG:4326"
// style, 2 x 1 tiles at zoom 0), which Leaflet supports out of the box.
// NOTE: Leaflet thinks distances are on Earth, so we never use Leaflet's own
// distance or scale-bar tools - we compute Mars distances ourselves.
const map = L.map("map", {
  crs: L.CRS.EPSG4326,
  center: [18.445, 77.43],
  zoom: 10,
  minZoom: 8,
  maxZoom: 18,
  zoomSnap: 0.25,   // allow in-between zooms so the crater fills a narrow phone screen
});

// Text for the box in the corner that describes the spot under the mouse.
function describeCell(lat, lon) {
  const cell = Grid.cellAt(lat, lon);
  if (!cell) return "Outside the elevation data";
  const elev = Grid.elevationAt(cell.row, cell.col);
  const slope = Grid.slopeAt(cell.row, cell.col);
  const unit = Grid.unitAt(cell.row, cell.col);
  const q = Grid.questionAt(cell.row, cell.col);
  return (
    `lon ${lon.toFixed(5)}, lat ${lat.toFixed(5)}<br>` +
    `Elevation: ${elev === null ? "NO DATA" : elev + " m"}<br>` +
    `Slope: ${slope === null ? "NO DATA" : slope.toFixed(1) + "°"}<br>` +
    `Bedrock unit: ${unit || "<i>not mapped by Stack et al. 2020</i>"}<br>` +
    `Question score: ${q.score}/3${q.reasons.length ? "<br><small>· " + q.reasons.join("<br>· ") + "</small>" : ""}`
  );
}

async function start() {
  await Grid.load();
  Route.prepare();
  const layers = await buildLayers();
  buildLayerPanel(map, layers);
  map.fitBounds(Grid.leafletBounds());
  PlanUI.init(map);

  const readout = document.getElementById("readout");
  map.on("mousemove", (e) => { readout.innerHTML = describeCell(e.latlng.lat, e.latlng.lng); });
  // Phones have no mouse: show the readout for the spot you tap instead.
  map.on("click", (e) => { readout.innerHTML = describeCell(e.latlng.lat, e.latlng.lng); });

  window.MarsCuff = { map, layers, Plan, PlanUI };   // handy for testing in the browser console
}

// If anything fails while loading, say so on screen instead of hanging on "Loading…".
start().catch((err) => {
  console.error(err);
  document.getElementById("plan-out").textContent = "Could not load the map data: " + err.message;
});
