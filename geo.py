"""City-level travel-time estimates for job locations.

All travel times here are ESTIMATES, not routing results.

Heuristic (minutes, between city centres, d = haversine km):
  car     = d * 1.3 / 80 km/h * 60 + 10
  transit = d * 1.3 / 55 km/h * 60 + 25   (same city: 15)

Overriding with real data: ``travel_matrix.json`` next to this module (or the
path in env var ``GEO_TRAVEL_MATRIX``, or ``set_matrix(...)`` at runtime) may
hold precomputed per-pair minutes, e.g. from OSRM (car) or OpenTripPlanner +
GTFS (transit)::

    {"car": {"Almere|Amsterdam": 31}, "transit": {"Almere|Amsterdam": 44}}

Keys are "CityA|CityB" using canonical gazetteer names; pairs are symmetric.
A matrix entry wins over the heuristic; missing pairs fall back to it.

Location results: ``resolve_location`` returns a City, ``None`` (UNKNOWN: no
usable info) or a City with ``far=True`` (FAR: known place outside NL/BE/DE/
LU/FR/UK).
"""
from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from geo_data import CITIES, CITY_ALIASES, FAR_PLACES, REGIONS

ROAD_FACTOR = 1.3


@dataclass(frozen=True)
class City:
    name: str
    lat: float
    lon: float
    country: str          # ISO-2, or "FAR" for the too-far marker
    far: bool = False
    kind: str = "city"    # city | region | country | far


@dataclass(frozen=True)
class TravelResult:
    minutes: int | None
    status: str           # ok | remote | unknown | too_far


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return t.strip()


_INDEX: dict[str, City] = {}
_FAR: set[str] = {_norm(p) for p in FAR_PLACES}


def _build() -> None:
    for name, lat, lon, cc in CITIES:
        _INDEX[_norm(name)] = City(name, lat, lon, cc)
    for alias, canon in CITY_ALIASES.items():
        _INDEX.setdefault(_norm(alias), _INDEX[_norm(canon)])
    for name, (lat, lon, cc) in REGIONS.items():
        kind = "region" if cc == "NL" and name not in (
            "Netherlands", "Nederland", "Holland", "The Netherlands") else "country"
        _INDEX.setdefault(_norm(name), City(name, lat, lon, cc, kind=kind))
    # "Zuid Holland" etc. normalise identically to the hyphenated forms.


_build()
FAR_CITY = City("Too far", 0.0, 0.0, "FAR", far=True, kind="far")

_NOISE_WORDS = re.compile(
    r"\b(area|region|regio|metropolitan|metro|and surroundings|omgeving|province|provincie)\b")


def _lookup(part: str) -> City | None:
    n = _norm(part)
    if not n:
        return None
    if n in _INDEX:
        return _INDEX[n]
    stripped = _norm(_NOISE_WORDS.sub(" ", part.lower()))
    if stripped and stripped in _INDEX:
        return _INDEX[stripped]
    if n in _FAR or (stripped and stripped in _FAR):
        return FAR_CITY
    return None


def resolve_location(text: str | None) -> City | None:
    """Resolve free text to a City; None if unknown; City(far=True) if too far."""
    if not text or not str(text).strip():
        return None
    s = str(text)
    whole = _lookup(s)
    if whole:
        return whole
    parts = [p for p in re.split(r"[,/|;()\-–]\s+|[,/|;()]", s) if p.strip()]
    found = [r for r in (_lookup(p) for p in parts) if r]
    if not found:
        return None
    # Prefer a specific place (city part) over region/country/far markers.
    for r in found:
        if r.kind == "city":
            return r
    for r in found:
        if r.kind == "region":
            return r
    return found[0]


def haversine_km(a: City, b: City) -> float:
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dphi = p2 - p1
    dl = math.radians(b.lon - a.lon)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


_MATRIX: dict[str, dict[str, float]] | None = None


def set_matrix(matrix: dict[str, dict[str, float]] | None) -> None:
    """Install precomputed {"car": {"A|B": min}, "transit": {...}} overrides."""
    global _MATRIX
    _MATRIX = {m: {k: v for k, v in d.items()} for m, d in (matrix or {}).items()}


def _matrix() -> dict[str, dict[str, float]]:
    global _MATRIX
    if _MATRIX is None:
        path = Path(os.environ.get("GEO_TRAVEL_MATRIX")
                    or Path(__file__).with_name("travel_matrix.json"))
        try:
            _MATRIX = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _MATRIX = {}
    return _MATRIX


def _override(mode: str, a: City, b: City) -> int | None:
    table = _matrix().get(mode, {})
    for key in (f"{a.name}|{b.name}", f"{b.name}|{a.name}"):
        if key in table:
            return int(round(table[key]))
    return None


def _estimate(mode: str, a: City, b: City) -> int:
    ov = _override(mode, a, b)
    if ov is not None:
        return ov
    d = haversine_km(a, b) * ROAD_FACTOR
    if mode == "car":
        return int(round(d / 80 * 60 + 10))
    if a.name == b.name:
        return 15
    return int(round(d / 55 * 60 + 25))


def car_minutes(a: City, b: City) -> int:
    """Estimated door-to-door car minutes between two cities."""
    return _estimate("car", a, b)


def transit_minutes(a: City, b: City) -> int:
    """Estimated public-transport minutes between two cities (same city: 15)."""
    return _estimate("transit", a, b)


def travel_time(home_city_text: str, job_location_text: str | None,
                workplace: str | None, mode: str = "car") -> TravelResult:
    """Estimated travel from home to job. mode: 'car' or 'transit'."""
    if mode not in ("car", "transit"):
        raise ValueError(f"mode must be 'car' or 'transit', got {mode!r}")
    if workplace and _norm(workplace) in ("fully remote", "remote"):
        return TravelResult(0, "remote")
    job = resolve_location(job_location_text)
    if job is None:
        return TravelResult(None, "unknown")
    if job.far:
        return TravelResult(None, "too_far")
    home = resolve_location(home_city_text)
    if home is None:
        raise ValueError(f"cannot resolve home location {home_city_text!r}")
    if home.far:
        return TravelResult(None, "too_far")
    fn = car_minutes if mode == "car" else transit_minutes
    return TravelResult(fn(home, job), "ok")


def within_limit(result: TravelResult, max_minutes: int) -> bool:
    """Remote/unknown pass; too_far fails; otherwise minutes <= max_minutes."""
    if result.status in ("remote", "unknown"):
        return True
    if result.status == "too_far":
        return False
    return result.minutes is not None and result.minutes <= max_minutes
