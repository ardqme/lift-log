"""Builds data/stats.json: every number the dashboard shows, computed by the same
rules the command line uses, so the page and the skill can never disagree."""

import datetime as dt

from . import calc, schema, store, validate

MAX_WEEKS = 26  # volume grid covers at most the last half year


def _effort(st):
    parts = []
    if st.get("rpe") is not None:
        parts.append(f"@{calc._trim(st['rpe'])}")
    if st.get("rir") is not None:
        parts.append(f"{calc._trim(st['rir'])} RIR")
    return " ".join(parts)


def _pr_flags(db):
    """{set_id: 'e1rm' | 'rep_max'} for every set that beat all earlier sessions.

    The first session on an exercise is a baseline, not a PR, matching the command line.
    """
    flags = {}
    rank = calc.session_rank(db)
    for ex in db["exercises"]:
        rows = calc.pr_candidates(db, ex)
        for sid in sorted({r["session_id"] for r in rows}, key=rank.get):
            if not any(rank[r["session_id"]] < rank[sid] for r in rows):
                continue
            old, now = calc.prs(db, ex, upto=sid, inclusive=False), calc.prs(db, ex, upto=sid)
            if ex["measure"] == "hold":
                for load, r in now["holds"].items():
                    prev = old["holds"].get(load)
                    if r["session_id"] == sid and (prev is None or r["seconds"] > prev["seconds"]):
                        flags.setdefault(r["set_id"], "rep_max")
                continue
            b, ob = now["e1rm"], old["e1rm"]
            if b and b["session_id"] == sid and (ob is None or b["e1rm"] > ob["e1rm"]):
                flags[b["set_id"]] = "e1rm"
            for n, r in now["rep_max"].items():
                prev = old["rep_max"].get(n)
                if r["session_id"] == sid and (prev is None or r["load_kg"] > prev["load_kg"] + 1e-9):
                    flags.setdefault(r["set_id"], "rep_max")
    return flags


def _set_roles(sets):
    """Name each of one exercise's sets in one session, in the order performed: `warm-up`,
    `top set` (the single heaviest working set), `backoff set i/n` for the lighter ones, or
    `set i/n` when no one set is heaviest. A set's load is its heaviest segment, in kg."""
    def kg(st):
        return max(calc.to_kg(s["load"], s["unit"]) for s in st["segments"])
    roles = {st["id"]: "warm-up" for st in sets if st["type"] == "warm-up"}
    working = [st for st in sets if st["type"] != "warm-up"]
    if not working:
        return roles
    top_kg = max(kg(st) for st in working)
    tops = [st for st in working if kg(st) == top_kg]
    if len(tops) == 1:
        roles[tops[0]["id"]] = "top set"
        backs = [st for st in working if st is not tops[0]]
        for i, st in enumerate(backs, 1):
            roles[st["id"]] = f"backoff set {i}/{len(backs)}"
    else:
        for i, st in enumerate(working, 1):
            roles[st["id"]] = f"set {i}/{len(working)}"
    return roles


def _exercise_block(db, ex):
    p = calc.prs(db, ex)
    sessions = {s["id"]: s for s in db["sessions"]}
    block = {
        "id": ex["id"], "name": ex["name"], "main": bool(ex.get("main")),
        "load_type": ex["load_type"], "measure": ex["measure"],
        "primary_muscles": ex["primary_muscles"], "secondary_muscles": ex.get("secondary_muscles", []),
        "e1rm_history": [{"date": r["date"], "session_id": r["session_id"], "kg": r["e1rm"],
                          "from": calc.format_segment(r["segment"], ex)}
                         for r in calc.e1rm_history(db, ex)],
        "e1rm": None, "rep_max": [], "holds": [], "best_sets": [],
        "cues": [{"date": d, "cue": c} for d, c in calc.cues(db, ex, last=5)],
        "videos": [],
    }
    if ex["measure"] == "hold":
        block["holds"] = [{"kg": load, "seconds": r["seconds"], "date": r["date"]}
                          for load, r in sorted(p["holds"].items())]
    else:
        b = p["e1rm"]
        if b:
            block["e1rm"] = {"kg": b["e1rm"], "date": b["date"], "set_id": b["set_id"],
                             "from": calc.format_segment(b["segment"], ex)}
        block["rep_max"] = [{"reps": n, "kg": r["load_kg"], "e1rm_kg": r["e1rm"], "date": r["date"],
                             "set_id": r["set_id"], "from": calc.format_segment(r["segment"], ex)}
                            for n, r in sorted(p["rep_max"].items())]
    for kind, r in calc.best_sets(db, ex).items():
        block["best_sets"].append({"type": kind, "date": r["date"], "volume_kg": r["volume_kg"],
                                   "segments": ", ".join(calc.format_segment(s, ex) for s in r["set"]["segments"])})
    mine = calc.sets_for(db, ex["id"])
    roles = {}
    for sid in {st["session_id"] for st in mine}:
        roles.update(_set_roles(sorted((st for st in mine if st["session_id"] == sid), key=lambda st: st["order"])))
    filmed = [st for st in mine if st.get("video")]
    filmed.sort(key=lambda st: (sessions[st["session_id"]]["date"], st["session_id"], st["order"]), reverse=True)
    block["videos"] = [{"date": sessions[st["session_id"]]["date"], "session_id": st["session_id"],
                        "set_id": st["id"], "video_id": validate.youtube_id(st["video"]), "role": roles[st["id"]],
                        "segments": ", ".join(calc.format_segment(s, ex) for s in st["segments"])}
                       for st in filmed]
    used = {st["session_id"] for st in db["sets"] if st["exercise_id"] == ex["id"]}
    dates = [s["date"] for s in db["sessions"] if s["id"] in used]
    block["last_logged"] = max(dates) if dates else None
    return block


