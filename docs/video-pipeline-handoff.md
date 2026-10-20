# Handoff: lift videos, from Apple Photos to the dashboard

Written 2026-10-20 for a fresh Claude session. Read this, then `README.md`, `docs/schema.md`, and
`.claude/skills/lift-log/SKILL.md` in the `claude` repo. Mark's working preferences are in that
repo's `CLAUDE.md`; nothing here repeats them.

## What this is for

Mark films his sets on his iPhone. iCloud Photos syncs them to this Mac. He wants each set in
the log to point at its clip, with the clip playable on the dashboard. He chose **YouTube,
unlisted** as the host (free, per-video links, embeddable player; the repo is public anyway, so
unlisted is enough). Nothing binary goes in this repo.

The goal of the next session: make this happen with as little of Mark's time per session as
possible, ideally zero clicks beyond confirming a mapping.

## What already exists (merged)

- **Data.** Each set has an optional `video` field: a YouTube URL (`youtu.be/ID`,
  `youtube.com/watch?v=ID`, or a Short), validated in `liftlog/validate.py` (`youtube_id()`).
- **CLI.** `python3 lift.py set-video SET_ID URL` writes it and rebuilds `data/stats.json`;
  `set-video SET_ID none` clears it. Set ids look like `2026-10-20-1-s04` (session id + set
  number in the order performed); `python3 lift.py show 2026-10-20-1` lists them.
- **Dashboard.** `stats.json` carries `video_id` on each set row and a `videos` list per
  exercise. `index.html` shows a ▶ chip on filmed sets in Sessions and a thumbnail strip on each
  lift; both open a `youtube-nocookie.com` embed on tap. Nothing to build there.
- **Skill.** The `lift-log` skill in the `claude` repo parses a pasted session, confirms, and
  writes it with `lift.py add`. It knows nothing about videos yet. It also doesn't yet set the
  `main` flag when it creates a new exercise (only the four barbell lifts are `main: true`; new
  exercises should default to `false`).

## The pipeline to build

1. **Find the session's clips.** After a session is written, list movies in the Mac's Photos
   library captured between the session's `start` and `end` on its `date`, Pacific time
   (`schema.TIMEZONE`). Use `osxphotos` (install with `pipx install osxphotos`; it reads the
   system library directly and `--download-missing` pulls iCloud originals). Output: capture
   time, duration, filename. Verify once that the library it finds is the one iCloud syncs to.
2. **Map clips to sets.** Propose a mapping in time order against the session's non-warm-up
   sets (include warm-ups only if the clip count says so). Show the table; Mark confirms or
   edits. His notes sometimes say "no video" on a set, which is a hint.
3. **Export with the set as the title**, e.g. `2026-10-20 Bench 115kg×5 @7.5.mov`, into
   `$CLAUDE_JOB_DIR/tmp/lift-clips/<session_id>/`. No re-encoding; YouTube accepts iPhone HEVC.
4. **Upload.** This is the part that still needs a decision; see below.
5. **Link.** Run `set-video` for each set, then commit and push to `main` (logged data goes
   straight to `main`; Mark agreed to that).
6. **Fix-ups.** `set-video SET_ID none` and repeat.

## The upload step: the real design question

- **YouTube Data API.** Clean, but an upload costs 1,600 quota units against a default 10,000
  per day: about **six clips a day**. A typical session has ten. Google grants higher quotas
  through a compliance review that takes days to weeks. Also needs a Google Cloud project,
  OAuth consent screen, and a stored refresh token. Don't start here unless Mark wants to file
  for the quota.
- **Browser automation (recommended first try).** Claude in Chrome has a `file_upload` tool.
  Drive `studio.youtube.com`: open the upload dialog, attach the folder's files (up to 15 per
  batch), let Studio's defaults apply, then read the video ids from the Content list (or from
  the upload dialog's "Video link" field) and match them to the exported titles. One-time setup:
  in Studio → Settings → Upload defaults, set visibility to **Unlisted** and clear the default
  title/description so the filename becomes the title. Mark must be signed in to YouTube in
  Chrome; the session can't sign in for him. Expect Studio's UI to be fiddly; prefer element
  references over coordinates (see the memory note about 1Password's popup breaking text
  fields).
- **Fallback.** Mark drags the folder into Studio himself and pastes the links, or the session
  reads the Content list afterwards. Keep this path working regardless.
- **If browser automation proves too brittle**, raise Cloudflare R2 again (own bucket, free at
  this scale, fully scriptable with `rclone`, plays in a plain `<video>` tag). Mark chose
  YouTube knowing the trade-offs, so only reopen it with a concrete reason.

## Skill changes (claude repo)

- Add a **Videos** section to `.claude/skills/lift-log/SKILL.md` describing steps 1–6, with the
  exact prompts to show Mark (the clip table, the mapping confirmation) and the fallback.
- Put the Photos listing / export logic in `.claude/skills/lift-log/scripts/session_clips.py`
  (arguments: session id or date+start+end; outputs JSON for listing, files for export).
- Teach the skill the `main` flag for new exercises.
- Update the `lift-log-design` memory file (video host, `set-video`, timezone constant, `main`).

## Verification before asking to merge

Run it live on session `2026-10-20-1` (bench and deadlift, 05:45–06:50 on 2026-10-20; Mark's
notes say the 100×5 bench warm-up was filmed and "no video" on at least one set). The dashboard
should then show ▶ chips on those sets at https://ardqme.github.io/lift-log/#sessions. Per
Mark's standing rule, a skill is exercised on real data before the merge question is asked.

## Conventions that matter here

- Work in a worktree in the `claude` repo; the lift-log repo takes data commits on `main` and
  code changes through a PR.
- Ask the merge question as an interactive prompt, say the PR's size, and on "merge" close the
  loop (merge, delete branch, remove worktree).
- Never guess YouTube's API shapes; probe with one small read-only call first.
