"""
Archive old meetings into an ArchivedMeetings table for cold storage.
Run this script periodically (cron/task scheduler) to move meetings older than a threshold.
"""
import sqlite3
import os
import json
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data.db')
THRESHOLD_DAYS = 365 * 2  # archive meetings older than 2 years

ARCHIVE_SCHEMA = '''
CREATE TABLE IF NOT EXISTS ArchivedMeetings (
    archived_id INTEGER PRIMARY KEY,
    original_meeting_id INTEGER UNIQUE,
    meeting_date DATE,
    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    payload_json TEXT NOT NULL
);
'''


def archive_old_meetings(db_path=DB_PATH, threshold_days=THRESHOLD_DAYS):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.executescript(ARCHIVE_SCHEMA)
    cutoff = (datetime.utcnow() - timedelta(days=threshold_days)).date().isoformat()

    # Ensure Meetings table exists
    try:
        rows = cur.execute('SELECT meeting_id, meeting_date FROM Meetings WHERE meeting_date <= ?', (cutoff,)).fetchall()
    except sqlite3.OperationalError:
        print('No Meetings table found; nothing to archive.')
        conn.close()
        return
    print(f"Found {len(rows)} meetings to archive (<= {cutoff})")

    for row in rows:
        meeting_id = row['meeting_id']
        # Get full meeting rows and segments
        meeting = cur.execute('SELECT * FROM Meetings WHERE meeting_id = ?', (meeting_id,)).fetchone()
        segments = cur.execute('SELECT * FROM Segments WHERE meeting_id = ?', (meeting_id,)).fetchall()
        payload = {
            'meeting': dict(meeting) if meeting else {},
            'segments': [dict(s) for s in segments]
        }
        # Insert into archive table
        cur.execute('INSERT OR REPLACE INTO ArchivedMeetings (original_meeting_id, meeting_date, payload_json) VALUES (?, ?, ?)',
                    (meeting_id, meeting['meeting_date'], json.dumps(payload)))
        # Optionally delete original rows (commented out for safety)
        # cur.execute('DELETE FROM Segments WHERE meeting_id = ?', (meeting_id,))
        # cur.execute('DELETE FROM Meetings WHERE meeting_id = ?', (meeting_id,))

    conn.commit()
    conn.close()
    print('Archiving complete.')


if __name__ == '__main__':
    archive_old_meetings()
