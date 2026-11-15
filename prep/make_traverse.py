"""
make_traverse.py  -  Perseverance's real drive path, made small enough for the web.

Source: NASA/JPL Mars 2020 mission map (MMGIS) traverse file, downloaded from
https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_traverse.json
(file name inside: "M20_Traverse_Path_tosol2022" = drives up to sol 2022).

The raw file has every rover position (1.7 MB). We keep one line per sol,
drop the height values and round to 5 decimals (~0.6 m on Mars), which is
plenty for a 40 m map.

Output: web/data/traverse.geojson
"""

import json

RAW = "data/raw/M20_traverse.json"


def main():
    raw = json.load(open(RAW))
    features = []
    for f in raw["features"]:
        coords = [[round(p[0], 5), round(p[1], 5)] for p in f["geometry"]["coordinates"]]
        # Remove repeated points (the rover stood still).
        clean = [coords[0]] + [p for i, p in enumerate(coords[1:]) if p != coords[i]]
        if len(clean) < 2:
            continue
        features.append({"type": "Feature",
                         "properties": {"sol": f["properties"]["sol"]},
                         "geometry": {"type": "LineString", "coordinates": clean}})
    out = {
        "type": "FeatureCollection",
        "name": raw.get("name"),
        "source": "NASA/JPL Mars 2020 MMGIS, M20_traverse.json (" + raw.get("name", "") + ")",
        "features": features,
    }
    json.dump(out, open("web/data/traverse.geojson", "w"), separators=(",", ":"))
    sols = [f["properties"]["sol"] for f in features]
    print(f"{len(features)} drive segments, sols {min(sols)} to {max(sols)}")


if __name__ == "__main__":
    main()
