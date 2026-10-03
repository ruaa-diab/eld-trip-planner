"""Stop placement and naming tests. HTTP is mocked; locate() tests are pure geometry."""

from datetime import datetime
from unittest import mock

import requests
from django.test import SimpleTestCase, override_settings

from trips.hos.engine import Event, Leg
from trips.services import routing
from trips.services.routing import Route
from trips.services.stops import city_name, haversine_miles, locate, name_stops

CHICAGO = (0.0, 0.0, "Chicago, IL")
ROCKFORD = (1.0, 0.0, "Rockford, IL")
DENVER = (3.0, 0.0, "Denver, CO")
DEG = haversine_miles((0, 0), (1, 0))     # one degree of latitude ≈ 69.09 mi
T = datetime(2026, 1, 5, 6)


def straight_route(leg0_miles=DEG, leg1_miles=2 * DEG, bounds=(0, 1, 3)):
    """Due-north line (0,0)→(3,0); leg 0 = geometry[0..1], leg 1 = geometry[1..3]."""
    return Route(
        legs=[Leg(CHICAGO[2], ROCKFORD[2], leg0_miles, 1.0),
              Leg(ROCKFORD[2], DENVER[2], leg1_miles, 2.0)],
        geometry=[[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [3.0, 0.0]],
        steps=[[], []],
        waypoints=[CHICAGO, ROCKFORD, DENVER],
        leg_bounds=list(bounds),
    )


def event(type_, leg_index, miles, status="off_duty"):
    return Event(status, type_, T, T, leg_index, miles, miles)


def drive(leg_index, start, end):
    return Event("driving", "drive", T, T, leg_index, start, end)


class LocateTest(SimpleTestCase):

    def assertPoint(self, got, expected):
        self.assertAlmostEqual(got[0], expected[0], places=9)
        self.assertAlmostEqual(got[1], expected[1], places=9)

    def test_leg_start_end_and_boundary(self):
        r = straight_route()
        self.assertPoint(locate(r, 0, 0), (0, 0))
        self.assertPoint(locate(r, 0, DEG), (1, 0))
        self.assertPoint(locate(r, 1, 0), (1, 0))
        self.assertPoint(locate(r, 1, 2 * DEG), (3, 0))

    def test_interpolates_within_a_segment(self):
        r = straight_route()
        self.assertPoint(locate(r, 0, DEG / 2), (0.5, 0))
        self.assertPoint(locate(r, 0, DEG / 4), (0.25, 0))

    def test_second_leg_offsets_by_its_boundary(self):
        r = straight_route()
        self.assertPoint(locate(r, 1, DEG), (2, 0))
        self.assertPoint(locate(r, 1, 1.5 * DEG), (2.5, 0))

    def test_road_miles_scale_to_geometry_length(self):
        # Road distance (100 mi) is longer than the polyline (≈69 mi).
        r = straight_route(leg0_miles=100)
        self.assertPoint(locate(r, 0, 50), (0.5, 0))
        self.assertPoint(locate(r, 0, 100), (1, 0))   # full distance lands on pickup

    def test_clamps_to_the_leg(self):
        r = straight_route()
        self.assertPoint(locate(r, 0, -5), (0, 0))
        self.assertPoint(locate(r, 0, 10 * DEG), (1, 0))
        self.assertPoint(locate(r, 1, 10 * DEG), (3, 0))

    def test_zero_length_leg_returns_its_start(self):
        r = straight_route(leg0_miles=0, leg1_miles=3 * DEG, bounds=(0, 0, 3))
        self.assertPoint(locate(r, 0, 0), (0, 0))
        self.assertPoint(locate(r, 1, 1.5 * DEG), (1.5, 0))

    def test_cumulative_miles_computed_once(self):
        r = straight_route()
        locate(r, 0, 1)
        cached = r.leg_cum_miles
        self.assertEqual(len(cached), 2)
        locate(r, 1, 1)
        self.assertIs(r.leg_cum_miles, cached)


def reverse_response(**props):
    resp = mock.Mock(status_code=200)
    resp.json.return_value = {"features": [{"properties": props}] if props else []}
    return resp


@override_settings(ORS_API_KEY="test-key")
@mock.patch.object(routing.requests, "request")
class CityNameTest(SimpleTestCase):

    def test_returns_city_and_state(self, req):
        req.return_value = reverse_response(locality="Ogallala", region_a="NE", county="Keith County")
        self.assertEqual(city_name(41.13, -101.72, "fallback"), "Ogallala, NE")

        method, url = req.call_args.args
        self.assertEqual((method, url), ("GET", "https://api.heigit.org/pelias/v1/reverse"))
        self.assertEqual(req.call_args.kwargs["params"], {
            "point.lat": 41.13, "point.lon": -101.72, "size": 1,
            "layers": "locality,county", "boundary.country": "US",
        })
        self.assertEqual(req.call_args.kwargs["timeout"], 5)

    def test_falls_back_to_county(self, req):
        req.return_value = reverse_response(county="Keith County", region_a="NE")
        self.assertEqual(city_name(41.0, -101.5, "fallback"), "Keith County, NE")

    def test_numeric_or_too_short_place_names_are_skipped(self, req):
        # Live bug: a stop was named "26, NE".
        for locality in ("26", "12-34", "Ab", " 7 "):
            with self.subTest(locality=locality):
                req.return_value = reverse_response(locality=locality, county="Keith County", region_a="NE")
                self.assertEqual(city_name(41.0, -101.5, "fallback"), "Keith County, NE")

    def test_unreadable_city_and_county_use_the_route_position(self, req):
        req.return_value = reverse_response(locality="26", county="9", region_a="NE")
        self.assertEqual(city_name(41.0, -101.5, "495 mi past Rockford, IL"), "495 mi past Rockford, IL")

    def test_failures_return_fallback_never_raise(self, req):
        cases = {
            "no results": dict(return_value=reverse_response()),
            "no place fields": dict(return_value=reverse_response(region_a="NE")),
            "quota": dict(return_value=mock.Mock(status_code=429, **{"json.return_value": {}})),
            "timeout": dict(side_effect=requests.Timeout()),
            "unexpected": dict(side_effect=RuntimeError("boom")),
        }
        for label, behaviour in cases.items():
            with self.subTest(label):
                req.reset_mock(return_value=True, side_effect=True)
                req.configure_mock(**behaviour)
                self.assertEqual(city_name(41.0, -101.5, "495 mi past Rockford, IL"),
                                 "495 mi past Rockford, IL")

    @override_settings(ORS_API_KEY="")
    def test_missing_key_returns_fallback_without_calling(self, req):
        self.assertEqual(city_name(41.0, -101.5, "fallback"), "fallback")
        req.assert_not_called()


@override_settings(ORS_API_KEY="test-key")
@mock.patch.object(routing.requests, "request")
class NameStopsTest(SimpleTestCase):

    EVENTS = [
        drive(0, 0, DEG),
        event("pickup", 0, DEG, "on_duty"),
        drive(1, 0, DEG),
        event("break_30", 1, DEG),                 # same point as the rest below
        event("rest_10", 1, DEG, "sleeper_berth"),
        drive(1, DEG, 1.5 * DEG),
        event("fuel", 1, 1.5 * DEG, "on_duty"),
        drive(1, 1.5 * DEG, 2 * DEG),
        event("dropoff", 1, 2 * DEG, "on_duty"),
    ]

    def test_names_only_stops_and_dedupes_points(self, req):
        def by_latitude(method, url, params, **kwargs):
            city = {2.0: "Lincoln", 2.5: "Kearney"}[round(params["point.lat"], 6)]
            return reverse_response(locality=city, region_a="NE")
        req.side_effect = by_latitude

        names = name_stops(self.EVENTS, straight_route())
        self.assertEqual(names, [
            None, "Rockford, IL", None,
            "Lincoln, NE", "Lincoln, NE", None,
            "Kearney, NE", None, "Denver, CO",
        ])
        self.assertEqual(req.call_count, 2)    # break and rest share one lookup

    def test_fallback_describes_position_on_route(self, req):
        req.return_value = mock.Mock(status_code=503, text="down",
                                     **{"json.side_effect": ValueError()})
        events = [event("restart_34", 0, 0), drive(0, 0, DEG),
                  event("pickup", 0, DEG, "on_duty"), drive(1, 0, DEG),
                  event("rest_10", 1, DEG, "sleeper_berth"), drive(1, DEG, 2 * DEG),
                  event("dropoff", 1, 2 * DEG, "on_duty")]
        names = name_stops(events, straight_route())
        self.assertEqual(names[0], "0 mi past Chicago, IL")
        self.assertEqual(names[4], "69 mi past Rockford, IL")
        self.assertEqual((names[2], names[6]), ("Rockford, IL", "Denver, CO"))

    def test_no_named_stops_makes_no_calls(self, req):
        events = [drive(0, 0, DEG), event("pickup", 0, DEG, "on_duty"),
                  drive(1, 0, 2 * DEG), event("dropoff", 1, 2 * DEG, "on_duty")]
        self.assertEqual(name_stops(events, straight_route()),
                         [None, "Rockford, IL", None, "Denver, CO"])
        req.assert_not_called()
