// planui.js - the clicking part: place the habitat and stations, draw the route,
// the Point of No Return pin, and the timeline panel.

const PlanUI = {
  mode: "habitat",        // what the next map click does: "habitat" or "station"
  markers: [],            // Leaflet markers for habitat + stations
  drawn: L.featureGroup(),  // route line + PNR pin (a featureGroup can tell us its bounds)

  init(map) {
    this.map = map;
    this.drawn.addTo(map);
    map.on("click", (e) => this.onMapClick(e.latlng));
    document.getElementById("btn-habitat").onclick = () => this.setMode("habitat");
    document.getElementById("btn-station").onclick = () => this.setMode("station");
    document.getElementById("btn-clear").onclick = () => this.clear();
    document.getElementById("btn-suggest").onclick = () => this.suggest();
    // "Remove this station" button inside a station's pop-up card.
    map.on("popupopen", (e) => {
      const b = e.popup.getElement().querySelector("[data-remove]");
      if (b) b.onclick = () => this.removeStation(Number(b.dataset.remove));
    });
    document.getElementById("btn-preview").onclick = () => this.previewCuff();
    document.getElementById("btn-print").onclick = () => { if (Cuff.build()) window.print(); else this.say("Plan a walk first."); };
    document.getElementById("btn-close-cuff").onclick = () => document.body.classList.remove("show-cuff");
    this.setMode("habitat");
    this.refresh();          // replaces "Loading NASA data…" with the first instruction
  },

  setMode(mode) {
    this.mode = mode;
    document.getElementById("btn-habitat").classList.toggle("active", mode === "habitat");
    document.getElementById("btn-station").classList.toggle("active", mode === "station");
  },

  onMapClick(latlng) {
    const cell = Grid.cellAt(latlng.lat, latlng.lng);
    if (!cell) return this.say("That spot is outside our elevation data.");
    if (!Route.walkable(cell.row, cell.col)) {
      return this.say(`Can't stand there: slope over ${MODELS.slopeBlockedDeg}° or no data.`);
    }
    if (this.mode === "habitat") {
      this.say("Working out walking times home from every cell…");
      setTimeout(() => {               // let the message show before the heavy maths
        Plan.setHabitat(cell);
        this.setMode("station");
        this.refresh();
      }, 20);
    } else {
      if (!Plan.habitat) return this.say("Place the habitat first.");
      if (Plan.stations.length >= 5) return this.say("Maximum 5 stations (playbook: 2–5).");
      Plan.stations.push(cell);
      this.refresh();
      this.openCard(Plan.stations.length - 1);   // show what to do at the new station
    }
  },

  // Delete ONE station (k = 0 for station 1) and keep the rest of the plan.
  removeStation(k) {
    Plan.stations.splice(k, 1);
    this.map.closePopup();
    this.refresh();
  },

  // Suggest stations: the spots with the most science only people can do, that the
  // crew can still reach. It uses only our Question score (the purple glow: rock no
  // rover has touched, ground orbit sees too blurry, contacts that show which rock is
  // older) and our walking model, so it is a MODEL suggestion, not NASA's own list.
  suggest() {
    if (!Plan.habitat) return this.say("First do step 1: tap the map to place the habitat. Then press Suggest.");
    this.say("Looking for the best science stations you can reach…");
    setTimeout(() => {
      const maxHome = MODELS.usableSeconds() / 4;  // each station within 1/4 of the day's walking budget from home
      const cand = [];
      for (let r = 0; r < Grid.meta.rows; r += 2) {
        for (let c = 0; c < Grid.meta.cols; c += 2) {
          const unit = Grid.unitAt(r, c);
          if (!unit || !Route.walkable(r, c)) continue;
          const home = Plan.homeField[Grid.index(r, c)];
          if (!Number.isFinite(home) || home > maxHome) continue;
          const score = Grid.questionAt(r, c).score;
          if (score > 0) cand.push({ row: r, col: c, unit, score, home });
        }
      }
      // Most science first; if equal, the one closer to home (less walking, more working).
      cand.sort((a, b) => b.score - a.score || a.home - b.home);
      const picks = [];
      for (const k of cand) {
        if (picks.length === 3) break;
        if (picks.some((p) => p.unit === k.unit)) continue;   // a different rock type at every station
        const { dx, dy } = Grid.cellSizeMetres(k.row);
        const far = (p) => Math.hypot((p.row - k.row) * dy, (p.col - k.col) * dx) >= 200;
        if (!far(Plan.habitat) || !picks.every(far)) continue;   // 200 m from home and from each other
        picks.push(k);
      }
      if (!picks.length) return this.say("No science spots within reach of this habitat. Try moving it closer to the purple glow.");
      // Visit them in a loop around the habitat (sorted by direction), not zig-zag.
      const h = Plan.habitat;
      picks.sort((a, b) => Math.atan2(a.row - h.row, a.col - h.col) - Math.atan2(b.row - h.row, b.col - h.col));
      Plan.stations = picks.map(({ row, col }) => ({ row, col }));
      // Too long for one EVA? Drop the last station until it fits.
      let res = Plan.compute();
      while (Plan.stations.length > 1 && (!res || res.error || !res.fits)) { Plan.stations.pop(); res = Plan.compute(); }
      this.setMode("station");
      this.refresh();
    }, 20);
  },

  clear() {
    Plan.habitat = null;
    Plan.stations = [];
    Plan.result = null;
    this.setMode("habitat");
    this.refresh();
  },

  // Redraw markers, route, PNR and timeline from the current plan.
  refresh() {
    const res = Plan.compute();
    this.markers.forEach((m) => this.map.removeLayer(m));
    this.markers = [];
    this.drawn.clearLayers();

    if (Plan.habitat) this.addMarker(Plan.habitat, "H", "habitat", null);
    const cards = Science.describeAll(Plan.stations);
    Plan.stations.forEach((s, k) => this.addMarker(s, String(k + 1), "station", k, Science.cardHtml(cards[k], k + 1)));

    if (!res) return this.say(Plan.habitat
      ? "Step 2: tap 2–5 places to explore (the glow = science only people can do), or press ✨ Suggest."
      : "Step 1: tap the map to place the habitat, the astronauts' home (try near the Perseverance landing site). Or press ▶ Demo to watch.");
    if (res.error) return this.say(res.error);

    // Route line, one polyline per leg.
    res.legs.forEach((leg) => {
      const pts = leg.cells.map((c) => { const p = Grid.latLonOf(c.row, c.col); return [p.lat, p.lon]; });
      L.polyline(pts, { color: "#00e5ff", weight: 4, opacity: 0.95 }).addTo(this.drawn);
    });

    // Point of No Return pin.
    if (res.pnr) {
      const p = Grid.latLonOf(res.pnr.row, res.pnr.col);
      L.marker([p.lat, p.lon], { icon: L.divIcon({ className: "pnr-pin", html: "PNR", iconSize: [40, 22] }) })
        .bindTooltip(`Point of No Return at EVA ${hm(res.pnr.clock)}: beyond here you can't get home with the ${MODELS.reserveFraction * 100}% reserve.`)
        .addTo(this.drawn);
    }
    this.showTimeline(res);
  },

  addMarker(cell, label, kind, stationIndex, cardHtml) {
    const p = Grid.latLonOf(cell.row, cell.col);
    const m = L.marker([p.lat, p.lon], {
      draggable: true,
      icon: L.divIcon({ className: `pin pin-${kind}`, html: label, iconSize: [26, 26] }),
    }).addTo(this.map);
    if (cardHtml) cardHtml += `<button class="remove-stop" data-remove="${stationIndex}">✕ Remove this station</button>`;
    if (cardHtml) m.bindPopup(cardHtml, { maxWidth: 270, autoPanPadding: [10, 10] });   // tap a station pin = its card
    // Dragging a pin moves the habitat/station and recomputes everything.
    m.on("dragend", () => {
      const ll = m.getLatLng();
      const c = Grid.cellAt(ll.lat, ll.lng);
      if (!c || !Route.walkable(c.row, c.col)) { this.say("Can't stand there - pin moved back."); return this.refresh(); }
      if (kind === "habitat") Plan.setHabitat(c); else Plan.stations[stationIndex] = c;
      this.refresh();
    });
    this.markers.push(m);
  },

  // Open the card of station k (0 = first station). Markers list = habitat first, then stations.
  openCard(k) {
    const m = this.markers[k + 1];
    if (m) m.openPopup();
  },

  previewCuff() {
    if (!Cuff.build()) return this.say("Plan a walk first.");
    document.body.classList.add("show-cuff");
  },

  showTimeline(res) {
    const info = Science.describeAll(Plan.stations);
    const rows = res.events.map((e) => {
      const flag = e.beyondPnr ? ' <b class="warn">beyond PNR</b>' : "";
      const tb = e.turnBackBy !== undefined ? ` <small>(turn back by ${hm(e.turnBackBy)})</small>` : "";
      let sci = "";
      if (e.turnBackBy !== undefined) {
        const d = info[e.station];
        sci = `<br><small>${d.unit || "unit not mapped"} · Question ${d.question.score}/3 · value ${d.value}` +
              `${d.neverDriven ? " · ★ never driven by Perseverance" : ""} · <a href="#" data-card="${e.station}">tasks</a> · ` +
              `<a href="#" data-remove="${e.station}">✕ remove</a></small>`;
      }
      return `<tr><td>${hm(e.t)}</td><td>${e.what}${tb}${flag}${sci}</td></tr>`;
    }).join("");
    const verdict = res.fits
      ? `<span class="ok">Fits: ${hm(res.totalSeconds)} of ${hm(res.usable)} usable</span>`
      : `<span class="warn">Too long: ${hm(res.totalSeconds)} &gt; ${hm(res.usable)} usable</span>`;
    document.getElementById("plan-out").innerHTML =
      `${verdict} <small>· Step 3: press Preview cuff</small><br>Walk: ${(res.metres / 1000).toFixed(2)} km · ` +
      (res.pnr ? `<b class="warn">PNR at EVA ${hm(res.pnr.clock)}</b>` : "No Point of No Return on this plan") +
      `<table>${rows}</table>` +
      `<small class="model">Times are a MODEL: ${MODELS.walkSource} ${MODELS.stationWorkSource} ` +
      `Budget: ${MODELS.evaBudgetSource} ${MODELS.reserveSource}</small>`;
    // "tasks" links in the timeline open that station's card on the map.
    document.querySelectorAll("#plan-out [data-card]").forEach((a) => {
      a.onclick = (ev) => { ev.preventDefault(); this.openCard(Number(a.dataset.card)); };
    });
    document.querySelectorAll("#plan-out [data-remove]").forEach((a) => {
      a.onclick = (ev) => { ev.preventDefault(); this.removeStation(Number(a.dataset.remove)); };
    });
  },

  say(text) { document.getElementById("plan-out").textContent = text; },
};
