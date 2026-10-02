import logging

from rest_framework.decorators import api_view
from rest_framework.response import Response

from trips.serializers import PlanTripSerializer
from trips.services import planner
from trips.services.autocomplete import suggest
from trips.services.routing import (
    ApiKeyError, NoRouteFound, QuotaExceeded, RoutingError, ServiceUnavailable,
)

logger = logging.getLogger(__name__)


def error_response(status, code, message, fields=None):
    body = {"code": code, "message": message}
    if fields is not None:
        body["fields"] = fields
    return Response({"error": body}, status=status)


@api_view(["GET"])
def health_check(request):
    return Response({"status": "ok"})


@api_view(["GET"])
def autocomplete(request):
    """Address suggestions; always 200, empty when unavailable."""
    labels = suggest(request.query_params.get("text", ""))
    return Response({"suggestions": [{"label": label} for label in labels]})


@api_view(["POST"])
def plan_trip(request):
    serializer = PlanTripSerializer(data=request.data)
    if not serializer.is_valid():
        return error_response(400, "invalid_input", "Some fields are missing or invalid.",
                              fields=serializer.errors)
    try:
        return Response(planner.plan(serializer.validated_data))
    except planner.AddressesNotFound as e:
        return error_response(400, "address_not_found", str(e), fields=e.fields)
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
