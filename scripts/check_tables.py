import sqlite3
import os

db_path = os.path.join(os.path.dirname('itds_minutes.db'), 'itds_minutes.db') if not os.path.exists('itds_minutes.db') else 'itds_minutes.db'
print(f"Using database: {db_path}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print('\n=== Tables in database ===')
for t in tables:
    print(f"  - {t[0]}")

# Check for tables with user_id FK
print('\n=== Tables with foreign keys to Users ===')
for t in tables:
    table_name = t[0]
    try:
        cursor.execute(f"PRAGMA foreign_key_list({table_name})")
        fks = cursor.fetchall()
        for fk in fks:
            if 'user_id' in fk[3].lower():
                print(f"  - {table_name}: {fk[3]} -> {fk[2]}")
    except:
        pass

conn.close()
