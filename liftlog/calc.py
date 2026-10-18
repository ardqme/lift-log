"""Everything computed from the log: e1RM, PRs, best sets, weekly volume, cues.

Nothing here is stored. Loads are compared in kilograms internally and shown
in both units, so a set entered in pounds and one entered in kilograms compete
fairly without either entry being rewritten.
"""

import datetime as dt
from collections import defaultdict

from . import schema


# ---------- lookups ----------

def norm(text):
    return " ".join(str(text).lower().replace("-", " ").split())


def resolve_exercise(db, query):
    """Find an exercise by id, name, or alias. Raises LookupError with near matches."""
    q = norm(query)
    for ex in db["exercises"]:
        names = [ex["id"], ex["name"]] + ex.get("aliases", [])
        if q in (norm(n) for n in names):
            return ex
    near = [ex["name"] for ex in db["exercises"]
            if any(w in norm(" ".join([ex["name"]] + ex.get("aliases", []))) for w in q.split())]
    raise LookupError(f"no exercise matches {query!r}" + (f"; did you mean: {', '.join(near)}" if near else ""))


def session_order(db):
    """Sessions oldest first."""
    return sorted(db["sessions"], key=lambda s: (s["date"], s.get("start") or "", s["id"]))


def sets_for(db, exercise_id):
    return [st for st in db["sets"] if st["exercise_id"] == exercise_id]


# ---------- units and load ----------

def to_kg(load, unit):
    return load if unit == "kg" else load / schema.LB_PER_KG


def show(kg):
    """'100 kg / 220.5 lb'"""
    return f"{_trim(round(kg, 1))} kg / {_trim(round(kg * schema.LB_PER_KG, 1))} lb"


def _trim(x):
    return int(x) if float(x).is_integer() else x


def bodyweight_kg(db, session):
    """The session's bodyweight, or the most recent earlier one recorded."""
    best = None
    for s in session_order(db):
        if s.get("bodyweight"):
            best = to_kg(s["bodyweight"]["value"], s["bodyweight"]["unit"])
        if s["id"] == session["id"]:
            break
    return best


def effective_kg(seg, ex, bw_kg):
    """The load a segment actually moved. None if a bodyweight lift has no bodyweight on record."""
    added = to_kg(seg["load"], seg["unit"])
    if ex["load_type"] != "bodyweight":
        return added
    if bw_kg is None:
        return None
    return bw_kg * ex["bodyweight_share"] + added


def format_segment(seg, ex):
    side = {"left": "L ", "right": "R "}.get(seg.get("side"), "")
    load = _trim(seg["load"])
    if ex["load_type"] == "bodyweight":
        w = "BW" if load == 0 else f"BW{'+' if load > 0 else ''}{load}{seg['unit']}"
    else:
        w = f"{load}{seg['unit']}"
    if ex["measure"] == "hold":
        return f"{side}{w}×{_trim(seg['seconds'])}s"
    reps = f"{seg['full']}" + (f"/{seg['partial']}" if seg.get("partial") else "")
    return f"{side}{w}×{reps}"


# ---------- effort and e1RM ----------

def reps_in_reserve(st):
    """Failure sets have none left; otherwise RIR as entered, or 10 - RPE, or 0 if unrated."""
    if st["type"] == "failure":
        return 0
    if st.get("rir") is not None:
        return st["rir"]
    if st.get("rpe") is not None:
        return 10 - st["rpe"]
    return 0


def epley(load_kg, reps_to_failure):
    if reps_to_failure <= 1:
        return load_kg
    return load_kg * (1 + reps_to_failure / 30)


def pr_candidates(db, ex):
    """Every full-rep segment from a regular or failure set of this exercise, with its e1RM.

    e1RM is None when the segment is outside the estimate's rules (over 12 reps,
    easier than RPE 6, or a bodyweight lift with no bodyweight on record).
    """
    sessions = {s["id"]: s for s in db["sessions"]}
    out = []
    for st in sets_for(db, ex["id"]):
        if st["type"] not in schema.PR_SET_TYPES:
            continue
        sess = sessions[st["session_id"]]
        bw = bodyweight_kg(db, sess)
        rir = reps_in_reserve(st)
        for seg in st["segments"]:
            load = effective_kg(seg, ex, bw)
            row = {"date": sess["date"], "session_id": sess["id"], "set_id": st["id"],
                   "side": seg["side"], "load_kg": load, "segment": seg, "e1rm": None}
            if ex["measure"] == "hold":
                row["seconds"] = seg["seconds"]
            else:
                row["full"] = seg["full"]
                ok = (load is not None and load > 0 and 1 <= seg["full"] <= schema.E1RM_MAX_REPS
                      and rir <= schema.E1RM_MAX_RIR)
                if ok:
                    row["e1rm"] = epley(load, seg["full"] + rir)
            out.append(row)
    return out


