from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import sqlite3
from werkzeug.security import generate_password_hash
from .models import get_db, execute_safe_query
from .models import log_action
from app.utils.validators import EmailValidator
import bleach
from datetime import datetime, timezone, timedelta
import logging
import secrets
import string

admin_bp = Blueprint('admin', __name__)


def generate_temporary_password(length=12):
    if length < 3:
        raise ValueError('Temporary password length must be at least 3 characters')

    alphabet = string.ascii_letters + string.digits
    while True:
        characters = [secrets.choice(alphabet) for _ in range(length)]
        characters[0] = secrets.choice(string.ascii_uppercase)
        characters[1] = secrets.choice(string.ascii_lowercase)
        characters[2] = secrets.choice(string.digits)
        secrets.SystemRandom().shuffle(characters)
        password = ''.join(characters)
        if any(char.isupper() for char in password):
            return password


def _get_actor_context():
    identity = get_jwt_identity()
    current_user_id = identity if isinstance(identity, (str, int)) else identity['user_id']
    actor = execute_safe_query(
        "SELECT user_id, username, role, is_deleted FROM Users WHERE user_id = ?",
        (current_user_id,)
    )
    return actor[0] if actor else None


def _require_admin_or_super_admin():
    actor = _get_actor_context()
    if not actor or actor.get('is_deleted'):
        return None, (jsonify({"error": "Admin access required"}), 403)
    if actor['role'] not in ['admin', 'super_admin']:
        return None, (jsonify({"error": "Admin access required"}), 403)
    return actor, None


@admin_bp.route('/api/admin/system-health', methods=['GET'])
@jwt_required()
def admin_system_health():
    try:
        actor, error_response = _require_admin_or_super_admin()
        if error_response:
            return error_response

        totals = execute_safe_query(
            """
            SELECT
                COUNT(*) AS total_users,
                SUM(CASE WHEN COALESCE(is_deleted, 0) = 1 THEN 1 ELSE 0 END) AS deleted_users
            FROM Users
            """
        )

        row = totals[0] if totals else {}
        total_users = int(row.get('total_users') or 0)
        deleted_users = int(row.get('deleted_users') or 0)
        active_users = max(total_users - deleted_users, 0)
        health_percentage = round((active_users / total_users) * 100) if total_users > 0 else 0

        return jsonify({
            'health_percentage': health_percentage,
            'total_users': total_users,
            'active_users': active_users,
            'deleted_users': deleted_users,
            'source': 'backend'
        }), 200
    except Exception as e:
        logging.error(f"System health error: {e}")
        return jsonify({'error': 'Failed to fetch system health'}), 500

