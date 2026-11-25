"""Price references derived from the supplied CSV.

No price is assigned to a specific station. The artifact aggregates original
observations by state and route; the API exposes the basis and source rows so
the estimate can always be reconstructed.
"""

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
import json
import math
import re
from pathlib import Path
from typing import Any


ARTIFACT_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "price_references.json"
)

# Approximate bounding boxes. They are used only to reject out-of-scope
# coordinates and to pick a coarse price region, never to invent a station.
US_STATE_BOUNDS: dict[str, tuple[float, float, float, float]] = {
    "AL": (-88.5, 30.1, -84.8, 35.1),
    "AK": (-179.0, 51.0, -129.0, 71.5),
    "AZ": (-114.9, 31.2, -109.0, 37.1),
    "AR": (-94.7, 32.9, -89.6, 36.6),
    "CA": (-124.5, 32.4, -114.0, 42.1),
    "CO": (-109.1, 36.9, -102.0, 41.1),
    "CT": (-73.8, 40.9, -71.7, 42.1),
    "DE": (-75.9, 38.4, -74.9, 39.9),
    "FL": (-87.7, 24.4, -79.9, 31.1),
    "GA": (-85.7, 30.3, -80.7, 35.1),
    "HI": (-160.3, 18.9, -154.7, 22.3),
    "ID": (-117.3, 41.9, -110.9, 49.1),
    "IL": (-91.6, 36.9, -87.4, 42.6),
    "IN": (-88.2, 37.7, -84.7, 41.9),
    "IA": (-96.7, 40.3, -90.0, 43.6),
    "KS": (-102.1, 36.9, -94.5, 40.1),
    "KY": (-89.6, 36.4, -81.9, 39.2),
    "LA": (-94.1, 28.8, -88.7, 33.1),
    "ME": (-71.1, 43.0, -66.8, 47.6),
    "MD": (-79.6, 37.8, -75.0, 39.8),
    "MA": (-73.6, 41.1, -69.8, 42.9),
    "MI": (-90.5, 41.6, -82.2, 48.3),
    "MN": (-97.3, 43.4, -89.4, 49.5),
    "MS": (-91.7, 30.1, -88.0, 35.1),
    "MO": (-95.8, 35.9, -89.0, 40.7),
    "MT": (-116.1, 44.3, -104.0, 49.1),
    "NE": (-104.1, 39.9, -95.2, 43.1),
    "NV": (-120.1, 34.9, -114.0, 42.1),
    "NH": (-72.6, 42.6, -70.6, 45.4),
    "NJ": (-75.6, 38.8, -73.8, 41.4),
    "NM": (-109.1, 31.2, -102.9, 37.1),
    "NY": (-79.9, 40.4, -71.8, 45.1),
    "NC": (-84.4, 33.7, -75.4, 36.7),
    "ND": (-104.1, 45.9, -96.5, 49.1),
    "OH": (-84.9, 38.3, -80.4, 42.4),
    "OK": (-103.1, 33.5, -94.4, 37.1),
    "OR": (-124.7, 41.9, -116.4, 46.4),
    "PA": (-80.6, 39.6, -74.6, 42.3),
    "RI": (-71.9, 41.1, -71.1, 42.0),
    "SC": (-83.4, 32.0, -78.4, 35.3),
    "SD": (-104.1, 42.4, -96.4, 46.1),
    "TN": (-90.4, 34.9, -81.6, 36.8),
    "TX": (-106.7, 25.8, -93.4, 36.6),
    "UT": (-114.1, 36.9, -109.0, 42.1),
    "VT": (-73.5, 42.6, -71.4, 45.1),
    "VA": (-83.8, 36.4, -75.1, 39.6),
    "WA": (-124.9, 45.5, -116.8, 49.1),
    "WV": (-82.7, 37.1, -77.6, 40.7),
    "WI": (-92.9, 42.4, -86.7, 47.1),
    "WY": (-111.1, 40.9, -104.0, 45.1),
}

ROUTE_NAME_PATTERN = re.compile(
    r"\b(interstate|i|us|sr|state road|state route|county road|cr)"
    r"[-\s]?(\d+[a-z]?)\b",
    re.IGNORECASE,
)


class PriceReferenceError(ValueError):
    """Raised when the derived price artifact cannot be used."""