# ---------- PRs ----------

def session_rank(db):
    """Each session's position in history, oldest = 0."""
    return {s["id"]: i for i, s in enumerate(session_order(db))}


def prs(db, ex, upto=None, inclusive=True):
    """Best e1RM and rep maxes (reps exercises) or longest holds (hold exercises).

    `upto` is a session id: history is cut at that session, keeping it if `inclusive`.
    """
    rows = pr_candidates(db, ex)
    if upto is not None:
        rank = session_rank(db)
        cut = rank[upto]
        rows = [r for r in rows if rank[r["session_id"]] < cut or (inclusive and rank[r["session_id"]] == cut)]
    if ex["measure"] == "hold":
        by_load = {}
        for r in rows:
            if r["load_kg"] is None:
                continue
            key = round(r["load_kg"], 1)
            if key not in by_load or r["seconds"] > by_load[key]["seconds"]:
                by_load[key] = r
        return {"holds": by_load}
    e1 = [r for r in rows if r["e1rm"] is not None]
    best = max(e1, key=lambda r: r["e1rm"]) if e1 else None
    rep_max = {}
    for n in schema.REP_MAX_RANGE:
        eligible = [r for r in rows if r["load_kg"] is not None and r["full"] >= n]
        if eligible:
            rep_max[n] = max(eligible, key=lambda r: r["load_kg"])
    return {"e1rm": best, "rep_max": rep_max}


def session_prs(db, session_id):
    """PRs set in one session, measured against everything logged before it."""
    ex_ids = []
    for st in db["sets"]:
        if st["session_id"] == session_id and st["exercise_id"] not in ex_ids:
            ex_ids.append(st["exercise_id"])
    rank = session_rank(db)
    found = []
    for ex in db["exercises"]:
        if ex["id"] not in ex_ids:
            continue
        history = [r for r in pr_candidates(db, ex) if rank[r["session_id"]] < rank[session_id]]
        old, now = prs(db, ex, upto=session_id, inclusive=False), prs(db, ex, upto=session_id)
        if not history:
            # Nothing to beat yet: report the starting point, not a pile of PRs.
            if ex["measure"] == "hold":
                found.append((ex, "first time logged (baseline)"))
            elif now["e1rm"]:
                found.append((ex, f"first time logged; baseline e1RM {show(now['e1rm']['e1rm'])}"))
            else:
                found.append((ex, "first time logged (baseline)"))
            continue
        if ex["measure"] == "hold":
            for load, r in now["holds"].items():
                prev = old["holds"].get(load)
                if r["session_id"] == session_id and (prev is None or r["seconds"] > prev["seconds"]):
                    found.append((ex, f"longest hold at {show(load)}: {_trim(r['seconds'])}s"))
            continue
        b, ob = now["e1rm"], old["e1rm"]
        if b and b["session_id"] == session_id and (ob is None or b["e1rm"] > ob["e1rm"]):
            found.append((ex, f"e1RM {show(b['e1rm'])}"))
        new_maxes = []
        for n, r in now["rep_max"].items():
            prev = old["rep_max"].get(n)
            if r["session_id"] == session_id and (prev is None or r["load_kg"] > prev["load_kg"] + 1e-9):
                new_maxes.append((n, r["load_kg"]))
        found += [(ex, text) for text in _collapse_rep_maxes(new_maxes)]
    return found


def _collapse_rep_maxes(pairs):
    """[(2, 100), (3, 100), (4, 100)] -> ['heaviest for 2–4 reps: 100 kg / 220.5 lb']"""
    out, run = [], []
    for n, load in pairs:
        if run and n == run[-1][0] + 1 and abs(load - run[-1][1]) < 1e-9:
            run.append((n, load))
            continue
        if run:
            out.append(_rep_run(run))
        run = [(n, load)]
    if run:
        out.append(_rep_run(run))
    return out


