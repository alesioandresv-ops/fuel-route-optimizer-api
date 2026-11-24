
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


def test_median_uses_distinct_price_values():
    observations = [
        FuelPriceObservation(
            station_id="105",
            station_name="TA Saginaw",
            address="I-75",
            city="Bridgeport",
            state="MI",
            rack_id="260",
            retail_price=price,
            source_row=2,
        )
        for price in [
            Decimal("3.000"),
            Decimal("3.000"),
            Decimal("4.000"),
            Decimal("10.000"),
        ]
    ]

    assert calculate_median_price(observations) == Decimal("4.000")


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
            source_row=2,
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



def test_load_preserves_original_csv_row_numbers(tmp_path):
    csv_file = create_csv(
        tmp_path,
        "105,TA Saginaw,I-75,Bridgeport,MI,260,3.269\n"
        "105,TA Saginaw,I-75,Bridgeport,MI,260,3.339\n",
    )

    stations = load_fuel_observations(csv_file)

    assert stations["105"][0].source_row == 2
    assert stations["105"][1].source_row == 3


def test_summary_includes_statistics_and_original_observations():
    from trips.services.fuel_data import summarize_station_prices

    observations = [
        FuelPriceObservation(
            station_id="105",
            station_name="TA Saginaw",
            address="I-75",
            city="Bridgeport",
            state="MI",
            rack_id="260",
            retail_price=Decimal(price),
            source_row=row,
        )
        for price, row in [
            ("3.000", 2),
            ("3.000", 3),
            ("4.000", 4),
            ("10.000", 5),
        ]
    ]

    summary = summarize_station_prices(observations)

    assert summary.station_id == "105"
    assert summary.median_price == Decimal("4.000")
    assert summary.observation_count == 4
    assert summary.min_price == Decimal("3.000")
    assert summary.max_price == Decimal("10.000")
    assert summary.currency == "unspecified"
    assert summary.fuel_type == "unspecified"
    assert summary.source_rows == (2, 3, 4, 5)
    assert len(summary.observations) == 4


def test_summary_rejects_observations_from_different_stations():
    from trips.services.fuel_data import summarize_station_prices

    observations = [
        FuelPriceObservation(
            station_id=station_id,
            station_name="Test Station",
            address="I-75",
            city="Test City",
            state="MI",
            rack_id="260",
            retail_price=Decimal("3.500"),
            source_row=row,
        )
        for station_id, row in [("105", 2), ("128", 3)]
    ]

    with pytest.raises(ValueError, match="same station"):
        summarize_station_prices(observations)