@admin_bp.route('/api/admin/users', methods=['GET', 'POST', 'DELETE'])
@admin_bp.route('/api/admin/users/<int:user_id>', methods=['PUT', 'DELETE'])
@jwt_required()
def admin_users(user_id=None):
    from .app import log_archiving_activity
    try:
        actor, error_response = _require_admin_or_super_admin()
        if error_response:
            return error_response

        if request.method == 'GET':
            include_deleted = request.args.get('include_deleted', '0') == '1' and actor['role'] == 'super_admin'
            if user_id:
                users = execute_safe_query(
                    "SELECT user_id, username, email, full_name, contact_number, role, created_at, is_deleted, deleted_at, deleted_by, delete_reason FROM Users WHERE user_id = ?",
                    (user_id,)
                )
            else:
                query = "SELECT user_id, username, email, full_name, contact_number, role, created_at, is_deleted, deleted_at, deleted_by, delete_reason FROM Users"
                if not include_deleted:
                    query += " WHERE COALESCE(is_deleted, 0) = 0"
                query += " ORDER BY created_at DESC"
                users = execute_safe_query(query)
            return jsonify(users if users else [])

        elif request.method == 'POST':
            data = request.get_json()
            if not data or not data.get('username'):
                return jsonify({"error": "Username required"}), 400

            requested_username = str(data.get('username', '')).strip()
            requested_email = str(data.get('email', '')).strip()
            requested_role = str(data.get('role', 'viewer')).strip().lower()
            if requested_role not in ['viewer', 'editor', 'admin', 'super_admin']:
                return jsonify({"error": "Invalid role"}), 400
            if requested_role == 'super_admin' and actor['role'] != 'super_admin':
                return jsonify({"error": "Only super admin can create super admin accounts"}), 403

            existing_username = execute_safe_query(
                "SELECT user_id, username, email, is_deleted FROM Users WHERE username = ?",
                (requested_username,)
            )
            existing_email = execute_safe_query(
                "SELECT user_id, username, email, is_deleted FROM Users WHERE email = ?",
                (requested_email,)
            ) if requested_email else []

            active_conflict = next((row for row in [*(existing_username or []), *(existing_email or [])] if row and not row.get('is_deleted')), None)
            if active_conflict:
                return jsonify({"error": "Username or email already exists"}), 409

            deleted_conflict = next((row for row in [*(existing_username or []), *(existing_email or [])] if row and row.get('is_deleted')), None)
            if deleted_conflict:
                return jsonify({
                    "error": "A deleted user already uses this username or email. Restore that account instead of creating a duplicate.",
                    "conflict_type": "deleted_user_exists",
                    "deleted_user_id": deleted_conflict.get('user_id'),
                    "deleted_username": deleted_conflict.get('username'),
                    "deleted_email": deleted_conflict.get('email')
                }), 409
            
            temp_pw = generate_temporary_password(12)
            password_hash = generate_password_hash(temp_pw)
            
            try:
                user_id = execute_safe_query(
                    """INSERT INTO Users (username, email, full_name, contact_number, password_hash, role, must_change_password, is_deleted, created_at) 
                       VALUES (?, ?, ?, ?, ?, ?, 1, 0, CURRENT_TIMESTAMP)""",
                    (
                        data.get('username'),
                        data.get('email', ''),
                        data.get('full_name', ''),
                        data.get('contact_number', ''),
                        password_hash,
                        requested_role
                    ),
                    fetch=False
                )
                email_sent = False
                email = data.get('email', '').strip()
                if email:
                    from .services.email_service import send_welcome_email
                    email_sent = send_welcome_email(
                        email,
                        data.get('username'),
                        temp_pw,
                        recipient_user_id=user_id,
                        actor_user_id=actor['user_id'],
                        actor_username=actor['username']
                    )
                    log_action('user_creation', f"Welcome email to {email}: {'success' if email_sent else 'failed'}", actor['user_id'])

                temp_response = temp_pw if not email_sent else '[emailed - change on login]'
                return jsonify({'user_id': user_id, 'email_sent': email_sent, 'temp_password': temp_response, 'message': 'User created successfully'}), 201
            except sqlite3.IntegrityError:
                return jsonify({"error": "Username already exists"}), 400

        elif request.method == 'PUT' and user_id:
            data = request.get_json()
            if not data:
                return jsonify({"error": "No data provided"}), 400

            target_user = execute_safe_query(
                "SELECT user_id, username, role FROM Users WHERE user_id = ?",
                (user_id,)
            )
            if not target_user:
                return jsonify({"error": "User not found"}), 404
            target_user = target_user[0]

            if target_user['role'] == 'super_admin' and actor['role'] != 'super_admin':
                return jsonify({"error": "Only super admin can modify a super admin account"}), 403

            updates = []
            params = []
            
            if 'email' in data:
                updates.append("email = ?")
                params.append(bleach.clean(data['email']))
            if 'full_name' in data:
                updates.append("full_name = ?")
                params.append(bleach.clean(data['full_name']))
            if 'contact_number' in data:
                updates.append("contact_number = ?")
                params.append(bleach.clean(data['contact_number']))
            if 'role' in data:
                requested_role = str(data['role']).strip().lower()
                if requested_role not in ['viewer', 'editor', 'admin', 'super_admin']:
                    return jsonify({"error": "Invalid role"}), 400
                if requested_role == 'super_admin' and actor['role'] != 'super_admin':
                    return jsonify({"error": "Only super admin can assign super admin role"}), 403
                if target_user['role'] == 'super_admin' and requested_role != 'super_admin':
                    if actor['role'] != 'super_admin':
                        return jsonify({"error": "Only super admin can downgrade a super admin account"}), 403
                    if target_user['user_id'] == actor['user_id']:
                        return jsonify({"error": "You cannot downgrade your own super admin role"}), 400
                updates.append("role = ?")
                params.append(requested_role)

            if not updates:
                return jsonify({"error": "No valid fields to update"}), 400

            params.append(user_id)
            query = f"UPDATE Users SET {', '.join(updates)} WHERE user_id = ?"
            
            execute_safe_query(query, params, fetch=False)
            return jsonify({"message": "User updated successfully"}), 200

        elif request.method == 'DELETE':
            if not user_id:
                return jsonify({"error": "User ID required"}), 400
            
            # Check user exists
            user_check = execute_safe_query("SELECT user_id, username, role, is_deleted FROM Users WHERE user_id = ?", (user_id,))
            if not user_check:
                return jsonify({"error": "User not found"}), 404

            target = user_check[0]
            if target['role'] == 'super_admin' and actor['role'] != 'super_admin':
                return jsonify({"error": "Only super admin can delete super admin accounts"}), 403
            if target['user_id'] == actor['user_id']:
                return jsonify({"error": "You cannot delete your own account"}), 400

            reason = (request.get_json(silent=True) or {}).get('reason', 'admin soft delete')
            execute_safe_query(
                "UPDATE Users SET is_deleted = 1, deleted_at = ?, deleted_by = ?, delete_reason = ? WHERE user_id = ?",
                (datetime.now(timezone.utc).isoformat(), actor['user_id'], bleach.clean(str(reason)), user_id),
                fetch=False
            )
            log_archiving_activity(actor['user_id'], 'soft_delete_user', {'target_user_id': user_id, 'target_username': target['username'], 'reason': reason}, actor_username=actor['username'], actor_role=actor['role'])
            return jsonify({"message": f"User {target['username']} moved to trash"}), 200

        return jsonify({"error": "Method not allowed"}), 405

    except sqlite3.IntegrityError as e:
        logging.error(f"Admin IntegrityError: {e}")
        return jsonify({"error": "Database constraint violation"}), 400
    except Exception as e:
        logging.error(f"Admin error: {e}")
        return jsonify({"error": "Server error"}), 500


