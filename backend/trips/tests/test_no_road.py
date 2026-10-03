"""No truck road near a location: name the field and the place. All HTTP is mocked."""

from unittest import mock

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from trips.services import routing
from trips.services.routing import NoRouteFound, UnroutablePoint, get_route
from trips.tests.test_api import FakeORS, ok, payload, route_body, status
from trips.tests.test_routing import (
    CHICAGO,
    DENVER,
    ROCKFORD,
    ROUTE_BODY,
    leg_of,
    per_leg,
    response,
)

LEG_STARTS = {(-87.63, 41.88): 0, (-89.09, 42.27): 1}     # test_routing points: leg index by start


def no_road_at(leg, coordinate, fallback):
    """Mock side_effect: ORS 2010 for one coordinate (0 start, 1 end) of one leg."""
    message = (f"Could not find routable point within a radius of 5000.0 meters of "
               f"specified coordinate {coordinate}: -118.1894750 34.3444170.")

    def answer(method, url, json, **kwargs):
        if LEG_STARTS.get(tuple(json["coordinates"][0])) == leg:
            return response(404, {"error": {"code": 2010, "message": message}})
        return fallback(method, url, json, **kwargs)
    return answer


@override_settings(ORS_API_KEY="test-key")
@mock.patch.object(routing.requests, "request")
class UnroutablePointTest(SimpleTestCase):

    def test_ors_coordinate_maps_to_the_trip_location(self, req):
        # (leg, coordinate in that leg's request) -> 0 current, 1 pickup, 2 dropoff
        cases = {(0, 0): 0, (0, 1): 1, (1, 0): 1, (1, 1): 2}
        for (leg, coordinate), point in cases.items():
            with self.subTest(leg=leg, coordinate=coordinate):
                req.side_effect = no_road_at(leg, coordinate, per_leg(ROUTE_BODY))
                with self.assertRaises(UnroutablePoint) as ctx:
                    get_route(CHICAGO, ROCKFORD, DENVER)
                self.assertEqual(ctx.exception.point_index, point)

    def test_2010_without_a_coordinate_stays_a_general_no_route(self, req):
        req.side_effect = None
        req.return_value = response(404, {"error": {"code": 2010, "message": "x"}})
        with self.assertRaises(NoRouteFound) as ctx:
            get_route(CHICAGO, ROCKFORD, DENVER)
        self.assertNotIsInstance(ctx.exception, UnroutablePoint)


class FakeORSWithDirections(FakeORS):
    """FakeORS whose directions answer can depend on the request (directions_fn)."""

    directions_fn = None

    def __call__(self, method, url, **kwargs):
        if "/directions/" in url and self.directions_fn:
            self.calls.append(url)
            return self.directions_fn(kwargs["json"])
        return super().__call__(method, url, **kwargs)


# Live: "Los Angeles County, CA" resolves to a point in the mountains, >5 km from a truck road.
LA_COUNTY = (34.344417, -118.189475)


