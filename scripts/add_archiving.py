import sqlite3
from itds_env.app.models import get_db  # Reuse existing DB connection

def ensure_archiving_schema():
    """Add archiving columns and indexes to AuditLogs."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Check existing columns
    cursor.execute("PRAGMA table_info(AuditLogs)")
    columns = {row[1] for row in cursor.fetchall()}
    
    if 'archived_at' not in columns:
        cursor.execute("ALTER TABLE AuditLogs ADD COLUMN archived_at TIMESTAMP")
        print("✓ Added archived_at column")
    else:
        print("ℹ archived_at column already exists")
    
    # Add indexes if missing
    indexes = {
        'idx_auditlogs_archived_at': 'CREATE INDEX IF NOT EXISTS idx_auditlogs_archived_at ON AuditLogs(archived_at)',
        'idx_auditlogs_archived_user': 'CREATE INDEX IF NOT EXISTS idx_auditlogs_archived_user ON AuditLogs(archived_at, user_id)'
    }
    
    for idx_name, create_sql in indexes.items():
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='index' AND name='{idx_name}'")
        if not cursor.fetchone():
            cursor.execute(create_sql)
            print(f"✓ Added index: {idx_name}")
        else:
            print(f"ℹ Index exists: {idx_name}")
    
    conn.commit()
    conn.close()
    print("✓ Archiving schema migration complete")

if __name__ == '__main__':
    ensure_archiving_schema()
