// minecraft.js - "Send to Minecraft": builds your planned walk inside a true-scale
// Minecraft model of Jezero Crater (see minecraft/README.md).
//
// The button only appears when this page is opened from the MarsCuff bridge
// (http://localhost:8770 on the computer that runs the Minecraft server).
// On the public website it stays hidden, so nothing changes there.

const MC = {
  available: location.port === "8770",

  area: null,          // scale + corridor widths, straight from the bridge
  corridor: null,      // the Leaflet layer showing the band we would build

  init() {
    if (!this.available) return;
    const btn = document.getElementById("btn-minecraft");
    btn.hidden = false;
    btn.onclick = () => this.send();
    // The whole Jezero map can be played now, so there is no square to outline.
    // Instead we shade the band along your walk: that is exactly the ground
    // Minecraft will build when you press the button.
    fetch("/api/area").then((r) => r.json()).then((a) => {
      this.area = a;
      this.drawCorridor();
      // The habitat and the stations are placed by clicking the map, so redraw after a click.
      PlanUI.map.on("click", () => setTimeout(() => this.drawCorridor(), 80));
    });
    if (location.hash === "#cuff") this.openLastCuff();     // the chat link inside Minecraft
  },

  // Shade the ground Minecraft would build for the walk on screen: about 500 m either
  // side of the route and about 800 m around the habitat and each station. The two
  // radii come from the bridge (/api/area), so the picture can never drift from the mod.
  drawCorridor() {
    if (!this.area || !PlanUI.map) return;
    if (this.corridor) { PlanUI.map.removeLayer(this.corridor); this.corridor = null; }
    const res = Plan.result;
    if (!res || res.error || !res.routeCells || !res.routeCells.length) return;

    const g = L.layerGroup();
    const skin = { color: "#ffd54a", weight: 1, opacity: 0.5, fillColor: "#ffd54a",
                   fillOpacity: 0.10, interactive: false };
    // One circle every few cells along the walk; overlapping, they read as one band.
    const cell = Grid.meta.cell_size_m_projected || 40;
    const step = Math.max(1, Math.round(this.area.corridor_radius_m / cell / 2));
    res.routeCells.forEach((c, i) => {
      if (i % step) return;
      const p = Grid.latLonOf(c.row, c.col);
      L.circle([p.lat, p.lon], Object.assign({ radius: this.area.corridor_radius_m }, skin)).addTo(g);
    });
    // Wider circles where you stop and work, so there is room to look around.
    [Plan.habitat].concat(Plan.stations).filter(Boolean).forEach((c) => {
      const p = Grid.latLonOf(c.row, c.col);
      L.circle([p.lat, p.lon], Object.assign({ radius: this.area.station_radius_m }, skin)).addTo(g);
    });
    const km2 = this.area.built && this.area.built.area_km2;
    const head = Grid.latLonOf(res.routeCells[0].row, res.routeCells[0].col);
    L.marker([head.lat, head.lon], { interactive: false, icon: L.divIcon({ className: "place-label",
      html: "⛏ Minecraft builds this band (1 block = 1 m)" + (km2 ? ` · in the world now: ${km2} km²` : ""),
      iconSize: null, iconAnchor: [0, -4] }) }).addTo(g);
    this.corridor = g.addTo(PlanUI.map);
  },

  // Everything the bridge needs: cells of the route + the text of the cuff book.
  payload() {
    const res = Plan.result;
    const info = Science.describeAll(Plan.stations);
    const arrive = (k) => res.events.find((e) => e.station === k && e.what.startsWith("Arrive"));
    const path = [];
    res.routeCells.forEach((c) => {
      const last = path[path.length - 1];
      if (!last || last[0] !== c.row || last[1] !== c.col) path.push([c.row, c.col, Math.round(c.clock)]);
    });
    return {
      habitat: Plan.habitat,
      stations: Plan.stations.map((s, k) => ({
        row: s.row, col: s.col, unit: info[k].unit,
        arrive: hm(arrive(k).t), leaveBy: hm(arrive(k).turnBackBy),
        beyondPnr: arrive(k).beyondPnr, neverDriven: info[k].neverDriven,
      })),
      pnr: res.pnr ? { row: res.pnr.row, col: res.pnr.col, clock: res.pnr.clock, label: hm(res.pnr.clock) } : null,
      path,
      summary: { km: (res.metres / 1000).toFixed(2), total: hm(res.totalSeconds), usable: hm(res.usable), fits: res.fits },
      book: this.bookSections(res, info),
    };
  },

  // A written book holds 100 pages, and the bridge wraps every section into
  // 19-character lines, 5 lines to a page. So count pages the same way the bridge
  // does, and stop adding step-by-step detail before the book runs off the end.
  bookPages(text) {
    let lines = 0;
    text.split("\n").forEach((para) => {
      let cur = "";
      para.split(" ").forEach((w) => {
        if (cur && cur.length + 1 + w.length > 19) { lines += 1; cur = w; } else { cur = cur ? cur + " " + w : w; }
      });
      lines += 1;                       // the last line of the paragraph
    });
    return Math.ceil(lines / 5);
  },

  // The cuff as short book sections (the bridge wraps them into 19-character lines).
  bookSections(res, info) {
    const cover = `MARSCUFF\nJezero EVA cuff\n\n${(res.metres / 1000).toFixed(2)} km walk\n` +
      `${hm(res.totalSeconds)} of ${hm(res.usable)} usable\n${res.fits ? "FITS" : "TOO LONG"}\n` +
      (res.pnr ? `PNR at EVA ${hm(res.pnr.clock)}` : "No Point of No Return");
    // True whichever way you walk it: the live mod draws arrows and beams, the
    // downloaded world has the same colours as tall pillars you can see far off.
    const how = "HOW TO FOLLOW\nWHITE = habitat.\nPURPLE = stations.\nRED = no return.\n" +
      "Glowing = route.\n(beams in game,\npillars in the zip)";
    const timeline = "TIMELINE\n" + res.events.map((e) =>
      `${hm(e.t)} ${e.what.replace("station", "sta")}${e.turnBackBy !== undefined ? ` (go by ${hm(e.turnBackBy)})` : ""}${e.beyondPnr ? " PAST PNR" : ""}`).join("\n");
    const hp = Science.habitatProtocol;
    const habitat = `AT THE HABITAT\n${hp.title}, ${hp.minutes} min\nDo it before you leave and again when you get back.\n\nWHERE\n${hp.where}\n\nSTEPS\n` +
      hp.steps.map((x, j) => `${j + 1}. ${x}`).join("\n");
    const emergency = "EMERGENCY\n" + Plan.stations.map((st, k) =>
      `Sta ${k + 1}: ${hm(Plan.homeField[Grid.index(st.row, st.col)])} walk home`).join("\n") +
      "\nSuit alarm: walk straight home." + (res.pnr ? `\nNever pass the PNR after ${hm(res.pnr.clock)}.` : "");
    const sources = "SOURCES\nGround: USGS CTX DTM (MRO). Rocks: Stack et al. 2020. Tracks: NASA/JPL Mars 2020. " +
      "Jobs: Mars 2020 instrument papers (Mastcam-Z, SuperCam, SHERLOC, PIXL, MEDA). " +
      "Times: MODEL (Tobler x 0.6, team assumptions). 1 block = 1 m.";

    // Per station: where you are and when to leave, why the spot is worth the walk,
    // and the list of jobs in the order to do them.
    const briefs = info.map((d, k) => {
      const a = res.events.find((e) => e.station === k && e.what.startsWith("Arrive"));
      const seen = new Set();
      const why = d.tasks.filter((t) => !t.baseline && !seen.has(t.signal) && seen.add(t.signal))
        .map((t) => `- ${t.signal}. ${t.gap}`).join("\n")
        || "- Orbit already sees this spot well. Only the baseline jobs apply here.";
      return [
        `STATION ${k + 1}\n${d.unit || "Rock not mapped"}\nArrive ${hm(a.t)}\nLeave by ${hm(a.turnBackBy)}` +
        `${d.neverDriven ? "\n* Never driven by Perseverance" : ""}${a.beyondPnr ? "\nBEYOND PNR - SKIP" : ""}` +
        `\n\nWHY HERE\n${why}`,
        `STATION ${k + 1} JOBS\n${d.coreMinutes} min must-do, ${d.budgetMinutes} min booked` +
        `${d.extraMinutes ? `, +${d.extraMinutes} if time` : ""}\n` +
        d.tasks.map((t, i) => `${i + 1}. ${t.title} (${t.minutes} min)${t.optional ? " IF TIME" : ""}`).join("\n"),
      ];
    });
    // One section per job: what to do, step by step, and where to stand.
    const detail = info.map((d, k) => d.tasks.map((t, i) =>
      `STA ${k + 1} JOB ${i + 1}\n${t.title}\n${t.minutes} min${t.optional ? " - IF TIME" : ""}\n\n` +
      `WHERE\n${t.where}\n\nSTEPS\n` + t.steps.map((x, j) => `${j + 1}. ${x}`).join("\n")));

    // The parts you must always have, then as much job detail as still fits.
    // Two pages are held back for the note that says which jobs did not fit.
    const fixed = [cover, how, timeline, habitat].concat(briefs.flat(), [emergency, sources]);
    let left = 98 - fixed.reduce((n, sec) => n + this.bookPages(sec), 0);
    // Share the room out fairly: every station's first must-do job before any
    // station's second, and the IF TIME jobs last. Otherwise station 1 would eat
    // the whole book and the last station would get nothing.
    const order = [];
    detail.forEach((jobs, k) => jobs.forEach((sec, i) => order.push({ k, i, sec, optional: info[k].tasks[i].optional })));
    order.sort((a, b) => (a.optional - b.optional) || (a.i - b.i) || (a.k - b.k));
    const kept = detail.map(() => []);
    order.forEach((job) => {
      const need = this.bookPages(job.sec);
      if (need <= left) { kept[job.k].push(job); left -= need; }
    });
    kept.forEach((list) => list.sort((a, b) => a.i - b.i));
    const dropped = order.length - kept.reduce((n, list) => n + list.length, 0);

    const out = [cover, how, timeline, habitat];
    briefs.forEach((b, k) => out.push(b[0], b[1], ...kept[k].map((job) => job.sec)));
    out.push(emergency + (dropped
      ? `\n${dropped} job${dropped > 1 ? "s" : ""} did not fit this book: those steps are on the printed cuff and the website.`
      : ""), sources);
    return out;
  },

  async send() {
    const res = Plan.result;
    if (!res || res.error) return PlanUI.say("Plan a walk first (habitat + 2-5 stations), then send it.");
    // A new walk needs new ground, and Minecraft holds its chunk files open while a world
    // is loaded, so the bridge closes the world, writes the band, and opens it again.
    PlanUI.say("Building the Mars ground along your walk… Minecraft will close and re-open "
               + "itself (about 30-60 seconds). Don't touch it until it comes back.");
    try {
      const r = await fetch("/api/route", { method: "POST", headers: { "Content-Type": "application/json" },
                                             body: JSON.stringify(this.payload()) });
      const out = await r.json();
      PlanUI.refresh();
      // The world now holds different ground, so ask the bridge again and redraw.
      fetch("/api/area").then((x) => x.json()).then((a) => { this.area = a; this.drawCorridor(); });
      document.getElementById("plan-out").insertAdjacentHTML("afterbegin",
        `<div class="${out.ok ? "ok" : "warn"}">⛏ ${out.message}</div>`);
    } catch (err) {
      PlanUI.say("Could not reach the MarsCuff bridge: is start.py still running? (" + err.message + ")");
    }
  },

  // Re-open the last plan sent to Minecraft and show its cuff (link from the Minecraft chat).
  async openLastCuff() {
    const last = await (await fetch("/api/last-plan")).json();
    if (!last.habitat) return;
    Plan.setHabitat({ row: last.habitat.row, col: last.habitat.col });
    Plan.stations = last.stations.map((s) => ({ row: s.row, col: s.col }));
    PlanUI.setMode("station");
    PlanUI.refresh();
    PlanUI.previewCuff();
  },
};
