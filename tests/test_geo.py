import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import geo
from geo import (car_minutes, resolve_location, transit_minutes, travel_time,
                 within_limit)


@pytest.fixture(autouse=True)
def _no_matrix():
    geo.set_matrix({})
    yield
    geo.set_matrix(None)


def test_almere_amsterdam_car_and_transit():
    r = travel_time("Almere", "Amsterdam", "On-site", "car")
    assert r.status == "ok" and 25 <= r.minutes <= 40
    t = travel_time("Almere", "Amsterdam", "On-site", "transit")
    assert t.minutes > transit_minutes(resolve_location("Almere"), resolve_location("Almere"))
    assert t.minutes == transit_minutes(resolve_location("Almere"), resolve_location("Amsterdam"))


def test_same_city_transit_is_15():
    a = resolve_location("Almere")
    assert transit_minutes(a, a) == 15
    assert car_minutes(a, a) == 10


@pytest.mark.parametrize("place", ["Madrid", "Barcelona", "United States", "Ukraine"])
def test_far(place):
    r = travel_time("Almere", place, "On-site", "car")
    assert (r.status, r.minutes) == ("too_far", None)
    assert not within_limit(r, 600)
    assert resolve_location(place).far


def test_remote():
    r = travel_time("Almere", "Madrid", "Fully Remote", "car")
    assert (r.minutes, r.status) == (0, "remote")
    assert within_limit(r, 0)


@pytest.mark.parametrize("text", ["Not Available", "", None, "hybride",
                                  "Time zone: CET (+/- 3 hours)"])
def test_unknown_passes(text):
    assert resolve_location(text) is None
    r = travel_time("Almere", text, "Hybrid", "car")
    assert (r.minutes, r.status) == (None, "unknown")
    assert within_limit(r, 1)


def test_aliases():
    base = resolve_location("Den Haag")
    for alias in ["'s-Gravenhage", "The Hague", "den haag", "DEN HAAG"]:
        assert resolve_location(alias) == base
    assert resolve_location("Den Bosch") == resolve_location("'s-Hertogenbosch")
    assert resolve_location("Frankfurt am Main").name == "Frankfurt"
    assert resolve_location("Düsseldorf") == resolve_location("Dusseldorf")


def test_city_province_and_regions():
    assert resolve_location("Weert, Limburg").name == "Weert"
    assert resolve_location("Almere, Flevoland").name == "Almere"
    z = resolve_location("Zuid Holland")
    assert z.country == "NL" and not z.far
    assert resolve_location("Noord-Brabant").country == "NL"
    assert resolve_location("Deutschland").country == "DE"
    assert resolve_location("Amsterdam, Netherlands").name == "Amsterdam"
    assert travel_time("Almere", "Zuid Holland", "On-site", "car").status == "ok"


def test_gazetteer_size_and_required_cities():
    assert len(geo.CITIES) >= 100
    for c in ["Almere", "Hoofddorp", "Tiel", "Weert", "Lelystad", "Paris", "London", "Lille"]:
        assert resolve_location(c).name == c


def test_hybrid_and_onsite_count_full_time():
    onsite = travel_time("Almere", "Eindhoven", "On-site", "car")
    hybrid = travel_time("Almere", "Eindhoven", "Hybrid", "car")
    assert hybrid == onsite and hybrid.minutes > 60


def test_both_modes_and_limit():
    car = travel_time("Almere", "Utrecht", "On-site", "car")
    tr = travel_time("Almere", "Utrecht", "On-site", "transit")
    assert tr.minutes > car.minutes
    assert within_limit(car, car.minutes) and not within_limit(car, car.minutes - 1)
    with pytest.raises(ValueError):
        travel_time("Almere", "Utrecht", "On-site", "bike")


def test_matrix_override():
    geo.set_matrix({"car": {"Amsterdam|Almere": 99}})
    assert travel_time("Almere", "Amsterdam", "On-site", "car").minutes == 99
    assert travel_time("Almere", "Amsterdam", "On-site", "transit").minutes != 99


def test_transit_override_almere_den_haag():
    """Almere->Den Haag: 70 rail min + 25 door-to-door = 95 min."""
    result = travel_time("Almere", "Den Haag", "On-site", "transit")
    assert result.status == "ok"
    assert 90 <= result.minutes <= 110, f"Expected ~95 min, got {result.minutes}"


def test_transit_override_amsterdam_utrecht():
    """Amsterdam->Utrecht: 27 rail min + 25 door-to-door = 52 min."""
    result = travel_time("Amsterdam", "Utrecht", "On-site", "transit")
    assert result.status == "ok"
    assert result.minutes == 52, f"Expected 52 min, got {result.minutes}"


def test_transit_override_symmetric():
    """Symmetric pair lookup: both A->B and B->A give same result."""
    ab = transit_minutes(resolve_location("Almere"), resolve_location("Den Haag"))
    ba = transit_minutes(resolve_location("Den Haag"), resolve_location("Almere"))
    assert ab == ba, f"Asymmetric: Almere->Den Haag={ab}, Den Haag->Almere={ba}"


def test_matrix_override_beats_transit_override():
    """External matrix override takes precedence over built-in transit override."""
    # Built-in override for Amsterdam|Utrecht is 52
    # But set it to 999 in the matrix
    geo.set_matrix({"transit": {"Amsterdam|Utrecht": 999}})
    result = travel_time("Amsterdam", "Utrecht", "On-site", "transit")
    assert result.minutes == 999, f"Matrix should win, got {result.minutes}"
    # Also test reverse order
    result2 = travel_time("Utrecht", "Amsterdam", "On-site", "transit")
    assert result2.minutes == 999, f"Matrix should win (reverse), got {result2.minutes}"


def test_transit_override_not_in_table_uses_heuristic():
    """Pairs not in TRANSIT_OVERRIDES fall back to heuristic."""
    # Helsinki is not in the override table, should use heuristic
    # (and since it's far, should return too_far, but let's test with a closer city)
    # Enschede->Leiden is not in the override table
    result = travel_time("Enschede", "Leiden", "On-site", "transit")
    assert result.status == "ok"
    # Just check it's reasonable (should be ~150-200 km by heuristic)
    assert result.minutes > 70  # Definitely longer than the shortest override


def test_almere_groningen_eindhoven_overrides():
    """Test specific Almere pairs mentioned in the task."""
    # Almere->Den Haag: 70+25=95
    result_den_haag = travel_time("Almere", "Den Haag", "On-site", "transit")
    assert result_den_haag.minutes == 95

    # Almere->Groningen: 115+25=140
    result_groningen = travel_time("Almere", "Groningen", "On-site", "transit")
    assert result_groningen.minutes == 140

    # Almere->Eindhoven: 105+25=130
    result_eindhoven = travel_time("Almere", "Eindhoven", "On-site", "transit")
    assert result_eindhoven.minutes == 130
