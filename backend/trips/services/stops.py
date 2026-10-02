"""Place HOS stops on the route map and give them city names for the log remarks.

Reverse geocoding: GET https://api.heigit.org/pelias/v1/reverse (Pelias /v1/reverse).
"""

import math
from bisect import bisect_left
from concurrent.futures import ThreadPoolExecutor

from trips.services.routing import request_json

REVERSE_PATH = "/pelias/v1/reverse"
REVERSE_TIMEOUT_SECONDS = 5     # names are cosmetic; don't hold the trip up
REVERSE_LAYERS = "locality,county"
MAX_WORKERS = 8
DEDUPE_DECIMALS = 4             # ~11 m

NAMED_STOP_TYPES = {"break_30", "rest_10", "fuel", "restart_34"}
EARTH_RADIUS_MILES = 3958.8


def haversine_miles(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(h))


def _leg_points(route, leg_index):
    start, end = route.leg_bounds[leg_index], route.leg_bounds[leg_index + 1]
    return route.geometry[start:end + 1]


def _leg_cum_miles(route, leg_index):
    """Cumulative haversine miles along a leg's geometry; computed once per route."""
    if route.leg_cum_miles is None:
        route.leg_cum_miles = []
        for i in range(len(route.legs)):
            pts = _leg_points(route, i)
            cum = [0.0]
            for a, b in zip(pts, pts[1:]):
                cum.append(cum[-1] + haversine_miles(a, b))
            route.leg_cum_miles.append(cum)
    return route.leg_cum_miles[leg_index]


def locate(route, leg_index, miles_from_leg_start):
    """(lat, lon) of the point miles_from_leg_start road miles into the given leg.

    Engine miles are ORS road miles; the polyline's haversine length is a bit shorter,
    so the target is scaled to the geometry. The leg's full distance lands on its end point.
    """
    pts = _leg_points(route, leg_index)
    cum = _leg_cum_miles(route, leg_index)
    leg_miles = route.legs[leg_index].distance_miles
    if leg_miles <= 0 or cum[-1] == 0:
        return tuple(pts[0])

    fraction = min(max(miles_from_leg_start, 0.0), leg_miles) / leg_miles
    target = fraction * cum[-1]
    j = bisect_left(cum, target)
    if j == 0:
        return tuple(pts[0])
    span = cum[j] - cum[j - 1]
    t = (target - cum[j - 1]) / span if span else 0.0
    (lat_a, lon_a), (lat_b, lon_b) = pts[j - 1][:2], pts[j][:2]
    return (lat_a + t * (lat_b - lat_a), lon_a + t * (lon_b - lon_a))


def city_name(lat, lon, fallback):
    """"City, ST" for a point; returns fallback on any failure. Never raises."""
    try:
        data = request_json("GET", REVERSE_PATH, timeout=REVERSE_TIMEOUT_SECONDS, params={
            "point.lat": lat,
            "point.lon": lon,
            "size": 1,
            "layers": REVERSE_LAYERS,
            "boundary.country": "US",
        })
        props = data["features"][0]["properties"]
        place = props.get("locality") or props.get("county")
        if place:
            region = props.get("region_a")
            return f"{place}, {region}" if region else place
    except Exception:
        pass
    return fallback


def _route_position(route, event):
    """Fallback name: "<miles> mi past <leg start label>"."""
    label = route.legs[event.leg_index].start_name
    if label.endswith(", USA"):
        label = label[:-len(", USA")]
    return f"{round(event.start_miles)} mi past {label}"


def name_stops(events, route):
    """One name per event (None for drive events), in event order.

    Pickup/dropoff use the leg labels. Other stops are reverse geocoded in parallel,
    one call per distinct point.
    """
    names = [None] * len(events)
    point_of = {}       # event index -> dedupe key
    lookups = {}        # dedupe key -> (lat, lon, fallback)

    for i, e in enumerate(events):
        if e.type in ("pickup", "dropoff"):
            names[i] = route.legs[e.leg_index].end_name
        elif e.type in NAMED_STOP_TYPES:
            lat, lon = locate(route, e.leg_index, e.start_miles)
            key = (round(lat, DEDUPE_DECIMALS), round(lon, DEDUPE_DECIMALS))
            point_of[i] = key
            lookups.setdefault(key, (lat, lon, _route_position(route, e)))

    if lookups:
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(lookups))) as pool:
            resolved = dict(zip(lookups, pool.map(lambda args: city_name(*args),
                                                  lookups.values())))
        for i, key in point_of.items():
            names[i] = resolved[key]
    return names
