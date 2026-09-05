"""
Database Models and Setup
"""
import sqlite3
import os
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash
import logging

DB_PATH = os.environ.get(
    'ITDS_DB_PATH',
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'itds_minutes.db')
)

def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA journal_mode = WAL')
    conn.execute('PRAGMA busy_timeout = 60000')
    return conn


def ensure_column(cursor, table_name, column_name, column_definition):
    """Add a column only if it does not already exist."""
    cursor.execute(f'PRAGMA table_info({table_name})')
    existing_columns = {row[1] for row in cursor.fetchall()}
    if column_name not in existing_columns:
        cursor.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_definition}')

# Removed duplicate execute_safe_query - use app.py version


def log_action(action, details, user_id=None):
    """Log user action to AuditLogs."""
    try:
        execute_safe_query(
            'INSERT INTO AuditLogs (user_id, action, details, timestamp) VALUES (?, ?, ?, ?)',
            (user_id, action, details, datetime.now(timezone.utc)),
            fetch=False
        )
    except Exception as e:
        print(f"Failed to log action: {e}")

def execute_safe_query(query, params=(), fetch=True):
    """Execute database query safely with error handling."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        if fetch:
            try:
                rows = cursor.fetchall()
            except (sqlite3.InterfaceError, ValueError) as fetch_err:
                logging.warning(f"Fetch error (bad timestamp data): {fetch_err}. Using basic mode.")
                conn.row_factory = None
                cursor = conn.cursor()
                cursor.execute(query, params)
                rows = cursor.fetchall()
                columns = [description[0] for description in cursor.description]
                result = [dict(zip(columns, row)) for row in rows]
                conn.row_factory = sqlite3.Row
                cursor.close()
                return result
            columns = [description[0] for description in cursor.description]
            result = [dict(zip(columns, row)) for row in rows]
            return result
        else:
            conn.commit()
            return cursor.lastrowid
    except sqlite3.OperationalError as e:
        if 'locked' in str(e).lower():
            logging.error(f"Database locked: {e}")
        else:
            logging.error(f"Database error: {e}")
        conn.rollback()
        raise
    except Exception as e:
        logging.error(f"Database error: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def setup_database():
    """Create all database tables."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''CREATE TABLE IF NOT EXISTS Users (  
        user_id INTEGER PRIMARY KEY,  
        username TEXT UNIQUE,  
        email TEXT UNIQUE DEFAULT NULL,  
        password_hash TEXT,  
        full_name TEXT DEFAULT NULL,  
        contact_number TEXT DEFAULT NULL,  
        must_change_password INTEGER DEFAULT 0,  
        role TEXT,  
        push_notifications_enabled INTEGER DEFAULT 1,
        email_alerts_enabled INTEGER DEFAULT 0,
        anomaly_email_alerts_enabled INTEGER DEFAULT 1,
        push_permission TEXT DEFAULT 'default',
        notification_settings_updated_at TIMESTAMP DEFAULT NULL,
        is_deleted INTEGER DEFAULT 0,
        deleted_at TIMESTAMP DEFAULT NULL,
        deleted_by INTEGER DEFAULT NULL,
        delete_reason TEXT DEFAULT NULL,
        login_attempts INTEGER DEFAULT 0,  
        locked_until TIMESTAMP,  
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_login TIMESTAMP DEFAULT NULL,
        last_logout TIMESTAMP DEFAULT NULL
    )''')

    # FTS Search table for Segments + Transcripts
    cursor.execute('''CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
        content,
        content_id UNINDEXED,
        type UNINDEXED,  -- 'segment' or 'transcript'
        tokenize='porter'
    )''')
    
# Audit logs with device tracking & indexes
    cursor.execute('''CREATE TABLE IF NOT EXISTS AuditLogs (
        log_id INTEGER PRIMARY KEY,
        user_id INTEGER,
        username TEXT,
        action TEXT,
        details TEXT,
        ip_address TEXT,
        user_agent TEXT,
        mac_address TEXT,
        ram_gb REAL,
        cpu_cores INTEGER,
        hardware_id TEXT,
        login_status TEXT,
        country TEXT,
        region TEXT,
        city TEXT,
        latitude REAL,
        longitude REAL,
        device_type TEXT,
        browser TEXT,
        os TEXT,
        timestamp TIMESTAMP,
        archived_at TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES Users(user_id)
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS NotificationSubscriptions (
        subscription_id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL,
        endpoint TEXT NOT NULL UNIQUE,
        p256dh_key TEXT NOT NULL,
        auth_key TEXT NOT NULL,
        content_encoding TEXT DEFAULT 'aesgcm',
        user_agent TEXT DEFAULT NULL,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES Users(user_id)
    )''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_notif_sub_user ON NotificationSubscriptions(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_notif_sub_active ON NotificationSubscriptions(is_active)')

    cursor.execute('''CREATE TABLE IF NOT EXISTS NotificationEvents (
        notification_id INTEGER PRIMARY KEY,
        user_id INTEGER,
        actor_user_id INTEGER DEFAULT NULL,
        actor_username TEXT DEFAULT NULL,
        channel TEXT NOT NULL,
        direction TEXT NOT NULL DEFAULT 'received',
        notification_type TEXT DEFAULT 'general',
        title TEXT NOT NULL,
        body TEXT DEFAULT NULL,
        status TEXT NOT NULL DEFAULT 'sent',
        source TEXT DEFAULT NULL,
        reference_id TEXT DEFAULT NULL,
        is_read INTEGER DEFAULT 0,
        read_at TIMESTAMP DEFAULT NULL,
        metadata TEXT DEFAULT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        sent_at TIMESTAMP DEFAULT NULL,
        delivered_at TIMESTAMP DEFAULT NULL,
        failed_at TIMESTAMP DEFAULT NULL,
        error_message TEXT DEFAULT NULL,
        recipient_email TEXT DEFAULT NULL,
        FOREIGN KEY (user_id) REFERENCES Users(user_id),
        FOREIGN KEY (actor_user_id) REFERENCES Users(user_id)
    )''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_notif_events_user ON NotificationEvents(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_notif_events_actor ON NotificationEvents(actor_user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_notif_events_channel ON NotificationEvents(channel)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_notif_events_read ON NotificationEvents(is_read)')

    # Refresh tokens (for JWT refresh + revocation)
    cursor.execute('''CREATE TABLE IF NOT EXISTS RefreshTokens (
        id INTEGER PRIMARY KEY,
        jti TEXT UNIQUE,
        user_id INTEGER,
        created_at TIMESTAMP,
        expires_at TIMESTAMP,
        revoked INTEGER DEFAULT 0,
        ip_address TEXT DEFAULT NULL,
        user_agent TEXT DEFAULT NULL,
        FOREIGN KEY (user_id) REFERENCES Users(user_id)
    )''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_refresh_user ON RefreshTokens(user_id)')
    
# Indexes for performance on Meetings and Segments
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_meetings_date ON Meetings(meeting_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_segments_meeting ON Segments(meeting_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_segments_created ON Segments(created_at)')
    
    # Indexes for fast sentiment and analysis queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sentiments_segment ON Sentiments(segment_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sentiments_confidence ON Sentiments(confidence)')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_sentiments_segment_unique ON Sentiments(segment_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_analysis_segment ON Analysis(segment_id)')
    # Ensure anomaly-specific email alerts column exists for upgrades
    ensure_column(cursor, 'Users', 'anomaly_email_alerts_enabled', 'anomaly_email_alerts_enabled INTEGER DEFAULT 1')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_analysis_theme ON Analysis(theme_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_analysis_score ON Analysis(confidence_score)')
    
    # Indexes for Keywords and ActionItems
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_keywords_segment ON Keywords(segment_id)')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_keywords_segment_unique ON Keywords(segment_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_actionitems_segment ON ActionItems(segment_id)')
    
    # Indexes for Transcripts and Topics
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_transcripts_user ON Transcripts(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_transcripts_meeting ON Transcripts(meeting_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_transcripts_analysis ON Transcripts(analysis_complete)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_transcripts_deleted ON Transcripts(is_deleted)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_topics_meeting ON Topics(meeting_id)')
    
    # Indexes for DocumentClassifications
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_docclass_meeting ON DocumentClassifications(meeting_id)')
    
    # Indexes for Summaries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_summaries_segment ON Summaries(segment_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_summaries_created ON Summaries(created_at)')
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_summaries_meeting_unique ON Summaries(meeting_id)')
    
    # Meetings
    cursor.execute('''CREATE TABLE IF NOT EXISTS Meetings (
        meeting_id INTEGER PRIMARY KEY,
        meeting_date DATE,
        source_filename TEXT DEFAULT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Segments
    cursor.execute('''CREATE TABLE IF NOT EXISTS Segments (
        segment_id INTEGER PRIMARY KEY,
        meeting_id INTEGER,
        original_text TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Themes
    cursor.execute('''CREATE TABLE IF NOT EXISTS Themes (
        theme_id INTEGER PRIMARY KEY,
        theme_name TEXT UNIQUE
    )''')
    
    # Analysis
    cursor.execute('''CREATE TABLE IF NOT EXISTS Analysis (
        analysis_id INTEGER PRIMARY KEY,
        segment_id INTEGER,
        theme_id INTEGER,
        confidence_score REAL,
        is_verified INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # Ensure is_verified column exists for upgrades
    ensure_column(cursor, 'Analysis', 'is_verified', 'is_verified INTEGER DEFAULT 0')
    
    # Summaries
    cursor.execute('''CREATE TABLE IF NOT EXISTS Summaries (
        summary_id INTEGER PRIMARY KEY,
        meeting_id INTEGER,
        segment_id INTEGER,
        summary_text TEXT,
        confidence_score REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Sentiments
    cursor.execute('''CREATE TABLE IF NOT EXISTS Sentiments (
        sentiment_id INTEGER PRIMARY KEY,
        segment_id INTEGER,
        sentiment TEXT,
        confidence REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    # Index on created_at to speed time-based sentiment queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sentiments_created ON Sentiments(created_at)')
    
    # Action Items
    cursor.execute('''CREATE TABLE IF NOT EXISTS ActionItems (
        item_id INTEGER PRIMARY KEY,
        segment_id INTEGER,
        item_type TEXT,
        item_text TEXT,
        keyword TEXT,
        persons TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Keywords
    cursor.execute('''CREATE TABLE IF NOT EXISTS Keywords (
        keyword_id INTEGER PRIMARY KEY,
        segment_id INTEGER,
        keywords TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Document Classifications
    cursor.execute('''CREATE TABLE IF NOT EXISTS DocumentClassifications (
        classification_id INTEGER PRIMARY KEY,
        meeting_id INTEGER,
        document_type TEXT,
        confidence REAL,
        all_scores TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (meeting_id) REFERENCES Meetings(meeting_id)
    )''')
    
    # Topics (for dynamic topic modeling)
    cursor.execute('''CREATE TABLE IF NOT EXISTS Topics (
        topic_id INTEGER PRIMARY KEY,
        meeting_id INTEGER,
        topic_name TEXT,
        confidence_score REAL,
        keywords TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (meeting_id) REFERENCES Meetings(meeting_id)
    )''')

    # Transcripts for live voice recording
    cursor.execute('''CREATE TABLE IF NOT EXISTS Transcripts (
        transcript_id INTEGER PRIMARY KEY,
        user_id INTEGER,
        transcript_text TEXT,
        meeting_id INTEGER DEFAULT NULL,
        sentiment TEXT DEFAULT NULL,
        keywords TEXT DEFAULT NULL,
        analysis_complete INTEGER DEFAULT 0,
        is_deleted INTEGER DEFAULT 0,
        deleted_at TIMESTAMP DEFAULT NULL,
        deleted_by INTEGER DEFAULT NULL,
        delete_reason TEXT DEFAULT NULL,
        analysis_cleared_at TIMESTAMP DEFAULT NULL,
        analysis_cleared_by INTEGER DEFAULT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES Users(user_id),
        FOREIGN KEY (meeting_id) REFERENCES Meetings(meeting_id)
    )''')
    
    # Add analysis_complete column to existing Transcripts table if it doesn't exist
    try:
        cursor.execute("ALTER TABLE Transcripts ADD COLUMN analysis_complete INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        # Column already exists
        pass

    # Add soft delete / recovery columns to existing tables.
    ensure_column(cursor, 'Users', 'is_deleted', 'is_deleted INTEGER DEFAULT 0')
    ensure_column(cursor, 'Users', 'deleted_at', 'deleted_at TIMESTAMP DEFAULT NULL')
    ensure_column(cursor, 'Users', 'deleted_by', 'deleted_by INTEGER DEFAULT NULL')
    ensure_column(cursor, 'Users', 'delete_reason', 'delete_reason TEXT DEFAULT NULL')
    ensure_column(cursor, 'Transcripts', 'is_deleted', 'is_deleted INTEGER DEFAULT 0')
    ensure_column(cursor, 'Transcripts', 'deleted_at', 'deleted_at TIMESTAMP DEFAULT NULL')
    ensure_column(cursor, 'Transcripts', 'deleted_by', 'deleted_by INTEGER DEFAULT NULL')
    ensure_column(cursor, 'Transcripts', 'delete_reason', 'delete_reason TEXT DEFAULT NULL')
    ensure_column(cursor, 'Transcripts', 'analysis_cleared_at', 'analysis_cleared_at TIMESTAMP DEFAULT NULL')
    ensure_column(cursor, 'Transcripts', 'analysis_cleared_by', 'analysis_cleared_by INTEGER DEFAULT NULL')
    ensure_column(cursor, 'Summaries', 'meeting_id', 'meeting_id INTEGER DEFAULT NULL')
    ensure_column(cursor, 'Summaries', 'confidence_score', 'confidence_score REAL DEFAULT NULL')

    # Backfill legacy summaries and retain the latest summary per meeting.
    try:
        cursor.execute(
            '''
                UPDATE Summaries
                SET meeting_id = (
                    SELECT s.meeting_id
                    FROM Segments s
                    WHERE s.segment_id = Summaries.segment_id
                    LIMIT 1
                )
                WHERE meeting_id IS NULL AND segment_id IS NOT NULL
            '''
        )
        cursor.execute(
            '''
                DELETE FROM Summaries
                WHERE summary_id NOT IN (
                    SELECT MAX(summary_id)
                    FROM Summaries
                    GROUP BY COALESCE(meeting_id, segment_id)
                )
            '''
        )
    except Exception:
        pass

    # Helpful indexes for soft-delete lookups.
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_deleted ON Users(is_deleted)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_role ON Users(role)')
    
    # Create default admin
    try:
        admin_password = generate_password_hash("admin123", method='pbkdf2:sha256')
        cursor.execute('INSERT OR IGNORE INTO Users (username, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)',
                       ('admin', 'admin@itds.local', admin_password, 'admin', datetime.utcnow()))
    except:
        pass

    # Create default super admin
    try:
        super_admin_username = os.getenv('SUPER_ADMIN_USERNAME', 'superadmin')
        super_admin_password = os.getenv('SUPER_ADMIN_PASSWORD', 'SuperAdmin123!')
        super_admin_hash = generate_password_hash(super_admin_password, method='pbkdf2:sha256')
        cursor.execute(
            'INSERT OR IGNORE INTO Users (username, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)',
            (super_admin_username, 'superadmin@itds.local', super_admin_hash, 'super_admin', datetime.utcnow())
        )
    except:
        pass

    
    conn.commit()
    conn.close()


def store_refresh_token(jti, user_id, expires_at, ip_address=None, user_agent=None):
    try:
        execute_safe_query(
            '''INSERT OR REPLACE INTO RefreshTokens (jti, user_id, created_at, expires_at, revoked, ip_address, user_agent)
               VALUES (?, ?, ?, ?, 0, ?, ?)''',
            (jti, user_id, datetime.now(timezone.utc).isoformat(), expires_at.isoformat() if hasattr(expires_at, 'isoformat') else str(expires_at), ip_address, user_agent),
            fetch=False
        )
    except Exception as e:
        # Try to auto-create the table if it doesn't exist, then retry once
        try:
            if 'no such table' in str(e).lower():
                _ensure_refresh_tokens_table()
                execute_safe_query(
                    '''INSERT OR REPLACE INTO RefreshTokens (jti, user_id, created_at, expires_at, revoked, ip_address, user_agent)
                       VALUES (?, ?, ?, ?, 0, ?, ?)''',
                    (jti, user_id, datetime.now(timezone.utc).isoformat(), expires_at.isoformat() if hasattr(expires_at, 'isoformat') else str(expires_at), ip_address, user_agent),
                    fetch=False
                )
                return
        except Exception:
            pass
        logging.warning(f"Failed to store refresh token: {e}")


def revoke_token(jti):
    try:
        execute_safe_query('UPDATE RefreshTokens SET revoked = 1 WHERE jti = ?', (jti,), fetch=False)
    except Exception as e:
        try:
            if 'no such table' in str(e).lower():
                _ensure_refresh_tokens_table()
                execute_safe_query('UPDATE RefreshTokens SET revoked = 1 WHERE jti = ?', (jti,), fetch=False)
                return
        except Exception:
            pass
        logging.warning(f"Failed to revoke token {jti}: {e}")


def is_token_revoked(jti):
    try:
        rows = execute_safe_query('SELECT revoked FROM RefreshTokens WHERE jti = ? LIMIT 1', (jti,))
        if not rows:
            return False
        return bool(rows[0].get('revoked'))
    except Exception as e:
        try:
            if 'no such table' in str(e).lower():
                _ensure_refresh_tokens_table()
                rows = execute_safe_query('SELECT revoked FROM RefreshTokens WHERE jti = ? LIMIT 1', (jti,))
                if not rows:
                    return False
                return bool(rows[0].get('revoked'))
        except Exception:
            pass
        logging.warning(f"Failed to check token revocation for {jti}: {e}")
        return True


def _ensure_refresh_tokens_table():
    """Create the RefreshTokens table if it doesn't exist."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS RefreshTokens (
            id INTEGER PRIMARY KEY,
            jti TEXT UNIQUE,
            user_id INTEGER,
            created_at TIMESTAMP,
            expires_at TIMESTAMP,
            revoked INTEGER DEFAULT 0,
            ip_address TEXT DEFAULT NULL,
            user_agent TEXT DEFAULT NULL,
            FOREIGN KEY (user_id) REFERENCES Users(user_id)
        )''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_refresh_user ON RefreshTokens(user_id)')
        conn.commit()
    except Exception as e:
        logging.warning(f"Failed to ensure RefreshTokens table: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass

