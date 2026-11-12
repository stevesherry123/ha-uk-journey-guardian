"""Station preferences must be unambiguous and separate from access timing."""

import pytest

from custom_components.journey_guardian.connection_preferences import (
    parse_station_transfers,
    station_key,
)


def test_exact_station_names_and_zone_prefix_share_a_key():
    assert parse_station_transfers("zzz Example Junction=15\nSample Harbour=0") == {
        "example junction": 15, "sample harbour": 0,
    }
    assert station_key("  Example   Junction ") == "example junction"
    assert parse_station_transfers(None) == {}


@pytest.mark.parametrize("text", [
    "Example=-1", "Example=1.5", "Example=1441", "=10", "Example=true",
    "Example=10\nexample=15", "zzz Example=10\nExample=15", "Example",
])
def test_invalid_or_duplicate_preferences_rejected(text):
    with pytest.raises(ValueError, match="invalid_station_transfers"):
        parse_station_transfers(text)
