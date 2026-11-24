import pytest

from trips.services.optimizer import locate_station_on_route
from trips.services.station_normalizer import GeographicStation
from trips.services.optimizer import optimize_route

from trips.services.optimizer import (
    OptimizationError,
    VehicleConfig,
)


def make_station(
    longitude: float,
    latitude: float = 0.0,
    osm_id: int = 1,
) -> GeographicStation:
    return GeographicStation(
        osm_id=osm_id,
        osm_type=1,
        longitude=longitude,
        latitude=latitude,
        distance_to_route_m=0.0,
        name=f"Station {osm_id}",
        brand=None,
        street=None,
        house_number=None,
        city=None,
        state=None,
        postcode=None,
        osm_tags={},
    )

def test_default_vehicle_starts_with_full_tank():
    vehicle = VehicleConfig()

    assert vehicle.capacity_gallons == 50
    assert vehicle.starting_fuel_gallons == 50


def test_vehicle_accepts_partial_initial_fuel():
    vehicle = VehicleConfig(initial_fuel_gallons=25)

    assert vehicle.starting_fuel_gallons == 25


def test_vehicle_accepts_zero_initial_fuel():
    vehicle = VehicleConfig(initial_fuel_gallons=0)

    assert vehicle.starting_fuel_gallons == 0


def test_vehicle_rejects_fuel_above_capacity():
    with pytest.raises(OptimizationError):
        VehicleConfig(initial_fuel_gallons=51)


def test_vehicle_rejects_negative_initial_fuel():
    with pytest.raises(OptimizationError):
        VehicleConfig(initial_fuel_gallons=-1)


def test_vehicle_rejects_invalid_mpg():
    with pytest.raises(OptimizationError):
        VehicleConfig(mpg=0)


def test_vehicle_rejects_invalid_range():
    with pytest.raises(OptimizationError):
        VehicleConfig(max_range_miles=-100)



def test_station_on_route_has_zero_lateral_distance():
    route = [
        [-80.0, 25.0],
        [-79.0, 25.0],
    ]

    position = locate_station_on_route(
        route,
        longitude=-79.5,
        latitude=25.0,
    )

    assert position.lateral_distance_m == pytest.approx(0, abs=0.01)
    assert position.progress_miles > 0
    assert position.segment_index == 0


def test_station_progress_is_halfway_on_route():
    route = [
        [-80.0, 25.0],
        [-79.0, 25.0],
    ]

    position = locate_station_on_route(
        route,
        longitude=-79.5,
        latitude=25.0,
    )

    assert position.progress_miles == pytest.approx(
        31.3,
        abs=0.2,
    )


def test_station_is_projected_to_nearest_segment():
    route = [
        [-80.0, 25.0],
        [-79.5, 25.0],
        [-79.0, 26.0],
    ]

    position = locate_station_on_route(
        route,
        longitude=-79.75,
        latitude=25.01,
    )

    assert position.segment_index == 0
    assert position.lateral_distance_m < 1200


def test_route_rejects_less_than_two_coordinates():
    with pytest.raises(OptimizationError):
        locate_station_on_route(
            [[-80.0, 25.0]],
            -80.0,
            25.0,
        )


def test_route_rejects_invalid_coordinates():
    with pytest.raises(OptimizationError):
        locate_station_on_route(
            [[-80.0, 25.0], [200.0, 26.0]],
            -80.0,
            25.0,
        )


def test_route_rejects_zero_length_geometry():
    with pytest.raises(OptimizationError):
        locate_station_on_route(
            [[-80.0, 25.0], [-80.0, 25.0]],
            -80.0,
            25.0,
        )



def test_route_within_range_requires_no_stops():
    route = [
        [-80.0, 25.0],
        [-79.0, 25.0],
    ]

    result = optimize_route(
        route_coordinates=route,
        stations=[],
        vehicle=VehicleConfig(),
    )

    assert result.feasible is True
    assert result.stops == ()
    assert result.route_distance_miles > 0
    assert result.remaining_fuel_gallons > 0


def test_route_requires_one_refueling_stop():
    route = [
        [0.0, 0.0],
        [10.0, 0.0],
    ]

    stations = [
        make_station(
            longitude=5.0,
            osm_id=100,
        ),
    ]

    result = optimize_route(
        route_coordinates=route,
        stations=stations,
        vehicle=VehicleConfig(),
    )

    assert result.feasible is True
    assert len(result.stops) == 1
    assert result.stops[0].station.osm_id == 100
    assert result.stops[0].fuel_at_arrival_gallons > 0
    assert result.stops[0].fuel_after_refuel_gallons == pytest.approx(50)



def test_route_rejects_invalid_intermediate_coordinate():
    route = [
        [-80.0, 25.0],
        [200.0, 26.0],
        [-79.0, 27.0],
    ]

    with pytest.raises(OptimizationError):
        locate_station_on_route(
            route,
            -80.0,
            25.0,
        )


