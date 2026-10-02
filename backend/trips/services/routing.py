"""OpenRouteService client: geocoding (Pelias) and HGV directions.

Endpoints on https://api.heigit.org (replaces the deprecated api.openrouteservice.org):
  geocode:    GET  /pelias/v1/search
  directions: POST /openrouteservice/v2/directions/driving-hgv/geojson
The API key goes in the Authorization header.
"""

from dataclasses import dataclass

import requests
from django.conf import settings

from trips.hos.engine import Leg

ORS_BASE_URL = "https://api.heigit.org"
GEOCODE_PATH = "/pelias/v1/search"
DIRECTIONS_PATH = "/openrouteservice/v2/directions/driving-hgv/geojson"
TIMEOUT_SECONDS = 15

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


def _request(method, path, **kwargs):
    key = settings.ORS_API_KEY
    if not key:
        raise ApiKeyError("The OpenRouteService API key is missing (set ORS_API_KEY).")

    try:
        resp = requests.request(
            method, ORS_BASE_URL + path,
            headers={"Authorization": key},
            timeout=TIMEOUT_SECONDS,
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

    data = _request("GET", GEOCODE_PATH, params={
        "text": text,
        "size": 1,
        "boundary.country": "US",
    })
    features = data.get("features") or []
    if not features:
        raise AddressNotFound(f"Address not found: {text}")

    feature = features[0]
    lon, lat = feature["geometry"]["coordinates"][:2]
    label = feature.get("properties", {}).get("label") or text
    return lat, lon, label


def get_route(current, pickup, dropoff):
    """Route current → pickup → dropoff. Each point is a (lat, lon, label) tuple."""
    points = [current, pickup, dropoff]
    data = _request("POST", DIRECTIONS_PATH, json={
        "coordinates": [[lon, lat] for lat, lon, _ in points],
        "units": "mi",
        "instructions": True,
    })

    try:
        feature = data["features"][0]
        segments = feature["properties"]["segments"]
        coords = feature["geometry"]["coordinates"]
    except (KeyError, IndexError, TypeError):
        raise RoutingError("The routing service returned an unexpected response.")
    if len(segments) != 2:
        raise RoutingError(f"Expected 2 route legs, got {len(segments)}.")

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
    return Route(legs=legs, geometry=geometry, steps=steps)
