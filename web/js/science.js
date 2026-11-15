// science.js - what the crew actually does at each station: real field protocols,
// which Mars 2020 instrument each step stands in for, where to stand, and how long it takes.
//
// IMPORTANT: every protocol below is a FIXED TEMPLATE written by the team from the
// published Mars 2020 instrument papers. Nothing here is generated, and no measurement
// or result is invented. The only made-up numbers are the MINUTES, which are a team
// assumption (MINUTES_SOURCE) picked so one station fits the 30 min the planner budgets.
//
// Which protocols a station gets comes from the Question layer, which says what orbit
// CANNOT already tell us there:
//   bit 1  no rover ever drove on this rock   -> ground truth: abrade, analyse, sample
//   bit 2  only coarse (20 m/px) terrain data -> footing survey at human scale
//   bit 4  a mapped contact between two rocks -> which layer sits on top of which
// Every station also gets the two baseline protocols, because on Mars 2020 nothing is
// ever touched before it has been imaged and shot from a distance first.

const MINUTES_SOURCE = "Minutes per step: MarsCuff team assumption, not a NASA figure. Steps marked IF TIME are the ones a crew drops first when the station runs long.";

// Done at every station, in this order.
const BASELINE = [
  {
    key: "recon", priority: 1,
    title: "Station recon panorama",
    stands_for: "Mastcam-Z, the stereo zoom cameras on the mast",
    why: "You cannot describe a rock you never framed. The panorama is the record every later step is tied to.",
    where: "Stand still at the station pin, on the flattest ground within about 5 m.",
    minutes: 5,
    steps: [
      "Put the scale bar (or your own boot, 30 cm) in view and note which way is north.",
      "Shoot a full circle of overlapping photos from one spot, about 20 degrees apart, held level.",
      "Shoot the same circle again one pace to the right, so the pair is stereo and gives depth.",
      "Say out loud and write down: station number, time on the EVA clock, what the ground is made of.",
    ],
    source: "Bell et al. 2021, Mastcam-Z; Farley et al. 2020, Mars 2020 mission overview.",
  },
  {
    key: "triage", priority: 1,
    title: "Remote triage of three targets",
    stands_for: "SuperCam, laser spectroscopy from a distance (out to roughly 7 m)",
    why: "Decide which few rocks are worth touching before spending suit time on any of them.",
    where: "Pick three rocks 2 to 7 m away that differ: one bedrock face, one loose rock, one dusty patch.",
    minutes: 5,
    steps: [
      "Number the three targets in the panorama and photograph each one zoomed in.",
      "For each: note grain size, colour, layering, and whether it is in place or loose.",
      "Rank them for the next protocol. In place beats loose; a fresh face beats a dusty one.",
      "Write down the one you rejected and why. A rejection is data too.",
    ],
    source: "Wiens et al. 2021 and Maurice et al. 2021, SuperCam.",
  },
];

