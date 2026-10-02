"""OpenRouteService client: geocoding (Pelias) and HGV directions.

Endpoints on https://api.heigit.org (replaces the deprecated api.openrouteservice.org):
  geocode:    GET  /pelias/v1/search
  directions: POST /openrouteservice/v2/directions/driving-hgv/geojson
The API key goes in the Authorization header.
"""

import re
from dataclasses import dataclass, field

import requests
from django.conf import settings

from trips.hos.engine import Leg

ORS_BASE_URL = "https://api.heigit.org"
GEOCODE_PATH = "/pelias/v1/search"
DIRECTIONS_PATH = "/openrouteservice/v2/directions/driving-hgv/geojson"
TIMEOUT_SECONDS = 15

# Geocoding acceptance. Pelias confidence is 0–1 with no documented threshold; correct
# city matches can be "fallback" at 0.6 (e.g. "Denver, CO"), while a typo that falls back
# to a whole state scores 0.3, so 0.5 separates them.
MIN_CONFIDENCE = 0.5
ACCEPTED_LAYERS = {"locality", "county", "address", "street", "venue"}

# US ZIP codes ("60632" or ZIP+4 "60632-1234") are looked up as postal codes.
ZIP_RE = re.compile(r"^(\d{5})(-\d{4})?$")


def is_zip(text):
    return bool(ZIP_RE.match((text or "").strip()))

# ORS routing error codes that mean "these places can't be routed".
NO_ROUTE_MESSAGES = {
    2004: "The route exceeds the routing service's limits (too long).",
    2009: "No truck route could be found between these locations.",
    2010: "No road could be found near one of these locations.",
}


class RoutingError(Exception):
    """Base class; str(error) is safe to show to the user."""


class AddressNotFound(RoutingError):
    pass


class InvalidPlace(AddressNotFound):
    """The best match is not a usable place type (e.g. a state, a country or a ZIP area)."""


class NoRouteFound(RoutingError):
    pass


class ApiKeyError(RoutingError):
    pass


class QuotaExceeded(RoutingError):
    pass


class ServiceUnavailable(RoutingError):
    pass


@dataclass
class Step:
    instruction: str
    name: str
    distance_miles: float
    duration_min: float


@dataclass
class Route:
    legs: list[Leg]                 # current → pickup, pickup → dropoff
    geometry: list[list[float]]     # [lat, lon] points, ready for Leaflet
    steps: list[list[Step]]         # turn-by-turn, one list per leg
    waypoints: list[tuple]          # (lat, lon, label) for current, pickup, dropoff
    leg_bounds: list[int]           # geometry indices of the waypoints; leg i = [b[i], b[i+1]]
    # Cumulative haversine miles per leg, filled lazily by stops.locate().
    leg_cum_miles: list | None = field(default=None, repr=False, compare=False)


def _error_details(resp):
    """(ORS error code or None, message) from an error response body."""
    try:
        body = resp.json()
    except ValueError:
        return None, resp.text[:200]
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        return error.get("code"), error.get("message", "")
    if isinstance(error, str):
        return None, error
    return None, str(body)[:200]


def request_json(method, path, timeout=TIMEOUT_SECONDS, **kwargs):
    """Call an api.heigit.org path and return the JSON body, mapping failures to RoutingError."""
    key = settings.ORS_API_KEY
    if not key:
        raise ApiKeyError("The OpenRouteService API key is missing (set ORS_API_KEY).")

    try:
        resp = requests.request(
            method, ORS_BASE_URL + path,
            headers={"Authorization": key},
            timeout=timeout,
            **kwargs,
        )
    except requests.Timeout:
        raise ServiceUnavailable("The routing service timed out. Try again.")
    except requests.RequestException:
        raise ServiceUnavailable("Could not reach the routing service. Try again.")

    if resp.status_code == 200:
        try:
            return resp.json()
        except ValueError:
            raise RoutingError("The routing service returned an unreadable response.")

    code, message = _error_details(resp)
    if resp.status_code in (401, 403):
        raise ApiKeyError("The OpenRouteService API key was rejected.")
    if resp.status_code == 429:
        raise QuotaExceeded("The routing service quota is used up. Try again later.")
    if code in NO_ROUTE_MESSAGES:
        raise NoRouteFound(NO_ROUTE_MESSAGES[code])
    if resp.status_code == 404:
        raise NoRouteFound("No route could be found between these locations.")
    if resp.status_code >= 500:
        raise ServiceUnavailable("The routing service is unavailable. Try again later.")
    raise RoutingError(f"Routing request failed ({resp.status_code}): {message}")


