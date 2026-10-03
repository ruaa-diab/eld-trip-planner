"""Routing service tests. All HTTP is mocked; no real API calls (they use up the quota)."""

from unittest import mock

import requests
from django.test import SimpleTestCase, override_settings

from trips.services import routing
from trips.services.routing import (
    AddressNotFound, ApiKeyError, InvalidPlace, NoRouteFound, QuotaExceeded, RoutingError,
    ServiceUnavailable, geocode, get_route, is_zip,
)

CHICAGO = (41.88, -87.63, "Chicago, IL")
ROCKFORD = (42.27, -89.09, "Rockford, IL")
DENVER = (39.74, -104.99, "Denver, CO")


def response(status=200, body=None, text=""):
    resp = mock.Mock(status_code=status, text=text)
    if body is None:
        resp.json.side_effect = ValueError("no json")
    else:
        resp.json.return_value = body
    return resp


def state_of(label):
    """Pelias region_a for a fake result: the last part of "City, ST[, USA]"."""
    parts = [p.strip() for p in label.split(",") if p.strip() and p.strip() != "USA"]
    return parts[-1] if len(parts) > 1 else None


def geocode_body(*features):
    return {"type": "FeatureCollection", "features": [
        {"geometry": {"type": "Point", "coordinates": [lon, lat]},
         "properties": {"label": label, "layer": "locality", "confidence": 1, "region_a": state_of(label)}}
        for lat, lon, label in features
    ]}


def step(instruction, name, miles, seconds):
    return {"instruction": instruction, "name": name, "distance": miles, "duration": seconds}


ROUTE_BODY = {"type": "FeatureCollection", "features": [{
    "geometry": {"type": "LineString", "coordinates": [
        [-87.63, 41.88], [-88.5, 42.1], [-89.09, 42.27], [-97.0, 41.0], [-104.99, 39.74],
    ]},
    "properties": {"way_points": [0, 2, 4], "segments": [
        {"distance": 89.4, "duration": 5400.0, "steps": [
            step("Head west on Madison Street", "Madison Street", 0.5, 90.0),
            step("Arrive at Rockford", "-", 0.0, 0.0),
        ]},
        {"distance": 950.2, "duration": 54000.0, "steps": [
            step("Turn left onto I-80 W", "I-80 W", 900.0, 51000.0),
        ]},
    ]},
}]}


@override_settings(ORS_API_KEY="test-key")
@mock.patch.object(routing.requests, "request")
class GeocodeTest(SimpleTestCase):

    def test_returns_lat_lon_label_of_first_match(self, req):
        pelias_label = (41.88, -87.63, "Chicago, IL, USA")
        req.return_value = response(body=geocode_body(pelias_label, DENVER))
        self.assertEqual(geocode("  Chicago, IL "), CHICAGO)     # ", USA" stripped

        method, url = req.call_args.args
        kwargs = req.call_args.kwargs
        self.assertEqual((method, url), ("GET", "https://api.heigit.org/pelias/v1/search"))
        self.assertEqual(kwargs["params"],
                         {"text": "Chicago, IL", "size": 1, "boundary.country": "US"})
        self.assertEqual(kwargs["headers"], {"Authorization": "test-key"})
        self.assertIn("timeout", kwargs)

    def test_no_match_raises_address_not_found(self, req):
        req.return_value = response(body=geocode_body())
        with self.assertRaisesRegex(AddressNotFound, "Nowhereville"):
            geocode("Nowhereville")

    def test_blank_text_raises_without_calling_api(self, req):
        with self.assertRaises(AddressNotFound):
            geocode("   ")
        req.assert_not_called()

    @override_settings(ORS_API_KEY="")
    def test_missing_key_raises_without_calling_api(self, req):
        with self.assertRaisesRegex(ApiKeyError, "missing"):
            geocode("Chicago, IL")
        req.assert_not_called()

    def test_rejected_key_raises_api_key_error(self, req):
        for status in (401, 403):
            with self.subTest(status=status):
                req.return_value = response(status, {"error": "Access to this API has been disallowed"})
                with self.assertRaisesRegex(ApiKeyError, "rejected"):
                    geocode("Chicago, IL")

    def test_429_raises_quota_exceeded(self, req):
        req.return_value = response(429, {"error": "Rate limit exceeded"})
        with self.assertRaises(QuotaExceeded):
            geocode("Chicago, IL")


def pelias(layer, confidence=1, label="Somewhere, IL, USA"):
    return response(body={"features": [{
        "geometry": {"type": "Point", "coordinates": [-89.0, 42.0]},
        "properties": {"label": label, "layer": layer, "confidence": confidence, "region_a": state_of(label)},
    }]})


