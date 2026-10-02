# HOS Engine — Design

Source of truth for data structures, algorithm, and approved test cases.
See SPEC.md §4–6 for the rules this implements.

---

## 1. Data Structures

### Input

```python
@dataclass
class Leg:
    start_name: str
    end_name: str
    distance_miles: float
    drive_hours: float          # HGV travel time (from ORS); 0 = zero-length leg
```

### Output

```python
@dataclass
class Event:
    status: str      # 'off_duty' | 'sleeper_berth' | 'driving' | 'on_duty'
    type: str        # 'drive' | 'pickup' | 'dropoff' | 'fuel' | 'break_30' | 'rest_10' | 'restart_34'
    start: datetime
    end: datetime
    leg_index: int
    start_miles: float   # miles from leg start at event start; equals end_miles for stationary events
    end_miles: float     # miles from leg start at event end
```

### Function signature

```python
def plan_trip(
    legs: list[Leg],
    cycle_used: float,   # hours already on 70-h cycle (0–70)
    start_dt: datetime,
) -> list[Event]:
```

---

## 2. Constants (integer minutes)

| Name | Value | Rule |
|---|---|---|
| BREAK_LIMIT | 480 | 8 h driving since last break |
| DRIVE_LIMIT | 660 | 11 h driving this shift |
| WINDOW_LIMIT | 840 | 14 h since shift start (no driving after) |
| CYCLE_LIMIT | 4200 | 70 h driving + on duty |
| FUEL_MILES | 1000 | miles since last fuel stop |
| PICKUP_DUR | 60 | 1 h on duty |
| DROPOFF_DUR | 60 | 1 h on duty |
| FUEL_DUR | 30 | 30 min on duty |
| BREAK_DUR | 30 | 30 min off duty |
| REST_DUR | 600 | 10 h sleeper berth |
| RESTART_DUR | 2040 | 34 h off duty |

---

## 3. Internal State

| Variable | Type | Resets on |
|---|---|---|
| `clock` | datetime | — |
| `shift_start` | datetime | rest\_10, restart\_34 |
| `drive_since_break` | int (min) | any non-drive stop ≥ 30 min |
| `drive_this_shift` | int (min) | rest\_10, restart\_34 |
| `cycle` | int (min) | restart\_34 → 0 |
| `miles_since_fuel` | float (mi) | fuel stop → 0 |
| `leg_idx` | int | leg transition |
| `leg_dm` | int (min) | leg transition — full drive minutes for current leg, constant, used for speed |
| `leg_min_rem` | int (min) | leg transition, decremented each drive segment |
| `leg_miles_done` | float (mi) | leg transition → 0, accumulated each drive segment |

`shift_elapsed` is always derived: `int((clock − shift_start).total_seconds() // 60)`

`speed` (mi/min) is derived per leg: `leg.distance_miles / leg_dm`

---

## 4. Algorithm

Three fixes applied vs. initial design:

- **Fix 1 (integer minutes):** all time math in integer minutes; `h_fuel = int((FUEL_MILES − miles_since_fuel) * leg_dm / leg.distance_miles)` (floor via truncation on positive values). Eliminates the sub-minute overshoot bug.
- **Fix 2 (zero-length legs):** if `leg.distance_miles == 0` or `leg.drive_hours == 0`, skip the drive segment entirely and go straight to the check order.
- **Fix 3 (safety net):** cap at 10 000 iterations; if the check order falls through without emitting an event or advancing state, raise a clear `RuntimeError`.

Amendments (found while implementing; supersede the pseudocode below where they differ):

- **Zero-length legs:** a leg is zero-length only when `leg.distance_miles == 0`. For such a leg, `leg_dm = 0`, set `leg_min_rem = 0` and go straight to the check order (item 1 → pickup/dropoff). Speed is never computed for it. Any leg with distance > 0 gets `leg_dm = max(1, round(drive_hours * 60))`, so its miles always appear in a drive event (no divide-by-zero, and driven miles always equal total leg distance). This replaces the `drive_hours == 0` test, which stalled on 0-mile legs with drive time > 0 and divided by zero when drive time rounded to 0 minutes.
- **Fuel due:** check item 4 fires when `miles_since_fuel >= FUEL_MILES` **or** `h_fuel` (drive minutes left until 1,000 mi, floored) is ≤ 0. Without this, less than one minute of driving left before 1,000 mi gave `drive_for = 0` with no check firing, which stalled. The fuel stop stays at or before 1,000 mi.