@admin_bp.route('/api/admin/users/<int:user_id>/restore', methods=['POST'])
@jwt_required()
def admin_restore_user(user_id):
    from .app import log_archiving_activity
    try:
        actor, error_response = _require_admin_or_super_admin()
        if error_response:
            return error_response

        if actor['role'] != 'super_admin':
            return jsonify({"error": "Super admin access required"}), 403

        user_check = execute_safe_query("SELECT user_id, username, role, is_deleted FROM Users WHERE user_id = ?", (user_id,))
        if not user_check:
            return jsonify({"error": "User not found"}), 404

        target = user_check[0]
        if not target['is_deleted']:
            return jsonify({"message": "User is already active"}), 200

        execute_safe_query(
            "UPDATE Users SET is_deleted = 0, deleted_at = NULL, deleted_by = NULL, delete_reason = NULL WHERE user_id = ?",
            (user_id,),
            fetch=False
        )
        log_archiving_activity(actor['user_id'], 'restore_user', {'target_user_id': user_id, 'target_username': target['username']}, actor_username=actor['username'], actor_role=actor['role'])
        return jsonify({"message": f"User {target['username']} restored"}), 200
    except Exception as e:
        logging.error(f"Restore user error: {e}")
        return jsonify({"error": "Restore failed"}), 500