@dataclass(frozen=True)
class PriceReference:
    price_per_gallon: Decimal
    basis: str
    region: str
    observation_count: int
    min_price: Decimal
    max_price: Decimal
    source_rows: tuple[int, ...]
    currency: str
    fuel_type: str
    method: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "price_basis": self.basis,
            "price_region": self.region,
            "station_specific": False,
            "observation_count": self.observation_count,
            "min_price": str(self.min_price),
            "max_price": str(self.max_price),
            "source_rows": list(self.source_rows),
            "currency": self.currency,
            "fuel_type": self.fuel_type,
            "method": self.method,
        }


@dataclass(frozen=True)
class PricedStation:
    """A geographic station plus a non-station-specific price reference."""

    station: Any
    price_reference: PriceReference

    @property
    def price_per_gallon(self) -> Decimal:
        return self.price_reference.price_per_gallon

    @property
    def longitude(self) -> float:
        return self.station.longitude

    @property
    def latitude(self) -> float:
        return self.station.latitude

    @property
    def osm_id(self) -> int:
        return self.station.osm_id

    @property
    def osm_type(self) -> int:
        return self.station.osm_type


def state_for_point(longitude: float, latitude: float) -> str | None:
    for state, (min_lon, min_lat, max_lon, max_lat) in US_STATE_BOUNDS.items():
        if min_lon <= longitude <= max_lon and min_lat <= latitude <= max_lat:
            return state
    return None


def is_in_usa(longitude: float, latitude: float) -> bool:
    if not all(math.isfinite(value) for value in (longitude, latitude)):
        return False
    return state_for_point(longitude, latitude) is not None


def canonical_route_name(name: str) -> str | None:
    match = ROUTE_NAME_PATTERN.search(name or "")
    if not match:
        return None
    prefix, number = match.groups()
    prefix = prefix.upper()
    if prefix in {"INTERSTATE", "I"}:
        prefix = "I"
    elif prefix in {"STATE ROAD", "STATE ROUTE", "SR"}:
        prefix = "SR"
    elif prefix in {"COUNTY ROAD", "CR"}:
        prefix = "CR"
    else:
        prefix = "US"
    return f"{prefix} {number.upper()}"


def _prices(bucket: dict[str, Any]) -> list[Decimal]:
    return [Decimal(value) for value in bucket.get("prices", [])]


def _rows(bucket: dict[str, Any]) -> list[int]:
    return [int(value) for value in bucket.get("source_rows", [])]


@lru_cache(maxsize=1)
def load_reference_artifact() -> dict[str, Any]:
    try:
        artifact = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PriceReferenceError(
            "Price reference artifact is not available."
        ) from error
    return artifact


def summarize_buckets(
    buckets: list[dict[str, Any]],
    basis: str,
    region: str,
) -> PriceReference:
    artifact = load_reference_artifact()
    prices = [
        price
        for bucket in buckets
        for price in _prices(bucket)
    ]
    rows = sorted(
        {
            row
            for bucket in buckets
            for row in _rows(bucket)
        }
    )

    if not prices:
        raise PriceReferenceError("No price observations for this region.")

    distinct_prices = sorted(set(prices))
    middle = len(distinct_prices) // 2

    if len(distinct_prices) % 2:
        median = distinct_prices[middle]
    else:
        median = (
            distinct_prices[middle - 1] + distinct_prices[middle]
        ) / Decimal("2")

    return PriceReference(
        price_per_gallon=median,
        basis=basis,
        region=region,
        observation_count=len(prices),
        min_price=min(prices),
        max_price=max(prices),
        source_rows=tuple(rows),
        currency=artifact["currency"],
        fuel_type=artifact["fuel_type"],
        method=artifact["method"],
    )


def resolve_price_reference(
    origin: tuple[float, float],
    destination: tuple[float, float],
    route_names: tuple[str, ...] = (),
) -> PriceReference | None:
    """Pick a CSV-derived reference for the corridor, never for a station."""

    artifact = load_reference_artifact()
    routes = artifact["routes"]
    states = artifact["states"]

    matched_routes = sorted(
        {
            name
            for raw in route_names
            if (name := canonical_route_name(raw))
            and name in routes
        }
    )

    if matched_routes:
        return summarize_buckets(
            [routes[name] for name in matched_routes],
            basis="csv_route_reference",
            region=", ".join(matched_routes),
        )

    origin_state = state_for_point(*origin)
    destination_state = state_for_point(*destination)

    matched_states = sorted(
        {
            state
            for state in (origin_state, destination_state)
            if state and state in states
        }
    )

    if matched_states:
        return summarize_buckets(
            [states[state] for state in matched_states],
            basis="csv_state_reference",
            region=", ".join(matched_states),
        )

    if "national" in artifact:
        return summarize_buckets(
            [artifact["national"]],
            basis="csv_national_reference",
            region="US",
        )

    return None