// Protocols chosen by the Question layer. The keys are the Question bits.
const PROTOCOLS = {
  1: {
    signal: "No rover has ever driven on this rock type",
    gap: "Texture and chemistry up close: nobody has ever had this rock in front of them",
    list: [
      {
        key: "abrade", priority: 1,
        title: "Abrade a patch and look inside",
        stands_for: "the abrading bit with WATSON and SHERLOC (close-up camera, deep-UV Raman and fluorescence)",
        why: "Mars is covered in dust and a weathered rind. The real rock starts a few millimetres down.",
        where: "On bedrock still attached to the ground, on a face you can reach standing up.",
        minutes: 10,
        steps: [
          "Brush the dust off a patch about the size of your palm.",
          "Grind a flat patch about 5 cm across and a few mm deep, the size Perseverance makes.",
          "Photograph the patch close up, filling the frame, with the scale bar touching it.",
          "Describe the fresh surface: grain size, cement between grains, veins, how it differs from the rind.",
          "Shade the patch with your body and look for anything that glows. That is the organics check.",
        ],
        source: "Bhartia et al. 2021, SHERLOC; Mars 2020 abrasion patches are about 5 cm across.",
      },
      {
        key: "chem", priority: 1,
        title: "Elemental map of the fresh patch",
        stands_for: "PIXL, micro X-ray fluorescence with a spot about a tenth of a millimetre wide",
        why: "A map of which elements sit where tells you whether the rock is volcanic or was laid down in water.",
        where: "The patch you just abraded, without moving the scale bar.",
        minutes: 5,
        steps: [
          "Lay a grid over the close-up photo: a few millimetres across, ten by ten.",
          "Work across the grid and note every change of colour or crystal shape, cell by cell.",
          "Mark grains that look like salt, carbonate or clay. Those are the water-formed ones.",
          "Write down whether the chemistry looks the same everywhere or comes in patches. Patches mean water moved through.",
        ],
        source: "Allwood et al. 2020, PIXL.",
      },
      {
        key: "core", priority: 1,
        title: "Take a sealed core",
        stands_for: "the Mars 2020 coring bit and sample tubes",
        why: "This is the only step that can ever be checked in a lab on Earth. Treat it as the point of the walk.",
        where: "Within one arm length of the abraded patch, in the same bedrock, never in a loose block.",
        minutes: 8,
        steps: [
          "Core about 6 cm long and 1.3 cm wide, like a Mars 2020 tube, and keep it in one piece.",
          "Seal the tube and label it: tube number, station, time, and which way was up.",
          "Photograph the hole you left and the tube together, so the sample can never be mixed up.",
          "Take one witness sample of the nearby air and dust, so contamination can be ruled out later.",
          "Say the tube number on the radio and write it on the cuff.",
        ],
        source: "Farley et al. 2020, Mars 2020 sampling and caching.",
      },
    ],
  },
  2: {
    signal: "Orbit only sees this ground at about 20 m per pixel",
    gap: "Boulders, small scarps and real footing: anything smaller than a house is invisible from orbit",
    list: [
      {
        key: "footing", priority: 2,
        title: "Footing and boulder survey",
        stands_for: "the job no orbiter can do: roughness at human scale",
        why: "Ground that looks walkable in a 20 m elevation map can be a boulder field. Future crews route around what you measure here.",
        where: "Pace out a 10 m by 10 m square with the station pin at one corner.",
        minutes: 8,
        steps: [
          "Count every rock wider than your boot inside the square, in four strips so you do not lose count.",
          "Measure the three biggest: length, width, and height above the ground.",
          "Measure the slope in two directions with the inclinometer and note which way is downhill.",
          "Photograph the square from one corner at chest height, and once straight down at your feet.",
          "Rate it for a future crew: easy walking, slow going, or go around.",
        ],
        source: "Terrain here is the USGS CTX DTM (MRO) at about 20 m per pixel, so finer roughness has to be measured on foot.",
      },
    ],
  },
  4: {
    signal: "A mapped contact between two rock units runs through here",
    gap: "Which rock sits on top of which, and therefore which one is older",
    list: [
      {
        key: "contact", priority: 2,
        title: "Read the contact",
        stands_for: "classic field geology, the way Apollo crews worked a traverse",
        why: "Order is time. Once you know which unit lies on the other, every sample from both gets an age order for free.",
        where: "Walk the contact until you find a spot where both rocks are exposed within a few metres of each other.",
        minutes: 12,
        steps: [
          "Photograph the contact from both sides, each time with the scale bar lying across the line.",
          "Measure how the layers tilt: the compass direction they run and how steeply they dip.",
          "Follow the contact about 20 m each way and note whether it stays straight, cuts across, or fades out.",
          "Take one sample from each side, within 2 m of the line, labelled A (lower) and B (upper).",
          "Write down which one you think is on top, and the one thing you saw that decided it.",
        ],
        source: "Contacts from Stack et al. 2020, Jezero geologic map; field method after Apollo traverse geology.",
      },
    ],
  },
};

// Done at the habitat rather than at a station: the weather log that makes the rest readable.
const HABITAT_PROTOCOL = {
  key: "weather", priority: 1,
  title: "Weather and dust log",
  stands_for: "MEDA, the weather station on Perseverance",
  why: "Wind and dust decide whether your photos and your suit survive the walk, and tie your day to the orbital record.",
  where: "At the habitat, once before you leave and again when you get back.",
  minutes: 3,
  steps: [
    "Note the time, the temperature, the wind direction and how hard it is blowing.",
    "Look across the crater floor for dust devils and count them.",
    "Photograph the sky to the north with the same exposure both times, so the haze can be compared.",
    "If the view got hazier while you were out, say so. It changes how your pictures should be read.",
  ],
  source: "Rodriguez-Manfredi et al. 2021, MEDA.",
};

