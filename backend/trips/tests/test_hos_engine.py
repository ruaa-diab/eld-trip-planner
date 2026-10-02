"""HOS engine tests. Expected tables are the approved cases in trips/hos/DESIGN.md §5."""

from dataclasses import replace
from datetime import datetime, timedelta
from unittest import mock

from django.test import SimpleTestCase

from trips.hos import engine
from trips.hos.engine import Event, Leg, plan_trip
from trips.hos.validator import validate_trip

DAY1 = datetime(2026, 1, 5)          # midnight of Day 1
START = DAY1 + timedelta(hours=6)    # all cases start Day 1 06:00


def at(day, hhmm):
    h, m = map(int, hhmm.split(":"))
    return DAY1 + timedelta(days=day - 1, hours=h, minutes=m)


def leg(miles, minutes):
    return Leg("A", "B", miles, minutes / 60)


# Approved case inputs: (cycle used in minutes, legs).
APPROVED_INPUTS = {
    "1":  (1200, [leg(110, 120), leg(880, 960)]),
    "2":  (3600, [leg(165, 180), leg(550, 600)]),
    "3":  (0,    [leg(120, 120), leg(1000, 1000)]),
    "3b": (0,    [leg(65, 120),  leg(1045, 1140)]),
    "4":  (0,    [leg(60, 60),   leg(600, 600)]),
    "4b": (3840, [leg(60, 60),   leg(240, 240)]),
    "4c": (0,    [leg(660, 660), leg(120, 120)]),
    "5":  (4200, [leg(60, 60),   leg(120, 120)]),
}


