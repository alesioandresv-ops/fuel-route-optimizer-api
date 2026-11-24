
import csv
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = BASE_DIR / "data" / "fuel-prices-for-be-assessment.csv"


def inspect_dataset():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH}")

    rows = []
    station_prices = defaultdict(set)
    state_counts = Counter()
    exact_rows = Counter()
    prices = []
    missing_values = 0

    with CSV_PATH.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        print("COLUMNS:", reader.fieldnames)

        for row in reader:
            rows.append(row)

            exact_key = tuple(row.values())
            exact_rows[exact_key] += 1

            station_id = row["OPIS Truckstop ID"]
            state = row["State"]
            raw_price = row["Retail Price"]

            state_counts[state] += 1

            if not station_id or not raw_price:
                missing_values += 1

            if station_id and raw_price:
                try:
                    price = Decimal(raw_price)
                    station_prices[station_id].add(price)
                    prices.append(price)
                except InvalidOperation:
                    print("Invalid price:", raw_price)

    duplicate_rows = sum(
        count - 1
        for count in exact_rows.values()
        if count > 1
    )

    stations_with_multiple_prices = {
        station_id: values
        for station_id, values in station_prices.items()
        if len(values) > 1
    }

    print("\n--- DATASET SUMMARY ---")
    print("Total records:", len(rows))
    print("Unique station IDs:", len(station_prices))
    print("Distinct states/regions:", len(state_counts))
    print("Exact duplicate rows:", duplicate_rows)
    print("Stations with multiple prices:", len(stations_with_multiple_prices))
    print("Missing required values:", missing_values)

    if prices:
        print("Minimum price:", min(prices))
        print("Maximum price:", max(prices))

    print("\n--- RECORDS BY STATE ---")
    for state, count in state_counts.most_common():
        print(f"{state}: {count}")

    print("\n--- EXAMPLES WITH MULTIPLE PRICES ---")
    for station_id, values in list(stations_with_multiple_prices.items())[:10]:
        print(f"Station {station_id}: {sorted(values)}")


if __name__ == "__main__":
    inspect_dataset()
