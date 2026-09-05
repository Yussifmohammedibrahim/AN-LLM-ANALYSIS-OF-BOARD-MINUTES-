import sqlite3
import os

# Use relative path to DB
DB_PATH = os.path.join('itds_env', 'itds_minutes.db')

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if columns exist
        cursor.execute("PRAGMA table_info(Users)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'login_attempts' not in columns:
            cursor.execute('ALTER TABLE Users ADD COLUMN login_attempts INTEGER DEFAULT 0')
            print('✅ Added login_attempts column')
        else:
            print('ℹ️ login_attempts column exists')
        
        if 'locked_until' not in columns:
            cursor.execute('ALTER TABLE Users ADD COLUMN locked_until TEXT')
            print('✅ Added locked_until column')
        else:
            print('ℹ️ locked_until column exists')
        
        # Reset attempts for safety
        cursor.execute('UPDATE Users SET login_attempts = 0, locked_until = NULL WHERE login_attempts IS NULL OR locked_until IS NULL')
        print(f'✅ Reset {cursor.rowcount} user records')
        
        conn.commit()
        print('🎉 DB Migration COMPLETE! Ready for login protection.')
        
    except sqlite3.Error as e:
        print(f'DB Error: {e}')
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()

