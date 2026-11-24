
import csv
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

with (DATA_DIR / "miami_orlando_stations_enriched.json").open(
    encoding="utf-8"
) as file:
    stations = json.load(file)

with (DATA_DIR / "fuel-prices-for-be-assessment.csv").open(
    encoding="utf-8-sig",
    newline="",
) as file:
    rows = list(csv.DictReader(file))

# Localidades de Florida identificadas en OSM
osm_cities = {
    tags.get("addr:city", "").strip().casefold()
    for station in stations
    if (tags := station["properties"].get("osm_tags_full", {}))
    and tags.get("addr:state", "").strip().upper() == "FL"
    and tags.get("addr:city")
}

# Registros del CSV correspondientes a Florida
florida_rows = [
    row for row in rows
    if row["State"].strip().upper() == "FL"
]

# Coincidencias de localidad y estado
city_matches = [
    row for row in florida_rows
    if row["City"].strip().casefold() in osm_cities
]

print("=== RESUMEN ===")
print("Estaciones OSM de Florida:", sum(
    1 for station in stations
    if station["properties"].get("osm_tags_full", {}).get(
        "addr:state", ""
    ).upper() == "FL"
))
print("Localidades OSM:", sorted(osm_cities))
print("Registros CSV de Florida:", len(florida_rows))
print("Registros en localidades compartidas:", len(city_matches))

print("\n=== REGISTROS CSV EN LOCALIDADES COMPARTIDAS ===")

for row in city_matches:
    print({
        "id": row["OPIS Truckstop ID"],
        "name": row["Truckstop Name"],
        "address": row["Address"],
        "city": row["City"],
        "state": row["State"],
        "price": row["Retail Price"],
    })

print("\n=== ESTACIONES OSM DE FLORIDA ===")

for station in stations:
    properties = station["properties"]
    tags = properties.get("osm_tags_full", {})

    if tags.get("addr:state", "").upper() == "FL":
        print({
            "osm_id": properties.get("osm_id"),
            "name": tags.get("name"),
            "brand": tags.get("brand"),
            "city": tags.get("addr:city"),
            "address": (
                f'{tags.get("addr:housenumber", "")} '
                f'{tags.get("addr:street", "")}'
            ).strip(),
        })
