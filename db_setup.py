import sqlite3
import os

DB_PATH = os.path.join('itds_env', 'itds_minutes.db')
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return column in [row[1] for row in cursor.fetchall()]

try:
    # Ensure Users table columns
    if not column_exists(c, 'Users', 'login_attempts'):
        c.execute('ALTER TABLE Users ADD COLUMN login_attempts INTEGER DEFAULT 0')
        print('login_attempts column added')
    else:
        print('login_attempts column already exists')

    if not column_exists(c, 'Users', 'locked_until'):
        c.execute('ALTER TABLE Users ADD COLUMN locked_until TEXT')
        print('locked_until column added')
    else:
        print('locked_until column already exists')

    c.execute('UPDATE Users SET login_attempts = 0, locked_until = NULL')
    print(f'Initialized login security for {c.rowcount} users')


    # Ensure Meetings table exists
    c.execute("""
        CREATE TABLE IF NOT EXISTS Meetings (
            meeting_id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_date TEXT,
            created_at TEXT,
            title TEXT
        )
    """)
    print('Meetings table ensured.')

    # Insert sample Meetings if empty
    c.execute('SELECT COUNT(*) FROM Meetings')
    if c.fetchone()[0] == 0:
        from datetime import datetime
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        sample_meetings = [
            ('2026-04-01', now, 'Project Roadmap Discussion'),
            ('2026-04-08', now, 'Budget Review Q2'),
            ('2026-04-15', now, 'Remote Work Concerns'),
            ('2026-04-22', now, 'Sprint Planning')
        ]
        c.executemany('INSERT INTO Meetings (meeting_date, created_at, title) VALUES (?, ?, ?)', sample_meetings)
        print('Sample Meetings data inserted.')

    # Ensure Segments table exists
    c.execute("""
        CREATE TABLE IF NOT EXISTS Segments (
            segment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id INTEGER,
            original_text TEXT,
            created_at TEXT
        )
    """)
    print('Segments table ensured.')

    # Insert longer, more diverse Segments for theme extraction
    c.execute('DELETE FROM Segments')
    from datetime import datetime
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    sample_segments = [
        (1, 'We discussed the new AI roadmap, set deadlines for each milestone, and assigned responsibilities for the upcoming quarter. The team is excited about integrating machine learning into our workflow.', now),
        (2, 'The finance department reviewed the Q2 budget allocation, identified cost-saving opportunities, and planned for increased investment in cloud infrastructure and cybersecurity.', now),
        (3, 'Concerns about remote work productivity, communication challenges, and employee engagement were addressed. Management proposed new collaboration tools and regular virtual check-ins.', now),
        (4, 'Sprint planning included assigning tasks, clarifying deliverables, and reviewing the agile methodology. The team reflected on the last sprint and discussed improvements for the next cycle.', now),
        (1, 'AI adoption, deep learning research, and natural language processing were major topics. The group also explored ethical considerations in artificial intelligence.', now),
        (2, 'Financial planning, budget forecasting, and quarterly reporting were emphasized. The CFO highlighted the importance of accurate data analytics for decision making.', now),
        (3, 'Employee engagement, remote collaboration tools, and mental health initiatives were discussed. HR will organize workshops and feedback sessions.', now),
        (4, 'Agile methodology, sprint retrospectives, and continuous improvement practices were reviewed. The team committed to better documentation and knowledge sharing.', now)
    ]
    c.executemany('INSERT INTO Segments (meeting_id, original_text, created_at) VALUES (?, ?, ?)', sample_segments)
    print('Long, diverse Segments data inserted.')

    conn.commit()
    print('✅ DB ready for login protection and Segments!')
except Exception as e:
    print(f'Error: {e}')
finally:
    conn.close()

