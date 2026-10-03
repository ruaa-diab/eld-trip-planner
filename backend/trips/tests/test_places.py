"""State the user typed is never swapped, and same-location notices. All HTTP is mocked."""

from unittest import mock

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from trips.services import routing
from trips.services.planner import same_location_notices
from trips.services.regions import typed_region
from trips.services.routing import AddressNotFound, OutsideUSInput, StateMismatch, geocode
from trips.tests.test_api import FakeORS, ok, payload


def hit(label, region_a, layer="locality", lat=41.0, lon=-89.0):
    return ok({"features": [{
        "geometry": {"coordinates": [lon, lat]},
        "properties": {"label": label, "layer": layer, "confidence": 1, "region_a": region_a},
    }]})


@override_settings(ORS_API_KEY="test-key")
@mock.patch.object(routing.requests, "request")
class StateCheckTest(SimpleTestCase):

    def test_toronto_on_is_outside_us_without_calling(self, req):
        # Pelias limited to the US would answer "Toronto, OH".
        for text in ("Toronto, ON", "Toronto, Ontario", "Vancouver, BC", "Montreal, QC"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(OutsideUSInput, "That location is outside the US. Enter a US address."):
                    geocode(text)
        req.assert_not_called()

    def test_plain_toronto_is_toronto_ohio(self, req):
        req.return_value = hit("Toronto, OH, USA", "OH")
        self.assertEqual(geocode("Toronto")[2], "Toronto, OH")

    def test_matching_state_code_or_name_is_accepted(self, req):
        req.return_value = hit("Rockford, IL, USA", "IL")
        for text in ("Rockford, IL", "Rockford, Illinois", "Rockford, il", "Rockford, IL 61101", "Rockford, IL, USA"):
            with self.subTest(text=text):
                self.assertEqual(geocode(text)[2], "Rockford, IL")

    def test_unknown_state_code_is_rejected_without_calling(self, req):
        with self.assertRaisesRegex(StateMismatch, r"Couldn't find 'Springfield, XX'. Check the city and state."):
            geocode("Springfield, XX")
        req.assert_not_called()

    def test_match_in_another_state_is_rejected(self, req):
        req.return_value = hit("Rockford, IL, USA", "IL")
        with self.assertRaisesRegex(StateMismatch, r"Couldn't find 'Rockford, CA'. Check the city and state."):
            geocode("Rockford, CA")
        with self.assertRaises(StateMismatch):
            geocode("Rockford, California")

    def test_match_without_a_state_is_rejected_when_one_was_typed(self, req):
        req.return_value = hit("Somewhere, USA", None)
        with self.assertRaises(StateMismatch):
            geocode("Somewhere, IL")

    def test_address_without_state_is_not_checked(self, req):
        req.return_value = hit("4400 South Pulaski Road, Chicago, IL, USA", "IL", layer="address")
        self.assertEqual(geocode("4400 S Pulaski Rd, Chicago")[2], "4400 South Pulaski Road, Chicago, IL")

    def test_state_errors_are_address_not_found(self, req):
        self.assertTrue(issubclass(OutsideUSInput, AddressNotFound))
        self.assertTrue(issubclass(StateMismatch, AddressNotFound))


class TypedRegionTest(SimpleTestCase):

    def test_parsing(self):
        cases = {
            "Toronto, ON": ("non_us", "ON"),
            "Toronto, Ontario": ("non_us", "ON"),
            "Rockford, IL": ("us", "IL"),
            "Rockford, Illinois": ("us", "IL"),
            "Chicago, IL 60632": ("us", "IL"),
            "Chicago, IL, USA": ("us", "IL"),
            "New York, New York": ("us", "NY"),
            "Springfield, XX": ("unknown_code", "XX"),
            "Toronto": None,
            "4400 S Pulaski Rd, Chicago": None,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(typed_region(text), expected)


@override_settings(ORS_API_KEY="test-key")
class StateCheckApiTest(SimpleTestCase):

    def setUp(self):
        self.client = APIClient()
        self.fake = FakeORS()
        patcher = mock.patch.object(routing.requests, "request", side_effect=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_reasons_and_messages(self):
        self.fake.search["Rockford, CA"] = hit("Rockford, IL, USA", "IL")
        resp = self.client.post("/api/plan-trip", payload(
            current_location="Toronto, ON", pickup_location="Rockford, CA"), format="json")
        self.assertEqual(resp.status_code, 400)
        error = resp.json()["error"]
        self.assertEqual(error["code"], "address_not_found")
        self.assertEqual(error["reasons"], {"current_location": "outside_us", "pickup_location": "state_mismatch"})
        self.assertIn("That location is outside the US. Enter a US address.", error["message"])
        self.assertIn("Couldn't find 'Rockford, CA'. Check the city and state.", error["message"])

    def test_rockford_illinois_plans(self):
        self.fake.search["Rockford, Illinois"] = hit("Rockford, IL, USA", "IL", lat=42.27, lon=-89.09)
        resp = self.client.post("/api/plan-trip", payload(pickup_location="Rockford, Illinois"), format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["waypoints"][1]["label"], "Rockford, IL")


# Resolved points: aliases ~0.03 mi apart are the same place; "Denver Union Station" is ~0.2 mi away.
SPOTS = {
    "Chicago Loop, IL": (41.8804, -87.6300, "IL"),
    "Chicago Center, IL": (41.8802, -87.6301, "IL"),
    "Denver Downtown, CO": (39.7404, -104.9900, "CO"),
    "Denver Union Station, CO": (39.7430, -104.9900, "CO"),
}


@override_settings(ORS_API_KEY="test-key")
class SameLocationNoticeTest(SimpleTestCase):

    def setUp(self):
        self.client = APIClient()
        self.fake = FakeORS()
        for text, (lat, lon, state) in SPOTS.items():
            self.fake.search[text] = hit(f"{text}, USA", state, lat=lat, lon=lon)
        patcher = mock.patch.object(routing.requests, "request", side_effect=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def notices(self, current, pickup, dropoff):
        resp = self.client.post("/api/plan-trip", payload(
            current_location=current, pickup_location=pickup, dropoff_location=dropoff), format="json")
        self.assertEqual(resp.status_code, 200, resp.content)    # never blocked
        return resp.json()["notices"]

    def test_all_different_has_no_notice(self):
        self.assertEqual(self.notices("Chicago, IL", "Rockford, IL", "Denver, CO"), [])

    def test_current_same_as_pickup_has_no_notice(self):
        # "Chicago, IL" resolves to 41.88,-87.63; the Loop alias is ~0.03 mi away.
        self.assertEqual(self.notices("Chicago, IL", "Chicago Loop, IL", "Denver, CO"), [])

    def test_current_same_as_dropoff_has_no_notice(self):
        self.assertEqual(self.notices("Denver Downtown, CO", "Rockford, IL", "Denver, CO"), [])

    def test_pickup_same_as_dropoff(self):
        self.assertEqual(self.notices("Chicago, IL", "Denver, CO", "Denver Downtown, CO"),
                         ["Pickup and dropoff are the same location."])

    def test_all_three_the_same(self):
        self.assertEqual(self.notices("Chicago, IL", "Chicago Loop, IL", "Chicago Center, IL"),
                         ["All three locations are the same; no driving is needed."])

    def test_compares_coordinates_not_text(self):
        # Different text, same place → notice; ~0.2 mi apart → not the same place.
        self.assertEqual(self.notices("Chicago, IL", "Denver, CO", "Denver Downtown, CO"),
                         ["Pickup and dropoff are the same location."])
        self.assertEqual(self.notices("Chicago, IL", "Denver, CO", "Denver Union Station, CO"), [])


class SameLocationThresholdTest(SimpleTestCase):

    def test_about_a_tenth_of_a_mile(self):
        base = (39.7400, -104.9900)
        near = (39.7400 + 0.0012, -104.9900)    # ≈0.08 mi
        far = (39.7400 + 0.0016, -104.9900)     # ≈0.11 mi
        place = lambda p: (*p, "x", "exact")    # noqa: E731
        current = place((41.88, -87.63))
        self.assertEqual(same_location_notices([current, place(base), place(near)]),
                         ["Pickup and dropoff are the same location."])
        self.assertEqual(same_location_notices([current, place(base), place(far)]), [])
