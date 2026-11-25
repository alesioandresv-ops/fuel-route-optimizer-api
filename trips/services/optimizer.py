from dataclasses import dataclass, replace
from decimal import Decimal
import math

EARTH_RADIUS_M = 6_371_000.0
METERS_PER_MILE = 1609.344


class OptimizationError(ValueError):
    """Raised when route optimization parameters are invalid."""


@dataclass(frozen=True)
class VehicleConfig:
    max_range_miles: float = 500.0
    mpg: float = 10.0
    initial_fuel_gallons: float | None = None

    def __post_init__(self):
        if (
            isinstance(self.max_range_miles, bool)
            or not isinstance(self.max_range_miles, (int, float))
            or not math.isfinite(self.max_range_miles)
            or self.max_range_miles <= 0
        ):
            raise OptimizationError(
                "Maximum range must be a positive finite number."
            )

        if (
            isinstance(self.mpg, bool)
            or not isinstance(self.mpg, (int, float))
            or not math.isfinite(self.mpg)
            or self.mpg <= 0
        ):
            raise OptimizationError(
                "MPG must be a positive finite number."
            )

        if self.initial_fuel_gallons is not None:
            fuel = self.initial_fuel_gallons

            if (
                isinstance(fuel, bool)
                or not isinstance(fuel, (int, float))
                or not math.isfinite(fuel)
                or fuel < 0
                or fuel > self.capacity_gallons
            ):
                raise OptimizationError(
                    "Initial fuel must be between zero "
                    "and the calculated tank capacity."
                )

    @property
    def capacity_gallons(self) -> float:
        return self.max_range_miles / self.mpg

    @property
    def starting_fuel_gallons(self) -> float:
        if self.initial_fuel_gallons is None:
            return self.capacity_gallons

        return float(self.initial_fuel_gallons)



@dataclass(frozen=True)
class RoutePosition:
    progress_miles: float
    lateral_distance_m: float
    segment_index: int
    projected_longitude: float
    projected_latitude: float


@dataclass(frozen=True)
class PlannedStop:
    station: object
    position: RoutePosition
    estimated_detour_miles: float
    fuel_at_arrival_gallons: float
    fuel_after_refuel_gallons: float
    price_per_gallon: Decimal | None = None
    estimated_cost: Decimal | None = None


@dataclass(frozen=True)
class OptimizationResult:
    feasible: bool
    stops: tuple[PlannedStop, ...]
    route_distance_miles: float
    estimated_total_distance_miles: float
    remaining_fuel_gallons: float | None
    warnings: tuple[str, ...]
    total_cost: Decimal | None = None
    optimized_for_cost: bool = False


def _validate_coordinate(
    longitude: float,
    latitude: float,
) -> None:
    if (
        isinstance(longitude, bool)
        or isinstance(latitude, bool)
        or not isinstance(longitude, (int, float))
        or not isinstance(latitude, (int, float))
        or not math.isfinite(longitude)
        or not math.isfinite(latitude)
    ):
        raise OptimizationError("Invalid coordinate.")

    if not -180 <= longitude <= 180:
        raise OptimizationError("Longitude is out of range.")

    if not -90 <= latitude <= 90:
        raise OptimizationError("Latitude is out of range.")


def _haversine_distance(
    lon1: float,
    lat1: float,
    lon2: float,
    lat2: float,
) -> float:
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)

    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(delta_lon / 2) ** 2
    )

    return 2 * EARTH_RADIUS_M * math.asin(
        math.sqrt(min(1.0, a))
    )


