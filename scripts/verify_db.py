import sqlite3

# Connect to database
db_path = r'itds_minutes.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print('=== Users Table Schema ===')
cursor.execute('PRAGMA table_info(Users);')
columns = cursor.fetchall()
for col in columns:
    col_name, col_type, nullable, default_val, pk = col[1], col[2], col[3], col[4], col[5]
    nullable_str = 'NO' if nullable == 0 else 'YES'
    default_str = str(default_val) if default_val else 'NULL'
    print(f'{col_name:20} {col_type:15} Default: {default_str:30} Nullable: {nullable_str}')

print('\n=== Trigger Verification ===')
cursor.execute("SELECT type, name, sql FROM sqlite_master WHERE type='trigger' AND name LIKE '%created_at%'")
triggers = cursor.fetchall()
if triggers:
    for trigger in triggers:
        print(f'✓ Trigger: {trigger[1]}')
        print(f'  SQL: {trigger[2]}')
else:
    print('✗ No created_at triggers found.')

conn.close()
print('\n=== Verification Complete ===')