```
INIT
  clock = shift_start = start_dt
  drive_since_break = drive_this_shift = 0
  cycle       = round(cycle_used * 60)
  miles_since_fuel = 0.0
  leg_idx     = 0
  leg_dm      = round(legs[0].drive_hours * 60)
  leg_min_rem = leg_dm
  leg_miles_done = 0.0
  iterations  = 0

LOOP  while leg_idx < len(legs):

  if iterations >= 10_000:
    raise RuntimeError("iteration cap exceeded")
  iterations += 1
  state_before = (clock, leg_idx, leg_min_rem)

  leg   = legs[leg_idx]
  zero_leg = (leg.distance_miles == 0 or leg.drive_hours == 0)   # Fix 2

  ── DRIVE SEGMENT ──────────────────────────────────────────────
  if not zero_leg:
    speed = leg.distance_miles / leg_dm   # mi/min, float

    shift_elapsed = int((clock − shift_start).total_seconds() // 60)
    can_drive = (drive_this_shift < DRIVE_LIMIT and
                 shift_elapsed   < WINDOW_LIMIT and
                 cycle           < CYCLE_LIMIT)

    if can_drive and leg_min_rem > 0:
      h_fuel = int((FUEL_MILES − miles_since_fuel) * leg_dm / leg.distance_miles)

      drive_for = min(
          BREAK_LIMIT  − drive_since_break,   # 8 h break counter
          DRIVE_LIMIT  − drive_this_shift,    # 11 h driving limit
          WINDOW_LIMIT − shift_elapsed,       # 14 h window
          CYCLE_LIMIT  − cycle,               # 70 h cycle
          h_fuel,                             # fuel distance
          leg_min_rem                         # leg end
      )
      # drive_for is integer; all inputs are integers or floored to integers

      if drive_for > 0:
        miles = drive_for * speed
        emit(driving, drive, leg_idx, leg_miles_done, leg_miles_done + miles)
        drive_since_break += drive_for ; drive_this_shift += drive_for
        cycle             += drive_for ; leg_miles_done   += miles
        miles_since_fuel  += miles     ; leg_min_rem      -= drive_for
        clock             += timedelta(minutes=drive_for)

  ── CHECK ORDER ────────────────────────────────────────────────
  shift_elapsed = int((clock − shift_start).total_seconds() // 60)

  # 1. Pickup or dropoff?
  if leg_min_rem == 0:
    if leg_idx == 0:                                   # first leg → pickup
      emit(on_duty, pickup, leg_idx, leg.distance_miles, leg.distance_miles)
      drive_since_break = 0 ; cycle += PICKUP_DUR
      clock += timedelta(minutes=PICKUP_DUR)
      leg_idx += 1
      leg_dm = round(legs[leg_idx].drive_hours * 60)
      leg_min_rem = leg_dm ; leg_miles_done = 0.0
      continue

    elif leg_idx == len(legs) − 1:                     # last leg → dropoff
      emit(on_duty, dropoff, leg_idx, leg.distance_miles, leg.distance_miles)
      drive_since_break = 0 ; cycle += DROPOFF_DUR
      clock += timedelta(minutes=DROPOFF_DUR)
      break                                            # trip complete

    else:                                              # middle leg (no special event)
      leg_idx += 1
      leg_dm = round(legs[leg_idx].drive_hours * 60)
      leg_min_rem = leg_dm ; leg_miles_done = 0.0
      continue

  # 2. Cycle at 70 h?
  if cycle >= CYCLE_LIMIT:
    emit(off_duty, restart_34, leg_idx, leg_miles_done, leg_miles_done)
    cycle = 0 ; drive_since_break = 0 ; drive_this_shift = 0
    clock += timedelta(minutes=RESTART_DUR) ; shift_start = clock
    continue

  # 3. 11 h driven or 14 h window expired?
  if drive_this_shift >= DRIVE_LIMIT or shift_elapsed >= WINDOW_LIMIT:
    emit(sleeper_berth, rest_10, leg_idx, leg_miles_done, leg_miles_done)
    drive_since_break = 0 ; drive_this_shift = 0
    clock += timedelta(minutes=REST_DUR) ; shift_start = clock
    continue

  # 4. 1,000 miles since fuel?
  if miles_since_fuel >= FUEL_MILES:
    emit(on_duty, fuel, leg_idx, leg_miles_done, leg_miles_done)
    drive_since_break = 0 ; miles_since_fuel = 0.0 ; cycle += FUEL_DUR
    clock += timedelta(minutes=FUEL_DUR)
    continue

  # 5. 8 h driving since last break?
  if drive_since_break >= BREAK_LIMIT:
    emit(off_duty, break_30, leg_idx, leg_miles_done, leg_miles_done)
    drive_since_break = 0
    clock += timedelta(minutes=BREAK_DUR)
    continue

  # Fix 3: safety net — no event emitted, no progress made
  if (clock, leg_idx, leg_min_rem) == state_before:
    raise RuntimeError(
        f"HOS engine stalled: no progress at {clock}, leg {leg_idx}, "
        f"leg_min_rem {leg_min_rem}"
    )

return events
```