def locate_station_on_route(
    route_coordinates: list[list[float]],
    longitude: float,
    latitude: float,
) -> RoutePosition:
    """
    Project a station onto the nearest route segment.

    Coordinates use GeoJSON order: [longitude, latitude].
    Progress is measured from the route origin.
    """

    _validate_coordinate(longitude, latitude)

    if not isinstance(route_coordinates, list) or len(route_coordinates) < 2:
        raise OptimizationError(
            "Route must contain at least two coordinates."
        )

    for coordinate in route_coordinates:
        if not isinstance(coordinate, (list, tuple)) or len(coordinate) != 2:
            raise OptimizationError("Invalid route coordinate.")

        _validate_coordinate(
            coordinate[0],
            coordinate[1],
        )

    cumulative_distance = 0.0
    best_position = None
    best_lateral_distance = float("inf")

    for index in range(len(route_coordinates) - 1):
        lon1, lat1 = route_coordinates[index]
        lon2, lat2 = route_coordinates[index + 1]

        segment_length = _haversine_distance(
            lon1, lat1, lon2, lat2
        )

        if segment_length == 0:
            continue

        # Local equirectangular projection in meters.
        reference_lat = math.radians(
            (lat1 + lat2 + latitude) / 3
        )

        longitude_scale = (
            EARTH_RADIUS_M * math.cos(reference_lat)
            * math.pi / 180
        )
        latitude_scale = EARTH_RADIUS_M * math.pi / 180

        dx = (lon2 - lon1) * longitude_scale
        dy = (lat2 - lat1) * latitude_scale

        station_x = (longitude - lon1) * longitude_scale
        station_y = (latitude - lat1) * latitude_scale

        segment_squared = dx * dx + dy * dy

        projection = (
            station_x * dx + station_y * dy
        ) / segment_squared

        projection = max(0.0, min(1.0, projection))

        projected_x = projection * dx
        projected_y = projection * dy

        lateral_distance = math.hypot(
            station_x - projected_x,
            station_y - projected_y,
        )

        if lateral_distance < best_lateral_distance:
            best_lateral_distance = lateral_distance

            projected_longitude = (
                lon1 + projection * (lon2 - lon1)
            )
            projected_latitude = (
                lat1 + projection * (lat2 - lat1)
            )

            progress_m = (
                cumulative_distance
                + projection * segment_length
            )

            best_position = RoutePosition(
                progress_miles=progress_m / METERS_PER_MILE,
                lateral_distance_m=lateral_distance,
                segment_index=index,
                projected_longitude=projected_longitude,
                projected_latitude=projected_latitude,
            )

        cumulative_distance += segment_length

    if best_position is None:
        raise OptimizationError(
            "Route does not contain a valid segment."
        )

    return best_position



