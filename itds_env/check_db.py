import sqlite3
conn = sqlite3.connect('itds_minutes.db')
cursor = conn.cursor()

# Check tables
cursor.execute('SELECT name FROM sqlite_master WHERE type="table"')
tables = [row[0] for row in cursor.fetchall()]
print('Tables:', tables)

# Check data in key tables
tables_to_check = ['Meetings', 'Segments', 'Themes', 'Sentiments', 'ActionItems']
for table in tables_to_check:
    try:
        cursor.execute(f'SELECT COUNT(*) FROM {table}')
        count = cursor.fetchone()[0]
        print(f'{table}: {count} records')
    except Exception as e:
        print(f'{table}: Error - {e}')

conn.close()