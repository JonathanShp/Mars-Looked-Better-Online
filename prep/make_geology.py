"""
make_geology.py  -  Geologic units of Jezero for the map and for the science tasks.

Source: Stack et al. 2020, "Photogeologic Map of the Perseverance Rover Field
Site in Jezero Crater Constructed by the Mars 2020 Science Team",
Space Science Reviews 216:127, doi:10.1007/s11214-020-00739-x (CC BY 4.0).
Supplementary file ESM 3 = the GIS shapefile (4,700 polygons in 161 map quads).

Each polygon has a BEDROCK unit (e.g. "Delta thinly layered") and sometimes a
SURFACE cover (sand ripples, talus...). We use the BEDROCK unit, because that is
what a geologist samples.

Outputs:
  web/data/geology.geojson - one simplified shape per bedrock unit (for drawing)
  web/data/units.bin       - which unit each 40 m grid cell is in (1 byte per cell,
                             0 = not mapped by Stack et al.)
  web/data/units.json      - the list of unit names (id -> name) and the source
"""

import json

import numpy as np
import shapely
from affine import Affine
from pyogrio.raw import read           # reads ESRI shapefiles (uses GDAL)
from rasterio.features import rasterize
from shapely import from_wkb
from shapely.geometry import mapping
from shapely.ops import unary_union

SHP = "data/raw/stack2020/shp/M2020_JEZ_geology_edited_equi0_allquads_v6_archive"
R = 3396190.0                          # Mars sphere radius of this map projection (m)


def metres_to_degrees(xy):
    """Equidistant cylindrical, centre 0: lon = x / R, lat = y / R (in radians).
    Rounded to 5 decimals (about 0.6 m on Mars) to keep the file small."""
    return np.round(np.degrees(xy / R), 5)


def main():
    grid = json.load(open("web/data/grid.json"))
    # pyogrio reads the shapefile with GDAL. 5 of the 4,700 shapes are empty;
    # GDAL gives those back as None and we skip them.
    meta, _, geoms, fields = read(SHP + ".shp")
    bedrock = fields[list(meta["fields"]).index("BedrkUName")]

    # 1) Group polygons by bedrock unit name.
    by_unit = {}
    for wkb, name in zip(geoms, bedrock):
        name = (name or "").strip()
        if wkb is None or not name:
            continue
        by_unit.setdefault(name, []).append(from_wkb(wkb).buffer(0))  # buffer(0) fixes tiny self-crossings

    names = sorted(by_unit)                     # stable id order: alphabetical
    unit_ids = {n: i + 1 for i, n in enumerate(names)}   # 0 is kept for "not mapped"

    # 2) Merge each unit's polygons into one shape (still in metres).
    merged = {n: unary_union(polys) for n, polys in by_unit.items()}

    # 3) Burn the units into our 40 m grid (same position as grid.bin).
    b = grid["bounds_m"]
    cell = grid["cell_size_m_projected"]
    to_grid = Affine(cell, 0, b["west"], 0, -cell, b["north"])
    units = rasterize(
        [(merged[n], unit_ids[n]) for n in names],
        out_shape=(grid["rows"], grid["cols"]),
        transform=to_grid, fill=0, dtype="uint8",
    )
    units.tofile("web/data/units.bin")

    # 4) Simplified shapes in degrees, for DRAWING only (the 40 m grid above is
    #    what the app uses for answers). 15 m tolerance = smaller than one cell.
    features = []
    for n in names:
        geom_deg = shapely.transform(merged[n].simplify(15), metres_to_degrees)
        features.append({"type": "Feature",
                         "properties": {"id": unit_ids[n], "unit": n},
                         "geometry": mapping(geom_deg)})
    with open("web/data/geology.geojson", "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f,
                  separators=(",", ":"))

    json.dump({
        "units": {str(unit_ids[n]): n for n in names},
        "unmapped_id": 0,
        "mapped_cells_percent": round(float((units > 0).mean() * 100), 1),
        "source": {
            "name": "Photogeologic map of the Perseverance rover field site (bedrock units)",
            "citation": "Stack et al. 2020, Space Science Reviews 216:127, "
                        "doi:10.1007/s11214-020-00739-x, CC BY 4.0",
            "mission": "Mars 2020 Science Team, mapped on MRO HiRISE images",
            "url": "https://doi.org/10.1007/s11214-020-00739-x",
        },
    }, open("web/data/units.json", "w"), indent=2)

    print(f"{len(names)} bedrock units; {(units > 0).mean() * 100:.1f}% of grid cells mapped")
    for n in names:
        print(f"  {unit_ids[n]:2d}  {n}  ({(units == unit_ids[n]).sum()} cells)")


if __name__ == "__main__":
    main()
