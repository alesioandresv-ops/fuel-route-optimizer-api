import csv
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Cargar estaciones enriquecidas
with (DATA_DIR / "miami_orlando_stations_enriched.json").open(
    encoding="utf-8"
) as file:
    stations = json.load(file)

# Cargar CSV original
csv_path = DATA_DIR / "fuel-prices-for-be-assessment.csv"

with csv_path.open(
    encoding="utf-8-sig",
    newline="",
) as file:
    reader = csv.DictReader(file)
    fuel_rows = list(reader)

print("=== RESUMEN ===")
print("Estaciones OSM:", len(stations))
print("Registros CSV:", len(fuel_rows))

# OSM tag coverage
fields = {
    "name": "name",
    "brand": "brand",
    "city": "addr:city",
    "state": "addr:state",
    "street": "addr:street",
    "housenumber": "addr:housenumber",
    "postcode": "addr:postcode",
}

print("\n=== COBERTURA OSM ===")

for label, tag in fields.items():
    count = sum(
        bool(s["properties"].get("osm_tags_full", {}).get(tag))
        for s in stations
    )
    print(f"{label}: {count}/{len(stations)}")

print("\n=== EJEMPLOS OSM ===")

for station in stations[:15]:
    properties = station["properties"]
    tags = properties.get("osm_tags_full", {})

    print({
        "osm_id": properties.get("osm_id"),
        "name": tags.get("name"),
        "brand": tags.get("brand"),
        "address": (
            f'{tags.get("addr:housenumber", "")} '
            f'{tags.get("addr:street", "")}'
        ).strip(),
        "city": tags.get("addr:city"),
        "state": tags.get("addr:state"),
    })

print("\n=== PRIMEROS 10 REGISTROS CSV ===")

for row in fuel_rows[:10]:
    print({
        "id": row["OPIS Truckstop ID"],
        "name": row["Truckstop Name"],
        "address": row["Address"],
        "city": row["City"],
        "state": row["State"],
        "price": row["Retail Price"],
    })
