from dataclasses import asdict, dataclass
import math
from typing import Any


class StationNormalizationError(ValueError):
    """Raised when a POI feature cannot be normalized safely."""


@dataclass(frozen=True)
class GeographicStation:
    osm_id: int
    osm_type: int
    longitude: float
    latitude: float
    distance_to_route_m: float
    name: str | None
    brand: str | None
    street: str | None
    house_number: str | None
    city: str | None
    state: str | None
    postcode: str | None
    osm_tags: dict[str, Any]

    @property
    def address(self) -> str | None:
        parts = [
            part
            for part in (self.house_number, self.street)
            if part
        ]
        return " ".join(parts) or None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["address"] = self.address
        return result


def _required_number(value: Any, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
    ):
        raise StationNormalizationError(
            f"{field} must be a valid number."
        )

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise StationNormalizationError(
            f"{field} must be a valid number."
        ) from None

    if not math.isfinite(number):
        raise StationNormalizationError(
            f"{field} must be finite."
        )

    return number


def _optional_tag(tags: dict[str, Any], key: str) -> str | None:
    value = tags.get(key)

    if not isinstance(value, str):
        return None

    value = value.strip()
    return value or None


def normalize_station(feature: dict[str, Any]) -> GeographicStation:
    if not isinstance(feature, dict):
        raise StationNormalizationError(
            "Feature must be a dictionary."
        )

    if feature.get("type") != "Feature":
        raise StationNormalizationError(
            "Feature type must be 'Feature'."
        )

    geometry = feature.get("geometry")

    if not isinstance(geometry, dict) or geometry.get("type") != "Point":
        raise StationNormalizationError(
            "Station geometry must be a GeoJSON Point."
        )

    coordinates = geometry.get("coordinates")

    if not isinstance(coordinates, list) or len(coordinates) != 2:
        raise StationNormalizationError(
            "Coordinates must contain [longitude, latitude]."
        )

    longitude = _required_number(coordinates[0], "longitude")
    latitude = _required_number(coordinates[1], "latitude")

    if not -180 <= longitude <= 180:
        raise StationNormalizationError("Longitude is out of range.")

    if not -90 <= latitude <= 90:
        raise StationNormalizationError("Latitude is out of range.")

    properties = feature.get("properties")

    if not isinstance(properties, dict):
        raise StationNormalizationError(
            "Feature properties must be a dictionary."
        )

    osm_id = properties.get("osm_id")
    osm_type = properties.get("osm_type")

    if (
        isinstance(osm_id, bool)
        or not isinstance(osm_id, int)
        or osm_id <= 0
    ):
        raise StationNormalizationError("Invalid osm_id.")

    if (
        isinstance(osm_type, bool)
        or not isinstance(osm_type, int)
        or osm_type not in {1, 2, 3}
    ):
        raise StationNormalizationError("Invalid osm_type.")

    distance = _required_number(
        properties.get("distance"),
        "distance",
    )

    if distance < 0:
        raise StationNormalizationError(
            "Distance cannot be negative."
        )

    tags = properties.get("osm_tags_full", {})

    if not isinstance(tags, dict):
        raise StationNormalizationError(
            "osm_tags_full must be a dictionary."
        )

    return GeographicStation(
        osm_id=osm_id,
        osm_type=osm_type,
        longitude=longitude,
        latitude=latitude,
        distance_to_route_m=distance,
        name=_optional_tag(tags, "name"),
        brand=_optional_tag(tags, "brand"),
        street=_optional_tag(tags, "addr:street"),
        house_number=_optional_tag(tags, "addr:housenumber"),
        city=_optional_tag(tags, "addr:city"),
        state=_optional_tag(tags, "addr:state"),
        postcode=_optional_tag(tags, "addr:postcode"),
        osm_tags=tags.copy(),
    )


def normalize_stations(
    features: list[dict[str, Any]],
) -> list[GeographicStation]:
    if not isinstance(features, list):
        raise StationNormalizationError(
            "Features must be a list."
        )

    stations = []

    for index, feature in enumerate(features):
        try:
            stations.append(normalize_station(feature))
        except StationNormalizationError as exc:
            raise StationNormalizationError(
                f"Invalid station at index {index}: {exc}"
            ) from exc

    return stations
