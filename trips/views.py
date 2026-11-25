from decimal import Decimal

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from trips.serializers import OptimizeRouteRequestSerializer
from trips.services.cache import (
    get_cached,
    poi_cache_key,
    route_cache_key,
    set_cached,
)
from trips.services.optimizer import (
    OptimizationError,
    VehicleConfig,
    optimize_route,
)
from trips.services.poi import (
    POIServiceError,
    get_fuel_stations,
)
from trips.services.price_reference import (
    PricedStation,
    PriceReferenceError,
    resolve_price_reference,
)
from trips.services.routing import (
    RoutingServiceError,
    get_route,
)
from trips.services.station_normalizer import (
    StationNormalizationError,
    normalize_stations,
)


METERS_PER_MILE = 1609.344


def _money(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(round(value, 2))


def _unwrap(station):
    if isinstance(station, PricedStation):
        return station.station, station.price_reference
    return station, None


def serialize_station(station, reference=None):
    station, reference = _unwrap(station)

    return {
        "osm_id": station.osm_id,
        "osm_type": station.osm_type,
        "name": station.name,
        "brand": station.brand,
        "address": station.address,
        "city": station.city,
        "state": station.state,
        "postcode": station.postcode,
        "coordinates": {
            "longitude": station.longitude,
            "latitude": station.latitude,
        },
        "distance_to_route_m": round(
            station.distance_to_route_m, 2
        ),
        "price_per_gallon": (
            _money(reference.price_per_gallon) if reference else None
        ),
        "price_status": (
            "csv_reference" if reference else "unavailable"
        ),
    }


def serialize_stop(stop):
    station, reference = _unwrap(stop.station)

    return {
        "station_id": station.osm_id,
        "station_name": station.name,
        "station_brand": station.brand,
        "coordinates": {
            "longitude": station.longitude,
            "latitude": station.latitude,
        },
        "route_progress_miles": round(
            stop.position.progress_miles, 2
        ),
        "estimated_detour_miles": round(
            stop.estimated_detour_miles, 2
        ),
        "fuel_at_arrival_gallons": round(
            stop.fuel_at_arrival_gallons, 2
        ),
        "fuel_after_refuel_gallons": round(
            stop.fuel_after_refuel_gallons, 2
        ),
        "fuel_price": (
            _money(stop.price_per_gallon)
            if stop.price_per_gallon is not None
            else None
        ),
        "fuel_price_basis": reference.basis if reference else None,
        "estimated_cost": _money(stop.estimated_cost),
    }


class OptimizeRouteView(APIView):
    def post(self, request):
        serializer = OptimizeRouteRequestSerializer(
            data=request.data
        )

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        validated = serializer.validated_data

        origin = validated["origin"]
        destination = validated["destination"]
        vehicle = VehicleConfig(**validated["vehicle"])

        origin_point = (
            origin["longitude"],
            origin["latitude"],
        )
        destination_point = (
            destination["longitude"],
            destination["latitude"],
        )

        route_key = route_cache_key(origin_point, destination_point)
        route = get_cached(route_key)
        route_hit = route is not None

        try:
            if route is None:
                route = get_route(
                    origin=origin_point,
                    destination=destination_point,
                )
                set_cached(route_key, route)

            poi_key = poi_cache_key(route.coordinates)
            raw_stations = get_cached(poi_key)
            poi_hit = raw_stations is not None

            if raw_stations is None:
                raw_stations = get_fuel_stations(route.coordinates)
                set_cached(poi_key, raw_stations)

        except (RoutingServiceError, POIServiceError) as exc:
            return Response(
                {
                    "error": "external_provider_error",
                    "detail": str(exc),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            stations = normalize_stations(raw_stations)

        except StationNormalizationError:
            return Response(
                {
                    "error": "invalid_provider_data",
                    "detail": (
                        "The station provider returned "
                        "data that could not be normalized."
                    ),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            reference = resolve_price_reference(
                origin_point,
                destination_point,
                route.road_names,
            )
        except PriceReferenceError:
            reference = None

        if reference is not None:
            stations = [
                PricedStation(station, reference)
                for station in stations
            ]

        route_distance_miles = (
            route.distance_meters / METERS_PER_MILE
        )

        try:
            result = optimize_route(
                route_coordinates=route.coordinates,
                stations=stations,
                vehicle=vehicle,
                route_distance_miles=route_distance_miles,
            )

        except OptimizationError:
            return Response(
                {
                    "error": "optimization_failed",
                    "detail": (
                        "The route or station data could "
                        "not be processed by the optimizer."
                    ),
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        warnings = list(result.warnings)

        warnings.append("no_verified_price_matches")
        if reference is not None and stations:
            warnings.append("reference_price_not_station_quote")
        if stations and reference is None:
            warnings.append("no_price_reference_available")

        warnings.append("geometric_detour_estimate")
        warnings.append("calculated_capacity_is_assumption")

        prices_available = bool(stations) and reference is not None

        # The headline fuel cost is the cost of the fuel consumed over the
        # whole route at the corridor reference price. It is independent of
        # whether a refueling stop was needed.
        reference_cost = None
        if reference is not None:
            reference_cost = (
                Decimal(str(route_distance_miles / vehicle.mpg))
                * reference.price_per_gallon
            )
        cost_available = reference_cost is not None

        return Response(
            {
                "route": {
                    "distance_meters": route.distance_meters,
                    "distance_miles": round(
                        route_distance_miles, 2
                    ),
                    "duration_seconds": route.duration_seconds,
                    "geometry": {
                        "type": "LineString",
                        "coordinates": route.coordinates,
                    },
                },
                "vehicle": {
                    "max_range_miles": vehicle.max_range_miles,
                    "mpg": vehicle.mpg,
                    "calculated_tank_capacity_gallons": round(
                        vehicle.capacity_gallons, 2
                    ),
                    "capacity_is_assumed": True,
                    "capacity_calculation": "max_range_miles / mpg",
                    "starting_fuel_gallons": round(
                        vehicle.starting_fuel_gallons, 2
                    ),
                },
                "optimization": {
                    "feasible": result.feasible,
                    "optimized_for_cost": result.optimized_for_cost,
                    "basis": (
                        "fuel_cost"
                        if result.optimized_for_cost
                        else "range_and_geometric_detour"
                    ),
                    "distance_estimation": {
                        "base_distance_miles": round(
                            result.route_distance_miles, 2
                        ),
                        "method": "provider_distance_plus_twice_lateral_offset",
                        "detours_are_road_distances": False,
                        "description": (
                            "Provider distance is authoritative. Detours are "
                            "estimated as twice the station's lateral distance "
                            "from the route. Actual road detours are not "
                            "calculated."
                        ),
                    },
                    "stops": [
                        serialize_stop(stop)
                        for stop in result.stops
                    ],
                    "estimated_total_distance_miles": round(
                        result.estimated_total_distance_miles, 2
                    ),
                    "remaining_fuel_gallons": (
                        round(result.remaining_fuel_gallons, 2)
                        if result.remaining_fuel_gallons is not None
                        else None
                    ),
                },
                "geographic_stations": [
                    serialize_station(station)
                    for station in stations
                ],
                "priced_stations": [
                    serialize_station(station)
                    for station in stations
                    if reference is not None
                ],
                "fuel_cost": {
                    "estimated_trip_fuel_cost": _money(reference_cost),
                    "estimated_refueling_cost": _money(result.total_cost),
                    "refueling_cost_note": (
                        "Estimated using prices available to the optimizer. "
                        "In live requests these are corridor reference "
                        "prices, not station quotes."
                        if result.total_cost is not None
                        else "No station-specific prices available; "
                        "refueling purchases are not estimated."
                    ),
                    "available": cost_available,
                    "is_monetary_quote": False,
                    "price_basis": reference.basis if reference else None,
                    "price_region": reference.region if reference else None,
                    "station_specific": False,
                    "source_rows": (
                        list(reference.source_rows)
                        if reference
                        else []
                    ),
                    "observation_count": (
                        reference.observation_count if reference else 0
                    ),
                    "currency": "unspecified",
                    "fuel_type": "unspecified",
                    "method": (
                        "route_distance_miles / mpg "
                        "* csv_reference_price_per_gallon"
                    ),
                    "note": (
                        "Estimated cost of fuel consumed over the whole "
                        "route, using a CSV-derived corridor reference. "
                        "It is not a station quote."
                    ),
                },
                "data_quality": {
                    "prices_available": prices_available,
                    "verified_price_matches": 0,
                    "price_matches_note": (
                        "No station-specific price was verified. Cost uses "
                        "a CSV-derived corridor reference."
                    ),
                    "csv_rows_evaluated": (
                        reference.observation_count if reference else 0
                    ),
                    "warnings": warnings,
                },
                "external_calls": {
                    "routing": 0 if route_hit else 1,
                    "poi": 0 if poi_hit else 1,
                    "total": (0 if route_hit else 1)
                    + (0 if poi_hit else 1),
                },
                "cache": {
                    "used": route_hit or poi_hit,
                    "route_hit": route_hit,
                    "poi_hit": poi_hit,
                },
            },
            status=status.HTTP_200_OK,
        )
