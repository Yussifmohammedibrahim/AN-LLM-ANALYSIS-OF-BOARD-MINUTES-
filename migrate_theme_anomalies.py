import sqlite3
import os

DB = os.path.join(os.path.dirname(__file__), 'itds_minutes.db')
if not os.path.exists(DB):
    print('Database not found:', DB)
    raise SystemExit(1)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("PRAGMA table_info(ThemeAnomalies)")
cols = cur.fetchall()
if cols:
    print('ThemeAnomalies table already exists')
else:
    print('Creating ThemeAnomalies table...')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS ThemeAnomalies (
        anomaly_id INTEGER PRIMARY KEY AUTOINCREMENT,
        theme TEXT,
        month TEXT,
        mention_count INTEGER DEFAULT 0,
        expected_baseline REAL DEFAULT 0.0,
        z_score REAL DEFAULT 0.0,
        severity TEXT DEFAULT 'low',
        metadata TEXT DEFAULT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT NULL
    )
    ''')
    conn.commit()
    print('Created ThemeAnomalies table')
conn.close()
