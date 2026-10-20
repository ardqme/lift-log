"""Checks every record against the rules in docs/schema.md.

Each check returns a list of plain-language problems; an empty list means valid.
"""

import re

from . import schema

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SUPERSET = re.compile(r"^[A-Z][1-9]$")
YOUTUBE = re.compile(r"^https?://(?:www\.)?(?:youtu\.be/|youtube\.com/(?:watch\?v=|shorts/))([A-Za-z0-9_-]{11})(?:[?&#].*)?$")


def youtube_id(url):
    """The 11-character video id from a youtu.be, watch?v=, or shorts URL; None if it isn't one."""
    m = YOUTUBE.match(url) if isinstance(url, str) else None
    return m.group(1) if m else None


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _opt_range(errs, where, rec, key, lo, hi):
    v = rec.get(key)
    if v is None:
        return
    if not _num(v) or not (lo <= v <= hi):
        errs.append(f"{where}: {key} must be a number from {lo} to {hi} (got {v!r})")


def exercise(ex):
    where = f"exercise {ex.get('id', '?')}"
    errs = []
    if not isinstance(ex.get("id"), str) or not SLUG.match(ex["id"]):
        errs.append(f"{where}: id must be lowercase words joined by hyphens")
    if not isinstance(ex.get("name"), str) or not ex["name"].strip():
        errs.append(f"{where}: name is required")
    if not isinstance(ex.get("aliases", []), list):
        errs.append(f"{where}: aliases must be a list")
    for key, allowed in (("equipment", schema.EQUIPMENT), ("load_type", schema.LOAD_TYPES),
                         ("measure", schema.MEASURES)):
        if ex.get(key) not in allowed:
            errs.append(f"{where}: {key} must be one of {allowed} (got {ex.get(key)!r})")
    share = ex.get("bodyweight_share")
    if ex.get("load_type") == "bodyweight":
        if not _num(share) or not (0 < share <= 1.5):
            errs.append(f"{where}: bodyweight exercises need a bodyweight_share between 0 and 1.5")
        if not ex.get("bodyweight_share_source"):
            errs.append(f"{where}: bodyweight_share_source must say where the share came from")
    elif share is not None:
        errs.append(f"{where}: only bodyweight exercises carry a bodyweight_share")
    prim = ex.get("primary_muscles")
    if not isinstance(prim, list) or not prim:
        errs.append(f"{where}: primary_muscles must list at least one muscle")
    for m in (prim or []) + (ex.get("secondary_muscles") or []):
        if m not in schema.MUSCLES:
            errs.append(f"{where}: unknown muscle {m!r}; allowed: {schema.MUSCLES}")
    overlap = set(prim or []) & set(ex.get("secondary_muscles") or [])
    if overlap:
        errs.append(f"{where}: {sorted(overlap)} listed as both primary and secondary")
    return errs


def session(s, require_id=True):
    where = f"session {s.get('id', '(new)')}"
    errs = []
    if require_id and not isinstance(s.get("id"), str):
        errs.append(f"{where}: id is missing")
    if not isinstance(s.get("date"), str) or not DATE.match(s["date"]):
        errs.append(f"{where}: date must be YYYY-MM-DD")
    for key in ("start", "end"):
        v = s.get(key)
        if v is not None and (not isinstance(v, str) or not TIME.match(v)):
            errs.append(f"{where}: {key} must be HH:MM in 24-hour time")
    _opt_range(errs, where, s, "readiness", 1, 10)
    _opt_range(errs, where, s, "sleep_score", 0, 100)
    _opt_range(errs, where, s, "hrv_ms", 1, 300)
    _opt_range(errs, where, s, "session_rpe", 1, 10)
    bw = s.get("bodyweight")
    if bw is not None:
        if not isinstance(bw, dict) or not _num(bw.get("value")) or bw.get("unit") not in schema.UNITS:
            errs.append(f"{where}: bodyweight must be {{\"value\": number, \"unit\": \"kg\" or \"lb\"}}")
    return errs


def segment(seg, ex, where):
    errs = []
    if seg.get("side") not in schema.SIDES:
        errs.append(f"{where}: side must be one of {schema.SIDES}")
    if seg.get("unit") not in schema.UNITS:
        errs.append(f"{where}: unit must be kg or lb")
    load = seg.get("load")
    if not _num(load):
        errs.append(f"{where}: load must be a number")
    elif load < 0 and (ex or {}).get("load_type") != "bodyweight":
        errs.append(f"{where}: negative load (assistance) only applies to bodyweight exercises")
    measure = (ex or {}).get("measure", "reps")
    if measure == "reps":
        if not _int(seg.get("full")) or seg["full"] < 0:
            errs.append(f"{where}: full reps must be a whole number")
        if not _int(seg.get("partial", 0)) or seg.get("partial", 0) < 0:
            errs.append(f"{where}: partial reps must be a whole number")
        if "seconds" in seg:
            errs.append(f"{where}: seconds only belong on hold exercises")
    else:
        if not _num(seg.get("seconds")) or seg["seconds"] <= 0:
            errs.append(f"{where}: hold exercises need seconds")
        if "full" in seg or "partial" in seg:
            errs.append(f"{where}: hold exercises record seconds, not reps")
    return errs


