import sqlite3
from itds_env.app.models import get_db

def add_device_tracking_columns():
    """Add device tracking columns to AuditLogs table."""
    conn = get_db()
    cursor = conn.cursor()
    
    columns_to_add = [
        ('mac_address', 'TEXT'),
        ('ram_gb', 'REAL'),
        ('cpu_cores', 'INTEGER'),
        ('hardware_id', 'TEXT')
    ]
    
    added = []
    for col_name, col_type in columns_to_add:
        try:
            cursor.execute(f'ALTER TABLE AuditLogs ADD COLUMN {col_name} {col_type}')
            added.append(col_name)
            print(f'✓ Added column: {col_name}')
        except sqlite3.OperationalError as e:
            if 'duplicate column name' in str(e).lower():
                print(f'ℹ Column {col_name} already exists')
            else:
                print(f'✗ Error adding {col_name}: {e}')
    
    if added:
        conn.commit()
        print(f'\n✅ Migration complete: Added {len(added)} new columns')
    else:
        print('\nℹ No changes needed - all columns exist')
    
    conn.close()

if __name__ == '__main__':
    print('ITDS Device Tracking Migration')
    print('=' * 40)
    add_device_tracking_columns()
    print('\nMigration finished. Restart backend server.')

