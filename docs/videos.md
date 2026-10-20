# Videos

Mark films sets on his iPhone. Each filmed set's clip goes to YouTube as an unlisted video and
the set's `video` field holds the link, so nothing binary lives in this repository (it's public,
and unlisted is enough). The dashboard shows a ▶ chip on a filmed set under Sessions and a
thumbnail strip on the exercise; both open a `youtube-nocookie.com` embed. Vertical iPhone
clips become Shorts, which the validator and the embed both accept.

What this repo holds:

- `video` on a set: `youtu.be/ID`, `youtube.com/watch?v=ID`, or `youtube.com/shorts/ID`,
  checked by `liftlog/validate.py`.
- `python3 lift.py set-video SET_ID URL` writes it and rebuilds `data/stats.json`;
  `set-video SET_ID none` clears it. Set ids look like `2026-10-20-1-s04`.
- `stats.json` carries `video_id` on each set row and a `videos` list per exercise.

The pipeline that gets a clip from Photos to here — listing the session's clips, mapping them
to sets, exporting the originals, uploading through YouTube Studio, reading back the ids — is
the **Videos** section of the `lift-log` skill in the `claude` repo, with its scripts in that
skill's `scripts/` folder. Video titles are `<date> <exercise> <set> <effort> (sNN)`; Studio
drops the punctuation, so a title ends in the bare set number, which is what the link step
matches on.
