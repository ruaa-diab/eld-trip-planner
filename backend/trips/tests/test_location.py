"""'Use my current location' (GET /api/reverse, plan-trip current_coords) and match precision.
All HTTP is mocked."""

from unittest import mock

import requests
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from trips.services import routing
from trips.tests.test_api import FakeORS, ok, payload, state_of, status

KEY = "secret-test-key-123"
CHICAGO_SPOT = (41.8102, -87.7133)


def reverse_hit(label, layer="address", country_a="USA"):
    return ok({"features": [{"properties": {"label": label, "layer": layer, "country_a": country_a}}]})


EMPTY = ok({"features": []})


@override_settings(ORS_API_KEY=KEY)
@mock.patch.object(routing.requests, "request")
class ReverseEndpointTest(SimpleTestCase):

    def setUp(self):
        self.client = APIClient()

    def get(self, **params):
        return self.client.get("/api/reverse", params)

    def by_layers(self, req, address, coarse):
        """Answer the address/street call and the locality/county call separately."""
        req.side_effect = lambda method, url, params, **kw: address if params["layers"] == "address,street" else coarse

    def test_nearest_address_with_short_label(self, req):
        self.by_layers(req, reverse_hit("4551 South Drake Avenue, Near South Side, Chicago, IL, USA"), EMPTY)
        resp = self.get(lat=CHICAGO_SPOT[0], lon=CHICAGO_SPOT[1])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {
            "label": "4551 South Drake Avenue, Near South Side, Chicago, IL",
            "lat": CHICAGO_SPOT[0], "lon": CHICAGO_SPOT[1],
        })
        self.assertEqual(req.call_count, 1)
        method, url = req.call_args.args
        self.assertEqual((method, url), ("GET", "https://api.heigit.org/pelias/v1/reverse"))
        self.assertEqual(req.call_args.kwargs["params"], {
            "point.lat": CHICAGO_SPOT[0], "point.lon": CHICAGO_SPOT[1], "size": 1, "layers": "address,street",
        })

    def test_rural_position_falls_back_to_city_or_county(self, req):
        # Live: a point on I-80 in Nebraska has no address nearby; the coarse lookup gives "Logan, NE".
        self.by_layers(req, EMPTY, reverse_hit("Logan, NE, USA", layer="locality"))
        resp = self.get(lat=41.1157, lon=-101.5339)
        self.assertEqual(resp.json()["label"], "Logan, NE")
        self.assertEqual(req.call_count, 2)

    def test_outside_us_is_422(self, req):
        self.by_layers(req, reverse_hit("100 Queen Street West, Toronto, ON, Canada", country_a="CAN"), EMPTY)
        resp = self.get(lat=43.6532, lon=-79.3832)
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["error"], {
            "code": "outside_us", "message": "Your location is outside the US. Enter a US address.",
        })

    def test_nothing_found_is_422(self, req):
        self.by_layers(req, EMPTY, EMPTY)
        resp = self.get(lat=30.0, lon=-60.0)    # open Atlantic
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["error"]["code"], "no_address")

    def test_invalid_coordinates_are_400_without_calling(self, req):
        cases = [{}, {"lat": 41.8}, {"lat": "abc", "lon": -87.7}, {"lat": 91, "lon": 0},
                 {"lat": 0, "lon": -181}, {"lat": "nan", "lon": 0}, {"lat": 0, "lon": "inf"}]
        for params in cases:
            with self.subTest(params=params):
                resp = self.get(**params)
                self.assertEqual(resp.status_code, 400)
                self.assertEqual(resp.json()["error"]["code"], "invalid_input")
        req.assert_not_called()

    def test_service_errors(self, req):
        for code, expected in ((429, 503), (503, 503)):
            with self.subTest(code=code):
                req.side_effect = None
                req.return_value = status(code, {"error": "x"})
                self.assertEqual(self.get(lat=41.8, lon=-87.7).status_code, expected)
        req.return_value = status(403, {"error": "Access to this API has been disallowed"})
        with self.assertLogs("trips.views", "ERROR"):
            resp = self.get(lat=41.8, lon=-87.7)
        self.assertEqual(resp.status_code, 500)
        self.assertNotIn(KEY, resp.content.decode())
        req.side_effect = requests.Timeout()
        self.assertEqual(self.get(lat=41.8, lon=-87.7).status_code, 503)

    def test_only_get_allowed(self, req):
        self.assertEqual(self.client.post("/api/reverse", {"lat": 41.8, "lon": -87.7}).status_code, 405)


