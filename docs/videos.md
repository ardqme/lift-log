# Videos

Mark films some sets on his iPhone and uploads the clips himself, from the YouTube app, as
unlisted videos on his channel. The set's `video` field holds the link, so nothing binary lives
in this repository (it's public, and unlisted is enough). The dashboard shows a ▶ chip on a filmed set under Sessions and a
thumbnail strip on the exercise; both open a `youtube-nocookie.com` embed. Vertical iPhone
clips become Shorts, which the validator and the embed both accept.

What this repo holds:

- `video` on a set: `youtu.be/ID`, `youtube.com/watch?v=ID`, or `youtube.com/shorts/ID`,
  checked by `liftlog/validate.py`.
- `python3 lift.py set-video SET_ID URL` writes it and rebuilds `data/stats.json`;
  `set-video SET_ID none` clears it. Set ids look like `2026-10-20-1-s04`.
- `stats.json` carries `video_id` on each set row and a `videos` list per exercise.

Linking is the **Videos** section of the `lift-log` skill in the `claude` repo: Mark pastes a
link and names the set, the skill runs `set-video`, validates, and commits to `main`. Matching
clips to sets from Photos capture times was tried and dropped; he owns the upload and the match.
