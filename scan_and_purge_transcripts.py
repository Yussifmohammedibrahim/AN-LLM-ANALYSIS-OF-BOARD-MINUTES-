import sqlite3
from pathlib import Path

ROOT = Path(r"c:/Users/DELL/Documents/itds_frameworks")
DBS = sorted(ROOT.rglob("*.db"))

print("=== DISCOVERED DB FILES ===")
for db in DBS:
    print(db)

print("\n=== PRE-CHECK ===")
records = []
for db in DBS:
    try:
        conn = sqlite3.connect(str(db))
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND lower(name)='transcripts'")
        has_transcripts = cur.fetchone() is not None
        if not has_transcripts:
            conn.close()
            continue

        cur.execute("SELECT COUNT(*) FROM Transcripts")
        total = cur.fetchone()[0]

        by_user = []
        try:
            cur.execute("SELECT user_id, COUNT(*) FROM Transcripts GROUP BY user_id ORDER BY COUNT(*) DESC")
            by_user = cur.fetchall()
        except Exception:
            by_user = []

        print(f"{db}: transcripts_total={total}, by_user={by_user}")
        records.append((db, total))
        conn.close()
    except Exception as exc:
        print(f"{db}: error={exc}")

print("\n=== PURGE ===")
for db, _ in records:
    try:
        conn = sqlite3.connect(str(db))
        cur = conn.cursor()
        cur.execute("DELETE FROM Transcripts")
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM Transcripts")
        after = cur.fetchone()[0]
        print(f"{db}: after_delete={after}")
        conn.close()
    except Exception as exc:
        print(f"{db}: purge_error={exc}")

print("\n=== POST-CHECK ===")
for db, _ in records:
    try:
        conn = sqlite3.connect(str(db))
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM Transcripts")
        total = cur.fetchone()[0]
        print(f"{db}: transcripts_total={total}")
        conn.close()
    except Exception as exc:
        print(f"{db}: postcheck_error={exc}")