---

## 5. Approved Test Cases

Columns: `#` · `type` · `status` · `start` · `end` · `leg` · `mi_s` (start_miles) · `mi_e` (end_miles)

Times are wall-clock on Day 1 / Day 2 / Day 3 (calendar days, starting at midnight).
All cases use a fixed start of **Day 1 06:00**.

---

### Case 1

**Inputs:** cycle 1200 min (20 h) · Leg 0: 110 mi, 120 min (55 mph) · Leg 1: 880 mi, 960 min (55 mph)

| # | type | status | start | end | leg | mi_s | mi_e |
|---|---|---|---|---|---|---|---|
| 1 | drive | driving | Day1 06:00 | Day1 08:00 | 0 | 0 | 110 |
| 2 | pickup | on_duty | Day1 08:00 | Day1 09:00 | 0 | 110 | 110 |
| 3 | drive | driving | Day1 09:00 | Day1 17:00 | 1 | 0 | 440 |
| 4 | break_30 | off_duty | Day1 17:00 | Day1 17:30 | 1 | 440 | 440 |
| 5 | drive | driving | Day1 17:30 | Day1 18:30 | 1 | 440 | 495 |
| 6 | rest_10 | sleeper_berth | Day1 18:30 | Day2 04:30 | 1 | 495 | 495 |
| 7 | drive | driving | Day2 04:30 | Day2 11:30 | 1 | 495 | 880 |
| 8 | dropoff | on_duty | Day2 11:30 | Day2 12:30 | 1 | 880 | 880 |

**Cycle after: 2400 min (40 h)**

Key checks: 8 h break fires at dsb=480 (E4) · 11 h limit fires at dts=660 (E6) · sheet totals sum to 24 h each day.

---

### Case 2

**Inputs:** cycle 3600 min (60 h) · Leg 0: 165 mi, 180 min (55 mph) · Leg 1: 550 mi, 600 min (55 mph)

| # | type | status | start | end | leg | mi_s | mi_e |
|---|---|---|---|---|---|---|---|
| 1 | drive | driving | Day1 06:00 | Day1 09:00 | 0 | 0 | 165 |
| 2 | pickup | on_duty | Day1 09:00 | Day1 10:00 | 0 | 165 | 165 |
| 3 | drive | driving | Day1 10:00 | Day1 16:00 | 1 | 0 | 330 |
| 4 | restart_34 | off_duty | Day1 16:00 | Day3 02:00 | 1 | 330 | 330 |
| 5 | drive | driving | Day3 02:00 | Day3 06:00 | 1 | 330 | 550 |
| 6 | dropoff | on_duty | Day3 06:00 | Day3 07:00 | 1 | 550 | 550 |

**Cycle after: 300 min (5 h)**

Key checks: cycle reaches 4200 (70 h) at 16:00 Day 1 (E3 ends) · restart spans all of Day 2 · Day 2 is a full off-duty log sheet.

---

### Case 3

**Inputs:** cycle 0 · Leg 0: 120 mi, 120 min (60 mph = 1 mi/min) · Leg 1: 1000 mi, 1000 min (60 mph)

| # | type | status | start | end | leg | mi_s | mi_e |
|---|---|---|---|---|---|---|---|
| 1 | drive | driving | Day1 06:00 | Day1 08:00 | 0 | 0 | 120 |
| 2 | pickup | on_duty | Day1 08:00 | Day1 09:00 | 0 | 120 | 120 |
| 3 | drive | driving | Day1 09:00 | Day1 17:00 | 1 | 0 | 480 |
| 4 | break_30 | off_duty | Day1 17:00 | Day1 17:30 | 1 | 480 | 480 |
| 5 | drive | driving | Day1 17:30 | Day1 18:30 | 1 | 480 | 540 |
| 6 | rest_10 | sleeper_berth | Day1 18:30 | Day2 04:30 | 1 | 540 | 540 |
| 7 | drive | driving | Day2 04:30 | Day2 10:10 | 1 | 540 | 880 |
| 8 | fuel | on_duty | Day2 10:10 | Day2 10:40 | 1 | 880 | 880 |
| 9 | drive | driving | Day2 10:40 | Day2 12:40 | 1 | 880 | 1000 |
| 10 | dropoff | on_duty | Day2 12:40 | Day2 13:40 | 1 | 1000 | 1000 |

