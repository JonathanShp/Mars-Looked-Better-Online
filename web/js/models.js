// models.js - every ASSUMPTION the app uses lives here, with its source.
// If a number on screen comes from a model and not straight from a dataset,
// it must come from this file so judges can see exactly where it came from.

const MODELS = {
  // Slope limits for walking in a suit (team assumptions, adjustable).
  slopeCautionDeg: 8,
  slopeBlockedDeg: 15,
  slopeSource: "Team assumption: caution above 8°, blocked above 15° (MarsCuff playbook).",

  // EVA time budget.
  evaBudgetHours: 8,
  evaBudgetSource: "NASA Human Mars surface concept of operations: EVAs of up to 8 hours.",
  reserveFraction: 0.2,
  reserveSource: "Team assumption: 20% of the EVA held in reserve.",

  // Time spent working at each station (photos + one sample).
  stationWorkMinutes: 30,
  stationWorkSource: "Team assumption: 30 min per station (to be checked by our geology expert).",

  // Walking speed in a suit.
  suitFactor: 0.6,
  walkSource: "Tobler's hiking function (Tobler 1993, Earth walkers) × 0.6 suit penalty (team assumption).",

  // Tobler's hiking function: walking speed in km/h from the ground's grade
  // (grade = metres up / metres along; downhill is negative).
  // Fastest (6 km/h) on a gentle 5% downhill, slower uphill and on steep downhill.
  toblerKmh(grade) {
    return 6 * Math.exp(-3.5 * Math.abs(grade + 0.05));
  },

  // Suited walking speed in metres per second.
  walkSpeedMs(grade) {
    return (6 * Math.exp(-3.5 * Math.abs(grade + 0.05)) * this.suitFactor) / 3.6;  // same as toblerKmh x suit, in m/s
  },

  // Fastest possible suited speed (used to make A* fast but still correct).
  maxWalkSpeedMs() {
    return (6 * this.suitFactor * 1000) / 3600;
  },

  usableSeconds() {
    return this.evaBudgetHours * 3600 * (1 - this.reserveFraction);
  },
};
