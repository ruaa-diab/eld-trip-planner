"""POST /api/plan-trip tests. All OpenRouteService HTTP is mocked by URL."""

import math
from unittest import mock

import requests
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from trips.services import routing

KEY = "secret-test-key-123"
URL = "/api/plan-trip"
PLACES = {
    "Chicago, IL": (41.88, -87.63),
    "Rockford, IL": (42.27, -89.09),
    "Denver, CO": (39.74, -104.99),
}


def line(a, b, n):
    """n points from a to b (excluding b)."""
    return [[a[1] + (b[1] - a[1]) * i / n, a[0] + (b[0] - a[0]) * i / n] for i in range(n)]


def ok(body):
    resp = mock.Mock(status_code=200)
    resp.json.return_value = body
    return resp


def status(code, body=None):
    resp = mock.Mock(status_code=code, text=str(body))
    if body is None:
        resp.json.side_effect = ValueError()
    else:
        resp.json.return_value = body
    return resp


def route_body(leg0=(110, 7200.0), leg1=(880, 57600.0)):
    """Case 1 shape: 110 mi / 2 h, 880 mi / 16 h. 3000 geometry points, ORS order [lon, lat]."""
    c, r, d = PLACES["Chicago, IL"], PLACES["Rockford, IL"], PLACES["Denver, CO"]
    coords = line(c, r, 1000) + line(r, d, 1999) + [[d[1], d[0]]]
    return {"features": [{
        "geometry": {"coordinates": coords},
        "properties": {
            "way_points": [0, 1000, 2999],
            "segments": [
                {"distance": leg0[0], "duration": leg0[1],
                 "steps": [{"instruction": "Head west", "name": "I-90", "distance": 110.0,
                            "duration": 7200.0}]},
                {"distance": leg1[0], "duration": leg1[1],
                 "steps": [{"instruction": "Turn left onto I-80 W", "name": "I-80 W",
                            "distance": 880.0, "duration": 57600.0}]},
            ],
        },
    }]}


class FakeORS:
    """Answers geocode/directions/reverse by URL; individual answers can be overridden."""

    def __init__(self, directions=None, search=None):
        self.directions = directions or ok(route_body())
        self.search = search or {}
        self.calls = []

    def __call__(self, method, url, **kwargs):
        self.calls.append(url)
        params = kwargs.get("params", {})
        if url.endswith("/pelias/v1/search"):
            text = params["text"]
            if text in self.search:
                return self.search[text]
            if text not in PLACES:
                return ok({"features": []})
            lat, lon = PLACES[text]
            return ok({"features": [{"geometry": {"coordinates": [lon, lat]},
                                     "properties": {"label": f"{text}, USA", "layer": "locality", "confidence": 1}}]})
        if url.endswith("/pelias/v1/reverse"):
            return ok({"features": [{"properties": {"county": "Test County", "region_a": "IA"}}]})
        if "/directions/" in url:
            return self.directions
        raise AssertionError(f"unexpected URL {url}")


def payload(**overrides):
    body = {
        "current_location": "Chicago, IL",
        "pickup_location": "Rockford, IL",
        "dropoff_location": "Denver, CO",
        "current_cycle_used": 20,
        "start_time": "2026-01-05T06:00",
    }
    body.update(overrides)
    return body


