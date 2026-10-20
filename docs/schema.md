# Data schema

Three files in `data/`, each holding one JSON object per line. `liftlog/validate.py` enforces
everything here; `python3 lift.py validate` checks the whole log. Vocabulary lists live in
`liftlog/schema.py`. Terms are defined in `GLOSSARY.md`.

## exercises.jsonl — the library

One line per exercise. An exercise is one specific variation: whenever a PR on one wouldn't
mean anything for the other (pause, bar, grip, angle, pulley ratio, machine setup), they are
separate exercises. Gear (belt, sleeves, shoes) never makes a new exercise.

| field | type | notes |
|---|---|---|
| `id` | slug | lowercase-hyphenated, from the name; never changes once sets reference it |
| `name` | text | full descriptive name, e.g. "Low-bar Barbell Back Squat" |
| `aliases` | list of text | what Mark might write in his notes ("lowbar squat") |
| `main` | true/false | one of the four primary lifts (squat, bench, deadlift, overhead press); the dashboard leads with these and files the rest under accessories |
| `equipment` | one of | barbell, dumbbell, kettlebell, machine, cable, bodyweight, band, other |
| `load_type` | one of | `total` (barbell incl. bar, plate-loaded total), `per-hand` (dumbbells), `bodyweight` (added + / assisting −, on top of bodyweight × share), `machine` (the weight the machine shows) |
| `measure` | one of | `reps` or `hold` (timed) |
| `bodyweight_share` | number or null | fraction of bodyweight the movement lifts; required for `bodyweight` load type only |
| `bodyweight_share_source` | text | where the share came from (a cited published estimate) |
| `primary_muscles` | list | at least one, from the fixed list below |
| `secondary_muscles` | list | from the fixed list; never repeats a primary |
| `notes` | text or null | standing notes about the exercise |

Muscles: quads, hamstrings, glutes, adductors, calves, chest, front-delts, side-delts,
rear-delts, lats, upper-back, traps, biceps, triceps, forearms, abs, spinal-erectors.

## sessions.jsonl

| field | type | notes |
|---|---|---|
| `id` | text | `YYYY-MM-DD-N`, assigned on write |
| `date` | YYYY-MM-DD | required |
| `start`, `end` | HH:MM or null | 24-hour |
| `location` | text or null | gym name, e.g. "HOTT Barbell" |
| `readiness` | 1–10 or null | how ready Mark felt walking in |
| `sleep_score` | 0–100 or null | Apple Watch sleep score |
| `hrv_ms` | number or null | Apple Watch HRV, milliseconds |
| `bodyweight` | `{"value", "unit"}` or null | |
| `session_rpe` | 1–10 or null | whole-session effort |
| `notes` | text or null | |
| `raw_text` | text | the notes exactly as pasted; kept for investigation, never displayed by default |
| `logged_at` | timestamp | assigned on write, always in `America/Los_Angeles` (`schema.TIMEZONE`) whatever machine wrote it |

## sets.jsonl

One line per set, however many segments it has.

| field | type | notes |
|---|---|---|
| `id` | text | `<session id>-sNN`, assigned on write |
| `session_id`, `exercise_id` | text | links |
| `order` | integer | position in the session, in the order performed (supersets in rounds) |
| `superset` | `A1`-style or null | exercises sharing a letter were supersetted |
| `type` | one of | warm-up, regular, failure, drop, myo-rep, myo-match |
| `rpe` | 1–10 by halves, or null | as entered |
| `rir` | 0–10 by halves, or null | as entered; usually only one of rpe/rir is set |
| `mode` | one of | `bilateral` (both sides together), `alternating`, `one-side` (all of one side, then the other) |
| `gear` | list of text | lowercase, e.g. ["squat shoes", "belt"] |
| `cue` | text or null | the "Cue:" note, kept separate so it can be shown next time |
| `notes` | text or null | everything else written about the set |
| `video` | YouTube URL or null | the clip of this set (`youtu.be/ID`, `youtube.com/watch?v=ID`, or a Short); set with `lift.py set-video` |
| `segments` | list | at least one; see below |

