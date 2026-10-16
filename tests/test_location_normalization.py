import json

from jarvis_channels.types import NormalizedLocation
from jarvis_channels.location import format_inbound_location


def test_format_inbound_location_pin():
    loc = NormalizedLocation(
        latitude=48.858844,
        longitude=2.294351,
        accuracy_m=12,
        source="pin"
    )
    
    res = format_inbound_location("Look at this!", loc)
    
    assert "Look at this!" in res
    assert "📍 48.858844, 2.294351 ±12m" in res
    assert "Location (untrusted metadata):" in res
    
    # Extract JSON part
    json_str = res.split("```json\n")[1].split("\n```")[0]
    data = json.loads(json_str)
    
    assert data["LocationLat"] == 48.858844
    assert data["LocationLon"] == 2.294351
    assert data["LocationSource"] == "pin"
    assert data["LocationIsLive"] is False
    assert data["LocationAccuracy"] == 12


def test_format_inbound_location_live():
    loc = NormalizedLocation(
        latitude=40.712800,
        longitude=-74.006000,
        source="live",
        is_live=True
    )
    
    res = format_inbound_location("", loc)
    
    assert "🛰 Live location 40.712800, -74.006000" in res
    
    json_str = res.split("```json\n")[1].split("\n```")[0]
    data = json.loads(json_str)
    
    assert data["LocationLat"] == 40.7128
    assert data["LocationLon"] == -74.0060
    assert data["LocationSource"] == "live"
    assert data["LocationIsLive"] is True
    assert "LocationAccuracy" not in data


def test_format_inbound_location_venue():
    loc = NormalizedLocation(
        latitude=51.5074,
        longitude=-0.1278,
        source="place",
        name="London Eye",
        address="Riverside Building, County Hall, London"
    )
    
    res = format_inbound_location("", loc)
    
    assert "📍 51.507400, -0.127800" in res
    
    json_str = res.split("```json\n")[1].split("\n```")[0]
    data = json.loads(json_str)
    
    assert data["LocationLat"] == 51.5074
    assert data["LocationName"] == "London Eye"
    assert data["LocationAddress"] == "Riverside Building, County Hall, London"