def test_route_is_infeasible_when_no_station_can_be_reached():
    route = [
        [0.0, 0.0],
        [20.0, 0.0],
    ]

    result = optimize_route(
        route_coordinates=route,
        stations=[],
        vehicle=VehicleConfig(),
    )

    assert result.feasible is False
    assert result.stops == ()
    assert result.remaining_fuel_gallons is None
    assert "no_feasible_refueling_plan" in result.warnings



def test_optimizer_ignores_stations_outside_route_corridor():
    route = [
        [0.0, 0.0],
        [10.0, 0.0],
    ]

    stations = [
        make_station(
            longitude=5.0,
            latitude=2.0,
            osm_id=200,
        ),
    ]

    result = optimize_route(
        route_coordinates=route,
        stations=stations,
        vehicle=VehicleConfig(),
        max_lateral_distance_m=1000.0,
    )

    assert result.feasible is False
    assert result.stops == ()
    assert "no_feasible_refueling_plan" in result.warnings




def test_optimizer_respects_partial_initial_fuel():
    route = [
        [0.0, 0.0],
        [5.0, 0.0],
    ]

    stations = [
        make_station(
            longitude=2.0,
            latitude=0.0,
            osm_id=300,
        ),
    ]

    vehicle = VehicleConfig(
        initial_fuel_gallons=20.0,
    )

    result = optimize_route(
        route_coordinates=route,
        stations=stations,
        vehicle=vehicle,
    )

    assert result.feasible is True
    assert len(result.stops) == 1

    stop = result.stops[0]

    assert stop.fuel_at_arrival_gallons == pytest.approx(
        20.0 - (result.stops[0].position.progress_miles / 10.0),
        abs=0.01,
    )

    assert stop.fuel_after_refuel_gallons == pytest.approx(50.0)



def test_optimizer_plans_multiple_refueling_stops():
    route = [
        [0.0, 0.0],
        [20.0, 0.0],
    ]

    stations = [
        make_station(longitude=5.0, latitude=0.0, osm_id=401),
        make_station(longitude=10.0, latitude=0.0, osm_id=402),
        make_station(longitude=15.0, latitude=0.0, osm_id=403),
    ]

    result = optimize_route(
        route_coordinates=route,
        stations=stations,
        vehicle=VehicleConfig(),
    )

    assert result.feasible is True
    assert len(result.stops) == 3

    assert [
        stop.station.osm_id for stop in result.stops
    ] == [401, 402, 403]

    for stop in result.stops:
        assert stop.fuel_at_arrival_gallons > 0
        assert stop.fuel_after_refuel_gallons == pytest.approx(50.0)

    assert result.remaining_fuel_gallons > 0



def test_optimizer_rejects_malformed_route_coordinate():
    with pytest.raises(OptimizationError):
        optimize_route(
            route_coordinates=[[]],
            stations=[],
            vehicle=VehicleConfig(),
        )

def test_optimizer_minimizes_number_of_stops():
    route = [
        [0.0, 0.0],
        [20.0, 0.0],
    ]

    stations = [
        make_station(longitude=4.0, osm_id=501),
        make_station(longitude=7.0, osm_id=502),
        make_station(longitude=14.0, osm_id=503),
        make_station(longitude=16.0, osm_id=504),
    ]

    result = optimize_route(
        route_coordinates=route,
        stations=stations,
        vehicle=VehicleConfig(),
    )

    assert result.feasible is True
    assert len(result.stops) == 2
    assert [
        stop.station.osm_id for stop in result.stops
    ] == [502, 503]


def test_optimizer_minimizes_detour_when_stop_count_is_equal():
    route = [
        [0.0, 0.0],
        [16.0, 0.0],
    ]

    stations = [
        make_station(
            longitude=5.0,
            latitude=0.004,
            osm_id=601,
        ),
        make_station(
            longitude=6.0,
            osm_id=0 + 602,
        ),
        make_station(
            longitude=11.0,
            osm_id=603,
        ),
        make_station(
            longitude=12.0,
            latitude=0.004,
            osm_id=604,
        ),
    ]

    result = optimize_route(
        route_coordinates=route,
        stations=stations,
        vehicle=VehicleConfig(),
    )

    assert result.feasible is True
    assert len(result.stops) == 2

    selected_ids = [
        stop.station.osm_id for stop in result.stops
    ]

    assert selected_ids == [602, 603]

    assert result.estimated_total_distance_miles == pytest.approx(
        result.route_distance_miles,
        abs=0.01,
    )


@pytest.mark.parametrize(
    "longitude, latitude",
    [
        (200.0, 0.0),
        (0.0, 95.0),
        (float("nan"), 0.0),
        (True, 0.0),
    ],
)
def test_optimizer_rejects_invalid_station_coordinates(
    longitude,
    latitude,
):
    route = [
        [0.0, 0.0],
        [20.0, 0.0],
    ]

    stations = [
        make_station(
            longitude=longitude,
            latitude=latitude,
            osm_id=701,
        ),
    ]

    with pytest.raises(OptimizationError):
        optimize_route(
            route_coordinates=route,
            stations=stations,
            vehicle=VehicleConfig(),
        )