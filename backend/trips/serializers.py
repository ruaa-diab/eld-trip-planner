import math
from datetime import datetime

from rest_framework import serializers

DETAIL_FIELDS = (
    "driver_name", "driver_number", "co_driver_name",
    "carrier_name", "main_office_address", "home_terminal_address",
    "truck_number", "trailer_number",
    "shipping_document", "shipper", "commodity",
)


class LocalDateTimeField(serializers.Field):
    """ISO date-time with no time zone, kept exactly as entered (home terminal time).

    DRF's DateTimeField would convert to UTC because USE_TZ is on.
    """

    def to_internal_value(self, value):
        if not isinstance(value, str):
            raise serializers.ValidationError("Enter a date and time like 2026-10-05T06:00.")
        try:
            dt = datetime.fromisoformat(value.strip())
        except ValueError:
            raise serializers.ValidationError("Enter a date and time like 2026-10-05T06:00.")
        if dt.tzinfo is not None:
            raise serializers.ValidationError(
                "Enter the time without a time zone; it is read as home terminal time.")
        return dt

    def to_representation(self, value):
        return value.isoformat()


class DetailsSerializer(serializers.Serializer):
    """Optional driver/carrier details, only printed on the log sheets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in DETAIL_FIELDS:
            self.fields[name] = serializers.CharField(
                required=False, allow_blank=True, max_length=200, default="")


class PlanTripSerializer(serializers.Serializer):
    current_location = serializers.CharField(max_length=200)
    pickup_location = serializers.CharField(max_length=200)
    dropoff_location = serializers.CharField(max_length=200)
    current_cycle_used = serializers.FloatField(min_value=0, max_value=70)
    start_time = LocalDateTimeField()
    details = DetailsSerializer(required=False)

    def validate_current_cycle_used(self, value):
        if not math.isfinite(value):
            raise serializers.ValidationError("Enter a number of hours from 0 to 70.")
        return value

    def validate(self, data):
        data.setdefault("details", {name: "" for name in DETAIL_FIELDS})
        return data
