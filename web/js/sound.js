// sound.js - small, soft sounds made in code with the Web Audio API.
// No sound files are downloaded: every sound is a short tone the browser plays.
// Browsers only allow sound after a click, so the first sound comes with the first tap.
//   tap   = any button
//   place = a habitat or station goes on the map
//   warn  = a Point of No Return appears on the plan
// The "Sound" button turns it all on or off.

const Sound = {
  on: true,
  ctx: null,

  // Play one soft tone: frequency in Hz, length in ms, starting `delay` ms from now.
  tone(freq, ms = 90, vol = 0.06, type = "sine", delay = 0) {
    if (!this.on) return;
    try {
      this.ctx = this.ctx || new (window.AudioContext || window.webkitAudioContext)();
      const t = this.ctx.currentTime + delay / 1000;
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = type;
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0, t);
      gain.gain.linearRampToValueAtTime(vol, t + 0.01);          // quick fade in (no click)
      gain.gain.exponentialRampToValueAtTime(0.0001, t + ms / 1000);  // gentle fade out
      osc.connect(gain).connect(this.ctx.destination);
      osc.start(t);
      osc.stop(t + ms / 1000 + 0.02);
    } catch (e) { /* no sound support: the site works the same without it */ }
  },

  tap()   { this.tone(1200, 40, 0.03); },
  place() { this.tone(660, 120); this.tone(990, 160, 0.05, "sine", 80); },
  warn()  { this.tone(330, 220, 0.07, "triangle"); this.tone(247, 320, 0.07, "triangle", 200); },
};

// A soft tick on every button press.
document.addEventListener("click", (e) => { if (e.target.closest("button")) Sound.tap(); }, true);

// A rising two-note "pop" when something is placed on the map (also during the demo).
const _onMapClick = PlanUI.onMapClick;
PlanUI.onMapClick = function (latlng) {
  const before = Plan.stations.length, home = Plan.habitat;
  _onMapClick.call(this, latlng);
  setTimeout(() => { if (Plan.stations.length > before || Plan.habitat !== home) Sound.place(); }, 60);
};

// A low two-note warning the moment a plan first gets a Point of No Return.
const _refresh = PlanUI.refresh;
PlanUI.refresh = function () {
  const hadPnr = !!(Plan.result && Plan.result.pnr);
  _refresh.call(this);
  if (!hadPnr && Plan.result && Plan.result.pnr) Sound.warn();
};

// The on/off button.
document.getElementById("btn-sound").onclick = (e) => {
  Sound.on = !Sound.on;
  e.target.textContent = Sound.on ? "Sound on" : "Sound off";
};
