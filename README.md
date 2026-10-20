# lift-log

Mark's personal weightlifting log. Sessions are written in the Notes app, pasted to Claude, parsed
by the `lift-log` skill (in the `claude` repo), confirmed, and stored here as plain-text JSONL.
The dashboard is at **https://ardqme.github.io/lift-log/**. It's `index.html` here, served by GitHub
Pages, and it draws everything from `data/stats.json`. `lift.py` rebuilds that file on every add,
replace, or exercise change, so the page shows the same numbers the skill reports. This repository
is public, so the log is readable by anyone with the link.

- `data/` — `exercises.jsonl` (the library), `sessions.jsonl`, `sets.jsonl`
- `docs/schema.md` — every field and every calculation rule
- `docs/videos.md` — how set videos are stored and where the upload pipeline lives
- `GLOSSARY.md` — the vocabulary (set types, segment, e1RM, PR, and so on)
- `docs/adr/` — the decisions most worth explaining
- `liftlog/` — validation and calculations, Python standard library only
- `assets/` — the front and back muscle figures the Load view recolours (Ryan Graves, CC BY 4.0; see `assets/CREDITS.md`)

## Commands

Run from this folder with `python3 lift.py <command>`.

| command | what it does |
|---|---|
| `preview BUNDLE.json` | check a parsed session and print it; writes nothing |
| `add BUNDLE.json` | write it as a new session, then report any new PRs |
| `bundle SESSION_ID` | print a stored session in editable form |
| `replace SESSION_ID BUNDLE.json` | swap a stored session for a corrected one (same id) |
| `put-exercise FILE.json` | add or update one library exercise |
| `set-video SET_ID URL` | link a set to its YouTube clip (`none` clears it) |
| `show SESSION_ID [--raw]` | print a session (with the original text if `--raw`) |
| `sessions`, `exercises` | list recent sessions / the library |
| `prs EXERCISE` | e1RM, rep maxes (each with its e1RM), best drop/myo sets |
| `e1rm EXERCISE` | e1RM per session |
| `volume [--weeks N]` | sets per muscle per week, warm-ups excluded |
| `cues EXERCISE` | the latest cues for an exercise |
| `load` | session RPE × minutes per session |
| `validate` | check every record |
| `stats` | rebuild `data/stats.json` for the dashboard (automatic after writes) |

To preview the dashboard locally: `python3 -m http.server` in this folder, then open
http://localhost:8000.

`EXERCISE` can be the id, the name, or any alias.

Tests: `python3 -m unittest discover tests`