@override_settings(ORS_API_KEY=KEY)
class PlanTripApiTest(SimpleTestCase):

    def setUp(self):
        self.client = APIClient()
        self.fake = FakeORS()
        patcher = mock.patch.object(routing.requests, "request", side_effect=self.fake)
        self.request_mock = patcher.start()
        self.addCleanup(patcher.stop)

    def post(self, body=None):
        return self.client.post(URL, body if body is not None else payload(), format="json")

    # ── Happy path ──

    def test_full_plan_response(self):
        details = {"driver_name": "Ruaa D.", "truck_number": "T-12"}
        resp = self.post(payload(details=details))
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()

        self.assertEqual(data["summary"], {
            "total_miles": 990.0, "days": 2, "cycle_after_min": 2400,
            "available_tomorrow_min": 1800, "restart_needed": False,
        })
        self.assertEqual([w["label"] for w in data["waypoints"]],
                         ["Chicago, IL", "Rockford, IL", "Denver, CO"])
        self.assertEqual(data["waypoints"][1]["lat"], 42.27)

        self.assertLessEqual(len(data["geometry"]), 1500)
        self.assertEqual(data["geometry"][0], [41.88, -87.63])
        self.assertEqual(data["geometry"][-1], [39.74, -104.99])
        self.assertIn([42.27, -89.09], data["geometry"])      # pickup point kept

        self.assertEqual([s["type"] for s in data["stops"]],
                         ["pickup", "break_30", "rest_10", "dropoff"])
        brk = data["stops"][1]
        self.assertEqual(brk["name"], "Test County, IA")
        self.assertEqual((brk["start"], brk["end"], brk["duration_min"]),
                         ("2026-01-05T17:00:00", "2026-01-05T17:30:00", 30))
        self.assertEqual(brk["trip_miles"], 550.0)               # 110 + 440
        self.assertEqual(data["stops"][0]["name"], "Rockford, IL")
        self.assertTrue(all(-90 <= s["lat"] <= 90 and -180 <= s["lon"] <= 180
                            for s in data["stops"]))

        self.assertEqual(len(data["directions"]), 2)
        self.assertEqual(data["directions"][1]["duration_min"], 960)
        self.assertEqual(data["directions"][1]["steps"][0]["instruction"], "Turn left onto I-80 W")

        self.assertEqual(len(data["sheets"]), data["summary"]["days"])
        day1 = data["sheets"][0]
        self.assertEqual(day1["date"], "2026-01-05")
        self.assertEqual(day1["totals"], {"off_duty": 390, "sleeper_berth": 330,
                                          "driving": 660, "on_duty": 60})
        self.assertEqual(day1["remarks"][0], {"minute": 360, "time": "06:00",
                                              "location": "Chicago, IL",
                                              "description": "Reported for work"})
        for sheet in data["sheets"]:
            self.assertEqual(sum(sheet["totals"].values()), 1440)

        self.assertEqual(data["details"]["driver_name"], "Ruaa D.")
        self.assertEqual(data["details"]["truck_number"], "T-12")
        self.assertEqual(data["details"]["carrier_name"], "")

    def test_details_default_to_blank(self):
        data = self.post().json()
        self.assertEqual(set(data["details"].values()), {""})

    def test_restart_needed_when_cycle_ends_at_70(self):
        # Case 4b shape: cycle 64 h, 60 mi / 1 h, 240 mi / 4 h → ends at 71 h.
        self.fake.directions = ok(route_body((60, 3600.0), (240, 14400.0)))
        data = self.post(payload(current_cycle_used=64)).json()
        self.assertEqual(data["summary"]["cycle_after_min"], 4260)
        self.assertEqual(data["summary"]["available_tomorrow_min"], 0)
        self.assertTrue(data["summary"]["restart_needed"])

    def test_start_time_is_kept_as_entered(self):
        data = self.post(payload(start_time="2026-01-05T06:00:00")).json()
        self.assertEqual(data["stops"][0]["start"], "2026-01-05T08:00:00")   # no offset added

    # ── Input validation ──

    def test_invalid_input_returns_400_per_field(self):
        cases = {
            "missing field": ({k: v for k, v in payload().items() if k != "pickup_location"},
                              "pickup_location"),
            "blank location": (payload(dropoff_location="   "), "dropoff_location"),
            "cycle over 70": (payload(current_cycle_used=70.5), "current_cycle_used"),
            "cycle negative": (payload(current_cycle_used=-1), "current_cycle_used"),
            "cycle NaN": (payload(current_cycle_used="NaN"), "current_cycle_used"),
            "bad date": (payload(start_time="tomorrow"), "start_time"),
            "time zone given": (payload(start_time="2026-01-05T06:00:00+02:00"), "start_time"),
            "utc Z": (payload(start_time="2026-01-05T06:00:00Z"), "start_time"),
        }
        for label, (body, field) in cases.items():
            with self.subTest(label):
                resp = self.post(body)
                self.assertEqual(resp.status_code, 400)
                error = resp.json()["error"]
                self.assertEqual(error["code"], "invalid_input")
                self.assertIn(field, error["fields"])
        self.request_mock.assert_not_called()

    def test_cycle_decimals_and_70_accepted(self):
        for cycle in (20.5, 0, 70):
            with self.subTest(cycle=cycle):
                self.assertEqual(self.post(payload(current_cycle_used=cycle)).status_code, 200)

    # ── Routing errors ──

    def test_address_not_found_names_the_field(self):
        resp = self.post(payload(pickup_location="Nowhereville"))
        self.assertEqual(resp.status_code, 400)
        error = resp.json()["error"]
        self.assertEqual(error["code"], "address_not_found")
        self.assertEqual(error["fields"], ["pickup_location"])
        self.assertIn("Pickup location not found: Nowhereville", error["message"])

    def test_several_addresses_not_found_are_all_listed(self):
        resp = self.post(payload(current_location="Xxx", dropoff_location="Yyy"))
        self.assertEqual(resp.json()["error"]["fields"], ["current_location", "dropoff_location"])
        self.assertEqual(resp.json()["error"]["reasons"],
                         {"current_location": "not_found", "dropoff_location": "not_found"})

    def test_too_short_or_letterless_locations_rejected_without_geocoding(self):
        for value in ("C", "  Ab ", "123", "12-34", "", "   "):
            with self.subTest(value=value):
                resp = self.post(payload(pickup_location=value))
                self.assertEqual(resp.status_code, 400)
                error = resp.json()["error"]
                self.assertEqual(error["code"], "invalid_input")
                self.assertEqual(error["fields"]["pickup_location"], ["Enter a city or address"])
        resp = self.post({k: v for k, v in payload().items() if k != "current_location"})
        self.assertEqual(resp.json()["error"]["fields"]["current_location"], ["Enter a city or address"])
        self.request_mock.assert_not_called()

    def test_three_letters_is_enough(self):
        self.fake.search["Ccc"] = ok({"features": [{
            "geometry": {"coordinates": [-85.5, 33.6]},
            "properties": {"label": "CCC, Cleburne County, AL, USA", "layer": "venue", "confidence": 1},
        }]})
        resp = self.post(payload(current_location="Ccc"))
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_state_or_country_match_is_not_a_proper_place(self):
        for text, layer in (("Illinois", "region"), ("USA", "country"), ("Chicago 60632", "postalcode")):
            with self.subTest(layer=layer):
                self.fake.search[text] = ok({"features": [{
                    "geometry": {"coordinates": [-89.2, 40.0]},
                    "properties": {"label": f"{text}, USA", "layer": layer, "confidence": 1},
                }]})
                resp = self.post(payload(dropoff_location=text))
                self.assertEqual(resp.status_code, 400)
                error = resp.json()["error"]
                self.assertEqual(error["code"], "address_not_found")
                self.assertEqual(error["reasons"], {"dropoff_location": "invalid_place"})
                self.assertIn("Enter a proper city or address", error["message"])

    def test_weak_match_is_not_found(self):
        # A typo that Pelias falls back to the whole state with low confidence.
        self.fake.search["Chicgo, IL"] = ok({"features": [{
            "geometry": {"coordinates": [-89.2, 40.0]},
            "properties": {"label": "Illinois, USA", "layer": "region", "confidence": 0.3, "match_type": "fallback"},
        }]})
        resp = self.post(payload(current_location="Chicgo, IL"))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"]["reasons"], {"current_location": "not_found"})

    def test_no_route_returns_422(self):
        for code in (2009, 2010):
            with self.subTest(code=code):
                self.fake.directions = status(404, {"error": {"code": code, "message": "x"}})
                resp = self.post()
                self.assertEqual(resp.status_code, 422)
                self.assertEqual(resp.json()["error"]["code"], "no_route")

    def test_key_problems_return_generic_500_without_the_key(self):
        self.fake.directions = status(403, {"error": "Access to this API has been disallowed"})
        with self.assertLogs("trips.views", "ERROR"):
            resp = self.post()
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.json()["error"]["code"], "service_misconfigured")
        self.assertNotIn(KEY, resp.content.decode())

        with override_settings(ORS_API_KEY=""), self.assertLogs("trips.views", "ERROR"):
            resp = self.post()
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.json()["error"]["message"],
                         "The route service is not configured correctly.")

    def test_quota_and_outages_return_503(self):
        cases = {
            "quota": status(429, {"error": "Quota exceeded"}),
            "down": status(503),
        }
        for label, directions in cases.items():
            with self.subTest(label):
                self.fake.directions = directions
                resp = self.post()
                self.assertEqual(resp.status_code, 503)
                self.assertEqual(resp.json()["error"]["code"], "service_unavailable")

        self.request_mock.side_effect = requests.Timeout()
        resp = self.post()
        self.assertEqual(resp.status_code, 503)

    def test_unexpected_route_response_returns_502(self):
        self.fake.directions = ok({"nonsense": True})
        with self.assertLogs("trips.views", "ERROR"):
            resp = self.post()
        self.assertEqual(resp.status_code, 502)

    # ── Safety net ──

    def test_validator_violation_returns_500_and_logs(self):
        with mock.patch("trips.services.planner.validate_trip",
                        return_value=["event 3: 700 driving min this shift (limit 660)"]), \
                self.assertLogs("trips.services.planner", "ERROR") as logs:
            resp = self.post()
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.json()["error"]["code"], "internal_error")
        self.assertNotIn("sheets", resp.json())
        self.assertTrue(any("700 driving min" in line for line in logs.output))

    def test_only_post_allowed(self):
        self.assertEqual(self.client.get(URL).status_code, 405)


class SimplifyTest(SimpleTestCase):

    def test_keeps_ends_and_waypoints_under_limit(self):
        from trips.services.planner import simplify
        geometry = [[i, 0] for i in range(5651)]
        out = simplify(geometry, keep=[0, 1234, 5650])
        self.assertLessEqual(len(out), 1500)
        self.assertLessEqual(len(simplify([[i, 0] for i in range(3000)], keep=[0, 1000, 2999])),
                             1500)
        self.assertEqual(out[0], [0, 0])
        self.assertEqual(out[-1], [5650, 0])
        self.assertIn([1234, 0], out)
        self.assertEqual(simplify(geometry[:10], keep=[0, 9]), geometry[:10])
        self.assertFalse(any(math.isnan(p[0]) for p in out))
