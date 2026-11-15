// demo.js - the "▶ Demo" button: plays the whole MarsCuff story by itself with
// big captions (about 28 seconds), so the 30-second video can be recorded in one take.
// Every number it shows comes from the same code as a normal click - nothing is faked.

const DEMO = {
  habitat: { lat: 18.4446, lng: 77.4509 },     // next to the Perseverance landing site
  stations: [                                  // 3 spots on rock boundaries (found in M3 testing)
    { lat: 18.4523, lng: 77.4348 },
    { lat: 18.4266, lng: 77.4334 },
    { lat: 18.4698, lng: 77.4294 },
  ],
  farStation: { lat: 18.62, lng: 77.24 },      // far away: the walk gets too long, so a PNR appears
};

// Tick or untick a layer's checkbox (so the layer panel stays in sync).
function setLayer(id, on) {
  const box = document.querySelector(`#layers input[data-layer="${id}"]`);
  if (box && box.checked !== on) { box.checked = on; box.dispatchEvent(new Event("change")); }
}

const Demo = {
  running: false,

  async play() {
    if (this.running) return;
    this.running = true;
    const caption = document.getElementById("caption");
    const say = (text) => { caption.textContent = text; caption.hidden = !text; };
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));

    // Start clean: map view, no plan, science glow on.
    document.body.classList.remove("show-cuff");
    map.closePopup();
    PlanUI.clear();
    setLayer("question", true);
    document.getElementById("layers").classList.add("folded");   // keep the map clear for the video
    map.fitBounds(Grid.leafletBounds());

    say("Jezero Crater, Mars · real NASA elevation, images and rock map");
    await wait(3500);
    say("Purple glow = places only astronauts can find out about");
    await wait(3500);

    say("1 · Put the habitat next to the Perseverance landing site");
    map.flyTo([18.448, 77.437], 12.5, { duration: 1 });   // zoom in on the landing area
    PlanUI.onMapClick(DEMO.habitat);
    await wait(2500);                                 // walking-time map takes ~1.5 s

    say("2 · Add stations · the route walks around steep slopes");
    for (const s of DEMO.stations) { PlanUI.onMapClick(s); await wait(900); }
    await wait(1200);
    say("Each station says WHY go there and WHAT to do");
    await wait(3000);
    map.closePopup();

    say("3 · Too far? The Point of No Return shows where to turn back");
    PlanUI.onMapClick(DEMO.farStation);
    map.closePopup();
    map.flyToBounds(PlanUI.drawn.getBounds(), { padding: [40, 40], duration: 1 });   // show the long walk + PNR
    await wait(4000);
    Plan.stations.pop();                              // remove the far station again
    PlanUI.refresh();

    say("4 · Print the astronaut's wrist checklist");
    PlanUI.previewCuff();
    await wait(4500);

    say("MarsCuff · NASA data from 4 missions");
    await wait(2500);
    say("");
    this.running = false;
  },
};

document.getElementById("btn-demo").onclick = () => Demo.play();
