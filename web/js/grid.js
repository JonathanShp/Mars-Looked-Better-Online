// grid.js - loads the 40 m elevation + slope grid made by prep/make_grid.py
// and answers "what is the ground like at this spot?"
//
// The grid is a big table: row 0 is the NORTH edge, column 0 is the WEST edge.
// Each cell is 40 m x 40 m (projected metres; see grid.json for details).

const Grid = {
  meta: null,      // contents of grid.json (size, position, source)
  elev: null,      // elevation in metres, one number per cell
  slope: null,     // slope in tenths of a degree, one number per cell

  units: null,     // geologic unit id per cell (0 = not mapped), from make_geology.py
  unitsMeta: null, // unit names + source
  question: null,  // Question-layer signal bits per cell, from make_question.py
  questionMeta: null,

  // Download every grid file. All tables use the same rows x cols layout.
  async load() {
    // Download one file; stop with a clear message if it is missing.
    const get = async (f) => {
      const r = await fetch(f);
      if (!r.ok) throw new Error(`could not download ${f} (HTTP ${r.status})`);
      return r;
    };
    const getJson = async (f) => (await get(f)).json();
    // The phone-link build sets window.BIN_AS_TEXT: that host can't serve .bin
    // files, so each one is stored as base64 text (x.bin.b64.txt) and decoded here.
    const getBytes = async (f) => {
      if (!window.BIN_AS_TEXT) return (await get(f)).arrayBuffer();
      const raw = atob((await (await get(f + ".b64.txt")).text()).trim());
      const bytes = new Uint8Array(raw.length);
      for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
      return bytes.buffer;
    };

    this.meta = await getJson("data/grid.json");
    const buffer = await getBytes("data/grid.bin");
    const n = this.meta.rows * this.meta.cols;
    this.elev = new Int16Array(buffer, 0, n);          // first half of the file
    this.slope = new Int16Array(buffer, n * 2, n);     // second half (2 bytes per number)

    this.unitsMeta = await getJson("data/units.json");
    this.units = new Uint8Array(await getBytes("data/units.bin"));
    this.questionMeta = await getJson("data/question.json");
    this.question = new Uint8Array(await getBytes("data/question.bin"));
  },

  // Bedrock unit name at a cell, or null if Stack et al. 2020 did not map it.
  unitAt(row, col) {
    const id = this.units[this.index(row, col)];
    return id === 0 ? null : this.unitsMeta.units[String(id)];
  },

  // Question layer: which signals are on at this cell, and the 0-3 score.
  questionAt(row, col) {
    const bits = this.question[this.index(row, col)];
    const reasons = [1, 2, 4].filter((b) => bits & b).map((b) => this.questionMeta.bits[String(b)]);
    return { bits, score: reasons.length, reasons };
  },

  // Latitude/longitude (degrees) -> {row, col}, or null if outside the grid.
  // Works because the map projection is "equirectangular": degrees map to cells
  // in straight lines, so it is just a proportion.
  cellAt(lat, lon) {
    const b = this.meta.bounds_deg;
    const col = Math.floor((lon - b.west) / (b.east - b.west) * this.meta.cols);
    const row = Math.floor((b.north - lat) / (b.north - b.south) * this.meta.rows);
    if (row < 0 || col < 0 || row >= this.meta.rows || col >= this.meta.cols) return null;
    return { row, col };
  },

  // {row, col} -> latitude/longitude of the cell centre.
  latLonOf(row, col) {
    const b = this.meta.bounds_deg;
    return {
      lat: b.north - (row + 0.5) / this.meta.rows * (b.north - b.south),
      lon: b.west + (col + 0.5) / this.meta.cols * (b.east - b.west),
    };
  },

  index(row, col) { return row * this.meta.cols + col; },

  // Elevation in metres, or null for "no data".
  elevationAt(row, col) {
    const v = this.elev[this.index(row, col)];
    return v === this.meta.nodata ? null : v;
  },

  // Slope in degrees, or null for "no data".
  slopeAt(row, col) {
    const v = this.slope[this.index(row, col)];
    return v === this.meta.nodata ? null : v / 10;
  },

  // Real ground size of one cell in metres (east-west, north-south).
  // East-west shrinks with cos(latitude) because of the map projection.
  cellSizeMetres(row) {
    const lat = this.latLonOf(row, 0).lat * Math.PI / 180;
    const s = this.meta.cell_size_m_projected;
    return { dx: s * Math.cos(lat), dy: s };
  },

  // Leaflet-style bounds [[south, west], [north, east]] for image overlays.
  leafletBounds() {
    const b = this.meta.bounds_deg;
    return [[b.south, b.west], [b.north, b.east]];
  },
};