@admin_bp.route('/api/admin/users/<int:user_id>/purge', methods=['DELETE'])
@jwt_required()
def admin_purge_user(user_id):
    from .app import log_archiving_activity
    try:
        actor, error_response = _require_admin_or_super_admin()
        if error_response:
            return error_response

        if actor['role'] != 'super_admin':
            return jsonify({"error": "Super admin access required"}), 403

        user_check = execute_safe_query("SELECT user_id, username, role, is_deleted FROM Users WHERE user_id = ?", (user_id,))
        if not user_check:
            return jsonify({"error": "User not found"}), 404

        target = user_check[0]
        if target['user_id'] == actor['user_id']:
            return jsonify({"error": "You cannot purge your own account"}), 400

        if not target.get('is_deleted'):
            return jsonify({"error": "User must be moved to trash before permanent purge"}), 400

        # Remove or detach dependent rows first to avoid FK constraint failures.
        # Must delete in correct order due to FK constraints
        execute_safe_query("DELETE FROM EventAnnouncementDeliveries WHERE user_id = ?", (user_id,), fetch=False)
        execute_safe_query("DELETE FROM EventReminderJobs WHERE event_id IN (SELECT event_id FROM EventAnnouncements WHERE created_by = ?)", (user_id,), fetch=False)
        execute_safe_query("DELETE FROM EventAnnouncements WHERE created_by = ?", (user_id,), fetch=False)
        execute_safe_query("DELETE FROM ReportSchedules WHERE user_id = ?", (user_id,), fetch=False)
        execute_safe_query("DELETE FROM NotificationSubscriptions WHERE user_id = ?", (user_id,), fetch=False)
        execute_safe_query("DELETE FROM NotificationEvents WHERE user_id = ? OR actor_user_id = ?", (user_id, user_id), fetch=False)
        execute_safe_query("DELETE FROM AuditLogs WHERE user_id = ?", (user_id,), fetch=False)
        execute_safe_query("DELETE FROM RefreshTokens WHERE user_id = ?", (user_id,), fetch=False)
        execute_safe_query("UPDATE Transcripts SET user_id = NULL WHERE user_id = ?", (user_id,), fetch=False)

        execute_safe_query("DELETE FROM Users WHERE user_id = ?", (user_id,), fetch=False)
        log_archiving_activity(actor['user_id'], 'purge_user', {'target_user_id': user_id, 'target_username': target['username']}, actor_username=actor['username'], actor_role=actor['role'])
        return jsonify({"message": f"User {target['username']} permanently deleted"}), 200
    except sqlite3.IntegrityError as e:
        logging.error(f"Purge user integrity error: {e}")
        return jsonify({"error": "Purge blocked by related records. Please contact admin support."}), 409
    except Exception as e:
        logging.error(f"Purge user error: {e}")
        return jsonify({"error": "Purge failed"}), 500

@admin_bp.route('/api/admin/archive-logs', methods=['POST'])
@jwt_required()
def admin_archive_logs():
    from .app import log_archiving_activity
    try:
        identity = get_jwt_identity()
        admin_user_id = identity if isinstance(identity, (str, int)) else identity['user_id']
        actor = _get_actor_context()
        data = request.get_json(silent=True) or {}
        log_ids = data.get('log_ids', []) if isinstance(data, dict) else []
        now_iso = datetime.now(timezone.utc).isoformat()

        # Bulk-selected archive path (frontend selection)
        if log_ids:
            placeholders = ','.join(['?' for _ in log_ids])
            count_query = (
                f"SELECT COUNT(*) as count FROM AuditLogs "
                f"WHERE log_id IN ({placeholders}) AND archived_at IS NULL "
                "AND action IN ('login', 'logout', 'failed_login')"
            )
            count_result = execute_safe_query(count_query, log_ids)
            count = int(count_result[0]['count']) if count_result else 0

            if count == 0:
                return jsonify({'message': 'No selected logs to archive', 'archived_count': 0}), 200

            update_query = (
                f"UPDATE AuditLogs SET archived_at = ? WHERE log_id IN ({placeholders}) "
                "AND archived_at IS NULL AND action IN ('login', 'logout', 'failed_login')"
            )
            execute_safe_query(update_query, [now_iso, *log_ids], fetch=False)

            log_archiving_activity(
                admin_user_id,
                'archive_logs',
                {'mode': 'selected', 'log_ids_count': len(log_ids), 'count': count},
                actor_username=actor['username'],
                actor_role=actor['role']
            )

            return jsonify({'message': f'Archived {count} selected logs', 'archived_count': count}), 200

        # Existing age-based archive path
        days = int(data.get('days', 90))
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_str = cutoff.isoformat()

        count_result = execute_safe_query(
            "SELECT COUNT(*) as count FROM AuditLogs WHERE timestamp < ? AND archived_at IS NULL AND action IN ('login', 'logout', 'failed_login')",
            (cutoff_str,)
        )
        count = int(count_result[0]['count']) if count_result else 0

        if count == 0:
            return jsonify({'message': 'No logs to archive', 'archived_count': 0}), 200

        execute_safe_query(
            "UPDATE AuditLogs SET archived_at = ? WHERE timestamp < ? AND archived_at IS NULL AND action IN ('login', 'logout', 'failed_login')",
            (now_iso, cutoff_str),
            fetch=False
        )

        log_archiving_activity(
            admin_user_id,
            'archive_logs',
            {'mode': 'days', 'days': days, 'cutoff': cutoff_str, 'count': count},
            actor_username=actor['username'],
            actor_role=actor['role']
        )

        return jsonify({'message': f'Archived {count} logs older than {days} days', 'archived_count': count}), 200
        
    except Exception as e:
        logging.error(f"Archive logs error: {e}")
        return jsonify({'error': 'Archive failed'}), 500