**Cycle after: 1270 min**

Key checks: fuel fires at msf=1000 (120 from leg 0 + 480+60+340 from leg 1) before driver passes 1000 mi · dsb resets at E8 (was 340, becomes 0) · no break event after fuel.

---

### Case 3b — fuel and 8 h break simultaneously due

**Inputs:** cycle 0 · Leg 0: 65 mi, 120 min (32.5 mph) · Leg 1: 1045 mi, 1140 min (55 mph = 11/12 mi/min)

Design intent: in the drive segment starting at Day2 04:30, `h_fuel = ⌊440×12/11⌋ = 480` and `h_break = 480 − 0 = 480` — exact tie. `drive_for = 480`. After driving, both msf=1000 and dsb=480. Check order fires item 4 (fuel) before item 5 (break) → fuel event, no break event.

| # | type | status | start | end | leg | mi_s | mi_e |
|---|---|---|---|---|---|---|---|
| 1 | drive | driving | Day1 06:00 | Day1 08:00 | 0 | 0 | 65 |
| 2 | pickup | on_duty | Day1 08:00 | Day1 09:00 | 0 | 65 | 65 |
| 3 | drive | driving | Day1 09:00 | Day1 17:00 | 1 | 0 | 440 |
| 4 | break_30 | off_duty | Day1 17:00 | Day1 17:30 | 1 | 440 | 440 |
| 5 | drive | driving | Day1 17:30 | Day1 18:30 | 1 | 440 | 495 |
| 6 | rest_10 | sleeper_berth | Day1 18:30 | Day2 04:30 | 1 | 495 | 495 |
| 7 | drive | driving | Day2 04:30 | Day2 12:30 | 1 | 495 | 935 |
| 8 | fuel | on_duty | Day2 12:30 | Day2 13:00 | 1 | 935 | 935 |
| 9 | drive | driving | Day2 13:00 | Day2 15:00 | 1 | 935 | 1045 |
| 10 | dropoff | on_duty | Day2 15:00 | Day2 16:00 | 1 | 1045 | 1045 |

**Cycle after: 1410 min**

Key check: NO break\_30 event after E8 — fuel covered it. After E8, dsb=0. E9 drives 120 min → dsb=120, safely under 480.

---

### Note on the 14 h window

Under these app assumptions the 14 h window can never be the binding constraint:
maximum shift elapsed = 660 driving + 60 pickup + 30 break + 30 fuel = **780 min < 840**.
The WINDOW\_LIMIT check is kept for correctness and future-proofing.

---

### Case 4 — dropoff coincides with the 11 h driving limit

**Inputs:** cycle 0 · Leg 0: 60 mi, 60 min (60 mph = 1 mi/min) · Leg 1: 600 mi, 600 min (60 mph)

Design intent: after the break, leg 1 has 120 min remaining and h\_11 = 660−540 = 120 — exact tie. drive\_for = 120. After driving, dts=660 and lmr=0 simultaneously. Check order fires item 1 (dropoff) before item 3 (11 h rest). Trip ends; no rest event emitted.

| # | type | status | start | end | leg | mi_s | mi_e |
|---|---|---|---|---|---|---|---|
| 1 | drive | driving | Day1 06:00 | Day1 07:00 | 0 | 0 | 60 |
| 2 | pickup | on_duty | Day1 07:00 | Day1 08:00 | 0 | 60 | 60 |
| 3 | drive | driving | Day1 08:00 | Day1 16:00 | 1 | 0 | 480 |
| 4 | break_30 | off_duty | Day1 16:00 | Day1 16:30 | 1 | 480 | 480 |
| 5 | drive | driving | Day1 16:30 | Day1 18:30 | 1 | 480 | 600 |
| 6 | dropoff | on_duty | Day1 18:30 | Day1 19:30 | 1 | 600 | 600 |

**Cycle after: 780 min (13 h)**

Key check: dts=660 (=DRIVE\_LIMIT) and lmr=0 at the same moment after E5. Item 1 (dropoff) fires first — no rest\_10 emitted.

