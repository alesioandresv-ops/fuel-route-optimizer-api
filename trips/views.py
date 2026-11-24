
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from trips.serializers import OptimizeRouteRequestSerializer
from trips.services.optimizer import (
    OptimizationError,
    VehicleConfig,
    optimize_route,
)
from trips.services.poi import (
    POIServiceError,
    get_fuel_stations,
)
from trips.services.routing import (
    RoutingServiceError,
    get_route,
)
from trips.services.station_normalizer import (
    StationNormalizationError,
    normalize_stations,
)


def serialize_station(station):
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
        "price": None,
        "price_status": "unavailable",
    }


def serialize_stop(stop):
    station = stop.station

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
        "fuel_price": None,
        "estimated_cost": None,
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
        vehicle_data = validated["vehicle"]

        vehicle = VehicleConfig(**vehicle_data)

        try:
            route = get_route(
                origin=(
                    origin["longitude"],
                    origin["latitude"],
                ),
                destination=(
                    destination["longitude"],
                    destination["latitude"],
                ),
            )

            raw_stations = get_fuel_stations(
                route.coordinates
            )

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
            result = optimize_route(
                route_coordinates=route.coordinates,
                stations=stations,
                vehicle=vehicle,
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

        route_distance_miles = (
            route.distance_meters / 1609.344
        )

        warnings = list(result.warnings)

        warnings.append("no_verified_price_matches")
        warnings.append("geometric_detour_estimate")
        warnings.append("calculated_capacity_is_assumption")

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
                    "basis": "range_and_geometric_detour",
                    "distance_estimation": {
                        "base_distance_miles": round(
                            result.route_distance_miles, 2
                        ),
                        "method": "route_geometry_plus_twice_lateral_offset",
                        "detours_are_road_distances": False,
                        "description": (
                            "Detours are estimated geometrically using "
                            "twice the station's lateral distance from the route. "
                            "Actual road detours are not calculated."
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
                "priced_stations": [],
                "fuel_cost": {
                    "total": None,
                    "currency": "unspecified",
                    "fuel_type": "unspecified",
                    "available": False,
                },
                "data_quality": {
                    "prices_available": False,
                    "verified_price_matches": 0,
                    "warnings": warnings,
                },
                "external_calls": {
                    "routing": 1,
                    "poi": 1,
                    "total": 2,
                },
                "cache": {
                    "used": False,
                },
            },
            status=status.HTTP_200_OK,
        )
