"""Run from the repo root: python3 -m unittest discover tests"""

import datetime as dt
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from liftlog import calc, cli, store, validate

SQUAT = {"id": "low-bar-back-squat", "name": "Low-bar Barbell Back Squat", "aliases": ["low bar squat"],
         "equipment": "barbell", "load_type": "total", "measure": "reps", "bodyweight_share": None,
         "primary_muscles": ["quads", "glutes"], "secondary_muscles": ["adductors", "spinal-erectors"],
         "notes": None}
CURL = {"id": "dumbbell-curl", "name": "Dumbbell Curl", "aliases": [], "equipment": "dumbbell",
        "load_type": "per-hand", "measure": "reps", "bodyweight_share": None,
        "primary_muscles": ["biceps"], "secondary_muscles": ["forearms"], "notes": None}
DIP = {"id": "parallel-bar-dip", "name": "Parallel-bar Dip", "aliases": ["dip"], "equipment": "bodyweight",
       "load_type": "bodyweight", "measure": "reps", "bodyweight_share": 0.9,
       "bodyweight_share_source": "test value", "primary_muscles": ["chest", "triceps"],
       "secondary_muscles": ["front-delts"], "notes": None}
PLANK = {"id": "plank", "name": "Plank", "aliases": [], "equipment": "bodyweight", "load_type": "total",
         "measure": "hold", "bodyweight_share": None, "primary_muscles": ["abs"], "secondary_muscles": [],
         "notes": None}


def seg(load, full, unit="kg", side="both", partial=0):
    return {"load": load, "unit": unit, "side": side, "full": full, "partial": partial}


def sset(ex, type_, segments, mode="bilateral", **kw):
    return dict({"exercise_id": ex, "type": type_, "mode": mode, "segments": segments}, **kw)


def bundle(date, sets, new=(), **session):
    return {"session": dict({"date": date, "start": "05:15", "end": "06:45", "location": "HOTT Barbell",
                             "raw_text": "test"}, **session),
            "sets": sets, "new_exercises": list(new)}


class LogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["LIFTLOG_DATA"] = self.tmp.name

    def tearDown(self):
        del os.environ["LIFTLOG_DATA"]
        self.tmp.cleanup()

    def run_cli(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(list(argv))
        return buf.getvalue()

    def add(self, b):
        path = Path(self.tmp.name) / "bundle.json"
        path.write_text(json.dumps(b))
        return self.run_cli("add", str(path))

    # --- e1RM rules ---

    def test_rpe_raises_e1rm_like_mark_described(self):
        at8 = {"type": "regular", "rpe": 8, "rir": None}
        at9 = {"type": "regular", "rpe": 9, "rir": None}
        # 300 x 3 @8 = 5 reps to failure; @9 = 4
        self.assertAlmostEqual(calc.epley(300, 3 + calc.reps_in_reserve(at8)), 350)
        self.assertAlmostEqual(calc.epley(300, 3 + calc.reps_in_reserve(at9)), 340)

    def test_failure_set_has_no_reserve_and_rir_wins_over_rpe(self):
        self.assertEqual(calc.reps_in_reserve({"type": "failure", "rpe": 7, "rir": None}), 0)
        self.assertEqual(calc.reps_in_reserve({"type": "regular", "rpe": 7, "rir": 1}), 1)
        self.assertEqual(calc.reps_in_reserve({"type": "regular", "rpe": None, "rir": None}), 0)

    def test_e1rm_excludes_warmups_easy_sets_high_reps_and_other_types(self):
        self.add(bundle("2026-10-18", [
            sset("low-bar-back-squat", "warm-up", [seg(140, 3)]),
            sset("low-bar-back-squat", "regular", [seg(150, 1)], rpe=5),       # too easy
            sset("low-bar-back-squat", "regular", [seg(60, 15)]),              # too many reps
            sset("low-bar-back-squat", "drop", [seg(130, 5), seg(100, 5)]),   # not a PR type
            sset("low-bar-back-squat", "regular", [seg(100, 6)], rpe=6),
        ], new=[SQUAT]))
        db = store.load_all()
        best = calc.prs(db, SQUAT)["e1rm"]
        self.assertAlmostEqual(best["e1rm"], 100 * (1 + 10 / 30))
        # rep maxes ignore warm-ups and drops but not the easy single or the 15-rep set
        rm = calc.prs(db, SQUAT)["rep_max"]
        self.assertEqual(rm[1]["load_kg"], 150)
        self.assertEqual(rm[10]["load_kg"], 60)

    def test_partials_never_count(self):
        self.add(bundle("2026-10-18", [sset("dumbbell-curl", "failure", [seg(30, 8, "lb", partial=4)])],
                        new=[CURL]))
        rm = calc.prs(store.load_all(), CURL)["rep_max"]
        self.assertIn(8, rm)
        self.assertNotIn(9, rm)

    def test_units_compete_fairly(self):
        self.add(bundle("2026-10-11", [sset("low-bar-back-squat", "regular", [seg(225, 5, "lb")])], new=[SQUAT]))
        self.add(bundle("2026-10-18", [sset("low-bar-back-squat", "regular", [seg(100, 5)])]))
        rm5 = calc.prs(store.load_all(), SQUAT)["rep_max"][5]
        self.assertEqual(rm5["date"], "2026-10-11")  # 225 lb = 102.1 kg beats 100 kg

    def test_bodyweight_share_and_carried_bodyweight(self):
        self.add(bundle("2026-10-11", [sset("parallel-bar-dip", "regular", [seg(0, 10, "lb")])], new=[DIP],
                        bodyweight={"value": 100, "unit": "kg"}))
        self.add(bundle("2026-10-18", [sset("parallel-bar-dip", "regular", [seg(20, 5)])]))  # no bodyweight
        db = store.load_all()
        hist = calc.e1rm_history(db, DIP)
        self.assertAlmostEqual(hist[0]["load_kg"], 90)
        self.assertAlmostEqual(hist[1]["load_kg"], 110)  # 100 kg carried forward x 0.9 + 20

    # --- holds, volume, PR detection ---

    def test_hold_records_longest_at_load(self):
        self.add(bundle("2026-10-18", [sset("plank", "regular", [{"load": 0, "unit": "kg", "side": "both",
                                                                  "seconds": 60}])], new=[PLANK]))
        holds = calc.prs(store.load_all(), PLANK)["holds"]
        self.assertEqual(holds[0]["seconds"], 60)

    def test_weekly_volume_counts_sets_once_and_halves_secondaries(self):
        self.add(bundle("2026-10-13", [
            sset("dumbbell-curl", "warm-up", [seg(15, 10, "lb")]),
            sset("dumbbell-curl", "regular", [seg(30, 10, "lb", "left"), seg(30, 10, "lb", "right")],
                 mode="one-side"),
            sset("dumbbell-curl", "drop", [seg(30, 10, "lb"), seg(20, 5, "lb"), seg(10, 4, "lb")]),
        ], new=[CURL]))
        vol = calc.weekly_volume(store.load_all(), weeks=1, today=dt.date(2026, 10, 18))
        self.assertEqual(vol["2026-10-12"]["biceps"], 2)
        self.assertEqual(vol["2026-10-12"]["forearms"], 1)

    def test_session_prs_against_history_only(self):
        first = self.add(bundle("2026-10-11", [sset("low-bar-back-squat", "regular", [seg(100, 5)])], new=[SQUAT]))
        self.assertIn("baseline", first)
        self.assertNotIn("heaviest", first)
        out = self.add(bundle("2026-10-18", [sset("low-bar-back-squat", "regular", [seg(105, 5)])]))
        self.assertIn("heaviest for 1–5 reps: 105 kg", out)
        self.assertNotIn("6 reps", out)

    # --- validation and editing ---

    def test_validation_catches_common_mistakes(self):
        db = {"exercises": [SQUAT, CURL], "sessions": [], "sets": []}
        bad = bundle("2026-10-18", [
            sset("low-bar-back-squat", "regular", [seg(-10, 5)]),
            sset("dumbbell-curl", "regular", [seg(30, 10, "lb")], mode="one-side"),
            sset("dumbbell-curl", "drop", [seg(30, 10, "lb")]),
            sset("nope", "regular", [seg(1, 1)]),
        ])
        msgs = " | ".join(validate.bundle(bad, db))
        for fragment in ("negative load", "left/right", "at least two segments", "not in the library"):
            self.assertIn(fragment, msgs)

    def test_replace_edits_in_place_and_keeps_id(self):
        self.add(bundle("2026-10-18", [sset("low-bar-back-squat", "regular", [seg(100, 6)], rpe=6)],
                        new=[SQUAT]))
        exported = json.loads(self.run_cli("bundle", "2026-10-18-1"))
        exported["sets"][0]["segments"][0]["full"] = 7
        path = Path(self.tmp.name) / "fix.json"
        path.write_text(json.dumps(exported))
        self.run_cli("replace", "2026-10-18-1", str(path))
        db = store.load_all()
        self.assertEqual(len(db["sessions"]), 1)
        self.assertEqual(db["sets"][0]["id"], "2026-10-18-1-s01")
        self.assertEqual(db["sets"][0]["segments"][0]["full"], 7)
        self.assertEqual(validate.database(db), [])

    def test_last_unit_and_alias_lookup(self):
        self.add(bundle("2026-10-18", [sset("dumbbell-curl", "regular", [seg(30, 10, "lb")])], new=[CURL, SQUAT]))
        db = store.load_all()
        self.assertEqual(calc.last_unit(db, "dumbbell-curl"), "lb")
        self.assertEqual(calc.resolve_exercise(db, "Low Bar Squat")["id"], "low-bar-back-squat")


if __name__ == "__main__":
    unittest.main()
