from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from trips.services.optimizer import OptimizationError
from trips.services.poi import POIServiceError
from trips.services.routing import RouteResult, RoutingServiceError


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def valid_payload():
    return {
        "origin": {
            "longitude": -80.1918,
            "latitude": 25.7617,
        },
        "destination": {
            "longitude": -81.3792,
            "latitude": 28.5383,
        },
    }


@pytest.fixture
def mock_route():
    return RouteResult(
        distance_meters=379151,
        duration_seconds=14375,
        coordinates=[
            [-80.1918, 25.7617],
            [-81.3792, 28.5383],
        ],
    )


def test_optimize_route_success_without_verified_prices(
    client, valid_payload, mock_route
):
    with (
        patch("trips.views.get_route", return_value=mock_route) as routing_mock,
        patch("trips.views.get_fuel_stations", return_value=[]) as poi_mock,
    ):
        response = client.post(
            "/api/v1/trips/optimize/",
            valid_payload,
            format="json",
        )

    assert response.status_code == 200

    data = response.data

    assert data["route"]["distance_meters"] == 379151
    assert data["route"]["geometry"]["type"] == "LineString"

    assert data["optimization"]["feasible"] is True
    assert data["optimization"]["stops"] == []

    # Vehicle assumptions must be explicit.
    assert data["vehicle"]["calculated_tank_capacity_gallons"] == 50
    assert data["vehicle"]["capacity_is_assumed"] is True
    assert (
        data["vehicle"]["capacity_calculation"]
        == "max_range_miles / mpg"
    )

    # Distance estimation must disclose its geometric approximation.
    distance_estimation = data["optimization"]["distance_estimation"]

    assert distance_estimation["base_distance_miles"] > 0
    assert (
        distance_estimation["method"]
        == "route_geometry_plus_twice_lateral_offset"
    )
    assert distance_estimation["detours_are_road_distances"] is False
    assert "Actual road detours are not calculated." in (
        distance_estimation["description"]
    )

    assert data["geographic_stations"] == []
    assert data["priced_stations"] == []

    assert data["fuel_cost"]["total"] is None
    assert data["fuel_cost"]["available"] is False
    assert data["fuel_cost"]["currency"] == "unspecified"
    assert data["fuel_cost"]["fuel_type"] == "unspecified"

    assert data["data_quality"]["prices_available"] is False
    assert "no_verified_price_matches" in data["data_quality"]["warnings"]
    assert "geometric_detour_estimate" in data["data_quality"]["warnings"]
    assert "calculated_capacity_is_assumption" in data["data_quality"]["warnings"]

    assert data["external_calls"] == {
        "routing": 1,
        "poi": 1,
        "total": 2,
    }

    routing_mock.assert_called_once_with(
        origin=(-80.1918, 25.7617),
        destination=(-81.3792, 28.5383),
    )

    poi_mock.assert_called_once_with(mock_route.coordinates)


def test_invalid_request_returns_400_without_external_calls(
    client, valid_payload
):
    valid_payload["origin"]["longitude"] = 250

    with (
        patch("trips.views.get_route") as routing_mock,
        patch("trips.views.get_fuel_stations") as poi_mock,
    ):
        response = client.post(
            "/api/v1/trips/optimize/",
            valid_payload,
            format="json",
        )

    assert response.status_code == 400
    assert "origin" in response.data

    routing_mock.assert_not_called()
    poi_mock.assert_not_called()


def test_routing_provider_error_returns_502(
    client, valid_payload
):
    with (
        patch(
            "trips.views.get_route",
            side_effect=RoutingServiceError("Routing provider unavailable"),
        ),
        patch("trips.views.get_fuel_stations") as poi_mock,
    ):
        response = client.post(
            "/api/v1/trips/optimize/",
            valid_payload,
            format="json",
        )

    assert response.status_code == 502
    assert response.data["error"] == "external_provider_error"

    poi_mock.assert_not_called()


def test_poi_provider_error_returns_502(
    client, valid_payload, mock_route
):
    with (
        patch("trips.views.get_route", return_value=mock_route),
        patch(
            "trips.views.get_fuel_stations",
            side_effect=POIServiceError("POI provider unavailable"),
        ),
    ):
        response = client.post(
            "/api/v1/trips/optimize/",
            valid_payload,
            format="json",
        )

    assert response.status_code == 502
    assert response.data["error"] == "external_provider_error"


def test_invalid_station_provider_data_returns_502(
    client, valid_payload, mock_route
):
    invalid_features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": ["invalid", 25.0],
            },
            "properties": {},
        }
    ]

    with (
        patch("trips.views.get_route", return_value=mock_route),
        patch(
            "trips.views.get_fuel_stations",
            return_value=invalid_features,
        ),
    ):
        response = client.post(
            "/api/v1/trips/optimize/",
            valid_payload,
            format="json",
        )

    assert response.status_code == 502
    assert response.data["error"] == "invalid_provider_data"


def test_optimizer_error_returns_502(
    client, valid_payload, mock_route
):
    with (
        patch("trips.views.get_route", return_value=mock_route),
        patch("trips.views.get_fuel_stations", return_value=[]),
        patch(
            "trips.views.optimize_route",
            side_effect=OptimizationError("Optimization failed"),
        ),
    ):
        response = client.post(
            "/api/v1/trips/optimize/",
            valid_payload,
            format="json",
        )

    assert response.status_code == 502
    assert response.data["error"] == "optimization_failed"
