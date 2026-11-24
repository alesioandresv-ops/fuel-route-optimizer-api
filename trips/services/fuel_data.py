
import csv
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path


REQUIRED_COLUMNS = {
    "OPIS Truckstop ID",
    "Truckstop Name",
    "Address",
    "City",
    "State",
    "Rack ID",
    "Retail Price",
}


@dataclass(frozen=True)
class FuelPriceObservation:
    station_id: str
    station_name: str
    address: str
    city: str
    state: str
    rack_id: str
    retail_price: Decimal


def load_fuel_observations(
    csv_path: Path,
) -> dict[str, list[FuelPriceObservation]]:
    """Read the original CSV without modifying its contents."""

    stations = defaultdict(list)

    with csv_path.open(
        mode="r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        if not reader.fieldnames:
            raise ValueError("The CSV file has no headers.")

        missing_columns = REQUIRED_COLUMNS - set(reader.fieldnames)

        if missing_columns:
            raise ValueError(
                f"Missing CSV columns: {sorted(missing_columns)}"
            )

        for row_number, row in enumerate(reader, start=2):
            try:
                price = Decimal(row["Retail Price"].strip())

                if price <= 0:
                    raise ValueError("Price must be greater than zero.")

                observation = FuelPriceObservation(
                    station_id=row["OPIS Truckstop ID"].strip(),
                    station_name=row["Truckstop Name"].strip(),
                    address=row["Address"].strip(),
                    city=row["City"].strip(),
                    state=row["State"].strip(),
                    rack_id=row["Rack ID"].strip(),
                    retail_price=price,
                )

                if not observation.station_id:
                    raise ValueError("Station ID cannot be empty.")

                stations[observation.station_id].append(observation)

            except (InvalidOperation, ValueError) as error:
                raise ValueError(
                    f"Invalid data at CSV row {row_number}: {error}"
                ) from error

    return dict(stations)


def calculate_median_price(
    observations: list[FuelPriceObservation],
) -> Decimal:
    """Calculate the median using all original price observations."""

    if not observations:
        raise ValueError("Cannot calculate median without observations.")

    prices = sorted(
        observation.retail_price
        for observation in observations
    )

    middle = len(prices) // 2

    if len(prices) % 2:
        return prices[middle]

    return (prices[middle - 1] + prices[middle]) / Decimal("2")