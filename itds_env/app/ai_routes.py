"""
AI Features Blueprint
Handles AI-powered analysis features including topic modeling.
"""
from flask import Blueprint, request, jsonify, Response
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
import sqlite3
from .models import execute_safe_query
import logging
import traceback
import threading
import uuid
import os
import json
import tempfile
from datetime import datetime, timezone
import time
from .services.email_service import send_email, render_email_template
from .ai.themes import _normalize_theme_name

try:
    from redis import Redis
    from rq import Queue, Worker, get_current_job
    from rq.job import Job
    RQ_AVAILABLE = True
except Exception:
    Redis = None
    Queue = None
    Worker = None
    Job = None
    get_current_job = None
    RQ_AVAILABLE = False

ai_bp = Blueprint('ai', __name__)

from .validation import validate_json

BATCH_ANALYSIS_JOBS = {}
BATCH_ANALYSIS_LOCK = threading.Lock()
ASYNC_AUDIO_JOBS = {}
ASYNC_AUDIO_LOCK = threading.Lock()
_rq_connection = None
_rq_queue = None
_rq_warned = False
_ANOMALY_ALERT_CACHE = {}
_ANOMALY_ALERT_LOCK = threading.Lock()
_ANOMALY_ALERT_TTL_SECONDS = int(os.getenv('ANOMALY_ALERT_TTL_SECONDS', '21600'))


def _critical_anomaly_key(year, anomaly):
    return f"{year}:{anomaly.get('theme')}:{anomaly.get('month')}:{anomaly.get('z_score')}"


def _dedupe_critical_alerts(year, anomalies):
    now = time.time()
    fresh = []
    with _ANOMALY_ALERT_LOCK:
        expired = [key for key, ts in _ANOMALY_ALERT_CACHE.items() if now - ts > _ANOMALY_ALERT_TTL_SECONDS]
        for key in expired:
            _ANOMALY_ALERT_CACHE.pop(key, None)

        for anomaly in anomalies:
            key = _critical_anomaly_key(year, anomaly)
            if key in _ANOMALY_ALERT_CACHE:
                continue
            _ANOMALY_ALERT_CACHE[key] = now
            fresh.append(anomaly)
    return fresh


def _get_anomaly_alert_recipients():
    rows = execute_safe_query(
        '''
                SELECT user_id, username, email
                FROM Users
                WHERE COALESCE(is_deleted, 0) = 0
                    AND LOWER(COALESCE(role, '')) IN ('admin', 'super_admin')
                    AND COALESCE(email_alerts_enabled, 0) = 1
                    AND COALESCE(anomaly_email_alerts_enabled, 1) = 1
                    AND email IS NOT NULL
                    AND TRIM(email) <> ''
        '''
    )
    return rows or []


def _send_critical_anomaly_alerts(year, anomalies, actor):
    recipients = _get_anomaly_alert_recipients()
    if not recipients:
        return {'sent': 0, 'failed': 0, 'skipped': len(anomalies), 'reason': 'no_opted_in_admin_recipients'}

    new_anomalies = _dedupe_critical_alerts(year, anomalies)
    if not new_anomalies:
        return {'sent': 0, 'failed': 0, 'skipped': len(anomalies), 'reason': 'throttled_duplicates'}

    sent = 0
    failed = 0
    anomaly_lines = []
    for item in new_anomalies[:10]:
        anomaly_lines.append(
            f"<li><strong>{item.get('theme')}</strong> ({item.get('month')}): "
            f"{item.get('mention_count')} mentions vs baseline {item.get('expected_baseline')} "
            f"(z={item.get('z_score')})</li>"
        )
    list_html = '<ul style="margin:8px 0 16px 18px;">' + ''.join(anomaly_lines) + '</ul>'
    extra_count = max(0, len(new_anomalies) - 10)
    if extra_count:
        list_html += f"<p style=\"margin:0 0 12px;\">...and {extra_count} more critical anomalies.</p>"

    actor_name = actor.get('username') or 'system'
    body_html = (
        f"<p style=\"margin:0 0 12px;\">Critical trend anomalies were detected for <strong>{year}</strong>.</p>"
        f"{list_html}"
        f"<p style=\"margin:0;\">Triggered by: <strong>{actor_name}</strong>.</p>"
    )
    note_html = (
        '<p style="margin:10px 0 0;padding:12px 14px;background:#fef2f2;'
        'border:1px solid #fecaca;border-radius:8px;font-size:13px;line-height:1.6;color:#b91c1c;">'
        'Please review flagged themes before using them for governance decisions.</p>'
    )

    subject = f"Board Minutes Alert: {len(new_anomalies)} Critical Theme Anomalies ({year})"
    for recipient in recipients:
        html_content, text_content = render_email_template(
            username=recipient.get('username') or 'Admin',
            title='Critical Theme Anomalies Detected',
            intro='The anomaly monitor found unusual spikes in theme activity.',
            body_html=body_html,
            note_html=note_html,
            action_text='Review anomalies in the Trend Analysis Dashboard.'
        )
        ok = send_email(recipient.get('email'), subject, html_content, text_content)
        if ok:
            sent += 1
        else:
            failed += 1

    _log_transcript_action('critical_theme_anomaly_email_alert', {
        'year': year,
        'critical_count': len(new_anomalies),
        'sent': sent,
        'failed': failed,
    })
    return {'sent': sent, 'failed': failed, 'skipped': len(anomalies) - len(new_anomalies), 'reason': None}


def _get_actor_context():
    identity = get_jwt_identity()
    claims = get_jwt() or {}
    if isinstance(identity, dict):
        user_id = identity.get('user_id')
        username = identity.get('username') or claims.get('username') or 'unknown'
        role = str(identity.get('role') or claims.get('role') or '').lower()
    else:
        user_id = identity
        username = claims.get('username', 'unknown')
        role = str(claims.get('role', '')).lower()

    try:
        user_id = int(user_id)
    except Exception:
        user_id = None

    return {
        'user_id': user_id,
        'username': username,
        'role': role,
    }


