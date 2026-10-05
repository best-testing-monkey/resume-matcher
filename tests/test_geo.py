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
