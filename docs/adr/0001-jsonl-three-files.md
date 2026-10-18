# Plain-text JSONL in three files, edited in place

The log is three JSONL files (exercises, sessions, sets) in a git repository rather than a database, Notion, or an app's own storage. Claude reads and writes plain text reliably, git gives full history and backup, and any future front end can import the files. Notion's Training Log was too coarse for set-level detail. Corrections rewrite the affected lines in place instead of appending correction records, because git already keeps every earlier version and append-only corrections would make every calculation reconcile two records.