---

### Case 4c — pickup coincides with the 11 h driving limit

**Inputs:** cycle 0 · Leg 0: 660 mi, 660 min (60 mph = 1 mi/min) · Leg 1: 120 mi, 120 min (60 mph)

Design intent: mirror of Case 4 at the pickup. After the break, leg 0 has 180 min remaining and h\_11 = 660−480 = 180 — exact tie. After driving, dts=660 and lmr=0 simultaneously. Item 1 (pickup) fires first — on-duty work past 11 h is allowed. On the next iteration `can_drive` is False (dts=660) and lmr≠0, so item 3 fires: rest\_10 before any leg-1 driving.

| # | type | status | start | end | leg | mi_s | mi_e |
|---|---|---|---|---|---|---|---|
| 1 | drive | driving | Day1 06:00 | Day1 14:00 | 0 | 0 | 480 |
| 2 | break_30 | off_duty | Day1 14:00 | Day1 14:30 | 0 | 480 | 480 |
| 3 | drive | driving | Day1 14:30 | Day1 17:30 | 0 | 480 | 660 |
| 4 | pickup | on_duty | Day1 17:30 | Day1 18:30 | 0 | 660 | 660 |
| 5 | rest_10 | sleeper_berth | Day1 18:30 | Day2 04:30 | 1 | 0 | 0 |
| 6 | drive | driving | Day2 04:30 | Day2 06:30 | 1 | 0 | 120 |
| 7 | dropoff | on_duty | Day2 06:30 | Day2 07:30 | 1 | 120 | 120 |

**Cycle after: 900 min (15 h)**

Key check: pickup fires at dts=660 (no rest before it); rest\_10 follows on leg 1 at mile 0. Shift elapsed at pickup end = 750 min < 840.

---

### Case 4b — dropoff coincides with the cycle limit

**Inputs:** cycle 3840 min (64 h) · Leg 0: 60 mi, 60 min (60 mph) · Leg 1: 240 mi, 240 min (60 mph)

Design intent: after pickup, cyc=3960, h\_70=240, h\_leg=240 — exact tie. drive\_for=240. After driving, cycle=4200 (=CYCLE\_LIMIT) and lmr=0 simultaneously. Item 1 (dropoff) fires before item 2 (restart). Trip ends; no restart emitted. Dropoff is allowed "even past 70".

| # | type | status | start | end | leg | mi_s | mi_e |
|---|---|---|---|---|---|---|---|
| 1 | drive | driving | Day1 06:00 | Day1 07:00 | 0 | 0 | 60 |
| 2 | pickup | on_duty | Day1 07:00 | Day1 08:00 | 0 | 60 | 60 |
| 3 | drive | driving | Day1 08:00 | Day1 12:00 | 1 | 0 | 240 |
| 4 | dropoff | on_duty | Day1 12:00 | Day1 13:00 | 1 | 240 | 240 |

**Cycle after: 4260 min (71 h)**

Key check: cycle reaches 4200 simultaneously with leg end after E3. Item 1 fires first — no restart\_34 emitted. Final cycle exceeds CYCLE\_LIMIT by one dropoff hour (60 min); this is correct and expected.

---

### Case 5 — cycle input = 70 h (restart before any driving)

**Inputs:** cycle 4200 min (70 h) · Leg 0: 60 mi, 60 min (60 mph) · Leg 1: 120 mi, 120 min (60 mph)

Design intent: on the very first iteration, `can_drive` = False (cycle=4200 is not < CYCLE\_LIMIT) and lmr≠0. Item 2 fires immediately: restart\_34 before any driving occurs.

| # | type | status | start | end | leg | mi_s | mi_e |
|---|---|---|---|---|---|---|---|
| 1 | restart_34 | off_duty | Day1 06:00 | Day2 16:00 | 0 | 0 | 0 |
| 2 | drive | driving | Day2 16:00 | Day2 17:00 | 0 | 0 | 60 |
| 3 | pickup | on_duty | Day2 17:00 | Day2 18:00 | 0 | 60 | 60 |
| 4 | drive | driving | Day2 18:00 | Day2 20:00 | 1 | 0 | 120 |
| 5 | dropoff | on_duty | Day2 20:00 | Day2 21:00 | 1 | 120 | 120 |

**Cycle after: 300 min (5 h)**

Key check: restart fires at clock=06:00 before a single mile is driven. After restart: cycle=0, shift\_start=Day2 16:00. Subsequent driving is unconstrained.
