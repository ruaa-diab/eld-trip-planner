"""Log builder tests. Inputs come from the approved engine cases (DESIGN.md §5)."""

from datetime import date, datetime

from django.test import SimpleTestCase

from trips.hos.engine import Leg, plan_trip
from trips.services.logs import build_logs
from trips.tests.test_hos_engine import APPROVED_INPUTS, START

START_LABEL, PICKUP_LABEL, DROPOFF_LABEL = "Chicago, IL", "Rockford, IL", "Denver, CO"


def named_legs(legs):
    """Approved legs with real-looking labels."""
    (l0, l1) = legs
    return [Leg(START_LABEL, PICKUP_LABEL, l0.distance_miles, l0.drive_hours),
            Leg(PICKUP_LABEL, DROPOFF_LABEL, l1.distance_miles, l1.drive_hours)]


def fake_names(events, legs):
    """What name_stops would return, with predictable stop names like 'rest_10 @ 495'."""
    names = []
    for e in events:
        if e.type in ("pickup", "dropoff"):
            names.append(legs[e.leg_index].end_name)
        elif e.type == "drive":
            names.append(None)
        else:
            names.append(f"{e.type} @ {e.start_miles:g}")
    return names


def build(cycle_min, legs, start=START):
    legs = named_legs(legs)
    events = plan_trip(legs, cycle_min / 60, start)
    return build_logs(events, fake_names(events, legs), legs, cycle_min / 60, start)


def segs(sheet):
    return [(s.status, s.start_min, s.end_min) for s in sheet.segments]


def remarks(sheet):
    return [(r.minute, r.location, r.description) for r in sheet.remarks]


def totals(off, sleeper, driving, on):
    return {"off_duty": off, "sleeper_berth": sleeper, "driving": driving, "on_duty": on}


class Case1LogTest(SimpleTestCase):

    def setUp(self):
        self.log = build(*APPROVED_INPUTS["1"])

    def test_trip_totals(self):
        self.assertEqual(self.log.days, 2)
        self.assertAlmostEqual(self.log.total_miles, 990)
        self.assertEqual(self.log.cycle_after_min, 2400)
        self.assertEqual(self.log.hours_available_tomorrow, 30)

    def test_day_1(self):
        d = self.log.sheets[0]
        self.assertEqual(d.date, date(2026, 1, 5))
        self.assertEqual((d.from_location, d.to_location), (START_LABEL, "rest_10 @ 495"))
        self.assertEqual(segs(d), [
            ("off_duty", 0, 360), ("driving", 360, 480), ("on_duty", 480, 540),
            ("driving", 540, 1020), ("off_duty", 1020, 1050), ("driving", 1050, 1110),
            ("sleeper_berth", 1110, 1440),
        ])
        self.assertEqual(d.totals, totals(390, 330, 660, 60))
        # SPEC §9 counts off duty + sleeper together: "off 12, driving 11, on duty 1".
        self.assertEqual(d.totals["off_duty"] + d.totals["sleeper_berth"], 12 * 60)
        self.assertAlmostEqual(d.miles, 605)
        self.assertEqual(remarks(d), [
            (360, START_LABEL, "Reported for work"),
            (480, PICKUP_LABEL, "Pickup"),
            (540, PICKUP_LABEL, "Driving"),
            (1020, "break_30 @ 440", "30-min break"),
            (1050, "break_30 @ 440", "Driving"),
            (1110, "rest_10 @ 495", "10-hour rest"),
        ])
        self.assertEqual((d.recap.on_duty_today, d.recap.a, d.recap.b, d.recap.c),
                         (720, 1920, 2280, 1920))

    def test_day_2(self):
        d = self.log.sheets[1]
        self.assertEqual(d.date, date(2026, 1, 6))
        self.assertEqual((d.from_location, d.to_location), ("rest_10 @ 495", DROPOFF_LABEL))
        self.assertEqual(segs(d), [
            ("sleeper_berth", 0, 270), ("driving", 270, 690),
            ("on_duty", 690, 750), ("off_duty", 750, 1440),
        ])
        self.assertEqual(d.totals, totals(690, 270, 420, 60))
        self.assertEqual(d.totals["off_duty"] + d.totals["sleeper_berth"], 16 * 60)
        self.assertAlmostEqual(d.miles, 385)
        self.assertEqual(remarks(d), [
            (270, "rest_10 @ 495", "Driving"),
            (690, DROPOFF_LABEL, "Dropoff"),
            (750, DROPOFF_LABEL, "Off duty"),
        ])
        self.assertEqual((d.recap.on_duty_today, d.recap.a, d.recap.b, d.recap.c),
                         (480, 2400, 1800, 2400))


