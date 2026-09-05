"""One-off migration script to create RefreshTokens table if it's missing.

Run from project root (with virtualenv activated):

python -m itds_env.app.scripts.create_refresh_tokens_table

"""
import logging
from app.models import get_db

logger = logging.getLogger(__name__)

SQL = '''CREATE TABLE IF NOT EXISTS RefreshTokens (
    id INTEGER PRIMARY KEY,
    jti TEXT UNIQUE,
    user_id INTEGER,
    created_at TIMESTAMP,
    expires_at TIMESTAMP,
    revoked INTEGER DEFAULT 0,
    ip_address TEXT DEFAULT NULL,
    user_agent TEXT DEFAULT NULL,
    FOREIGN KEY (user_id) REFERENCES Users(user_id)
);
'''

INDEX_SQL = 'CREATE INDEX IF NOT EXISTS idx_refresh_user ON RefreshTokens(user_id)'


def main():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(SQL)
        cursor.execute(INDEX_SQL)
        conn.commit()
        conn.close()
        print('[OK] RefreshTokens table ensured')
    except Exception as e:
        logger.error('Failed to create RefreshTokens table: %s', e)
        print('ERROR creating RefreshTokens table:', e)


if __name__ == '__main__':
    main()
