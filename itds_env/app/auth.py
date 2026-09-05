"""
Authentication Routes
Handles login, logout, registration, and password management.
"""
import re
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity, get_jwt, decode_token
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import logging
import bleach
import os
from datetime import datetime, timezone, timedelta
from flask import current_app, make_response

# Import models for get_db
from .models import get_db, execute_safe_query, log_action

auth_bp = Blueprint('auth', __name__)

# ============================================
# VALIDATION FUNCTIONS
# ============================================

def validate_username(username):
    if not username or not isinstance(username, str):
        return False
    pattern = r'^[a-zA-Z0-9_-]{1,20}$'
    return bool(re.match(pattern, username))

def validate_password(password):
    """Strong password validation"""
    if not password or not isinstance(password, str):
        return False
    if len(password) < 8:
        return False
    if not re.search(r'[A-Z]', password):
        return False
    if not re.search(r'[a-z]', password):
        return False
    if not re.search(r'[0-9]', password):
        return False
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False
    return True


def is_privileged_role(role):
    return str(role).lower() in {'admin', 'super_admin'}

# ============================================
# HELPER FUNCTIONS
# ============================================

# log_action is imported from models.py above

# ============================================
# ROUTES
# ============================================

@auth_bp.route('/register', methods=['POST'])
def register():
    """
    Register new user (admin creates, temp password).
    
    Request:
        {
            "username": "string",
            "password": "string",  # temp password
            "role": "viewer" (optional)
        }
    
    Response (201):
        {
            "message": "User registered successfully"
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        username = data.get('username', '').strip()
        password = data.get('password', '')
        role = str(data.get('role', 'viewer')).strip().lower()

        if role not in {'viewer', 'editor', 'admin', 'super_admin'}:
            return jsonify({'error': 'Invalid role'}), 400

        if role == 'super_admin':
            return jsonify({'error': 'Super admin accounts must be created by a super admin bootstrap process'}), 403
        
        if not validate_username(username):
            return jsonify({'error': 'Invalid username. Must be 3-20 alphanumeric characters'}), 400
        
        if not validate_password(password):
            return jsonify({'error': 'Invalid password. Must be strong password'}), 400
        
        # Sanitize input
        username = bleach.clean(username)
        password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        
        try:
            user_id = execute_safe_query(
                'INSERT INTO Users (username, password_hash, role, must_change_password, created_at) VALUES (?, ?, ?, ?, ?)',
                (username, password_hash, role, 1, datetime.now(timezone.utc)),
                fetch=False
            )
            log_action('register', f'User {username} registered as new user with temp password', user_id)
            return jsonify({'message': 'User registered successfully with temporary password. Must change on first login.', 'user_id': user_id}), 201
        except sqlite3.IntegrityError:
            return jsonify({'error': 'Username already exists'}), 400
    except Exception as e:
        logging.error(f"Registration error: {e}")
        return jsonify({'error': 'Registration failed'}), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    User login.
    
    Request:
        {
            "username": "string",
            "password": "string"
        }
    
    Response (200):
        {
            "access_token": "string",
            "must_change_password": boolean,
            "role": "string",
            "username": "string"
        }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400
        
        if not validate_username(username):
            return jsonify({'error': 'Invalid credentials'}), 401
        
        # Sanitize input
        username = bleach.clean(username)
        
        result = execute_safe_query(
            'SELECT user_id, username, password_hash, role, must_change_password, is_deleted FROM Users WHERE username = ?',
            (username,)
        )
        
        if not result:
            return jsonify({'error': 'Invalid credentials'}), 401
        
        user = result[0]
        
        if user.get('is_deleted'):
            return jsonify({'error': 'Account is disabled'}), 403

        if check_password_hash(user['password_hash'], password):
            identity_payload = {
                'user_id': user['user_id'],
                'username': user['username'],
                'role': user['role']
            }
            access_token = create_access_token(identity=identity_payload)
            refresh_token = create_refresh_token(identity=identity_payload)

            # Persist refresh token jti for revocation and rotation support
            try:
                from .models import store_refresh_token
                decoded = decode_token(refresh_token)
                jti = decoded.get('jti')
                exp = decoded.get('exp')
                expires_at = datetime.utcfromtimestamp(exp)
                ip = request.remote_addr
                ua = request.headers.get('User-Agent')
                store_refresh_token(jti, user['user_id'], expires_at, ip_address=ip, user_agent=ua)
            except Exception:
                pass

            log_action('login', f'User {username} logged in, must_change={user["must_change_password"]}', user['user_id'])

            # Build response and set HttpOnly refresh cookie (also include refresh token in body for non-cookie setups)
            resp = make_response(jsonify({
                'access_token': access_token,
                'must_change_password': bool(user['must_change_password']),
                'role': user['role'],
                'username': user['username'],
                'user_id': user['user_id']
            }), 200)
            # Cookie settings
            cookie_name = current_app.config.get('JWT_REFRESH_COOKIE_NAME', 'refresh_token')
            secure_flag = current_app.config.get('JWT_COOKIE_SECURE', True)
            max_age = int(current_app.config.get('JWT_REFRESH_TOKEN_EXPIRES', timedelta(days=7)).total_seconds())
            resp.set_cookie(cookie_name, refresh_token, httponly=True, secure=secure_flag, samesite='Lax', max_age=max_age, path='/')
            return resp
        
        return jsonify({'error': 'Invalid credentials'}), 401
    except Exception as e:
        logging.error(f"Login error: {e}")
        return jsonify({'error': 'Login failed'}), 500


@auth_bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """
    User logout.
    
    Headers:
        Authorization: Bearer <token>
    
    Response (200):
        {
            "message": "Logged out successfully"
        }
    """
    identity = get_jwt_identity()
    username = identity.get('username', 'unknown')
    user_id = identity.get('user_id')

    # Revoke the access token (blocklist by inserting revoked record)
    try:
        jwt_payload = get_jwt()
        jti = jwt_payload.get('jti')
        exp_ts = jwt_payload.get('exp')
        from .models import store_refresh_token, revoke_token
        if jti:
            # store as revoked entry so blocklist will detect it
            expires_at = datetime.utcfromtimestamp(exp_ts) if exp_ts else None
            store_refresh_token(jti, user_id, expires_at, ip_address=request.remote_addr, user_agent=request.headers.get('User-Agent'))
            revoke_token(jti)
    except Exception:
        pass

    # Also try to revoke provided refresh token if present in body
    try:
        data = request.get_json(silent=True) or {}
        provided_refresh_jti = data.get('refresh_jti') or None
        from .models import revoke_token
        if provided_refresh_jti:
            revoke_token(provided_refresh_jti)
    except Exception:
        pass

    # Clear refresh cookie
    try:
        cookie_name = current_app.config.get('JWT_REFRESH_COOKIE_NAME', 'refresh_token')
        secure_flag = current_app.config.get('JWT_COOKIE_SECURE', True)
        resp = make_response(jsonify({'message': 'Logged out successfully'}), 200)
        resp.set_cookie(cookie_name, '', httponly=True, secure=secure_flag, samesite='Lax', max_age=0, expires=0, path='/')
    except Exception:
        resp = jsonify({'message': 'Logged out successfully'})

    log_action('logout', f'User {username} logged out', user_id)
    return resp



@auth_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """Refresh access token using a valid refresh token. Rotates refresh token by revoking old one and issuing a new one."""
    try:
        jwt_payload = get_jwt()
        identity = get_jwt_identity()
        user_id = identity.get('user_id') if isinstance(identity, dict) else None

        old_jti = jwt_payload.get('jti')

        # Issue new access token
        new_access = create_access_token(identity=identity)

        # Rotate refresh token: revoke old, issue new, persist
        new_refresh = create_refresh_token(identity=identity)
        try:
            from .models import revoke_token, store_refresh_token
            # revoke old
            if old_jti:
                revoke_token(old_jti)
            decoded = decode_token(new_refresh)
            new_jti = decoded.get('jti')
            exp = decoded.get('exp')
            expires_at = datetime.utcfromtimestamp(exp) if exp else None
            store_refresh_token(new_jti, user_id, expires_at, ip_address=request.remote_addr, user_agent=request.headers.get('User-Agent'))
        except Exception:
            pass

        # Set HttpOnly cookie with new refresh token
        try:
            cookie_name = current_app.config.get('JWT_REFRESH_COOKIE_NAME', 'refresh_token')
            secure_flag = current_app.config.get('JWT_COOKIE_SECURE', True)
            max_age = int(current_app.config.get('JWT_REFRESH_TOKEN_EXPIRES', timedelta(days=7)).total_seconds())
            resp = make_response(jsonify({'access_token': new_access}), 200)
            resp.set_cookie(cookie_name, new_refresh, httponly=True, secure=secure_flag, samesite='Lax', max_age=max_age, path='/')
            log_action('token_refresh', f'User {identity.get("username") if isinstance(identity, dict) else identity} refreshed access token', user_id)
            return resp
        except Exception:
            log_action('token_refresh', f'User {identity.get("username") if isinstance(identity, dict) else identity} refreshed access token (cookie set failed)', user_id)
            return jsonify({'access_token': new_access, 'refresh_token': new_refresh}), 200
    except Exception as e:
        logging.error(f"Token refresh error: {e}")
        return jsonify({'error': 'Refresh failed'}), 500



@auth_bp.route('/users', methods=['GET'])
@jwt_required
def get_users():
    """
    Get all users (admin only).
    
    Headers:
        Authorization: Bearer <token>
    
    Response (200):
        [
            {
                "user_id": 1,
                "username": "admin",
                "role": "admin",
                "must_change_password": 0,
                "created_at": "2024-01-01 00:00:00"
            }
        ]
    """
    try:
        identity = get_jwt_identity()
        if identity.get('role') not in {'admin', 'super_admin'}:
            return jsonify({'error': 'Admin access required'}), 403
        
        include_deleted = request.args.get('include_deleted', '0') == '1' and identity.get('role') == 'super_admin'
        query = 'SELECT user_id, username, role, must_change_password, created_at, is_deleted, deleted_at, delete_reason FROM Users'
        params = []
        if not include_deleted:
            query += ' WHERE COALESCE(is_deleted, 0) = 0'
        query += ' ORDER BY created_at DESC'
        
        users = execute_safe_query(query, params)
        
        user_list = []
        for user in users:
            user_list.append({
                'user_id': user['user_id'],
                'username': user['username'],
                'role': user['role'],
                'must_change_password': user['must_change_password'],
                'created_at': str(user['created_at']),
                'is_deleted': bool(user['is_deleted']),
                'deleted_at': str(user['deleted_at']) if user['deleted_at'] else None,
                'delete_reason': user['delete_reason']
            })
        
        return jsonify(user_list), 200
        
    except Exception as e:
        logging.error(f"Get users error: {e}")
        return jsonify({'error': 'Failed to get users'}), 500


@auth_bp.route('/me', methods=['GET'])
@jwt_required
def get_current_user():
    """
    Get current user info.
    
    Headers:
        Authorization: Bearer <token>
    
    Response (200):
        {
            "user_id": 1,
            "username": "admin",
            "role": "admin",
            "must_change_password": 0
        }
    """
    identity = get_jwt_identity()
    
    # Get full user info from DB including must_change_password
    user = execute_safe_query(
        'SELECT user_id, username, role, must_change_password, is_deleted FROM Users WHERE user_id = ?', 
        (identity['user_id'],)
    )
    
    if user and not user[0]['is_deleted']:
        user_data = user[0]
        return jsonify({
            'user_id': user_data['user_id'],
            'username': user_data['username'],
            'role': user_data['role'],
            'must_change_password': user_data['must_change_password']
        }), 200
    if user and user['is_deleted']:
        return jsonify({'error': 'User account is disabled'}), 403
    return jsonify({'error': 'User not found'}), 404


def requires_roles(*allowed_roles):
    from functools import wraps
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                identity = get_jwt_identity()
                role = identity.get('role') if isinstance(identity, dict) else None
                if role is None or role not in allowed_roles:
                    return jsonify({'error': 'Access denied'}), 403
            except Exception:
                return jsonify({'error': 'Access denied'}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator



