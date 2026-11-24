
import pytest

from trips.serializers import (
    OptimizeRouteRequestSerializer,
    VehicleSerializer,
)


def valid_route_data():
    return {
        "origin": {
            "longitude": -80.1918,
            "latitude": 25.7617,
        },
        "destination": {
            "longitude": -81.3792,
            "latitude": 28.5383,
        },
    }


def test_request_accepts_valid_coordinates():
    serializer = OptimizeRouteRequestSerializer(
        data=valid_route_data()
    )

    assert serializer.is_valid(), serializer.errors


def test_request_adds_default_vehicle():
    serializer = OptimizeRouteRequestSerializer(
        data=valid_route_data()
    )

    assert serializer.is_valid(), serializer.errors

    assert serializer.validated_data["vehicle"] == {
        "max_range_miles": 500.0,
        "mpg": 10.0,
        "initial_fuel_gallons": None,
    }


def test_request_rejects_out_of_range_longitude():
    data = valid_route_data()
    data["origin"]["longitude"] = -200

    serializer = OptimizeRouteRequestSerializer(data=data)

    assert not serializer.is_valid()
    assert "origin" in serializer.errors


def test_request_rejects_out_of_range_latitude():
    data = valid_route_data()
    data["origin"]["latitude"] = 95

    serializer = OptimizeRouteRequestSerializer(data=data)

    assert not serializer.is_valid()
    assert "origin" in serializer.errors


def test_request_rejects_identical_origin_and_destination():
    data = valid_route_data()
    data["destination"] = data["origin"].copy()

    serializer = OptimizeRouteRequestSerializer(data=data)

    assert not serializer.is_valid()
    assert "non_field_errors" in serializer.errors


def test_vehicle_rejects_zero_max_range():
    serializer = VehicleSerializer(
        data={
            "max_range_miles": 0,
            "mpg": 10,
        }
    )

    assert not serializer.is_valid()
    assert "max_range_miles" in serializer.errors


def test_vehicle_rejects_zero_mpg():
    serializer = VehicleSerializer(
        data={
            "max_range_miles": 500,
            "mpg": 0,
        }
    )

    assert not serializer.is_valid()
    assert "mpg" in serializer.errors


def test_vehicle_rejects_initial_fuel_above_capacity():
    serializer = VehicleSerializer(
        data={
            "max_range_miles": 500,
            "mpg": 10,
            "initial_fuel_gallons": 60,
        }
    )

    assert not serializer.is_valid()
    assert "initial_fuel_gallons" in serializer.errors


def test_vehicle_accepts_initial_fuel_at_capacity():
    serializer = VehicleSerializer(
        data={
            "max_range_miles": 500,
            "mpg": 10,
            "initial_fuel_gallons": 50,
        }
    )

    assert serializer.is_valid(), serializer.errors


def test_vehicle_accepts_partial_initial_fuel():
    serializer = VehicleSerializer(
        data={
            "max_range_miles": 500,
            "mpg": 10,
            "initial_fuel_gallons": 25,
        }
    )

    assert serializer.is_valid(), serializer.errors


def test_vehicle_accepts_null_initial_fuel():
    serializer = VehicleSerializer(
        data={
            "max_range_miles": 500,
            "mpg": 10,
            "initial_fuel_gallons": None,
        }
    )

    assert serializer.is_valid(), serializer.errors
