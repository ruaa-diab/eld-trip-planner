"""Routing service tests. All HTTP is mocked; no real API calls (they use up the quota)."""

from unittest import mock

import requests
from django.test import SimpleTestCase, override_settings

from trips.services import routing
from trips.services.routing import (
    AddressNotFound, ApiKeyError, NoRouteFound, QuotaExceeded, RoutingError,
    ServiceUnavailable, geocode, get_route,
)

CHICAGO = (41.88, -87.63, "Chicago, IL, USA")
ROCKFORD = (42.27, -89.09, "Rockford, IL, USA")
DENVER = (39.74, -104.99, "Denver, CO, USA")


def response(status=200, body=None, text=""):
    resp = mock.Mock(status_code=status, text=text)
    if body is None:
        resp.json.side_effect = ValueError("no json")
    else:
        resp.json.return_value = body
    return resp


def geocode_body(*features):
    return {"type": "FeatureCollection", "features": [
        {"geometry": {"type": "Point", "coordinates": [lon, lat]},
         "properties": {"label": label}}
        for lat, lon, label in features
    ]}


def step(instruction, name, miles, seconds):
    return {"instruction": instruction, "name": name, "distance": miles, "duration": seconds}


ROUTE_BODY = {"type": "FeatureCollection", "features": [{
    "geometry": {"type": "LineString", "coordinates": [
        [-87.63, 41.88], [-88.5, 42.1], [-89.09, 42.27], [-97.0, 41.0], [-104.99, 39.74],
    ]},
    "properties": {"segments": [
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
        req.return_value = response(body=geocode_body(CHICAGO, DENVER))
        self.assertEqual(geocode("  Chicago, IL "), CHICAGO)

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


@override_settings(ORS_API_KEY="test-key")
@mock.patch.object(routing.requests, "request")
class GetRouteTest(SimpleTestCase):

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

    def test_zero_length_segment_without_distance_or_duration(self, req):
        body = {"features": [{
            "geometry": {"coordinates": [[-87.63, 41.88], [-104.99, 39.74]]},
            "properties": {"segments": [
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
                              "properties": {"segments": [{"distance": 1, "duration": 1}]}}]}
        req.return_value = response(body=body)
        with self.assertRaisesRegex(RoutingError, "Expected 2 route legs, got 1"):
            get_route(CHICAGO, ROCKFORD, DENVER)

    def test_malformed_response_raises(self, req):
        req.return_value = response(body={"unexpected": True})
        with self.assertRaisesRegex(RoutingError, "unexpected response"):
            get_route(CHICAGO, ROCKFORD, DENVER)
