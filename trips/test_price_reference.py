from decimal import Decimal

import pytest

from trips.services.price_reference import (
    PriceReference,
    canonical_route_name,
    is_in_usa,
    load_reference_artifact,
    resolve_price_reference,
    state_for_point,
)


def make_reference(price, basis="csv_state_reference", region="FL"):
    return PriceReference(
        price_per_gallon=Decimal(price),
        basis=basis,
        region=region,
        observation_count=3,
        min_price=Decimal("1.000"),
        max_price=Decimal("5.000"),
        source_rows=(2, 3, 4),
        currency="unspecified",
        fuel_type="unspecified",
        method="median of distinct values",
    )


def test_artifact_is_committed_and_traceable():
    artifact = load_reference_artifact()

    assert artifact["source"] == "fuel-prices-for-be-assessment.csv"
    assert artifact["currency"] == "unspecified"
    assert artifact["fuel_type"] == "unspecified"

    florida = artifact["states"]["FL"]
    assert len(florida["prices"]) == 220
    assert len(florida["source_rows"]) == 220
    assert min(florida["source_rows"]) >= 2
    assert all(Decimal(value) > 0 for value in florida["prices"])


def test_state_reference_is_real_and_has_source_rows():
    reference = resolve_price_reference(
        origin=(-80.1918, 25.7617),
        destination=(-81.3792, 28.5383),
        route_names=(),
    )

    assert reference is not None
    assert reference.basis == "csv_state_reference"
    assert reference.region == "FL"
    assert reference.price_per_gallon > 0
    assert reference.observation_count == 220
    assert reference.source_rows
    assert reference.currency == "unspecified"
    assert reference.fuel_type == "unspecified"
    assert reference.as_dict()["station_specific"] is False


def test_route_reference_wins_over_state_reference():
    reference = resolve_price_reference(
        origin=(-80.1918, 25.7617),
        destination=(-81.3792, 28.5383),
        route_names=("I-95", "I-4"),
    )

    assert reference is not None
    assert reference.basis == "csv_route_reference"
    assert "I 95" in reference.region
    assert "I 4" in reference.region
    assert reference.observation_count > 0


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Interstate 95", "I 95"),
        ("I-4", "I 4"),
        ("US-441", "US 441"),
        ("State Road 7", "SR 7"),
        ("County Road 1", "CR 1"),
        ("Florida Turnpike", None),
    ],
)
def test_canonical_route_name(raw, expected):
    assert canonical_route_name(raw) == expected


@pytest.mark.parametrize(
    "longitude,latitude,state",
    [
        (-80.1918, 25.7617, "FL"),
        (-118.2437, 34.0522, "CA"),
        (-73.7562, 42.6526, "NY"),
    ],
)
def test_us_points_are_recognized(longitude, latitude, state):
    assert state_for_point(longitude, latitude) == state
    assert is_in_usa(longitude, latitude) is True


@pytest.mark.parametrize(
    "longitude,latitude",
    [
        (2.3522, 48.8566),
        (-99.1332, 19.4326),
        (0.0, 0.0),
    ],
)
def test_non_us_points_are_rejected(longitude, latitude):
    assert is_in_usa(longitude, latitude) is False
