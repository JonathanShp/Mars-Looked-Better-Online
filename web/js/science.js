// science.js - what the crew does at each station, and why.
//
// Tasks are FIXED TEMPLATES written by the team (MarsCuff playbook, Question
// layer table) - never generated text. Each task names the gap it fills:
// "what can't orbit tell us here?"

const TASKS = {
  1: { signal: "Rover never went there",
       gap: "Rock texture and chemistry up close",
       task: "Close-up photo + one sample: first ground truth here." },
  2: { signal: "Only coarse terrain",
       gap: "Boulders, small scarps, real footing (only 20 m CTX elevation here)",
       task: "Photo-survey the walking surface; report slope and rock size." },
  4: { signal: "Geologic contact",
       gap: "Which layer sits on which",
       task: "Photograph the contact from two sides; one sample on each side." },
};
const TASK_SOURCE = "Task templates: MarsCuff team (playbook Question-layer table), pending expert review.";

const Science = {
  drivenUnits: null,   // bedrock units Perseverance's path crosses (from the traverse layer)

  // Which bedrock units did Perseverance drive across? (traverse line x unit grid)
  findDrivenUnits(traverseGeojson) {
    this.drivenUnits = new Set();
    traverseGeojson.features.forEach((f) =>
      f.geometry.coordinates.forEach(([lon, lat]) => {
        const c = Grid.cellAt(lat, lon);
        const u = c && Grid.unitAt(c.row, c.col);
        if (u) this.drivenUnits.add(u);
      }));
  },

  // Other bedrock units within 100 m (for the contact task: "which two units?").
  unitsNearby(cell, metres = 100) {
    const { dx, dy } = Grid.cellSizeMetres(cell.row);
    const k = Math.ceil(metres / Math.min(dx, dy));
    const here = Grid.unitAt(cell.row, cell.col);
    const found = new Set();
    for (let dr = -k; dr <= k; dr++) {
      for (let dc = -k; dc <= k; dc++) {
        if (Math.hypot(dr * dy, dc * dx) > metres) continue;
        const r = cell.row + dr, c = cell.col + dc;
        if (r < 0 || c < 0 || r >= Grid.meta.rows || c >= Grid.meta.cols) continue;
        const u = Grid.unitAt(r, c);
        if (u && u !== here) found.add(u);
      }
    }
    return [...found];
  },

  // Everything the cuff needs to know about one station.
  // seenUnits: units already visited earlier on THIS walk (for the +1 bonus).
  describeStation(cell, seenUnits) {
    const unit = Grid.unitAt(cell.row, cell.col);
    const q = Grid.questionAt(cell.row, cell.col);
    const tasks = [1, 2, 4].filter((b) => q.bits & b).map((b) => {
      const t = { ...TASKS[b] };
      if (b === 4) {
        const other = this.unitsNearby(cell);
        t.task = `Photograph the contact between ${unit} and ${other.join(" / ")} from two sides; one sample on each side.`;
      }
      return t;
    });
    const newUnitOnWalk = unit !== null && !seenUnits.has(unit);
    return {
      unit,
      unitMapped: unit !== null,
      neverDriven: unit !== null && !this.drivenUnits.has(unit),
      question: q,
      tasks,
      // Science value (playbook): Question score + 1 for a unit not yet visited on this walk.
      value: q.score + (newUnitOnWalk ? 1 : 0),
      newUnitOnWalk,
      elevation: Grid.elevationAt(cell.row, cell.col),
      slope: Grid.slopeAt(cell.row, cell.col),
      latlon: Grid.latLonOf(cell.row, cell.col),
    };
  },

  // The card that pops up on a station pin: what rock, why go, what to do.
  cardHtml(d, number) {
    const why = d.tasks.length
      ? d.tasks.map((t) => `<li>${t.signal}: <i>${t.gap}</i></li>`).join("")
      : "<li>No open question here: orbiters already see it well.</li>";
    const todo = d.tasks.map((t) => `<li>${t.task}</li>`).join("");
    return `<div class="card">
      <b class="card-title">Station ${number} · ${d.unit || "rock type not mapped"}</b>
      <small>${d.unit ? "Bedrock unit from Stack et al. 2020" : "Outside the Stack et al. 2020 rock map"}` +
      `${d.neverDriven ? " · ★ Perseverance never drove on this rock" : ""}</small>
      <div class="card-h">Why go here</div><ul>${why}</ul>
      ${todo ? `<div class="card-h">What to do</div><ol>${todo}</ol>` : ""}
      <small>Science value ${d.value} (reasons ${d.question.score}${d.newUnitOnWalk ? " + new rock on this walk" : ""}) ·
      ${d.elevation} m · slope ${d.slope.toFixed(1)}°<br>${TASK_SOURCE}</small></div>`;
  },

  // Describe all stations in walking order.
  describeAll(stations) {
    const seen = new Set();
    return stations.map((s) => {
      const d = this.describeStation(s, seen);
      if (d.unit) seen.add(d.unit);
      return d;
    });
  },
};