@admin_bp.route('/api/admin/restore-logs', methods=['POST'])
@jwt_required()
def admin_restore_logs():
    from .app import log_archiving_activity
    try:
        identity = get_jwt_identity()
        admin_user_id = identity if isinstance(identity, (str, int)) else identity['user_id']
        actor = _get_actor_context()
        data = request.get_json()
        log_ids = data.get('log_ids', [])
        
        if not log_ids:
            return jsonify({'error': 'log_ids required'}), 400
        
        placeholders = ','.join(['?' for _ in log_ids])
        query = f"UPDATE AuditLogs SET archived_at = NULL WHERE log_id IN ({placeholders}) AND archived_at IS NOT NULL"
        
        result = execute_safe_query(query, log_ids, fetch=False)
        restored_count = result  # lastrowid not for UPDATE; use separate COUNT if needed
        
        log_archiving_activity(admin_user_id, 'restore_logs', {'log_ids_count': len(log_ids), 'restored_count': restored_count}, actor_username=actor['username'], actor_role=actor['role'])
        
        return jsonify({'message': f'Restored {restored_count} logs', 'restored_count': restored_count}), 200
        
    except Exception as e:
        logging.error(f"Restore logs error: {e}")
        return jsonify({'error': 'Restore failed'}), 500


@admin_bp.route('/api/admin/purge-login-history', methods=['DELETE'])
@jwt_required()
def admin_purge_login_history():
    from .app import log_archiving_activity
    try:
        actor, error_response = _require_admin_or_super_admin()
        if error_response:
            return error_response

        if actor['role'] != 'super_admin':
            return jsonify({'error': 'Super admin access required'}), 403

        data = request.get_json(silent=True) or {}
        confirmation_phrase = str(data.get('confirmation_phrase', '')).strip()
        required_phrase = 'PURGE LOGIN HISTORY'
        if confirmation_phrase != required_phrase:
            return jsonify({'error': f'Confirmation phrase must be exactly "{required_phrase}"'}), 400

        count_result = execute_safe_query(
            "SELECT COUNT(*) as count FROM AuditLogs WHERE action IN ('login', 'logout', 'failed_login')"
        )
        purge_count = int(count_result[0]['count']) if count_result else 0

        execute_safe_query(
            "DELETE FROM AuditLogs WHERE action IN ('login', 'logout', 'failed_login')",
            fetch=False
        )

        log_archiving_activity(
            actor['user_id'],
            'purge_login_history',
            {'purged_count': purge_count},
            actor_username=actor['username'],
            actor_role=actor['role']
        )

        return jsonify({'message': f'Permanently purged {purge_count} login history records', 'purged_count': purge_count}), 200
    except Exception as e:
        logging.error(f"Purge login history error: {e}")
        return jsonify({'error': 'Purge failed'}), 500

@admin_bp.route('/api/admin/audit-trail', methods=['GET'])
@jwt_required()
def admin_audit_trail():
    try:
        identity = get_jwt_identity()
        current_user_id = identity if isinstance(identity, (str, int)) else identity['user_id']
        result = execute_safe_query("SELECT role FROM Users WHERE user_id = ?", (current_user_id,))
        if not result or result[0]['role'] not in ['admin', 'super_admin']:
            return jsonify({"error": "Admin access required"}), 403

        limit = int(request.args.get('limit', 100))
        logs = execute_safe_query("""
            SELECT * FROM AuditLogs 
            WHERE action IN ('archive_logs', 'restore_logs', 'purge_login_history') 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (limit,))
        
        return jsonify(logs)
    except Exception as e:
        logging.error(f"Audit trail error: {e}")
        return jsonify({'error': 'Failed to fetch audit trail'}), 500

