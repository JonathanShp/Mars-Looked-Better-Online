// cuff.js - writes the astronaut's wrist checklist: small 3 x 5 inch pages,
// like the Apollo cuff checklists. Pages:
//   1. Traverse map     2. Timeline     3+. One page per station     last. Emergency
// Every number on a page comes from Plan.result / Science (data or labelled model).

const Cuff = {
  // Draw the traverse map on a canvas from OUR grid data (no web tiles, so it
  // always prints): grey hillshade, red = too steep, route in blue, pins.
  drawMap(res, stations, widthPx, heightPx) {
    const canvas = document.createElement("canvas");
    canvas.width = widthPx;
    canvas.height = heightPx;
    const ctx = canvas.getContext("2d");

    // 1) Which part of the grid to show: the route plus a margin, keeping the
    //    page's shape and true ground proportions (east-west cells are narrower).
    let r0 = Infinity, r1 = -Infinity, c0 = Infinity, c1 = -Infinity;
    res.routeCells.forEach((c) => { r0 = Math.min(r0, c.row); r1 = Math.max(r1, c.row); c0 = Math.min(c0, c.col); c1 = Math.max(c1, c.col); });
    const { dx, dy } = Grid.cellSizeMetres(Math.round((r0 + r1) / 2));
    const pad = 12;
    let hM = (r1 - r0 + 2 * pad) * dy, wM = (c1 - c0 + 2 * pad) * dx;   // metres
    const want = widthPx / heightPx;                                     // page shape
    if (wM / hM < want) wM = hM * want; else hM = wM / want;
    const midR = (r0 + r1) / 2, midC = (c0 + c1) / 2;
    const top = midR - hM / dy / 2, left = midC - wM / dx / 2;
    const metresPerPx = wM / widthPx;
    const toPx = (row, col) => [((col + 0.5 - left) * dx) / metresPerPx, ((row + 0.5 - top) * dy) / metresPerPx];

    // 2) Hillshade + slope colour, pixel by pixel.
    const img = ctx.createImageData(widthPx, heightPx);
    const { rows, cols } = Grid.meta;
    for (let y = 0; y < heightPx; y++) {
      for (let x = 0; x < widthPx; x++) {
        const row = Math.floor(top + (y * metresPerPx) / dy), col = Math.floor(left + (x * metresPerPx) / dx);
        let rgb = [255, 255, 255];                                       // outside data: white
        if (row > 0 && col > 0 && row < rows - 1 && col < cols - 1) {
          const e = (r, c) => Grid.elev[r * cols + c];
          // Light from the north-west: ground rising toward the south-east faces
          // the light and is drawn brighter (ex = rise eastward, ey = rise southward).
          const ex = (e(row, col + 1) - e(row, col - 1)) / (2 * dx);
          const ey = (e(row + 1, col) - e(row - 1, col)) / (2 * dy);
          const shade = Math.max(0, Math.min(1, 0.6 + 1.5 * (ex + ey)));
          const g = 120 + 120 * shade;
          const s = Grid.slopeAt(row, col);
          if (s === null) rgb = (x + y) % 8 < 4 ? [90, 90, 90] : [200, 200, 200];   // NO DATA stripes
          else if (s > MODELS.slopeBlockedDeg) rgb = [225, 60, 50];
          else if (s > MODELS.slopeCautionDeg) rgb = [g, g * 0.85, g * 0.55];
          else rgb = [g, g, g];
        }
        img.data.set([...rgb, 255], (y * widthPx + x) * 4);
      }
    }
    ctx.putImageData(img, 0, 0);

    // 3) Route line, then PNR, then station pins on top.
    ctx.lineWidth = 3;
    ctx.strokeStyle = "#0057d9";
    ctx.beginPath();
    res.legs.forEach((leg) => leg.cells.forEach((c, i) => {
      const [x, y] = toPx(c.row, c.col);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }));
    ctx.stroke();

    const pin = (row, col, label, fill) => {
      const [x, y] = toPx(row, col);
      ctx.fillStyle = fill; ctx.strokeStyle = "#fff"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(x, y, 11, 0, 2 * Math.PI); ctx.fill(); ctx.stroke();
      ctx.fillStyle = "#fff"; ctx.font = "bold 13px sans-serif";
      ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(label, x, y + 1);
    };
    if (res.pnr) {
      const [x, y] = toPx(res.pnr.row, res.pnr.col);
      ctx.fillStyle = "#d00"; ctx.fillRect(x - 18, y - 9, 36, 18);
      ctx.fillStyle = "#fff"; ctx.font = "bold 11px sans-serif"; ctx.textAlign = "center";
      ctx.textBaseline = "middle"; ctx.fillText("PNR", x, y + 1);
    }
    pin(Plan.habitat.row, Plan.habitat.col, "H", "#0057d9");
    stations.forEach((s, k) => pin(s.row, s.col, String(k + 1), "#c1502e"));

    // 4) Scale bar (Mars metres, computed by us) and north arrow.
    const barM = [100, 200, 500, 1000, 2000, 5000].find((m) => m / metresPerPx > widthPx * 0.2) || 5000;
    const barPx = barM / metresPerPx;
    ctx.fillStyle = "#000"; ctx.fillRect(10, heightPx - 16, barPx, 5);
    ctx.font = "bold 11px sans-serif"; ctx.textAlign = "left"; ctx.textBaseline = "bottom";
    ctx.fillText(barM >= 1000 ? `${barM / 1000} km` : `${barM} m`, 10, heightPx - 18);
    ctx.textAlign = "center"; ctx.fillText("N ▲", widthPx - 20, 18);
    return canvas;
  },

  // Build all cuff pages as HTML inside #cuff.
  build() {
    const res = Plan.result;
    if (!res || res.error) return false;
    const st = Science.describeAll(Plan.stations);
    const pages = [];
    const page = (title, body) => pages.push(
      `<section class="cuff-page"><header>${title}<span>MARSCUFF · JEZERO</span></header>${body}</section>`);

    // Page 1: map
    page("TRAVERSE MAP", `<div class="cuff-map"></div>
      <p class="cuff-small">Blue = route · Red = slope &gt; ${MODELS.slopeBlockedDeg}° (blocked) ·
      Tan = &gt; ${MODELS.slopeCautionDeg}° · Stripes = no data · ${(res.metres / 1000).toFixed(1)} km total</p>`);

    // Page 2: timeline
    const lines = res.events.map((e) => {
      const flag = e.beyondPnr ? " ✖ PAST PNR" : "";
      const tb = e.turnBackBy !== undefined ? `<br><i>turn back by ${hm(e.turnBackBy)}</i>` : "";
      return `<tr><td>${hm(e.t)}</td><td>${e.what.toUpperCase()}${flag}${tb}</td></tr>`;
    }).join("");
    page("TIMELINE (EVA h:mm)", `<table class="cuff-table">${lines}</table>
      <p><b>${res.pnr ? `POINT OF NO RETURN: ${hm(res.pnr.clock)}` : "NO PNR ON THIS PLAN"}</b><br>
      Total ${hm(res.totalSeconds)} · usable ${hm(res.usable)} of ${MODELS.evaBudgetHours}:00</p>
      <p class="cuff-small">MODEL: Tobler hiking fn × ${MODELS.suitFactor} suit (team), ${MODELS.stationWorkMinutes} min/station (team),
      8 h EVA (NASA surface ConOps), ${MODELS.reserveFraction * 100}% reserve (team).</p>`);

    // Station pages
    st.forEach((d, k) => {
      const e = res.events.find((ev) => ev.station === k && ev.what.startsWith("Arrive"));
      const flags = [
        d.unitMapped ? "" : "UNIT NOT MAPPED (outside Stack et al. 2020)",
        d.neverDriven ? "★ UNIT PERSEVERANCE NEVER DROVE ON" : "",
        e.beyondPnr ? "✖ BEYOND POINT OF NO RETURN - SKIP" : "",
      ].filter(Boolean).map((f) => `<div class="cuff-flag">${f}</div>`).join("");
      const tasks = d.tasks.length
        ? d.tasks.map((t) => `<li><b>${t.task}</b><br><span class="cuff-small">Gap: ${t.gap}</span></li>`).join("")
        : "<li>No orbital gap scored here (Question 0/3). Consider moving this station.</li>";
      page(`STATION ${k + 1}`, `
        <p class="cuff-unit">${d.unit || "Unmapped unit"}</p>
        <p>Arrive ${hm(e.t)} · work ${MODELS.stationWorkMinutes} min · leave by ${hm(e.turnBackBy)}</p>
        ${flags}
        <ol class="cuff-tasks">${tasks}</ol>
        <p class="cuff-small">Question ${d.question.score}/3 · science value ${d.value} ·
        ${d.latlon.lat.toFixed(4)}°N ${d.latlon.lon.toFixed(4)}°E · ${d.elevation} m · slope ${d.slope.toFixed(1)}°</p>`);
    });

    // Emergency page: shortest walk home from each station (computed), plus team rules.
    const home = Plan.stations.map((s, k) =>
      `<tr><td>STA ${k + 1}</td><td>${hm(Plan.homeField[Grid.index(s.row, s.col)])} walk home</td></tr>`).join("");
    page("EMERGENCY", `
      <table class="cuff-table">${home}</table>
      <p><b>IF SUIT ALARM:</b> stop work, walk straight home (times above).</p>
      <p><b>IF BEHIND SCHEDULE:</b> leave each station by its turn-back time; skip the next station.</p>
      <p><b>IF DUST RISING:</b> stop sampling; head home on the planned route.</p>
      ${res.pnr ? `<p><b>NEVER PASS THE PNR</b> after EVA ${hm(res.pnr.clock)}.</p>` : ""}
      <p class="cuff-small">Walk-home times: MarsCuff model (Tobler × ${MODELS.suitFactor}) on USGS CTX DTM. Rules: team procedures (draft).</p>`);

    const cuff = document.getElementById("cuff");
    cuff.innerHTML = pages.join("");
    // 2.7 x 2.9 inch map at 200 px per inch.
    cuff.querySelector(".cuff-map").appendChild(this.drawMap(res, Plan.stations, 540, 580));
    return true;
  },
};