def _build_cost_plan(
    candidates: list[dict],
    route_distance_miles: float,
    vehicle: VehicleConfig,
    starting_range_miles: float,
) -> tuple[list[PlannedStop], Decimal, float, float] | None:
    """Select stops that minimize purchased fuel cost, subject to range."""

    capacity = vehicle.capacity_gallons
    maximum_range = capacity * vehicle.mpg
    count = len(candidates)

    best_cost: list[Decimal | None] = [None] * count
    best_stops: list[int | None] = [None] * count
    predecessors: list[int | None] = [None] * count

    for i, candidate in enumerate(candidates):
        progress = candidate["position"].progress_miles
        lateral = candidate["lateral_miles"]

        if progress + lateral <= starting_range_miles:
            best_cost[i] = Decimal("0")
            best_stops[i] = 1

        for j in range(i):
            if best_cost[j] is None or best_stops[j] is None:
                continue

            previous = candidates[j]
            leg = (
                previous["lateral_miles"]
                + (progress - previous["position"].progress_miles)
                + lateral
            )
            if leg <= 0 or leg > maximum_range:
                continue

            price = previous["station"].price_per_gallon
            if price is None:
                continue

            proposed = best_cost[j] + Decimal(str(leg / vehicle.mpg)) * price
            proposed_stops = best_stops[j] + 1

            if (
                best_cost[i] is None
                or proposed < best_cost[i]
                or (
                    proposed == best_cost[i]
                    and proposed_stops < (best_stops[i] or count + 1)
                )
            ):
                best_cost[i] = proposed
                best_stops[i] = proposed_stops
                predecessors[i] = j

    best_total: Decimal | None = None
    last_index: int | None = None
    remaining_fuel = 0.0

    for i, candidate in enumerate(candidates):
        if best_cost[i] is None:
            continue

        final_leg = (
            route_distance_miles
            - candidate["position"].progress_miles
            + candidate["lateral_miles"]
        )
        if final_leg < 0 or final_leg > maximum_range:
            continue

        price = candidate["station"].price_per_gallon
        if price is None:
            continue

        proposed = best_cost[i] + Decimal(str(final_leg / vehicle.mpg)) * price

        current_stops = (
            best_stops[last_index] if last_index is not None else count + 1
        )
        candidate_stops = best_stops[i] or count + 1

        if (
            best_total is None
            or proposed < best_total
            or (proposed == best_total and candidate_stops < current_stops)
        ):
            best_total = proposed
            last_index = i
            remaining_fuel = vehicle.capacity_gallons - final_leg / vehicle.mpg

    if last_index is None or best_total is None:
        return None

    selected: list[int] = []
    current: int | None = last_index
    while current is not None:
        selected.append(current)
        current = predecessors[current]
    selected.reverse()

    stops: list[PlannedStop] = []
    total_detours = 0.0

    for order, index in enumerate(selected):
        candidate = candidates[index]
        lateral = candidate["lateral_miles"]
        total_detours += 2 * lateral

        if order == 0:
            leg = (
                candidate["position"].progress_miles
                + lateral
            )
            arrival_fuel = vehicle.starting_fuel_gallons - leg / vehicle.mpg
        else:
            previous = candidates[selected[order - 1]]
            leg = (
                candidate["position"].progress_miles
                - previous["position"].progress_miles
                + previous["lateral_miles"]
                + lateral
            )
            arrival_fuel = capacity - leg / vehicle.mpg

        next_candidate = (
            candidates[selected[order + 1]]
            if order + 1 < len(selected)
            else None
        )

        if next_candidate is None:
            next_progress = route_distance_miles
            next_lateral = 0.0
        else:
            next_progress = next_candidate["position"].progress_miles
            next_lateral = next_candidate["lateral_miles"]

        purchase_leg = (
            next_progress
            - candidate["position"].progress_miles
            + lateral
            + next_lateral
        )
        price = candidate["station"].price_per_gallon
        estimated_cost = (
            Decimal(str(purchase_leg / vehicle.mpg)) * price
            if price is not None
            else None
        )

        stops.append(
            PlannedStop(
                station=candidate["station"],
                position=candidate["position"],
                estimated_detour_miles=2 * lateral,
                fuel_at_arrival_gallons=max(0.0, arrival_fuel),
                fuel_after_refuel_gallons=capacity,
                price_per_gallon=price,
                estimated_cost=estimated_cost,
            )
        )

    return stops, best_total, max(0.0, remaining_fuel), total_detours


