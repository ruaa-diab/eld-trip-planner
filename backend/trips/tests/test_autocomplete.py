"""GET /api/autocomplete tests. HTTP is mocked; no real API calls."""

from unittest import mock

import requests
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIClient

from trips.services import routing

URL = "/api/autocomplete"
KEY = "secret-test-key-123"


def response(status=200, body=None):
    resp = mock.Mock(status_code=status, text=str(body))
    if body is None:
        resp.json.side_effect = ValueError()
    else:
        resp.json.return_value = body
    return resp


def features(*labels):
    return {"features": [{"properties": {"label": label}} for label in labels]}


@override_settings(ORS_API_KEY=KEY)
@mock.patch.object(routing.requests, "request")
class AutocompleteTest(SimpleTestCase):

    def setUp(self):
        self.client = APIClient()

    def get(self, text):
        return self.client.get(URL, {"text": text})

    def test_returns_short_labels_without_duplicates(self, req):
        req.return_value = response(body=features(
            "Chicago, IL, USA", "Chicago Heights, IL, USA", "Chicago, IL, USA",
            "Chicago Ridge, IL, USA", "West Chicago, IL, USA", "North Chicago, IL, USA",
        ))
        resp = self.get("  Chic ")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"suggestions": [
            {"label": "Chicago, IL"}, {"label": "Chicago Heights, IL"}, {"label": "Chicago Ridge, IL"},
            {"label": "West Chicago, IL"}, {"label": "North Chicago, IL"},
        ]})

        method, url = req.call_args.args
        kwargs = req.call_args.kwargs
        self.assertEqual((method, url), ("GET", "https://api.heigit.org/pelias/v1/autocomplete"))
        self.assertEqual(kwargs["params"], {
            "text": "Chic", "boundary.country": "US", "size": 5,
            "layers": "locality,county,address,street,venue",
        })
        self.assertEqual(kwargs["headers"], {"Authorization": KEY})
        self.assertEqual(kwargs["timeout"], 5)

    def test_short_blank_or_long_text_makes_no_call(self, req):
        for text in ("", "   ", "Ch", " Ch ", "x" * 201):
            with self.subTest(text=text[:10]):
                resp = self.get(text)
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.json(), {"suggestions": []})
        req.assert_not_called()

    def test_missing_text_param_returns_empty(self, req):
        resp = self.client.get(URL)
        self.assertEqual(resp.json(), {"suggestions": []})
        req.assert_not_called()

    @override_settings(ORS_API_KEY="")
    def test_missing_key_returns_empty_without_calling(self, req):
        with self.assertLogs("trips.services.autocomplete", "WARNING"):
            resp = self.get("Chicago")
        self.assertEqual((resp.status_code, resp.json()), (200, {"suggestions": []}))
        req.assert_not_called()

    def test_failures_return_empty_and_log(self, req):
        cases = {
            "rejected key": dict(return_value=response(403, {"error": "Access to this API has been disallowed"})),
            "quota": dict(return_value=response(429, {"error": "Rate limit exceeded"})),
            "down": dict(return_value=response(503)),
            "timeout": dict(side_effect=requests.Timeout()),
            "malformed": dict(return_value=response(200, {"features": "nonsense"})),
        }
        for label, behaviour in cases.items():
            with self.subTest(label):
                req.reset_mock(return_value=True, side_effect=True)
                req.configure_mock(**behaviour)
                with self.assertLogs("trips.services.autocomplete", "WARNING"):
                    resp = self.get("Chicago")
                self.assertEqual((resp.status_code, resp.json()), (200, {"suggestions": []}))
                self.assertNotIn(KEY, resp.content.decode())

    def test_only_get_allowed(self, req):
        self.assertEqual(self.client.post(URL, {"text": "Chicago"}).status_code, 405)
