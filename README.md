# lift-log

Mark's personal weightlifting log. Sessions are written in the Notes app, pasted to Claude, parsed
by the `lift-log` skill (in the `claude` repo), confirmed, and stored here as plain-text JSONL.
A front end comes later; for now, questions are answered by the command line.

- `data/` — `exercises.jsonl` (the library), `sessions.jsonl`, `sets.jsonl`
- `docs/schema.md` — every field and every calculation rule
- `GLOSSARY.md` — the vocabulary (set types, segment, e1RM, PR, and so on)
- `docs/adr/` — the decisions most worth explaining
- `liftlog/` — validation and calculations, Python standard library only

## Commands

Run from this folder with `python3 lift.py <command>`.

| command | what it does |
|---|---|
| `preview BUNDLE.json` | check a parsed session and print it; writes nothing |
| `add BUNDLE.json` | write it as a new session, then report any new PRs |
| `bundle SESSION_ID` | print a stored session in editable form |
| `replace SESSION_ID BUNDLE.json` | swap a stored session for a corrected one (same id) |
| `put-exercise FILE.json` | add or update one library exercise |
| `show SESSION_ID [--raw]` | print a session (with the original text if `--raw`) |
| `sessions`, `exercises` | list recent sessions / the library |
| `prs EXERCISE` | e1RM, rep maxes 1–10, best drop/myo sets |
| `e1rm EXERCISE` | e1RM per session |
| `volume [--weeks N]` | hard sets per muscle per week |
| `cues EXERCISE` | the latest cues for an exercise |
| `load` | session RPE × minutes per session |
| `validate` | check every record |

`EXERCISE` can be the id, the name, or any alias.

Tests: `python3 -m unittest discover tests`