class Case2LogTest(SimpleTestCase):
    RESTART = "restart_34 @ 330"

    def setUp(self):
        self.log = build(*APPROVED_INPUTS["2"])

    def test_trip_totals(self):
        self.assertEqual(self.log.days, 3)
        self.assertAlmostEqual(self.log.total_miles, 715)
        self.assertEqual(self.log.cycle_after_min, 300)
        self.assertEqual(self.log.hours_available_tomorrow, 65)

    def test_day_1_reaches_70_hours(self):
        d = self.log.sheets[0]
        self.assertEqual(segs(d), [
            ("off_duty", 0, 360), ("driving", 360, 540), ("on_duty", 540, 600),
            ("driving", 600, 960), ("off_duty", 960, 1440),
        ])
        self.assertEqual(d.totals, totals(840, 0, 540, 60))
        self.assertAlmostEqual(d.miles, 495)
        self.assertEqual(remarks(d), [
            (360, START_LABEL, "Reported for work"),
            (540, PICKUP_LABEL, "Pickup"),
            (600, PICKUP_LABEL, "Driving"),
            (960, self.RESTART, "34-hour restart"),
        ])
        self.assertEqual((d.recap.on_duty_today, d.recap.a, d.recap.b), (600, 4200, 0))

    def test_day_2_full_off_duty_sheet(self):
        d = self.log.sheets[1]
        self.assertEqual(d.date, date(2026, 1, 6))
        self.assertEqual(segs(d), [("off_duty", 0, 1440)])
        self.assertEqual(d.totals, totals(1440, 0, 0, 0))
        self.assertEqual(d.miles, 0)
        self.assertEqual((d.from_location, d.to_location), (self.RESTART, self.RESTART))
        self.assertEqual(remarks(d), [(0, self.RESTART, "34-hour restart (continuing)")])
        # Option (a): restart not finished yet, so A is not reset.
        self.assertEqual((d.recap.on_duty_today, d.recap.a, d.recap.b, d.recap.c),
                         (0, 4200, 0, 4200))

    def test_day_3_after_restart(self):
        d = self.log.sheets[2]
        self.assertEqual(segs(d), [
            ("off_duty", 0, 120), ("driving", 120, 360),
            ("on_duty", 360, 420), ("off_duty", 420, 1440),
        ])
        self.assertEqual(d.totals, totals(1140, 0, 240, 60))
        self.assertAlmostEqual(d.miles, 220)
        self.assertEqual(remarks(d), [
            (120, self.RESTART, "Driving"),
            (360, DROPOFF_LABEL, "Dropoff"),
            (420, DROPOFF_LABEL, "Off duty"),
        ])
        self.assertEqual((d.recap.on_duty_today, d.recap.a, d.recap.b, d.recap.c),
                         (300, 300, 3900, 300))


class MidnightAndEdgeTest(SimpleTestCase):
    def test_drive_crossing_midnight_is_split_with_prorated_miles(self):
        # 23:00 start, 120 mi in 120 min: 60 min / 60 mi before midnight, the rest after.
        log = build(0, [Leg("", "", 120, 2), Leg("", "", 60, 1)],
                    start=datetime(2026, 1, 5, 23, 0))
        d1, d2 = log.sheets
        self.assertEqual(segs(d1), [("off_duty", 0, 1380), ("driving", 1380, 1440)])
        self.assertAlmostEqual(d1.miles, 60)
        self.assertEqual((d1.from_location, d1.to_location), (START_LABEL, START_LABEL))
        self.assertEqual(remarks(d1), [(1380, START_LABEL, "Reported for work")])

        self.assertEqual(segs(d2), [
            ("driving", 0, 60), ("on_duty", 60, 120), ("driving", 120, 180),
            ("on_duty", 180, 240), ("off_duty", 240, 1440),
        ])
        self.assertAlmostEqual(d2.miles, 120)       # 60 from the split drive + 60 on leg 1
        self.assertEqual(d2.from_location, START_LABEL)
        self.assertEqual(remarks(d2)[0], (60, PICKUP_LABEL, "Pickup"))
        self.assertAlmostEqual(log.total_miles, 180)

    def test_dropoff_ending_at_midnight_makes_no_empty_sheet(self):
        log = build(0, [Leg("", "", 60, 1), Leg("", "", 60, 1)],
                    start=datetime(2026, 1, 5, 20, 0))
        self.assertEqual(log.days, 1)
        self.assertEqual(log.sheets[0].segments[-1].end_min, 1440)
        self.assertEqual(log.sheets[0].totals, totals(1200, 0, 120, 120))

    def test_trip_starting_with_restart_remarks_it_at_start_location(self):
        log = build(*APPROVED_INPUTS["5"])
        self.assertEqual(remarks(log.sheets[0]), [(360, START_LABEL, "34-hour restart")])
        self.assertEqual(log.cycle_after_min, 300)

    def test_b_and_hours_available_never_negative(self):
        log = build(*APPROVED_INPUTS["4b"])           # ends at 4260 min (71 h)
        self.assertEqual(log.cycle_after_min, 4260)
        self.assertEqual(log.sheets[-1].recap.b, 0)
        self.assertEqual(log.hours_available_tomorrow, 0)


class AllApprovedCasesTest(SimpleTestCase):

    def test_every_sheet_sums_to_1440_with_contiguous_segments(self):
        for name, (cycle_min, legs) in APPROVED_INPUTS.items():
            log = build(cycle_min, legs)
            for i, d in enumerate(log.sheets, 1):
                with self.subTest(case=name, day=i):
                    self.assertEqual(sum(d.totals.values()), 1440)
                    self.assertEqual(d.segments[0].start_min, 0)
                    self.assertEqual(d.segments[-1].end_min, 1440)
                    for a, b in zip(d.segments, d.segments[1:]):
                        self.assertEqual(a.end_min, b.start_min)
                        self.assertNotEqual(a.status, b.status)
                    self.assertTrue(d.remarks)
            with self.subTest(case=name, check="miles"):
                self.assertAlmostEqual(log.total_miles,
                                       sum(l.distance_miles for l in legs), places=6)
