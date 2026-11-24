
from decimal import Decimal

import pytest

from trips.services.fuel_data import (
    FuelPriceObservation,
    calculate_median_price,
    load_fuel_observations,
)


HEADERS = (
    "OPIS Truckstop ID,Truckstop Name,Address,City,"
    "State,Rack ID,Retail Price\n"
)


def create_csv(tmp_path, content):
    csv_file = tmp_path / "fuel_test.csv"
    csv_file.write_text(
        HEADERS + content,
        encoding="utf-8",
    )
    return csv_file


def test_load_groups_observations_by_station(tmp_path):
    csv_file = create_csv(
        tmp_path,
        "105,TA Saginaw,I-75,Bridgeport,MI,260,3.269\n"
        "105,TA Saginaw,I-75,Bridgeport,MI,260,3.339\n"
        "128,Effingham Shop,I-57,Effingham,IL,510,3.399\n",
    )

    stations = load_fuel_observations(csv_file)

    assert len(stations) == 2
    assert len(stations["105"]) == 2
    assert len(stations["128"]) == 1
    assert stations["105"][0].retail_price == Decimal("3.269")


def test_load_preserves_duplicate_observations(tmp_path):
    row = "105,TA Saginaw,I-75,Bridgeport,MI,260,3.269\n"
    csv_file = create_csv(tmp_path, row + row)

    stations = load_fuel_observations(csv_file)

    assert len(stations["105"]) == 2


def test_median_uses_all_observations():
    observations = [
        FuelPriceObservation(
            station_id="105",
            station_name="TA Saginaw",
            address="I-75",
            city="Bridgeport",
            state="MI",
            rack_id="260",
            retail_price=price,
        )
        for price in [
            Decimal("3.000"),
            Decimal("3.000"),
            Decimal("4.000"),
            Decimal("10.000"),
        ]
    ]

    assert calculate_median_price(observations) == Decimal("3.500")


def test_median_with_odd_number_of_observations():
    observations = [
        FuelPriceObservation(
            station_id="105",
            station_name="TA Saginaw",
            address="I-75",
            city="Bridgeport",
            state="MI",
            rack_id="260",
            retail_price=price,
        )
        for price in [
            Decimal("3.000"),
            Decimal("3.500"),
            Decimal("4.000"),
        ]
    ]

    assert calculate_median_price(observations) == Decimal("3.500")


def test_median_rejects_empty_observations():
    with pytest.raises(ValueError):
        calculate_median_price([])


def test_load_rejects_invalid_price(tmp_path):
    csv_file = create_csv(
        tmp_path,
        "105,TA Saginaw,I-75,Bridgeport,MI,260,invalid\n",
    )

    with pytest.raises(ValueError, match="Invalid data"):
        load_fuel_observations(csv_file)


def test_load_rejects_non_positive_price(tmp_path):
    csv_file = create_csv(
        tmp_path,
        "105,TA Saginaw,I-75,Bridgeport,MI,260,0\n",
    )

    with pytest.raises(ValueError, match="greater than zero"):
        load_fuel_observations(csv_file)


def test_load_rejects_missing_column(tmp_path):
    csv_file = tmp_path / "invalid.csv"
    csv_file.write_text(
        "OPIS Truckstop ID,Truckstop Name,Retail Price\n"
        "105,TA Saginaw,3.269\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Missing CSV columns"):
        load_fuel_observations(csv_file)
