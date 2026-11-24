
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

with (DATA_DIR / "miami_orlando_stations.json").open(
    encoding="utf-8"
) as file:
    stations = json.load(file)

with (DATA_DIR / "miami_orlando_overpass.json").open(
    encoding="utf-8"
) as file:
    osm_data = json.load(file)

elements = osm_data.get("elements", [])

osm_type_names = {
    1: "node",
    2: "way",
    3: "relation",
}

overpass_index = {
    (element["type"], element["id"]): element
    for element in elements
}

matched = []
unmatched = []

for station in stations:
    properties = station["properties"]

    osm_type = osm_type_names.get(properties.get("osm_type"))
    osm_id = properties.get("osm_id")

    element = overpass_index.get((osm_type, osm_id))

    if element:
        enriched = {
            **station,
            "properties": {
                **properties,
                "osm_tags_full": element.get("tags", {}),
            },
        }
        matched.append(enriched)
    else:
        unmatched.append({
            "osm_type": osm_type,
            "osm_id": osm_id,
            "name": properties.get("osm_tags", {}).get("name"),
        })

output_path = DATA_DIR / "miami_orlando_stations_enriched.json"

with output_path.open("w", encoding="utf-8") as file:
    json.dump(matched, file, ensure_ascii=False, indent=2)

print("Estaciones originales:", len(stations))
print("Objetos Overpass:", len(elements))
print("Coincidencias exactas:", len(matched))
print("Sin coincidencia:", len(unmatched))
print("Archivo generado:", output_path)

print("\nPrimeras coincidencias:")
for station in matched[:5]:
    properties = station["properties"]
    print({
        "osm_id": properties.get("osm_id"),
        "name": properties.get("osm_tags_full", {}).get("name"),
        "brand": properties.get("osm_tags_full", {}).get("brand"),
        "city": properties.get("osm_tags_full", {}).get("addr:city"),
        "state": properties.get("osm_tags_full", {}).get("addr:state"),
    })
