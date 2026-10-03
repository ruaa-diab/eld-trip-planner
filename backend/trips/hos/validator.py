"""Independent HOS rule checker. Shares no code with engine.py on purpose.

Rules are re-derived from SPEC.md §4 so the checker can catch engine bugs.
Events and legs are duck-typed: anything with the same attributes works.
"""

SHIFT_DRIVE_MAX = 660       # 11 h driving per shift
SHIFT_WINDOW_MAX = 840      # no driving after 14 h from shift start
DRIVE_BEFORE_BREAK = 480    # 8 h driving without a qualifying break
BREAK_MIN = 30              # consecutive non-driving minutes that count as a break
SHIFT_REST_MIN = 600        # consecutive off/sleeper minutes that end a shift
CYCLE_MAX = 4200            # 70 h driving + on duty
RESTART_MIN = 2040          # consecutive off/sleeper minutes that reset the cycle
FUEL_INTERVAL_MILES = 1000

OFF_STATUSES = ("off_duty", "sleeper_berth")
MILES_TOL = 1e-6


def _minutes(start, end):
    return (end - start).total_seconds() / 60


def validate_trip(events, cycle_used, legs) -> list[str]:
    """Return a list of rule violations; empty if the trip is legal.

    cycle_used is in hours, as passed to the planner.
    """
    violations: list[str] = []

    def flag(i, msg):
        violations.append(f"event {i}: {msg}")

    if not events:
        return ["trip has no events"]

    # Order and continuity
    for i, e in enumerate(events, 1):
        if e.end <= e.start:
            flag(i, f"{e.type} has non-positive duration ({e.start} → {e.end})")
        if i > 1:
            prev = events[i - 2]
            if e.start > prev.end:
                flag(i, f"gap of {_minutes(prev.end, e.start):g} min after previous event")
            elif e.start < prev.end:
                flag(i, f"overlaps previous event by {_minutes(e.start, prev.end):g} min")

    # Time-based limits
    cycle = round(cycle_used * 60)
    shift_start = events[0].start     # driver starts on a fresh shift (SPEC §6)
    shift_drive = 0.0
    drive_since_break = 0.0
    off_run = 0.0          # consecutive off_duty/sleeper minutes
    non_drive_run = 0.0    # consecutive non-driving minutes (any status)
    miles_since_fuel = 0.0

    for i, e in enumerate(events, 1):
        dur = _minutes(e.start, e.end)

        if e.status in OFF_STATUSES:
            off_run += dur
            non_drive_run += dur
            continue

        # Work (driving or on duty) begins: apply resets earned by the preceding off period.
        if off_run >= SHIFT_REST_MIN:
            shift_start = e.start
            shift_drive = 0.0
        if off_run >= RESTART_MIN:
            cycle = 0
        off_run = 0.0

        if e.status == "driving":
            if non_drive_run >= BREAK_MIN:
                drive_since_break = 0.0
            non_drive_run = 0.0

            if cycle + dur > CYCLE_MAX:
                flag(i, f"driving with cycle at {cycle:g} min; would reach "
                        f"{cycle + dur:g} > {CYCLE_MAX}")
            minutes_into_shift = _minutes(shift_start, e.end)
            if minutes_into_shift > SHIFT_WINDOW_MAX:
                flag(i, f"driving until {minutes_into_shift:g} min after shift start "
                        f"(limit {SHIFT_WINDOW_MAX})")
            shift_drive += dur
            if shift_drive > SHIFT_DRIVE_MAX:
                flag(i, f"{shift_drive:g} driving min this shift (limit {SHIFT_DRIVE_MAX})")
            drive_since_break += dur
            if drive_since_break > DRIVE_BEFORE_BREAK:
                flag(i, f"{drive_since_break:g} driving min without a {BREAK_MIN}-min break "
                        f"(limit {DRIVE_BEFORE_BREAK})")

            miles_since_fuel += e.end_miles - e.start_miles
            if miles_since_fuel > FUEL_INTERVAL_MILES + MILES_TOL:
                flag(i, f"{miles_since_fuel:g} miles since last fuel "
                        f"(limit {FUEL_INTERVAL_MILES})")
        elif e.status == "on_duty":
            non_drive_run += dur
            if e.type == "fuel":
                miles_since_fuel = 0.0
        else:
            flag(i, f"unknown status {e.status!r}")

        cycle += dur

    # Distance and stops
    driven = sum(e.end_miles - e.start_miles for e in events if e.status == "driving")
    planned = sum(leg.distance_miles for leg in legs)
    if abs(driven - planned) > MILES_TOL:
        violations.append(f"trip: drove {driven:g} miles but legs total {planned:g}")

    pickups = [i for i, e in enumerate(events, 1) if e.type == "pickup"]
    dropoffs = [i for i, e in enumerate(events, 1) if e.type == "dropoff"]
    if len(pickups) != 1:
        violations.append(f"trip: expected 1 pickup, found {len(pickups)}")
    if len(dropoffs) != 1:
        violations.append(f"trip: expected 1 dropoff, found {len(dropoffs)}")
    if len(pickups) == 1 and len(dropoffs) == 1 and pickups[0] > dropoffs[0]:
        violations.append(f"trip: dropoff (event {dropoffs[0]}) before pickup "
                          f"(event {pickups[0]})")

    return violations