@override_settings(ORS_API_KEY="test-key")
@mock.patch.object(routing.requests, "request")
class GeocodeQualityTest(SimpleTestCase):
    """Never guess: weak matches and non-place types are rejected."""

    def test_accepts_cities_counties_addresses_streets_and_venues(self, req):
        for layer in ("locality", "county", "address", "street", "venue"):
            with self.subTest(layer=layer):
                req.return_value = pelias(layer)
                self.assertEqual(geocode("Somewhere")[2], "Somewhere, IL")

    def test_rejects_other_place_types(self, req):
        for layer in ("region", "macroregion", "country", "postalcode", "localadmin", "neighbourhood", None):
            with self.subTest(layer=layer):
                req.return_value = pelias(layer)
                with self.assertRaisesRegex(InvalidPlace, "Enter a proper city or address"):
                    geocode("Somewhere")

    def test_low_confidence_is_not_found(self, req):
        req.return_value = pelias("region", confidence=0.3, label="Illinois, USA")
        with self.assertRaises(AddressNotFound) as ctx:
            geocode("Chicgo, IL")
        self.assertNotIsInstance(ctx.exception, InvalidPlace)

    def test_fallback_city_at_0_6_is_accepted(self, req):
        # Live Pelias returns "Denver, CO" as a fallback locality with confidence 0.6.
        req.return_value = pelias("locality", confidence=0.6, label="Denver, CO, USA")
        self.assertEqual(geocode("Denver, CO")[2], "Denver, CO")

    def test_threshold_boundary(self, req):
        req.return_value = pelias("locality", confidence=0.5)
        geocode("Somewhere")                                   # 0.5 is accepted
        req.return_value = pelias("locality", confidence=0.49)
        with self.assertRaises(AddressNotFound):
            geocode("Somewhere")


def postal(code, locality="Chicago", region_a="IL", confidence=1, layer="postalcode"):
    props = {"label": f"{code}, USA", "name": code, "postalcode": code, "layer": layer,
             "confidence": confidence, "region_a": region_a}
    if locality:
        props["locality"] = locality
    return response(body={"features": [{"geometry": {"coordinates": [-87.72, 41.81]}, "properties": props}]})


class IsZipTest(SimpleTestCase):

    def test_only_5_digits_or_zip_plus_4(self):
        for text in ("60632", " 60632 ", "60632-1234", "00501"):
            with self.subTest(text=text):
                self.assertTrue(is_zip(text))
        for text in ("6063", "606321", "60632-12", "606321234", "60632 1234", "60632-", "6063A", "", None):
            with self.subTest(text=text):
                self.assertFalse(is_zip(text))


@override_settings(ORS_API_KEY="test-key")
@mock.patch.object(routing.requests, "request")
class GeocodeZipTest(SimpleTestCase):

    def test_zip_with_city_is_labelled_with_city(self, req):
        # No brackets in the label; the UI adds "(ZIP area)".
        req.return_value = postal("60632")
        self.assertEqual(geocode("60632"), (41.81, -87.72, "60632, Chicago, IL"))
        self.assertEqual(req.call_args.kwargs["params"], {
            "text": "60632", "size": 1, "boundary.country": "US", "layers": "postalcode",
        })

    def test_zip_plus_4_looks_up_the_5_digit_zip(self, req):
        req.return_value = postal("60632")
        self.assertEqual(geocode("60632-1234")[2], "60632-1234, Chicago, IL")
        self.assertEqual(req.call_args.kwargs["params"]["text"], "60632")

    def test_zip_without_city_is_labelled_zip(self, req):
        # Live: 82190 (Yellowstone) has a state but no locality.
        req.return_value = postal("82190", locality=None, region_a="WY")
        self.assertEqual(geocode("82190")[2], "ZIP 82190")

    def test_unknown_or_mismatched_zip_is_not_found(self, req):
        cases = {
            "no result": response(body={"features": []}),
            "different zip": postal("60633"),
            "not a postal code": postal("60632", layer="locality"),
            "weak match": postal("60632", confidence=0.3),
        }
        for label, resp in cases.items():
            with self.subTest(label):
                req.return_value = resp
                with self.assertRaisesRegex(AddressNotFound, "ZIP code not found: 60632"):
                    geocode("60632")


