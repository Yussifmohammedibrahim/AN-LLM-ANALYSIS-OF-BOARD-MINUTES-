-- Add indexes to improve query performance for common analytics queries
-- Run these against your SQLite DB using sqlite3 or via migration script.

CREATE INDEX IF NOT EXISTS idx_meetings_meeting_date ON Meetings(meeting_date);
CREATE INDEX IF NOT EXISTS idx_segments_meeting_id ON Segments(meeting_id);
CREATE INDEX IF NOT EXISTS idx_segments_created_at ON Segments(created_at);
CREATE INDEX IF NOT EXISTS idx_themes_name ON Themes(name);
CREATE INDEX IF NOT EXISTS idx_keywords_segment_id ON Keywords(segment_id);
CREATE INDEX IF NOT EXISTS idx_sentiments_segment_id ON Sentiments(segment_id);
CREATE INDEX IF NOT EXISTS idx_auditlogs_user_id ON AuditLogs(user_id);
