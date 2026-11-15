// route.js - finds safe walking routes on the 40 m grid and times them.
//
// The ground is a grid of cells. From a cell you can step to any of its 8
// neighbours. A step is NOT allowed onto a cell that is too steep
// (slope > MODELS.slopeBlockedDeg) or has no elevation data.
// The "cost" of a step is the TIME it takes to walk it (Tobler's function).

// ---- A tiny priority queue (binary heap): always hands back the smallest item.
// Keys (times) and values (cell numbers) live in two plain number arrays,
// which is much faster in the browser than lots of little [key, value] pairs.
class MinHeap {
  constructor() { this.keys = new Float64Array(1 << 16); this.vals = new Int32Array(1 << 16); this.size = 0; }
  grow() {
    const k = new Float64Array(this.keys.length * 2); k.set(this.keys); this.keys = k;
    const v = new Int32Array(this.vals.length * 2); v.set(this.vals); this.vals = v;
  }
  push(key, value) {
    if (this.size === this.keys.length) this.grow();
    const K = this.keys, V = this.vals;
    let i = this.size++;
    while (i > 0) {                                   // bubble up: move bigger parents down
      const p = (i - 1) >> 1;
      if (K[p] <= key) break;
      K[i] = K[p]; V[i] = V[p];
      i = p;
    }
    K[i] = key; V[i] = value;
  }
  pop() {                                             // returns [key, value] of the smallest
    const K = this.keys, V = this.vals;
    const topKey = K[0], topVal = V[0];
    const n = --this.size;
    const key = K[n], val = V[n];                     // last item, to sink down from the top
    let i = 0;
    while (true) {
      const l = 2 * i + 1;
      if (l >= n) break;
      const m = l + 1 < n && K[l + 1] < K[l] ? l + 1 : l;
      if (K[m] >= key) break;
      K[i] = K[m]; V[i] = V[m];
      i = m;
    }
    K[i] = key; V[i] = val;
    return [topKey, topVal];
  }
}

const NEIGHBOURS = [[-1, -1], [-1, 0], [-1, 1], [0, -1], [0, 1], [1, -1], [1, 0], [1, 1]];

const Route = {
  // Speed-up tables, filled once by prepare(): looking a number up in a table
  // is much faster than recomputing it hundreds of thousands of times.
  canWalk: null,   // 1 = safe to stand on, 0 = blocked (too steep or no data)
  dxRow: null,     // east-west ground width of a cell, for each row (metres)
  dy: 0,           // north-south ground height of a cell (metres)

  prepare() {
    const { rows, cols } = Grid.meta;
    this.canWalk = new Uint8Array(rows * cols);
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const s = Grid.slopeAt(r, c);
        this.canWalk[r * cols + c] = s !== null && s <= MODELS.slopeBlockedDeg ? 1 : 0;
      }
    }
    this.dxRow = new Float64Array(rows);
    for (let r = 0; r < rows; r++) this.dxRow[r] = Grid.cellSizeMetres(r).dx;
    this.dy = Grid.cellSizeMetres(0).dy;
  },

  // Can an astronaut stand on this cell?
  walkable(row, col) {
    return this.canWalk[Grid.index(row, col)] === 1;
  },

  // Ground distance in metres between two neighbouring cells.
  stepMetres(r1, c1, r2, c2) {
    return Math.hypot((c2 - c1) * this.dxRow[r1], (r2 - r1) * this.dy);
  },

  // Seconds to walk from cell 1 to neighbouring cell 2 (uphill is slower).
  stepSeconds(r1, c1, r2, c2) {
    const metres = this.stepMetres(r1, c1, r2, c2);
    const cols = Grid.meta.cols;
    const grade = (Grid.elev[r2 * cols + c2] - Grid.elev[r1 * cols + c1]) / metres;
    return metres / MODELS.walkSpeedMs(grade);
  },

  // A* search: the quickest safe path from start to goal ({row, col} each).
  // Returns { cells: [{row, col, t}], seconds, metres } or null if no safe path.
  findPath(start, goal) {
    const { rows, cols } = Grid.meta;
    if (!this.walkable(start.row, start.col) || !this.walkable(goal.row, goal.col)) return null;

    const n = rows * cols;
    const best = new Float64Array(n).fill(Infinity);   // best known time to each cell
    const cameFrom = new Int32Array(n).fill(-1);
    const startI = Grid.index(start.row, start.col);
    const goalI = Grid.index(goal.row, goal.col);
    const fastest = MODELS.maxWalkSpeedMs();
    const { dx, dy } = Grid.cellSizeMetres(goal.row);
    // Guess of time left: straight-line distance at the fastest possible speed.
    // It never over-guesses, so A* still finds the truly quickest path.
    const guess = (r, c) => Math.hypot((c - goal.col) * dx, (r - goal.row) * dy) / fastest;

    const open = new MinHeap();
    best[startI] = 0;
    open.push(guess(start.row, start.col), startI);

    while (open.size > 0) {
      const [, i] = open.pop();
      if (i === goalI) break;
      const r = Math.floor(i / cols), c = i % cols;
      for (const [dr, dc] of NEIGHBOURS) {
        const nr = r + dr, nc = c + dc;
        if (nr < 0 || nc < 0 || nr >= rows || nc >= cols || !this.walkable(nr, nc)) continue;
        const ni = nr * cols + nc;
        const t = best[i] + this.stepSeconds(r, c, nr, nc);
        if (t < best[ni]) {
          best[ni] = t;
          cameFrom[ni] = i;
          open.push(t + guess(nr, nc), ni);
        }
      }
    }
    if (best[goalI] === Infinity) return null;

    // Walk backwards from the goal to rebuild the path.
    const cells = [];
    for (let i = goalI; i !== -1; i = cameFrom[i]) {
      cells.push({ row: Math.floor(i / cols), col: i % cols, t: best[i] });
    }
    cells.reverse();
    let metres = 0;
    for (let k = 1; k < cells.length; k++) {
      metres += this.stepMetres(cells[k - 1].row, cells[k - 1].col, cells[k].row, cells[k].col);
    }
    return { cells, seconds: best[goalI], metres };
  },

  // Time to walk HOME from every cell (Dijkstra outward from home, with each
  // step timed in the direction of walking home). Infinity = can't get home.
  timeHomeField(home) {
    const { rows, cols } = Grid.meta;
    const field = new Float64Array(rows * cols).fill(Infinity);
    const homeI = Grid.index(home.row, home.col);
    const open = new MinHeap();
    field[homeI] = 0;
    open.push(0, homeI);
    while (open.size > 0) {
      const [t0, i] = open.pop();
      if (t0 > field[i]) continue;                     // old queue entry, skip
      const r = Math.floor(i / cols), c = i % cols;
      for (const [dr, dc] of NEIGHBOURS) {
        const nr = r + dr, nc = c + dc;
        if (nr < 0 || nc < 0 || nr >= rows || nc >= cols) continue;
        const ni = nr * cols + nc;
        if (!this.canWalk[ni]) continue;
        // Walking home means stepping FROM the neighbour TO this cell.
        const t = field[i] + this.stepSeconds(nr, nc, r, c);
        if (t < field[ni]) { field[ni] = t; open.push(t, ni); }
      }
    }
    return field;
  },
};
