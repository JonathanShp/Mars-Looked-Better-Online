// plan.js - the walk plan: habitat, stations, route, timeline, Point of No Return.
//
// How a plan is worked out (recomputed every time something moves):
//   1. Route legs: habitat -> station 1 -> ... -> last station -> habitat (A*).
//   2. Timeline: walking time of each leg + MODELS.stationWorkMinutes per station.
//   3. Point of No Return (PNR): walking the route from the start, the FIRST
//      point where   time so far + time to walk straight home  >  usable budget
//      (usable budget = 8 h EVA minus the 20% reserve).
//      Past that point the crew could not get home with the reserve intact.

const Plan = {
  habitat: null,         // {row, col}
  stations: [],          // [{row, col}]
  homeField: null,       // seconds to walk home from every cell
  result: null,          // the latest computed plan (see compute())

  setHabitat(cell) {
    this.habitat = cell;
    this.homeField = Route.timeHomeField(cell);   // only changes when the habitat moves
  },

  // Work out the whole plan. Returns an object the screen and the cuff both use.
  compute() {
    if (!this.habitat || this.stations.length === 0) return (this.result = null);
    const stops = [this.habitat, ...this.stations, this.habitat];
    const legs = [];
    for (let k = 1; k < stops.length; k++) {
      const leg = Route.findPath(stops[k - 1], stops[k]);
      if (!leg) return (this.result = { error: `No safe path to ${k === stops.length - 1 ? "the habitat" : "station " + k} (slopes over ${MODELS.slopeBlockedDeg}° or no data block the way).` });
      legs.push(leg);
    }

    // Timeline: walk every leg, stop at each station to work.
    const work = MODELS.stationWorkMinutes * 60;
    const usable = MODELS.usableSeconds();
    const events = [{ what: "Leave habitat", t: 0 }];
    const routeCells = [];          // every cell walked, with the clock time we are there
    let clock = 0, metres = 0;
    legs.forEach((leg, k) => {
      leg.cells.forEach((c) => routeCells.push({ ...c, clock: clock + c.t }));
      clock += leg.seconds;
      metres += leg.metres;
      if (k < this.stations.length) {
        const st = this.stations[k];
        events.push({ what: `Arrive station ${k + 1}`, t: clock, station: k,
                      // Latest time to LEAVE this station and still get home inside the budget.
                      turnBackBy: usable - this.homeField[Grid.index(st.row, st.col)] });
        clock += work;
        routeCells.push({ ...st, t: 0, clock });      // standing still while working
        events.push({ what: `Leave station ${k + 1}`, t: clock, station: k });
      }
    });
    events.push({ what: "Back at habitat", t: clock });

    // Point of No Return: first route point where clock + time home > usable.
    let pnr = null;
    for (const c of routeCells) {
      if (c.clock + this.homeField[Grid.index(c.row, c.col)] > usable) { pnr = c; break; }
    }
    // Any station reached after the PNR is beyond safe reach.
    events.forEach((e) => { e.beyondPnr = pnr !== null && e.station !== undefined && e.t > pnr.clock; });

    return (this.result = { legs, events, routeCells, totalSeconds: clock, metres, pnr, usable,
                            fits: clock <= usable });
  },
};

// "2:05" style time from seconds.
function hm(seconds) {
  const m = Math.round(seconds / 60);
  return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`;
}