@override_settings(ORS_API_KEY="test-key")
class NoRoadApiTest(SimpleTestCase):

    def setUp(self):
        self.client = APIClient()
        self.fake = FakeORSWithDirections()
        patcher = mock.patch.object(routing.requests, "request", side_effect=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def unreachable(self, lat, lon):
        """ORS answers 2010 for whichever request contains (lat, lon), naming its coordinate."""
        def answer(request_json):
            for i, (x, y) in enumerate(request_json["coordinates"]):
                if (round(y, 6), round(x, 6)) == (lat, lon):
                    message = (f"Could not find routable point within a radius of 5000.0 meters "
                               f"of specified coordinate {i}: {x} {y}.")
                    return status(404, {"error": {"code": 2010, "message": message}})
            return ok(leg_of(route_body(), request_json))     # the other leg routes normally
        return answer

    def post(self, **fields):
        return self.client.post("/api/plan-trip", payload(**fields), format="json")

    def test_county_center_without_a_road_names_the_field_and_county(self):
        self.fake.search["Los Angeles County, CA"] = ok({"features": [{
            "geometry": {"coordinates": [LA_COUNTY[1], LA_COUNTY[0]]},
            "properties": {
                "label": "Los Angeles County, CA, USA", "layer": "county", "confidence": 1, "region_a": "CA",
            },
        }]})
        self.fake.directions_fn = self.unreachable(*LA_COUNTY)
        resp = self.post(pickup_location="Los Angeles County, CA")
        self.assertEqual(resp.status_code, 400)
        error = resp.json()["error"]
        self.assertEqual(error["code"], "address_not_found")
        self.assertEqual(error["fields"], ["pickup_location"])
        self.assertEqual(error["reasons"], {"pickup_location": "no_road"})
        self.assertEqual(error["messages"], {"pickup_location":
            "No road near Los Angeles County, CA. Please be more specific: enter a city or address in the county."})

    def test_other_match_without_a_road_asks_for_a_nearby_address(self):
        spot = (39.2, -106.9)
        self.fake.search["Snowmass Peak, CO"] = ok({"features": [{
            "geometry": {"coordinates": [spot[1], spot[0]]},
            "properties": {"label": "Snowmass Peak, CO, USA", "layer": "venue", "confidence": 1, "region_a": "CO"},
        }]})
        self.fake.directions_fn = self.unreachable(*spot)
        resp = self.post(dropoff_location="Snowmass Peak, CO")
        error = resp.json()["error"]
        self.assertEqual(error["fields"], ["dropoff_location"])
        self.assertEqual(error["messages"], {"dropoff_location":
            "No road near Snowmass Peak, CO. Please be more specific: try a nearby address."})

    def no_connection_to(self, lat, lon):
        """ORS 2009 for the leg that ends at (lat, lon); other legs route normally."""
        def answer(request_json):
            x, y = request_json["coordinates"][1]
            if (round(y, 6), round(x, 6)) == (lat, lon):
                return status(404, {"error": {"code": 2009, "message":
                    "Route could not be found - Unable to find a route between points 1 and 2."}})
            return ok(leg_of(route_body(), request_json))
        return answer

    def test_leg_without_a_road_connection_names_the_leg_and_its_destination(self):
        # Live: Denver, CO -> Honolulu, HI is ORS 2009. Pelias resolves "Honolulu, HI" to
        # "Kaneohe, HI", so the message uses the typed text.
        honolulu = (21.40572, -157.789396)
        self.fake.search["Honolulu, HI"] = ok({"features": [{
            "geometry": {"coordinates": [honolulu[1], honolulu[0]]},
            "properties": {"label": "Kaneohe, HI, USA", "layer": "locality", "confidence": 1, "region_a": "HI"},
        }]})
        self.fake.directions_fn = self.no_connection_to(*honolulu)
        resp = self.post(pickup_location="Denver, CO", dropoff_location="Honolulu, HI")
        self.assertEqual(resp.status_code, 400)
        error = resp.json()["error"]
        self.assertEqual(error["code"], "address_not_found")
        self.assertEqual(error["fields"], ["dropoff_location"])
        self.assertEqual(error["reasons"], {"dropoff_location": "no_route"})
        self.assertEqual(error["messages"], {"dropoff_location":
            "No truck route from Denver, CO to Honolulu, HI. Is there a road connection?"})

    def test_first_leg_without_a_connection_highlights_the_pickup(self):
        honolulu = (21.40572, -157.789396)
        self.fake.search["Honolulu, HI"] = ok({"features": [{
            "geometry": {"coordinates": [honolulu[1], honolulu[0]]},
            "properties": {"label": "Kaneohe, HI, USA", "layer": "locality", "confidence": 1, "region_a": "HI"},
        }]})
        self.fake.directions_fn = self.no_connection_to(*honolulu)
        resp = self.post(current_location="Chicago, IL", pickup_location="Honolulu, HI")
        error = resp.json()["error"]
        self.assertEqual(error["fields"], ["pickup_location"])
        self.assertEqual(error["messages"], {"pickup_location":
            "No truck route from Chicago, IL to Honolulu, HI. Is there a road connection?"})

    def test_other_no_route_errors_stay_a_general_422(self):
        self.fake.directions_fn = lambda request_json: status(400, {"error": {"code": 2004, "message": "too long"}})
        resp = self.post()
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["error"]["code"], "no_route")

    def test_other_address_errors_have_no_messages_field(self):
        resp = self.post(pickup_location="Nowhereville")
        self.assertNotIn("messages", resp.json()["error"])
