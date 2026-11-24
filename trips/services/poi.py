import math
import httpx
from django.conf import settings


class POIServiceError(Exception):
    """Raised when the POI provider cannot retrieve fuel stations."""


def get_fuel_stations(
    route_coordinates: list[list[float]],
    buffer_meters: int = 1000,
    limit: int = 2000,
) -> list[dict]:
    """
    Retrieve fuel stations near a route using HeiGIT OpenPOIService.

    Coordinates must use [longitude, latitude] order.
    """

    if not settings.HEIGIT_API_KEY:
        raise POIServiceError("HeiGIT API key is not configured.")

    if not isinstance(route_coordinates, list) or len(route_coordinates) < 2:
        raise ValueError("A route must contain at least two coordinates.")

    if (
        isinstance(buffer_meters, bool)
        or not isinstance(buffer_meters, int)
        or not 1 <= buffer_meters <= 2000
    ):
        raise ValueError("Buffer must be an integer between 1 and 2000 meters.")

    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or limit < 1
    ):
        raise ValueError("Limit must be a positive integer.")

    for coordinate in route_coordinates:
        if not isinstance(coordinate, (list, tuple)) or len(coordinate) != 2:
            raise ValueError(
                "Each coordinate must contain longitude and latitude."
            )

        longitude, latitude = coordinate

        if (
            isinstance(longitude, bool)
            or isinstance(latitude, bool)
            or not isinstance(longitude, (int, float))
            or not isinstance(latitude, (int, float))
            or not math.isfinite(longitude)
            or not math.isfinite(latitude)
            or not -180 <= longitude <= 180
            or not -90 <= latitude <= 90
        ):
            raise ValueError("Invalid coordinate values.")

    url = (
        f"{settings.HEIGIT_BASE_URL.rstrip('/')}"
        "/openpoiservice/v0/pois"
    )

    headers = {
        "Authorization": settings.HEIGIT_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "request": "pois",
        "geometry": {
            "geojson": {
                "type": "LineString",
                "coordinates": route_coordinates,
            },
            "buffer": buffer_meters,
        },
        "limit": limit,
        "filters": {
            "category_ids": [596],
        },
    }

    try:
        response = httpx.post(
            url,
            headers=headers,
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()

    except httpx.HTTPStatusError as error:
        raise POIServiceError(
            f"HeiGIT POI returned HTTP {error.response.status_code}."
        ) from error

    except httpx.TimeoutException as error:
        raise POIServiceError(
            "HeiGIT POI request timed out."
        ) from error

    except httpx.RequestError as error:
        raise POIServiceError(
            "Could not connect to HeiGIT POI."
        ) from error

    try:
        data = response.json()
        features = data["features"]

        if not isinstance(features, list):
            raise ValueError("Invalid features collection.")

    except (ValueError, KeyError, TypeError) as error:
        raise POIServiceError(
            "HeiGIT POI returned an invalid response."
        ) from error

    return features
