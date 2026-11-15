// minecraft.js - "Send to Minecraft": builds your planned walk inside a true-scale
// Minecraft model of Jezero Crater (see minecraft/README.md).
//
// The button only appears when this page is opened from the MarsCuff bridge
// (http://localhost:8770 on the computer that runs the Minecraft server).
// On the public website it stays hidden, so nothing changes there.

const MC = {
  available: location.port === "8770",

  init() {
    if (!this.available) return;
    const btn = document.getElementById("btn-minecraft");
    btn.hidden = false;
    btn.onclick = () => this.send();
    if (location.hash === "#cuff") this.openLastCuff();     // the chat link inside Minecraft
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

  // The cuff as short book sections (the bridge wraps them into 19-character lines).
  bookSections(res, info) {
    const s = [];
    s.push(`MARSCUFF\nJezero EVA cuff\n\n${(res.metres / 1000).toFixed(2)} km walk\n` +
           `${hm(res.totalSeconds)} of ${hm(res.usable)} usable\n${res.fits ? "FITS" : "TOO LONG"}\n` +
           (res.pnr ? `PNR at EVA ${hm(res.pnr.clock)}` : "No Point of No Return"));
    s.push("HOW TO FOLLOW\nGlowing arrows in the sky = route.\nRed arrows = past the PNR.\n" +
           "White beam = habitat.\nPurple beams = stations.\nRed beam = PNR.");
    s.push("TIMELINE\n" + res.events.map((e) =>
      `${hm(e.t)} ${e.what.replace("station", "sta")}${e.turnBackBy !== undefined ? ` (go by ${hm(e.turnBackBy)})` : ""}${e.beyondPnr ? " PAST PNR" : ""}`).join("\n"));
    info.forEach((d, k) => {
      const a = res.events.find((e) => e.station === k && e.what.startsWith("Arrive"));
      s.push(`STATION ${k + 1}\n${d.unit || "Rock not mapped"}\nArrive ${hm(a.t)}\nLeave by ${hm(a.turnBackBy)}` +
             `${d.neverDriven ? "\n* Never driven by Perseverance" : ""}${a.beyondPnr ? "\nBEYOND PNR - SKIP" : ""}`);
      s.push(`STATION ${k + 1} TASKS\n` + (d.tasks.length
        ? d.tasks.map((t, i) => `${i + 1}. ${t.task}`).join("\n")
        : "No orbital gap here. Consider moving it."));
    });
    s.push("EMERGENCY\n" + Plan.stations.map((st, k) =>
      `Sta ${k + 1}: ${hm(Plan.homeField[Grid.index(st.row, st.col)])} walk home`).join("\n") +
      "\nSuit alarm: walk straight home." + (res.pnr ? `\nNever pass the PNR after ${hm(res.pnr.clock)}.` : ""));
    s.push("SOURCES\nGround: USGS CTX DTM (MRO). Rocks: Stack et al. 2020. Tracks: NASA/JPL Mars 2020. " +
           "Times: MODEL (Tobler x 0.6, team assumptions). 1 block = 10 m.");
    return s;
  },

  async send() {
    const res = Plan.result;
    if (!res || res.error) return PlanUI.say("Plan a walk first (habitat + 2-5 stations), then send it.");
    PlanUI.say("Building your route in Minecraft… (about 10-30 seconds)");
    try {
      const r = await fetch("/api/route", { method: "POST", headers: { "Content-Type": "application/json" },
                                             body: JSON.stringify(this.payload()) });
      const out = await r.json();
      PlanUI.refresh();
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
