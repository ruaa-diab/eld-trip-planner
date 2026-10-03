"""Full trip plan: geocode → route → HOS engine → validator → stop names → log sheets."""

import logging
from concurrent.futures import ThreadPoolExecutor

from trips.hos.engine import plan_trip
from trips.hos.validator import validate_trip
from trips.services.logs import CYCLE_LIMIT_MIN, build_logs
from trips.services.routing import (
    AddressNotFound, InvalidPlace, OutsideUSInput, StateMismatch, UnroutableLeg, UnroutablePoint,
    geocode_place, get_route,
)
from trips.services.stops import haversine_miles, locate, name_stops

logger = logging.getLogger(__name__)

LOCATION_FIELDS = ("current_location", "pickup_location", "dropoff_location")
FIELD_LABELS = {
    "current_location": "Current location",
    "pickup_location": "Pickup location",
    "dropoff_location": "Dropoff location",
}
MAX_GEOMETRY_POINTS = 1500
SAME_PLACE_MILES = 0.1      # resolved points this close count as the same location


def no_road_message(label, precision):
    """Message for a location found by the geocoder but too far from any truck road."""
    if precision == "county":
        return f"No road near {label}. Please be more specific: enter a city or address in the county."
    return f"No road near {label}. Please be more specific: try a nearby address."


def same_location_notices(places):
    """Notices for repeated locations, from resolved coordinates (never the typed text).

    Current = pickup or current = dropoff is normal (the truck is already there): no notice.
    """
    current, pickup, dropoff = [p[:2] for p in places]
    pickup_is_dropoff = haversine_miles(pickup, dropoff) <= SAME_PLACE_MILES
    if pickup_is_dropoff and haversine_miles(current, pickup) <= SAME_PLACE_MILES:
        return ["All three locations are the same; no driving is needed."]
    if pickup_is_dropoff:
        return ["Pickup and dropoff are the same location."]
    return []


class AddressesNotFound(Exception):
    """One or more locations could not be used.

    .fields lists them in form order; .reasons maps each to "not_found" (no confident match),
    "invalid_place" (the match is a state, country, ZIP area, ...), "outside_us" (a non-US
    region was typed), "state_mismatch" (no match in the state that was typed), "no_road"
    (the location was found but no truck road is near it) or "no_route" (no road connects
    this leg's start to this location). .messages holds ready-made per-field messages the
    form shows as given (no_road, no_route).
    """

    def __init__(self, reasons, texts, field_messages=None):
        self.fields = list(reasons)
        self.reasons = reasons
        self.messages = field_messages or {}
        messages = {
            "no_road": lambda f: f"{FIELD_LABELS[f]}: {self.messages[f]}",
            "no_route": lambda f: f"{FIELD_LABELS[f]}: {self.messages[f]}",
            "invalid_place": lambda f: f"{FIELD_LABELS[f]}: Enter a proper city or address",
            "outside_us": lambda f: f"{FIELD_LABELS[f]}: That location is outside the US. Enter a US address.",
            "state_mismatch": lambda f: f"{FIELD_LABELS[f]}: Couldn't find '{texts[f]}'. Check the city and state.",
            "not_found": lambda f: f"{FIELD_LABELS[f]} not found: {texts[f]}",
        }
        super().__init__("; ".join(messages[r](f) for f, r in reasons.items()))


class IllegalPlan(Exception):
    """The validator rejected the engine output. Never returned to the user."""


def _geocode_all(data):
    """(lat, lon, label, precision) for current, pickup, dropoff.

    With current_coords (from "Use my current location") the current location is not
    geocoded: those exact coordinates are used, labelled with the current_location text.
    """
    coords = data.get("current_coords")

    def lookup(field):
        if field == "current_location" and coords:
            return coords["lat"], coords["lon"], data[field], "exact"
        try:
            return geocode_place(data[field])
        except InvalidPlace:
            return "invalid_place"
        except OutsideUSInput:
            return "outside_us"
        except StateMismatch:
            return "state_mismatch"
        except AddressNotFound:
            return "not_found"

    with ThreadPoolExecutor(max_workers=len(LOCATION_FIELDS)) as pool:
        results = list(pool.map(lookup, LOCATION_FIELDS))
    reasons = {f: r for f, r in zip(LOCATION_FIELDS, results) if isinstance(r, str)}
    if reasons:
        raise AddressesNotFound(reasons, data)
    return results