def optimize_route(
    route_coordinates,
    stations,
    vehicle,
    max_lateral_distance_m=1000.0,
    route_distance_miles=None,
):
    """
    Find a feasible refueling plan with the minimum number of stops.
    Route coordinates use GeoJSON order: [longitude, latitude].
    Station distances and route progress are geometric approximations.
    """

    if not isinstance(vehicle, VehicleConfig):
        raise OptimizationError("Invalid vehicle configuration.")

    if (
        isinstance(max_lateral_distance_m, bool)
        or not isinstance(max_lateral_distance_m, (int, float))
        or not math.isfinite(max_lateral_distance_m)
        or max_lateral_distance_m < 0
    ):
        raise OptimizationError(
            "Maximum lateral distance must be a non-negative finite number."
        )

    if not isinstance(route_coordinates, list) or len(route_coordinates) < 2:
        raise OptimizationError(
        "Route must contain at least two coordinates."
    )

    for coordinate in route_coordinates:
        if (
            not isinstance(coordinate, (list, tuple))
            or len(coordinate) != 2
        ):
            raise OptimizationError("Invalid route coordinate.")

        _validate_coordinate(
            coordinate[0],
            coordinate[1],
        )

    if not isinstance(stations, (list, tuple)):
        raise OptimizationError("Stations must be a list or tuple.")

    # Validate route geometry and reject zero-length routes.
    locate_station_on_route(
        route_coordinates,
        route_coordinates[0][0],
        route_coordinates[0][1],
    )

    # The provider's distance is authoritative. Geometry is used only to
    # place stations along the route; progress is scaled to match it.
    geometry_distance_m = sum(
        _haversine_distance(
            route_coordinates[index][0],
            route_coordinates[index][1],
            route_coordinates[index + 1][0],
            route_coordinates[index + 1][1],
        )
        for index in range(len(route_coordinates) - 1)
    )

    if geometry_distance_m <= 0:
        raise OptimizationError("Route geometry has zero length.")

    if route_distance_miles is None:
        route_distance_miles = geometry_distance_m / METERS_PER_MILE
        progress_scale = 1.0
    else:
        if (
            isinstance(route_distance_miles, bool)
            or not isinstance(route_distance_miles, (int, float))
            or not math.isfinite(route_distance_miles)
            or route_distance_miles <= 0
        ):
            raise OptimizationError("Invalid provider route distance.")
        progress_scale = route_distance_miles / (
            geometry_distance_m / METERS_PER_MILE
        )

    starting_fuel = vehicle.starting_fuel_gallons
    capacity = vehicle.capacity_gallons

    starting_range = starting_fuel * vehicle.mpg
    maximum_range = capacity * vehicle.mpg

    # The vehicle can reach the destination without refueling.
    if route_distance_miles <= starting_range:
        remaining_fuel = (
            starting_fuel
            - route_distance_miles / vehicle.mpg
        )

        return OptimizationResult(
            feasible=True,
            stops=(),
            route_distance_miles=route_distance_miles,
            estimated_total_distance_miles=route_distance_miles,
            remaining_fuel_gallons=max(0.0, remaining_fuel),
            warnings=(),
            total_cost=None,
            optimized_for_cost=False,
        )

    # Normalize and filter stations.
    candidates = []

    for station in stations:
        try:
            position = locate_station_on_route(
                route_coordinates,
                station.longitude,
                station.latitude,
            )
        except AttributeError as exc:
            raise OptimizationError(
                "Invalid station object."
            ) from exc

        if progress_scale != 1.0:
            position = replace(
                position,
                progress_miles=position.progress_miles * progress_scale,
            )

        if position.lateral_distance_m > max_lateral_distance_m:
            continue

        # Ignore stations at the origin or destination.
        if position.progress_miles <= 0:
            continue

        if position.progress_miles >= route_distance_miles:
            continue

        lateral_miles = (
            position.lateral_distance_m / METERS_PER_MILE
        )

        candidates.append({
            "station": station,
            "position": position,
            "lateral_miles": lateral_miles,
        })

    candidates.sort(
        key=lambda item: (
            item["position"].progress_miles,
            item["lateral_miles"],
        )
    )

    cost_mode = bool(candidates) and all(
        getattr(candidate["station"], "price_per_gallon", None) is not None
        for candidate in candidates
    )

    if cost_mode:
        cost_plan = _build_cost_plan(
            candidates,
            route_distance_miles,
            vehicle,
            starting_range,
        )

        if cost_plan is None:
            return OptimizationResult(
                feasible=False,
                stops=(),
                route_distance_miles=route_distance_miles,
                estimated_total_distance_miles=route_distance_miles,
                remaining_fuel_gallons=None,
                warnings=("no_feasible_refueling_plan",),
                optimized_for_cost=True,
            )

        stops, total_cost, remaining, detours = cost_plan

        warnings: tuple[str, ...] = ()
        if starting_fuel < capacity:
            warnings = ("initial_leg_cost_excluded",)

        return OptimizationResult(
            feasible=True,
            stops=tuple(stops),
            route_distance_miles=route_distance_miles,
            estimated_total_distance_miles=(
                route_distance_miles + detours
            ),
            remaining_fuel_gallons=remaining,
            warnings=warnings,
            total_cost=total_cost,
            optimized_for_cost=True,
        )

    # Dynamic programming:
    # best_stops[i] = minimum stops needed to reach station i.
    count = len(candidates)

    best_stops = [float("inf")] * count
    total_detours = [float("inf")] * count
    predecessors = [None] * count
    arrival_fuel = [0.0] * count

    for i, candidate in enumerate(candidates):
        progress = candidate["position"].progress_miles
        lateral = candidate["lateral_miles"]

        # Option 1: reach this station directly from the origin.
        initial_leg = progress + lateral

        if initial_leg <= starting_range:
            best_stops[i] = 1
            total_detours[i] = 2 * lateral
            arrival_fuel[i] = (
                starting_fuel - initial_leg / vehicle.mpg
            )

        # Option 2: reach this station from a previous station.
        for j in range(i):
            if best_stops[j] == float("inf"):
                continue

            previous = candidates[j]

            progress_difference = (
                progress
                - previous["position"].progress_miles
            )

            leg_distance = (
                previous["lateral_miles"]
                + progress_difference
                + lateral
            )

            if leg_distance > maximum_range:
                continue

            proposed_stops = best_stops[j] + 1
            proposed_detours = total_detours[j] + 2 * lateral

            if (
                proposed_stops < best_stops[i]
                or (
                    proposed_stops == best_stops[i]
                    and proposed_detours < total_detours[i]
                )
            ):
                best_stops[i] = proposed_stops
                total_detours[i] = proposed_detours
                predecessors[i] = j

                arrival_fuel[i] = (
                    capacity - leg_distance / vehicle.mpg
                )

    # Find the best way to reach the destination.
    best_destination_stops = float("inf")
    best_destination_detours = float("inf")
    destination_predecessor = None
    remaining_fuel = None

    for i, candidate in enumerate(candidates):
        if best_stops[i] == float("inf"):
            continue

        progress = candidate["position"].progress_miles
        lateral = candidate["lateral_miles"]

        final_leg = (
            route_distance_miles - progress + lateral
        )

        if final_leg > maximum_range:
            continue

        proposed_stops = best_stops[i]
        proposed_detours = total_detours[i]

        if (
            proposed_stops < best_destination_stops
            or (
                proposed_stops == best_destination_stops
                and proposed_detours < best_destination_detours
            )
        ):
            best_destination_stops = proposed_stops
            best_destination_detours = proposed_detours
            destination_predecessor = i

            remaining_fuel = (
                capacity - final_leg / vehicle.mpg
            )

    # No feasible refueling plan exists.
    if destination_predecessor is None:
        return OptimizationResult(
            feasible=False,
            stops=(),
            route_distance_miles=route_distance_miles,
            estimated_total_distance_miles=route_distance_miles,
            remaining_fuel_gallons=None,
            warnings=("no_feasible_refueling_plan",),
        )

    # Reconstruct the selected station sequence.
    selected_indices = []
    current = destination_predecessor

    while current is not None:
        selected_indices.append(current)
        current = predecessors[current]

    selected_indices.reverse()

    planned_stops = []

    for index in selected_indices:
        candidate = candidates[index]

        planned_stops.append(
            PlannedStop(
                station=candidate["station"],
                position=candidate["position"],
                estimated_detour_miles=(
                    2 * candidate["lateral_miles"]
                ),
                fuel_at_arrival_gallons=max(
                    0.0,
                    arrival_fuel[index],
                ),
                fuel_after_refuel_gallons=capacity,
            )
        )

    estimated_total_distance = (
        route_distance_miles + best_destination_detours
    )

    return OptimizationResult(
        feasible=True,
        stops=tuple(planned_stops),
        route_distance_miles=route_distance_miles,
        estimated_total_distance_miles=estimated_total_distance,
        remaining_fuel_gallons=max(0.0, remaining_fuel),
        warnings=(),
    )