@override_settings(ORS_API_KEY="test-key")
@mock.patch.object(routing.requests, "request")
class GetRouteTest(SimpleTestCase):

    def test_points_may_snap_to_roads_up_to_5_km_away(self, req):
        # ORS's default 350 m radius fails for city centers far from a road
        # (live: Corpus Christi, TX is ~2.4 km out in the bay).
        req.return_value = response(body=ROUTE_BODY)
        get_route(CHICAGO, ROCKFORD, DENVER)
        body = req.call_args.kwargs["json"]
        self.assertEqual(body["radiuses"], [5000, 5000, 5000])
        self.assertEqual(len(body["radiuses"]), len(body["coordinates"]))

    def test_builds_two_legs_geometry_and_steps(self, req):
        req.return_value = response(body=ROUTE_BODY)
        route = get_route(CHICAGO, ROCKFORD, DENVER)

        method, url = req.call_args.args
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://api.heigit.org/openrouteservice/v2/directions/driving-hgv/geojson")
        self.assertEqual(req.call_args.kwargs["json"], {
            "coordinates": [[-87.63, 41.88], [-89.09, 42.27], [-104.99, 39.74]],
            "units": "mi",
            "instructions": True,
            "radiuses": [5000, 5000, 5000],
        })

        leg0, leg1 = route.legs
        self.assertEqual((leg0.start_name, leg0.end_name), (CHICAGO[2], ROCKFORD[2]))
        self.assertEqual((leg1.start_name, leg1.end_name), (ROCKFORD[2], DENVER[2]))
        self.assertEqual(leg0.distance_miles, 89.4)
        self.assertEqual(leg0.drive_hours, 1.5)
        self.assertEqual(leg1.distance_miles, 950.2)
        self.assertEqual(leg1.drive_hours, 15.0)

        self.assertEqual(route.geometry[0], [41.88, -87.63])     # flipped to [lat, lon]
        self.assertEqual(route.geometry[-1], [39.74, -104.99])
        self.assertEqual(len(route.geometry), 5)

        self.assertEqual([len(s) for s in route.steps], [2, 1])
        first = route.steps[0][0]
        self.assertEqual(first.instruction, "Head west on Madison Street")
        self.assertEqual(first.name, "Madison Street")
        self.assertEqual(first.distance_miles, 0.5)
        self.assertEqual(first.duration_min, 1.5)
        self.assertEqual(route.steps[1][0].instruction, "Turn left onto I-80 W")
        self.assertEqual(route.waypoints, [CHICAGO, ROCKFORD, DENVER])
        self.assertEqual(route.leg_bounds, [0, 2, 4])

    def test_zero_length_segment_without_distance_or_duration(self, req):
        body = {"features": [{
            "geometry": {"coordinates": [[-87.63, 41.88], [-104.99, 39.74]]},
            "properties": {"way_points": [0, 0, 1], "segments": [
                {"steps": []},                                  # pickup at current location
                {"distance": 1000.0, "duration": 57600.0, "steps": []},
            ]},
        }]}
        req.return_value = response(body=body)
        leg0, leg1 = get_route(CHICAGO, CHICAGO, DENVER).legs
        self.assertEqual((leg0.distance_miles, leg0.drive_hours), (0.0, 0.0))
        self.assertEqual((leg1.distance_miles, leg1.drive_hours), (1000.0, 16.0))

    def test_ors_no_route_codes_raise_no_route_found(self, req):
        for status, code, fragment in [(404, 2009, "No truck route"),
                                       (404, 2010, "No road could be found"),
                                       (400, 2004, "too long")]:
            with self.subTest(code=code):
                req.return_value = response(status, {"error": {"code": code, "message": "x"}})
                with self.assertRaisesRegex(NoRouteFound, fragment):
                    get_route(CHICAGO, ROCKFORD, DENVER)

    def test_server_error_raises_service_unavailable(self, req):
        req.return_value = response(503, text="Service Unavailable")
        with self.assertRaises(ServiceUnavailable):
            get_route(CHICAGO, ROCKFORD, DENVER)

    def test_timeout_and_connection_error_raise_service_unavailable(self, req):
        for exc in (requests.Timeout(), requests.ConnectionError()):
            with self.subTest(exc=type(exc).__name__):
                req.side_effect = exc
                with self.assertRaises(ServiceUnavailable):
                    get_route(CHICAGO, ROCKFORD, DENVER)

    def test_rejected_key_and_quota_on_directions(self, req):
        req.return_value = response(403, {"error": "Access to this API has been disallowed"})
        with self.assertRaises(ApiKeyError):
            get_route(CHICAGO, ROCKFORD, DENVER)
        req.return_value = response(429, {"error": "Quota exceeded"})
        with self.assertRaises(QuotaExceeded):
            get_route(CHICAGO, ROCKFORD, DENVER)

    def test_wrong_segment_count_raises(self, req):
        body = {"features": [{"geometry": {"coordinates": []},
                              "properties": {"way_points": [0, 0], "segments": [{"distance": 1, "duration": 1}]}}]}
        req.return_value = response(body=body)
        with self.assertRaisesRegex(RoutingError, "Expected 2 route legs, got 1"):
            get_route(CHICAGO, ROCKFORD, DENVER)

    def test_malformed_response_raises(self, req):
        req.return_value = response(body={"unexpected": True})
        with self.assertRaisesRegex(RoutingError, "unexpected response"):
            get_route(CHICAGO, ROCKFORD, DENVER)