A segment is one uninterrupted piece of a set:

| field | type | notes |
|---|---|---|
| `load` | number | as entered; negative only for assisted bodyweight lifts |
| `unit` | kg or lb | as entered, never converted in storage |
| `side` | both, left, right | bilateral sets use `both`; alternating and one-side sets log each side separately |
| `full` | integer | full-range reps (reps exercises) |
| `partial` | integer | partial reps after the full ones (reps exercises) |
| `seconds` | number | hold exercises only, instead of `full`/`partial` |

How set types use segments: a regular or failure set is usually one segment (two for one side
at a time). A drop set is one segment per weight. A myo-rep set is the activation plus every
mini-set. Each myo-match set is its own line, with one segment per break needed to reach the
target reps.

## Session bundle

What the skill builds from pasted notes and hands to `lift.py preview` / `add` / `replace`:

```json
{"session": {"date": "...", "start": "...", ...},
 "new_exercises": [ {...library entry...} ],
 "sets": [ {"exercise_id": "...", "type": "...", "mode": "...", "segments": [...] , ...} ]}
```

Sets appear in the order performed. Ids, `order`, and `logged_at` are filled in on write.

## stats.json

`data/stats.json` is generated, never edited by hand: `liftlog/stats.py` writes every number the
dashboard shows. It's rebuilt after every write, so it's always committed alongside the three
JSONL files. Top level: `generated` (timestamp), `lb_per_kg`, `exercises`, `volume`, `sessions`.

- Each exercise: identity, `main`, and muscles; `e1rm_history` (best per session, oldest first);
  `e1rm` (the overall best); `rep_max` rows `{reps, kg, e1rm_kg, date, set_id, from}`, one per
  rep count performed; `holds`; `best_sets`; the last five `cues`; `videos` (`date`,
  `session_id`, `set_id`, `video_id`, `segments`, newest first); `last_logged`. Exercises are
  ordered most recently trained first.
- `volume`: `weeks` (Monday dates, at most 26), `muscles`, and `table[muscle][week index]`.
- Each session, newest first: the session fields (bodyweight converted to `bodyweight_kg`),
  `minutes`, `training_load`, `hard_sets`, and `sets`. Each set row carries `set_id`,
  `exercise_id`, `exercise` (name), `superset`, `type`, `segments` (display text), `load_kg` and
  `reps` (filled only for a one-segment reps set, for charts), `mode`, `effort` (`@7.5`, `2 RIR`),
  `gear`, `cue`, `notes`, `video_id`, and `pr` (`"e1rm"`, `"rep_max"`, or null: the set beat every
  earlier session on that exercise; the first session is a baseline, never a PR).

## Computed, never stored

- **e1RM**: Epley, `load × (1 + reps to failure / 30)`, where reps to failure = full reps +
  RIR (RIR as entered, else 10 − RPE, else 0; failure sets are 0). Only regular and failure
  sets, only full reps, only 1–12 full reps, only RIR ≤ 4 (RPE 6 or harder). A single at
  RIR 0 equals its load. Every qualifying set gets its own estimate and the highest wins; there
  is no preference by set type or rep count, so an easy single and a hard set of six compete on
  equal terms.
- **Rep maxes**: for every rep count actually performed, the heaviest load at exactly that many
  full reps, from regular and failure sets. A set of 3 never stands in for a 2-rep max, so the
  list only has the numbers that were done. Each rep max carries the e1RM of the set that set it.
- **Best sets**: for drop, myo-rep, and myo-match sets, the set with the most total load
  (load × full reps across its segments).
- **Holds**: longest time at each load.
- **Bodyweight lifts**: effective load = bodyweight × share + added load. Bodyweight comes
  from the session, or the most recent earlier session that recorded it.
- **Weekly volume**: every non-warm-up set gives 1 to each primary muscle and 0.5 to each
  secondary. One line is one set, whatever its segments. Weeks start Monday.
- **Training load**: session RPE × minutes.
- All comparisons convert to kilograms internally and display both units.
