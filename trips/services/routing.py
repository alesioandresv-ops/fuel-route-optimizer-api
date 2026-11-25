import math
from dataclasses import dataclass

import httpx
from django.conf import settings


@dataclass(frozen=True)
class RouteResult:
    distance_meters: float
    duration_seconds: float
    coordinates: list[list[float]]
    road_names: tuple[str, ...] = ()


class RoutingServiceError(Exception):
    """Raised when the routing provider cannot calculate a route."""


def get_route(
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> RouteResult:
    """
    Calculate a driving route using HeiGIT.

    Coordinates must use longitude, latitude order.
    """

    if not settings.HEIGIT_API_KEY:
        raise RoutingServiceError("HeiGIT API key is not configured.")

    for name, (longitude, latitude) in (
        ("origin", origin),
        ("destination", destination),
    ):
        if not -180 <= longitude <= 180:
            raise ValueError(f"Invalid longitude for {name}.")

        if not -90 <= latitude <= 90:
            raise ValueError(f"Invalid latitude for {name}.")

    url = (
        f"{settings.HEIGIT_BASE_URL.rstrip('/')}"
        "/openrouteservice/v2/directions/driving-car/geojson"
    )

    headers = {
        "Authorization": settings.HEIGIT_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "coordinates": [
            list(origin),
            list(destination),
        ],
        "instructions": True,
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
        raise RoutingServiceError(
            f"HeiGIT returned HTTP {error.response.status_code}."
        ) from error

    except httpx.TimeoutException as error:
        raise RoutingServiceError(
            "HeiGIT request timed out."
        ) from error

    except httpx.RequestError as error:
        raise RoutingServiceError(
            "Could not connect to HeiGIT."
        ) from error

    try:
        data = response.json()
        feature = data["features"][0]
        summary = feature["properties"]["summary"]
        coordinates = feature["geometry"]["coordinates"]

        distance = float(summary["distance"])
        duration = float(summary["duration"])

        if (
            not math.isfinite(distance)
            or not math.isfinite(duration)
            or distance <= 0
            or duration <= 0
        ):
            raise ValueError("Invalid route metrics.")

        if not isinstance(coordinates, list) or len(coordinates) < 2:
            raise ValueError("Invalid route geometry.")

        for coordinate in coordinates:
            if not isinstance(coordinate, (list, tuple)) or len(coordinate) != 2:
                raise ValueError("Invalid route coordinate.")

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
                raise ValueError("Invalid route coordinate values.")

        raw_segments = feature["properties"].get("segments", [])
        if not isinstance(raw_segments, list):
            raise ValueError("Invalid route segments.")

        road_names = tuple(
            step["name"]
            for segment in raw_segments
            if isinstance(segment, dict)
            for step in segment.get("steps", [])
            if isinstance(step, dict)
            and isinstance(step.get("name"), str)
            and step["name"].strip()
        )

    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise RoutingServiceError(
            "HeiGIT returned an invalid route response."
        ) from error

    return RouteResult(
        distance_meters=distance,
        duration_seconds=duration,
        coordinates=coordinates,
        road_names=road_names,
    )