def _volume(db, today):
    if not db["sessions"]:
        return {"weeks": [], "muscles": [], "table": {}}
    first = dt.date.fromisoformat(min(s["date"] for s in db["sessions"]))
    first_monday = first - dt.timedelta(days=first.weekday())
    this_monday = today - dt.timedelta(days=today.weekday())
    weeks = min(MAX_WEEKS, (this_monday - first_monday).days // 7 + 1)
    table = calc.weekly_volume(db, weeks=weeks, today=today)
    week_keys = list(table)
    muscles = [m for m in schema.MUSCLES if any(table[w].get(m) for w in week_keys)]
    return {"weeks": week_keys, "muscles": muscles,
            "table": {m: [table[w].get(m, 0) for w in week_keys] for m in muscles}}


def _session_block(db, sess, pr_flags):
    exercises = {ex["id"]: ex for ex in db["exercises"]}
    sets = sorted((st for st in db["sets"] if st["session_id"] == sess["id"]), key=lambda st: st["order"])
    bw_kg = calc.bodyweight_kg(db, sess)
    rows = []
    for st in sets:
        ex = exercises[st["exercise_id"]]
        # One plain segment gets numbers the charts can plot; anything fancier keeps only the text.
        seg = st["segments"][0] if len(st["segments"]) == 1 and ex["measure"] == "reps" else None
        rows.append({"set_id": st["id"], "exercise_id": ex["id"], "exercise": ex["name"],
                     "superset": st.get("superset"), "type": st["type"],
                     "segments": ", ".join(calc.format_segment(s, ex) for s in st["segments"]),
                     "load_kg": calc.effective_kg(seg, ex, bw_kg) if seg else None,
                     "reps": seg["full"] if seg else None,
                     "mode": st["mode"], "effort": _effort(st), "gear": st.get("gear", []),
                     "cue": st.get("cue"), "notes": st.get("notes"),
                     "video_id": validate.youtube_id(st["video"]) if st.get("video") else None,
                     "pr": pr_flags.get(st["id"])})
    bw = sess.get("bodyweight")
    return {"id": sess["id"], "date": sess["date"], "start": sess.get("start"), "end": sess.get("end"),
            "location": sess.get("location"), "readiness": sess.get("readiness"),
            "sleep_score": sess.get("sleep_score"), "hrv_ms": sess.get("hrv_ms"),
            "bodyweight_kg": calc.to_kg(bw["value"], bw["unit"]) if bw else None,
            "session_rpe": sess.get("session_rpe"), "minutes": calc.minutes(sess),
            "training_load": calc.training_load(sess), "notes": sess.get("notes"),
            "hard_sets": sum(1 for st in sets if st["type"] != "warm-up"), "sets": rows}


def _exercise_order(db, blocks):
    """Most recently trained first; within a session, in the order performed."""
    rank = calc.session_rank(db)
    pos = {}
    for st in db["sets"]:
        key = (rank[st["session_id"]], -st["order"])
        if st["exercise_id"] not in pos or key > pos[st["exercise_id"]]:
            pos[st["exercise_id"]] = key
    # latest session first, then earliest set within it
    return sorted(blocks, key=lambda b: (-pos.get(b["id"], (-1, 0))[0], -pos.get(b["id"], (-1, 0))[1], b["name"]))


def build(db, today=None):
    today = today or dt.date.today()
    sessions = calc.session_order(db)
    pr_flags = _pr_flags(db)
    return {
        "generated": store.timestamp(),
        "lb_per_kg": schema.LB_PER_KG,
        "exercises": _exercise_order(db, [_exercise_block(db, ex) for ex in db["exercises"]]),
        "volume": _volume(db, today),
        "sessions": [_session_block(db, s, pr_flags) for s in reversed(sessions)],
    }