const Science = {
  drivenUnits: null,   // bedrock units Perseverance's path crosses (from the traverse layer)
  habitatProtocol: HABITAT_PROTOCOL,

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

  // Other bedrock units within 100 m (for the contact protocol: "which two units?").
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
    const neighbours = this.unitsNearby(cell);

    // Baseline first, then whatever the Question layer asks for in this cell.
    const tasks = BASELINE.map((p) => this.fill(p, unit, neighbours, null));
    [1, 2, 4].forEach((bit) => {
      if (!(q.bits & bit)) return;
      const group = PROTOCOLS[bit];
      group.list.forEach((p) => tasks.push(this.fill(p, unit, neighbours, group)));
    });
    // A crew works the must-do steps first and only then the rest, because the
    // clock can run out. Sorting keeps that order no matter which gaps fired.
    tasks.sort((a, b) => a.priority - b.priority);

    const newUnitOnWalk = unit !== null && !seenUnits.has(unit);
    return {
      unit,
      unitMapped: unit !== null,
      neverDriven: unit !== null && !this.drivenUnits.has(unit),
      question: q,
      tasks,
      minutes: tasks.reduce((sum, t) => sum + t.minutes, 0),
      coreMinutes: tasks.filter((t) => !t.optional).reduce((sum, t) => sum + t.minutes, 0),
      extraMinutes: tasks.filter((t) => t.optional).reduce((sum, t) => sum + t.minutes, 0),
      budgetMinutes: MODELS.stationWorkMinutes,
      // Science value (playbook): Question score + 1 for a unit not yet visited on this walk.
      value: q.score + (newUnitOnWalk ? 1 : 0),
      newUnitOnWalk,
      elevation: Grid.elevationAt(cell.row, cell.col),
      slope: Grid.slopeAt(cell.row, cell.col),
      latlon: Grid.latLonOf(cell.row, cell.col),
    };
  },

  // Copy a template and drop this station's own rock names into it.
  // `task` stays one short line, because the map pins and the Minecraft book print it.
  fill(p, unit, neighbours, group) {
    const rock = unit || "the rock here";
    const other = neighbours.length ? neighbours.join(" / ") : "the next unit along";
    const t = Object.assign({}, p, {
      signal: group ? group.signal : "Done at every station",
      gap: group ? group.gap : "The record every later step hangs on",
      optional: p.priority === 2,
      baseline: !group,        // true for the two protocols every station gets
      task: `${p.title} (${p.minutes} min)${p.priority === 2 ? " IF TIME" : ""} - ${p.stands_for}`,
      steps: p.steps.slice(),
    });
    if (p.key === "contact") {
      t.where = `Walk the contact between ${rock} and ${other} until both are exposed within a few metres of each other.`;
      t.steps[3] = `Take one sample from each side of the ${rock} / ${other} line, within 2 m of it, labelled A (lower) and B (upper).`;
    }
    if (p.key === "core") t.where = `Within one arm length of the abraded patch, in ${rock} itself, never in a loose block.`;
    return t;
  },

  // The card that pops up on a station pin: what rock, why go, exactly what to do.
  cardHtml(d, number) {
    const open = [1, 2, 4].filter((b) => d.question.bits & b).map((b) => PROTOCOLS[b]);
    const why = open.length
      ? open.map((g) => `<li>${g.signal}: <i>${g.gap}</i></li>`).join("")
      : "<li>No open question here: orbiters already see this spot well, so only the baseline protocols apply. "
        + "Moving the station a few hundred metres usually finds a gap.</li>";
    const steps = d.tasks.map((t) => `<li><b>${t.title}</b> · ${t.minutes} min${t.optional ? " · <b>only if the clock allows</b>" : ""} · stands in for ${t.stands_for}
      <div class="task-why">${t.why}</div>
      <div class="task-where"><b>Where:</b> ${t.where}</div>
      <ol class="task-steps">${t.steps.map((s) => `<li>${s}</li>`).join("")}</ol>
      <small>${t.source}</small></li>`).join("");
    return `<div class="card">
      <b class="card-title">Station ${number} · ${d.unit || "rock type not mapped"}</b>
      <small>${d.unit ? "Bedrock unit from Stack et al. 2020" : "Outside the Stack et al. 2020 rock map"}` +
      `${d.neverDriven ? " · ★ Perseverance never drove on this rock" : ""}</small>
      <div class="card-h">Why go here</div><ul>${why}</ul>
      <div class="card-h">What to do, in order</div>
      <small>${d.coreMinutes} min of must-do work against the ${d.budgetMinutes} min the timeline books here${d.extraMinutes ? `, plus ${d.extraMinutes} min more if the clock allows` : ""}.</small>
      <ol class="protocols">${steps}</ol>
      <small>Science value ${d.value} (reasons ${d.question.score}${d.newUnitOnWalk ? " + new rock on this walk" : ""}) ·
      ${d.elevation} m · slope ${d.slope.toFixed(1)}°<br>${MINUTES_SOURCE}</small></div>`;
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
