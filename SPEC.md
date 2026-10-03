# ELD Trip Planner – Spec (Spotter AI Full Stack Assessment)

Deadline: Sunday, October 4, 2026, 10:00 PM (Palestine time). Max 16 work hours.
Deliverables: hosted link, GitHub repo, 3–5 minute Loom (app + code walkthrough).

## 1. What the app does

A website for truck drivers/dispatchers. The driver enters a trip once and gets a finished plan:
a route map with every stop, turn-by-turn directions, and the filled-in daily log sheets for the trip.
It plans ahead. It does not track live hours (that is the ELD device's job).

## 2. Inputs

Required (from Spotter's spec):
- Current location
- Pickup location
- Dropoff location
- Current cycle used (hours): 0 to 70, decimals allowed (e.g. 20.5). Reject < 0 or > 70.

Added by us:
- Start date/time: pre-filled with "now", editable.

Optional, only printed on the log sheets (all have placeholder defaults):
- Driver name, driver number, co-driver name
- Carrier name, main office address, home terminal address
- Truck/tractor and trailer numbers
- Shipping document number, or shipper + commodity

## 3. Outputs

1. Map: route line current → pickup → dropoff, with markers for pickup, dropoff, fuel stops,
   30-min breaks, 10-hour rests, 34-hour restarts. Each marker shows type, time, duration, city.
2. Route instructions: turn-by-turn directions list (from OpenRouteService). REQUIRED by spec.
3. Trip summary: total miles, total days, list of stops, "cycle used after this trip: X / 70",
   "hours available tomorrow".
4. Daily log sheets: one per calendar day (midnight to midnight), matching the blank form
   Spotter attached. As many sheets as the trip needs, including full off-duty days.

## 4. Hours of Service rules (property-carrying, 70 hrs / 8 days)

Duty statuses:
| Status | Counts toward |
|---|---|
| Driving | 8-hour break counter, 11, 14, 70 |
| On duty (not driving): pickup, dropoff, fueling | 14, 70 |
| Off duty | nothing (14 clock keeps running) |
| Sleeper berth | nothing (14 clock keeps running) |

Rules:
- 11-hour limit: max 11 hours driving per shift.
- 14-hour window: starts when the shift starts, never pauses. No DRIVING after hour 14.
  On-duty work (e.g. dropoff) after hour 14 is allowed.
- 30-minute break: required after 8 cumulative hours of DRIVING (not clock time).
  Any 30 consecutive minutes not driving satisfies it (off duty, sleeper, or on duty).
  So pickup (1h), dropoff (1h), fuel (30 min) all reset the 8-hour counter.
  If the 11/14 limit is hit at the same time, skip the break; the 10-hour rest covers it.
- 10-hour rest: 10 consecutive hours off duty/sleeper. Resets 11, 14, and the 8 counter.
  Comes BETWEEN shifts. On-duty time does not count toward it (rest starts when he goes off duty).
  Next shift starts immediately after the rest, not tied to the calendar day.
- 70-hour / 8-day: driving + on duty total. Starts at the cycle input. Only ever add to it.
  No rolling-window subtraction (we don't have day-by-day history).
- 34-hour restart: when cycle reaches 70, insert 34 consecutive hours off duty, cycle → 0.
  (Restart is optional by law; we use it because we have no history. Old 1–5 AM rule is no longer in effect.)
- Sleeper berth split (7/3, 8/2): NOT used. Always a single 10-hour block.

Spotter's assumptions:
- Pickup: 1 hour on duty. Dropoff: 1 hour on duty.
- Fuel at least every 1,000 miles: stop before passing 1,000 miles since last fuel. 30 min on duty
  (matches the FMCSA guide's own example).
- No adverse driving conditions. No short-haul exceptions.

## 5. Simulation counters

Track during the simulation:
1. Driving since last 30-min break (limit 8)
2. Driving this shift (limit 11)
3. Time since shift start (limit 14)
4. Cycle hours (limit 70)
5. Miles since last fuel (limit 1,000)
6. Current clock time (to split log sheets at midnight)

The list above is just the counters, not an order. CHECK ORDER at every stop point
(order matters so one stop covers several needs and he never stops twice for no reason):
1. Arrived at pickup/dropoff? → 1 hour on duty. Allowed even past 11/14/70 (on duty only).
   Covers the 30-min break (resets the 8 counter).
2. Cycle at 70? → 34-hour restart, cycle → 0 (also resets 11, 14, 8).
3. 11h driven or 14h passed? → 10-hour rest (also covers the 30-min break).
4. 1,000 miles since fuel? → 30-min fuel stop, on duty (covers the 30-min break, resets 8).
5. 8 hours driving since last break? → 30-min break, off duty.
6. Otherwise → drive until the NEAREST of: 8h break limit, 11h, 14h, 70h, 1,000 miles, leg end.
Repeat until dropoff is done.

## 6. Decisions (state these in README and Loom)

- Driver starts the trip on a fresh shift (just had 10 hours off).
- Trip is exactly current → pickup → dropoff. No extra stops. New stop = new trip.
- Cycle used is typed by the driver each time (he knows it from his logbook/ELD).
- Time zone: times are in home terminal time exactly as the driver enters them; the app does
  no time zone conversion. The form tells the driver to enter the start time in home terminal
  time, and each log sheet shows "Times in home terminal time".
  (FMCSA: logs use home terminal time even when crossing zones.)
- Status choices: 30-min break = off duty; 10-hour rest = sleeper berth;
  34-hour restart = off duty; fuel/pickup/dropoff = on duty.
- Drive times from the TRUCK profile (OpenRouteService driving-hgv), not car.
- Stops placed at the point on the route where time runs out; nearest city name used for remarks.
- No pre-trip/post-trip inspection (not in Spotter's assumptions).
- No database, no login. Nothing is stored. Driver details are used only to render the sheets.
  Only locations are sent to the map API.
- After dropoff, rest of that day is off duty.

## 7. Log sheet contents (copy the blank form Spotter attached)

- Header: date (month/day/year), From, To, total miles driving today, total mileage today
  (same number for one truck), carrier name, main office address, home terminal address,
  truck/trailer numbers, driver name/number, co-driver.
- Grid: 4 rows (off duty, sleeper berth, driving, on duty), 24 hours with 15-min ticks.
  Horizontal line in the matching row, vertical lines at each status change.
- Total hours per row on the right. Must sum to 24.
- Remarks: city, state + what happened at every status change, starting with
  "Reported for work, <city>".
- Shipping documents: doc number or shipper + commodity.
- Recap (70-hour/8-day column only): on duty today; total last 7/8 days (cycle input +
  trip hours so far); hours available tomorrow (70 − total). Mark the 60-hour column unused.

## 8. Tech stack

- Backend: Django + Django REST Framework. One endpoint: POST /api/plan-trip.
  Modules: route service (geocode, route, directions, reverse geocode), HOS engine, log builder.
- Frontend: React (Vite) + Leaflet with OpenStreetMap tiles. Log sheets drawn as SVG.
- Map API: OpenRouteService (free key, 2,000 routes/day).
- API key in an environment variable on the backend only. Never committed to GitHub.
- CORS configured so the frontend can call the backend.
- Hosting: frontend on Vercel. Backend on Vercel (no DB needed) or Render
  (Render free tier sleeps ~50s; avoid or warn).

## 9. Tests (HOS engine)

1. Cycle 20, current→pickup 2h, pickup→dropoff 16h, start 6:00 AM.
   Day 1: drive 6–8, pickup 8–9, drive 9–17, break 17–17:30, drive 17:30–18:30, rest from 18:30.
   Day 1 totals: off 12, driving 11, on duty 1. Day 2: rest until 4:30, drive 4:30–11:30,
   dropoff 11:30–12:30, off after. Day 2 totals: off 16, driving 7, on duty 1. Cycle after: 40.
2. Cycle 60, current→pickup 3h, pickup→dropoff 10h, start 6:00 AM.
   Drive 6–9 (63), pickup 9–10 (64), drive 10–16 (70). 34h restart 16:00 day 1 → 02:00 day 3.
   Day 2 = full off-duty sheet. Day 3: drive 2:00–6:00, dropoff 6:00–7:00.
3. Trip over 1,000 miles: fuel stop appears before 1,000 miles and resets the 8 counter.
4. Arrival at dropoff right at hour 14: dropoff still happens (on duty allowed), no rest first.
5. Cycle input 70: trip starts with a 34-hour restart.
6. Every sheet's totals sum to exactly 24.

## 10. Build plan

- Day 1 (Thu, ~3h): repo, Django + React skeleton, ORS key, deploy hello-world of both.
- Day 2 (Fri, ~5h): HOS engine + tests above, then the API endpoint.
- Day 3 (Sat, ~5h): form, map + markers, directions list, log sheet SVG.
- Day 4 (Sun, ~3h): UI polish, edge cases, README (with all decisions in section 6), Loom, submit.
