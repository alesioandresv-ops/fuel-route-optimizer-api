import pytest

from trips.services.station_normalizer import (
    GeographicStation,
    StationNormalizationError,
    normalize_station,
    normalize_stations,
)


@pytest.fixture
def station_feature():
    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [-80.301406, 27.161983],
        },
        "properties": {
            "osm_id": 150573636,
            "osm_type": 2,
            "distance": 297.28718857,
            "category_ids": {
                "596": {
                    "category_name": "fuel",
                    "category_group": "transport",
                }
            },
            "osm_tags_full": {
                "addr:city": "Palm City",
                "addr:housenumber": "3551",
                "addr:postcode": "34990",
                "addr:state": "FL",
                "addr:street": "Southwest Martin Downs Boulevard",
                "amenity": "fuel",
                "building": "roof",
                "source": "Bing",
            },
        },
    }


def test_normalizes_station_without_name_or_brand(station_feature):
    station = normalize_station(station_feature)

    assert isinstance(station, GeographicStation)
    assert station.osm_id == 150573636
    assert station.osm_type == 2
    assert station.longitude == -80.301406
    assert station.latitude == 27.161983
    assert station.distance_to_route_m == pytest.approx(297.28718857)
    assert station.name is None
    assert station.brand is None
    assert station.city == "Palm City"
    assert station.state == "FL"


def test_builds_address_from_available_tags(station_feature):
    station = normalize_station(station_feature)

    assert station.address == (
        "3551 Southwest Martin Downs Boulevard"
    )


def test_preserves_original_osm_tags(station_feature):
    station = normalize_station(station_feature)

    assert station.osm_tags["amenity"] == "fuel"
    assert station.osm_tags["source"] == "Bing"


def test_normalizes_name_and_brand(station_feature):
    station_feature["properties"]["osm_tags_full"].update({
        "name": "Mobil",
        "brand": "Mobil",
    })

    station = normalize_station(station_feature)

    assert station.name == "Mobil"
    assert station.brand == "Mobil"


def test_normalizes_multiple_stations(station_feature):
    stations = normalize_stations([
        station_feature,
        station_feature,
    ])

    assert len(stations) == 2


def test_rejects_invalid_coordinates(station_feature):
    station_feature["geometry"]["coordinates"] = [200, 27]

    with pytest.raises(StationNormalizationError):
        normalize_station(station_feature)


def test_rejects_negative_distance(station_feature):
    station_feature["properties"]["distance"] = -10

    with pytest.raises(StationNormalizationError):
        normalize_station(station_feature)


def test_rejects_invalid_osm_type(station_feature):
    station_feature["properties"]["osm_type"] = 4

    with pytest.raises(StationNormalizationError):
        normalize_station(station_feature)


def test_reports_invalid_feature_index(station_feature):
    with pytest.raises(
        StationNormalizationError,
        match="index 1",
    ):
        normalize_stations([
            station_feature,
            {"type": "Invalid"},
        ])


@pytest.mark.parametrize(
    "invalid_value",
    [
        "297.28",
        True,
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_rejects_invalid_distance_values(station_feature, invalid_value):
    station_feature["properties"]["distance"] = invalid_value

    with pytest.raises(StationNormalizationError):
        normalize_station(station_feature)


def test_rejects_string_coordinates(station_feature):
    station_feature["geometry"]["coordinates"] = [
        "-80.301406",
        27.161983,
    ]

    with pytest.raises(StationNormalizationError):
        normalize_station(station_feature)


def test_rejects_boolean_coordinates(station_feature):
    station_feature["geometry"]["coordinates"] = [
        True,
        27.161983,
    ]

    with pytest.raises(StationNormalizationError):
        normalize_station(station_feature)


def test_rejects_non_finite_coordinates(station_feature):
    station_feature["geometry"]["coordinates"] = [
        float("nan"),
        27.161983,
    ]

    with pytest.raises(StationNormalizationError):
        normalize_station(station_feature)