def _rep_run(run):
    lo, hi = run[0][0], run[-1][0]
    reps = f"{lo} rep{'s' if lo > 1 else ''}" if lo == hi else f"{lo}–{hi} reps"
    return f"heaviest for {reps}: {show(run[0][1])}"


def e1rm_history(db, ex):
    """Best e1RM per session, oldest first."""
    best = {}
    for r in pr_candidates(db, ex):
        if r["e1rm"] is None:
            continue
        if r["session_id"] not in best or r["e1rm"] > best[r["session_id"]]["e1rm"]:
            best[r["session_id"]] = r
    return sorted(best.values(), key=lambda r: (r["date"], r["session_id"]))


# ---------- best sets for drop, myo-rep, myo-match ----------

def best_sets(db, ex):
    """For each non-PR set type, the set that moved the most total load (load × full reps)."""
    sessions = {s["id"]: s for s in db["sessions"]}
    best = {}
    for st in sets_for(db, ex["id"]):
        if st["type"] not in schema.BEST_SET_TYPES or ex["measure"] == "hold":
            continue
        sess = sessions[st["session_id"]]
        bw = bodyweight_kg(db, sess)
        loads = [effective_kg(seg, ex, bw) for seg in st["segments"]]
        if any(l is None for l in loads):
            continue
        volume = sum(l * seg["full"] for l, seg in zip(loads, st["segments"]))
        if st["type"] not in best or volume > best[st["type"]]["volume_kg"]:
            best[st["type"]] = {"date": sess["date"], "set": st, "volume_kg": volume,
                                "full_reps": sum(seg["full"] for seg in st["segments"])}
    return best


# ---------- weekly volume ----------

def week_of(date_str):
    d = dt.date.fromisoformat(date_str)
    monday = d - dt.timedelta(days=d.weekday())
    return monday.isoformat()


def weekly_volume(db, weeks=4, today=None):
    """Hard sets per muscle per week (weeks start Monday). Warm-ups don't count."""
    today = today or dt.date.today()
    this_monday = today - dt.timedelta(days=today.weekday())
    starts = [(this_monday - dt.timedelta(weeks=i)).isoformat() for i in range(weeks - 1, -1, -1)]
    sessions = {s["id"]: s for s in db["sessions"]}
    exercises = {ex["id"]: ex for ex in db["exercises"]}
    table = {w: defaultdict(float) for w in starts}
    for st in db["sets"]:
        if st["type"] == "warm-up":
            continue
        w = week_of(sessions[st["session_id"]]["date"])
        if w not in table:
            continue
        ex = exercises[st["exercise_id"]]
        for m in ex["primary_muscles"]:
            table[w][m] += schema.PRIMARY_CREDIT
        for m in ex.get("secondary_muscles", []):
            table[w][m] += schema.SECONDARY_CREDIT
    return table


# ---------- session-level numbers ----------

def minutes(sess):
    if not sess.get("start") or not sess.get("end"):
        return None
    h1, m1 = map(int, sess["start"].split(":"))
    h2, m2 = map(int, sess["end"].split(":"))
    mins = (h2 * 60 + m2) - (h1 * 60 + m1)
    return mins if mins > 0 else mins + 24 * 60


def training_load(sess):
    """Session RPE × minutes (Foster's session-RPE load)."""
    m = minutes(sess)
    if m is None or sess.get("session_rpe") is None:
        return None
    return sess["session_rpe"] * m


def cues(db, ex, last=5):
    """Most recent cues for an exercise, newest first."""
    sessions = {s["id"]: s for s in db["sessions"]}
    rows = [(sessions[st["session_id"]]["date"], st["session_id"], st["order"], st["cue"])
            for st in sets_for(db, ex["id"]) if st.get("cue")]
    rows.sort(reverse=True)
    return [(d, c) for d, _, _, c in rows[:last]]


def last_unit(db, ex_id):
    """The unit this exercise was most recently logged in, or None if never logged."""
    sessions = {s["id"]: s for s in db["sessions"]}
    latest = None
    for st in sets_for(db, ex_id):
        key = (sessions[st["session_id"]]["date"], st["session_id"], st["order"])
        if latest is None or key > latest[0]:
            latest = (key, st["segments"][-1]["unit"])
    return latest[1] if latest else None
