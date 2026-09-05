import sqlite3
from pathlib import Path

DBS = [
    Path(r"c:/Users/DELL/Documents/itds_frameworks/itds_minutes.db"),
    Path(r"c:/Users/DELL/Documents/itds_frameworks/itds_env/itds.db"),
    Path(r"c:/Users/DELL/Documents/itds_frameworks/itds_env/itds_minutes.db"),
    Path(r"c:/Users/DELL/Documents/itds_frameworks/itds_env/frontend/itds_minutes.db"),
]

for db in DBS:
    if not db.exists():
        continue
    try:
        conn = sqlite3.connect(str(db))
        cur = conn.cursor()

        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Transcripts'")
        has_transcripts = cur.fetchone() is not None
        if not has_transcripts:
            print(f"{db}: skipped (missing Transcripts)")
            conn.close()
            continue

        cur.execute("SELECT COUNT(*) FROM Transcripts")
        before = cur.fetchone()[0]
        cur.execute("DELETE FROM Transcripts")
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM Transcripts")
        after = cur.fetchone()[0]
        print(f"{db}: before={before}, after={after}, deleted={before - after}")
        conn.close()
    except Exception as exc:
        print(f"{db}: error={exc}")
