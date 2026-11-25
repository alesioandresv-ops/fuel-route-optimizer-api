from decimal import Decimal

from trips.services.optimizer import optimize_route, VehicleConfig
from trips.services.price_reference import PricedStation
from trips.services.station_normalizer import GeographicStation


# Synthetic fixtures: used to prove the optimizer responds to price, not to
# claim that any of these stations or prices exist in the supplied dataset.
ROUTE = [[longitude, 0.0] for longitude in range(0, 21)]

STATION_SPECS = [
    (1, 4.0, "10.000"),
    (2, 5.0, "1.000"),
    (3, 9.0, "3.000"),
    (4, 13.0, "3.000"),
    (5, 17.0, "3.000"),
]


def make_reference(price):
    from trips.services.price_reference import PriceReference

    return PriceReference(
        price_per_gallon=Decimal(price),
        basis="synthetic_test_fixture",
        region="synthetic",
        observation_count=1,
        min_price=Decimal(price),
        max_price=Decimal(price),
        source_rows=(),
        currency="unspecified",
        fuel_type="unspecified",
        method="synthetic test fixture",
    )


def make_station(osm_id, longitude):
    return GeographicStation(
        osm_id=osm_id,
        osm_type=1,
        longitude=longitude,
        latitude=0.0,
        distance_to_route_m=0.0,
        name=f"Synthetic station {osm_id}",
        brand=None,
        street=None,
        house_number=None,
        city=None,
        state=None,
        postcode=None,
        osm_tags={},
    )


def priced_stations(early_osm_id=1):
    """Build a synthetic corridor with one early station and three later ones."""
    specifications = [
        spec for spec in STATION_SPECS if spec[0] in {early_osm_id, 3, 4, 5}
    ]
    return [
        PricedStation(
            make_station(osm_id, longitude),
            make_reference(price),
        )
        for osm_id, longitude, price in specifications
    ]


def test_cost_mode_prefers_cheaper_farther_station():
    result = optimize_route(
        route_coordinates=ROUTE,
        stations=priced_stations(early_osm_id=2),
        vehicle=VehicleConfig(),
    )

    assert result.feasible is True
    assert result.optimized_for_cost is True
    assert result.total_cost is not None
    assert result.stops[0].station.osm_id == 2
    assert sum(
        stop.estimated_cost for stop in result.stops
    ) == result.total_cost
    assert all(stop.price_per_gallon is not None for stop in result.stops)


def test_cost_mode_total_is_lower_than_with_expensive_station_only():
    cheap_plan = optimize_route(
        route_coordinates=ROUTE,
        stations=priced_stations(early_osm_id=2),
        vehicle=VehicleConfig(),
    )

    expensive_plan = optimize_route(
        route_coordinates=ROUTE,
        stations=priced_stations(early_osm_id=1),
        vehicle=VehicleConfig(),
    )

    assert expensive_plan.feasible is True
    assert cheap_plan.total_cost < expensive_plan.total_cost


def test_unpriced_stations_fall_back_to_minimum_stops():
    stations = [make_station(1, 4.0)] + [
        make_station(osm_id, longitude)
        for osm_id, longitude, _ in STATION_SPECS[1:]
    ]

    result = optimize_route(
        route_coordinates=ROUTE,
        stations=stations,
        vehicle=VehicleConfig(),
    )

    assert result.feasible is True
    assert result.optimized_for_cost is False
    assert result.total_cost is None
    assert [stop.station.osm_id for stop in result.stops] == [1, 3, 4]


def test_first_leg_respects_partial_initial_fuel_in_cost_mode():
    stations = priced_stations(early_osm_id=2)

    result = optimize_route(
        route_coordinates=ROUTE,
        stations=stations,
        vehicle=VehicleConfig(initial_fuel_gallons=20),
    )

    # 20 gallons x 10 mpg = 200 miles; the station at 5 degrees is 347 miles
    # away, so no stop is reachable with the initial fuel.
    assert result.feasible is False
    assert result.total_cost is None


def test_provider_distance_is_authoritative():
    result = optimize_route(
        route_coordinates=ROUTE,
        stations=priced_stations(early_osm_id=2),
        vehicle=VehicleConfig(),
        route_distance_miles=900.0,
    )

    assert round(result.route_distance_miles, 2) == 900.0