def set_(st, exercises_by_id, require_id=True):
    where = f"set {st.get('id', '#' + str(st.get('order', '?')))}"
    errs = []
    if require_id:
        for key in ("id", "session_id"):
            if not isinstance(st.get(key), str):
                errs.append(f"{where}: {key} is missing")
        if not _int(st.get("order")) or st["order"] < 1:
            errs.append(f"{where}: order must be a whole number from 1")
    ex = exercises_by_id.get(st.get("exercise_id"))
    if ex is None:
        errs.append(f"{where}: exercise {st.get('exercise_id')!r} is not in the library")
    if st.get("type") not in schema.SET_TYPES:
        errs.append(f"{where}: type must be one of {schema.SET_TYPES}")
    if st.get("mode") not in schema.MODES:
        errs.append(f"{where}: mode must be one of {schema.MODES}")
    ss = st.get("superset")
    if ss is not None and (not isinstance(ss, str) or not SUPERSET.match(ss)):
        errs.append(f"{where}: superset label must look like A1, A2, B1")
    rpe, rir = st.get("rpe"), st.get("rir")
    if rpe is not None and (not _num(rpe) or not (1 <= rpe <= 10) or (rpe * 2) % 1):
        errs.append(f"{where}: rpe must be 1 to 10 in half steps")
    if rir is not None and (not _num(rir) or not (0 <= rir <= 10) or (rir * 2) % 1):
        errs.append(f"{where}: rir must be 0 to 10 in half steps")
    if not isinstance(st.get("gear", []), list):
        errs.append(f"{where}: gear must be a list")
    if st.get("video") is not None and youtube_id(st["video"]) is None:
        errs.append(f"{where}: video must be a YouTube link (youtu.be/ID or youtube.com/watch?v=ID)")
    segs = st.get("segments")
    if not isinstance(segs, list) or not segs:
        errs.append(f"{where}: at least one segment is required")
        return errs
    for i, seg in enumerate(segs, 1):
        errs += segment(seg, ex, f"{where} segment {i}")
    sides = {seg.get("side") for seg in segs}
    if st.get("mode") == "bilateral" and sides != {"both"}:
        errs.append(f"{where}: a bilateral set's segments must all have side 'both'")
    if st.get("mode") in ("alternating", "one-side") and "both" in sides:
        errs.append(f"{where}: an {st.get('mode')} set logs each side as its own segment (left/right)")
    if st.get("type") in ("drop", "myo-rep") and len(segs) < 2:
        errs.append(f"{where}: a {st['type']} set needs at least two segments")
    return errs


def database(db):
    """Validate everything, including links between files."""
    errs = []
    ex_by_id = {}
    for ex in db["exercises"]:
        errs += exercise(ex)
        if ex.get("id") in ex_by_id:
            errs.append(f"exercise id {ex['id']!r} appears twice")
        ex_by_id[ex.get("id")] = ex
    session_ids = set()
    for s in db["sessions"]:
        errs += session(s)
        if s.get("id") in session_ids:
            errs.append(f"session id {s['id']!r} appears twice")
        session_ids.add(s.get("id"))
    set_ids = set()
    for st in db["sets"]:
        errs += set_(st, ex_by_id)
        if st.get("session_id") not in session_ids:
            errs.append(f"set {st.get('id')}: session {st.get('session_id')!r} does not exist")
        if st.get("id") in set_ids:
            errs.append(f"set id {st['id']!r} appears twice")
        set_ids.add(st.get("id"))
    return errs


def bundle(b, db):
    """Validate a session bundle (session + sets + any new exercises) before it is written."""
    errs = []
    ex_by_id = {ex["id"]: ex for ex in db["exercises"]}
    for ex in b.get("new_exercises", []):
        errs += exercise(ex)
        if ex.get("id") in ex_by_id:
            errs.append(f"new exercise {ex.get('id')!r} is already in the library")
        ex_by_id[ex.get("id")] = ex
    if not isinstance(b.get("session"), dict):
        return errs + ["bundle has no session"]
    errs += session(b["session"], require_id=False)
    if not b.get("sets"):
        errs.append("bundle has no sets")
    for i, st in enumerate(b.get("sets", []), 1):
        st = dict(st, order=i)
        errs += set_(st, ex_by_id, require_id=False)
    return errs
