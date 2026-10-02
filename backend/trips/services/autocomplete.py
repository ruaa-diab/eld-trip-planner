"""Address suggestions for the trip form: GET https://api.heigit.org/pelias/v1/autocomplete.

Suggestions are a convenience, so this never raises: any failure (no key, quota,
timeout, bad reply) is logged and returns no suggestions.
"""

import logging

from trips.services.routing import RoutingError, request_json, short_label

logger = logging.getLogger(__name__)

AUTOCOMPLETE_PATH = "/pelias/v1/autocomplete"
TIMEOUT_SECONDS = 5
MIN_CHARS = 3
MAX_CHARS = 200
MAX_RESULTS = 5
# Real cities first, full addresses still work; no townships (localadmin) or neighbourhoods.
LAYERS = "locality,county,address,street,venue"


def suggest(text):
    """Up to 5 distinct US address labels for the typed text, or [] on any problem."""
    text = (text or "").strip()
    if len(text) < MIN_CHARS or len(text) > MAX_CHARS:
        return []

    try:
        data = request_json("GET", AUTOCOMPLETE_PATH, timeout=TIMEOUT_SECONDS, params={
            "text": text,
            "boundary.country": "US",
            "size": MAX_RESULTS,
            "layers": LAYERS,
        })
        features = data.get("features") or []
        labels = []
        for feature in features:
            label = (feature.get("properties") or {}).get("label")
            if label:
                label = short_label(label)
                if label not in labels:
                    labels.append(label)
        return labels[:MAX_RESULTS]
    except RoutingError as e:
        logger.warning("Autocomplete unavailable: %s", e)
    except Exception:
        logger.warning("Autocomplete failed", exc_info=True)
    return []
