"""OpenRouteService client: geocoding (Pelias) and HGV directions.

Endpoints on https://api.heigit.org (replaces the deprecated api.openrouteservice.org):
  geocode:    GET  /pelias/v1/search
  directions: POST /openrouteservice/v2/directions/driving-hgv/geojson
The API key goes in the Authorization header.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import requests
from django.conf import settings

from trips.hos.engine import Leg
from trips.services.regions import typed_region

ORS_BASE_URL = "https://api.heigit.org"
GEOCODE_PATH = "/pelias/v1/search"
REVERSE_PATH = "/pelias/v1/reverse"
DIRECTIONS_PATH = "/openrouteservice/v2/directions/driving-hgv/geojson"
TIMEOUT_SECONDS = 15
SNAP_RADIUS_METERS = 5000

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


class OutsideUS(RoutingError):
    pass


class NoAddress(RoutingError):
    pass


class OutsideUSInput(AddressNotFound):
    """The user typed a non-US region ("Toronto, ON")."""


class StateMismatch(AddressNotFound):
    """The match is not in the state the user typed (never swap "ON" for "OH")."""


class InvalidPlace(AddressNotFound):
    """The best match is not a usable place type (e.g. a state, a country or a ZIP area)."""


class NoRouteFound(RoutingError):
    def __init__(self, message, code=None, detail=""):
        super().__init__(message)
        self.code = code          # ORS error code, e.g. 2009 or 2010
        self.detail = detail      # ORS's own message


class UnroutablePoint(NoRouteFound):
    """No road near one trip location. .point_index: 0 current, 1 pickup, 2 dropoff."""

    def __init__(self, point_index):
        super().__init__("No road could be found near one of these locations.", code=2010)
        self.point_index = point_index


# ORS 2010: "Could not find routable point within a radius of 5000.0 meters of specified coordinate 1: ..."
_UNROUTABLE_COORDINATE = re.compile(r"specified coordinate (\d+)")


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
        raise NoRouteFound(NO_ROUTE_MESSAGES[code], code=code, detail=message)
    if resp.status_code == 404:
        raise NoRouteFound("No route could be found between these locations.")
    if resp.status_code >= 500:
        raise ServiceUnavailable("The routing service is unavailable. Try again later.")
    raise RoutingError(f"Routing request failed ({resp.status_code}): {message}")


# How precise a match is, by Pelias layer: an exact point, or the centre of a city/county/ZIP area.
LAYER_PRECISION = {
    "address": "exact", "venue": "exact", "street": "exact",
    "locality": "city", "county": "county", "postalcode": "zip",
}


def geocode(text):
    """Return (lat, lon, label) of the best US match for an address or place name."""
    return geocode_place(text)[:3]


def geocode_place(text):
    """Like geocode(), plus the match precision: "exact", "city", "county" or "zip"."""
    text = (text or "").strip()
    if not text:
        raise AddressNotFound("Enter an address.")
    if is_zip(text):
        return _geocode_zip(text)

    # Never swap the state the user typed: Pelias, limited to the US, turns "Toronto, ON"
    # into Toronto, OH. Reject non-US regions up front and check US states after the match.
    region = typed_region(text)
    if region and region[0] == "non_us":
        raise OutsideUSInput("That location is outside the US. Enter a US address.")
    if region and region[0] == "unknown_code":
        raise StateMismatch(f"Couldn't find '{text}'. Check the city and state.")

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
    if region and (props.get("region_a") or "").upper() != region[1]:
        raise StateMismatch(f"Couldn't find '{text}'. Check the city and state.")
    if props.get("layer") not in ACCEPTED_LAYERS:
        raise InvalidPlace("Enter a proper city or address")

    lon, lat = feature["geometry"]["coordinates"][:2]
    label = short_label(props.get("label") or text)
    return lat, lon, label, LAYER_PRECISION[props["layer"]]


def _geocode_zip(text):
    """US ZIP (or ZIP+4) → (lat, lon, "60632, Chicago, IL" or "ZIP 82190").

    No brackets: the UI adds "(ZIP area)" after ZIP-level locations.
    """
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
    label = f"{text}, {city}, {state}" if city and state else f"ZIP {text}"
    return lat, lon, label, "zip"


def reverse_address(lat, lon):
    """Readable US address label for a device position.

    Tries the nearest address/street, then the city/county (rural highways often have no
    address nearby). Raises OutsideUS for a non-US position, NoAddress when nothing is found.
    """
    for layers in ("address,street", "locality,county"):
        data = request_json("GET", REVERSE_PATH, params={
            "point.lat": lat, "point.lon": lon, "size": 1, "layers": layers,
        })
        features = data.get("features") or []
        if not features:
            continue
        props = features[0].get("properties") or {}
        if props.get("country_a") != "USA":
            raise OutsideUS("Your location is outside the US. Enter a US address.")
        return short_label(props.get("label") or "")
    raise NoAddress("Couldn't find an address for your location. Enter it instead.")


def short_label(label):
    """Pelias label in our "City, ST" style: "Chicago, IL, USA" → "Chicago, IL"."""
    label = label.strip()
    return label[:-len(", USA")] if label.endswith(", USA") else label


def _route_leg(a, b):
    """One leg a → b: (segment, [lon, lat] coordinates). Each point is (lat, lon, label)."""
    data = request_json("POST", DIRECTIONS_PATH, json={
        "coordinates": [[a[1], a[0]], [b[1], b[0]]],
        "units": "mi",
        "instructions": True,
        # Let each point snap to a road up to 5 km away (ORS default: 350 m). A city's
        # center point can be far from any road, e.g. Corpus Christi, TX is ~2.4 km out
        # in the bay. Kept finite so a point far out at sea still fails instead of guessing.
        "radiuses": [SNAP_RADIUS_METERS, SNAP_RADIUS_METERS],
    })
    try:
        feature = data["features"][0]
        segments = feature["properties"]["segments"]
        coords = feature["geometry"]["coordinates"]
        way_points = list(feature["properties"]["way_points"])
    except (KeyError, IndexError, TypeError):
        raise RoutingError("The routing service returned an unexpected response.")
    if len(segments) != 1:
        raise RoutingError(f"Expected 1 route segment per leg, got {len(segments)}.")
    if len(way_points) != 2 or not coords:
        raise RoutingError("The routing service returned an unexpected response.")
    return segments[0], coords


def get_route(current, pickup, dropoff):
    """Route current → pickup → dropoff. Each point is a (lat, lon, label) tuple.

    Each leg is its own request (sent in parallel): ORS limits the distance of a single
    request, so a long trip (e.g. Columbus → Los Angeles → Pennsylvania, ~4,700 mi) fails
    as one request even when each leg is within the limit. The legs are combined into the
    same Route a single request produced.
    """
    points = [current, pickup, dropoff]
    def leg(index):
        try:
            return _route_leg(points[index], points[index + 1])
        except NoRouteFound as e:
            # Name the location ORS couldn't reach: its coordinate number in this leg's
            # request (0 = leg start, 1 = leg end) plus the leg's offset in the trip.
            match = _UNROUTABLE_COORDINATE.search(e.detail) if e.code == 2010 else None
            if match and int(match.group(1)) in (0, 1):
                raise UnroutablePoint(index + int(match.group(1))) from e
            raise

    with ThreadPoolExecutor(max_workers=2) as pool:
        (seg0, coords0), (seg1, coords1) = pool.map(leg, [0, 1])

    # Join the geometries at the pickup; drop leg 2's first point when it repeats leg 1's last.
    if coords1[0] == coords0[-1]:
        coords1 = coords1[1:]
    coords = coords0 + coords1
    leg_bounds = [0, len(coords0) - 1, len(coords) - 1]
    segments = [seg0, seg1]

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
                 waypoints=list(points), leg_bounds=leg_bounds)
