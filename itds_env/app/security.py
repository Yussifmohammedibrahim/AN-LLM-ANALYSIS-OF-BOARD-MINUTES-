"""
Security Utilities
JWT token handling, authentication decorators, and security functions.
"""
import re
import bcrypt
import bleach
from datetime import datetime, timedelta
from functools import wraps
import hashlib
import secrets
import jwt
import logging
from flask import request, jsonify
from app.config import Config


# ============================================
# Validation Functions
# ============================================

def validate_username(username):
    """Validate username format."""
    if not username or not isinstance(username, str):
        return False
    pattern = r'^[a-zA-Z0-9_]{3,20}$'
    return bool(re.match(pattern, username))


def validate_password(password):
    """Validate password strength."""
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


def validate_email(email):
    """Validate email format."""
    if not email or not isinstance(email, str):
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_theme(theme, allowed_themes):
    """Validate theme against allowed list."""
    return theme in allowed_themes


def validate_year(year):
    """Validate year format."""
    if not year or not isinstance(year, str):
        return False
    pattern = r'^\d{4}$'
    return bool(re.match(pattern, year)) and 2000 <= int(year) <= 2100


def validate_search_query(query):
    """Validate search query."""
    if not query or not isinstance(query, str):
        return False
    if len(query) < 3 or len(query) > 100:
        return False
    return True


# ============================================
# Sanitization Functions
# ============================================

def sanitize_input(text):
    """Sanitize user input."""
    if not text:
        return ""
    return bleach.clean(str(text))


# ============================================
# Password Functions
# ============================================

def hash_password(password):
    """Hash password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def check_password(password, password_hash):
    """Check password against hash."""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except Exception:
        return False


# ============================================
# Token Functions
# ============================================

def generate_reset_token():
    """Generate password reset token."""
    return secrets.token_urlsafe(32)


def hash_token(token):
    """Hash a token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_token(user_id, username, role):
    """
    Generate a JWT token for a user.
    
    Args:
        user_id: User's database ID
        username: User's username
        role: User's role (admin, editor, viewer)
    
    Returns:
        JWT token string
    """
    payload = {
        'user_id': user_id,
        'username': username,
        'role': role,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(hours=24)
    }
    
    return jwt.encode(payload, Config.SECRET_KEY, algorithm="HS256")


def decode_token(token):
    """
    Decode and validate a JWT token.
    
    Args:
        token: JWT token string
    
    Returns:
        Decoded payload or None if invalid
    """
    try:
        data = jwt.decode(token, Config.SECRET_KEY, algorithms=["HS256"])
        return data
    except jwt.ExpiredSignatureError:
        return {'error': 'Token has expired'}
    except jwt.InvalidTokenError:
        return {'error': 'Invalid token'}


# ============================================
# Account Security Functions
# ============================================

def is_account_locked(locked_until):
    """Check if account is locked."""
    if not locked_until:
        return False
    try:
        return datetime.utcnow() < datetime.fromisoformat(locked_until.replace('Z', '+00:00'))
    except Exception:
        return False


# ============================================
# Request Utility Functions
# ============================================

def get_client_ip(request):
    """Get client IP address."""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr or '0.0.0.0'


def get_user_agent(request):
    """Get user agent string."""
    return request.headers.get('User-Agent', 'Unknown')


# ============================================
# Logging Functions
# ============================================

def log_security_event(action, user_id, ip_address, user_agent, details=""):
    """Log security events."""
    logging.warning(
        f"SECURITY: {action} - User: {user_id} - IP: {ip_address} - Details: {details}"
    )


# ============================================
# Decorators
# ============================================

def token_required(f):
    """
    Decorator to require valid JWT token for routes.
    
    Usage:
        @app.route('/api/protected')
        @token_required
        def protected_route(current_user):
            return jsonify({'message': 'Hello', 'user': current_user.username})
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Get token from Authorization header
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({
                'message': 'Token is missing!',
                'error': 'authentication_required'
            }), 401
        
        try:
            from app.models import User
            data = jwt.decode(token, Config.SECRET_KEY, algorithms=["HS256"])
            current_user = User.query.filter_by(id=data['user_id']).first()
            
            if not current_user:
                return jsonify({
                    'message': 'User not found!',
                    'error': 'invalid_token'
                }), 401
            
            if not getattr(current_user, 'is_active', True):
                return jsonify({
                    'message': 'User account is disabled!',
                    'error': 'account_disabled'
                }), 401
            
            # Add current_user to kwargs
            kwargs['current_user'] = current_user
            
        except jwt.ExpiredSignatureError:
            return jsonify({
                'message': 'Token has expired!',
                'error': 'token_expired'
            }), 401
        
        except jwt.InvalidTokenError:
            return jsonify({
                'message': 'Invalid token!',
                'error': 'invalid_token'
            }), 401
        
        except Exception as e:
            return jsonify({
                'message': 'Authentication failed!',
                'error': 'authentication_error'
            }), 401
        
        return f(*args, **kwargs)
    
    return decorated


def admin_required(f):
    """
    Decorator to require admin role for routes.
    
    Usage:
        @app.route('/api/admin')
        @token_required
        @admin_required
        def admin_route(current_user):
            return jsonify({'message': 'Admin area'})
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # First check if user is authenticated
        if 'current_user' not in kwargs:
            return jsonify({
                'message': 'Authentication required!',
                'error': 'authentication_required'
            }), 401
        
        current_user = kwargs['current_user']
        
        if getattr(current_user, 'role', None) not in ['admin', 'super_admin']:
            return jsonify({
                'message': 'Admin access required!',
                'error': 'insufficient_permissions'
            }), 403
        
        return f(*args, **kwargs)
    
    return decorated


def editor_required(f):
    """
    Decorator to require editor or admin role for routes.
    
    Usage:
        @app.route('/api/edit')
        @token_required
        @editor_required
        def edit_route(current_user):
            return jsonify({'message': 'Editor area'})
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'current_user' not in kwargs:
            return jsonify({
                'message': 'Authentication required!',
                'error': 'authentication_required'
            }), 401
        
        current_user = kwargs['current_user']
        role = getattr(current_user, 'role', None)
        
        if role not in ['admin', 'editor', 'super_admin']:
            return jsonify({
                'message': 'Editor access required!',
                'error': 'insufficient_permissions'
            }), 403


def super_admin_required(f):
    """Decorator to require super admin role for routes."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'current_user' not in kwargs:
            return jsonify({
                'message': 'Authentication required!',
                'error': 'authentication_required'
            }), 401

        current_user = kwargs['current_user']
        if getattr(current_user, 'role', None) != 'super_admin':
            return jsonify({
                'message': 'Super admin access required!',
                'error': 'insufficient_permissions'
            }), 403

        return f(*args, **kwargs)

    return decorated
        
        return f(*args, **kwargs)
    
    return decorated


# ============================================
# Export
# ============================================

__all__ = [
    # Validation
    'validate_username',
    'validate_password',
    'validate_email',
    'validate_theme',
    'validate_year',
    'validate_search_query',
    
    # Sanitization
    'sanitize_input',
    
    # Password
    'hash_password',
    'check_password',
    
    # Token
    'generate_token',
    'decode_token',
    'generate_reset_token',
    'hash_token',
    
    # Account
    'is_account_locked',
    
    # Request
    'get_client_ip',
    'get_user_agent',
    
    # Logging
    'log_security_event',
    
    # Decorators
    'token_required',
    'admin_required',
    'editor_required',
    'super_admin_required'
]