def geocode(text):
    """Return (lat, lon, label) of the best US match for an address or place name."""
    text = (text or "").strip()
    if not text:
        raise AddressNotFound("Enter an address.")
    if is_zip(text):
        return _geocode_zip(text)

    data = request_json("GET", GEOCODE_PATH, params={
        "text": text,
        "size": 1,
        "boundary.country": "US",
    })
    features = data.get("features") or []
    if not features:
        raise AddressNotFound(f"Address not found: {text}")

    feature = features[0]
    props = feature.get("properties") or {}
    # Never guess: a weak match (e.g. a typo that falls back to the whole state) is "not found".
    confidence = props.get("confidence")
    if confidence is not None and confidence < MIN_CONFIDENCE:
        raise AddressNotFound(f"Address not found: {text}")
    if props.get("layer") not in ACCEPTED_LAYERS:
        raise InvalidPlace("Enter a proper city or address")

    lon, lat = feature["geometry"]["coordinates"][:2]
    label = short_label(props.get("label") or text)
    return lat, lon, label


def _geocode_zip(text):
    """US ZIP (or ZIP+4) → (lat, lon, "60632 (Chicago, IL)" or "ZIP 82190")."""
    zip5 = ZIP_RE.match(text).group(1)
    data = request_json("GET", GEOCODE_PATH, params={
        "text": zip5,
        "size": 1,
        "boundary.country": "US",
        "layers": "postalcode",
    })
    features = data.get("features") or []
    props = (features[0].get("properties") or {}) if features else {}
    confidence = props.get("confidence")
    # Never guess: the match must be this exact ZIP, with good confidence.
    if (not features or props.get("layer") != "postalcode"
            or (props.get("postalcode") or props.get("name")) != zip5
            or (confidence is not None and confidence < MIN_CONFIDENCE)):
        raise AddressNotFound(f"ZIP code not found: {text}")

    lon, lat = features[0]["geometry"]["coordinates"][:2]
    city, state = props.get("locality"), props.get("region_a")
    label = f"{text} ({city}, {state})" if city and state else f"ZIP {text}"
    return lat, lon, label


def short_label(label):
    """Pelias label in our "City, ST" style: "Chicago, IL, USA" → "Chicago, IL"."""
    label = label.strip()
    return label[:-len(", USA")] if label.endswith(", USA") else label


def get_route(current, pickup, dropoff):
    """Route current → pickup → dropoff. Each point is a (lat, lon, label) tuple."""
    points = [current, pickup, dropoff]
    data = request_json("POST", DIRECTIONS_PATH, json={
        "coordinates": [[lon, lat] for lat, lon, _ in points],
        "units": "mi",
        "instructions": True,
    })

    try:
        feature = data["features"][0]
        segments = feature["properties"]["segments"]
        coords = feature["geometry"]["coordinates"]
        way_points = list(feature["properties"]["way_points"])
    except (KeyError, IndexError, TypeError):
        raise RoutingError("The routing service returned an unexpected response.")
    if len(segments) != 2:
        raise RoutingError(f"Expected 2 route legs, got {len(segments)}.")
    if len(way_points) != 3:
        raise RoutingError("The routing service returned an unexpected response.")

    # ORS omits distance/duration when they are 0 (e.g. pickup at the current location).
    legs = [
        Leg(
            start_name=points[i][2],
            end_name=points[i + 1][2],
            distance_miles=seg.get("distance", 0.0),
            drive_hours=seg.get("duration", 0.0) / 3600,
        )
        for i, seg in enumerate(segments)
    ]
    steps = [
        [
            Step(
                instruction=s.get("instruction", ""),
                name=s.get("name", ""),
                distance_miles=s.get("distance", 0.0),
                duration_min=s.get("duration", 0.0) / 60,
            )
            for s in seg.get("steps", [])
        ]
        for seg in segments
    ]
    geometry = [[c[1], c[0]] for c in coords]
    return Route(legs=legs, geometry=geometry, steps=steps,
                 waypoints=list(points), leg_bounds=way_points)
