"""Build a small, traceable price-reference artifact from the supplied CSV.

The original dataset is never modified or committed. This script only derives
aggregate price references and keeps the source row numbers so every value can
be reconstructed from the original file.
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from trips.services.fuel_data import load_fuel_observations  # noqa: E402

CSV_PATH = BASE_DIR / "data" / "fuel-prices-for-be-assessment.csv"
OUTPUT_PATH = (
    BASE_DIR / "trips" / "data" / "price_references.json"
)

ROUTE_PATTERN = re.compile(
    r"\b(I|US|SR|CR|FL)[-\s]?(\d+[A-Z]?)\b",
    re.IGNORECASE,
)


def route_references(address: str) -> set[str]:
    references = {
        f"{match.group(1).upper()} {match.group(2).upper()}"
        for match in ROUTE_PATTERN.finditer(address)
    }
    if "TURNPIKE" in address.upper():
        references.add("FL TURNPIKE")
    return references


def bucket() -> dict:
    return {"prices": [], "source_rows": []}


def add(bucket_data: dict, price, row: int) -> None:
    bucket_data["prices"].append(str(price))
    bucket_data["source_rows"].append(row)


def build() -> dict:
    observations = load_fuel_observations(CSV_PATH)
    states = defaultdict(bucket)
    routes = defaultdict(bucket)
    national = bucket()

    for station_observations in observations.values():
        for observation in station_observations:
            price = observation.retail_price
            row = observation.source_row

            add(national, price, row)

            if observation.state:
                add(states[observation.state.upper()], price, row)

            for reference in route_references(observation.address):
                add(routes[reference], price, row)

    return {
        "source": CSV_PATH.name,
        "generated_by": "scripts/build_price_references.py",
        "method": (
            "Aggregated from original Retail Price observations. "
            "The runtime calculates the median of distinct values and "
            "reports observation count, minimum and maximum."
        ),
        "currency": "unspecified",
        "fuel_type": "unspecified",
        "national": national,
        "states": dict(states),
        # Small/ambiguous route references are not useful price references.
        "routes": {
            key: value
            for key, value in routes.items()
            if len(value["prices"]) >= 10
        },
    }


def main() -> None:
    artifact = build()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("Generated:", OUTPUT_PATH)
    print("States:", len(artifact["states"]))
    print("Routes:", len(artifact["routes"]))
    print("National observations:", len(artifact["national"]["prices"]))


if __name__ == "__main__":
    main()
