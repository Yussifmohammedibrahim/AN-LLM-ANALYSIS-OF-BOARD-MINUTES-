import sqlite3
import sys

db_path = sys.argv[1] if len(sys.argv) > 1 else 'itds_env/itds_minutes.db'

try:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Check Meetings
    c.execute('SELECT COUNT(*) FROM Meetings')
    meetings_count = c.fetchone()[0]
    print(f'Meetings: {meetings_count}')
    
    # Check Segments  
    c.execute('SELECT COUNT(*) FROM Segments')
    segments_count = c.fetchone()[0]
    print(f'Segments: {segments_count}')
    
    # Check themes data
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%theme%'")
    theme_tables = c.fetchall()
    print(f'Tables with theme: {theme_tables}')
    
    # Check if there's any data
    if meetings_count > 0:
        c.execute("SELECT meeting_id, meeting_date FROM Meetings LIMIT 5")
        rows = c.fetchall()
        print(f'Sample meetings: {rows}')
    
    conn.close()
except Exception as e:
    print(f'Error: {e}')
