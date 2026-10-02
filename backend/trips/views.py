import logging

from rest_framework.decorators import api_view
from rest_framework.response import Response

from trips.serializers import CoordsSerializer, PlanTripSerializer
from trips.services import planner
from trips.services.autocomplete import suggest
from trips.services.routing import (
    ApiKeyError, NoAddress, NoRouteFound, OutsideUS, QuotaExceeded, RoutingError,
    ServiceUnavailable, reverse_address,
)

logger = logging.getLogger(__name__)


def error_response(status, code, message, fields=None, **extra):
    body = {"code": code, "message": message}
    if fields is not None:
        body["fields"] = fields
    body.update(extra)
    return Response({"error": body}, status=status)


@api_view(["GET"])
def health_check(request):
    return Response({"status": "ok"})


@api_view(["GET"])
def autocomplete(request):
    """Address suggestions; always 200, empty when unavailable."""
    labels = suggest(request.query_params.get("text", ""))
    return Response({"suggestions": [{"label": label} for label in labels]})


@api_view(["GET"])
def reverse_location(request):
    """Readable US address for the browser's position ("Use my current location")."""
    serializer = CoordsSerializer(data=request.query_params)
    if not serializer.is_valid():
        return error_response(400, "invalid_input", "Invalid coordinates.", fields=serializer.errors)
    lat, lon = serializer.validated_data["lat"], serializer.validated_data["lon"]
    try:
        label = reverse_address(lat, lon)
    except OutsideUS as e:
        return error_response(422, "outside_us", str(e))
    except NoAddress as e:
        return error_response(422, "no_address", str(e))
    except ApiKeyError as e:
        logger.error("Route service API key problem: %s", e)
        return error_response(500, "service_misconfigured", "The route service is not configured correctly.")
    except (QuotaExceeded, ServiceUnavailable):
        return error_response(503, "service_unavailable", "Location lookup is unavailable. Try again.")
    except RoutingError as e:
        logger.error("Unexpected reverse geocoding response: %s", e)
        return error_response(502, "bad_gateway", "The route service returned an unexpected response.")
    return Response({"label": label, "lat": lat, "lon": lon})


@api_view(["POST"])
def plan_trip(request):
    serializer = PlanTripSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response(400, "invalid_input", "Some fields are missing or invalid.",
                              fields=serializer.errors)
    try:
        return Response(planner.plan(serializer.validated_data))
    except planner.AddressesNotFound as e:
        return error_response(400, "address_not_found", str(e), fields=e.fields, reasons=e.reasons)
    except NoRouteFound as e:
        return error_response(422, "no_route", str(e))
    except ApiKeyError as e:
        logger.error("Route service API key problem: %s", e)
        return error_response(500, "service_misconfigured",
                              "The route service is not configured correctly.")
    except QuotaExceeded:
        return error_response(503, "service_unavailable",
                              "Route service quota is used up. Try again later.")
    except ServiceUnavailable:
        return error_response(503, "service_unavailable",
                              "Route service is unavailable. Try again.")
    except RoutingError as e:
        logger.error("Unexpected route service response: %s", e)
        return error_response(502, "bad_gateway",
                              "The route service returned an unexpected response.")
    except (planner.IllegalPlan, RuntimeError):
        logger.exception("Trip planning failed")
        return error_response(500, "internal_error", "Something went wrong planning this trip.")
