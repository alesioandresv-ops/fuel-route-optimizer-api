
import httpx
import pytest

from trips.services.routing import (
    RoutingServiceError,
    get_route,
)


@pytest.fixture
def valid_route_response():
    return {
        "features": [
            {
                "properties": {
                    "summary": {
                        "distance": 379151.0,
                        "duration": 14375.0,
                    }
                },
                "geometry": {
                    "coordinates": [
                        [-80.1918, 25.7617],
                        [-81.3792, 28.5383],
                    ]
                },
            }
        ]
    }


def test_get_route_success(monkeypatch, valid_route_response):
    monkeypatch.setattr(
        "trips.services.routing.settings.HEIGIT_API_KEY",
        "test-api-key",
    )

    def mock_post(*args, **kwargs):
        return httpx.Response(
            200,
            json=valid_route_response,
            request=httpx.Request("POST", "https://test.example"),
        )

    monkeypatch.setattr(
        "trips.services.routing.httpx.post",
        mock_post,
    )

    route = get_route(
        origin=(-80.1918, 25.7617),
        destination=(-81.3792, 28.5383),
    )

    assert route.distance_meters == 379151.0
    assert route.duration_seconds == 14375.0
    assert len(route.coordinates) == 2


def test_get_route_rejects_invalid_coordinates():
    with pytest.raises(ValueError):
        get_route(
            origin=(-200, 25.7617),
            destination=(-81.3792, 28.5383),
        )


def test_get_route_requires_api_key(monkeypatch):
    monkeypatch.setattr(
        "trips.services.routing.settings.HEIGIT_API_KEY",
        "",
    )

    with pytest.raises(RoutingServiceError):
        get_route(
            origin=(-80.1918, 25.7617),
            destination=(-81.3792, 28.5383),
        )


def test_get_route_handles_http_error(monkeypatch):
    monkeypatch.setattr(
        "trips.services.routing.settings.HEIGIT_API_KEY",
        "test-api-key",
    )

    def mock_post(*args, **kwargs):
        return httpx.Response(
            429,
            request=httpx.Request("POST", "https://test.example"),
        )

    monkeypatch.setattr(
        "trips.services.routing.httpx.post",
        mock_post,
    )

    with pytest.raises(RoutingServiceError, match="HTTP 429"):
        get_route(
            origin=(-80.1918, 25.7617),
            destination=(-81.3792, 28.5383),
        )


def test_get_route_handles_timeout(monkeypatch):
    monkeypatch.setattr(
        "trips.services.routing.settings.HEIGIT_API_KEY",
        "test-api-key",
    )

    def mock_post(*args, **kwargs):
        raise httpx.TimeoutException(
            "Request timed out",
            request=httpx.Request("POST", "https://test.example"),
        )

    monkeypatch.setattr(
        "trips.services.routing.httpx.post",
        mock_post,
    )

    with pytest.raises(RoutingServiceError, match="timed out"):
        get_route(
            origin=(-80.1918, 25.7617),
            destination=(-81.3792, 28.5383),
        )
