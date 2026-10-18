"""Command line for the lifting log. Run `python3 lift.py --help` from the repo root."""

import argparse
import datetime as dt
import json
import sys

from . import calc, schema, store, validate


def _load_bundle(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _fail(errors):
    print("Not written. Problems found:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)


def _new_session_id(db, date):
    taken = {s["id"] for s in db["sessions"]}
    n = 1
    while f"{date}-{n}" in taken:
        n += 1
    return f"{date}-{n}"


def _materialize(bundle, session_id):
    """Turn a bundle into finished session and set rows with ids and order."""
    sess = dict(bundle["session"], id=session_id,
                logged_at=dt.datetime.now().astimezone().isoformat(timespec="seconds"))
    sets = []
    for i, st in enumerate(bundle["sets"], 1):
        row = {"id": f"{session_id}-s{i:02d}", "session_id": session_id, "order": i}
        row.update({k: v for k, v in st.items() if k not in ("id", "session_id", "order")})
        row.setdefault("superset", None)
        row.setdefault("rpe", None)
        row.setdefault("rir", None)
        row.setdefault("gear", [])
        row.setdefault("cue", None)
        row.setdefault("notes", None)
        for seg in row["segments"]:
            if "full" in seg:
                seg.setdefault("partial", 0)
        sets.append(row)
    return sess, sets


def _preview_lines(db, bundle):
    ex_by_id = {ex["id"]: ex for ex in db["exercises"] + bundle.get("new_exercises", [])}
    s = bundle["session"]
    bw = s.get("bodyweight")
    head = [
        f"Session {s['date']}  {s.get('start') or '?'}–{s.get('end') or '?'}  at {s.get('location') or '?'}",
        "  readiness {}  sleep {}  HRV {}  bodyweight {}  session RPE {}".format(
            s.get("readiness", "—"), s.get("sleep_score", "—"), s.get("hrv_ms", "—"),
            f"{bw['value']} {bw['unit']}" if bw else "—", s.get("session_rpe", "—")),
    ]
    if s.get("notes"):
        head.append(f"  notes: {s['notes']}")
    for ex in bundle.get("new_exercises", []):
        head.append(f"  NEW exercise: {ex['name']} ({ex['load_type']}, {ex['measure']}; "
                    f"primary {', '.join(ex['primary_muscles'])}; "
                    f"secondary {', '.join(ex.get('secondary_muscles', [])) or 'none'})")
    lines, current = [], None
    for i, st in enumerate(bundle["sets"], 1):
        ex = ex_by_id.get(st["exercise_id"])
        name = ex["name"] if ex else f"?? {st['exercise_id']}"
        gear = st.get("gear") or []
        gear_txt = f"   [{', '.join(gear)}]" if gear else ""
        ss = st.get("superset")
        # A superset gets one heading; its sets name their exercise inline.
        group = f"superset {ss[0]}" if ss else name
        if group != current:
            if ss:
                members = []
                for other in bundle["sets"]:
                    lab = other.get("superset")
                    if lab and lab[0] == ss[0] and lab not in [m[0] for m in members]:
                        oex = ex_by_id.get(other["exercise_id"])
                        members.append((lab, oex["name"] if oex else other["exercise_id"]))
                lines.append(f"\nSuperset {ss[0]}: " + " / ".join(f"{lab} {n}" for lab, n in sorted(members)))
            else:
                lines.append(f"\n{name}{gear_txt}")
            current = group
        segs = ", ".join(calc.format_segment(seg, ex) for seg in st["segments"]) if ex else "?"
        effort = " ".join(x for x in (
            f"@{calc._trim(st['rpe'])}" if st.get("rpe") is not None else "",
            f"{calc._trim(st['rir'])}RIR" if st.get("rir") is not None else "") if x)
        mode = "" if st.get("mode") == "bilateral" else f" ({st.get('mode')})"
        label = f"{ss} " if ss else ""
        extra = f"   [{', '.join(gear)}]" if ss and gear else ""
        lines.append(f"  {i:>2}. {label}{st['type']:<9} {segs}{mode} {effort}".rstrip() + extra)
        if st.get("cue"):
            lines.append(f"        cue: {st['cue']}")
        if st.get("notes"):
            lines.append(f"        notes: {st['notes']}")
    return head + lines


def cmd_preview(args):
    db = store.load_all()
    bundle = _load_bundle(args.bundle)
    errors = validate.bundle(bundle, db)
    print("\n".join(_preview_lines(db, bundle)))
    if errors:
        print("\nProblems to fix before writing:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    print("\nValid. Nothing written yet.")


def _write_bundle(db, bundle, session_id):
    sess, sets = _materialize(bundle, session_id)
    db["exercises"] += bundle.get("new_exercises", [])
    db["sessions"].append(sess)
    db["sets"] += sets
    errors = validate.database(db)
    if errors:
        _fail(errors)
    for name in ("exercises", "sessions", "sets"):
        store.write(name, db[name])
    return sess, sets


def cmd_add(args):
    db = store.load_all()
    bundle = _load_bundle(args.bundle)
    errors = validate.bundle(bundle, db)
    if errors:
        _fail(errors)
    sid = _new_session_id(db, bundle["session"]["date"])
    sess, sets = _write_bundle(db, bundle, sid)
    print(f"Wrote session {sid}: {len(sets)} sets, {len(bundle.get('new_exercises', []))} new exercises.")
    _report_prs(store.load_all(), sid)


def cmd_replace(args):
    """Edit in place: swap a session and its sets for a corrected bundle, keeping its id."""
    db = store.load_all()
    if not any(s["id"] == args.session_id for s in db["sessions"]):
        _fail([f"session {args.session_id} does not exist"])
    bundle = _load_bundle(args.bundle)
    db["sessions"] = [s for s in db["sessions"] if s["id"] != args.session_id]
    db["sets"] = [st for st in db["sets"] if st["session_id"] != args.session_id]
    errors = validate.bundle(bundle, db)
    if errors:
        _fail(errors)
    _write_bundle(db, bundle, args.session_id)
    print(f"Replaced session {args.session_id}.")
    _report_prs(store.load_all(), args.session_id)


def cmd_put_exercise(args):
    """Add an exercise, or replace the library entry with the same id."""
    db = store.load_all()
    ex = _load_bundle(args.file)
    errors = validate.exercise(ex)
    if errors:
        _fail(errors)
    existing = [e for e in db["exercises"] if e["id"] != ex["id"]]
    action = "Updated" if len(existing) < len(db["exercises"]) else "Added"
    db["exercises"] = existing + [ex]
    errors = validate.database(db)
    if errors:
        _fail(errors)
    store.write("exercises", db["exercises"])
    print(f"{action} exercise {ex['id']}.")


def _report_prs(db, sid):
    found = calc.session_prs(db, sid)
    if not found:
        print("No new PRs this session.")
        return
    print("New PRs:")
    for ex, what in found:
        print(f"  - {ex['name']}: {what}")


def cmd_show(args):
    db = store.load_all()
    sess = next((s for s in db["sessions"] if s["id"] == args.session_id), None)
    if sess is None:
        _fail([f"session {args.session_id} does not exist"])
    sets = sorted((st for st in db["sets"] if st["session_id"] == sess["id"]), key=lambda st: st["order"])
    bundle = {"session": sess, "sets": sets}
    print("\n".join(_preview_lines(db, bundle)))
    load = calc.training_load(sess)
    if load is not None:
        print(f"\nTraining load (session RPE × {calc.minutes(sess)} min): {load}")
    if args.raw and sess.get("raw_text"):
        print("\nOriginal text:\n" + sess["raw_text"])


def cmd_bundle(args):
    """Print a stored session as a bundle, ready to correct and pass to `replace`."""
    db = store.load_all()
    sess = next((s for s in db["sessions"] if s["id"] == args.session_id), None)
    if sess is None:
        _fail([f"session {args.session_id} does not exist"])
    sets = sorted((st for st in db["sets"] if st["session_id"] == sess["id"]), key=lambda st: st["order"])
    strip = lambda d, keys: {k: v for k, v in d.items() if k not in keys}
    print(json.dumps({"session": strip(sess, ("id", "logged_at")),
                      "sets": [strip(st, ("id", "session_id", "order")) for st in sets]},
                     indent=2, ensure_ascii=False))


def cmd_sessions(args):
    db = store.load_all()
    for s in session_order(db)[-args.last:]:
        n = sum(1 for st in db["sets"] if st["session_id"] == s["id"])
        print(f"{s['id']:<14} {s.get('start') or '':>5}–{s.get('end') or '':<5} {s.get('location') or '':<14} {n} sets")


def session_order(db):
    return calc.session_order(db)


def cmd_exercises(args):
    db = store.load_all()
    if args.json:
        rows = [dict(ex, last_unit=calc.last_unit(db, ex["id"])) for ex in db["exercises"]]
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return
    for ex in sorted(db["exercises"], key=lambda e: e["name"]):
        aliases = f"  (also: {', '.join(ex.get('aliases', []))})" if ex.get("aliases") else ""
        print(f"{ex['id']:<40} {ex['name']}{aliases}  last unit: {calc.last_unit(db, ex['id']) or '—'}")


def _exercise(db, query):
    try:
        return calc.resolve_exercise(db, query)
    except LookupError as e:
        _fail([str(e)])


def cmd_prs(args):
    db = store.load_all()
    ex = _exercise(db, args.exercise)
    result = calc.prs(db, ex)
    print(ex["name"])
    if ex["measure"] == "hold":
        for load, r in sorted(result["holds"].items()):
            print(f"  longest at {calc.show(load)}: {calc._trim(r['seconds'])}s  ({r['date']})")
        return
    b = result["e1rm"]
    if b:
        print(f"  e1RM {calc.show(b['e1rm'])}  from {calc.format_segment(b['segment'], ex)} "
              f"({b['date']})")
    else:
        print("  no e1RM yet")
    for n, r in result["rep_max"].items():
        print(f"  {n:>2}-rep max {calc.show(r['load_kg'])}  ({r['date']}, {calc.format_segment(r['segment'], ex)})")
    for kind, r in calc.best_sets(db, ex).items():
        segs = ", ".join(calc.format_segment(s, ex) for s in r["set"]["segments"])
        print(f"  best {kind} set: {segs}  ({r['date']})")


def cmd_e1rm(args):
    db = store.load_all()
    ex = _exercise(db, args.exercise)
    print(ex["name"])
    for r in calc.e1rm_history(db, ex)[-args.last:]:
        print(f"  {r['date']}  {calc.show(r['e1rm'])}  from {calc.format_segment(r['segment'], ex)}")


def cmd_volume(args):
    db = store.load_all()
    table = calc.weekly_volume(db, weeks=args.weeks)
    weeks = list(table)
    muscles = [m for m in schema.MUSCLES if any(table[w].get(m) for w in weeks)]
    if not muscles:
        print("No working sets in that window.")
        return
    print("hard sets per muscle, weeks starting Monday")
    print(f"{'':<16}" + "".join(f"{w[5:]:>8}" for w in weeks))
    for m in muscles:
        print(f"{m:<16}" + "".join(f"{calc._trim(table[w].get(m, 0)):>8}" for w in weeks))


def cmd_cues(args):
    db = store.load_all()
    ex = _exercise(db, args.exercise)
    rows = calc.cues(db, ex, last=args.last)
    print(ex["name"])
    for date, cue in rows:
        print(f"  {date}  {cue}")
    if not rows:
        print("  no cues recorded")


def cmd_load(args):
    db = store.load_all()
    for s in session_order(db)[-args.last:]:
        print(f"{s['id']:<14} {calc.training_load(s) or '—'}")


def cmd_validate(args):
    errors = validate.database(store.load_all())
    if errors:
        _fail(errors)
    print("All records valid.")


def main(argv=None):
    p = argparse.ArgumentParser(prog="lift.py", description="Lifting log")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_, *arguments):
        sp = sub.add_parser(name, help=help_)
        for a, kw in arguments:
            sp.add_argument(*a, **kw)
        sp.set_defaults(fn=fn)

    add("preview", cmd_preview, "check a session bundle and print it, writing nothing", (("bundle",), {}))
    add("add", cmd_add, "write a session bundle as a new session", (("bundle",), {}))
    add("replace", cmd_replace, "replace a stored session with a corrected bundle",
        (("session_id",), {}), (("bundle",), {}))
    add("bundle", cmd_bundle, "print a stored session as an editable bundle", (("session_id",), {}))
    add("put-exercise", cmd_put_exercise, "add or update one library exercise from a JSON file", (("file",), {}))
    add("show", cmd_show, "print a stored session",
        (("session_id",), {}), (("--raw",), {"action": "store_true", "help": "include the original text"}))
    add("sessions", cmd_sessions, "list recent sessions", (("--last",), {"type": int, "default": 10}))
    add("exercises", cmd_exercises, "list the exercise library",
        (("--json",), {"action": "store_true"}))
    add("prs", cmd_prs, "PRs, rep maxes, and best sets for an exercise", (("exercise",), {}))
    add("e1rm", cmd_e1rm, "e1RM per session for an exercise",
        (("exercise",), {}), (("--last",), {"type": int, "default": 20}))
    add("volume", cmd_volume, "hard sets per muscle per week", (("--weeks",), {"type": int, "default": 4}))
    add("cues", cmd_cues, "recent cues for an exercise",
        (("exercise",), {}), (("--last",), {"type": int, "default": 5}))
    add("load", cmd_load, "session RPE × minutes per session", (("--last",), {"type": int, "default": 10}))
    add("validate", cmd_validate, "check every stored record")

    args = p.parse_args(argv)
    args.fn(args)