def cycle_after(cycle_used_min, events):
    """Cycle minutes at trip end: driving + on duty since the last restart_34."""
    cycle = cycle_used_min
    for e in events:
        if e.type == "restart_34":
            cycle = 0
        elif e.status in ("driving", "on_duty"):
            cycle += int((e.end - e.start).total_seconds() // 60)
    return cycle


class ApprovedCaseMixin:
    """Each row: (type, status, start_day, start_hhmm, end_day, end_hhmm, leg, mi_s, mi_e)."""

    def assertTrip(self, cycle_used_min, legs, rows, expected_cycle_after):
        events = plan_trip(legs, cycle_used_min / 60, START)
        self.assertEqual(len(events), len(rows), [e.type for e in events])
        for i, (e, row) in enumerate(zip(events, rows), 1):
            ty, st, d1, t1, d2, t2, li, ms, me = row
            with self.subTest(event=i, type=ty):
                self.assertIsInstance(e, Event)
                self.assertEqual(e.type, ty)
                self.assertEqual(e.status, st)
                self.assertEqual(e.start, at(d1, t1))
                self.assertEqual(e.end, at(d2, t2))
                self.assertEqual(e.leg_index, li)
                self.assertAlmostEqual(e.start_miles, ms, places=6)
                self.assertAlmostEqual(e.end_miles, me, places=6)
        self.assertEqual(cycle_after(cycle_used_min, events), expected_cycle_after)
        return events


class ApprovedCasesTest(ApprovedCaseMixin, SimpleTestCase):

    def test_case_1_break_then_11h_rest(self):
        self.assertTrip(*APPROVED_INPUTS["1"], [
            ("drive",    "driving",       1, "06:00", 1, "08:00", 0, 0,   110),
            ("pickup",   "on_duty",       1, "08:00", 1, "09:00", 0, 110, 110),
            ("drive",    "driving",       1, "09:00", 1, "17:00", 1, 0,   440),
            ("break_30", "off_duty",      1, "17:00", 1, "17:30", 1, 440, 440),
            ("drive",    "driving",       1, "17:30", 1, "18:30", 1, 440, 495),
            ("rest_10",  "sleeper_berth", 1, "18:30", 2, "04:30", 1, 495, 495),
            ("drive",    "driving",       2, "04:30", 2, "11:30", 1, 495, 880),
            ("dropoff",  "on_duty",       2, "11:30", 2, "12:30", 1, 880, 880),
        ], 2400)

    def test_case_2_cycle_restart(self):
        self.assertTrip(*APPROVED_INPUTS["2"], [
            ("drive",      "driving",  1, "06:00", 1, "09:00", 0, 0,   165),
            ("pickup",     "on_duty",  1, "09:00", 1, "10:00", 0, 165, 165),
            ("drive",      "driving",  1, "10:00", 1, "16:00", 1, 0,   330),
            ("restart_34", "off_duty", 1, "16:00", 3, "02:00", 1, 330, 330),
            ("drive",      "driving",  3, "02:00", 3, "06:00", 1, 330, 550),
            ("dropoff",    "on_duty",  3, "06:00", 3, "07:00", 1, 550, 550),
        ], 300)

    def test_case_3_fuel_stop(self):
        self.assertTrip(*APPROVED_INPUTS["3"], [
            ("drive",    "driving",       1, "06:00", 1, "08:00", 0, 0,    120),
            ("pickup",   "on_duty",       1, "08:00", 1, "09:00", 0, 120,  120),
            ("drive",    "driving",       1, "09:00", 1, "17:00", 1, 0,    480),
            ("break_30", "off_duty",      1, "17:00", 1, "17:30", 1, 480,  480),
            ("drive",    "driving",       1, "17:30", 1, "18:30", 1, 480,  540),
            ("rest_10",  "sleeper_berth", 1, "18:30", 2, "04:30", 1, 540,  540),
            ("drive",    "driving",       2, "04:30", 2, "10:10", 1, 540,  880),
            ("fuel",     "on_duty",       2, "10:10", 2, "10:40", 1, 880,  880),
            ("drive",    "driving",       2, "10:40", 2, "12:40", 1, 880,  1000),
            ("dropoff",  "on_duty",       2, "12:40", 2, "13:40", 1, 1000, 1000),
        ], 1270)

    def test_case_3b_fuel_and_break_tie_fuel_wins(self):
        events = self.assertTrip(*APPROVED_INPUTS["3b"], [
            ("drive",    "driving",       1, "06:00", 1, "08:00", 0, 0,    65),
            ("pickup",   "on_duty",       1, "08:00", 1, "09:00", 0, 65,   65),
            ("drive",    "driving",       1, "09:00", 1, "17:00", 1, 0,    440),
            ("break_30", "off_duty",      1, "17:00", 1, "17:30", 1, 440,  440),
            ("drive",    "driving",       1, "17:30", 1, "18:30", 1, 440,  495),
            ("rest_10",  "sleeper_berth", 1, "18:30", 2, "04:30", 1, 495,  495),
            ("drive",    "driving",       2, "04:30", 2, "12:30", 1, 495,  935),
            ("fuel",     "on_duty",       2, "12:30", 2, "13:00", 1, 935,  935),
            ("drive",    "driving",       2, "13:00", 2, "15:00", 1, 935,  1045),
            ("dropoff",  "on_duty",       2, "15:00", 2, "16:00", 1, 1045, 1045),
        ], 1410)
        self.assertNotIn("break_30", [e.type for e in events[7:]])

    def test_case_4_dropoff_coincides_with_11h_limit(self):
        events = self.assertTrip(*APPROVED_INPUTS["4"], [
            ("drive",    "driving",  1, "06:00", 1, "07:00", 0, 0,   60),
            ("pickup",   "on_duty",  1, "07:00", 1, "08:00", 0, 60,  60),
            ("drive",    "driving",  1, "08:00", 1, "16:00", 1, 0,   480),
            ("break_30", "off_duty", 1, "16:00", 1, "16:30", 1, 480, 480),
            ("drive",    "driving",  1, "16:30", 1, "18:30", 1, 480, 600),
            ("dropoff",  "on_duty",  1, "18:30", 1, "19:30", 1, 600, 600),
        ], 780)
        self.assertNotIn("rest_10", [e.type for e in events])

    def test_case_4b_dropoff_coincides_with_cycle_limit(self):
        events = self.assertTrip(*APPROVED_INPUTS["4b"], [
            ("drive",   "driving", 1, "06:00", 1, "07:00", 0, 0,   60),
            ("pickup",  "on_duty", 1, "07:00", 1, "08:00", 0, 60,  60),
            ("drive",   "driving", 1, "08:00", 1, "12:00", 1, 0,   240),
            ("dropoff", "on_duty", 1, "12:00", 1, "13:00", 1, 240, 240),
        ], 4260)
        self.assertNotIn("restart_34", [e.type for e in events])

    def test_case_4c_pickup_coincides_with_11h_limit(self):
        events = self.assertTrip(*APPROVED_INPUTS["4c"], [
            ("drive",    "driving",       1, "06:00", 1, "14:00", 0, 0,   480),
            ("break_30", "off_duty",      1, "14:00", 1, "14:30", 0, 480, 480),
            ("drive",    "driving",       1, "14:30", 1, "17:30", 0, 480, 660),
            ("pickup",   "on_duty",       1, "17:30", 1, "18:30", 0, 660, 660),
            ("rest_10",  "sleeper_berth", 1, "18:30", 2, "04:30", 1, 0,   0),
            ("drive",    "driving",       2, "04:30", 2, "06:30", 1, 0,   120),
            ("dropoff",  "on_duty",       2, "06:30", 2, "07:30", 1, 120, 120),
        ], 900)
        self.assertEqual([e.type for e in events].count("rest_10"), 1)

    def test_case_5_cycle_full_at_start(self):
        self.assertTrip(*APPROVED_INPUTS["5"], [
            ("restart_34", "off_duty", 1, "06:00", 2, "16:00", 0, 0,   0),
            ("drive",      "driving",  2, "16:00", 2, "17:00", 0, 0,   60),
            ("pickup",     "on_duty",  2, "17:00", 2, "18:00", 0, 60,  60),
            ("drive",      "driving",  2, "18:00", 2, "20:00", 1, 0,   120),
            ("dropoff",    "on_duty",  2, "20:00", 2, "21:00", 1, 120, 120),
        ], 300)


class EdgeCasesTest(ApprovedCaseMixin, SimpleTestCase):

    def test_zero_mile_leg_with_drive_time_goes_straight_to_pickup(self):
        legs = [Leg("A", "A", 0, 0.5), leg(120, 120)]
        self.assertTrip(0, legs, [
            ("pickup",  "on_duty", 1, "06:00", 1, "07:00", 0, 0,   0),
            ("drive",   "driving", 1, "07:00", 1, "09:00", 1, 0,   120),
            ("dropoff", "on_duty", 1, "09:00", 1, "10:00", 1, 120, 120),
        ], 240)

    def test_drive_time_rounding_to_zero_minutes_gets_one_minute(self):
        legs = [Leg("A", "B", 0.2, 0.005), leg(120, 120)]   # 0.3 min → rounds to 0 → 1
        events = self.assertTrip(0, legs, [
            ("drive",   "driving", 1, "06:00", 1, "06:01", 0, 0,   0.2),
            ("pickup",  "on_duty", 1, "06:01", 1, "07:01", 0, 0.2, 0.2),
            ("drive",   "driving", 1, "07:01", 1, "09:01", 1, 0,   120),
            ("dropoff", "on_duty", 1, "09:01", 1, "10:01", 1, 120, 120),
        ], 241)
        self.assertEqual(validate_trip(events, 0, legs), [])

    def test_under_one_minute_to_1000_miles_fuels_instead_of_stalling(self):
        # Leg 0 ends at 999.7 mi since fuel; at 1 mi/min on leg 1, 0.3 mi floors to 0 minutes.
        legs = [leg(999.7, 1000), leg(120, 120)]
        events = plan_trip(legs, 0, START)
        types = [e.type for e in events]
        self.assertEqual(types, [
            "drive", "break_30", "drive", "rest_10", "drive",
            "pickup", "fuel", "drive", "dropoff",
        ])
        fuel = events[6]
        self.assertEqual(fuel.leg_index, 1)
        self.assertEqual(fuel.status, "on_duty")
        self.assertEqual(fuel.start_miles, 0)
        self.assertEqual(fuel.end - fuel.start, timedelta(minutes=engine.FUEL_DUR))
        # Fuel stop happens at or before 1,000 miles since the trip started.
        self.assertLessEqual(events[4].end_miles, 1000)


class ValidatorTest(SimpleTestCase):

    def test_approved_cases_have_no_violations(self):
        for name, (cycle_min, legs) in APPROVED_INPUTS.items():
            with self.subTest(case=name):
                events = plan_trip(legs, cycle_min / 60, START)
                self.assertEqual(validate_trip(events, cycle_min / 60, legs), [])


class ValidatorMutationTest(SimpleTestCase):
    """Tamper with legal engine output; the validator must name the broken rule."""

    def plan(self, case):
        cycle_min, legs = APPROVED_INPUTS[case]
        return plan_trip(legs, cycle_min / 60, START), cycle_min / 60, legs

    def assertViolation(self, violations, *fragments):
        for fragment in fragments:
            self.assertTrue(any(fragment in v for v in violations),
                            f"no violation containing {fragment!r} in {violations}")

    def without(self, events, type_):
        kept = [e for e in events if e.type != type_]
        self.assertEqual(len(kept), len(events) - 1)
        return kept

    def test_removing_break_flags_8h_rule(self):
        events, cyc, legs = self.plan("1")
        self.assertViolation(validate_trip(self.without(events, "break_30"), cyc, legs),
                             "gap of 30 min", "540 driving min without a 30-min break")

    def test_removing_rest_flags_11h_and_14h_rules(self):
        events, cyc, legs = self.plan("1")
        self.assertViolation(validate_trip(self.without(events, "rest_10"), cyc, legs),
                             "gap of 600 min", "1080 driving min this shift",
                             "after shift start (limit 840)")

    def test_removing_fuel_flags_1000_mile_rule(self):
        events, cyc, legs = self.plan("3")
        self.assertViolation(validate_trip(self.without(events, "fuel"), cyc, legs),
                             "gap of 30 min", "1120 miles since last fuel")

    def test_removing_restart_flags_70h_rule(self):
        events, cyc, legs = self.plan("2")
        self.assertViolation(validate_trip(self.without(events, "restart_34"), cyc, legs),
                             "gap of 2040 min", "driving with cycle at 4200 min")

    def test_shortening_break_by_one_minute_flags_gap_and_8h_rule(self):
        events, cyc, legs = self.plan("1")
        i = [e.type for e in events].index("break_30")
        events[i] = replace(events[i], end=events[i].end - timedelta(minutes=1))
        self.assertViolation(validate_trip(events, cyc, legs),
                             "gap of 1 min", "540 driving min without a 30-min break")

    def test_mismatched_leg_distance_flags_total_miles(self):
        events, cyc, _ = self.plan("2")
        legs = [leg(165, 180), leg(551, 600)]
        self.assertEqual(validate_trip(events, cyc, legs),
                         ["trip: drove 715 miles but legs total 716"])


class SafetyNetTest(SimpleTestCase):

    def test_stall_raises_instead_of_looping(self):
        # Force drive_for = 0 in the drive segment (0 fuel minutes) while the fuel
        # check sees time left (1 minute): nothing fires and no state advances.
        with mock.patch.object(engine, "_fuel_minutes_left", side_effect=[0, 1]):
            with self.assertRaisesRegex(RuntimeError, "stalled"):
                plan_trip([leg(60, 60), leg(60, 60)], 0, START)
