
import httpx
import pytest

from trips.services.poi import (
    POIServiceError,
    get_fuel_stations,
)


@pytest.fixture
def valid_poi_response():
    return {
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": "Example Fuel Station",
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [-80.5, 26.0],
                },
            }
        ]
    }


@pytest.fixture
def route_coordinates():
    return [
        [-80.1918, 25.7617],
        [-81.3792, 28.5383],
    ]


def test_get_fuel_stations_success(
    monkeypatch,
    valid_poi_response,
    route_coordinates,
):
    monkeypatch.setattr(
        "trips.services.poi.settings.HEIGIT_API_KEY",
        "test-api-key",
    )

    captured = {}

    def mock_post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs

        return httpx.Response(
            200,
            json=valid_poi_response,
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(
        "trips.services.poi.httpx.post",
        mock_post,
    )

    stations = get_fuel_stations(route_coordinates)

    assert len(stations) == 1
    assert stations[0]["properties"]["name"] == "Example Fuel Station"

    payload = captured["kwargs"]["json"]

    assert payload["request"] == "pois"
    assert payload["filters"]["category_ids"] == [596]
    assert payload["geometry"]["buffer"] == 1000
    assert payload["geometry"]["geojson"]["coordinates"] == route_coordinates


def test_get_fuel_stations_rejects_short_route(
    monkeypatch,
):
    monkeypatch.setattr(
        "trips.services.poi.settings.HEIGIT_API_KEY",
        "test-api-key",
    )

    with pytest.raises(ValueError, match="at least two"):
        get_fuel_stations([[-80.1918, 25.7617]])


def test_get_fuel_stations_rejects_invalid_buffer(
    monkeypatch,
    route_coordinates,
):
    monkeypatch.setattr(
        "trips.services.poi.settings.HEIGIT_API_KEY",
        "test-api-key",
    )

    with pytest.raises(ValueError, match="Buffer"):
        get_fuel_stations(
            route_coordinates,
            buffer_meters=3000,
        )


def test_get_fuel_stations_requires_api_key(
    monkeypatch,
    route_coordinates,
):
    monkeypatch.setattr(
        "trips.services.poi.settings.HEIGIT_API_KEY",
        "",
    )

    with pytest.raises(POIServiceError, match="API key"):
        get_fuel_stations(route_coordinates)


def test_get_fuel_stations_handles_http_error(
    monkeypatch,
    route_coordinates,
):
    monkeypatch.setattr(
        "trips.services.poi.settings.HEIGIT_API_KEY",
        "test-api-key",
    )

    def mock_post(url, **kwargs):
        return httpx.Response(
            429,
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(
        "trips.services.poi.httpx.post",
        mock_post,
    )

    with pytest.raises(POIServiceError, match="HTTP 429"):
        get_fuel_stations(route_coordinates)


def test_get_fuel_stations_handles_timeout(
    monkeypatch,
    route_coordinates,
):
    monkeypatch.setattr(
        "trips.services.poi.settings.HEIGIT_API_KEY",
        "test-api-key",
    )

    def mock_post(url, **kwargs):
        raise httpx.TimeoutException(
            "Request timed out",
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(
        "trips.services.poi.httpx.post",
        mock_post,
    )

    with pytest.raises(POIServiceError, match="timed out"):
        get_fuel_stations(route_coordinates)


def test_get_fuel_stations_handles_invalid_response(
    monkeypatch,
    route_coordinates,
):
    monkeypatch.setattr(
        "trips.services.poi.settings.HEIGIT_API_KEY",
        "test-api-key",
    )

    def mock_post(url, **kwargs):
        return httpx.Response(
            200,
            json={"unexpected": "response"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(
        "trips.services.poi.httpx.post",
        mock_post,
    )

    with pytest.raises(POIServiceError, match="invalid response"):
        get_fuel_stations(route_coordinates)
