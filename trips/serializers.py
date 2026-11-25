from rest_framework import serializers

from trips.services.price_reference import is_in_usa


class CoordinateSerializer(serializers.Serializer):
    longitude = serializers.FloatField(
        min_value=-180,
        max_value=180,
    )
    latitude = serializers.FloatField(
        min_value=-90,
        max_value=90,
    )


class VehicleSerializer(serializers.Serializer):
    max_range_miles = serializers.FloatField(
        min_value=0,
        default=500.0,
    )
    mpg = serializers.FloatField(
        min_value=0,
        default=10.0,
    )
    initial_fuel_gallons = serializers.FloatField(
        min_value=0,
        required=False,
        allow_null=True,
        default=None,
    )

    def validate_max_range_miles(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Maximum range must be greater than zero."
            )
        return value

    def validate_mpg(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "MPG must be greater than zero."
            )
        return value

    def validate(self, attrs):
        max_range = attrs["max_range_miles"]
        mpg = attrs["mpg"]
        initial_fuel = attrs["initial_fuel_gallons"]

        capacity = max_range / mpg

        if initial_fuel is not None and initial_fuel > capacity:
            raise serializers.ValidationError({
                "initial_fuel_gallons": (
                    "Initial fuel cannot exceed "
                    "the calculated tank capacity."
                )
            })

        return attrs


class OptimizeRouteRequestSerializer(serializers.Serializer):
    origin = CoordinateSerializer()
    destination = CoordinateSerializer()
    vehicle = VehicleSerializer(required=False)

    def validate(self, attrs):
        origin = attrs["origin"]
        destination = attrs["destination"]

        if (
            origin["longitude"] == destination["longitude"]
            and origin["latitude"] == destination["latitude"]
        ):
            raise serializers.ValidationError(
                "Origin and destination must be different."
            )

        location_errors = {}

        for field, point in (("origin", origin), ("destination", destination)):
            if not is_in_usa(point["longitude"], point["latitude"]):
                location_errors[field] = (
                    "Location must be within the United States."
                )

        if location_errors:
            raise serializers.ValidationError(location_errors)

        if "vehicle" not in attrs:
            attrs["vehicle"] = VehicleSerializer().to_internal_value({})

        return attrs