def _log_transcript_action(action, details):
    try:
        actor = _get_actor_context()
        execute_safe_query(
            '''
            INSERT INTO AuditLogs (user_id, username, action, details, ip_address, user_agent, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                actor['user_id'],
                actor['username'],
                action,
                json.dumps({**(details or {}), 'actor_role': actor['role']}),
                request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown'),
                request.headers.get('User-Agent', 'Unknown'),
                datetime.now(timezone.utc).isoformat()
            ),
            fetch=False
        )
    except Exception as exc:
        logging.warning(f"Failed to log transcript action: {exc}")


def _ensure_deleted_meeting_snapshots_table():
    """Ensure snapshot table exists for recovering cleared meeting minutes."""
    execute_safe_query(
        '''
        CREATE TABLE IF NOT EXISTS DeletedMeetingSnapshots (
            snapshot_id INTEGER PRIMARY KEY,
            original_meeting_id INTEGER UNIQUE,
            meeting_date DATE,
            source_filename TEXT DEFAULT NULL,
            segments_json TEXT NOT NULL,
            deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_by INTEGER DEFAULT NULL,
            deleted_by_role TEXT DEFAULT NULL,
            delete_reason TEXT DEFAULT NULL
        )
        ''',
        fetch=False
    )

    # Backward-compatible schema repair for existing deployments.
    required_columns = {
        'source_filename': 'TEXT DEFAULT NULL',
        'deleted_by': 'INTEGER DEFAULT NULL',
        'deleted_by_role': 'TEXT DEFAULT NULL',
        'delete_reason': 'TEXT DEFAULT NULL',
    }
    existing_columns = execute_safe_query("PRAGMA table_info(DeletedMeetingSnapshots)")
    existing_names = {str(row.get('name') or '').strip() for row in existing_columns}
    for column_name, column_def in required_columns.items():
        if column_name not in existing_names:
            execute_safe_query(
                f"ALTER TABLE DeletedMeetingSnapshots ADD COLUMN {column_name} {column_def}",
                fetch=False
            )


def _snapshot_meeting_before_clear(meeting_id, actor):
    """Persist a recoverable snapshot of a meeting and its segments before deletion."""
    _ensure_deleted_meeting_snapshots_table()

    meeting_rows = execute_safe_query(
        'SELECT meeting_id, meeting_date, source_filename FROM Meetings WHERE meeting_id = ?',
        (meeting_id,)
    )
    if not meeting_rows:
        return False

    segment_rows = execute_safe_query(
        'SELECT segment_id, original_text, created_at FROM Segments WHERE meeting_id = ? ORDER BY segment_id',
        (meeting_id,)
    )

    segments_payload = [
        {
            'segment_id': row.get('segment_id'),
            'original_text': row.get('original_text') or '',
            'created_at': row.get('created_at'),
        }
        for row in segment_rows
    ]

    meeting = meeting_rows[0]
    execute_safe_query(
        '''
        INSERT INTO DeletedMeetingSnapshots (
            original_meeting_id,
            meeting_date,
            source_filename,
            segments_json,
            deleted_at,
            deleted_by,
            deleted_by_role,
            delete_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(original_meeting_id) DO UPDATE SET
            meeting_date = excluded.meeting_date,
            source_filename = excluded.source_filename,
            segments_json = excluded.segments_json,
            deleted_at = excluded.deleted_at,
            deleted_by = excluded.deleted_by,
            deleted_by_role = excluded.deleted_by_role,
            delete_reason = excluded.delete_reason
        ''',
        (
            meeting_id,
            meeting.get('meeting_date'),
            meeting.get('source_filename'),
            json.dumps(segments_payload),
            datetime.now(timezone.utc).isoformat(),
            actor.get('user_id'),
            actor.get('role'),
            'meeting clear',
        ),
        fetch=False
    )
    return True



@ai_bp.route('/api/ai/sentiments/<int:sentiment_id>', methods=['DELETE'])
@jwt_required()
def delete_sentiment_record_route(sentiment_id):
    """Delete a single sentiment report row by id."""
    try:
        actor = _get_actor_context()
        if actor['role'] not in {'admin', 'super_admin', 'editor'}:
            return jsonify({'error': 'Insufficient privileges'}), 403

        existing = execute_safe_query(
            'SELECT sentiment_id, segment_id FROM Sentiments WHERE sentiment_id = ? LIMIT 1',
            (sentiment_id,)
        )
        if not existing:
            return jsonify({'error': 'Sentiment record not found'}), 404

        execute_safe_query(
            'DELETE FROM Sentiments WHERE sentiment_id = ?',
            (sentiment_id,),
            fetch=False
        )

        _log_transcript_action('delete_sentiment_record', {
            'sentiment_id': sentiment_id,
            'segment_id': existing[0].get('segment_id'),
        })

        return jsonify({'message': 'Sentiment record deleted', 'sentiment_id': sentiment_id}), 200
    except Exception as e:
        logging.error(f"Delete sentiment record error: {e}")
        return jsonify({'error': 'Failed to delete sentiment record'}), 500


@ai_bp.route('/api/ai/keywords/<int:keyword_id>', methods=['DELETE'])
@jwt_required()
def delete_keyword_record_route(keyword_id):
    """Delete a single keyword report row by id."""
    try:
        actor = _get_actor_context()
        if actor['role'] not in {'admin', 'super_admin', 'editor'}:
            return jsonify({'error': 'Insufficient privileges'}), 403

        existing = execute_safe_query(
            'SELECT keyword_id, segment_id FROM Keywords WHERE keyword_id = ? LIMIT 1',
            (keyword_id,)
        )
        if not existing:
            return jsonify({'error': 'Keyword record not found'}), 404

        execute_safe_query(
            'DELETE FROM Keywords WHERE keyword_id = ?',
            (keyword_id,),
            fetch=False
        )

        _log_transcript_action('delete_keyword_record', {
            'keyword_id': keyword_id,
            'segment_id': existing[0].get('segment_id'),
        })

        return jsonify({'message': 'Keyword record deleted', 'keyword_id': keyword_id}), 200
    except Exception as e:
        logging.error(f"Delete keyword record error: {e}")
        return jsonify({'error': 'Failed to delete keyword record'}), 500

def _table_exists(table_name):
    try:
        result = execute_safe_query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
            (table_name,)
        )
        return bool(result)
    except Exception:
        return False


def _table_has_column(table_name, column_name):
    try:
        if not _table_exists(table_name):
            return False
        columns = execute_safe_query(f"PRAGMA table_info({table_name})")
        return any(str(col.get('name') or '').strip().lower() == column_name.lower() for col in columns)
    except Exception:
        return False


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def _set_job_state(job_id, updates):
    with BATCH_ANALYSIS_LOCK:
        job = BATCH_ANALYSIS_JOBS.get(job_id, {})
        job.update(updates)
        BATCH_ANALYSIS_JOBS[job_id] = job

    # Mirror progress into RQ job metadata when running inside an RQ worker.
    if get_current_job is not None:
        try:
            current_job = get_current_job()
            if current_job and current_job.id == job_id:
                merged = dict(current_job.meta or {})
                merged.update(BATCH_ANALYSIS_JOBS.get(job_id, {}))
                current_job.meta = merged
                current_job.save_meta()
        except Exception:
            pass


def _is_batch_job_cancel_requested(job_id):
    with BATCH_ANALYSIS_LOCK:
        job = BATCH_ANALYSIS_JOBS.get(job_id) or {}
        if bool(job.get('cancel_requested')):
            return True

    # When running inside RQ worker, prefer local job meta.
    if get_current_job is not None:
        try:
            current_job = get_current_job()
            if current_job and current_job.id == job_id:
                return bool((current_job.meta or {}).get('cancel_requested'))
        except Exception:
            pass

    # Cross-process check for RQ workers.
    queue = _get_rq_queue()
    if queue and Job is not None:
        try:
            rq_job = Job.fetch(job_id, connection=queue.connection)
            if bool((rq_job.meta or {}).get('cancel_requested')):
                return True
        except Exception:
            pass

    return False


def _set_audio_job_state(job_id, updates):
    with ASYNC_AUDIO_LOCK:
        job = ASYNC_AUDIO_JOBS.get(job_id, {})
        job.update(updates)
        ASYNC_AUDIO_JOBS[job_id] = job


def _is_audio_job_cancel_requested(job_id):
    with ASYNC_AUDIO_LOCK:
        job = ASYNC_AUDIO_JOBS.get(job_id) or {}
        return bool(job.get('cancel_requested'))


def _mark_audio_job_canceled(job_id, message='Audio processing canceled by user'):
    _set_audio_job_state(job_id, {
        'status': 'canceled',
        'message': message,
        'current_step': 'canceled',
        'progress': 100,
        'finished_at': _utc_now_iso(),
    })


def _normalize_audio_mode(mode):
    mode = str(mode or 'fast').strip().lower()
    return 'full' if mode == 'full' else 'fast'


def _run_async_audio_job(job_id, temp_path, user_id, source_filename, mode='fast'):
    mode = _normalize_audio_mode(mode)
    try:
        if _is_audio_job_cancel_requested(job_id):
            _mark_audio_job_canceled(job_id)
            return

        _set_audio_job_state(job_id, {
            'status': 'running',
            'message': 'Transcribing uploaded audio...',
            'current_step': 'transcribing',
            'progress': 35,
        })

        from .ai.speech import transcribe_audio_file, process_recording_transcript, FAST_AUDIO_SECONDS
        transcript_text = transcribe_audio_file(temp_path, max_seconds=(FAST_AUDIO_SECONDS if mode == 'fast' else 0))

        if _is_audio_job_cancel_requested(job_id):
            _mark_audio_job_canceled(job_id)
            return

        _set_audio_job_state(job_id, {
            'status': 'running',
            'message': 'Analyzing transcript...',
            'current_step': 'analyzing',
            'progress': 75,
        })

        result = process_recording_transcript(
            transcript_text,
            user_id,
            source_filename=source_filename,
            full_pipeline=(mode == 'full'),
        )

        _set_audio_job_state(job_id, {
            'status': 'completed',
            'message': 'Audio upload completed successfully',
            'current_step': 'completed',
            'progress': 100,
            'finished_at': _utc_now_iso(),
            'result': result,
        })
    except Exception as exc:
        logging.error(f"Async audio job failed for {job_id}: {exc}", exc_info=True)
        _set_audio_job_state(job_id, {
            'status': 'failed',
            'message': 'Audio transcription failed',
            'current_step': 'failed',
            'progress': 100,
            'finished_at': _utc_now_iso(),
            'error': str(exc),
        })
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def _get_rq_queue():
    """Return a connected RQ queue if Redis is configured and reachable."""
    global _rq_connection, _rq_queue, _rq_warned

    if not RQ_AVAILABLE:
        return None

    if _rq_queue is not None:
        return _rq_queue

    redis_url = os.getenv('REDIS_URL', '').strip()
    if not redis_url:
        return None

    try:
        _rq_connection = Redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
        _rq_connection.ping()
        _rq_queue = Queue('batch-analysis', connection=_rq_connection, default_timeout=60 * 60 * 2)
        return _rq_queue
    except Exception as exc:
        if not _rq_warned:
            logging.warning(f"RQ disabled (Redis not reachable): {exc}")
            _rq_warned = True
        _rq_connection = None
        _rq_queue = None
        return None


def _has_active_rq_worker(queue):
    """Return True when there is an active worker listening on the batch-analysis queue."""
    if os.name == 'nt':
        # Windows workers are best handled in-process for this app's long-running jobs.
        return False

    if not queue or Worker is None:
        return False

    try:
        workers = Worker.all(connection=queue.connection)
    except Exception:
        return False

    for worker in workers or []:
        try:
            queue_names = list(worker.queue_names())
        except Exception:
            queue_names = [q.name for q in getattr(worker, 'queues', [])]

        if queue.name in queue_names:
            return True

    return False


def _count_meetings_for_batch(payload):
    """Count meetings that the current batch run will attempt to process."""
    requested_ids = payload.get('meeting_ids') if isinstance(payload.get('meeting_ids'), list) else None

    if requested_ids:
        placeholders = ','.join(['?'] * len(requested_ids))
        rows = execute_safe_query(
            f'''SELECT COUNT(DISTINCT meeting_id) AS count
                FROM Meetings
                WHERE meeting_id IN ({placeholders})''',
            tuple(requested_ids)
        )
    else:
        rows = execute_safe_query('SELECT COUNT(DISTINCT meeting_id) AS count FROM Meetings')

    if not rows:
        return 0

    return int(rows[0].get('count', 0) or 0)


def _hydrate_status_from_rq(job_id):
    """Fetch job status from RQ backend (used after API restarts)."""
    queue = _get_rq_queue()
    if not queue or Job is None:
        return None

    try:
        rq_job = Job.fetch(job_id, connection=queue.connection)
    except Exception:
        return None

    meta = dict(rq_job.meta or {})
    raw_status = rq_job.get_status(refresh=True)
    mapped = {
        'queued': 'queued',
        'started': 'running',
        'deferred': 'queued',
        'finished': 'completed',
        'failed': 'failed',
        'stopped': 'failed',
        'canceled': 'failed',
    }.get(raw_status, raw_status or 'queued')

    job = {
        'job_id': job_id,
        'status': mapped,
        'message': meta.get('message', f'Batch analysis {mapped}'),
        'current_step': meta.get('current_step', mapped),
        'processed_meetings': meta.get('processed_meetings', 0),
        'total_meetings': meta.get('total_meetings', 0),
        'totals': meta.get('totals', {
            'summaries': 0,
            'sentiments': 0,
            'action_items': 0,
            'keywords': 0,
            'topics': 0,
            'failed_meetings': 0,
        }),
        'loader_errors': meta.get('loader_errors', []),
        'details': meta.get('details', []),
        'started_at': meta.get('started_at'),
        'finished_at': meta.get('finished_at'),
        'error': meta.get('error'),
        'backend': 'rq',
    }

    if mapped == 'completed' and isinstance(rq_job.result, dict):
        result = rq_job.result
        job.update({
            'processed_meetings': result.get('processed_meetings', job['processed_meetings']),
            'total_meetings': result.get('processed_meetings', job['total_meetings']),
            'totals': result.get('totals', job['totals']),
            'details': result.get('details', job['details']),
            'loader_errors': result.get('loader_errors', job['loader_errors']),
            'message': meta.get('message', 'Batch analysis completed'),
        })

    return job


def _execute_batch_analysis_job(payload, job_id):
    """Worker entrypoint for RQ and local thread workers."""
    try:
        _set_job_state(job_id, {
            'status': 'running',
            'message': 'Batch analysis started',
            'current_step': 'initializing',
        })
        result = _run_batch_analysis_with_cache_invalidation(payload, job_id=job_id)
        if result.get('canceled'):
            _set_job_state(job_id, {
                'status': 'canceled',
                'message': result.get('message') or 'Batch analysis canceled',
                'current_step': 'canceled',
                'processed_meetings': result.get('processed_meetings', 0),
                'total_meetings': result.get('total_meetings', result.get('processed_meetings', 0)),
                'totals': result.get('totals', {}),
                'details': result.get('details', []),
                'loader_errors': result.get('loader_errors', []),
                'finished_at': _utc_now_iso(),
            })
        else:
            _set_job_state(job_id, {
                'status': 'completed',
                'message': 'Batch analysis completed',
                'current_step': 'completed',
                'processed_meetings': result.get('processed_meetings', 0),
                'total_meetings': result.get('processed_meetings', 0),
                'totals': result.get('totals', {}),
                'details': result.get('details', []),
                'loader_errors': result.get('loader_errors', []),
                'finished_at': _utc_now_iso(),
            })
        return result
    except Exception as worker_error:
        logging.error(f"Async batch analysis failed for job {job_id}: {worker_error}")
        _set_job_state(job_id, {
            'status': 'failed',
            'message': 'Batch analysis failed',
            'current_step': 'failed',
            'error': str(worker_error),
            'finished_at': _utc_now_iso(),
        })
        raise

@ai_bp.route('/api/ai/summarize', methods=['POST'])
@jwt_required()
@validate_json({'meeting_id': int})
def summarize():
    """Summarize meeting segments."""
    try:
        from .ai.summarizer import summarize_segments
        
        data = request.get_json()
        meeting_id = data.get('meeting_id')

        summaries = summarize_segments(meeting_id)
        return jsonify({'summaries': summaries}), 200
    except Exception as e:
        logging.error(f"Summarize error: {e}")
        return jsonify({'error': 'Summarization failed'}), 500

@ai_bp.route('/api/ai/sentiment', methods=['POST'])
@jwt_required()
@validate_json({'meeting_id': int})
def analyze_sentiment_route():
    """Analyze sentiment of meeting segments."""
    try:
        from .ai.sentiment import analyze_sentiment
        
        data = request.get_json()
        meeting_id = data.get('meeting_id')

        sentiments = analyze_sentiment(meeting_id)
        return jsonify({'sentiments': sentiments}), 200
    except Exception as e:
        logging.error(f"Sentiment analysis error: {e}")
        return jsonify({'error': 'Sentiment analysis failed'}), 500


@ai_bp.route('/api/ai/answer-question', methods=['POST'])
@jwt_required()
@validate_json({'question': str})
def answer_question_route():
    """Answer a natural language question about meeting minutes."""
    try:
        from .ai.qa import answer_question
        
        data = request.get_json()
        question = (data or {}).get('question', '').strip()
        history = data.get('history', [])
        
        if not question:
            return jsonify({'error': 'Question required'}), 400
            
        
        result = answer_question(question, history=history)
        
        return jsonify({
            'question': question,
            'answer': result.get('answer'),
            'confidence': result.get('confidence'),
            'context_preview': result.get('context'),
            'success': True
        }), 200
    except Exception as e:
        logging.error(f"QA error: {e}")
        return jsonify({'error': 'Failed to answer question', 'details': str(e)}), 500


@ai_bp.route('/api/ai/transcribe', methods=['POST'])
@jwt_required()
@validate_json({'transcript': str})
def transcribe_route():
    """Save live voice transcript and run the full meeting analysis pipeline."""
    try:
        data = request.get_json()
        transcript = data.get('transcript')
        if not transcript:
            return jsonify({'error': 'Transcript required'}), 400
        
        identity = get_jwt_identity()
        user_id = int(identity) if isinstance(identity, (str, int)) else int(identity.get('user_id', identity))
        
        from .ai.speech import process_recording_transcript
        result = process_recording_transcript(transcript, user_id)
        
        return jsonify({
            'transcript_id': result.get('transcript_id'),
            'meeting_id': result.get('meeting_id'),
            'segment_count': result.get('segment_count', 0),
            'summary_count': result.get('summary_count', 0),
            'sentiment_count': result.get('sentiment_count', 0),
            'action_item_count': result.get('action_item_count', 0),
            'keyword_count': result.get('keyword_count', 0),
            'topic_count': result.get('topic_count', 0),
            'message': result.get('message', 'Transcript analyzed successfully')
        }), 201
    except Exception as e:
        logging.error(f"Transcribe error: {e}")
        return jsonify({'error': 'Transcript save failed'}), 500


@ai_bp.route('/api/ai/transcribe-audio', methods=['POST'])
@jwt_required()
def transcribe_audio_route():
    """Upload an audio file, transcribe it, and run full meeting analysis."""
    temp_path = None
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'Audio file is required'}), 400

        audio_file = request.files['audio']
        if not audio_file or not audio_file.filename:
            return jsonify({'error': 'Audio file is required'}), 400

        extension = os.path.splitext(audio_file.filename)[1].lower()
        allowed_extensions = {'.wav', '.mp3', '.m4a', '.webm', '.mp4'}
        if extension not in allowed_extensions:
            return jsonify({'error': 'Unsupported audio format. Use WAV, MP3, M4A, WEBM, or MP4.'}), 400

        mode = _normalize_audio_mode(request.form.get('mode', 'fast'))

        identity = get_jwt_identity()
        if isinstance(identity, (str, int)):
            user_id = int(identity)
        elif isinstance(identity, dict) and identity.get('user_id') is not None:
            user_id = int(identity.get('user_id'))
        else:
            raise ValueError(f'Invalid JWT identity: {identity}')

        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as temp_file:
            audio_file.save(temp_file.name)
            temp_path = temp_file.name

        from .ai.speech import transcribe_audio_file, process_recording_transcript, FAST_AUDIO_SECONDS

        transcript_text = transcribe_audio_file(temp_path, max_seconds=(FAST_AUDIO_SECONDS if mode == 'fast' else 0))
        analysis_result = process_recording_transcript(
            transcript_text,
            user_id,
            source_filename=audio_file.filename or 'uploaded_audio.wav',
            full_pipeline=(mode == 'full'),
        )

        return jsonify(analysis_result), 201
    except Exception as e:
        logging.error(f"Audio transcribe error: {e}")
        return jsonify({'error': str(e) or 'Audio transcription failed'}), 500
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


@ai_bp.route('/api/ai/transcribe-audio/start', methods=['POST'])
@jwt_required()
def transcribe_audio_start_route():
    """Queue uploaded audio for background transcription+analysis and return a job id."""
    temp_path = None
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'Audio file is required'}), 400

        audio_file = request.files['audio']
        if not audio_file or not audio_file.filename:
            return jsonify({'error': 'Audio file is required'}), 400

        extension = os.path.splitext(audio_file.filename)[1].lower()
        allowed_extensions = {'.wav', '.mp3', '.m4a', '.webm', '.mp4'}
        if extension not in allowed_extensions:
            return jsonify({'error': 'Unsupported audio format. Use WAV, MP3, M4A, WEBM, or MP4.'}), 400

        mode = _normalize_audio_mode(request.form.get('mode', 'fast'))

        identity = get_jwt_identity()
        if isinstance(identity, (str, int)):
            user_id = int(identity)
        elif isinstance(identity, dict) and identity.get('user_id') is not None:
            user_id = int(identity.get('user_id'))
        else:
            raise ValueError(f'Invalid JWT identity: {identity}')

        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as temp_file:
            audio_file.save(temp_file.name)
            temp_path = temp_file.name

        job_id = str(uuid.uuid4())
        _set_audio_job_state(job_id, {
            'job_id': job_id,
            'status': 'queued',
            'message': 'Audio received. Processing in background...',
            'current_step': 'queued',
            'progress': 5,
            'started_at': _utc_now_iso(),
            'finished_at': None,
            'error': None,
            'result': None,
        })

        thread = threading.Thread(
            target=_run_async_audio_job,
            args=(job_id, temp_path, user_id, audio_file.filename or 'uploaded_audio.wav', mode),
            daemon=True,
        )
        thread.start()

        return jsonify({
            'job_id': job_id,
            'status': 'queued',
            'message': f'Audio upload accepted. {mode.title()} mode transcription is running in background.',
            'mode': mode,
        }), 202
    except Exception as e:
        logging.error(f"Audio start error: {e}")
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        return jsonify({'error': str(e) or 'Audio transcription start failed'}), 500


@ai_bp.route('/api/ai/transcribe-audio/status/<job_id>', methods=['GET'])
@jwt_required()
def transcribe_audio_status_route(job_id):
    """Get background audio transcription job state."""
    with ASYNC_AUDIO_LOCK:
        job = dict(ASYNC_AUDIO_JOBS.get(job_id) or {})

    if not job:
        return jsonify({'error': 'Audio job not found'}), 404

    return jsonify(job), 200


@ai_bp.route('/api/ai/transcribe-audio/cancel/<job_id>', methods=['POST'])
@jwt_required()
def transcribe_audio_cancel_route(job_id):
    """Request cancellation of an in-flight async audio transcription job."""
    with ASYNC_AUDIO_LOCK:
        job = ASYNC_AUDIO_JOBS.get(job_id)

    if not job:
        return jsonify({'error': 'Audio job not found'}), 404

    current_status = str(job.get('status') or '').lower()
    if current_status in {'completed', 'failed', 'canceled'}:
        return jsonify({'job_id': job_id, 'status': current_status, 'message': 'Job already finalized'}), 200

    _set_audio_job_state(job_id, {
        'cancel_requested': True,
        'message': 'Cancel requested. Stopping audio job...',
        'current_step': 'canceling',
    })

    return jsonify({'job_id': job_id, 'status': 'canceling', 'message': 'Cancellation requested'}), 202


@ai_bp.route('/api/ai/transcripts', methods=['GET'])
@jwt_required()
def get_transcripts_route():
    """Get user's voice transcripts history."""
    try:
        actor = _get_actor_context()
        claims = get_jwt() or {}
        role = actor['role']
        user_id = actor['user_id']
        include_deleted = request.args.get('include_deleted', '0') == '1' and role == 'super_admin'

        if role in {'admin', 'super_admin'}:
            query = '''SELECT transcript_id, user_id, transcript_text, sentiment, keywords, analysis_complete, created_at, is_deleted, deleted_at, delete_reason
                       FROM Transcripts'''
            if not include_deleted:
                query += ' WHERE COALESCE(is_deleted, 0) = 0'
            query += ' ORDER BY created_at DESC LIMIT 200'
            transcripts = execute_safe_query(
                query
            )
        else:
            transcripts = execute_safe_query(
                '''SELECT transcript_id, user_id, transcript_text, sentiment, keywords, analysis_complete, created_at, is_deleted, deleted_at, delete_reason
                   FROM Transcripts
                   WHERE user_id = ? AND COALESCE(is_deleted, 0) = 0
                   ORDER BY created_at DESC
                   LIMIT 20''',
                (user_id,)
            )

        try:
            from .ai.speech import analyze_sentiment_fast
            for transcript in transcripts:
                if not transcript.get('sentiment') and transcript.get('transcript_text'):
                    derived_sentiment, derived_confidence = analyze_sentiment_fast(transcript.get('transcript_text'))
                    transcript['sentiment'] = derived_sentiment
                    transcript['sentiment_confidence'] = derived_confidence
        except Exception as sentiment_exc:
            logging.warning(f"Transcript sentiment hydration failed: {sentiment_exc}")

        return jsonify({'transcripts': transcripts}), 200
    except Exception as e:
        logging.error(f"Transcripts error: {e}")
        return jsonify({'error': 'Failed to fetch transcripts', 'transcripts': []}), 500


@ai_bp.route('/api/ai/transcripts/<int:transcript_id>', methods=['DELETE'])
@jwt_required()
def delete_transcript_route(transcript_id):
    """Soft delete a transcript by default, or permanently delete for super admins with ?permanent=1."""
    try:
        actor = _get_actor_context()
        permanent = request.args.get('permanent', '0') == '1'
        if permanent and actor['role'] != 'super_admin':
            return jsonify({'error': 'Super admin access required for permanent delete'}), 403

        user_id = actor['user_id']
        if actor['role'] in {'admin', 'super_admin'}:
            existing = execute_safe_query(
                'SELECT transcript_id, user_id, transcript_text, is_deleted FROM Transcripts WHERE transcript_id = ?',
                (transcript_id,)
            )
        else:
            existing = execute_safe_query(
                'SELECT transcript_id, user_id, transcript_text, is_deleted FROM Transcripts WHERE transcript_id = ? AND user_id = ?',
                (transcript_id, user_id)
            )
        if not existing:
            return jsonify({'error': 'Transcript not found'}), 404

        target = existing[0]
        if permanent:
            execute_safe_query(
                'DELETE FROM Transcripts WHERE transcript_id = ?',
                (transcript_id,),
                fetch=False
            )
        else:
            execute_safe_query(
                'UPDATE Transcripts SET is_deleted = 1, deleted_at = ?, deleted_by = ?, delete_reason = ? WHERE transcript_id = ?',
                (datetime.now(timezone.utc).isoformat(), user_id, 'soft delete', transcript_id),
                fetch=False
            )

        _log_transcript_action(
            'delete_transcript_permanent' if permanent else 'soft_delete_transcript',
            {'transcript_id': transcript_id, 'user_id': target['user_id'], 'permanent': permanent}
        )

        return jsonify({'message': 'Transcript deleted successfully', 'transcript_id': transcript_id, 'permanent': permanent}), 200
    except Exception as e:
        logging.error(f"Transcript delete error: {e}")
        return jsonify({'error': 'Failed to delete transcript'}), 500


@ai_bp.route('/api/ai/transcripts', methods=['DELETE'])
@jwt_required()
def delete_all_transcripts_route():
    """Soft delete all transcripts for the current user, or permanently delete for super admins with ?permanent=1."""
    try:
        actor = _get_actor_context()
        role = actor['role']
        user_id = actor['user_id']
        permanent = request.args.get('permanent', '0') == '1'
        full_cleanup = request.args.get('full_cleanup', '0') == '1'
        hard_delete = request.args.get('hard_delete', '0') == '1'
        deleted_only = request.args.get('deleted_only', '0') == '1'

        if hard_delete:
            permanent = True
            # Safety default: hard-delete endpoint should only purge already deleted data.
            deleted_only = True
            full_cleanup = False

        if permanent and role != 'super_admin':
            return jsonify({'error': 'Super admin access required for permanent delete'}), 403
        if full_cleanup and role not in {'admin', 'super_admin'}:
            return jsonify({'error': 'Admin access required for full cleanup'}), 403
        if hard_delete and role != 'super_admin':
            return jsonify({'error': 'Super admin access required for hard delete'}), 403
        if deleted_only and role != 'super_admin':
            return jsonify({'error': 'Super admin access required for deleted-only purge'}), 403

        snapshots_purged = 0

        if permanent and deleted_only:
            existing = execute_safe_query(
                'SELECT COUNT(*) AS count FROM Transcripts WHERE COALESCE(is_deleted, 0) = 1'
            )
            total_before = int(existing[0].get('count', 0)) if existing else 0
            if _table_exists('DeletedMeetingSnapshots'):
                snapshot_rows = execute_safe_query('SELECT COUNT(*) AS count FROM DeletedMeetingSnapshots')
                snapshots_purged = int(snapshot_rows[0].get('count', 0)) if snapshot_rows else 0
        elif role in {'admin', 'super_admin'}:
            existing = execute_safe_query(
                'SELECT COUNT(*) AS count FROM Transcripts WHERE COALESCE(is_deleted, 0) = 0'
            )
            total_before = int(existing[0].get('count', 0)) if existing else 0
        else:
            existing = execute_safe_query(
                'SELECT COUNT(*) AS count FROM Transcripts WHERE user_id = ? AND COALESCE(is_deleted, 0) = 0',
                (user_id,)
            )
            total_before = int(existing[0].get('count', 0)) if existing else 0

        if permanent:
            if deleted_only:
                execute_safe_query(
                    'DELETE FROM Transcripts WHERE COALESCE(is_deleted, 0) = 1',
                    fetch=False
                )
                if _table_exists('DeletedMeetingSnapshots'):
                    execute_safe_query('DELETE FROM DeletedMeetingSnapshots', fetch=False)
            else:
                execute_safe_query(
                    'DELETE FROM Transcripts',
                    fetch=False
                )
        else:
            if role in {'admin', 'super_admin'}:
                execute_safe_query(
                    '''UPDATE Transcripts
                       SET is_deleted = 1,
                           deleted_at = ?,
                           deleted_by = ?,
                           delete_reason = ?,
                           sentiment = NULL,
                           keywords = NULL,
                           analysis_complete = 0,
                           analysis_cleared_at = ?,
                           analysis_cleared_by = ?
                       WHERE COALESCE(is_deleted, 0) = 0''',
                    (datetime.now(timezone.utc).isoformat(), user_id, 'bulk soft delete', datetime.now(timezone.utc).isoformat(), user_id),
                    fetch=False
                )
            else:
                execute_safe_query(
                    '''UPDATE Transcripts
                       SET is_deleted = 1,
                           deleted_at = ?,
                           deleted_by = ?,
                           delete_reason = ?,
                           sentiment = NULL,
                           keywords = NULL,
                           analysis_complete = 0,
                           analysis_cleared_at = ?,
                           analysis_cleared_by = ?
                       WHERE user_id = ? AND COALESCE(is_deleted, 0) = 0''',
                    (datetime.now(timezone.utc).isoformat(), user_id, 'bulk soft delete', datetime.now(timezone.utc).isoformat(), user_id, user_id),
                    fetch=False
                )

        if full_cleanup:
            # Preserve deleted records for super-admin recovery.
            # Snapshot all current meetings before removing meeting-derived tables.
            snapshots_created = 0
            if not hard_delete:
                meeting_rows = execute_safe_query('SELECT meeting_id FROM Meetings') if _table_exists('Meetings') else []
                meeting_ids = [int(row['meeting_id']) for row in meeting_rows if row.get('meeting_id') is not None]
                for meeting_id in meeting_ids:
                    snapshot_saved = _snapshot_meeting_before_clear(meeting_id, actor)
                    if not snapshot_saved:
                        raise RuntimeError(f"Snapshot not created for meeting_id={meeting_id}")
                    snapshots_created += 1

                if meeting_ids and snapshots_created != len(meeting_ids):
                    raise RuntimeError(
                        f"Snapshot mismatch before cleanup (expected={len(meeting_ids)}, saved={snapshots_created})"
                    )

            # Keep transcript rows (soft-deleted) but detach meeting references so meeting purge can proceed.
            if (not permanent) and _table_has_column('Transcripts', 'meeting_id'):
                execute_safe_query('UPDATE Transcripts SET meeting_id = NULL WHERE meeting_id IS NOT NULL', fetch=False)

            # Remove all meeting-derived analysis artifacts.
            # Event tables must be ordered by FK dependencies: deliveries/jobs -> announcements -> meetings.
            for table_name in [
                'Analysis',
                'Summaries',
                'Sentiments',
                'ActionItems',
                'Keywords',
                'Topics',
                'Segments',
                'EventAnnouncementDeliveries',
                'EventReminderJobs',
                'EventAnnouncements'
            ]:
                if _table_exists(table_name):
                    execute_safe_query(f'DELETE FROM {table_name}', fetch=False)

            if _table_exists('DocumentClassifications'):
                execute_safe_query('DELETE FROM DocumentClassifications', fetch=False)

            if _table_exists('Meetings'):
                execute_safe_query('DELETE FROM Meetings', fetch=False)

            if hard_delete and _table_exists('DeletedMeetingSnapshots'):
                execute_safe_query('DELETE FROM DeletedMeetingSnapshots', fetch=False)

        _log_transcript_action(
            'purge_all_transcripts' if permanent else 'soft_delete_all_transcripts',
            {
                'user_id': user_id,
                'count': total_before,
                'permanent': permanent,
                'full_cleanup': full_cleanup,
                'deleted_only': deleted_only,
                'deleted_meeting_snapshots_purged': snapshots_purged,
            }
        )

        return jsonify({
            'message': 'Deleted minutes and recordings permanently purged' if deleted_only else ('System data permanently deleted' if hard_delete else 'All transcripts deleted successfully'),
            'deleted_count': total_before,
            'permanent': permanent,
            'full_cleanup': full_cleanup,
            'hard_delete': hard_delete,
            'deleted_only': deleted_only,
            'deleted_meeting_snapshots_purged': snapshots_purged,
            'snapshots_created': snapshots_created if full_cleanup else 0
        }), 200
    except sqlite3.IntegrityError as e:
        logging.error(f"Bulk transcript delete integrity error: {e}")
        error_message = str(e).strip() or 'Failed to delete all transcripts'
        return jsonify({'error': error_message}), 409
    except Exception as e:
        logging.error(f"Bulk transcript delete error: {e}")
        error_message = str(e).strip() or 'Failed to delete all transcripts'
        return jsonify({'error': error_message}), 500


@ai_bp.route('/api/ai/transcripts/<int:transcript_id>/restore', methods=['POST'])
@jwt_required()
def restore_transcript_route(transcript_id):
    """Restore a soft-deleted transcript."""
    try:
        actor = _get_actor_context()
        if actor['role'] not in {'admin', 'super_admin'}:
            return jsonify({'error': 'Admin access required'}), 403

        existing = execute_safe_query('SELECT transcript_id, transcript_text, is_deleted FROM Transcripts WHERE transcript_id = ?', (transcript_id,))
        if not existing:
            return jsonify({'error': 'Transcript not found'}), 404

        if not existing[0].get('is_deleted'):
            return jsonify({'message': 'Transcript is already active'}), 200

        execute_safe_query(
            'UPDATE Transcripts SET is_deleted = 0, deleted_at = NULL, deleted_by = NULL, delete_reason = NULL WHERE transcript_id = ?',
            (transcript_id,),
            fetch=False
        )
        _log_transcript_action('restore_transcript', {'transcript_id': transcript_id})
        return jsonify({'message': 'Transcript restored successfully', 'transcript_id': transcript_id}), 200
    except Exception as e:
        logging.error(f"Restore transcript error: {e}")
        return jsonify({'error': 'Failed to restore transcript'}), 500


@ai_bp.route('/api/ai/transcripts/<int:transcript_id>/clear-analysis', methods=['POST'])
@jwt_required()
def clear_transcript_analysis_route(transcript_id):
    """Clear the sentiment/keywords analysis from a transcript."""
    try:
        actor = _get_actor_context()
        if actor['role'] not in {'admin', 'super_admin'}:
            return jsonify({'error': 'Admin access required'}), 403

        existing = execute_safe_query('SELECT transcript_id FROM Transcripts WHERE transcript_id = ?', (transcript_id,))
        if not existing:
            return jsonify({'error': 'Transcript not found'}), 404

        execute_safe_query(
            '''UPDATE Transcripts
               SET sentiment = NULL,
                   keywords = NULL,
                   analysis_complete = 0,
                   analysis_cleared_at = ?,
                   analysis_cleared_by = ?
               WHERE transcript_id = ?''',
            (datetime.now(timezone.utc).isoformat(), actor['user_id'], transcript_id),
            fetch=False
        )
        _log_transcript_action('clear_transcript_analysis', {'transcript_id': transcript_id})
        return jsonify({'message': 'Transcript analysis cleared', 'transcript_id': transcript_id}), 200
    except Exception as e:
        logging.error(f"Clear transcript analysis error: {e}")
        return jsonify({'error': 'Failed to clear transcript analysis'}), 500


@ai_bp.route('/api/ai/transcripts/clear-analysis', methods=['POST'])
@jwt_required()
def clear_all_transcript_analysis_route():
    """Bulk clear transcript analysis for the current user's scope."""
    try:
        actor = _get_actor_context()
        if actor['role'] not in {'admin', 'super_admin'}:
            return jsonify({'error': 'Admin access required'}), 403

        if actor['role'] == 'super_admin':
            query = 'UPDATE Transcripts SET sentiment = NULL, keywords = NULL, analysis_complete = 0, analysis_cleared_at = ?, analysis_cleared_by = ? WHERE COALESCE(is_deleted, 0) = 0'
            params = (datetime.now(timezone.utc).isoformat(), actor['user_id'])
        else:
            query = 'UPDATE Transcripts SET sentiment = NULL, keywords = NULL, analysis_complete = 0, analysis_cleared_at = ?, analysis_cleared_by = ? WHERE user_id = ? AND COALESCE(is_deleted, 0) = 0'
            params = (datetime.now(timezone.utc).isoformat(), actor['user_id'], actor['user_id'])

        execute_safe_query(query, params, fetch=False)
        _log_transcript_action('clear_all_transcript_analysis', {'scope': actor['role']})
        return jsonify({'message': 'Transcript analysis cleared'}), 200
    except Exception as e:
        logging.error(f"Clear all transcript analysis error: {e}")
        return jsonify({'error': 'Failed to clear transcript analysis'}), 500


@ai_bp.route('/api/ai/meetings/<int:meeting_id>/clear-minute-analysis', methods=['POST'])
@jwt_required()
def clear_meeting_minute_and_analysis_route(meeting_id):
    """Soft-delete linked transcripts and remove derived analysis for a meeting."""
    try:
        actor = _get_actor_context()
        if actor['role'] not in {'admin', 'super_admin'}:
            return jsonify({'error': 'Admin access required'}), 403

        meeting_rows = execute_safe_query('SELECT meeting_id FROM Meetings WHERE meeting_id = ?', (meeting_id,))
        if not meeting_rows:
            return jsonify({'error': 'Meeting not found'}), 404

        _snapshot_meeting_before_clear(meeting_id, actor)

        segment_rows = execute_safe_query('SELECT segment_id FROM Segments WHERE meeting_id = ?', (meeting_id,))
        segment_ids = [int(row['segment_id']) for row in segment_rows if row.get('segment_id') is not None]

        transcript_rows = execute_safe_query('SELECT transcript_id FROM Transcripts WHERE meeting_id = ?', (meeting_id,))
        transcript_ids = [int(row['transcript_id']) for row in transcript_rows if row.get('transcript_id') is not None]

        if transcript_ids:
            execute_safe_query(
                '''UPDATE Transcripts
                   SET is_deleted = 1,
                       deleted_at = ?,
                       deleted_by = ?,
                       delete_reason = ?,
                       sentiment = NULL,
                       keywords = NULL,
                       analysis_complete = 0,
                       analysis_cleared_at = ?,
                       analysis_cleared_by = ?,
                       meeting_id = NULL
                   WHERE meeting_id = ?''',
                (
                    datetime.now(timezone.utc).isoformat(),
                    actor['user_id'],
                    'meeting cleanup',
                    datetime.now(timezone.utc).isoformat(),
                    actor['user_id'],
                    meeting_id,
                ),
                fetch=False
            )

        if segment_ids:
            placeholders = ','.join(['?'] * len(segment_ids))
            for table_name in ['Analysis', 'Summaries', 'Sentiments', 'ActionItems', 'Keywords']:
                execute_safe_query(
                    f'DELETE FROM {table_name} WHERE segment_id IN ({placeholders})',
                    tuple(segment_ids),
                    fetch=False
                )

        execute_safe_query('DELETE FROM Topics WHERE meeting_id = ?', (meeting_id,), fetch=False)
        if _table_exists('DocumentClassifications'):
            execute_safe_query('DELETE FROM DocumentClassifications WHERE meeting_id = ?', (meeting_id,), fetch=False)
        execute_safe_query('DELETE FROM Segments WHERE meeting_id = ?', (meeting_id,), fetch=False)
        execute_safe_query('DELETE FROM Meetings WHERE meeting_id = ?', (meeting_id,), fetch=False)

        _log_transcript_action(
            'clear_meeting_minute_and_analysis',
            {
                'meeting_id': meeting_id,
                'segment_count': len(segment_ids),
                'transcript_count': len(transcript_ids),
                'actor_role': actor['role']
            }
        )

        return jsonify({
            'message': 'Meeting minute and analysis cleared',
            'meeting_id': meeting_id,
            'segment_count': len(segment_ids),
            'transcript_count': len(transcript_ids)
        }), 200
    except Exception as e:
        logging.error(f"Clear meeting minute and analysis error: {e}")
        return jsonify({'error': 'Failed to clear meeting minute and analysis'}), 500


@ai_bp.route('/api/ai/meetings/deleted', methods=['GET'])
@jwt_required()
def get_deleted_meeting_snapshots_route():
    """List deleted meeting snapshots for super admin recovery."""
    try:
        actor = _get_actor_context()
        if actor['role'] != 'super_admin':
            return jsonify({'error': 'Super admin access required'}), 403

        _ensure_deleted_meeting_snapshots_table()
        snapshots = execute_safe_query(
            '''
            SELECT
                snapshot_id,
                original_meeting_id AS meeting_id,
                meeting_date,
                source_filename,
                deleted_at,
                deleted_by,
                deleted_by_role,
                delete_reason,
                segments_json
            FROM DeletedMeetingSnapshots
            ORDER BY deleted_at DESC, snapshot_id DESC
            '''
        )
        for item in snapshots:
            try:
                payload = json.loads(item.get('segments_json') or '[]')
                item['segments_count'] = len(payload) if isinstance(payload, list) else 0
            except Exception:
                item['segments_count'] = 0
            item.pop('segments_json', None)
        return jsonify({'meetings': snapshots}), 200
    except Exception as e:
        logging.error(f"Deleted meeting snapshots list error: {e}")
        return jsonify({'error': 'Failed to load deleted meeting snapshots', 'meetings': []}), 500


@ai_bp.route('/api/ai/meetings/<int:meeting_id>/restore-minute', methods=['POST'])
@jwt_required()
def restore_deleted_meeting_minute_route(meeting_id):
    """Restore a deleted meeting + segments snapshot (super admin only)."""
    try:
        actor = _get_actor_context()
        if actor['role'] != 'super_admin':
            return jsonify({'error': 'Super admin access required'}), 403

        _ensure_deleted_meeting_snapshots_table()

        existing_meeting = execute_safe_query('SELECT meeting_id FROM Meetings WHERE meeting_id = ?', (meeting_id,))
        if existing_meeting:
            return jsonify({'error': 'Meeting is already active'}), 400

        snapshot_rows = execute_safe_query(
            '''
            SELECT original_meeting_id, meeting_date, source_filename, segments_json
            FROM DeletedMeetingSnapshots
            WHERE original_meeting_id = ?
            LIMIT 1
            ''',
            (meeting_id,)
        )
        if not snapshot_rows:
            return jsonify({'error': 'Deleted meeting snapshot not found'}), 404

        snapshot = snapshot_rows[0]
        segments_payload = []
        try:
            segments_payload = json.loads(snapshot.get('segments_json') or '[]')
        except Exception:
            segments_payload = []

        execute_safe_query(
            'INSERT INTO Meetings (meeting_id, meeting_date, source_filename) VALUES (?, ?, ?)',
            (snapshot.get('original_meeting_id'), snapshot.get('meeting_date'), snapshot.get('source_filename')),
            fetch=False
        )

        restored_segments = 0
        for segment in segments_payload:
            execute_safe_query(
                'INSERT INTO Segments (meeting_id, original_text) VALUES (?, ?)',
                (snapshot.get('original_meeting_id'), (segment or {}).get('original_text') or ''),
                fetch=False
            )
            restored_segments += 1

        execute_safe_query(
            'DELETE FROM DeletedMeetingSnapshots WHERE original_meeting_id = ?',
            (meeting_id,),
            fetch=False
        )

        _log_transcript_action(
            'restore_deleted_meeting_minute',
            {
                'meeting_id': meeting_id,
                'restored_segments': restored_segments,
                'actor_role': actor['role'],
            }
        )

        return jsonify(
            {
                'message': 'Meeting minute restored successfully',
                'meeting_id': meeting_id,
                'restored_segments': restored_segments,
            }
        ), 200
    except Exception as e:
        logging.error(f"Restore deleted meeting minute error: {e}")
        return jsonify({'error': 'Failed to restore deleted meeting minute'}), 500


@ai_bp.route('/api/ai/analyze-speech', methods=['POST'])
@jwt_required()
@validate_json({'text': str})
def analyze_speech_route():
    """Analyze live speech transcript and return fast sentiment results."""
    try:
        data = request.get_json() or {}
        text = data.get('text', '').strip()
        if not text:
            return jsonify({'error': 'Text required'}), 400

        identity = get_jwt_identity()
        logging.info(f"Speech analysis request: user={identity}, text_len={len(text)}")
        if isinstance(identity, (str, int)):
            user_id = int(identity)
        elif isinstance(identity, dict) and identity.get('user_id') is not None:
            user_id = int(identity.get('user_id'))
        else:
            raise ValueError(f'Invalid JWT identity: {identity}')

        from .ai.speech import analyze_speech_text
        analysis = analyze_speech_text(text, user_id)
        logging.info(f"Speech analysis success for user {user_id}")
        return jsonify(analysis), 200

    except Exception as e:
        error_text = str(e)
        stack = traceback.format_exc()
        logging.error(f"Speech analysis error (user={identity if 'identity' in locals() else 'unknown'}): {error_text}\n{stack}")

        # Return details for easier debugging (remove in production if too verbose)
        return jsonify({
            'error': 'Speech analysis failed',
            'details': error_text,
        }), 500

@ai_bp.route('/api/ai/action-items', methods=['POST'])
@jwt_required()
@validate_json({'meeting_id': int})
def extract_action_items_route():
    """Extract action items from meeting segments."""
    try:
        from .ai.actions import extract_action_items
        
        data = request.get_json()
        meeting_id = data.get('meeting_id')

        actions = extract_action_items(meeting_id)
        return jsonify({'action_items': actions}), 200
    except Exception as e:
        logging.error(f"Action items extraction error: {e}")
        return jsonify({'error': 'Action items extraction failed'}), 500

@ai_bp.route('/api/ai/keywords', methods=['POST'])
@jwt_required()
@validate_json({'meeting_id': int})
def extract_keywords_route():
    """Extract keywords from meeting segments."""
    try:
        from .ai.keywords import extract_keywords
        
        data = request.get_json()
        meeting_id = data.get('meeting_id')

        keywords = extract_keywords(meeting_id)
        return jsonify({'keywords': keywords}), 200
    except Exception as e:
        logging.error(f"Keywords extraction error: {e}")
        return jsonify({'error': 'Keywords extraction failed'}), 500

@ai_bp.route('/api/ai/ner', methods=['GET'])
@jwt_required()
def get_ner():
    """Extract named entities from meeting segments."""
    try:
        meeting_id = request.args.get('meeting_id')
        from .ai.ner import get_entities

        entities = get_entities(meeting_id)
        return jsonify(entities), 200
    except Exception as e:
        logging.error(f"NER extraction error: {e}")
        return jsonify({'error': 'NER extraction failed'}), 500

@ai_bp.route('/api/ai/simplify', methods=['POST'])
@jwt_required()
def simplify_text():
    """Simplify complex text using Gemini AI.
    
    Request body:
    {
        "text": "Text to simplify",
        "max_length": 150,  # optional
        "simplification_level": "medium"  # optional: 'basic', 'medium', or 'advanced'
    }
    """
    try:
        data = request.get_json() or {}
        text = (data.get('text') or '').strip()
        max_length = int(data.get('max_length', 150) or 150)
        simplification_level = (data.get('simplification_level') or 'medium').strip().lower()

        if not text:
            return jsonify({'error': 'Text required'}), 400

        if max_length < 50:
            max_length = 50
        if max_length > 512:
            max_length = 512
        
        if simplification_level not in ['basic', 'medium', 'advanced']:
            simplification_level = 'medium'

        from .ai.simplifier import simplify_text as simplify_text_impl
        result = simplify_text_impl(text, max_length=max_length, simplification_level=simplification_level)

        return jsonify(result), 200
    except Exception as e:
        logging.error(f"Simplify error: {e}")
        return jsonify({'error': 'Text simplification failed'}), 500



@ai_bp.route('/api/ai/export/pdf', methods=['POST'])
@jwt_required()
def export_pdf_route():
    """Generate a PDF with embedded chart images and text report.

    Accepts multipart/form-data or JSON:
    - multipart: title (str), text (str), images[] (file array with PNG images)
    - JSON (fallback): { title: string, text: string }
    
    Returns: PDF file as attachment
    """
    logging.info(f"PDF export route called: method={request.method}, has_files={bool(request.files)}, has_form={bool(request.form)}")
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, PageBreak
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from io import BytesIO
        from PIL import Image as PILImage

        title = 'export'
        content = ''
        images = []

        # Try to extract from multipart/form-data (has image files)
        if request.files or request.form:
            logging.info(f"Processing multipart: form_keys={list(request.form.keys())}, file_keys={list(request.files.keys())}")
            title = request.form.get('title', 'export')
            content = request.form.get('text', '')
            # Collect all uploaded images - getlist handles multiple files with same name
            image_files = request.files.getlist('images')
            logging.info(f"PDF export: received {len(image_files)} images")
            for i, file in enumerate(image_files):
                if file and file.filename:
                    try:
                        img_data = file.read()
                        images.append({'filename': file.filename, 'data': img_data})
                        logging.info(f"  [{i+1}] Loaded image: {file.filename} ({len(img_data)} bytes)")
                    except Exception as img_err:
                        logging.warning(f"Failed to load image {file.filename}: {img_err}")
        else:
            # Fallback to JSON
            logging.info("Processing as JSON (no multipart data)")
            data = request.get_json() or {}
            title = str(data.get('title') or 'export')
            content = str(data.get('text') or '')

        logging.info(f"PDF export starting: title={title}, content_len={len(content)}, images={len(images)}")

        # Build PDF with embedded images
        buf = BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor='#1e293b',
            spaceAfter=12,
            alignment=TA_CENTER,
        )
        body_style = ParagraphStyle(
            'CustomBody',
            parent=styles['Normal'],
            fontSize=10,
            textColor='#1e293b',
            spaceAfter=6,
            alignment=TA_LEFT,
        )

        story = []
        # Title
        story.append(Paragraph(title, title_style))
        story.append(Spacer(1, 0.3 * inch))

        # Text content
        for line in content.split('\n'):
            if line.strip():
                story.append(Paragraph(line[:500], body_style))
            else:
                story.append(Spacer(1, 0.1 * inch))

        # Embed chart images
        if images:
            story.append(PageBreak())
            story.append(Paragraph('Charts & Visualizations', title_style))
            story.append(Spacer(1, 0.2 * inch))

            for img_info in images:
                try:
                    img_bytes = BytesIO(img_info['data'])
                    pil_img = PILImage.open(img_bytes)
                    # Scale to fit page width (6.5 inches for letter with margins)
                    max_width = 6.5 * inch
                    max_height = 3 * inch
                    pil_img.thumbnail((max_width / 72, max_height / 72), PILImage.Resampling.LANCZOS)
                    
                    # Save resized image to bytes
                    resized_bytes = BytesIO()
                    pil_img.save(resized_bytes, format='PNG')
                    resized_bytes.seek(0)
                    
                    # Add to PDF
                    rl_img = RLImage(resized_bytes, width=4*inch, height=2*inch)
                    story.append(rl_img)
                    story.append(Spacer(1, 0.3 * inch))
                    logging.info(f"âœ“ Embedded image: {img_info['filename']}")
                except Exception as img_embed_err:
                    logging.warning(f"Failed to embed image {img_info['filename']}: {img_embed_err}", exc_info=True)
                    story.append(Paragraph(f"<i>[Image: {img_info['filename']} - failed to embed: {str(img_embed_err)[:50]}]</i>", body_style))
                    story.append(Spacer(1, 0.2 * inch))

        # Build PDF
        logging.info(f"Building PDF with {len(story)} story elements...")
        doc.build(story)
        buf.seek(0)
        pdf_bytes = buf.read()
        logging.info(f"âœ“ PDF built successfully: {len(pdf_bytes)} bytes")

        headers = {
            'Content-Disposition': f'attachment; filename="{title}.pdf"'
        }
        return Response(pdf_bytes, mimetype='application/pdf', headers=headers)
    except Exception as e:
        logging.error(f"PDF export error: {e}", exc_info=True)
        error_msg = str(e)[:200]
        return jsonify({'error': 'PDF export failed', 'details': error_msg}), 500


@ai_bp.route('/api/ai/simplify/meeting/<int:meeting_id>', methods=['POST'])
@jwt_required()
def simplify_meeting_route(meeting_id):
    """Simplify all segments for a meeting and return simplified rows."""
    try:
        from .ai.simplifier import simplify_meeting_minutes, get_simplified_segments

        simplified_count = simplify_meeting_minutes(meeting_id)
        segments = get_simplified_segments(meeting_id)

        return jsonify({
            'meeting_id': meeting_id,
            'simplified_count': simplified_count,
            'segments': segments,
        }), 200
    except Exception as e:
        logging.error(f"Meeting simplification error: {e}")
        return jsonify({'error': 'Meeting text simplification failed'}), 500

@ai_bp.route('/api/ai/classify-document', methods=['POST'])
@jwt_required()
def classify_document():
    """Classify document segments."""
    try:
        data = request.get_json()
        meeting_id = data.get('meeting_id')
        from .ai.classifier import classify_document as classify_document_segments, get_classifications

        classify_document_segments(meeting_id)
        classifications = get_classifications(meeting_id)
        return jsonify(classifications), 200
    except Exception as e:
        logging.error(f"Document classification error: {e}")
        return jsonify({'error': 'Document classification failed'}), 500

@ai_bp.route('/api/ai/theme-trends', methods=['GET'])
@jwt_required()
def get_theme_trends():
    """Get trend analysis data by year."""
    try:
        from .ai.trends import analyze_theme_trends, analyze_theme_frequency

        year = request.args.get('year', type=int)
        theme = request.args.get('theme', type=str)
        force_refresh = request.args.get('force_refresh', default='false')
        force_refresh = str(force_refresh).lower() in ('1', 'true', 'yes')
        try:
            trends_data = analyze_theme_trends(year=year, theme=theme, force_refresh=force_refresh)
        except Exception as e:
            logging.warning(f"analyze_theme_trends failed: {e}")
            trends_data = {}

# Add a 'themes' array for frontend charts - pass theme filter for targeted analysis
        try:
            top_themes = analyze_theme_frequency(year=year, theme=theme, top_n=10)
            themes = []
            total_theme_mentions = 0

            def _resolve_theme_name(record, index):
                candidate = str(record.get('name') or '').strip()
                if candidate.lower() in {'theme', 'themes', 'general', 'general topic', 'topic', 'unknown', 'unknown theme'}:
                    candidate = ''
                if not candidate and record.get('keywords') and isinstance(record['keywords'], list):
                    candidate = ' '.join(str(k).strip() for k in record['keywords'][:4] if str(k).strip())
                if not candidate:
                    candidate = str(record.get('theme_id') or f'Cluster {index + 1}')
                return candidate

            for index, t in enumerate(top_themes):
                # Handle various field name formats from analyze_theme_frequency.
                # Prefer the canonical name, then keywords, then a stable synthetic label.
                name = _resolve_theme_name(t, index)
                
                # Always include theme_id for stable selection
                tid = t.get('theme_id') or f"theme-{top_themes.index(t)}"
                
                # Map total_mentions (from trends.py) to frequency for frontend compatibility
                frequency = t.get('total_mentions') or t.get('frequency') or t.get('count') or 0
                
                # Map growth_rate to confidence (or use explicit confidence if available)
                confidence = t.get('confidence') if t.get('confidence') is not None else 0
                if confidence == 0 and t.get('growth_rate'):
                    # Convert growth rate to a 0-1 scale for confidence display
                    growth = float(t.get('growth_rate', 0))
                    if growth > 0:
                        confidence = min(1.0, growth / 100.0)
                    else:
                        confidence = max(0.1, 1.0 + (growth / 100.0))
                
                themes.append({
                    'theme_id': tid,
                    'name': name,
                    'frequency': int(frequency) if frequency else 0,
                    'confidence': float(confidence) if confidence else 0.5
                })
                total_theme_mentions += int(frequency) if frequency else 0
            trends_data['themes'] = themes
            trends_data.setdefault('statistics', {})['theme_mentions_total'] = total_theme_mentions
        except Exception as theme_patch_error:
            logging.warning(f"Could not add themes from analyze_theme_frequency: {theme_patch_error}")
            # Fallback: use the themes API directly
            try:
                from .ai.themes import get_all_themes_from_meetings
                all_themes = get_all_themes_from_meetings()
                if all_themes:
                    themes = []
                    total_theme_mentions = 0
                    for index, t in enumerate(all_themes[:10]):
                        name = _resolve_theme_name(t, index)
                        tid = t.get('theme_id') or f"theme-{all_themes.index(t)}"
                        frequency = t.get('frequency') or t.get('meeting_count') or 0
                        confidence = t.get('confidence', 0.5)
                        themes.append({
                            'theme_id': tid,
                            'name': name,
                            'frequency': int(frequency),
                            'confidence': float(confidence) if confidence else 0.5
                        })
                        total_theme_mentions += int(frequency)
                    trends_data['themes'] = themes
                    trends_data.setdefault('statistics', {})['theme_mentions_total'] = total_theme_mentions
                else:
                    trends_data['themes'] = []
            except Exception as fallback_error:
                logging.warning(f"Fallback themes also failed: {fallback_error}")
                trends_data['themes'] = []

        # Always return a valid structure
        if 'themes' not in trends_data:
            trends_data['themes'] = []
        return jsonify(trends_data), 200
    except Exception as e:
        logging.error(f"Theme trends error: {e}")
        return jsonify({'themes': [], 'error': 'Theme trends retrieval failed'}), 200


@ai_bp.route('/api/ai/theme-frequency', methods=['GET'])
@jwt_required()
def get_theme_frequency():
    """Get top themes with monthly distribution and growth rates."""
    try:
        from .ai.trends import analyze_theme_frequency

        year = request.args.get('year', type=int)
        theme = request.args.get('theme', type=str)
        top_n = request.args.get('top_n', default=8, type=int)
        frequency_data = analyze_theme_frequency(year=year, theme=theme, top_n=top_n)
        return jsonify(frequency_data), 200
    except Exception as e:
        logging.error(f"Theme frequency error: {e}")
        return jsonify({'error': 'Theme frequency retrieval failed'}), 500


@ai_bp.route('/api/ai/emerging-themes', methods=['GET'])
@jwt_required()
def get_emerging_themes_route():
    """Get rapidly growing themes."""
    try:
        from .ai.trends import get_emerging_themes

        year = request.args.get('year', type=int)
        sensitivity = request.args.get('sensitivity', default=0.20, type=float)
        emerging = get_emerging_themes(year=year, sensitivity=sensitivity)
        return jsonify(emerging), 200
    except Exception as e:
        logging.error(f"Emerging themes error: {e}")
        return jsonify({'error': 'Emerging themes retrieval failed'}), 500


@ai_bp.route('/api/ai/recurring-issues', methods=['GET'])
@jwt_required()
def get_recurring_issues_route():
    """Get recurring issues across meetings."""
    try:
        from .ai.trends import get_recurring_issues

        year = request.args.get('year', type=int)
        min_frequency = request.args.get('min_frequency', default=3, type=int)
        recurring = get_recurring_issues(year=year, min_frequency=min_frequency)
        return jsonify(recurring), 200
    except Exception as e:
        logging.error(f"Recurring issues error: {e}")
        return jsonify({'error': 'Recurring issues retrieval failed'}), 500


@ai_bp.route('/api/ai/sentiment-trends', methods=['GET'])
@jwt_required()
def get_sentiment_trends_route():
    """Get monthly sentiment trends."""
    try:
        from .ai.trends import analyze_sentiment_trends

        year = request.args.get('year', type=int)
        force_refresh = request.args.get('force_refresh', default='false')
        force_refresh = str(force_refresh).lower() in ('1', 'true', 'yes')
        sentiment_data = analyze_sentiment_trends(year=year, force_refresh=force_refresh)
        return jsonify(sentiment_data), 200
    except Exception as e:
        logging.error(f"Sentiment trends error: {e}")
        return jsonify({'error': 'Sentiment trends retrieval failed'}), 500


@ai_bp.route('/api/ai/theme-anomalies', methods=['GET'])
@jwt_required()
def get_theme_anomalies_route():
    """Get statistical anomalies in theme activity and optionally alert admins by email."""
    try:
        from .ai.trends import detect_theme_anomalies

        actor = _get_actor_context()
        year = request.args.get('year', type=int)
        sensitivity = request.args.get('sensitivity', default=2.0, type=float)
        notify_raw = str(request.args.get('notify', 'true')).lower()
        notify = notify_raw in ('1', 'true', 'yes')

        anomalies = detect_theme_anomalies(year=year, sensitivity=sensitivity)
        critical = [a for a in anomalies if str(a.get('severity', '')).lower() == 'critical']

        alert_summary = None
        if notify and critical:
            if actor.get('role') in {'admin', 'super_admin'}:
                alert_summary = _send_critical_anomaly_alerts(year or datetime.now().year, critical, actor)
            else:
                alert_summary = {
                    'sent': 0,
                    'failed': 0,
                    'skipped': len(critical),
                    'reason': 'insufficient_privileges_for_email_alerts'
                }

        return jsonify({
            'year': year,
            'sensitivity': sensitivity,
            'total': len(anomalies),
            'critical_count': len(critical),
            'anomalies': anomalies,
            'alert_summary': alert_summary,
        }), 200
    except Exception as e:
        logging.error(f"Theme anomalies error: {e}")
        return jsonify({'error': 'Theme anomalies retrieval failed', 'anomalies': []}), 500

@ai_bp.route('/api/ai/themes', methods=['GET'])
@jwt_required()
def get_dynamic_themes():
    """Get dynamically extracted themes from all meetings."""
    try:
        from .ai.themes import get_all_themes_from_meetings
        try:
            themes = get_all_themes_from_meetings()
        except Exception as e:
            logging.warning(f"get_all_themes_from_meetings failed: {e}")
            themes = []
        return jsonify({'themes': themes}), 200
    except Exception as e:
        logging.error(f"Dynamic themes error: {e}")
        return jsonify({'themes': [], 'error': 'Failed to extract themes'}), 200

@ai_bp.route('/api/ai/themes/sentiment', methods=['GET'])
@jwt_required()
def get_theme_sentiment():
    """Get sentiment distribution for themes."""
    try:
        from .ai.themes import get_theme_sentiment_distribution
        
        theme = request.args.get('theme')
        year = request.args.get('year', type=int)
        
        sentiment_data = get_theme_sentiment_distribution(theme, year)
        
        return jsonify(sentiment_data), 200
    except Exception as e:
        logging.error(f"Theme sentiment error: {e}")
        return jsonify({'error': 'Failed to get sentiment distribution'}), 500

@ai_bp.route('/api/ai/extract-topics', methods=['POST'])
@jwt_required()
def extract_topics():
    """Extract topics from meeting segments using advanced topic modeling."""
    try:
        data = request.get_json()
        meeting_id = data.get('meeting_id')

        if not meeting_id:
            return jsonify({'error': 'Meeting ID required'}), 400

        # Get meeting segments
        segments = execute_safe_query(
            'SELECT segment_id, original_text FROM Segments WHERE meeting_id = ?',
            (meeting_id,)
        )

        if not segments:
            return jsonify({'error': 'No segments found for meeting'}), 404

        # Extract topics using advanced topic modeling
        topics = extract_topics_from_segments(segments)

        # Store topics in database
        for topic in topics:
            execute_safe_query(
                'INSERT INTO Topics (meeting_id, topic_name, confidence_score, keywords) VALUES (?, ?, ?, ?)',
                (meeting_id, topic['name'], topic['confidence'], ','.join(topic['keywords'])),
                fetch=False
            )

        return jsonify({'topics': topics}), 200

    except Exception as e:
        logging.error(f"Topic extraction error: {e}")
        return jsonify({'error': 'Topic extraction failed'}), 500


@ai_bp.route('/api/ai/map-topic-to-theme', methods=['POST'])
@jwt_required()
def map_topic_to_theme():
    """Map a dashboard topic (name/keywords) to the best matching dynamic theme_id.

    Expects JSON: { 'topic': 'Topic Name', 'keywords': ['kw1','kw2'], 'year': 2026 }
    Returns: { topic, mapped_theme_id, mapped_name, score }
    """
    try:
        payload = request.get_json() or {}
        topic = (payload.get('topic') or payload.get('name') or '').strip()
        keywords = payload.get('keywords') or []
        year = payload.get('year')

        if not topic and not keywords:
            return jsonify({'error': 'Provide topic name or keywords'}), 400

        # Collect candidate themes from frequency and dynamic extraction
        try:
            from .ai.trends import analyze_theme_frequency
            candidates = analyze_theme_frequency(year=year, top_n=50) or []
        except Exception:
            candidates = []

        try:
            from .ai.themes import get_all_themes_from_meetings
            extra = get_all_themes_from_meetings() or []
        except Exception:
            extra = []

        # Merge candidates, prefer those with theme_id
        merged = { (c.get('theme_id') or c.get('name')): c for c in (candidates + extra) }
        import difflib

        target = (topic or ' ').lower()
        best = None
        best_score = 0.0

        for key, cand in merged.items():
            name = str(cand.get('name') or '')
            cand_keywords = [str(k).lower() for k in (cand.get('keywords') or []) if k]
            score = 0.0
            # exact name match
            if target and name and target == name.lower():
                score += 2.0
            # substring match
            if target and name and target in name.lower():
                score += 1.0
            # keywords overlap
            if keywords:
                overlap = 0
                for kw in keywords:
                    if any(kw.lower() in ck for ck in cand_keywords):
                        overlap += 1
                if overlap:
                    score += 1.0 + (overlap * 0.2)
            # fuzzy similarity on names
            if target and name:
                ratio = difflib.SequenceMatcher(None, target, name.lower()).ratio()
                score += ratio

            if score > best_score:
                best_score = score
                best = cand

        if not best:
            return jsonify({'topic': topic, 'mapped_theme_id': None, 'mapped_name': None, 'score': 0.0}), 200

        mapped_id = best.get('theme_id') or best.get('id') or f"theme-auto-{abs(hash(best.get('name') or ''))%100000}"
        return jsonify({'topic': topic, 'mapped_theme_id': mapped_id, 'mapped_name': best.get('name'), 'score': float(best_score)}), 200
    except Exception as e:
        logging.error(f"map-topic-to-theme error: {e}")
        return jsonify({'error': 'Mapping failed'}), 500

@ai_bp.route('/api/ai/run-batch-analysis', methods=['POST'])
@jwt_required()
def run_batch_analysis():
    """Run all AI analyses across all meetings synchronously (legacy mode)."""
    try:
        payload = request.get_json(silent=True) or {}
        result = _run_batch_analysis_with_cache_invalidation(payload)
        return jsonify(result), 200
    except Exception as e:
        logging.error(f"Batch analysis error: {e}")
        return jsonify({'error': 'Batch analysis failed'}), 500


@ai_bp.route('/api/ai/run-batch-analysis/start', methods=['POST'])
@jwt_required()
def start_batch_analysis():
    """Start batch analysis in background and return a job id for progress polling."""
    payload = request.get_json(silent=True) or {}
    # Enforce server-side role check: only editors/admins/super_admin may start batch analysis
    try:
        actor = _get_actor_context()
        role = (actor.get('role') or '').lower()
        if role not in ['editor', 'admin', 'super_admin']:
            logging.warning(f"Unauthorized batch analysis start attempt by role='{role}' user_id={actor.get('user_id')}")
            return jsonify({'error': 'insufficient_permissions', 'message': 'Only editors and administrators may start batch analysis.'}), 403
    except Exception:
        logging.exception('Failed to determine actor role for batch analysis start')
        return jsonify({'error': 'authentication_error', 'message': 'Unable to verify permissions.'}), 401
    job_id = str(uuid.uuid4())
    total_candidates = _count_meetings_for_batch(payload)

    _set_job_state(job_id, {
        'job_id': job_id,
        'status': 'queued',
        'message': 'Batch analysis queued',
        'current_step': 'queued',
        'processed_meetings': 0,
        'total_meetings': total_candidates,
        'totals': {
            'summaries': 0,
            'sentiments': 0,
            'action_items': 0,
            'keywords': 0,
            'topics': 0,
            'failed_meetings': 0,
        },
        'loader_errors': [],
        'details': [],
        'started_at': _utc_now_iso(),
        'finished_at': None,
        'error': None,
        'backend': 'thread',
    })

    queue = _get_rq_queue()
    if queue and _has_active_rq_worker(queue):
        _set_job_state(job_id, {'backend': 'rq'})
        queue.enqueue(
            _execute_batch_analysis_job,
            payload,
            job_id,
            job_id=job_id,
            result_ttl=60 * 60 * 24,
            failure_ttl=60 * 60 * 24,
        )
    else:
        if queue:
            logging.warning('RQ queue is available but no active batch-analysis worker was detected; using thread fallback.')
        thread = threading.Thread(target=_execute_batch_analysis_job, args=(payload, job_id), daemon=True)
        thread.start()

    return jsonify({
        'success': True,
        'job_id': job_id,
        'status': 'queued',
        'backend': BATCH_ANALYSIS_JOBS.get(job_id, {}).get('backend', 'thread'),
    }), 202


@ai_bp.route('/api/ai/run-batch-analysis/status/<job_id>', methods=['GET'])
@jwt_required()
def get_batch_analysis_status(job_id):
    """Get progress/status for a previously started batch analysis job."""
    with BATCH_ANALYSIS_LOCK:
        job = BATCH_ANALYSIS_JOBS.get(job_id)

    if not job:
        job = _hydrate_status_from_rq(job_id)

    if not job:
        return jsonify({'error': 'Job not found'}), 404

    return jsonify(job), 200


@ai_bp.route('/api/ai/run-batch-analysis/cancel/<job_id>', methods=['POST'])
@jwt_required()
def cancel_batch_analysis(job_id):
    """Request cancellation for a running/queued batch analysis job."""
    with BATCH_ANALYSIS_LOCK:
        local_job = BATCH_ANALYSIS_JOBS.get(job_id)

    hydrated = None if local_job else _hydrate_status_from_rq(job_id)
    job = local_job or hydrated
    if not job:
        return jsonify({'error': 'Job not found'}), 404

    current_status = str(job.get('status') or '').lower()
    if current_status in {'completed', 'failed', 'canceled'}:
        return jsonify({'job_id': job_id, 'status': current_status, 'message': 'Job already finalized'}), 200

    _set_job_state(job_id, {
        'cancel_requested': True,
        'status': 'canceling',
        'message': 'Cancel requested. Stopping batch analysis...',
        'current_step': 'canceling',
    })

    queue = _get_rq_queue()
    if queue and Job is not None:
        try:
            rq_job = Job.fetch(job_id, connection=queue.connection)
            meta = dict(rq_job.meta or {})
            meta.update({
                'cancel_requested': True,
                'status': 'canceling',
                'message': 'Cancel requested. Stopping batch analysis...',
                'current_step': 'canceling',
            })
            rq_job.meta = meta
            rq_job.save_meta()
        except Exception:
            pass

    return jsonify({'job_id': job_id, 'status': 'canceling', 'message': 'Cancellation requested'}), 202


def _execute_batch_analysis(payload, job_id=None):
    """Core batch analysis implementation shared by sync and async endpoints."""
    try:
        reset_existing = bool(payload.get('reset_existing', True))
        requested_ids = payload.get('meeting_ids') if isinstance(payload.get('meeting_ids'), list) else None

        include_summaries = bool(payload.get('include_summaries', True))
        include_sentiments = bool(payload.get('include_sentiments', True))
        include_action_items = bool(payload.get('include_action_items', True))
        include_keywords = bool(payload.get('include_keywords', True))
        include_topics = bool(payload.get('include_topics', True))
        include_themes = bool(payload.get('include_themes', True))

        if not any([include_summaries, include_sentiments, include_action_items, include_keywords, include_topics, include_themes]):
            return {
                'success': False,
                'message': 'No analysis targets selected.',
                'processed_meetings': 0,
                'total_meetings': 0,
                'totals': {
                    'summaries': 0,
                    'sentiments': 0,
                    'action_items': 0,
                    'keywords': 0,
                    'topics': 0,
                    'failed_meetings': 0,
                },
                'details': [],
                'loader_errors': [],
                'reset_existing': reset_existing,
            }

        summarize_segments = None
        analyze_sentiment = None
        extract_action_items = None
        extract_keywords = None
        loader_errors = []

        if include_summaries:
            try:
                from .ai.summarizer import summarize_segments as _summarize_segments
                summarize_segments = _summarize_segments
            except Exception as import_error:
                loader_errors.append(f"summaries unavailable: {import_error}")
                logging.warning(f"Batch loader: summarizer unavailable: {import_error}")

        if include_sentiments:
            try:
                from .ai.sentiment import analyze_sentiment as _analyze_sentiment
                analyze_sentiment = _analyze_sentiment
            except Exception as import_error:
                loader_errors.append(f"sentiment unavailable: {import_error}")
                logging.warning(f"Batch loader: sentiment unavailable: {import_error}")

        if include_action_items:
            try:
                from .ai.actions import extract_action_items as _extract_action_items
                extract_action_items = _extract_action_items
            except Exception as import_error:
                loader_errors.append(f"action-items unavailable: {import_error}")
                logging.warning(f"Batch loader: action-items unavailable: {import_error}")

        if include_keywords:
            try:
                from .ai.keywords import extract_keywords as _extract_keywords
                extract_keywords = _extract_keywords
            except Exception as import_error:
                loader_errors.append(f"keywords unavailable: {import_error}")
                logging.warning(f"Batch loader: keywords unavailable: {import_error}")

        if requested_ids:
            placeholders = ','.join(['?'] * len(requested_ids))
            meetings = execute_safe_query(
                f'''SELECT DISTINCT meeting_id FROM Meetings
                    WHERE meeting_id IN ({placeholders})
                    ORDER BY meeting_id''',
                tuple(requested_ids)
            )
        else:
            meetings = execute_safe_query(
                '''SELECT DISTINCT meeting_id
                   FROM Meetings
                   ORDER BY meeting_id'''
            )

        if not meetings:
            return {
                'success': True,
                'processed_meetings': 0,
                'message': 'No uploaded meetings found for batch analysis.'
            }

        # Ensure Topics table exists in active DB before topic insertion/deletion.
        execute_safe_query(
            '''CREATE TABLE IF NOT EXISTS Topics (
                   topic_id INTEGER PRIMARY KEY,
                   meeting_id INTEGER,
                   topic_name TEXT,
                   confidence_score REAL,
                   keywords TEXT,
                   created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
               )''',
            fetch=False
        )

        meeting_ids = [int(row['meeting_id']) for row in meetings if row.get('meeting_id') is not None]

        if job_id:
            _set_job_state(job_id, {
                'total_meetings': len(meeting_ids),
                'processed_meetings': 0,
                'current_step': 'preparing-data',
                'message': f'Preparing batch for {len(meeting_ids)} meetings'
            })

        if reset_existing:
            if include_summaries:
                execute_safe_query('DELETE FROM Summaries', fetch=False)
            if include_sentiments:
                execute_safe_query('DELETE FROM Sentiments', fetch=False)
            if include_action_items:
                execute_safe_query('DELETE FROM ActionItems', fetch=False)
            if include_keywords:
                execute_safe_query('DELETE FROM Keywords', fetch=False)
            if include_topics:
                execute_safe_query('DELETE FROM Topics', fetch=False)
            if include_themes or include_topics:
                # Purge both themes and their mappings to segments
                execute_safe_query('DELETE FROM Analysis', fetch=False)
                execute_safe_query('DELETE FROM Themes', fetch=False)
                # Clear filesystem cache to force fresh extraction
                try:
                    from .ai.themes import clear_theme_cache
                    clear_theme_cache()
                except ImportError:
                    pass

        totals = {
            'summaries': 0,
            'sentiments': 0,
            'action_items': 0,
            'keywords': 0,
            'topics': 0,
            'failed_meetings': 0,
        }
        details = []

        if job_id and _is_batch_job_cancel_requested(job_id):
            return {
                'success': False,
                'canceled': True,
                'message': 'Batch analysis canceled by user.',
                'processed_meetings': 0,
                'total_meetings': len(meeting_ids),
                'totals': totals,
                'details': details,
                'loader_errors': loader_errors,
                'reset_existing': reset_existing,
            }

        for index, meeting_id in enumerate(meeting_ids, start=1):
            if job_id and _is_batch_job_cancel_requested(job_id):
                return {
                    'success': False,
                    'canceled': True,
                    'message': 'Batch analysis canceled by user.',
                    'processed_meetings': index - 1,
                    'total_meetings': len(meeting_ids),
                    'totals': totals,
                    'details': details,
                    'loader_errors': loader_errors,
                    'reset_existing': reset_existing,
                }

            if job_id:
                _set_job_state(job_id, {
                    'current_step': f'processing-meeting-{meeting_id}',
                    'message': f'Processing meeting {index}/{len(meeting_ids)} (ID: {meeting_id})',
                    'processed_meetings': index - 1,
                    'totals': totals,
                })

            meeting_result = {
                'meeting_id': meeting_id,
                'summaries': 0,
                'sentiments': 0,
                'action_items': 0,
                'keywords': 0,
                'topics': 0,
                'status': 'ok',
                'error': None,
            }

            try:
                if reset_existing:
                    if include_summaries:
                        execute_safe_query(
                            '''DELETE FROM Summaries WHERE segment_id IN
                               (SELECT segment_id FROM Segments WHERE meeting_id = ?)''',
                            (meeting_id,),
                            fetch=False,
                        )
                    if include_sentiments:
                        execute_safe_query(
                            '''DELETE FROM Sentiments WHERE segment_id IN
                               (SELECT segment_id FROM Segments WHERE meeting_id = ?)''',
                            (meeting_id,),
                            fetch=False,
                        )
                    if include_action_items:
                        execute_safe_query(
                            '''DELETE FROM ActionItems WHERE segment_id IN
                               (SELECT segment_id FROM Segments WHERE meeting_id = ?)''',
                            (meeting_id,),
                            fetch=False,
                        )
                    if include_keywords:
                        execute_safe_query(
                            '''DELETE FROM Keywords WHERE segment_id IN
                               (SELECT segment_id FROM Segments WHERE meeting_id = ?)''',
                            (meeting_id,),
                            fetch=False,
                        )
                    if include_topics:
                        execute_safe_query('DELETE FROM Topics WHERE meeting_id = ?', (meeting_id,), fetch=False)
                    if include_themes or include_topics:
                        # Purge segment-to-theme mappings for this specific meeting
                        execute_safe_query(
                            '''DELETE FROM Analysis WHERE segment_id IN 
                               (SELECT segment_id FROM Segments WHERE meeting_id = ?)''', 
                            (meeting_id,), 
                            fetch=False
                        )

                summaries = []
                sentiments = []
                actions = []
                keywords = []
                topics = []

                if include_summaries and summarize_segments:
                    try:
                        summaries = summarize_segments(meeting_id)
                    except Exception as sub_err:
                        logging.error(f"Summarization failed for meeting {meeting_id}: {sub_err}")

                if include_sentiments and analyze_sentiment:
                    try:
                        sentiments = analyze_sentiment(meeting_id)
                    except Exception as sub_err:
                        logging.error(f"Sentiment analysis failed for meeting {meeting_id}: {sub_err}")

                if include_action_items and extract_action_items:
                    try:
                        actions = extract_action_items(meeting_id)
                    except Exception as sub_err:
                        logging.error(f"Action-item extraction failed for meeting {meeting_id}: {sub_err}")

                if include_keywords and extract_keywords:
                    try:
                        keywords = extract_keywords(meeting_id)
                    except Exception as sub_err:
                        logging.error(f"Keyword extraction failed for meeting {meeting_id}: {sub_err}")

                if include_topics:
                    try:
                        segments = execute_safe_query(
                            'SELECT segment_id, original_text FROM Segments WHERE meeting_id = ?',
                            (meeting_id,)
                        )
                        topics = extract_topics_from_segments(segments) if segments else []
                        for topic in topics:
                            execute_safe_query(
                                'INSERT INTO Topics (meeting_id, topic_name, confidence_score, keywords) VALUES (?, ?, ?, ?)',
                                (meeting_id, topic['name'], topic['confidence'], ','.join(topic.get('keywords', []))),
                                fetch=False
                            )
                    except Exception as sub_err:
                        logging.error(f"Topic extraction failed for meeting {meeting_id}: {sub_err}")

                meeting_result['summaries'] = len(summaries)
                meeting_result['sentiments'] = len(sentiments)
                meeting_result['action_items'] = len(actions)
                meeting_result['keywords'] = len(keywords)
                meeting_result['topics'] = len(topics)

                totals['summaries'] += len(summaries)
                totals['sentiments'] += len(sentiments)
                totals['action_items'] += len(actions)
                totals['keywords'] += len(keywords)
                totals['topics'] += len(topics)
            except Exception as meeting_error:
                totals['failed_meetings'] += 1
                meeting_result['status'] = 'failed'
                meeting_result['error'] = str(meeting_error)
                logging.error(f"Batch analysis failed for meeting {meeting_id}: {meeting_error}")

            details.append(meeting_result)

            if job_id:
                _set_job_state(job_id, {
                    'processed_meetings': index,
                    'totals': totals,
                    'details': details,
                })

        return {
            'success': True,
            'processed_meetings': len(meeting_ids),
            'totals': totals,
            'details': details,
            'loader_errors': loader_errors,
            'reset_existing': reset_existing,
        }
    except Exception as e:
        logging.error(f"Batch analysis error: {e}")
        raise


def _run_batch_analysis_with_cache_invalidation(payload, job_id=None):
    result = _execute_batch_analysis(payload, job_id=job_id)
    if result.get('success'):
        _invalidate_analysis_caches()
    return result


def _invalidate_analysis_caches():
    try:
        from .ai.themes import clear_theme_cache
        from .ai.trends import clear_trend_caches

        clear_theme_cache()
        clear_trend_caches()
    except Exception as cache_error:
        logging.warning(f"Failed to clear analysis caches after batch run: {cache_error}")

def extract_topics_from_segments(segments):
    """
    Extract topics from meeting segments using advanced NLP techniques.
    This implements dynamic topic discovery beyond predefined categories.
    """
    try:
        from .ai.semantic_topics import clean_text, extract_semantic_topics

        texts = [clean_text(segment.get('original_text')) for segment in segments if clean_text(segment.get('original_text'))]
        semantic_topics = extract_semantic_topics(texts, max_topics=min(8, max(2, len(texts) // 5 or 2)), min_topic_size=2)
        if semantic_topics:
            normalized_topics = []
            for topic in semantic_topics:
                topic = dict(topic or {})
                normalized_name, was_normalized = _normalize_theme_name(topic.get('name'), keywords=topic.get('keywords', []))
                if was_normalized and normalized_name:
                    topic['name'] = normalized_name
                normalized_topics.append(topic)
            return normalized_topics

        return extract_keyword_based_topics(texts)

    except Exception as e:
        logging.warning(f"Advanced topic modeling not available: {e}. Using fallback method.")
        return extract_keyword_based_topics([segment.get('original_text') for segment in segments])

def extract_keyword_based_topics(texts):
    """Fallback topic extraction using keyword frequency."""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer, ENGLISH_STOP_WORDS
        import numpy as np
        import re

        def clean_text(text):
            text = str(text or '').lower()
            text = re.sub(r'[^a-z0-9\s-]', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text

        texts = [clean_text(t) for t in texts if clean_text(t)]

        if not texts:
            return []

        # Simple TF-IDF for keyword extraction
        vectorizer = TfidfVectorizer(
            max_features=50,
            stop_words=list(set(ENGLISH_STOP_WORDS).union({'meeting', 'meetings', 'minutes'})),
            ngram_range=(1, 2),
            token_pattern=r'(?u)\b[a-z][a-z0-9-]{2,}\b'
        )

        tfidf_matrix = vectorizer.fit_transform(texts)
        feature_names = vectorizer.get_feature_names_out()

        # Get top keywords across all documents
        mean_tfidf = np.mean(tfidf_matrix.toarray(), axis=0)
        top_indices = mean_tfidf.argsort()[:-6:-1]  # Top 5

        keywords = [feature_names[i] for i in top_indices if len(feature_names[i]) >= 3 and not feature_names[i].isdigit()]

        return [{
            'name': 'General Discussion',
            'confidence': 0.5,
            'keywords': keywords,
            'segment_count': len(texts)
        }]

    except Exception as e:
        logging.error(f"Keyword-based topic extraction failed: {e}")
        return []

def generate_topic_name(keywords):
    """Generate a human-readable topic name from keywords."""
    if not keywords:
        return "General"

    def _short_label(parts):
        cleaned = []
        for part in parts:
            value = str(part).strip().title()
            if value and value.lower() not in {'discussion', 'meeting', 'minutes'} and value not in cleaned:
                cleaned.append(value)
        if not cleaned:
            return "General"
        if len(cleaned) == 1 and len(parts) > 1:
            second = str(parts[1]).strip().title()
            if second and second.lower() not in {'discussion', 'meeting', 'minutes'} and second != cleaned[0]:
                cleaned.append(second)
        return ' '.join(cleaned[:6])

    # Common topic patterns
    topic_patterns = {
        'budget': ('Budget Planning', ['budget', 'funding', 'financial', 'cost', 'expense']),
        'curriculum': ('Curriculum Review', ['curriculum', 'course', 'program', 'education', 'academic']),
        'staff': ('Staff Updates', ['staff', 'personnel', 'employee', 'hiring', 'recruitment']),
        'student': ('Student Matters', ['student', 'enrollment', 'admission', 'academic']),
        'infrastructure': ('Infrastructure Update', ['facility', 'building', 'maintenance', 'construction']),
        'policy': ('Policy Review', ['policy', 'procedure', 'guideline', 'regulation']),
        'meeting': ('Meeting Updates', ['meeting', 'discussion', 'agenda', 'minutes'])
    }

    # Check for matching patterns
    for _, (label, pattern_words) in topic_patterns.items():
        if any(word in keywords[:3] for word in pattern_words):
            normalized_label, _ = _normalize_theme_name(label, keywords=keywords)
            return normalized_label

    # Fallback: Use first keyword as topic name
    fallback_label = _short_label(keywords)
    normalized_label, _ = _normalize_theme_name(fallback_label, keywords=keywords)
    return normalized_label


@ai_bp.route('/api/ai/report-item/<int:item_id>', methods=['DELETE'])
@jwt_required()
def delete_report_item_route(item_id):
    """
    Delete a single report item (summary, keyword, sentiment, action item, or topic).
    Attempts to delete from multiple tables based on item type.
    """
    try:
        actor = _get_actor_context()
        user_id = actor['user_id']
        role = actor['role']
        
        # Try to identify and delete the item from different tables
        deleted = False
        deletion_type = None
        
        # Try Summary
        existing = execute_safe_query(
            'SELECT summary_id, meeting_id FROM Summaries WHERE summary_id = ?',
            (item_id,)
        )
        if existing:
            # Delete summary
            execute_safe_query(
                'DELETE FROM Summaries WHERE summary_id = ?',
                (item_id,),
                fetch=False
            )
            deleted = True
            deletion_type = 'summary'
        
        # Try Sentiment
        if not deleted:
            existing = execute_safe_query(
                'SELECT sentiment_id, segment_id FROM Sentiments WHERE sentiment_id = ?',
                (item_id,)
            )
            if existing:
                execute_safe_query(
                    'DELETE FROM Sentiments WHERE sentiment_id = ?',
                    (item_id,),
                    fetch=False
                )
                deleted = True
                deletion_type = 'sentiment'
        
        # Try Keyword
        if not deleted:
            existing = execute_safe_query(
                'SELECT keyword_id, segment_id FROM Keywords WHERE keyword_id = ?',
                (item_id,)
            )
            if existing:
                execute_safe_query(
                    'DELETE FROM Keywords WHERE keyword_id = ?',
                    (item_id,),
                    fetch=False
                )
                deleted = True
                deletion_type = 'keyword'
        
        # Try ActionItem
        if not deleted:
            existing = execute_safe_query(
                'SELECT item_id, segment_id FROM ActionItems WHERE item_id = ?',
                (item_id,)
            )
            if existing:
                execute_safe_query(
                    'DELETE FROM ActionItems WHERE item_id = ?',
                    (item_id,),
                    fetch=False
                )
                deleted = True
                deletion_type = 'action_item'
        
        # Try Topic
        if not deleted:
            existing = execute_safe_query(
                'SELECT topic_id, meeting_id FROM Topics WHERE topic_id = ?',
                (item_id,)
            )
            if existing:
                execute_safe_query(
                    'DELETE FROM Topics WHERE topic_id = ?',
                    (item_id,),
                    fetch=False
                )
                deleted = True
                deletion_type = 'topic'
        
        if not deleted:
            return jsonify({'error': 'Report item not found'}), 404
        
        _log_transcript_action(
            f'delete_{deletion_type}',
            {'item_id': item_id, 'user_id': user_id, 'deletion_type': deletion_type}
        )
        
        return jsonify({
            'message': f'{deletion_type.replace("_", " ").title()} deleted successfully',
            'item_id': item_id,
            'deletion_type': deletion_type
        }), 200
        
    except Exception as e:
        logging.error(f"Report item delete error: {e}")
        return jsonify({'error': 'Failed to delete report item'}), 500

@ai_bp.route('/api/ai/verify-theme', methods=['POST'])
@jwt_required()
def verify_theme_route():
    try:
        actor = _get_actor_context()
        if actor['role'] not in {'admin', 'super_admin'}:
            return jsonify({'error': 'Insufficient privileges'}), 403
        data = request.get_json()
        meeting_id = data.get('meeting_id')
        theme_name = data.get('theme_name')
        
        if meeting_id:
            analysis_records = execute_safe_query(
                'SELECT a.analysis_id FROM Analysis a JOIN Themes t ON a.theme_id = t.theme_id JOIN Segments s ON a.segment_id = s.segment_id WHERE LOWER(t.theme_name) = LOWER(?) AND s.meeting_id = ?',
                (theme_name, meeting_id)
            )
        else:
            # Global verification across all meetings - use fuzzy match to be more resilient
            analysis_records = execute_safe_query(
                'SELECT a.analysis_id FROM Analysis a JOIN Themes t ON a.theme_id = t.theme_id WHERE LOWER(t.theme_name) = LOWER(?) OR LOWER(t.theme_name) LIKE ?',
                (theme_name, f'%{theme_name}%')
            )

        if not analysis_records:
            # Fallback: Try to find by keyword match if direct name match fails
            analysis_records = execute_safe_query(
                'SELECT a.analysis_id FROM Analysis a JOIN Themes t ON a.theme_id = t.theme_id WHERE t.keywords LIKE ?',
                (f'%{theme_name}%',)
            )
            
        if not analysis_records:
            logging.warning(f"Verification failed: Theme '{theme_name}' not found in database.")
            return jsonify({'error': f"Theme '{theme_name}' not found in any analysis records"}), 404
            
        analysis_ids = [r['analysis_id'] for r in analysis_records]
        # SQLite has limits on parameter count, so we process in chunks if needed
        CHUNK_SIZE = 900
        for i in range(0, len(analysis_ids), CHUNK_SIZE):
            chunk = analysis_ids[i:i + CHUNK_SIZE]
            placeholders = ','.join(['?'] * len(chunk))
            execute_safe_query(f'UPDATE Analysis SET is_verified = 1 WHERE analysis_id IN ({placeholders})', tuple(chunk), fetch=False)
            
        from .ai.themes import _get_cache_key, _set_cached_themes
        if meeting_id:
            _set_cached_themes(_get_cache_key(meeting_id=meeting_id), [], ttl=0)
        _log_transcript_action('verify_theme', {'meeting_id': meeting_id, 'theme_name': theme_name, 'global': not bool(meeting_id)})
        return jsonify({'message': 'Theme verified successfully', 'theme_name': theme_name, 'count': len(analysis_ids)}), 200
    except Exception as e:
        logging.error(f'Verify theme error: {e}')
        return jsonify({'error': 'Failed to verify theme'}), 500

@ai_bp.route('/api/ai/regenerate-themes', methods=['POST'])
@jwt_required()
def regenerate_themes_route():
    """Purge bad themes and re-trigger extraction for a specific year."""
    try:
        actor = _get_actor_context()
        if actor['role'] not in {'admin', 'super_admin'}:
            return jsonify({'error': 'Insufficient privileges'}), 403
            
        data = request.get_json() or {}
        year = data.get('year', datetime.now().year)
        
        # 1. Clear caches
        from .ai.themes import clear_theme_cache, extract_dynamic_themes, TRASH_THEME_WORDS
        clear_theme_cache(year=year)
        
        # 2. Identify all unverified themes for this year and delete them
        # This provides a truly clean slate for the regeneration
        trash_themes = execute_safe_query(
            '''SELECT DISTINCT t.theme_id FROM Themes t 
               JOIN Analysis a ON t.theme_id = a.theme_id 
               JOIN Segments s ON a.segment_id = s.segment_id 
               WHERE strftime('%Y', s.created_at) = ? AND a.is_verified = 0''',
            (str(year),)
        )
        
        if trash_themes:
            theme_ids = [t['theme_id'] for t in trash_themes]
            id_placeholders = ','.join(['?'] * len(theme_ids))
            execute_safe_query(f'DELETE FROM Analysis WHERE theme_id IN ({id_placeholders}) AND is_verified = 0', tuple(theme_ids), fetch=False)
            # Only delete the theme record if it's no longer used in Analysis
            execute_safe_query(
                f'DELETE FROM Themes WHERE theme_id IN ({id_placeholders}) AND theme_id NOT IN (SELECT theme_id FROM Analysis)', 
                tuple(theme_ids), 
                fetch=False
            )
            
        # 3. Trigger fresh extraction
        new_themes = extract_dynamic_themes(num_themes=8, force_refresh=True)
        
        return jsonify({
            'message': 'Themes regenerated and noise purged',
            'purged_count': len(trash_themes),
            'new_theme_count': len(new_themes)
        }), 200
    except Exception as e:
        logging.error(f"Regenerate themes error: {e}")
        return jsonify({'error': 'Failed to regenerate themes'}), 500
