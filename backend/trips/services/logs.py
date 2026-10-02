"""Daily log sheet builder: cuts the engine timeline into one sheet per calendar day.

Times are home terminal time exactly as entered (no time zone conversion), so every
day has 1440 minutes. A trip crossing a daylight-saving change is off by an hour
from that point (documented in the README).
"""

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

DAY_MIN = 1440
CYCLE_LIMIT_MIN = 4200
STATUSES = ("off_duty", "sleeper_berth", "driving", "on_duty")
WORK_STATUSES = ("driving", "on_duty")

DESCRIPTIONS = {
    "drive": "Driving",
    "pickup": "Pickup",
    "dropoff": "Dropoff",
    "fuel": "Fuel",
    "break_30": "30-min break",
    "rest_10": "10-hour rest",
    "restart_34": "34-hour restart",
    "post_trip": "Off duty",
}


@dataclass
class Segment:
    status: str
    start_min: int
    end_min: int


@dataclass
class Remark:
    minute: int
    location: str
    description: str


@dataclass
class Recap:
    on_duty_today: int      # driving + on duty today
    a: int                  # total on duty (cycle input + trip so far), reset after a 34 h restart
    b: int                  # available tomorrow: max(0, 4200 − A)
    c: int                  # same as A (no daily history)


@dataclass
class DaySheet:
    date: object
    from_location: str
    to_location: str
    segments: list[Segment] = field(default_factory=list)
    totals: dict = field(default_factory=dict)
    miles: float = 0.0
    remarks: list[Remark] = field(default_factory=list)
    recap: Recap | None = None


@dataclass
class TripLog:
    sheets: list[DaySheet]
    total_miles: float
    days: int
    cycle_after_min: int
    hours_available_tomorrow: float


@dataclass
class _Piece:
    """One stretch of the timeline: an engine event, or off duty before/after the trip."""
    status: str
    type: str
    start: datetime
    end: datetime
    location: str
    miles: float


def _midnight(dt):
    return datetime.combine(dt.date(), time(0), tzinfo=dt.tzinfo)


def _minute(dt, day_start):
    """Whole minutes from day_start, clamped to the day."""
    return min(max(int((dt - day_start).total_seconds() // 60), 0), DAY_MIN)


def _timeline(events, names, legs, trip_start):
    current = legs[0].start_name
    first_day = _midnight(trip_start)
    pieces = [_Piece("off_duty", "pre_trip", first_day, events[0].start, current, 0.0)]
    for e, name in zip(events, names):
        if name:
            current = name
        pieces.append(_Piece(e.status, e.type, e.start, e.end, current,
                             e.end_miles - e.start_miles if e.status == "driving" else 0.0))
    last_end = events[-1].end
    end_of_last_day = _midnight(last_end - timedelta(microseconds=1)) + timedelta(days=1)
    pieces.append(_Piece("off_duty", "post_trip", last_end, end_of_last_day, current, 0.0))
    return [p for p in pieces if p.end > p.start], first_day, end_of_last_day


def build_logs(events, names, legs, cycle_used_hours, trip_start):
    """Build one DaySheet per calendar day plus trip totals.

    events/names: engine events and their stop names (None for drive events).
    trip_start: start time as entered, in home terminal time.
    """
    pieces, first_day, end = _timeline(events, names, legs, trip_start)
    a = round(cycle_used_hours * 60)
    sheets = []
    first_trip_event = pieces[0] if pieces[0].type != "pre_trip" else pieces[1]
    prev_status = None

    day_start = first_day
    while day_start < end:
        day_end = day_start + timedelta(days=1)
        today = [p for p in pieces if p.start < day_end and p.end > day_start]
        sheet = DaySheet(date=day_start.date(),
                         from_location=today[0].location,
                         to_location=today[-1].location)

        for p in today:
            s, t = _minute(p.start, day_start), _minute(p.end, day_start)
            if t <= s:
                continue
            if sheet.segments and sheet.segments[-1].status == p.status:
                sheet.segments[-1].end_min = t
            else:
                sheet.segments.append(Segment(p.status, s, t))

            if p.miles:
                share = (min(p.end, day_end) - max(p.start, day_start)) / (p.end - p.start)
                sheet.miles += p.miles * share

            starts_today = p.start >= day_start
            if p is first_trip_event:
                if starts_today:
                    desc = DESCRIPTIONS[p.type]
                    if p.status in WORK_STATUSES:
                        desc = "Reported for work"
                    sheet.remarks.append(Remark(s, legs[0].start_name, desc))
            elif starts_today and p.status != prev_status and p.type != "pre_trip":
                sheet.remarks.append(Remark(s, p.location, DESCRIPTIONS[p.type]))
            prev_status = p.status

            if p.status in WORK_STATUSES:
                a += t - s
            if p.type == "restart_34" and p.end <= day_end:
                a = 0       # option (a): A resets when the restart ends

        if not sheet.remarks:
            p = today[0]
            sheet.remarks.append(Remark(0, p.location, f"{DESCRIPTIONS[p.type]} (continuing)"))

        sheet.totals = {status: 0 for status in STATUSES}
        for seg in sheet.segments:
            sheet.totals[seg.status] += seg.end_min - seg.start_min
        on_duty_today = sheet.totals["driving"] + sheet.totals["on_duty"]
        sheet.recap = Recap(on_duty_today=on_duty_today, a=a,
                            b=max(0, CYCLE_LIMIT_MIN - a), c=a)
        sheets.append(sheet)
        day_start = day_end

    return TripLog(
        sheets=sheets,
        total_miles=sum(s.miles for s in sheets),
        days=len(sheets),
        cycle_after_min=a,
        hours_available_tomorrow=max(0.0, 70 - a / 60),
    )
