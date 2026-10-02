"""HOS simulation engine. See DESIGN.md (algorithm) and SPEC.md §4–6 (rules)."""

from dataclasses import dataclass
from datetime import datetime, timedelta

# All durations in integer minutes.
BREAK_LIMIT = 480      # 8 h driving since last break
DRIVE_LIMIT = 660      # 11 h driving this shift
WINDOW_LIMIT = 840     # 14 h since shift start (no driving after)
CYCLE_LIMIT = 4200     # 70 h driving + on duty
FUEL_MILES = 1000      # miles since last fuel stop
PICKUP_DUR = 60
DROPOFF_DUR = 60
FUEL_DUR = 30
BREAK_DUR = 30
REST_DUR = 600
RESTART_DUR = 2040

MAX_ITERATIONS = 10_000


@dataclass
class Leg:
    start_name: str
    end_name: str
    distance_miles: float
    drive_hours: float          # HGV travel time (from ORS); 0 = zero-length leg


@dataclass
class Event:
    status: str      # 'off_duty' | 'sleeper_berth' | 'driving' | 'on_duty'
    type: str        # 'drive' | 'pickup' | 'dropoff' | 'fuel' | 'break_30' | 'rest_10' | 'restart_34'
    start: datetime
    end: datetime
    leg_index: int
    start_miles: float   # miles from leg start at event start; equals end_miles for stationary events
    end_miles: float     # miles from leg start at event end


def _fuel_minutes_left(miles_since_fuel: float, leg_dm: int, distance_miles: float) -> int:
    """Whole drive minutes until 1,000 miles since fuel, at the current leg's speed."""
    return int((FUEL_MILES - miles_since_fuel) * leg_dm / distance_miles)


def _leg_minutes(leg: Leg) -> int:
    """Drive minutes for a leg. Any leg with distance > 0 gets at least 1 minute."""
    if leg.distance_miles == 0:
        return 0
    return max(1, round(leg.drive_hours * 60))


def plan_trip(
    legs: list[Leg],
    cycle_used: float,   # hours already on 70-h cycle (0–70)
    start_dt: datetime,
) -> list[Event]:
    events: list[Event] = []

    def emit(status, type_, duration, leg_index, start_miles, end_miles):
        events.append(Event(
            status=status,
            type=type_,
            start=clock,
            end=clock + timedelta(minutes=duration),
            leg_index=leg_index,
            start_miles=start_miles,
            end_miles=end_miles,
        ))

    # INIT
    clock = shift_start = start_dt
    drive_since_break = drive_this_shift = 0
    cycle = round(cycle_used * 60)
    miles_since_fuel = 0.0
    leg_idx = 0
    leg_dm = _leg_minutes(legs[0])
    leg_min_rem = leg_dm
    leg_miles_done = 0.0
    iterations = 0

    while leg_idx < len(legs):
        if iterations >= MAX_ITERATIONS:
            raise RuntimeError("iteration cap exceeded")
        iterations += 1
        state_before = (clock, leg_idx, leg_min_rem)

        leg = legs[leg_idx]
        zero_leg = leg.distance_miles == 0
        if zero_leg:
            leg_min_rem = 0   # straight to pickup/dropoff; speed never computed

        # ── DRIVE SEGMENT ──
        if not zero_leg:
            speed = leg.distance_miles / leg_dm   # mi/min

            shift_elapsed = int((clock - shift_start).total_seconds() // 60)
            can_drive = (drive_this_shift < DRIVE_LIMIT
                         and shift_elapsed < WINDOW_LIMIT
                         and cycle < CYCLE_LIMIT)

            if can_drive and leg_min_rem > 0:
                h_fuel = _fuel_minutes_left(miles_since_fuel, leg_dm, leg.distance_miles)

                drive_for = min(
                    BREAK_LIMIT - drive_since_break,
                    DRIVE_LIMIT - drive_this_shift,
                    WINDOW_LIMIT - shift_elapsed,
                    CYCLE_LIMIT - cycle,
                    h_fuel,
                    leg_min_rem,
                )

                if drive_for > 0:
                    miles = drive_for * speed
                    emit('driving', 'drive', drive_for, leg_idx,
                         leg_miles_done, leg_miles_done + miles)
                    drive_since_break += drive_for
                    drive_this_shift += drive_for
                    cycle += drive_for
                    leg_miles_done += miles
                    miles_since_fuel += miles
                    leg_min_rem -= drive_for
                    clock += timedelta(minutes=drive_for)

        # ── CHECK ORDER ──
        shift_elapsed = int((clock - shift_start).total_seconds() // 60)

        # 1. Pickup or dropoff?
        if leg_min_rem == 0:
            if leg_idx == 0:
                emit('on_duty', 'pickup', PICKUP_DUR, leg_idx,
                     leg.distance_miles, leg.distance_miles)
                drive_since_break = 0
                cycle += PICKUP_DUR
                clock += timedelta(minutes=PICKUP_DUR)
                leg_idx += 1
                leg_dm = _leg_minutes(legs[leg_idx])
                leg_min_rem = leg_dm
                leg_miles_done = 0.0
                continue

            elif leg_idx == len(legs) - 1:
                emit('on_duty', 'dropoff', DROPOFF_DUR, leg_idx,
                     leg.distance_miles, leg.distance_miles)
                drive_since_break = 0
                cycle += DROPOFF_DUR
                clock += timedelta(minutes=DROPOFF_DUR)
                break

            else:
                leg_idx += 1
                leg_dm = _leg_minutes(legs[leg_idx])
                leg_min_rem = leg_dm
                leg_miles_done = 0.0
                continue

        # 2. Cycle at 70 h?
        if cycle >= CYCLE_LIMIT:
            emit('off_duty', 'restart_34', RESTART_DUR, leg_idx,
                 leg_miles_done, leg_miles_done)
            cycle = 0
            drive_since_break = 0
            drive_this_shift = 0
            clock += timedelta(minutes=RESTART_DUR)
            shift_start = clock
            continue

        # 3. 11 h driven or 14 h window expired?
        if drive_this_shift >= DRIVE_LIMIT or shift_elapsed >= WINDOW_LIMIT:
            emit('sleeper_berth', 'rest_10', REST_DUR, leg_idx,
                 leg_miles_done, leg_miles_done)
            drive_since_break = 0
            drive_this_shift = 0
            clock += timedelta(minutes=REST_DUR)
            shift_start = clock
            continue

        # 4. 1,000 miles since fuel, or less than one drive minute left before it?
        # Reached only with leg_min_rem > 0, so the current leg is not zero-length.
        if (miles_since_fuel >= FUEL_MILES
                or _fuel_minutes_left(miles_since_fuel, leg_dm, leg.distance_miles) <= 0):
            emit('on_duty', 'fuel', FUEL_DUR, leg_idx,
                 leg_miles_done, leg_miles_done)
            drive_since_break = 0
            miles_since_fuel = 0.0
            cycle += FUEL_DUR
            clock += timedelta(minutes=FUEL_DUR)
            continue

        # 5. 8 h driving since last break?
        if drive_since_break >= BREAK_LIMIT:
            emit('off_duty', 'break_30', BREAK_DUR, leg_idx,
                 leg_miles_done, leg_miles_done)
            drive_since_break = 0
            clock += timedelta(minutes=BREAK_DUR)
            continue

        # Safety net: no event emitted, no progress made
        if (clock, leg_idx, leg_min_rem) == state_before:
            raise RuntimeError(
                f"HOS engine stalled: no progress at {clock}, leg {leg_idx}, "
                f"leg_min_rem {leg_min_rem}"
            )

    return events