def simplify(geometry, keep, max_points=MAX_GEOMETRY_POINTS):
    """Evenly spaced points (at most max_points), always keeping the ends and `keep` indices."""
    n = len(geometry)
    if n <= max_points:
        return [list(p) for p in geometry]
    budget = max_points - len(keep) - 1     # leave room for the kept points and the end
    stride = -(-n // budget)                # ceil
    indices = set(range(0, n, stride)) | {n - 1} | set(keep)
    return [list(geometry[i]) for i in sorted(indices)]


def _iso(dt):
    return dt.isoformat()


def _round1(x):
    return round(x, 1)


def plan(data):
    """Plan a trip from validated request data. Returns the response body as a dict."""
    places = _geocode_all(data)
    points = [p[:3] for p in places]
    try:
        route = get_route(*points)
    except UnroutablePoint as e:
        field = LOCATION_FIELDS[e.point_index]
        _, _, label, precision = places[e.point_index]
        raise AddressesNotFound({field: "no_road"}, data, {field: no_road_message(label, precision)}) from e
    except UnroutableLeg as e:
        # Highlight the leg's destination. Name the places as typed: the geocoder's match can
        # read differently (live, "Honolulu, HI" resolves to "Kaneohe, HI").
        start, end = LOCATION_FIELDS[e.leg_index], LOCATION_FIELDS[e.leg_index + 1]
        message = (f"No truck route from {data[start].strip()} to {data[end].strip()}. "
                   "Is there a road connection?")
        raise AddressesNotFound({end: "no_route"}, data, {end: message}) from e
    cycle_used = data["current_cycle_used"]
    start = data["start_time"]

    events = plan_trip(route.legs, cycle_used, start)
    violations = validate_trip(events, cycle_used, route.legs)
    if violations:
        logger.error("HOS validator rejected a plan (%d violations): %s",
                     len(violations), violations)
        raise IllegalPlan(violations)

    names = name_stops(events, route)
    log = build_logs(events, names, route.legs, cycle_used, start)

    leg0_miles = route.legs[0].distance_miles
    stops = []
    for e, name in zip(events, names):
        if e.type == "drive":
            continue
        lat, lon = locate(route, e.leg_index, e.start_miles)
        stops.append({
            "type": e.type,
            "status": e.status,
            "name": name,
            "lat": lat,
            "lon": lon,
            "leg_index": e.leg_index,
            "trip_miles": _round1(e.start_miles + (leg0_miles if e.leg_index == 1 else 0)),
            "start": _iso(e.start),
            "end": _iso(e.end),
            "duration_min": int((e.end - e.start).total_seconds() // 60),
        })

    return {
        "summary": {
            "total_miles": _round1(log.total_miles),
            "days": log.days,
            "cycle_after_min": log.cycle_after_min,
            "available_tomorrow_min": max(0, CYCLE_LIMIT_MIN - log.cycle_after_min),
            "restart_needed": log.cycle_after_min >= CYCLE_LIMIT_MIN,
        },
        "waypoints": [
            {"role": role, "label": label, "lat": lat, "lon": lon, "precision": precision}
            for role, (lat, lon, label, precision) in zip(("current", "pickup", "dropoff"), places)
        ],
        "geometry": simplify(route.geometry, keep=route.leg_bounds),
        "stops": stops,
        "directions": [
            {
                "from": leg.start_name,
                "to": leg.end_name,
                "distance_miles": _round1(leg.distance_miles),
                "duration_min": round(leg.drive_hours * 60),
                "steps": [
                    {"instruction": s.instruction, "name": s.name,
                     "distance_miles": round(s.distance_miles, 2),
                     "duration_min": _round1(s.duration_min)}
                    for s in steps
                ],
            }
            for leg, steps in zip(route.legs, route.steps)
        ],
        "sheets": [
            {
                "date": sheet.date.isoformat(),
                "from": sheet.from_location,
                "to": sheet.to_location,
                "miles": _round1(sheet.miles),
                "segments": [{"status": s.status, "start_min": s.start_min, "end_min": s.end_min}
                             for s in sheet.segments],
                "totals": sheet.totals,
                "remarks": [{"minute": r.minute, "time": f"{r.minute // 60:02d}:{r.minute % 60:02d}",
                             "location": r.location, "description": r.description}
                            for r in sheet.remarks],
                "recap": {"on_duty_today": sheet.recap.on_duty_today, "a": sheet.recap.a,
                          "b": sheet.recap.b, "c": sheet.recap.c},
            }
            for sheet in log.sheets
        ],
        "notices": same_location_notices(places),
        "details": data["details"],
    }