@override_settings(ORS_API_KEY=KEY)
class PlanFromDevicePositionTest(SimpleTestCase):

    def setUp(self):
        self.client = APIClient()
        self.fake = FakeORS()
        patcher = mock.patch.object(routing.requests, "request", side_effect=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def post(self, body):
        return self.client.post("/api/plan-trip", body, format="json")

    def test_current_coords_are_used_exactly_and_not_geocoded(self):
        label = "4551 South Drake Avenue, Near South Side, Chicago, IL"
        resp = self.post(payload(current_location=label,
                                 current_coords={"lat": CHICAGO_SPOT[0], "lon": CHICAGO_SPOT[1]}))
        self.assertEqual(resp.status_code, 200, resp.content)
        start = resp.json()["waypoints"][0]
        self.assertEqual(start, {"role": "current", "label": label, "lat": CHICAGO_SPOT[0],
                                 "lon": CHICAGO_SPOT[1], "precision": "exact"})
        searches = [c for c in self.fake.calls if c.endswith("/pelias/v1/search")]
        self.assertEqual(len(searches), 2)    # pickup and dropoff only

    def test_out_of_range_coords_are_rejected(self):
        for coords in ({"lat": 95, "lon": 0}, {"lat": 0, "lon": 200}, {"lat": 41.8}, {"lat": "x", "lon": 1}):
            with self.subTest(coords=coords):
                resp = self.post(payload(current_coords=coords))
                self.assertEqual(resp.status_code, 400)
                self.assertIn("current_coords", resp.json()["error"]["fields"])

    def test_without_coords_current_location_is_geocoded(self):
        resp = self.post(payload())
        self.assertEqual(resp.status_code, 200)
        searches = [c for c in self.fake.calls if c.endswith("/pelias/v1/search")]
        self.assertEqual(len(searches), 3)


@override_settings(ORS_API_KEY=KEY)
class WaypointPrecisionTest(SimpleTestCase):
    """The API tells the UI how precise each location is."""

    def setUp(self):
        self.client = APIClient()
        self.fake = FakeORS()
        patcher = mock.patch.object(routing.requests, "request", side_effect=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def search_hit(self, text, layer, **props):
        self.fake.search[text] = ok({"features": [{
            "geometry": {"coordinates": [-87.7, 41.8]},
            "properties": {"label": f"{text}, USA", "layer": layer, "confidence": 1, "region_a": state_of(text), **props},
        }]})

    def test_precision_by_match_level(self):
        self.search_hit("4400 S Pulaski Rd, Chicago, IL", "address")
        self.search_hit("Cook County, IL", "county")
        self.fake.search["60632"] = ok({"features": [{
            "geometry": {"coordinates": [-87.72, 41.81]},
            "properties": {"label": "60632, Chicago, IL, USA", "postalcode": "60632", "layer": "postalcode",
                           "confidence": 1, "locality": "Chicago", "region_a": "IL"},
        }]})
        cases = [
            ("4400 S Pulaski Rd, Chicago, IL", "exact"),
            ("Chicago, IL", "city"),          # FakeORS default: locality
            ("Cook County, IL", "county"),
            ("60632", "zip"),
        ]
        for text, precision in cases:
            with self.subTest(text=text):
                resp = self.client.post("/api/plan-trip", payload(current_location=text), format="json")
                self.assertEqual(resp.status_code, 200, resp.content)
                self.assertEqual(resp.json()["waypoints"][0]["precision"], precision)
