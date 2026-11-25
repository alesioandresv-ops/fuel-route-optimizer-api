from unittest.mock import patch

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from trips.services.optimizer import OptimizationError
from trips.services.poi import POIServiceError
from trips.services.routing import RouteResult, RoutingServiceError


@pytest.fixture(autouse=True)
def clear_external_cache():
    cache.clear()
    yield
    cache.clear()


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
        == "provider_distance_plus_twice_lateral_offset"
    )
    assert distance_estimation["detours_are_road_distances"] is False
    assert "Actual road detours are not calculated." in (
        distance_estimation["description"]
    )

    assert data["geographic_stations"] == []
    assert data["priced_stations"] == []

    assert data["fuel_cost"]["total"] > 0
    assert data["fuel_cost"]["available"] is True
    assert data["fuel_cost"]["price_basis"] == "csv_state_reference"
    assert data["fuel_cost"]["source_rows"]
    assert data["fuel_cost"]["method"] == (
        "route_distance_miles / mpg * csv_reference_price_per_gallon"
    )
    assert data["fuel_cost"]["currency"] == "unspecified"
    assert data["fuel_cost"]["fuel_type"] == "unspecified"

    assert data["data_quality"]["prices_available"] is False
    assert data["data_quality"]["csv_rows_evaluated"] == 220
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


def test_cache_hits_are_measured_and_providers_called_once(
    client, valid_payload, mock_route
):
    with (
        patch(
            "trips.views.get_route", return_value=mock_route
        ) as routing_mock,
        patch(
            "trips.views.get_fuel_stations", return_value=[]
        ) as poi_mock,
    ):
        first = client.post(
            "/api/v1/trips/optimize/",
            valid_payload,
            format="json",
        )
        second = client.post(
            "/api/v1/trips/optimize/",
            valid_payload,
            format="json",
        )

    assert first.data["external_calls"] == {
        "routing": 1,
        "poi": 1,
        "total": 2,
    }
    assert second.data["external_calls"] == {
        "routing": 0,
        "poi": 0,
        "total": 0,
    }
    assert first.data["cache"]["used"] is False
    assert second.data["cache"]["used"] is True
    assert routing_mock.call_count == 1
    assert poi_mock.call_count == 1


def test_route_reference_and_compact_osm_tags_are_used(
    client, valid_payload, mock_route
):
    mock_route_with_steps = RouteResult(
        distance_meters=379151,
        duration_seconds=14375,
        coordinates=mock_route.coordinates,
        road_names=("I-95",),
    )
    compact_feature = {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [-80.7855, 27.15],
        },
        "properties": {
            "osm_id": 123,
            "osm_type": 1,
            "distance": 0.0,
            "osm_tags": {
                "name": "Test Fuel",
                "brand": "Shell",
                "addr:street": "I-95",
            },
        },
    }

    with (
        patch(
            "trips.views.get_route",
            return_value=mock_route_with_steps,
        ),
        patch(
            "trips.views.get_fuel_stations",
            return_value=[compact_feature],
        ),
    ):
        response = client.post(
            "/api/v1/trips/optimize/",
            valid_payload,
            format="json",
        )

    assert response.status_code == 200
    data = response.data

    assert data["geographic_stations"][0]["name"] == "Test Fuel"
    assert data["geographic_stations"][0]["brand"] == "Shell"
    assert data["priced_stations"][0]["price_status"] == "csv_reference"
    assert data["fuel_cost"]["price_basis"] == "csv_route_reference"
    assert data["fuel_cost"]["source_rows"]
    assert data["fuel_cost"]["total"] > 0
    assert "reference_price_not_station_quote" in (
        data["data_quality"]["warnings"]
    )


def test_non_us_coordinates_are_rejected(client):
    payload = {
        "origin": {"longitude": 2.3522, "latitude": 48.8566},
        "destination": {"longitude": -81.3792, "latitude": 28.5383},
    }

    with (
        patch("trips.views.get_route") as routing_mock,
        patch("trips.views.get_fuel_stations") as poi_mock,
    ):
        response = client.post(
            "/api/v1/trips/optimize/",
            payload,
            format="json",
        )

    assert response.status_code == 400
    assert "origin" in response.data
    routing_mock.assert_not_called()
    poi_mock.assert_not_called()


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
