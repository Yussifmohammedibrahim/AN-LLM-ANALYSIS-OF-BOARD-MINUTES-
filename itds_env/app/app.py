from flask import Flask, request, jsonify, send_from_directory, Response, copy_current_request_context
from flask_cors import CORS, cross_origin
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity, create_access_token, get_jwt, decode_token
import sqlite3
from datetime import datetime, timezone, timedelta
import io
import logging
from dotenv import load_dotenv
import os
import tempfile
import shutil
import secrets
import json
import time
import html as html_utils
from urllib.parse import urlparse
from email.utils import formatdate
from email.mime.base import MIMEBase
from email import encoders
import uuid
from werkzeug.security import generate_password_hash, check_password_hash
from .models import get_db
import re
import ipaddress
import importlib
import threading
import ssl

logger = logging.getLogger(__name__)

try:
    import requests as http_requests
except ImportError:
    http_requests = None

# Optional field encryption helpers (uses Fernet symmetric encryption if available)
try:
    from cryptography.fernet import Fernet, InvalidToken
    CRYPTO_KEY = os.getenv('ITDS_CRYPTO_KEY')
    if not CRYPTO_KEY:
        # Do not auto-generate in production; only fallback for local dev
        CRYPTO_KEY = Fernet.generate_key().decode('utf-8')
    _fernet = Fernet(CRYPTO_KEY.encode('utf-8'))

    def encrypt_value(plaintext: str) -> str:
        if plaintext is None:
            return None
        return _fernet.encrypt(plaintext.encode('utf-8')).decode('utf-8')

    def decrypt_value(token: str) -> str:
        if token is None:
            return None
        try:
            return _fernet.decrypt(token.encode('utf-8')).decode('utf-8')
        except InvalidToken:
            raise ValueError('Invalid encrypted value')
except Exception:
    _fernet = None
    def encrypt_value(plaintext: str) -> str:
        raise RuntimeError('Field encryption not available. Install cryptography and set ITDS_CRYPTO_KEY')
    def decrypt_value(token: str) -> str:
        raise RuntimeError('Field encryption not available. Install cryptography and set ITDS_CRYPTO_KEY')

try:
    _pywebpush_module = importlib.import_module('pywebpush')
    webpush = getattr(_pywebpush_module, 'webpush', None)
    WebPushException = getattr(_pywebpush_module, 'WebPushException', Exception)
except Exception:
    webpush = None
    WebPushException = Exception

parse_user_agent = None
try:
    import pytesseract
    from PIL import Image, ImageOps, ImageFilter
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False
    print("Warning: pytesseract not available. Image processing will be limited.")

try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
    print("Warning: PyPDF2 not available. PDF processing will be limited.")

try:
    import fitz
    PYMUPDF_AVAILABLE = True
except ImportError:
    fitz = None
    PYMUPDF_AVAILABLE = False
    print("Warning: PyMuPDF not available. Scanned PDF OCR will be limited.")

try:
    from docx import Document
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    print("Warning: python-docx not available. DOCX processing will be limited.")

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))
logger.info("OPENAI_API_KEY loaded: %s", "yes" if os.environ.get("OPENAI_API_KEY") else "no")

from .models import get_db, execute_safe_query
from .services.email_service import (
    send_email, send_welcome_email, send_reset_email,
    send_password_reset_confirmation, send_password_changed_email,
    _send_web_push, _create_notification_event, _get_vapid_config,
    generate_button, render_email_template
)

# Email and Notification logic moved to services/email_service.py

# Initialize NER for anonymization lazily to avoid slow startup
ner_pipeline = None

def get_ner_pipeline():
    global ner_pipeline
    if ner_pipeline is None:
        try:
            from transformers import pipeline
            model_name = os.getenv('ITDS_NER_MODEL', '').strip()
            if not model_name:
                raise RuntimeError('Missing required environment variable: ITDS_NER_MODEL')
            ner_pipeline = pipeline("ner", model=model_name)
        except Exception as exc:
            logging.warning(f"NER pipeline unavailable: {exc}")
            ner_pipeline = False
    return ner_pipeline

def sanitize_filename(filename):
    """Sanitize uploaded filenames to prevent path traversal."""
    return os.path.basename(filename)


def _configure_tesseract_cmd():
    """Resolve Tesseract binary path, especially on Windows deployments."""
    if not PYTESSERACT_AVAILABLE:
        return

    env_cmd = os.getenv('TESSERACT_CMD')
    if env_cmd and os.path.exists(env_cmd):
        pytesseract.pytesseract.tesseract_cmd = env_cmd
        return

    detected_cmd = shutil.which('tesseract')
    if detected_cmd:
        pytesseract.pytesseract.tesseract_cmd = detected_cmd
        return

    if os.name == 'nt':
        common_windows_paths = [
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        ]
        for candidate in common_windows_paths:
            if os.path.exists(candidate):
                pytesseract.pytesseract.tesseract_cmd = candidate
                return


def _extract_text_from_image(file_path):
    """Run OCR with light preprocessing to improve scanned-image extraction."""
    if not PYTESSERACT_AVAILABLE:
        raise ValueError("Image processing not available. Please install pytesseract: pip install pytesseract")

    _configure_tesseract_cmd()

    # Enhance contrast and size for cleaner OCR on scanned documents.
    with Image.open(file_path) as source_image:
        image = source_image.convert('L')
        image = ImageOps.autocontrast(image)
        image = image.filter(ImageFilter.MedianFilter(size=3))

        min_width = 1800
        if image.width < min_width:
            scale = min_width / float(image.width)
            new_size = (int(image.width * scale), int(image.height * scale))
            image = image.resize(new_size, Image.Resampling.LANCZOS)

        binary_image = image.point(lambda px: 255 if px > 170 else 0)
        ocr_config = '--oem 3 --psm 6'
        return pytesseract.image_to_string(binary_image, config=ocr_config)


def _extract_text_from_scanned_pdf(file_path):
    """Render scanned PDF pages and OCR them page by page."""
    if not PYMUPDF_AVAILABLE:
        raise ValueError(
            "Scanned PDF OCR is not available. Please install PyMuPDF or upload an image file."
        )

    page_texts = []
    with fitz.open(file_path) as pdf_document:
        for page in pdf_document:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.open(io.BytesIO(pixmap.tobytes("png")))
            image = image.convert('L')
            image = ImageOps.autocontrast(image)
            image = image.filter(ImageFilter.MedianFilter(size=3))
            if image.width < 1800:
                scale = 1800 / float(image.width)
                new_size = (int(image.width * scale), int(image.height * scale))
                image = image.resize(new_size, Image.Resampling.LANCZOS)

            binary_image = image.point(lambda px: 255 if px > 170 else 0)
            page_text = pytesseract.image_to_string(binary_image, config='--oem 3 --psm 6')
            if page_text and page_text.strip():
                page_texts.append(page_text.strip())

    return '\n\n'.join(page_texts)


_configure_tesseract_cmd()

def extract_text(file_path):
    """Extract text from PDF, .docx, or image files with validation."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    # Check file extension
    allowed_extensions = {'.pdf', '.docx', '.png', '.jpg', '.jpeg', '.tiff', '.tif', '.webp'}
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in allowed_extensions:
        raise ValueError(f"Unsupported file type: {ext}")
    
    if file_path.endswith('.pdf'):
        if not PYPDF2_AVAILABLE:
            raise ValueError("PDF processing not available. Please install PyPDF2: pip install PyPDF2")
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            text = ''.join((page.extract_text() or '') for page in reader.pages)

            if not text.strip():
                text = _extract_text_from_scanned_pdf(file_path)
    elif file_path.endswith('.docx'):
        if not DOCX_AVAILABLE:
            raise ValueError("DOCX processing not available. Please install python-docx: pip install python-docx")
        doc = Document(file_path)
        text = '\n'.join([para.text for para in doc.paragraphs])
    else:
        # Image files
        text = _extract_text_from_image(file_path)

    if not text or not text.strip():
        raise ValueError(
            "No readable text was extracted from this file. "
            "Please upload a clearer scan or higher-resolution image."
        )
    
    return text

def transform_text(text):
    """Clean, anonymize, and segment text."""
    # Remove metadata
    text = re.sub(r'(Attendance|Signatures|Header|Footer).*?\n', '', text, flags=re.IGNORECASE)
    # Remove special characters for security
    text = re.sub(r'[^\w\s.,!?-]', '', text)
    # Anonymize personal names
    ner = get_ner_pipeline()
    if ner:
        entities = ner(text)
        for entity in entities:
            if entity['entity'] == 'PERSON':
                text = text.replace(entity['word'], f'[MEMBER_{hash(entity["word"]) % 1000}]')
    # Segment into chunks
    words = text.split()
    segments = [' '.join(words[i:i+500]) for i in range(0, len(words), 500)]
    return segments

app = Flask(__name__)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret')
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'dev-jwt')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=7)

jwt = JWTManager(app)

# Allow cookies as a token location (so refresh token can be stored HttpOnly)
app.config.setdefault('JWT_TOKEN_LOCATION', ['headers', 'cookies'])
app.config.setdefault('JWT_REFRESH_COOKIE_NAME', 'refresh_token')
app.config.setdefault('JWT_COOKIE_CSRF_PROTECT', False)
app.config.setdefault('JWT_COOKIE_SECURE', os.getenv('ENABLE_SECURE_COOKIES', '1') == '1')

# Enable CORS with credentials (so browser can send cookies)
CORS(app, supports_credentials=True, allow_headers=['Content-Type', 'Authorization'], methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])

# Handle CORS preflight requests
@app.before_request
def handle_preflight_request():
    if request.method == 'OPTIONS':
        response = Response()
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Max-Age'] = '3600'
        return response, 200

# Blocklist / revocation support for JWTs
try:
    from .models import is_token_revoked

    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        jti = jwt_payload.get('jti')
        if not jti:
            return True
        try:
            return bool(is_token_revoked(jti))
        except Exception:
            return True
except Exception:
    pass

# Optional Swagger UI using flasgger (enabled if package installed)
try:
    from flasgger import Swagger
    swagger = Swagger(app)
except Exception:
    swagger = None

# Let browser CORS preflight (OPTIONS) pass without JWT checks.
app.config['JWT_EXEMPT_METHODS'] = ['OPTIONS']

# Optional rate limiting using flask-limiter (if installed)
limiter = None

# Standardized JSON error handlers
@app.errorhandler(400)
def _handle_400(err):
    return jsonify({'error': 'bad_request', 'message': str(err)}), 400

@app.errorhandler(404)
def _handle_404(err):
    return jsonify({'error': 'not_found', 'message': str(err)}), 404

@app.errorhandler(500)
def _handle_500(err):
    import traceback
    logging.error('Internal server error: %s', traceback.format_exc())
    return jsonify({'error': 'internal_server_error', 'message': 'An unexpected error occurred'}), 500

# ============================================
# INITIALIZE AI MODELS ON APP STARTUP
# ============================================
def initialize_models_on_startup():
    """Initialize AI models once during app startup."""
    try:
        from .model_manager import initialize_models
        logging.info("Pre-loading AI models on startup...")
        initialize_models()
        logging.info("[OK] AI models startup initialization completed")
    except Exception as e:
        # Non-blocking: endpoints can still trigger lazy model load when needed.
        logging.warning(f"AI model startup initialization warning (non-blocking): {e}")

# Make uploaded profile images publicly accessible
@app.route('/uploads/profile_images/<path:filename>')
def serve_profile_image(filename):
    directory = os.path.join(os.getcwd(), 'uploads', 'profile_images')
    return send_from_directory(directory, filename)

# ============================================
# DASHBOARD ROUTES
# ============================================

from .admin import admin_bp
app.register_blueprint(admin_bp)

from .ai_routes import ai_bp
app.register_blueprint(ai_bp)

from .report_generator import report_bp
app.register_blueprint(report_bp)

# Logging handled by logging.conf

# execute_safe_query is imported from models.py above


def get_client_ip():
    """Resolve client IP from proxy headers or remote address."""
    # Ordered by common deployment setups (Cloudflare/reverse proxy/load balancer).
    candidates = [
        request.headers.get('CF-Connecting-IP'),
        request.headers.get('True-Client-IP'),
        request.headers.get('X-Real-IP'),
        request.headers.get('X-Forwarded-For'),
        request.remote_addr,
    ]

    for candidate in candidates:
        if not candidate:
            continue

        # X-Forwarded-For can be a comma-separated chain.
        raw_value = str(candidate).split(',')[0].strip()
        if not raw_value:
            continue

        try:
            ip_obj = ipaddress.ip_address(raw_value)
            if ip_obj.is_unspecified:
                continue
            return raw_value
        except Exception:
            continue

    return '0.0.0.0'


def get_client_location():
    """Best-effort location based on proxy/CDN headers."""
    country = (
        request.headers.get('X-Country')
        or request.headers.get('CF-IPCountry')
        or request.headers.get('X-Geo-Country')
        or ''
    ).strip()
    city = (request.headers.get('X-City') or request.headers.get('X-Geo-City') or '').strip()

    if city and country:
        return f"{city}, {country}"
    if country:
        return country
    return 'Unknown'


def _is_public_ip(ip_value):
    try:
        ip_obj = ipaddress.ip_address(ip_value)
        return not (ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved or ip_obj.is_multicast)
    except Exception:
        return False


def parse_client_user_agent(user_agent):
    """Parse user-agent into device type, browser, and OS."""
    global parse_user_agent

    if parse_user_agent is None:
        try:
            parse_user_agent = importlib.import_module('user_agents').parse
        except Exception:
            parse_user_agent = False

    default = {
        'device_type': 'Desktop',
        'browser': 'Chrome',
        'os': 'Windows',  # Dev fallback - real after metadata/user_agents
    }



    if not user_agent:
        return default

    try:
        if parse_user_agent:
            ua = parse_user_agent(user_agent)
            if ua.is_mobile:
                device_type = 'mobile'
            elif ua.is_tablet:
                device_type = 'tablet'
            else:
                device_type = 'desktop'

            browser = ua.browser.family or 'Unknown'
            os_name = ua.os.family or 'Unknown'
            return {
                'device_type': device_type,
                'browser': browser,
                'os': os_name,
            }
    except Exception as exc:
        logging.warning(f"UA parse failed: {exc}")

    ua_lower = str(user_agent).lower()
    device_type = 'mobile' if any(x in ua_lower for x in ['iphone', 'android', 'mobile']) else 'desktop'
    browser = 'Chrome' if 'chrome' in ua_lower else 'Firefox' if 'firefox' in ua_lower else 'Safari' if 'safari' in ua_lower else 'Unknown'
    os_name = 'Windows' if 'windows' in ua_lower else 'Android' if 'android' in ua_lower else 'iOS' if 'iphone' in ua_lower or 'ipad' in ua_lower else 'Unknown'

    return {
        'device_type': device_type,
        'browser': browser,
        'os': os_name,
    }


def get_ip_geolocation(ip_address):
    """Resolve IP address to a coarse location using ip-api.com (best effort)."""
    if not ip_address or not _is_public_ip(ip_address) or not http_requests:
        return {
            'country': None,
            'region': None,
            'city': None,
            'lat': None,
            'lon': None,
        }

    try:
        resp = http_requests.get(
            f"http://ip-api.com/json/{ip_address}?fields=status,country,regionName,city,lat,lon",
            timeout=1.2,
        )
        if resp.status_code != 200:
            return {
                'country': None,
                'region': None,
                'city': None,
                'lat': None,
                'lon': None,
            }

        payload = resp.json() if resp.content else {}
        if payload.get('status') != 'success':
            return {
                'country': None,
                'region': None,
                'city': None,
                'lat': None,
                'lon': None,
            }

        return {
            'country': payload.get('country'),
            'region': payload.get('regionName'),
            'city': payload.get('city'),
            'lat': payload.get('lat'),
            'lon': payload.get('lon'),
        }
    except Exception as exc:
        logging.info(f"IP geolocation skipped: {exc}")
        return {
            'country': None,
            'region': None,
            'city': None,
            'lat': None,
            'lon': None,
        }


def log_archiving_activity(admin_user_id, action, details, actor_username='admin', actor_role='admin'):
    """Log admin archiving actions to AuditLogs for audit trail."""
    try:
        ip_address = get_client_ip()
        user_agent = request.headers.get('User-Agent', 'Unknown')
        payload = dict(details or {}) if isinstance(details, dict) else {'details': details}
        payload['actor_role'] = actor_role
        execute_safe_query(
            '''
            INSERT INTO AuditLogs (user_id, username, action, details, ip_address, user_agent, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                admin_user_id, actor_username, action, json.dumps(payload),
                ip_address, user_agent, datetime.now(timezone.utc).isoformat()
            ),
            fetch=False
        )
    except Exception as exc:
        logging.warning(f"Failed to log archiving activity: {exc}")

def log_auth_activity(action, user_id, username, details='', client_metadata=None, login_status='success'):
    """Write auth activity with metadata to AuditLogs - runs asynchronously without blocking response."""
    # Run logging in background thread to avoid delaying login/logout response
    @copy_current_request_context
    def _log_activity():
        try:
            # Prefer client-detected IP (more accurate), fallback to server-detected IP
            ip_address = None
            if isinstance(client_metadata, dict):
                ip_address = client_metadata.get('client_ip')
            if not ip_address:
                ip_address = get_client_ip()
            
            user_agent = request.headers.get('User-Agent', 'Unknown')
            location = get_client_location()
            device_name = None
            platform = None
            timezone_name = None
            browser_language = None
            metadata_latitude = None
            metadata_longitude = None
            metadata_accuracy = None

            if isinstance(client_metadata, dict):
                device_name = client_metadata.get('device_name')
                platform = client_metadata.get('platform')
                timezone_name = client_metadata.get('timezone')
                browser_language = client_metadata.get('browser_language')

                loc = client_metadata.get('location')
                if isinstance(loc, dict):
                    lat = loc.get('latitude')
                    lon = loc.get('longitude')
                    accuracy = loc.get('accuracy_m')
                    if lat is not None and lon is not None:
                        metadata_latitude = lat
                        metadata_longitude = lon
                        metadata_accuracy = accuracy
                        if accuracy is not None:
                            location = f"{lat}, {lon} (±{accuracy}m)"
                        else:
                            location = f"{lat}, {lon}"
                elif isinstance(loc, str) and loc.strip():
                    location = loc.strip()

            if (not device_name or str(device_name).strip().lower() in {'', 'unknown', 'unknown device'}) and platform:
                device_name = platform

            if (not location or str(location).strip().lower() in {'', 'unknown'}) and timezone_name:
                location = f"Timezone: {timezone_name}"

            ua_data = parse_client_user_agent(user_agent)
            device_type = ua_data.get('device_type') or 'desktop'
            browser_name = ua_data.get('browser') or 'Unknown'
            os_name = ua_data.get('os') or 'Unknown'

            has_precise_client_location = metadata_latitude is not None and metadata_longitude is not None
            country = None
            region = None
            city = None
            latitude = metadata_latitude
            longitude = metadata_longitude

            if not has_precise_client_location:
                geo = get_ip_geolocation(ip_address)
                country = geo.get('country')
                region = geo.get('region')
                city = geo.get('city')
                latitude = geo.get('lat')
                longitude = geo.get('lon')

                if city and country:
                    location = f"{city}, {country}"
                elif country:
                    location = country

            payload = {
                'details': details,
                'location': location,
                'ip_address': ip_address,
                'event': action,
                'login_status': login_status,
                'device_name': device_name,
                'device_type': device_type,
                'browser': browser_name,
                'os': os_name,
                'country': country,
                'region': region,
                'city': city,
                'latitude': latitude,
                'longitude': longitude,
                'location_source': 'gps' if has_precise_client_location else 'ip',
                'location_accuracy_m': metadata_accuracy,
                'platform': platform,
                'timezone': timezone_name,
                'browser_language': browser_language,
                'client_metadata': client_metadata if isinstance(client_metadata, dict) else None,
            }

            # Parse new device metadata
            mac_address = None
            ram_gb = None
            cpu_cores = None
            hardware_id = None
            
            if isinstance(client_metadata, dict):
                mac_address = client_metadata.get('mac_approx') or client_metadata.get('hardware_id')
                ram_gb = client_metadata.get('ram_gb')
                cpu_cores = client_metadata.get('cpu_cores')
                hardware_id = client_metadata.get('hardware_id')
            
            execute_safe_query(
                '''
                INSERT INTO AuditLogs (
                    user_id, username, action, details, ip_address, user_agent,
                    mac_address, ram_gb, cpu_cores, hardware_id,
                    login_status, country, region, city, latitude, longitude,
                    device_type, browser, os, timestamp, archived_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                ''',
                (
                    user_id, username, action, json.dumps(payload),
                    ip_address, user_agent,
                    mac_address, ram_gb, cpu_cores, hardware_id,
                    login_status, country, region, city, latitude, longitude,
                    device_type, browser_name, os_name, 
                    datetime.now(timezone.utc).isoformat()
                ),
                fetch=False,
            )
        except Exception as exc:
            logging.warning(f"Failed to log auth activity: {exc}")

    # Start background thread without blocking
    thread = threading.Thread(target=_log_activity, daemon=True)
    thread.start()


def ensure_audit_logs_schema():
    """Backfill missing AuditLogs columns for enhanced device tracking."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(AuditLogs)")
        columns = {row[1] for row in cursor.fetchall()}

        required = {
            'username': 'TEXT',
            'ip_address': 'TEXT',
            'user_agent': 'TEXT',
            'mac_address': 'TEXT',
            'ram_gb': 'REAL',
            'cpu_cores': 'INTEGER',
            'hardware_id': 'TEXT',
            'login_status': 'TEXT',
            'country': 'TEXT',
            'region': 'TEXT',
            'city': 'TEXT',
            'latitude': 'REAL',
            'longitude': 'REAL',
            'device_type': 'TEXT',
            'browser': 'TEXT',
            'os': 'TEXT',
        }
        for column_name, column_type in required.items():
            if column_name not in columns:
                cursor.execute(f"ALTER TABLE AuditLogs ADD COLUMN {column_name} {column_type}")
                print(f"Added column: {column_name}")

        conn.commit()
        print("[OK] AuditLogs schema ensured")
    except Exception as exc:
        logging.warning(f"AuditLogs schema check failed: {exc}")
    finally:
        conn.close()


def ensure_users_schema():
    """Backfill missing Users columns needed by auth activity updates."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(Users)")
        columns = {row[1] for row in cursor.fetchall()}

        required = {
            'created_at': 'TIMESTAMP',
            'last_login': 'TIMESTAMP',
            'last_logout': 'TIMESTAMP',
            'is_deleted': 'INTEGER DEFAULT 0',
            'deleted_at': 'TIMESTAMP DEFAULT NULL',
            'deleted_by': 'INTEGER DEFAULT NULL',
            'delete_reason': 'TEXT DEFAULT NULL',
            'push_notifications_enabled': 'INTEGER DEFAULT 1',
            'email_alerts_enabled': 'INTEGER DEFAULT 0',
            'push_permission': "TEXT DEFAULT 'default'",
            'notification_settings_updated_at': 'TIMESTAMP DEFAULT NULL',
        }
        for column_name, column_type in required.items():
            if column_name not in columns:
                cursor.execute(f"ALTER TABLE Users ADD COLUMN {column_name} {column_type}")

        # Backfill missing timestamps for existing users.
        cursor.execute("UPDATE Users SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")

        # Ensure future inserts get created_at even when not provided explicitly.
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS users_set_created_at
            AFTER INSERT ON Users
            FOR EACH ROW
            WHEN NEW.created_at IS NULL
            BEGIN
                UPDATE Users
                SET created_at = CURRENT_TIMESTAMP
                WHERE user_id = NEW.user_id;
            END;
        ''')

        conn.commit()
    except Exception as exc:
        logging.warning(f"Users schema check failed: {exc}")
    finally:
        conn.close()


def ensure_transcripts_schema():
    """Ensure Transcripts table and required columns exist for realtime analytics."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS Transcripts (
                transcript_id INTEGER PRIMARY KEY,
                user_id INTEGER,
                transcript_text TEXT,
                meeting_id INTEGER DEFAULT NULL,
                sentiment TEXT DEFAULT NULL,
                keywords TEXT DEFAULT NULL,
                analysis_complete INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute("PRAGMA table_info(Transcripts)")
        columns = {row[1] for row in cursor.fetchall()}
        required = {
            'meeting_id': 'INTEGER DEFAULT NULL',
            'sentiment': 'TEXT DEFAULT NULL',
            'keywords': 'TEXT DEFAULT NULL',
            'analysis_complete': 'INTEGER DEFAULT 0',
            'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
            'is_deleted': 'INTEGER DEFAULT 0',
            'deleted_at': 'TIMESTAMP DEFAULT NULL',
            'deleted_by': 'INTEGER DEFAULT NULL',
            'delete_reason': 'TEXT DEFAULT NULL',
            'analysis_cleared_at': 'TIMESTAMP DEFAULT NULL',
            'analysis_cleared_by': 'INTEGER DEFAULT NULL',
        }
        for column_name, column_type in required.items():
            if column_name not in columns:
                cursor.execute(f"ALTER TABLE Transcripts ADD COLUMN {column_name} {column_type}")

        conn.commit()
    except Exception as exc:
        logging.warning(f"Transcripts schema check failed: {exc}")
    finally:
        conn.close()


def ensure_meetings_schema():
    """Ensure Meetings has the metadata needed to list uploaded documents."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(Meetings)")
        columns = {row[1] for row in cursor.fetchall()}

        if 'source_filename' not in columns:
            cursor.execute('ALTER TABLE Meetings ADD COLUMN source_filename TEXT DEFAULT NULL')

        conn.commit()
    except Exception as exc:
        logging.warning(f"Meetings schema check failed: {exc}")
    finally:
        conn.close()


def ensure_report_schedules_schema():
    """Persist per-user scheduled report preferences for future delivery hooks."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ReportSchedules (
                schedule_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                enabled INTEGER DEFAULT 0,
                cadence TEXT DEFAULT 'weekly',
                delivery_date TEXT DEFAULT NULL,
                delivery_time TEXT DEFAULT '08:00',
                recipient_emails TEXT DEFAULT NULL,
                filters_json TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES Users(user_id)
            )
        ''')
        cursor.execute('PRAGMA table_info(ReportSchedules)')
        columns = {row[1] for row in cursor.fetchall()}
        if 'delivery_date' not in columns:
            cursor.execute('ALTER TABLE ReportSchedules ADD COLUMN delivery_date TEXT DEFAULT NULL')
        if 'last_delivery_status' not in columns:
            cursor.execute('ALTER TABLE ReportSchedules ADD COLUMN last_delivery_status TEXT DEFAULT NULL')
        if 'last_delivery_error' not in columns:
            cursor.execute('ALTER TABLE ReportSchedules ADD COLUMN last_delivery_error TEXT DEFAULT NULL')
        if 'last_delivery_at' not in columns:
            cursor.execute('ALTER TABLE ReportSchedules ADD COLUMN last_delivery_at TEXT DEFAULT NULL')
        if 'is_deleted' not in columns:
            cursor.execute('ALTER TABLE ReportSchedules ADD COLUMN is_deleted INTEGER DEFAULT 0')
        if 'deleted_at' not in columns:
            cursor.execute('ALTER TABLE ReportSchedules ADD COLUMN deleted_at TEXT DEFAULT NULL')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_report_schedules_user ON ReportSchedules(user_id)')
        conn.commit()
    except Exception as exc:
        logging.warning(f"Report schedules schema check failed: {exc}")
    finally:
        conn.close()


def ensure_document_classifications_schema():
    """Ensure DocumentClassifications exists for cleanup and classifier results."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS DocumentClassifications (
                classification_id INTEGER PRIMARY KEY,
                meeting_id INTEGER,
                document_type TEXT,
                confidence REAL,
                all_scores TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (meeting_id) REFERENCES Meetings(meeting_id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_docclass_meeting ON DocumentClassifications(meeting_id)')
        conn.commit()
    except Exception as exc:
        logging.warning(f"DocumentClassifications schema check failed: {exc}")
    finally:
        conn.close()


def ensure_summaries_schema():
    """Ensure Summaries is stored as one row per meeting with confidence metadata."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(Summaries)")
        columns = {row[1] for row in cursor.fetchall()}

        if 'meeting_id' not in columns:
            cursor.execute('ALTER TABLE Summaries ADD COLUMN meeting_id INTEGER DEFAULT NULL')
        if 'confidence_score' not in columns:
            cursor.execute('ALTER TABLE Summaries ADD COLUMN confidence_score REAL DEFAULT NULL')

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
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_summaries_meeting_unique ON Summaries(meeting_id)')
        conn.commit()
    except Exception as exc:
        logging.warning(f"Summaries schema check failed: {exc}")
    finally:
        conn.close()


def ensure_segment_analysis_uniqueness_schema():
    """Ensure one Sentiments/Keywords row per segment to prevent duplicate report rows."""
    conn = get_db()
    try:
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Sentiments' LIMIT 1")
        has_sentiments = bool(cursor.fetchone())
        if has_sentiments:
            cursor.execute('''
                DELETE FROM Sentiments
                WHERE sentiment_id NOT IN (
                    SELECT MAX(sentiment_id)
                    FROM Sentiments
                    GROUP BY segment_id
                )
            ''')
            cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_sentiments_segment_unique ON Sentiments(segment_id)')

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Keywords' LIMIT 1")
        has_keywords = bool(cursor.fetchone())
        if has_keywords:
            cursor.execute('''
                DELETE FROM Keywords
                WHERE keyword_id NOT IN (
                    SELECT MAX(keyword_id)
                    FROM Keywords
                    GROUP BY segment_id
                )
            ''')
            cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_keywords_segment_unique ON Keywords(segment_id)')

        conn.commit()
    except Exception as exc:
        logging.warning(f"Segment analysis uniqueness schema check failed: {exc}")
    finally:
        conn.close()


def ensure_notification_subscriptions_schema():
    """Ensure subscription table exists for server-driven web push delivery."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS NotificationSubscriptions (
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
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notif_sub_user ON NotificationSubscriptions(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notif_sub_active ON NotificationSubscriptions(is_active)')
        conn.commit()
    except Exception as exc:
        logging.warning(f"NotificationSubscriptions schema check failed: {exc}")
    finally:
        conn.close()


def ensure_notification_events_schema():
    """Ensure unified notification history exists for email and push delivery."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS NotificationEvents (
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
                is_deleted INTEGER DEFAULT 0,
                deleted_at TIMESTAMP DEFAULT NULL,
                is_archived INTEGER DEFAULT 0,
                archived_at TIMESTAMP DEFAULT NULL,
                metadata TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_at TIMESTAMP DEFAULT NULL,
                delivered_at TIMESTAMP DEFAULT NULL,
                failed_at TIMESTAMP DEFAULT NULL,
                error_message TEXT DEFAULT NULL,
                recipient_email TEXT DEFAULT NULL,
                FOREIGN KEY (user_id) REFERENCES Users(user_id),
                FOREIGN KEY (actor_user_id) REFERENCES Users(user_id)
            )
        ''')
        cursor.execute('PRAGMA table_info(NotificationEvents)')
        existing_columns = {row[1] for row in cursor.fetchall()}
        if 'is_deleted' not in existing_columns:
            cursor.execute('ALTER TABLE NotificationEvents ADD COLUMN is_deleted INTEGER DEFAULT 0')
        if 'deleted_at' not in existing_columns:
            cursor.execute('ALTER TABLE NotificationEvents ADD COLUMN deleted_at TIMESTAMP DEFAULT NULL')
        if 'is_archived' not in existing_columns:
            cursor.execute('ALTER TABLE NotificationEvents ADD COLUMN is_archived INTEGER DEFAULT 0')
        if 'archived_at' not in existing_columns:
            cursor.execute('ALTER TABLE NotificationEvents ADD COLUMN archived_at TIMESTAMP DEFAULT NULL')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notif_events_user ON NotificationEvents(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notif_events_actor ON NotificationEvents(actor_user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notif_events_channel ON NotificationEvents(channel)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notif_events_read ON NotificationEvents(is_read)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notif_events_deleted ON NotificationEvents(is_deleted)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_notif_events_archived ON NotificationEvents(is_archived)')
        conn.commit()
    except Exception as exc:
        logging.warning(f"NotificationEvents schema check failed: {exc}")
    finally:
        conn.close()


def ensure_event_announcements_schema():
    """Ensure event announcement tables exist for event creation and delivery tracking."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS EventAnnouncements (
                event_id INTEGER PRIMARY KEY,
                event_uuid TEXT DEFAULT NULL,
                meeting_id INTEGER DEFAULT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT NULL,
                meeting_date TEXT DEFAULT NULL,
                start_time TEXT DEFAULT NULL,
                end_time TEXT DEFAULT NULL,
                location TEXT DEFAULT NULL,
                meeting_link TEXT DEFAULT NULL,
                link_provider TEXT DEFAULT NULL,
                link_room_id TEXT DEFAULT NULL,
                ai_summary TEXT DEFAULT NULL,
                ai_details_json TEXT DEFAULT NULL,
                audience_roles_json TEXT DEFAULT NULL,
                only_email_opt_in INTEGER DEFAULT 1,
                template_name TEXT DEFAULT 'meeting_notice',
                reminder_24h INTEGER DEFAULT 1,
                reminder_day_of INTEGER DEFAULT 1,
                reminder_post INTEGER DEFAULT 0,
                scheduled_send_at TIMESTAMP DEFAULT NULL,
                status TEXT DEFAULT 'draft',
                is_deleted INTEGER DEFAULT 0,
                deleted_at TIMESTAMP DEFAULT NULL,
                deleted_by INTEGER DEFAULT NULL,
                created_by INTEGER DEFAULT NULL,
                updated_by INTEGER DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_at TIMESTAMP DEFAULT NULL,
                reminder_config_json TEXT DEFAULT NULL,
                FOREIGN KEY (created_by) REFERENCES Users(user_id),
                FOREIGN KEY (updated_by) REFERENCES Users(user_id),
                FOREIGN KEY (deleted_by) REFERENCES Users(user_id),
                FOREIGN KEY (meeting_id) REFERENCES Meetings(meeting_id)
            )
        ''')
        cursor.execute('PRAGMA table_info(EventAnnouncements)')
        existing_columns = {row[1] for row in cursor.fetchall()}
        required_columns = {
            'event_uuid': 'TEXT DEFAULT NULL',
            'meeting_id': 'INTEGER DEFAULT NULL',
            'link_provider': 'TEXT DEFAULT NULL',
            'link_room_id': 'TEXT DEFAULT NULL',
            'template_name': "TEXT DEFAULT 'meeting_notice'",
            'reminder_24h': 'INTEGER DEFAULT 1',
            'reminder_day_of': 'INTEGER DEFAULT 1',
            'reminder_post': 'INTEGER DEFAULT 0',
            'scheduled_send_at': 'TIMESTAMP DEFAULT NULL',
            'is_deleted': 'INTEGER DEFAULT 0',
            'deleted_at': 'TIMESTAMP DEFAULT NULL',
            'deleted_by': 'INTEGER DEFAULT NULL',
            'reminder_config_json': 'TEXT DEFAULT NULL',
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                cursor.execute(f'ALTER TABLE EventAnnouncements ADD COLUMN {column_name} {column_type}')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS EventReminderJobs (
                job_id INTEGER PRIMARY KEY,
                event_id INTEGER NOT NULL,
                job_type TEXT NOT NULL,
                scheduled_for TIMESTAMP NOT NULL,
                status TEXT DEFAULT 'queued',
                attempt_count INTEGER DEFAULT 0,
                last_error TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_at TIMESTAMP DEFAULT NULL,
                FOREIGN KEY (event_id) REFERENCES EventAnnouncements(event_id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS EventAnnouncementDeliveries (
                delivery_id INTEGER PRIMARY KEY,
                event_id INTEGER NOT NULL,
                user_id INTEGER DEFAULT NULL,
                recipient_email TEXT DEFAULT NULL,
                recipient_role TEXT DEFAULT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                error_message TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_at TIMESTAMP DEFAULT NULL,
                FOREIGN KEY (event_id) REFERENCES EventAnnouncements(event_id),
                FOREIGN KEY (user_id) REFERENCES Users(user_id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_event_announcements_status ON EventAnnouncements(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_event_announcements_schedule ON EventAnnouncements(scheduled_send_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_event_announcements_created_by ON EventAnnouncements(created_by)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_event_announcements_deleted ON EventAnnouncements(is_deleted)')
        cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_event_announcements_uuid ON EventAnnouncements(event_uuid)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_event_deliveries_event ON EventAnnouncementDeliveries(event_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_event_deliveries_status ON EventAnnouncementDeliveries(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_event_reminder_jobs_due ON EventReminderJobs(status, scheduled_for)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_event_reminder_jobs_event ON EventReminderJobs(event_id)')
        conn.commit()
    except Exception as exc:
        logging.warning(f"EventAnnouncements schema check failed: {exc}")
    finally:
        conn.close()


def transcripts_table_exists():
    """Return True if Transcripts table is present in current DB."""
    try:
        result = execute_safe_query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='Transcripts' LIMIT 1"
        )
        return bool(result)
    except Exception:
        return False


ensure_audit_logs_schema()
ensure_users_schema()
ensure_transcripts_schema()
ensure_meetings_schema()
ensure_document_classifications_schema()
ensure_summaries_schema()
ensure_segment_analysis_uniqueness_schema()
ensure_notification_subscriptions_schema()
ensure_notification_events_schema()
ensure_event_announcements_schema()
ensure_report_schedules_schema()


def _identity_user_id():
    identity = get_jwt_identity()
    return int(identity) if isinstance(identity, (str, int)) else int(identity['user_id'])


def _coerce_bool(value, field_name):
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise ValueError(f'{field_name} must be a boolean')


def _get_user_row(user_id):
    result = execute_safe_query(
        '''
        SELECT user_id, username, email, role, is_deleted, push_notifications_enabled, email_alerts_enabled, push_permission
        FROM Users
        WHERE user_id = ?
        ''',
        (user_id,),
    )
    return result[0] if result else None


def _is_super_admin_row(user_row):
    """Return True if user_row represents a non-deleted super_admin."""
    return bool(user_row) and not bool(user_row.get('is_deleted')) and user_row.get('role') == 'super_admin'


def _is_admin_or_super_admin_row(user_row):
    """Return True if user_row represents a non-deleted admin or super_admin."""
    return bool(user_row) and not bool(user_row.get('is_deleted')) and user_row.get('role') in {'admin', 'super_admin'}


def _notification_scope_clause(user_id, scope):
    """Return (where_clause, params) restricting NotificationEvents to the given scope."""
    if scope == 'all':
        return '1=1', ()
    return 'user_id = ?', (user_id,)


def _resolve_notification_scope(user_row, requested_scope, default_scope='mine'):
    """Validate and resolve the notification scope for a request.
    Returns the resolved scope string, or None if the request is forbidden.
    """
    requested = str(requested_scope or '').strip().lower() or default_scope
    if requested == 'all':
        if not _is_super_admin_row(user_row):
            return None  # forbidden
        return 'all'
    return 'mine'


def _fetch_notification_counts(user_id, scope='mine'):
    """Return a dict of notification counts for the given user/scope."""
    scope_where, scope_params = _notification_scope_clause(user_id, scope)
    try:
        base = f'FROM NotificationEvents WHERE {scope_where}'
        rows = execute_safe_query(
            f'''
            SELECT
                SUM(CASE WHEN COALESCE(is_deleted, 0) = 0 THEN 1 ELSE 0 END) AS total,
                SUM(CASE WHEN COALESCE(is_deleted, 0) = 0 AND is_read = 0 THEN 1 ELSE 0 END) AS unread,
                SUM(CASE WHEN COALESCE(is_deleted, 0) = 0 AND is_read = 1 THEN 1 ELSE 0 END) AS read,
                SUM(CASE WHEN COALESCE(is_deleted, 0) = 0 AND is_archived = 1 THEN 1 ELSE 0 END) AS archived,
                SUM(CASE WHEN COALESCE(is_deleted, 0) = 1 THEN 1 ELSE 0 END) AS deleted,
                SUM(CASE WHEN COALESCE(is_deleted, 0) = 0 AND direction = "received" THEN 1 ELSE 0 END) AS received,
                SUM(CASE WHEN COALESCE(is_deleted, 0) = 0 AND direction = "sent" THEN 1 ELSE 0 END) AS sent,
                SUM(CASE WHEN COALESCE(is_deleted, 0) = 0 AND channel = "email" THEN 1 ELSE 0 END) AS email,
                SUM(CASE WHEN COALESCE(is_deleted, 0) = 0 AND channel = "push" THEN 1 ELSE 0 END) AS push
            {base}
            ''',
            scope_params
        )
        row = rows[0] if rows else {}
        return {
            'total': int(row.get('total') or 0),
            'unread': int(row.get('unread') or 0),
            'read': int(row.get('read') or 0),
            'archived': int(row.get('archived') or 0),
            'deleted': int(row.get('deleted') or 0),
            'received': int(row.get('received') or 0),
            'sent': int(row.get('sent') or 0),
            'email': int(row.get('email') or 0),
            'push': int(row.get('push') or 0),
        }
    except Exception as exc:
        logging.warning(f'_fetch_notification_counts error: {exc}')
        return {
            'total': 0,
            'unread': 0,
            'read': 0,
            'archived': 0,
            'deleted': 0,
            'received': 0,
            'sent': 0,
            'email': 0,
            'push': 0,
        }


def _user_can_manage_system_notifications(user_row):
    return bool(user_row) and not bool(user_row.get('is_deleted')) and user_row.get('role') in {'admin', 'super_admin'}


def _resolve_notification_target_for_actor(notification_id, user_id, actor_row):
    """Resolve the target notification and validate actor permissions.
    
    Returns:
        tuple: (target_row, error_response) - target_row is the notification dict if found, 
              error_response is a Flask response tuple (json, status_code) if unauthorized or not found
    """
    # Fetch the notification
    rows = execute_safe_query(
        'SELECT * FROM NotificationEvents WHERE notification_id = ? LIMIT 1',
        (notification_id,)
    )
    if not rows:
        return (None, (jsonify({'error': 'Notification not found'}), 404))
    
    target = rows[0]
    
    # Check permissions: actors can only modify their own notifications unless they are super_admin
    if _is_super_admin_row(actor_row):
        # Super admins can access all notifications
        return (target, None)
    
    # Regular users can only access their own notifications
    target_user_id = target.get('user_id')
    if target_user_id != user_id:
        return (None, (jsonify({'error': 'Unauthorized to access this notification'}), 403))
    
    return (target, None)


def _log_super_admin_notification_action(actor_row, action, notification_id=None, target_user_id=None, extra_details=None):
    """Log super admin actions on notifications to AuditLogs for audit trail.
    
    Args:
        actor_row: The admin/super_admin user performing the action
        action: The action being performed (e.g., 'notification_marked_read', 'notification_deleted')
        notification_id: The notification ID being acted on
        target_user_id: The user who owns the notification
        extra_details: Additional details to log
    """
    if not _is_super_admin_row(actor_row):
        return  # Only log for super admin actions
    
    try:
        ip_address = get_client_ip()
        user_agent = request.headers.get('User-Agent', 'Unknown')
        
        details = {
            'action': action,
            'notification_id': notification_id,
            'target_user_id': target_user_id,
        }
        if extra_details:
            details.update(extra_details)
        
        execute_safe_query(
            '''INSERT INTO AuditLogs (user_id, username, action, details, ip_address, user_agent, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (
                actor_row.get('user_id'),
                actor_row.get('username'),
                action,
                json.dumps(details),
                ip_address,
                user_agent,
                datetime.now(timezone.utc).isoformat()
            ),
            fetch=False
        )
    except Exception as exc:
        logging.warning(f"Failed to log super admin notification action: {exc}")


EVENT_ALLOWED_AUDIENCE_ROLES = {'viewer', 'editor', 'admin', 'super_admin'}
EVENT_SCHEDULER_STARTED = False
EVENT_SCHEDULER_LOCK = threading.Lock()
EVENT_SCHEDULER_INTERVAL_SECONDS = max(10, int(os.getenv('EVENT_SCHEDULER_INTERVAL_SECONDS', '30')))
EVENT_BATCH_SIZE = max(10, int(os.getenv('EVENT_BATCH_SIZE', '50')))
EVENT_BATCH_DELAY_SECONDS = max(0, float(os.getenv('EVENT_BATCH_DELAY_SECONDS', '0.25')))
EVENT_ALLOWED_LINK_HOSTS = [host.strip().lower() for host in str(os.getenv('EVENT_ALLOWED_LINK_HOSTS', '')).split(',') if host.strip()]


def _user_can_manage_events(user_row):
    return bool(user_row) and not bool(user_row.get('is_deleted')) and user_row.get('role') in {'admin', 'super_admin'}


def _is_valid_http_link(url_value):
    if not url_value:
        return True
    try:
        parsed = urlparse(url_value)
        return parsed.scheme in {'http', 'https'} and bool(parsed.netloc)
    except Exception:
        return False


def _extract_meeting_link_metadata(url_value):
    text = str(url_value or '').strip()
    if not text:
        return {'provider': None, 'room_id': None}
    try:
        parsed = urlparse(text)
        host = (parsed.netloc or '').lower()
        path = (parsed.path or '').strip('/')
        provider = 'custom'
        room_id = None
        if 'zoom.us' in host:
            provider = 'zoom'
            match = re.search(r'/j/([A-Za-z0-9]+)', parsed.path or '')
            room_id = match.group(1) if match else None
        elif 'teams.microsoft.com' in host:
            provider = 'teams'
            room_id = path.split('/')[-1] if path else None
        elif 'meet.google.com' in host:
            provider = 'google_meet'
            room_id = path.split('/')[-1] if path else None
        return {'provider': provider, 'room_id': room_id}
    except Exception:
        return {'provider': 'custom', 'room_id': None}


def _is_allowed_meeting_link(url_value):
    text = str(url_value or '').strip()
    if not text:
        return True
    if not EVENT_ALLOWED_LINK_HOSTS:
        return True
    try:
        host = (urlparse(text).netloc or '').lower()
    except Exception:
        return False
    if not host:
        return False
    return any(host == allowed or host.endswith(f'.{allowed}') for allowed in EVENT_ALLOWED_LINK_HOSTS)


def _normalize_event_datetime(value, field_name):
    text = str(value or '').strip()
    if not text:
        return None
    try:
        normalized_text = text.replace('Z', '+00:00')
        parsed = datetime.fromisoformat(normalized_text)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as exc:
        raise ValueError(f'{field_name} must be a valid date/time') from exc


def _normalize_event_roles(raw_roles):
    if raw_roles is None:
        return sorted(EVENT_ALLOWED_AUDIENCE_ROLES)
    if not isinstance(raw_roles, list):
        raise ValueError('audienceRoles must be an array')

    normalized = []
    for role in raw_roles:
        value = str(role or '').strip().lower()
        if not value:
            continue
        if value not in EVENT_ALLOWED_AUDIENCE_ROLES:
            raise ValueError(f'Unsupported role in audienceRoles: {value}')
        if value not in normalized:
            normalized.append(value)

    if not normalized:
        raise ValueError('Select at least one audience role')
    return normalized


def _normalize_event_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError('Request body must be a JSON object')

    title = str(payload.get('title') or '').strip()
    if not title:
        raise ValueError('title is required')

    description = str(payload.get('description') or '').strip()
    meeting_date = str(payload.get('meetingDate') or '').strip()
    start_time = str(payload.get('startTime') or '').strip()
    end_time = str(payload.get('endTime') or '').strip()
    location = str(payload.get('location') or '').strip()
    meeting_link = str(payload.get('meetingLink') or '').strip()
    ai_summary = str(payload.get('aiSummary') or '').strip()
    ai_details = payload.get('aiDetails') if isinstance(payload.get('aiDetails'), (dict, list)) else None
    only_email_opt_in = bool(payload.get('onlyEmailOptIn', True))
    template_name = str(payload.get('templateName') or 'meeting_notice').strip().lower()
    meeting_id = payload.get('meetingId')
    reminder_24h = bool(payload.get('reminder24h', True))
    reminder_day_of = bool(payload.get('reminderDayOf', True))
    reminder_post = bool(payload.get('reminderPost', False))
    scheduled_send_at = _normalize_event_datetime(payload.get('scheduledSendAt'), 'scheduledSendAt')

    if meeting_link and not _is_valid_http_link(meeting_link):
        raise ValueError('meetingLink must be a valid http(s) URL')
    if meeting_link and not _is_allowed_meeting_link(meeting_link):
        raise ValueError('meetingLink host is not in the allowed domain list')

    if template_name not in {'meeting_notice', 'agenda_reminder', 'post_meeting_summary'}:
        raise ValueError('templateName is not supported')

    if meeting_id not in (None, ''):
        try:
            meeting_id = int(meeting_id)
        except Exception as exc:
            raise ValueError('meetingId must be a number') from exc
    else:
        meeting_id = None

    if scheduled_send_at:
        scheduled_dt = datetime.strptime(scheduled_send_at, '%Y-%m-%d %H:%M:%S')
        if scheduled_dt <= datetime.now():
            raise ValueError('scheduledSendAt must be in the future')

    audience_roles = _normalize_event_roles(payload.get('audienceRoles'))
    link_meta = _extract_meeting_link_metadata(meeting_link)
    reminder_config = {
        'reminder24h': reminder_24h,
        'reminderDayOf': reminder_day_of,
        'reminderPost': reminder_post,
    }

    return {
        'title': title,
        'meeting_id': meeting_id,
        'description': description or None,
        'meeting_date': meeting_date or None,
        'start_time': start_time or None,
        'end_time': end_time or None,
        'location': location or None,
        'meeting_link': meeting_link or None,
        'link_provider': link_meta.get('provider'),
        'link_room_id': link_meta.get('room_id'),
        'ai_summary': ai_summary or None,
        'ai_details_json': json.dumps(ai_details) if ai_details is not None else None,
        'audience_roles': audience_roles,
        'audience_roles_json': json.dumps(audience_roles),
        'only_email_opt_in': 1 if only_email_opt_in else 0,
        'template_name': template_name,
        'reminder_24h': 1 if reminder_24h else 0,
        'reminder_day_of': 1 if reminder_day_of else 0,
        'reminder_post': 1 if reminder_post else 0,
        'reminder_config_json': json.dumps(reminder_config),
        'scheduled_send_at': scheduled_send_at,
        'status': 'scheduled' if scheduled_send_at else 'draft',
    }


def _compose_event_datetime(event_row):
    meeting_date = str(event_row.get('meeting_date') or '').strip()
    start_time = str(event_row.get('start_time') or '').strip()
    if not meeting_date:
        return None
    if not start_time:
        start_time = '09:00'
    try:
        return datetime.strptime(f'{meeting_date} {start_time}', '%Y-%m-%d %H:%M')
    except Exception:
        try:
            return datetime.strptime(f'{meeting_date} {start_time}', '%Y-%m-%d %H:%M:%S')
        except Exception:
            return None


def _build_event_ics(event_row):
    dt_start = _compose_event_datetime(event_row)
    if not dt_start:
        return None
    dt_end = dt_start + timedelta(minutes=60)
    try:
        end_time = str(event_row.get('end_time') or '').strip()
        if end_time:
            dt_end = datetime.strptime(f"{event_row.get('meeting_date')} {end_time}", '%Y-%m-%d %H:%M')
    except Exception:
        pass

    uid = f"event-{event_row.get('event_uuid') or event_row.get('event_id')}@boardminutes.local"
    now_utc = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    dt_start_utc = dt_start.strftime('%Y%m%dT%H%M%SZ')
    dt_end_utc = dt_end.strftime('%Y%m%dT%H%M%SZ')
    title = str(event_row.get('title') or 'Meeting Event').replace('\n', ' ')
    description = str(event_row.get('description') or '').replace('\n', '\\n')
    location = str(event_row.get('location') or '').replace('\n', ' ')
    link = str(event_row.get('meeting_link') or '').strip()
    if link:
        description = f"{description}\\nJoin Link: {link}".strip()

    ics = "\r\n".join([
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//Board Minutes Analyser//Event Hub//EN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        'BEGIN:VEVENT',
        f'UID:{uid}',
        f'DTSTAMP:{now_utc}',
        f'DTSTART:{dt_start_utc}',
        f'DTEND:{dt_end_utc}',
        f'SUMMARY:{title}',
        f'DESCRIPTION:{description}',
        f'LOCATION:{location}',
        'BEGIN:VALARM',
        'TRIGGER:-PT30M',
        'ACTION:DISPLAY',
        'DESCRIPTION:Meeting reminder',
        'END:VALARM',
        'END:VEVENT',
        'END:VCALENDAR',
        '',
    ])
    return ics


def _upsert_event_reminder_jobs(event_row):
    event_id = event_row.get('event_id')
    if not event_id:
        return

    execute_safe_query(
        "DELETE FROM EventReminderJobs WHERE event_id = ? AND status IN ('queued', 'processing')",
        (event_id,),
        fetch=False,
    )

    event_dt = _compose_event_datetime(event_row)
    if not event_dt:
        return

    now_dt = datetime.now()
    jobs = []
    if int(event_row.get('reminder_24h') or 0) == 1:
        jobs.append(('pre_24h', event_dt - timedelta(hours=24)))
    if int(event_row.get('reminder_day_of') or 0) == 1:
        jobs.append(('day_of', event_dt.replace(hour=8, minute=0, second=0, microsecond=0)))
    if int(event_row.get('reminder_post') or 0) == 1:
        jobs.append(('post_summary', event_dt + timedelta(hours=2)))

    for job_type, scheduled_for in jobs:
        if scheduled_for <= now_dt:
            continue
        execute_safe_query(
            '''
            INSERT INTO EventReminderJobs (event_id, job_type, scheduled_for, status, attempt_count, created_at, updated_at)
            VALUES (?, ?, ?, 'queued', 0, ?, ?)
            ''',
            (
                event_id,
                job_type,
                scheduled_for.strftime('%Y-%m-%d %H:%M:%S'),
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat(),
            ),
            fetch=False,
        )


def _get_event_announcement(event_id):
    rows = execute_safe_query(
        '''
        SELECT *
        FROM EventAnnouncements
        WHERE event_id = ? AND COALESCE(is_deleted, 0) = 0
        LIMIT 1
        ''',
        (event_id,),
    )
    return rows[0] if rows else None


def _resolve_event_recipients(audience_roles, only_email_opt_in):
    if not audience_roles:
        return []

    placeholders = ','.join(['?'] * len(audience_roles))
    query = f'''
        SELECT user_id, username, email, role, email_alerts_enabled
        FROM Users
        WHERE COALESCE(is_deleted, 0) = 0
          AND role IN ({placeholders})
          AND email IS NOT NULL
          AND TRIM(email) <> ''
    '''
    params = list(audience_roles)
    if only_email_opt_in:
        query += ' AND COALESCE(email_alerts_enabled, 0) = 1'

    rows = execute_safe_query(query, tuple(params))
    return rows or []


def _build_event_email_content(event_row, recipient_username, recipient_role=None, job_type='initial'):
    date_text = event_row.get('meeting_date') or 'TBA'
    time_text = ' - '.join([part for part in [event_row.get('start_time'), event_row.get('end_time')] if part]) or 'TBA'
    location_text = event_row.get('location') or 'TBA'
    link_text = event_row.get('meeting_link') or ''
    description_text = event_row.get('description') or 'No additional description was provided.'
    ai_summary = event_row.get('ai_summary') or ''

    safe_description = html_utils.escape(description_text)
    safe_location = html_utils.escape(location_text)
    safe_date = html_utils.escape(date_text)
    safe_time = html_utils.escape(time_text)
    safe_ai_summary = html_utils.escape(ai_summary)

    link_section = ''
    action_html = ''
    action_text = ''
    if link_text:
        safe_link = html_utils.escape(link_text, quote=True)
        link_section = (
            '<p style="margin:0 0 12px;font-size:14px;line-height:1.6;color:#334155;">'
            f'<strong>Meeting Link:</strong> <a href="{safe_link}" target="_blank" rel="noopener noreferrer">{safe_link}</a>'
            '</p>'
        )
        action_html = generate_button(link_text, 'Join Meeting')
        action_text = f'Join Meeting: {link_text}'

    body_html = (
        '<div style="margin:14px 0;padding:16px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;">'
        f'<p style="margin:0 0 10px;font-size:14px;line-height:1.6;color:#334155;"><strong>Date:</strong> {safe_date}</p>'
        f'<p style="margin:0 0 10px;font-size:14px;line-height:1.6;color:#334155;"><strong>Time:</strong> {safe_time}</p>'
        f'<p style="margin:0 0 10px;font-size:14px;line-height:1.6;color:#334155;"><strong>Location:</strong> {safe_location}</p>'
        f'{link_section}'
        '</div>'
        f'<p style="margin:0 0 12px;font-size:14px;line-height:1.7;color:#334155;">{safe_description}</p>'
    )

    note_html = ''
    if ai_summary:
        note_html = (
            '<p style="margin:12px 0 0;padding:12px 14px;background:#f0fdf4;border:1px solid #dcfce7;border-radius:8px;font-size:14px;line-height:1.6;color:#15803d;">'
            f'<strong>AI Suggested Summary:</strong> {safe_ai_summary}'
            '</p>'
        )

    title = event_row.get('title') or 'Meeting Event'
    role_label = str(recipient_role or 'member').replace('_', ' ').title()
    intro_map = {
        'initial': f'A new meeting event has been scheduled for your role group ({role_label}).',
        'pre_24h': f'Reminder: this meeting starts in about 24 hours for your {role_label} group.',
        'day_of': f'Reminder: this meeting is happening today for your {role_label} group.',
        'post_summary': f'Post-meeting follow-up for your {role_label} group.',
    }
    template_name = str(event_row.get('template_name') or '').strip().lower()
    if template_name == 'agenda_reminder' and job_type in {'initial', 'pre_24h', 'day_of'}:
        intro_map[job_type] = f'Agenda reminder for your {role_label} group.'
    if template_name == 'post_meeting_summary' or job_type == 'post_summary':
        intro_map['post_summary'] = f'Here is the post-meeting summary for your {role_label} group.'

    conditional_role_note = ''
    if str(recipient_role or '').lower() in {'admin', 'super_admin'}:
        conditional_role_note = (
            '<p style="margin:12px 0 0;padding:10px 12px;background:#fffbeb;border:1px solid #fef3c7;border-radius:8px;font-size:13px;color:#b45309;">'
            '<strong>Admin prep:</strong> Please review attendance controls, approvals, and final agenda ordering before start.'
            '</p>'
        )
    elif str(recipient_role or '').lower() == 'editor':
        conditional_role_note = (
            '<p style="margin:12px 0 0;padding:10px 12px;background:#f0f9ff;border:1px solid #e0f2fe;border-radius:8px;font-size:13px;color:#0369a1;">'
            '<strong>Editor prep:</strong> Please confirm minutes templates and note capture sections are ready.'
            '</p>'
        )

    body_html = body_html + conditional_role_note
    html_content, text_content = render_email_template(
        username=recipient_username,
        title=f'Meeting Notice: {title}',
        intro=intro_map.get(job_type, intro_map['initial']),
        body_html=body_html,
        action_html=action_html,
        note_html=note_html,
        action_text=action_text,
    )
    return html_content, text_content


def _dispatch_event_announcement(event_row, actor_row=None, clear_existing_deliveries=True, source_label='event_hub', job_type='initial'):
    try:
        audience_roles = json.loads(event_row.get('audience_roles_json') or '[]')
    except Exception:
        audience_roles = []

    recipients = _resolve_event_recipients(audience_roles, bool(event_row.get('only_email_opt_in', 1)))
    if clear_existing_deliveries:
        execute_safe_query('DELETE FROM EventAnnouncementDeliveries WHERE event_id = ?', (event_row.get('event_id'),), fetch=False)

    if not recipients:
        execute_safe_query(
            'UPDATE EventAnnouncements SET status = ?, updated_at = ? WHERE event_id = ?',
            ('failed', datetime.now(timezone.utc).isoformat(), event_row.get('event_id')),
            fetch=False,
        )
        return {'sent': 0, 'failed': 0, 'total': 0, 'recipients': 0}

    now_iso = datetime.now(timezone.utc).isoformat()
    actor_user_id = actor_row.get('user_id') if actor_row else None
    execute_safe_query(
        'UPDATE EventAnnouncements SET status = ?, updated_by = ?, updated_at = ? WHERE event_id = ?',
        ('sending', actor_user_id, now_iso, event_row.get('event_id')),
        fetch=False,
    )

    sent = 0
    failed = 0
    ics_content = _build_event_ics(event_row)
    for index, recipient in enumerate(recipients):
        html_content, text_content = _build_event_email_content(
            event_row,
            recipient.get('username') or 'User',
            recipient.get('role'),
            job_type=job_type,
        )
        subject = f"Meeting Event: {event_row.get('title') or 'Event'}"
        ok = send_email(
            recipient.get('email'),
            subject,
            html_content,
            text_content,
            attachments=[
                {
                    'filename': f"event-{event_row.get('event_id')}.ics",
                    'content': ics_content,
                    'mimetype': 'text/calendar',
                }
            ] if ics_content else None,
            notification_event={
                'user_id': recipient.get('user_id'),
                'actor_user_id': actor_user_id,
                'actor_username': actor_row.get('username', 'scheduler') if actor_row else 'scheduler',
                'notification_type': 'event_announcement',
                'title': subject,
                'body': event_row.get('description') or 'A meeting event was announced.',
                'source': source_label,
                'reference_id': str(event_row.get('event_id')),
                'metadata': {
                    'event_id': event_row.get('event_id'),
                    'meeting_date': event_row.get('meeting_date'),
                    'start_time': event_row.get('start_time'),
                    'end_time': event_row.get('end_time'),
                    'location': event_row.get('location'),
                    'scheduled_send_at': event_row.get('scheduled_send_at'),
                    'job_type': job_type,
                },
            },
        )

        execute_safe_query(
            '''
            INSERT INTO EventAnnouncementDeliveries (
                event_id, user_id, recipient_email, recipient_role, status, error_message, sent_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                event_row.get('event_id'),
                recipient.get('user_id'),
                recipient.get('email'),
                recipient.get('role'),
                'sent' if ok else 'failed',
                None if ok else 'Email delivery failed. Check SMTP settings.',
                datetime.now(timezone.utc).isoformat() if ok else None,
                datetime.now(timezone.utc).isoformat(),
            ),
            fetch=False,
        )
        if ok:
            sent += 1
        else:
            failed += 1
        if index > 0 and index % EVENT_BATCH_SIZE == 0:
            time.sleep(EVENT_BATCH_DELAY_SECONDS)

    final_status = 'sent' if failed == 0 else ('partial' if sent > 0 else 'failed')
    execute_safe_query(
        '''
        UPDATE EventAnnouncements
        SET status = ?,
            sent_at = ?,
            updated_by = ?,
            updated_at = ?
        WHERE event_id = ?
        ''',
        (
            final_status,
            datetime.now(timezone.utc).isoformat() if sent > 0 else None,
            actor_user_id,
            datetime.now(timezone.utc).isoformat(),
            event_row.get('event_id'),
        ),
        fetch=False,
    )
    return {'sent': sent, 'failed': failed, 'total': len(recipients), 'recipients': len(recipients)}


def _dispatch_due_event_announcements():
    due_rows = execute_safe_query(
        '''
        SELECT *
        FROM EventAnnouncements
        WHERE COALESCE(is_deleted, 0) = 0
          AND status = 'scheduled'
          AND scheduled_send_at IS NOT NULL
          AND datetime(scheduled_send_at) <= datetime('now')
        ORDER BY scheduled_send_at ASC
        LIMIT 25
        '''
    )
    for row in due_rows or []:
        event_id = row.get('event_id')
        if not event_id:
            continue
        with EVENT_SCHEDULER_LOCK:
            lock_row = execute_safe_query(
                'SELECT status FROM EventAnnouncements WHERE event_id = ? LIMIT 1',
                (event_id,),
            )
            if not lock_row or lock_row[0].get('status') != 'scheduled':
                continue
            execute_safe_query(
                'UPDATE EventAnnouncements SET status = ?, updated_at = ? WHERE event_id = ? AND status = ?',
                ('sending', datetime.now(timezone.utc).isoformat(), event_id, 'scheduled'),
                fetch=False,
            )
        current_row = _get_event_announcement(event_id)
        if current_row:
            _dispatch_event_announcement(current_row, actor_row=None, clear_existing_deliveries=True, source_label='event_scheduler')


def _dispatch_due_event_reminder_jobs():
    jobs = execute_safe_query(
        '''
        SELECT job_id, event_id, job_type, scheduled_for, status, attempt_count
        FROM EventReminderJobs
        WHERE status = 'queued'
          AND datetime(scheduled_for) <= datetime('now')
        ORDER BY scheduled_for ASC
        LIMIT 50
        '''
    )
    for job in jobs or []:
        job_id = job.get('job_id')
        event_id = job.get('event_id')
        if not job_id or not event_id:
            continue

        with EVENT_SCHEDULER_LOCK:
            execute_safe_query(
                '''
                UPDATE EventReminderJobs
                SET status = 'processing', updated_at = ?
                WHERE job_id = ? AND status = 'queued'
                ''',
                (datetime.now(timezone.utc).isoformat(), job_id),
                fetch=False,
            )

        event_row = _get_event_announcement(event_id)
        if not event_row:
            execute_safe_query(
                "UPDATE EventReminderJobs SET status = 'failed', last_error = ?, updated_at = ? WHERE job_id = ?",
                ('Event not found/deleted', datetime.now(timezone.utc).isoformat(), job_id),
                fetch=False,
            )
            continue

        result = _dispatch_event_announcement(
            event_row,
            actor_row=None,
            clear_existing_deliveries=False,
            source_label='event_reminder',
            job_type=str(job.get('job_type') or 'initial'),
        )
        if result.get('failed', 0) == 0:
            execute_safe_query(
                "UPDATE EventReminderJobs SET status = 'sent', sent_at = ?, updated_at = ? WHERE job_id = ?",
                (datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat(), job_id),
                fetch=False,
            )
        else:
            attempts = int(job.get('attempt_count') or 0) + 1
            if attempts >= 3:
                execute_safe_query(
                    "UPDATE EventReminderJobs SET status = 'failed', attempt_count = ?, last_error = ?, updated_at = ? WHERE job_id = ?",
                    (attempts, 'Reminder email delivery failed after retries', datetime.now(timezone.utc).isoformat(), job_id),
                    fetch=False,
                )
            else:
                retry_delay_minutes = [5, 30, 120][attempts - 1]
                retry_for = (datetime.now() + timedelta(minutes=retry_delay_minutes)).strftime('%Y-%m-%d %H:%M:%S')
                execute_safe_query(
                    "UPDATE EventReminderJobs SET status = 'queued', attempt_count = ?, scheduled_for = ?, updated_at = ? WHERE job_id = ?",
                    (attempts, retry_for, datetime.now(timezone.utc).isoformat(), job_id),
                    fetch=False,
                )


def _event_scheduler_loop():
    while True:
        try:
            _dispatch_due_event_announcements()
            _dispatch_due_event_reminder_jobs()
        except Exception as exc:
            logging.warning(f'Event scheduler loop error: {exc}')
        time.sleep(EVENT_SCHEDULER_INTERVAL_SECONDS)


def _start_event_scheduler_thread():
    global EVENT_SCHEDULER_STARTED
    if EVENT_SCHEDULER_STARTED:
        return
    EVENT_SCHEDULER_STARTED = True
    thread = threading.Thread(target=_event_scheduler_loop, daemon=True)
    thread.start()


def _normalize_subscription_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError('subscription payload is required')

    endpoint = str(payload.get('endpoint') or '').strip()
    keys = payload.get('keys') or {}
    p256dh_key = str(keys.get('p256dh') or '').strip()
    auth_key = str(keys.get('auth') or '').strip()
    content_encoding = str(payload.get('contentEncoding') or 'aesgcm').strip()

    if not endpoint:
        raise ValueError('subscription endpoint is required')
    if not p256dh_key or not auth_key:
        raise ValueError('subscription keys are required')

    return {
        'endpoint': endpoint,
        'p256dh_key': p256dh_key,
        'auth_key': auth_key,
        'content_encoding': content_encoding,
    }


def _dispatch_push_to_opted_users(payload, target_user_ids=None):
    if webpush is None:
        return {'sent': 0, 'failed': 0, 'deactivated': 0, 'reason': 'pywebpush not installed'}
    vapid = _get_vapid_config()
    if not vapid['configured']:
        return {'sent': 0, 'failed': 0, 'deactivated': 0, 'reason': 'VAPID keys not configured'}

    where_clause = 'WHERE ns.is_active = 1 AND u.is_deleted = 0 AND u.push_notifications_enabled = 1'
    params = []
    if target_user_ids:
        placeholders = ','.join(['?'] * len(target_user_ids))
        where_clause += f' AND u.user_id IN ({placeholders})'
        params.extend(target_user_ids)

    subscriptions = execute_safe_query(
        f'''
        SELECT ns.subscription_id, ns.endpoint, ns.p256dh_key, ns.auth_key, ns.content_encoding,
               u.user_id, u.username, u.email
        FROM NotificationSubscriptions ns
        JOIN Users u ON u.user_id = ns.user_id
        {where_clause}
        ''',
        tuple(params),
    )

    sent = 0
    failed = 0
    deactivated = 0
    for item in subscriptions:
        subscription_info = {
            'endpoint': item.get('endpoint'),
            'keys': {
                'p256dh': item.get('p256dh_key'),
                'auth': item.get('auth_key'),
            },
        }
        result = _send_web_push(subscription_info, payload)
        if result.get('ok'):
            _create_notification_event(
                user_id=item.get('user_id'),
                actor_user_id=None,
                actor_username=None,
                channel='push',
                direction='received',
                notification_type='push',
                title=payload.get('title') or 'Push Notification',
                body=payload.get('body'),
                status='sent',
                source='web_push',
                metadata=payload,
                recipient_email=item.get('email'),
                delivered_at=datetime.now(timezone.utc).isoformat(),
            )
            sent += 1
            continue

        failed += 1
        _create_notification_event(
            user_id=item.get('user_id'),
            actor_user_id=None,
            actor_username=None,
            channel='push',
            direction='received',
            notification_type='push',
            title=payload.get('title') or 'Push Notification',
            body=payload.get('body'),
            status='failed',
            source='web_push',
            metadata=payload,
            recipient_email=item.get('email'),
            failed_at=datetime.now(timezone.utc).isoformat(),
            error_message=result.get('error'),
        )
        error_text = (result.get('error') or '').lower()
        if '404' in error_text or '410' in error_text or 'unsubscribed' in error_text or 'gone' in error_text:
            execute_safe_query(
                'UPDATE NotificationSubscriptions SET is_active = 0, updated_at = ? WHERE subscription_id = ?',
                (datetime.now(timezone.utc).isoformat(), item.get('subscription_id')),
                fetch=False,
            )
            deactivated += 1

    return {'sent': sent, 'failed': failed, 'deactivated': deactivated}

# ============================================
# DASHBOARD ROUTES
# ============================================

@app.route('/api/dashboard', methods=['GET'])
# @jwt_required()  # Temporarily disabled for testing
def get_dashboard_data():
    """Get aggregated dashboard data for real-time visualization with filters & anomalies."""
    try:
        # Parse query params for filters
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        limit_themes = int(request.args.get('limit_themes', 10))
        
        where_clause = "WHERE 1=1"
        params = []
        if start_date:
            where_clause += " AND m.meeting_date >= ?"
            params.append(start_date)
        if end_date:
            where_clause += " AND m.meeting_date <= ?"
            params.append(end_date)
        
        print("Dashboard API called")  # Debug log
        # Get basic stats
        # Basic stats with filters
        total_meetings_result = execute_safe_query(f'''
            SELECT COUNT(DISTINCT m.meeting_id) as count
            FROM Meetings m
            {where_clause}
        ''', params)
        total_meetings = total_meetings_result[0]['count'] if total_meetings_result else 0
        
        total_segments_result = execute_safe_query(f'''
            SELECT COUNT(s.segment_id) as count 
            FROM Segments s 
            JOIN Meetings m ON s.meeting_id = m.meeting_id
            {where_clause}
        ''', params)
        total_segments = total_segments_result[0]['count'] if total_segments_result else 0
        
        total_action_items_result = execute_safe_query('SELECT COUNT(*) FROM ActionItems')
        total_action_items = total_action_items_result[0]['COUNT(*)'] if total_action_items_result else 0
        
        total_themes_result = execute_safe_query(f'''
            SELECT COUNT(DISTINCT COALESCE(tp.topic_name, '')) as count
            FROM Topics tp
            JOIN Meetings m ON tp.meeting_id = m.meeting_id
            {where_clause}
              AND COALESCE(tp.topic_name, '') <> ''
        ''', params)
        total_themes = total_themes_result[0]['count'] if total_themes_result else 0
        
        print(f"Total meetings: {total_meetings}")  # Debug log

        # Get theme distribution (filtered)
        theme_data = execute_safe_query(f'''
                SELECT tp.topic_name as theme_name, COUNT(tp.topic_id) as count
                FROM Topics tp
                JOIN Meetings m ON tp.meeting_id = m.meeting_id
                {where_clause}
                    AND COALESCE(tp.topic_name, '') <> ''
                GROUP BY tp.topic_name
                ORDER BY count DESC
                LIMIT ?
        ''', params + [limit_themes])

        # Get sentiment distribution (filtered)
        sentiment_data = execute_safe_query(f'''
            SELECT s.sentiment, COUNT(*) as count
            FROM Sentiments s
            JOIN Segments seg ON s.segment_id = seg.segment_id
            JOIN Meetings m ON seg.meeting_id = m.meeting_id
            {where_clause}
            GROUP BY s.sentiment
        ''', params)

        # Get monthly trends (filtered, last 6 months within range)
        monthly_trends = execute_safe_query(f'''
            SELECT
                strftime('%Y-%m', COALESCE(m.meeting_date, m.created_at)) as month,
                COUNT(DISTINCT m.meeting_id) as meetings,
                COUNT(s.segment_id) as segments
            FROM Meetings m
            LEFT JOIN Segments s ON m.meeting_id = s.meeting_id
            {where_clause} AND DATE(COALESCE(m.meeting_date, m.created_at)) >= date('now', '-6 months')
            GROUP BY strftime('%Y-%m', COALESCE(m.meeting_date, m.created_at))
            ORDER BY month
        ''', params)

        # Get recent activity (last 7 days)
        recent_activity = execute_safe_query('''
            SELECT
                DATE(m.created_at) as date,
                COUNT(DISTINCT m.meeting_id) as meetings_added,
                COUNT(s.segment_id) as segments_added
            FROM Meetings m
            LEFT JOIN Segments s ON m.meeting_id = s.meeting_id
            WHERE m.created_at >= date('now', '-7 days')
            GROUP BY DATE(m.created_at)
            ORDER BY date DESC
        ''')

        # Get action items by type
        action_items_by_type = execute_safe_query('''
            SELECT item_type, COUNT(*) as count
            FROM ActionItems
            GROUP BY item_type
        ''')

        # Get recent transcripts (voice recordings) - only if table exists
        recent_transcripts = []
        try:
            recent_transcripts = execute_safe_query('''
                SELECT transcript_id, transcript_text, sentiment, created_at
                FROM Transcripts
                WHERE created_at >= date('now', '-7 days')
                ORDER BY created_at DESC
                LIMIT 10
            ''')
        except Exception as e:
            logging.warning(f"Transcripts table not available: {e}")
            recent_transcripts = []

        # Format data for charts
        theme_chart_data = {
            'labels': [row['theme_name'] for row in theme_data],
            'datasets': [{
                'data': [row['count'] for row in theme_data],
                'backgroundColor': [
                    '#2563eb', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6',
                    '#06b6d4', '#84cc16', '#f97316', '#ec4899', '#6366f1'
                ],
                'borderWidth': 0
            }]
        }

        sentiment_chart_data = {
            'labels': [row['sentiment'] for row in sentiment_data],
            'datasets': [{
                'label': 'Sentiment Analysis',
                'data': [row['count'] for row in sentiment_data],
                'backgroundColor': [
                    '#22c55e', '#64748b', '#ef4444'
                ],
                'borderWidth': 0
            }]
        }

        # Format monthly trends
        months = []
        meetings_data = []
        segments_data = []
        for row in monthly_trends:
            months.append(row['month'])
            meetings_data.append(row['meetings'])
            segments_data.append(row['segments'])

        trends_chart_data = {
            'labels': months,
            'datasets': [
                {
                    'label': 'Meetings',
                    'data': meetings_data,
                    'borderColor': '#2563eb',
                    'backgroundColor': 'rgba(37, 99, 235, 0.1)',
                    'fill': True,
                    'tension': 0.4
                },
                {
                    'label': 'Segments',
                    'data': segments_data,
                    'borderColor': '#22c55e',
                    'backgroundColor': 'rgba(34, 197, 94, 0.1)',
                    'fill': True,
                    'tension': 0.4
                }
            ]
        }

        # Calculate richer insights + anomalies
        insights = []
        anomalies = []
        
        if total_meetings > 0:
            avg_segments_per_meeting = round(total_segments / total_meetings, 1)
            insights.append(f"Average {avg_segments_per_meeting} segments per meeting")
        
        # Anomaly: Recent activity spike
        historical_avg_meetings = execute_safe_query('''
            SELECT AVG(meetings) as avg 
            FROM (
                SELECT COUNT(DISTINCT m.meeting_id) as meetings
                FROM Meetings m 
                WHERE m.meeting_date >= date('now', '-30 days')
                GROUP BY strftime('%Y-%m-%d', m.meeting_date)
            )
        ''')[0]['avg'] or 0.0
        
        recent_7d_meetings = sum(row['meetings_added'] for row in recent_activity)
        if recent_7d_meetings > historical_avg_meetings * 1.5 * 7:
            anomalies.append({
                'type': 'activity_spike',
                'message': "Unusual activity: {} meetings in 7 days (avg {:.1f}/day)".format(recent_7d_meetings, historical_avg_meetings),
                'severity': 'high'
            })
            insights.append("🚨 Activity spike detected in last 7 days")
        
        if sentiment_data:
            total_sentiments = sum(row['count'] for row in sentiment_data)
            positive_pct = round((next((row['count'] for row in sentiment_data if row['sentiment'].lower() == 'positive'), 0) / total_sentiments) * 100, 1)
            insights.append(f"{positive_pct}% positive sentiment")
            
            # Sentiment shift anomaly
            recent_positive = execute_safe_query('''
                SELECT AVG(CASE WHEN sentiment = "positive" THEN 1.0 ELSE 0 END) as recent_pos
                FROM Sentiments s JOIN Segments seg ON s.segment_id = seg.segment_id
                JOIN Meetings m ON seg.meeting_id = m.meeting_id
                WHERE m.meeting_date >= date('now', '-14 days')
            ''')[0]['recent_pos'] or 0
            if abs(recent_positive - positive_pct/100) > 0.2:
                anomalies.append({
                    'type': 'sentiment_shift',
                    'message': f'Sentiment shift: recent {recent_positive*100:.0f}% vs overall {positive_pct}%',
                    'severity': 'medium'
                })
        
        # Rising theme
        if theme_data:
            top_theme_growth = execute_safe_query('''
                SELECT t.theme_name,
                       recent.count as recent_count,
                       overall.count as overall_count,
                       (recent.count * 1.0 / overall.count - 1) * 100 as growth_pct
                FROM Themes t
                JOIN (SELECT theme_id, COUNT(*) as count FROM Analysis 
                      JOIN Segments s ON Analysis.segment_id = s.segment_id
                      JOIN Meetings m ON s.meeting_id = m.meeting_id
                      WHERE m.meeting_date >= date('now', '-30 days')
                      GROUP BY theme_id) recent ON t.theme_id = recent.theme_id
                JOIN (SELECT theme_id, COUNT(*) as count FROM Analysis GROUP BY theme_id) overall ON t.theme_id = overall.theme_id
                ORDER BY growth_pct DESC LIMIT 1
            ''')
            if top_theme_growth:
                growth = top_theme_growth[0]
                if growth['growth_pct'] > 50:
                    anomalies.append({
                        'type': 'rising_theme',
                        'message': f"{growth['theme_name']} up {growth['growth_pct']:.0f}% in last 30 days",
                        'severity': 'low'
                    })
                    insights.append(f"📈 {growth['theme_name']} gaining traction")

        # Detect anomalies (meeting spike)
        anomalies_result = execute_safe_query('''
            SELECT 
                COUNT(DISTINCT m.meeting_id) as recent_meetings,
                AVG(historical.meetings_per_day) as avg_daily
            FROM Meetings m
            CROSS JOIN (SELECT AVG(meetings) as meetings_per_day FROM (
                SELECT COUNT(DISTINCT meeting_id) as meetings 
                FROM Meetings WHERE meeting_date >= date('now', '-30 days')
                GROUP BY strftime('%Y-%m-%d', meeting_date)
            )) historical
            WHERE m.created_at >= date('now', '-7 days')
        ''')
        if anomalies_result and anomalies_result[0]['recent_meetings'] > (anomalies_result[0]['avg_daily'] or 0) * 1.5:
            anomalies.append("📈 Meeting spike detected!")
        
        return jsonify({
            'stats': {
                'totalMeetings': total_meetings,
                'totalSegments': total_segments,
                'actionItems': total_action_items,
                'themes': total_themes
            },
            'charts': {
                'themeData': theme_chart_data,
                'sentimentData': sentiment_chart_data,
                'trendsData': trends_chart_data
            },
            'insights': insights,
            'anomalies': anomalies,
            'recentActivity': recent_activity,
            'actionItemsByType': action_items_by_type,
            'recentTranscripts': recent_transcripts,
            'filtersApplied': {
                'start_date': start_date,
                'end_date': end_date,
                'limit_themes': limit_themes
            }
        }), 200

    except Exception as e:
        logging.error(f"Dashboard data error: {e}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': 'Failed to load dashboard data'}), 500


@app.route('/api/meetings', methods=['GET'])
@jwt_required()
def list_meetings():
    """List uploaded documents as meeting records."""
    try:
        limit = max(1, min(int(request.args.get('limit', 50)), 200))
        offset = max(0, int(request.args.get('offset', 0)))

        meetings = execute_safe_query(
            '''
            SELECT
                m.meeting_id,
                COALESCE(m.source_filename, '') AS source_filename,
                m.meeting_date,
                m.created_at,
                COUNT(DISTINCT s.segment_id) AS segments_count,
                COUNT(DISTINCT sm.summary_id) AS summaries_count,
                COUNT(DISTINCT t.transcript_id) AS transcripts_count
            FROM Meetings m
            LEFT JOIN Segments s ON m.meeting_id = s.meeting_id
            LEFT JOIN Summaries sm ON s.segment_id = sm.segment_id
            LEFT JOIN Transcripts t ON m.meeting_id = t.meeting_id
            GROUP BY m.meeting_id
            ORDER BY COALESCE(m.created_at, m.meeting_date) DESC, m.meeting_id DESC
            LIMIT ? OFFSET ?
            ''',
            (limit, offset)
        )

        total_row = execute_safe_query('SELECT COUNT(*) AS total FROM Meetings')
        total = int(total_row[0].get('total', 0)) if total_row else 0

        return jsonify({
            'meetings': meetings,
            'total': total,
            'limit': limit,
            'offset': offset,
        }), 200
    except Exception as e:
        logging.error(f"List meetings error: {e}")
        return jsonify({'error': 'Failed to load uploaded documents', 'meetings': []}), 500


@app.route('/api/events', methods=['GET'])
@jwt_required()
def list_events():
    try:
        actor = _get_user_row(_identity_user_id())
        if not _user_can_manage_events(actor):
            return jsonify({'error': 'Admin access required'}), 403

        limit = max(1, min(int(request.args.get('limit', 50)), 200))
        offset = max(0, int(request.args.get('offset', 0)))

        rows = execute_safe_query(
            '''
            SELECT
                e.event_id,
                e.event_uuid,
                e.meeting_id,
                e.title,
                e.description,
                e.meeting_date,
                e.start_time,
                e.end_time,
                e.location,
                e.meeting_link,
                e.link_provider,
                e.link_room_id,
                e.ai_summary,
                e.audience_roles_json,
                e.only_email_opt_in,
                e.template_name,
                e.reminder_24h,
                e.reminder_day_of,
                e.reminder_post,
                e.scheduled_send_at,
                e.status,
                e.is_deleted,
                e.created_by,
                e.updated_by,
                e.created_at,
                e.updated_at,
                e.sent_at,
                COALESCE(SUM(CASE WHEN d.status = 'sent' THEN 1 ELSE 0 END), 0) AS sent_count,
                COALESCE(SUM(CASE WHEN d.status = 'failed' THEN 1 ELSE 0 END), 0) AS failed_count
            FROM EventAnnouncements e
            LEFT JOIN EventAnnouncementDeliveries d ON d.event_id = e.event_id
            WHERE COALESCE(e.is_deleted, 0) = 0
            GROUP BY e.event_id
            ORDER BY COALESCE(e.updated_at, e.created_at) DESC, e.event_id DESC
            LIMIT ? OFFSET ?
            ''',
            (limit, offset),
        )
        total_row = execute_safe_query('SELECT COUNT(*) AS total FROM EventAnnouncements WHERE COALESCE(is_deleted, 0) = 0')
        total = int(total_row[0].get('total', 0)) if total_row else 0

        events = []
        for row in rows or []:
            event = dict(row)
            try:
                event['audienceRoles'] = json.loads(event.get('audience_roles_json') or '[]')
            except Exception:
                event['audienceRoles'] = []
            event['onlyEmailOptIn'] = bool(event.get('only_email_opt_in'))
            event['scheduledSendAt'] = event.get('scheduled_send_at')
            event['meetingId'] = event.get('meeting_id')
            event['templateName'] = event.get('template_name')
            event['reminder24h'] = bool(event.get('reminder_24h'))
            event['reminderDayOf'] = bool(event.get('reminder_day_of'))
            event['reminderPost'] = bool(event.get('reminder_post'))
            events.append(event)

        return jsonify({'events': events, 'total': total, 'limit': limit, 'offset': offset}), 200
    except Exception as e:
        logging.error(f"List events error: {e}")
        return jsonify({'error': 'Failed to load events', 'events': []}), 500


@app.route('/api/events', methods=['POST'])
@jwt_required()
def create_event():
    try:
        actor = _get_user_row(_identity_user_id())
        if not _user_can_manage_events(actor):
            return jsonify({'error': 'Admin access required'}), 403

        data = request.get_json(silent=True) or {}
        normalized = _normalize_event_payload(data)
        now_iso = datetime.now(timezone.utc).isoformat()

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO EventAnnouncements (
                event_uuid, meeting_id, title, description, meeting_date, start_time, end_time,
                location, meeting_link, link_provider, link_room_id,
                ai_summary, ai_details_json, audience_roles_json, only_email_opt_in,
                template_name, reminder_24h, reminder_day_of, reminder_post,
                reminder_config_json, scheduled_send_at, status,
                created_by, updated_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                str(uuid.uuid4()),
                normalized['meeting_id'],
                normalized['title'],
                normalized['description'],
                normalized['meeting_date'],
                normalized['start_time'],
                normalized['end_time'],
                normalized['location'],
                normalized['meeting_link'],
                normalized['link_provider'],
                normalized['link_room_id'],
                normalized['ai_summary'],
                normalized['ai_details_json'],
                normalized['audience_roles_json'],
                normalized['only_email_opt_in'],
                normalized['template_name'],
                normalized['reminder_24h'],
                normalized['reminder_day_of'],
                normalized['reminder_post'],
                normalized['reminder_config_json'],
                normalized['scheduled_send_at'],
                normalized['status'],
                actor['user_id'],
                actor['user_id'],
                now_iso,
                now_iso,
            ),
        )
        event_id = cursor.lastrowid
        conn.commit()
        conn.close()

        created_row = _get_event_announcement(event_id)
        if created_row:
            _upsert_event_reminder_jobs(created_row)

        return jsonify({'message': 'Event saved', 'event_id': event_id}), 201
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as e:
        logging.error(f"Create event error: {e}")
        return jsonify({'error': 'Failed to save event'}), 500


@app.route('/api/events/<int:event_id>', methods=['PUT'])
@jwt_required()
def update_event(event_id):
    try:
        actor = _get_user_row(_identity_user_id())
        if not _user_can_manage_events(actor):
            return jsonify({'error': 'Admin access required'}), 403

        existing = _get_event_announcement(event_id)
        if not existing:
            return jsonify({'error': 'Event not found'}), 404

        data = request.get_json(silent=True) or {}
        normalized = _normalize_event_payload(data)
        now_iso = datetime.now(timezone.utc).isoformat()

        execute_safe_query(
            '''
            UPDATE EventAnnouncements
            SET meeting_id = ?,
                title = ?,
                description = ?,
                meeting_date = ?,
                start_time = ?,
                end_time = ?,
                location = ?,
                meeting_link = ?,
                link_provider = ?,
                link_room_id = ?,
                ai_summary = ?,
                ai_details_json = ?,
                audience_roles_json = ?,
                only_email_opt_in = ?,
                template_name = ?,
                reminder_24h = ?,
                reminder_day_of = ?,
                reminder_post = ?,
                reminder_config_json = ?,
                scheduled_send_at = ?,
                status = ?,
                updated_by = ?,
                updated_at = ?
            WHERE event_id = ? AND COALESCE(is_deleted, 0) = 0
            ''',
            (
                normalized['meeting_id'],
                normalized['title'],
                normalized['description'],
                normalized['meeting_date'],
                normalized['start_time'],
                normalized['end_time'],
                normalized['location'],
                normalized['meeting_link'],
                normalized['link_provider'],
                normalized['link_room_id'],
                normalized['ai_summary'],
                normalized['ai_details_json'],
                normalized['audience_roles_json'],
                normalized['only_email_opt_in'],
                normalized['template_name'],
                normalized['reminder_24h'],
                normalized['reminder_day_of'],
                normalized['reminder_post'],
                normalized['reminder_config_json'],
                normalized['scheduled_send_at'],
                normalized['status'],
                actor['user_id'],
                now_iso,
                event_id,
            ),
            fetch=False,
        )

        updated_row = _get_event_announcement(event_id)
        if updated_row:
            _upsert_event_reminder_jobs(updated_row)

        return jsonify({'message': 'Event updated', 'event_id': event_id}), 200
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as e:
        logging.error(f"Update event error: {e}")
        return jsonify({'error': 'Failed to update event'}), 500


@app.route('/api/events/<int:event_id>', methods=['DELETE'])
@jwt_required()
def delete_event(event_id):
    try:
        actor = _get_user_row(_identity_user_id())
        if not _user_can_manage_events(actor):
            return jsonify({'error': 'Admin access required'}), 403

        existing = _get_event_announcement(event_id)
        if not existing:
            return jsonify({'error': 'Event not found'}), 404

        now_iso = datetime.now(timezone.utc).isoformat()
        execute_safe_query(
            '''
            UPDATE EventAnnouncements
            SET is_deleted = 1,
                deleted_at = ?,
                deleted_by = ?,
                status = 'deleted',
                updated_by = ?,
                updated_at = ?
            WHERE event_id = ?
            ''',
            (now_iso, actor['user_id'], actor['user_id'], now_iso, event_id),
            fetch=False,
        )

        return jsonify({'message': 'Event deleted', 'event_id': event_id}), 200
    except Exception as e:
        logging.error(f"Delete event error: {e}")
        return jsonify({'error': 'Failed to delete event'}), 500


@app.route('/api/events/preview-recipients', methods=['POST'])
@jwt_required()
def preview_event_recipients():
    try:
        actor = _get_user_row(_identity_user_id())
        if not _user_can_manage_events(actor):
            return jsonify({'error': 'Admin access required'}), 403

        payload = request.get_json(silent=True) or {}
        audience_roles = _normalize_event_roles(payload.get('audienceRoles'))
        only_email_opt_in = bool(payload.get('onlyEmailOptIn', True))
        show_all_users = bool(payload.get('showAllUsers', False))

        # If showAllUsers is True, temporarily disable email opt-in filter to show all users
        if show_all_users:
            only_email_opt_in = False

        recipients = _resolve_event_recipients(audience_roles, only_email_opt_in)

        recipient_preview = [
            {
                'user_id': row.get('user_id'),
                'username': row.get('username'),
                'email': row.get('email'),
                'role': row.get('role'),
            }
            for row in recipients
        ]

        breakdown = {}
        for row in recipients:
            role = str(row.get('role') or '').lower()
            breakdown[role] = breakdown.get(role, 0) + 1

        return jsonify({
            'count': len(recipients),
            'roles': breakdown,
            'recipients': recipient_preview,
        }), 200
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as e:
        logging.error(f"Preview event recipients error: {e}")
        return jsonify({'error': 'Failed to preview recipients'}), 500


@app.route('/api/events/<int:event_id>/send', methods=['POST'])
@jwt_required()
def send_event_announcement(event_id):
    try:
        actor = _get_user_row(_identity_user_id())
        if not _user_can_manage_events(actor):
            return jsonify({'error': 'Admin access required'}), 403

        event_row = _get_event_announcement(event_id)
        if not event_row:
            return jsonify({'error': 'Event not found'}), 404

        result = _dispatch_event_announcement(event_row, actor_row=actor, clear_existing_deliveries=True, source_label='event_hub')

        return jsonify({
            'message': 'Event notification dispatch completed',
            'event_id': event_id,
            'email': {'sent': result['sent'], 'failed': result['failed'], 'total': result['total']},
        }), 200
    except Exception as e:
        logging.error(f"Send event announcement error: {e}")
        return jsonify({'error': 'Failed to send event notifications'}), 500


@app.route('/api/events/<int:event_id>/test-email', methods=['POST'])
@jwt_required()
def send_event_test_email(event_id):
    try:
        actor = _get_user_row(_identity_user_id())
        if not _user_can_manage_events(actor):
            return jsonify({'error': 'Admin access required'}), 403
        if not actor.get('email'):
            return jsonify({'error': 'Your account has no email address'}), 400

        event_row = _get_event_announcement(event_id)
        if not event_row:
            return jsonify({'error': 'Event not found'}), 404

        html_content, text_content = _build_event_email_content(
            event_row,
            actor.get('username') or 'Admin',
            actor.get('role'),
            job_type='initial',
        )
        ics_content = _build_event_ics(event_row)
        ok = send_email(
            actor.get('email'),
            f"[TEST] Meeting Event: {event_row.get('title') or 'Event'}",
            html_content,
            text_content,
            attachments=[
                {
                    'filename': f"event-{event_row.get('event_id')}-test.ics",
                    'content': ics_content,
                    'mimetype': 'text/calendar',
                }
            ] if ics_content else None,
            notification_event={
                'user_id': actor.get('user_id'),
                'actor_user_id': actor.get('user_id'),
                'actor_username': actor.get('username', 'unknown'),
                'notification_type': 'event_test_email',
                'title': f"[TEST] Meeting Event: {event_row.get('title') or 'Event'}",
                'body': 'Event test email preview sent.',
                'source': 'event_hub_test',
                'reference_id': str(event_id),
            },
        )
        if not ok:
            return jsonify({'error': 'Email delivery failed. Check SMTP settings.'}), 502

        return jsonify({'message': 'Test email sent successfully.'}), 200
    except Exception as e:
        logging.error(f"Send event test email error: {e}")
        return jsonify({'error': 'Failed to send test email'}), 500


@app.route('/api/events/<int:event_id>/calendar.ics', methods=['GET'])
@jwt_required()
def download_event_calendar(event_id):
    try:
        actor = _get_user_row(_identity_user_id())
        if not _user_can_manage_events(actor):
            return jsonify({'error': 'Admin access required'}), 403

        event_row = _get_event_announcement(event_id)
        if not event_row:
            return jsonify({'error': 'Event not found'}), 404
        ics_content = _build_event_ics(event_row)
        if not ics_content:
            return jsonify({'error': 'Meeting date/time is required to generate calendar file'}), 400

        response = Response(ics_content, mimetype='text/calendar; charset=utf-8')
        response.headers['Content-Disposition'] = f"attachment; filename=event-{event_id}.ics"
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Last-Modified'] = formatdate(timeval=None, localtime=False, usegmt=True)
        return response
    except Exception as e:
        logging.error(f"Download event calendar error: {e}")
        return jsonify({'error': 'Failed to generate calendar file'}), 500


# =====================================================
# REPORT SCHEDULER (Auto-generate and send reports)
# =====================================================

REPORT_SCHEDULER_STARTED = False
REPORT_SCHEDULER_LOCK = threading.Lock()
REPORT_SCHEDULER_INTERVAL_SECONDS = max(5, int(os.getenv('REPORT_SCHEDULER_INTERVAL_SECONDS', '5')))  # Default 5 seconds


def _generate_report_for_schedule(schedule_row):
    """Generate a board minutes report based on schedule filters."""
    try:
        user_id = schedule_row.get('user_id')
        filters_json = schedule_row.get('filters_json')
        
        # Parse filters
        filters = {}
        if filters_json:
            try:
                filters = json.loads(filters_json)
            except:
                filters = {}
        
        # Query board minutes (events) based on filters
        query = 'SELECT event_id, title, description, meeting_date, created_by FROM EventAnnouncements WHERE is_deleted = 0'
        params = []
        
        # Note: theme and sentiment filters are not supported on EventAnnouncements table
        # They are UI options but not stored in the event data; only stored in ReportSchedules.filters_json
        
        # Default to recent events
        query += ' ORDER BY meeting_date DESC LIMIT 50'
        
        result = execute_safe_query(query, tuple(params))
        events = result or []

        generated_at = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        summary_html = (
            '<div style="margin:14px 0 18px;padding:14px 16px;background:#eff6ff;border:1px solid #bfdbfe;'
            'border-radius:10px;font-size:14px;line-height:1.6;color:#1e3a8a;">'
            f'<strong>Generated:</strong> {html_utils.escape(generated_at)}<br/>'
            f'<strong>Total events:</strong> {len(events)}'
            '</div>'
        )

        if events:
            event_cards = []
            for event in events:
                event_cards.append(
                    '<div style="margin:0 0 14px;padding:14px 16px;background:#f8fafc;border:1px solid #d7e4f6;'
                    'border-left:4px solid #2563eb;border-radius:10px;">'
                    f'<div style="font-size:16px;font-weight:700;color:#12243a;margin-bottom:6px;">{html_utils.escape(str(event.get("title") or "Untitled"))}</div>'
                    f'<div style="font-size:13px;color:#5f7089;margin-bottom:8px;">Date: {html_utils.escape(str(event.get("meeting_date") or "N/A"))}</div>'
                    f'<div style="font-size:14px;line-height:1.7;color:#30445f;">{html_utils.escape(str(event.get("description") or "No description"))}</div>'
                    '</div>'
                )
            events_html = ''.join(event_cards)
            body_html = f'<p style="margin:0 0 12px;font-size:15px;line-height:1.7;color:#30445f;">The report below includes the latest board meeting events that matched your schedule filters.</p>{summary_html}{events_html}'
            text_lines = [
                'The report below includes the latest board meeting events that matched your schedule filters.',
                '',
                f'Generated: {generated_at}',
                f'Total events: {len(events)}',
                '',
            ]
            for event in events:
                text_lines.extend([
                    f'Title: {event.get("title", "Untitled")}',
                    f'Date: {event.get("meeting_date", "N/A")}',
                    f'Description: {event.get("description", "No description")}',
                    '',
                ])
            text_content = '\n'.join(text_lines).strip()
        else:
            body_html = (
                '<p style="margin:0 0 12px;font-size:15px;line-height:1.7;color:#30445f;">'
                'No events were found for the selected filters.'
                '</p>'
            )
            text_content = f'No events were found for the selected filters.\n\nGenerated: {generated_at}\nTotal events: 0'

        frontend_base = os.getenv('FRONTEND_URL', 'http://localhost:3000').rstrip('/')
        report_link = f"{frontend_base}/reports/scheduled/{schedule_row.get('schedule_id')}"

        html_content, _ = render_email_template(
            username='User',
            title='Board Minutes Scheduled Report',
            intro='Your scheduled board minutes report is ready.',
            body_html=body_html,
            action_url=report_link,
            action_label='View full report',
            note_html='<p style="margin:12px 0 0;padding:12px 14px;background:#f8fafc;border:1px solid #d7e4f6;border-radius:8px;font-size:14px;line-height:1.6;color:#475569;">This report was generated automatically from your saved schedule settings.</p>'
        )

        # Ensure plain-text contains a direct link to the full report
        if text_content and isinstance(text_content, str):
            text_content = text_content + f"\n\nView full report: {report_link}"

        return {
            'subject': 'Board Minutes - Scheduled Report',
            'html': html_content,
            'text': text_content,
            'event_count': len(events)
        }
    except Exception as e:
        logging.error(f"Report generation error for schedule {schedule_row.get('schedule_id')}: {e}")
        return None


def _send_scheduled_report(schedule_row, report):
    """Send a generated report via email."""
    try:
        recipient_emails = schedule_row.get('recipient_emails', '').strip().split(',')
        recipient_emails = [e.strip() for e in recipient_emails if e.strip()]
        
        if not recipient_emails:
            logging.warning(f"No recipient emails for schedule {schedule_row.get('schedule_id')}")
            db = get_db()
            now_iso = datetime.now(timezone.utc).isoformat()
            db.execute(
                '''
                UPDATE ReportSchedules
                SET last_delivery_status = ?,
                    last_delivery_error = ?,
                    last_delivery_at = ?,
                    updated_at = ?
                WHERE schedule_id = ?
                ''',
                ('failed', 'No recipient emails configured', now_iso, now_iso, schedule_row.get('schedule_id'))
            )
            db.commit()
            return False
        
        user_row = execute_safe_query('SELECT user_id, username, email FROM Users WHERE user_id = ?', (schedule_row.get('user_id'),))
        if not user_row:
            logging.warning(f"User not found for schedule {schedule_row.get('schedule_id')}")
            db = get_db()
            now_iso = datetime.now(timezone.utc).isoformat()
            db.execute(
                '''
                UPDATE ReportSchedules
                SET last_delivery_status = ?,
                    last_delivery_error = ?,
                    last_delivery_at = ?,
                    updated_at = ?
                WHERE schedule_id = ?
                ''',
                ('failed', 'Schedule owner not found', now_iso, now_iso, schedule_row.get('schedule_id'))
            )
            db.commit()
            return False
        
        user = user_row[0]
        
        # Send to each recipient
        all_sent = True
        failed_recipients = []
        for recipient in recipient_emails:
            try:
                ok = send_email(
                    recipient,
                    report['subject'],
                    report['html'],
                    text_content=report['text'],
                )
                if not ok:
                    all_sent = False
                    failed_recipients.append(recipient)
                    logging.error(f"Failed to send report to {recipient}: send_email returned False")
                else:
                    logging.info(f"Sent scheduled report to {recipient} from schedule {schedule_row.get('schedule_id')}")
            except Exception as e:
                logging.error(f"Failed to send report to {recipient}: {e}")
                all_sent = False
                failed_recipients.append(recipient)
        
        if all_sent:
            # Preserve configured delivery_date; only track delivery outcome fields.
            db = get_db()
            now_iso = datetime.now(timezone.utc).isoformat()
            db.execute(
                '''
                UPDATE ReportSchedules
                SET last_delivery_status = ?,
                    last_delivery_error = ?,
                    last_delivery_at = ?,
                    updated_at = ?
                WHERE schedule_id = ?
                ''',
                ('sent', None, now_iso, now_iso, schedule_row.get('schedule_id'))
            )
            db.commit()
        else:
            db = get_db()
            now_iso = datetime.now(timezone.utc).isoformat()
            failed_msg = 'One or more recipient deliveries failed'
            if failed_recipients:
                failed_msg = f"Failed recipients: {', '.join(failed_recipients[:5])}" + ('...' if len(failed_recipients) > 5 else '')
            db.execute(
                '''
                UPDATE ReportSchedules
                SET last_delivery_status = ?,
                    last_delivery_error = ?,
                    last_delivery_at = ?,
                    updated_at = ?
                WHERE schedule_id = ?
                ''',
                ('failed', failed_msg, now_iso, now_iso, schedule_row.get('schedule_id'))
            )
            db.commit()
        
        return all_sent
    except Exception as e:
        logging.error(f"Report sending error for schedule {schedule_row.get('schedule_id')}: {e}")
        try:
            db = get_db()
            now_iso = datetime.now(timezone.utc).isoformat()
            db.execute(
                '''
                UPDATE ReportSchedules
                SET last_delivery_status = ?,
                    last_delivery_error = ?,
                    last_delivery_at = ?,
                    updated_at = ?
                WHERE schedule_id = ?
                ''',
                ('failed', str(e), now_iso, now_iso, schedule_row.get('schedule_id'))
            )
            db.commit()
        except Exception:
            pass
        return False


def _check_and_dispatch_due_reports():
    """Check for due scheduled reports and dispatch them."""
    try:
        now = datetime.now(timezone.utc)
        today_str = now.strftime('%Y-%m-%d')
        
        # Get all enabled schedules
        schedules = execute_safe_query(
            '''SELECT schedule_id, user_id, enabled, cadence, delivery_date, delivery_time, recipient_emails, filters_json, last_delivery_status, last_delivery_error, last_delivery_at
               FROM ReportSchedules WHERE enabled = 1 AND COALESCE(is_deleted, 0) = 0''',
            ()
        )
        
        if not schedules:
            return
        
        for schedule in schedules:
            try:
                cadence = schedule.get('cadence', 'weekly').lower()
                delivery_time = schedule.get('delivery_time', '08:00')
                last_delivery = schedule.get('delivery_date')
                last_delivery_at = schedule.get('last_delivery_at')
                
                should_send = False

                # Only send once the configured time has passed.
                time_due = False
                try:
                    [sched_hour, sched_min] = delivery_time.split(':')[:2]
                    scheduled_today = now.replace(hour=int(sched_hour), minute=int(sched_min), second=0, microsecond=0)
                    time_due = now >= scheduled_today
                except:
                    time_due = False
                
                if not time_due:
                    continue  # Skip this schedule until the time has passed

                # If a delivery_date exists, treat it as the schedule start date.
                # This prevents future-dated schedules from sending too early.
                if last_delivery:
                    try:
                        delivery_start = datetime.fromisoformat(str(last_delivery))
                        if delivery_start.tzinfo is None:
                            delivery_start = delivery_start.replace(tzinfo=timezone.utc)
                    except Exception:
                        try:
                            delivery_start = datetime.strptime(str(last_delivery)[:10], '%Y-%m-%d')
                            delivery_start = delivery_start.replace(tzinfo=timezone.utc)
                        except Exception:
                            delivery_start = None
                    if delivery_start and now < delivery_start:
                        continue

                last_delivery_dt = None
                if last_delivery_at:
                    try:
                        last_delivery_dt = datetime.fromisoformat(str(last_delivery_at))
                        if last_delivery_dt.tzinfo is None:
                            last_delivery_dt = last_delivery_dt.replace(tzinfo=timezone.utc)
                    except Exception:
                        last_delivery_dt = None
                
                # Determine if report should be sent based on cadence
                if cadence == 'daily':
                    # Send daily once per day after the scheduled time.
                    should_send = (not last_delivery_dt or last_delivery_dt.strftime('%Y-%m-%d') != today_str)
                
                elif cadence == 'weekly':
                    # Send once per week after the scheduled time.
                    should_send = (not last_delivery_dt or last_delivery_dt < now - timedelta(days=7))
                
                elif cadence == 'monthly':
                    # Send once per month after the scheduled time.
                    should_send = (not last_delivery_dt or last_delivery_dt < now - timedelta(days=30))
                
                if should_send:
                    # Generate report
                    report = _generate_report_for_schedule(schedule)
                    if report:
                        # Send report
                        success = _send_scheduled_report(schedule, report)
                        if success:
                            logging.info(f"Report sent for schedule {schedule.get('schedule_id')} (cadence: {cadence})")
                        else:
                            logging.warning(f"Report send failed for schedule {schedule.get('schedule_id')} (cadence: {cadence})")
                    
            except Exception as e:
                logging.error(f"Error processing schedule {schedule.get('schedule_id')}: {e}")
                continue
    
    except Exception as e:
        logging.error(f"Report scheduler check error: {e}")


def _report_scheduler_loop():
    """Background loop for report scheduling."""
    while True:
        try:
            _check_and_dispatch_due_reports()
        except Exception as exc:
            logging.warning(f'Report scheduler loop error: {exc}')
        time.sleep(REPORT_SCHEDULER_INTERVAL_SECONDS)


def _start_report_scheduler_thread():
    """Start the background report scheduler thread."""
    global REPORT_SCHEDULER_STARTED
    if REPORT_SCHEDULER_STARTED:
        return
    REPORT_SCHEDULER_STARTED = True
    thread = threading.Thread(target=_report_scheduler_loop, daemon=True)
    thread.start()
    logging.info(f"Report scheduler started (check interval: {REPORT_SCHEDULER_INTERVAL_SECONDS}s)")


_start_event_scheduler_thread()
_start_report_scheduler_thread()

@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        username = (data.get('username') or '').strip()
        password = data.get('password') or ''
        client_metadata = data.get('client_metadata') if isinstance(data.get('client_metadata'), dict) else None
        
        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400
        
        result = execute_safe_query('SELECT * FROM Users WHERE username = ?', (username,))
        
        if not result:
            log_auth_activity(
                'failed_login',
                None,
                username or 'unknown',
                'Login failed: user not found',
                client_metadata,
                login_status='failed',
            )
            return jsonify({'error': 'Invalid credentials'}), 401
        
        user = result[0]

        if user.get('is_deleted'):
            log_auth_activity(
                'failed_login',
                user['user_id'],
                user['username'],
                'Login blocked: account is deleted',
                client_metadata,
                login_status='failed',
            )
            return jsonify({'error': 'Invalid credentials'}), 401
        
        if not check_password_hash(user['password_hash'], password):
            log_auth_activity(
                'failed_login',
                user['user_id'],
                user['username'],
                'Login failed: invalid password',
                client_metadata,
                login_status='failed',
            )
            return jsonify({'error': 'Invalid credentials'}), 401
        
        access_token = create_access_token(
            identity=str(user['user_id']),
            additional_claims={
                'username': user['username'],
                'role': user['role']
            }
        )

        try:
            execute_safe_query(
                'UPDATE Users SET last_login = ? WHERE user_id = ?',
                (datetime.now(timezone.utc).isoformat(), user['user_id']),
                fetch=False,
            )
        except Exception as exc:
            logging.warning(f"Failed to update last_login: {exc}")

        log_auth_activity(
            'login',
            user['user_id'],
            user['username'],
            'User logged in successfully',
            client_metadata,
            login_status='success',
        )
        
        return jsonify({
            'access_token': access_token,
            'must_change_password': bool(user.get('must_change_password')),
            'role': user['role'],
            'username': user['username'],
            'user_id': user['user_id']
        }), 200
    except Exception as e:
        logging.exception(f"Login error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/auth/logout', methods=['POST'])
@jwt_required()
def logout():
    """Logout current user and persist logout activity metadata."""
    try:
        data = request.get_json(silent=True) or request.form.to_dict() or {}
        client_metadata = data.get('client_metadata') if isinstance(data.get('client_metadata'), dict) else None
        identity = get_jwt_identity()
        claims = get_jwt()

        user_id = int(identity) if isinstance(identity, (str, int)) else int(identity.get('user_id'))
        username = claims.get('username', 'unknown')

        try:
            execute_safe_query(
                'UPDATE Users SET last_logout = ? WHERE user_id = ?',
                (datetime.now(timezone.utc).isoformat(), user_id),
                fetch=False,
            )
        except Exception as exc:
            logging.warning(f"Failed to update last_logout: {exc}")

        log_auth_activity(
            'logout',
            user_id,
            username,
            'User logged out successfully',
            client_metadata,
            login_status='success',
        )

        return jsonify({'message': 'Logged out successfully'}), 200
    except Exception as e:
        logging.error(f"Logout error: {e}")
        return jsonify({'error': 'Server error'}), 500

@app.route('/api/auth/me', methods=['GET'])
@jwt_required()
def get_current_user():
    try:
        identity = get_jwt_identity()
        
        # Handle both str and dict identity formats
        user_id = int(identity) if isinstance(identity, (str, int)) else int(identity['user_id'])
        
        result = execute_safe_query(
            'SELECT user_id, username, email, full_name, role, profile_image, must_change_password FROM Users WHERE user_id = ?',
            (user_id,)
        )
        if result:
            user = dict(result[0])
            user['must_change_password'] = bool(user.get('must_change_password'))
            return jsonify(user), 200
        return jsonify({'error': 'User not found'}), 404
    except Exception as e:
        logging.error(f"Get current user error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/user/settings/notifications', methods=['GET'])
@jwt_required()
def get_notification_settings():
    try:
        user_id = _identity_user_id()
        result = execute_safe_query(
            '''
            SELECT user_id, is_deleted, push_notifications_enabled, email_alerts_enabled, anomaly_email_alerts_enabled, push_permission
            FROM Users
            WHERE user_id = ?
            ''',
            (user_id,)
        )
        if not result:
            return jsonify({'error': 'User not found'}), 404

        user_row = result[0]
        if bool(user_row.get('is_deleted')):
            return jsonify({'error': 'User account is disabled'}), 403

        return jsonify({
            'notifications': bool(user_row.get('push_notifications_enabled', 1)),
            'emailAlerts': bool(user_row.get('email_alerts_enabled', 0)),
            'anomalyEmailAlerts': bool(user_row.get('anomaly_email_alerts_enabled', 1)),
            'pushPermission': user_row.get('push_permission') or 'default',
            'pushConfigured': _get_vapid_config()['configured']
        }), 200
    except Exception as e:
        logging.error(f"Get notification settings error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/user/settings/notifications', methods=['PUT'])
@jwt_required()
def update_notification_settings():
    try:
        user_id = _identity_user_id()
        payload = request.get_json(silent=True) or {}

        if 'notifications' not in payload and 'emailAlerts' not in payload and 'anomalyEmailAlerts' not in payload and 'pushPermission' not in payload:
            return jsonify({'error': 'No settings provided'}), 400

        existing = execute_safe_query(
            'SELECT user_id, is_deleted, push_notifications_enabled, email_alerts_enabled, anomaly_email_alerts_enabled, push_permission FROM Users WHERE user_id = ?',
            (user_id,)
        )
        if not existing:
            return jsonify({'error': 'User not found'}), 404

        current_row = existing[0]
        if bool(current_row.get('is_deleted')):
            return jsonify({'error': 'User account is disabled'}), 403

        next_notifications = bool(current_row.get('push_notifications_enabled', 1))
        next_email_alerts = bool(current_row.get('email_alerts_enabled', 0))
        next_anomaly_alerts = bool(current_row.get('anomaly_email_alerts_enabled', 1))
        next_push_permission = current_row.get('push_permission') or 'default'

        if 'notifications' in payload:
            next_notifications = _coerce_bool(payload.get('notifications'), 'notifications')
        if 'emailAlerts' in payload:
            next_email_alerts = _coerce_bool(payload.get('emailAlerts'), 'emailAlerts')
        if 'anomalyEmailAlerts' in payload:
            next_anomaly_alerts = _coerce_bool(payload.get('anomalyEmailAlerts'), 'anomalyEmailAlerts')
        if 'pushPermission' in payload:
            permission = str(payload.get('pushPermission') or '').strip().lower()
            if permission not in {'default', 'granted', 'denied', 'unsupported'}:
                return jsonify({'error': 'Invalid pushPermission value'}), 400
            next_push_permission = permission

        execute_safe_query(
            '''
            UPDATE Users
            SET push_notifications_enabled = ?,
                email_alerts_enabled = ?,
                anomaly_email_alerts_enabled = ?,
                push_permission = ?,
                notification_settings_updated_at = ?
            WHERE user_id = ?
            ''',
            (
                1 if next_notifications else 0,
                1 if next_email_alerts else 0,
                1 if next_anomaly_alerts else 0,
                next_push_permission,
                datetime.now(timezone.utc).isoformat(),
                user_id,
            ),
            fetch=False,
        )

        return jsonify({
            'message': 'Notification settings updated',
            'settings': {
                'notifications': next_notifications,
                'emailAlerts': next_email_alerts,
                'anomalyEmailAlerts': next_anomaly_alerts,
                'pushPermission': next_push_permission,
            }
        }), 200
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as e:
        logging.error(f"Update notification settings error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/user/settings/report-schedules', methods=['GET'])
@jwt_required()
def get_report_schedules():
    try:
        user_id = _identity_user_id()
        result = execute_safe_query(
            '''
            SELECT schedule_id, enabled, cadence, delivery_date, delivery_time, recipient_emails, filters_json, last_delivery_status, last_delivery_error, last_delivery_at, created_at, updated_at
            FROM ReportSchedules
            WHERE user_id = ? AND COALESCE(is_deleted, 0) = 0
            ORDER BY updated_at DESC
            LIMIT 1
            ''',
            (user_id,)
        )
        schedule = result[0] if result else None
        return jsonify({'schedule': schedule}), 200
    except Exception as e:
        logging.error(f"Get report schedules error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/user/settings/report-schedules/history', methods=['GET'])
@jwt_required()
def get_report_schedules_history():
    """Return recent saved schedules for the current user (history)."""
    try:
        user_id = _identity_user_id()
        rows = execute_safe_query(
            '''
            SELECT schedule_id, enabled, cadence, delivery_date, delivery_time, recipient_emails, filters_json, last_delivery_status, last_delivery_error, last_delivery_at, created_at, updated_at
            FROM ReportSchedules
            WHERE user_id = ? AND COALESCE(is_deleted, 0) = 0
            ORDER BY updated_at DESC
            LIMIT 50
            ''',
            (user_id,)
        )
        return jsonify({'schedules': rows or []}), 200
    except Exception as e:
        logging.error(f"Get report schedules history error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/user/settings/report-schedules', methods=['PUT'])
@jwt_required()
def update_report_schedules():
    try:
        user_id = _identity_user_id()
        payload = request.get_json(silent=True) or {}
        try:
            enabled = _coerce_bool(payload.get('enabled', False), 'enabled')
        except ValueError as ve:
            return jsonify({'error': str(ve)}), 400
        cadence = str(payload.get('cadence') or 'weekly').strip().lower()
        delivery_date = str(payload.get('delivery_date') or '').strip()
        delivery_time = str(payload.get('delivery_time') or '08:00').strip()
        recipient_emails = str(payload.get('recipient_emails') or '').strip()
        filters_json = payload.get('filters_json')
        if filters_json is not None and not isinstance(filters_json, str):
            try:
                filters_json = json.dumps(filters_json)
            except Exception:
                filters_json = None

        if cadence not in {'daily', 'weekly', 'monthly'}:
            return jsonify({'error': 'Invalid cadence value'}), 400
        if delivery_date and not re.match(r'^\d{4}-\d{2}-\d{2}$', delivery_date):
            return jsonify({'error': 'Invalid delivery date'}), 400
        # Allow HH:MM or HH:MM:SS formats from different browsers/inputs
        if delivery_time and not re.match(r'^\d{2}:\d{2}(:\d{2})?$', delivery_time):
            return jsonify({'error': 'Invalid delivery time'}), 400

        now_iso = datetime.now(timezone.utc).isoformat()
        # Always insert a new row so users can see schedule history over time.
        logging.debug(f"Inserting report schedule for user_id={user_id} cadence={cadence} delivery_date={delivery_date} delivery_time={delivery_time}")
        db = get_db()
        cursor = db.execute(
            '''
            INSERT INTO ReportSchedules (user_id, enabled, cadence, delivery_date, delivery_time, recipient_emails, filters_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (user_id, 1 if enabled else 0, cadence, delivery_date or None, delivery_time, recipient_emails, filters_json, now_iso, now_iso)
        )
        db.commit()
        schedule_id = cursor.lastrowid

        return jsonify({
            'message': 'Report schedule updated successfully.',
            'schedule': {
                'schedule_id': schedule_id,
                'enabled': bool(enabled),
                'cadence': cadence,
                'delivery_date': delivery_date or None,
                'delivery_time': delivery_time,
                'recipient_emails': recipient_emails,
                'filters_json': filters_json,
            }
        }), 200
    except Exception as e:
        logging.error(f"Update report schedules error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/user/settings/report-schedules/<int:schedule_id>', methods=['DELETE'])
@jwt_required()
def delete_report_schedule(schedule_id):
    try:
        user_id = _identity_user_id()
        # Confirm schedule belongs to user
        rows = execute_safe_query(
            '''
            SELECT schedule_id FROM ReportSchedules WHERE schedule_id = ? AND user_id = ?
            ''',
            (schedule_id, user_id)
        )
        if not rows:
            return jsonify({'error': 'Schedule not found'}), 404

        # Soft-delete so schedules can be restored by super-admins
        now_iso = datetime.now(timezone.utc).isoformat()
        execute_safe_query(
            '''
            UPDATE ReportSchedules SET is_deleted = 1, deleted_at = ?, enabled = 0, updated_at = ?
            WHERE schedule_id = ? AND user_id = ?
            ''',
            (now_iso, now_iso, schedule_id, user_id),
            fetch=False
        )
        return jsonify({'message': 'Schedule deleted (soft) successfully.'}), 200
    except Exception as e:
        logging.error(f"Delete report schedule error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/user/settings/report-schedules/<int:schedule_id>/status', methods=['GET'])
@jwt_required()
def get_report_schedule_status(schedule_id):
    """Get the delivery status and next send time for a report schedule."""
    try:
        user_id = _identity_user_id()
        rows = execute_safe_query(
            '''
            SELECT schedule_id, enabled, cadence, delivery_date, delivery_time, recipient_emails, created_at, updated_at
            FROM ReportSchedules
            WHERE schedule_id = ? AND user_id = ?
            ''',
            (schedule_id, user_id)
        )
        
        if not rows:
            return jsonify({'error': 'Schedule not found'}), 404
        
        schedule = rows[0]
        
        # Calculate next send time
        now = datetime.now(timezone.utc)
        next_send_time = None
        
        try:
            [hour, minute] = schedule.get('delivery_time', '08:00').split(':')[:2]
            hour, minute = int(hour), int(minute)
            
            next_send = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            if next_send <= now:
                if schedule.get('cadence') == 'daily':
                    next_send = next_send + timedelta(days=1)
                elif schedule.get('cadence') == 'weekly':
                    next_send = next_send + timedelta(days=7)
                elif schedule.get('cadence') == 'monthly':
                    next_send = next_send + timedelta(days=30)
            
            next_send_time = next_send.isoformat()
        except:
            pass
        
        return jsonify({
            'schedule_id': schedule.get('schedule_id'),
            'enabled': bool(schedule.get('enabled')),
            'cadence': schedule.get('cadence'),
            'delivery_time': schedule.get('delivery_time'),
            'last_delivery': schedule.get('delivery_date'),
            'last_delivery_status': schedule.get('last_delivery_status'),
            'last_delivery_error': schedule.get('last_delivery_error'),
            'last_delivery_at': schedule.get('last_delivery_at'),
            'next_send_time': next_send_time,
            'recipient_count': len([e for e in (schedule.get('recipient_emails') or '').split(',') if e.strip()]),
            'created_at': schedule.get('created_at'),
            'updated_at': schedule.get('updated_at'),
        }), 200
    except Exception as e:
        logging.error(f"Get report schedule status error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/admin/report-schedules', methods=['GET'])
@jwt_required()
def admin_list_report_schedules():
    """Admin endpoint: list all report schedules across users."""
    try:
        actor = _get_user_row(_identity_user_id())
        if not _is_super_admin_row(actor):
            return jsonify({'error': 'Forbidden'}), 403

        include_deleted = str(request.args.get('include_deleted') or 'false').strip().lower() in ('1', 'true', 'yes')
        try:
            limit = int(request.args.get('limit') or 200)
        except Exception:
            limit = 200

        base_query = '''
            SELECT rs.schedule_id, rs.user_id, u.username, u.email, rs.enabled, rs.cadence, rs.delivery_date, rs.delivery_time,
                   rs.recipient_emails, rs.filters_json, rs.last_delivery_status, rs.last_delivery_error, rs.last_delivery_at,
                   COALESCE(rs.is_deleted, 0) AS is_deleted, rs.deleted_at, rs.created_at, rs.updated_at
            FROM ReportSchedules rs
            LEFT JOIN Users u ON u.user_id = rs.user_id
        '''
        params = []
        if not include_deleted:
            base_query += ' WHERE COALESCE(rs.is_deleted, 0) = 0'
        base_query += ' ORDER BY rs.updated_at DESC LIMIT ?'
        params.append(limit)

        rows = execute_safe_query(base_query, tuple(params))
        return jsonify({'schedules': rows or []}), 200
    except Exception as e:
        logging.error(f"Admin list report schedules error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/admin/report-schedules/<int:schedule_id>/restore', methods=['POST'])
@jwt_required()
def admin_restore_report_schedule(schedule_id):
    """Super-admin endpoint: restore a soft-deleted schedule."""
    try:
        actor = _get_user_row(_identity_user_id())
        if not _is_super_admin_row(actor):
            return jsonify({'error': 'Forbidden'}), 403

        rows = execute_safe_query('SELECT schedule_id, is_deleted FROM ReportSchedules WHERE schedule_id = ? LIMIT 1', (schedule_id,))
        if not rows:
            return jsonify({'error': 'Schedule not found'}), 404

        is_deleted = int(rows[0].get('is_deleted') or 0)
        if is_deleted == 0:
            return jsonify({'message': 'Schedule is not deleted.'}), 400

        now_iso = datetime.now(timezone.utc).isoformat()
        execute_safe_query(
            '''
            UPDATE ReportSchedules
            SET is_deleted = 0, deleted_at = NULL, enabled = 1, updated_at = ?
            WHERE schedule_id = ?
            ''',
            (now_iso, schedule_id),
            fetch=False
        )

        updated = execute_safe_query('SELECT schedule_id, user_id, enabled, cadence, delivery_date, delivery_time, recipient_emails, filters_json, last_delivery_status, last_delivery_error, last_delivery_at, is_deleted, deleted_at, created_at, updated_at FROM ReportSchedules WHERE schedule_id = ? LIMIT 1', (schedule_id,))
        return jsonify({'message': 'Schedule restored.', 'schedule': updated[0] if updated else None}), 200
    except Exception as e:
        logging.error(f"Admin restore report schedule error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/admin/report-schedules/<int:schedule_id>/purge', methods=['DELETE'])
@jwt_required()
def admin_purge_report_schedule(schedule_id):
    """Super-admin endpoint: permanently delete a report schedule."""
    try:
        actor = _get_user_row(_identity_user_id())
        if not _is_super_admin_row(actor):
            return jsonify({'error': 'Forbidden'}), 403

        rows = execute_safe_query('SELECT schedule_id FROM ReportSchedules WHERE schedule_id = ? LIMIT 1', (schedule_id,))
        if not rows:
            return jsonify({'error': 'Schedule not found'}), 404

        execute_safe_query('DELETE FROM ReportSchedules WHERE schedule_id = ?', (schedule_id,), fetch=False)
        return jsonify({'message': 'Schedule permanently deleted.'}), 200
    except Exception as e:
        logging.error(f"Admin purge report schedule error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/admin/report-schedules/clear-all', methods=['POST'])
@jwt_required()
def admin_clear_all_report_schedules():
    """Admin endpoint: soft-delete all visible report schedules in the aggregate report."""
    try:
        actor = _get_user_row(_identity_user_id())
        if not _is_super_admin_row(actor):
            return jsonify({'error': 'Forbidden'}), 403

        now_iso = datetime.now(timezone.utc).isoformat()
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            '''
            UPDATE ReportSchedules
            SET is_deleted = 1, deleted_at = ?, enabled = 0, updated_at = ?
            WHERE COALESCE(is_deleted, 0) = 0
              AND user_id IN (
                  SELECT user_id FROM Users WHERE role IN ('editor', 'admin', 'super_admin')
              )
            ''',
            (now_iso, now_iso)
        )
        deleted_count = cursor.rowcount if cursor.rowcount is not None else 0
        db.commit()
        return jsonify({'message': 'All aggregate report schedules cleared.', 'deleted_count': deleted_count}), 200
    except Exception as e:
        logging.error(f"Admin clear all report schedules error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/admin/aggregated-report-schedules', methods=['GET'])
@jwt_required()
def admin_aggregated_report_schedules():
    """Admin endpoint: get aggregated report schedules from all non-viewer roles."""
    try:
        actor = _get_user_row(_identity_user_id())
        if not _is_admin_or_super_admin_row(actor):
            return jsonify({'error': 'Forbidden'}), 403

        include_deleted = str(request.args.get('include_deleted') or 'false').strip().lower() in ('1', 'true', 'yes')
        try:
            limit = int(request.args.get('limit') or 500)
        except Exception:
            limit = 500

        # Exclude 'viewer' role as per requirements
        query = '''
            SELECT rs.schedule_id, rs.user_id, u.username, u.email, u.role, rs.enabled, rs.cadence, rs.delivery_date, rs.delivery_time,
                   rs.recipient_emails, rs.filters_json, rs.last_delivery_status, rs.last_delivery_error, rs.last_delivery_at,
                   COALESCE(rs.is_deleted, 0) AS is_deleted, rs.deleted_at, rs.created_at, rs.updated_at
            FROM ReportSchedules rs
            LEFT JOIN Users u ON u.user_id = rs.user_id
            WHERE u.role IN ('editor', 'admin', 'super_admin')
        '''
        if not include_deleted:
            query += ' AND COALESCE(rs.is_deleted, 0) = 0'
        query += ' ORDER BY rs.updated_at DESC LIMIT ?'

        rows = execute_safe_query(query, (limit,))
        
        # Group by user for easier visualization
        by_user = {}
        for row in (rows or []):
            user_id = row.get('user_id')
            if user_id not in by_user:
                by_user[user_id] = {
                    'user_id': user_id,
                    'username': row.get('username'),
                    'email': row.get('email'),
                    'role': row.get('role'),
                    'schedules': []
                }
            by_user[user_id]['schedules'].append(row)
        
        return jsonify({
            'aggregated': list(by_user.values()),
            'all_schedules': rows or [],
            'total': len(rows or [])
        }), 200
    except Exception as e:
        logging.error(f"Admin aggregated report schedules error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/user/settings/notifications/test-email', methods=['POST'])
@jwt_required()
def send_test_notification_email():
    try:
        user_id = _identity_user_id()
        result = execute_safe_query(
            '''
            SELECT user_id, username, email, is_deleted, email_alerts_enabled
            FROM Users
            WHERE user_id = ?
            ''',
            (user_id,)
        )
        if not result:
            return jsonify({'error': 'User not found'}), 404

        user_row = result[0]
        if bool(user_row.get('is_deleted')):
            return jsonify({'error': 'User account is disabled'}), 403
        if not bool(user_row.get('email_alerts_enabled')):
            return jsonify({'error': 'Enable Email Alerts first.'}), 400
        if not user_row.get('email'):
            return jsonify({'error': 'No email address on file for this account.'}), 400

        html_content, text_content = render_email_template(
            username=user_row.get('username'),
            title='Email Alerts Test',
            intro='Your email alerts setting is active.',
            body_html='<p style="margin:0 0 12px;font-size:14px;line-height:1.6;color:#41546f;">This is a test notification sent from your account settings page.</p>',
            note_html='<p style="margin:10px 0 0;padding:12px 14px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;font-size:14px;line-height:1.6;color:#1d4ed8;">If you received this message, your Email Alerts toggle is fully connected.</p>'
        )

        if not send_email(
            user_row.get('email'),
            'Email Alerts Test',
            html_content,
            text_content,
            notification_event=None
        ):
            return jsonify({'error': 'Email delivery failed. Check SMTP settings.'}), 502

        try:
            _create_notification_event(
                user_id=user_id,
                actor_user_id=user_id,
                actor_username=user_row.get('username'),
                channel='email',
                direction='received',
                notification_type='test',
                title='Email Alerts Test',
                body='This is a test notification sent from your account settings page.',
                status='sent',
                source='settings_test_email',
                recipient_email=user_row.get('email'),
                sent_at=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as log_err:
            logging.warning(f"Failed to persist test email notification event: {log_err}")

        return jsonify({'message': 'Test email sent successfully.'}), 200
    except Exception as e:
        logging.error(f"Send test notification email error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/user/settings/notifications/push/public-key', methods=['GET'])
@jwt_required()
def get_push_public_key():
    try:
        user_id = _identity_user_id()
        user_row = _get_user_row(user_id)
        if not user_row:
            return jsonify({'error': 'User not found'}), 404
        if bool(user_row.get('is_deleted')):
            return jsonify({'error': 'User account is disabled'}), 403

        vapid = _get_vapid_config()
        if not vapid['configured']:
            return jsonify({'error': 'Push notifications are not configured on the server.'}), 503

        return jsonify({'publicKey': vapid['public_key']}), 200
    except Exception as e:
        logging.error(f"Get push public key error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/user/settings/notifications/push/subscription', methods=['POST'])
@jwt_required()
def upsert_push_subscription():
    try:
        user_id = _identity_user_id()
        user_row = _get_user_row(user_id)
        if not user_row:
            return jsonify({'error': 'User not found'}), 404
        if bool(user_row.get('is_deleted')):
            return jsonify({'error': 'User account is disabled'}), 403

        subscription = _normalize_subscription_payload(request.get_json(silent=True) or {})
        now = datetime.now(timezone.utc).isoformat()
        user_agent = (request.headers.get('User-Agent') or '')[:512]

        existing = execute_safe_query(
            'SELECT subscription_id FROM NotificationSubscriptions WHERE endpoint = ? LIMIT 1',
            (subscription['endpoint'],),
        )

        if existing:
            execute_safe_query(
                '''
                UPDATE NotificationSubscriptions
                SET user_id = ?,
                    p256dh_key = ?,
                    auth_key = ?,
                    content_encoding = ?,
                    user_agent = ?,
                    is_active = 1,
                    updated_at = ?
                WHERE endpoint = ?
                ''',
                (
                    user_id,
                    subscription['p256dh_key'],
                    subscription['auth_key'],
                    subscription['content_encoding'],
                    user_agent,
                    now,
                    subscription['endpoint'],
                ),
                fetch=False,
            )
        else:
            execute_safe_query(
                '''
                INSERT INTO NotificationSubscriptions (
                    user_id, endpoint, p256dh_key, auth_key, content_encoding, user_agent, is_active, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                ''',
                (
                    user_id,
                    subscription['endpoint'],
                    subscription['p256dh_key'],
                    subscription['auth_key'],
                    subscription['content_encoding'],
                    user_agent,
                    now,
                    now,
                ),
                fetch=False,
            )

        return jsonify({'message': 'Push subscription saved'}), 200
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as e:
        logging.error(f"Upsert push subscription error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/user/settings/notifications/push/subscription', methods=['DELETE'])
@jwt_required()
def deactivate_push_subscription():
    try:
        user_id = _identity_user_id()
        user_row = _get_user_row(user_id)
        if not user_row:
            return jsonify({'error': 'User not found'}), 404
        if bool(user_row.get('is_deleted')):
            return jsonify({'error': 'User account is disabled'}), 403

        payload = request.get_json(silent=True) or {}
        endpoint = str(payload.get('endpoint') or '').strip()
        if endpoint:
            execute_safe_query(
                'UPDATE NotificationSubscriptions SET is_active = 0, updated_at = ? WHERE user_id = ? AND endpoint = ?',
                (datetime.now(timezone.utc).isoformat(), user_id, endpoint),
                fetch=False,
            )
        else:
            execute_safe_query(
                'UPDATE NotificationSubscriptions SET is_active = 0, updated_at = ? WHERE user_id = ?',
                (datetime.now(timezone.utc).isoformat(), user_id),
                fetch=False,
            )

        return jsonify({'message': 'Push subscription removed'}), 200
    except Exception as e:
        logging.error(f"Deactivate push subscription error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/user/settings/notifications/test-push', methods=['POST'])
@jwt_required()
def send_test_push_notification():
    try:
        user_id = _identity_user_id()
        user_row = _get_user_row(user_id)
        if not user_row:
            return jsonify({'error': 'User not found'}), 404
        if bool(user_row.get('is_deleted')):
            return jsonify({'error': 'User account is disabled'}), 403
        if not bool(user_row.get('push_notifications_enabled')):
            return jsonify({'error': 'Enable Push Notifications first.'}), 400

        payload = {
            'title': 'ITDS Push Test',
            'body': 'Your push notification delivery is configured correctly.',
            'tag': 'itds-push-test',
            'url': '/settings',
        }
        stats = _dispatch_push_to_opted_users(payload, target_user_ids=[user_id])
        if stats.get('sent', 0) == 0:
            reason = stats.get('reason') or 'No active browser push subscription found.'
            return jsonify({'error': reason}), 400
        return jsonify({'message': 'Test push sent.', 'delivery': stats}), 200
    except Exception as e:
        logging.error(f"Send test push notification error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/admin/notifications/system-status', methods=['POST'])
@jwt_required()
def send_system_status_notification():
    try:
        actor_id = _identity_user_id()
        actor = _get_user_row(actor_id)
        if not _user_can_manage_system_notifications(actor):
            return jsonify({'error': 'Admin access required'}), 403

        data = request.get_json(silent=True) or {}
        title = str(data.get('title') or 'System Status Update').strip()
        message = str(data.get('message') or '').strip()
        severity = str(data.get('severity') or 'info').strip().lower()
        if not message:
            return jsonify({'error': 'Message is required'}), 400
        if severity not in {'info', 'warning', 'critical'}:
            return jsonify({'error': 'Severity must be info, warning, or critical'}), 400

        opted_email_users = execute_safe_query(
            '''
            SELECT user_id, username, email
            FROM Users
            WHERE is_deleted = 0 AND email_alerts_enabled = 1 AND email IS NOT NULL AND TRIM(email) <> ''
            '''
        )

        email_sent = 0
        email_failed = 0
        severity_styles = {
            'info': ('#eff6ff', '#bfdbfe', '#1d4ed8'),
            'warning': ('#fffbeb', '#fcd34d', '#92400e'),
            'critical': ('#fef2f2', '#fecaca', '#b91c1c'),
        }
        note_background, note_border, note_color = severity_styles.get(severity, severity_styles['info'])
        for user_item in opted_email_users:
            html_content, text_content = render_email_template(
                username=user_item.get('username'),
                title=title,
                intro=message,
                note_html=(
                    f'<p style="margin:10px 0 0;padding:12px 14px;background:{note_background};border:1px solid {note_border};'
                    f'border-radius:8px;font-size:14px;line-height:1.6;color:{note_color};">'
                    f'Severity: <strong>{html_utils.escape(severity.upper())}</strong></p>'
                )
            )
            if send_email(
                user_item.get('email'),
                f'{title} - Board Minutes Analyser',
                html_content,
                text_content,
                notification_event={
                    'user_id': user_item.get('user_id'),
                    'actor_user_id': actor_id,
                    'actor_username': actor.get('username', 'unknown'),
                    'notification_type': 'broadcast',
                    'title': title,
                    'body': message,
                    'source': 'admin_system_status',
                    'metadata': {'severity': severity},
                }
            ):
                email_sent += 1
            else:
                email_failed += 1

        push_payload = {
            'title': title,
            'body': message,
            'severity': severity,
            'tag': f'system-status-{severity}',
            'url': '/dashboard',
        }
        push_stats = _dispatch_push_to_opted_users(push_payload)

        log_archiving_activity(
            actor_id,
            'system_status_notification',
            {
                'title': title,
                'severity': severity,
                'email_sent': email_sent,
                'email_failed': email_failed,
                'push_delivery': push_stats,
            },
            actor_username=actor.get('username', 'unknown'),
            actor_role=actor.get('role', 'admin'),
        )

        return jsonify({
            'message': 'System status notification dispatched',
            'email': {'sent': email_sent, 'failed': email_failed},
            'push': push_stats,
        }), 200
    except Exception as e:
        logging.error(f"Send system status notification error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/notifications/summary', methods=['GET'])
@jwt_required()
def get_notifications_summary():
    try:
        user_id = _identity_user_id()
        user_row = _get_user_row(user_id)
        if not user_row:
            return jsonify({'error': 'User not found'}), 404
        if bool(user_row.get('is_deleted')):
            return jsonify({'error': 'User account is disabled'}), 403

        default_scope = 'all' if _is_super_admin_row(user_row) else 'mine'
        scope = _resolve_notification_scope(user_row, request.args.get('scope'), default_scope=default_scope)
        if scope is None:
            return jsonify({'error': 'Only super admin can request global notification scope'}), 403

        counts = _fetch_notification_counts(user_id, scope=scope)
        counts['scope'] = scope
        return jsonify(counts), 200
    except Exception as e:
        logging.error(f"Get notifications summary error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/notifications', methods=['GET'])
@jwt_required()
def list_notifications():
    try:
        user_id = _identity_user_id()
        user_row = _get_user_row(user_id)
        if not user_row:
            return jsonify({'error': 'User not found'}), 404
        if bool(user_row.get('is_deleted')):
            return jsonify({'error': 'User account is disabled'}), 403

        default_scope = 'all' if _is_super_admin_row(user_row) else 'mine'
        scope = _resolve_notification_scope(user_row, request.args.get('scope'), default_scope=default_scope)
        if scope is None:
            return jsonify({'error': 'Only super admin can request global notification scope'}), 403

        tab = str(request.args.get('tab') or 'all').strip().lower()
        channel = str(request.args.get('channel') or 'all').strip().lower()
        limit = min(max(int(request.args.get('limit', 25)), 1), 100)

        scope_where, scope_params = _notification_scope_clause(user_id, scope)
        where = [scope_where]
        params = list(scope_params)

        if tab == 'deleted':
            where.append('COALESCE(is_deleted, 0) = 1')
        else:
            where.append('COALESCE(is_deleted, 0) = 0')

        if tab == 'archived':
            where.append('COALESCE(is_archived, 0) = 1')

        if tab == 'received':
            where.append("direction = 'received'")
        elif tab == 'sent':
            where.append("direction = 'sent'")
        elif tab == 'read':
            where.append('is_read = 1')
        elif tab == 'unread':
            where.append('is_read = 0')

        if channel in {'email', 'push'}:
            where.append('channel = ?')
            params.append(channel)

        query = f'''
            SELECT
                notification_id,
                user_id,
                actor_user_id,
                actor_username,
                channel,
                direction,
                notification_type,
                title,
                body,
                status,
                source,
                reference_id,
                is_read,
                read_at,
                is_deleted,
                deleted_at,
                is_archived,
                archived_at,
                metadata,
                created_at,
                sent_at,
                delivered_at,
                failed_at,
                error_message,
                recipient_email
            FROM NotificationEvents
            WHERE {' AND '.join(where)}
            ORDER BY datetime(COALESCE(created_at, sent_at, delivered_at, failed_at)) DESC, notification_id DESC
            LIMIT ?
        '''
        params.append(limit)

        rows = execute_safe_query(query, tuple(params))
        notifications = []
        for row in rows or []:
            row_copy = dict(row)
            if row_copy.get('metadata'):
                try:
                    row_copy['metadata'] = json.loads(row_copy['metadata'])
                except Exception:
                    pass
            notifications.append(row_copy)

        return jsonify({'items': notifications, 'counts': _fetch_notification_counts(user_id, scope=scope), 'scope': scope}), 200
    except Exception as e:
        logging.error(f"List notifications error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/notifications/<int:notification_id>/archive', methods=['POST'])
@jwt_required()
def archive_notification(notification_id):
    try:
        user_id = _identity_user_id()
        actor_row = _get_user_row(user_id)
        if not actor_row:
            return jsonify({'error': 'User not found'}), 404
        if bool(actor_row.get('is_deleted')):
            return jsonify({'error': 'User account is disabled'}), 403

        target_row, error_response = _resolve_notification_target_for_actor(notification_id, user_id, actor_row)
        if error_response:
            return error_response

        execute_safe_query(
            'UPDATE NotificationEvents SET is_archived = 1, archived_at = ? WHERE notification_id = ?',
            (datetime.now(timezone.utc).isoformat(), notification_id),
            fetch=False,
        )
        _log_super_admin_notification_action(
            actor_row,
            'notification_archived',
            notification_id=notification_id,
            target_user_id=target_row.get('user_id'),
        )
        return jsonify({'message': 'Notification archived'}), 200
    except Exception as e:
        logging.error(f"Archive notification error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/notifications/<int:notification_id>/restore', methods=['POST'])
@jwt_required()
def restore_notification(notification_id):
    try:
        user_id = _identity_user_id()
        actor_row = _get_user_row(user_id)
        if not actor_row:
            return jsonify({'error': 'User not found'}), 404
        if bool(actor_row.get('is_deleted')):
            return jsonify({'error': 'User account is disabled'}), 403

        target_row, error_response = _resolve_notification_target_for_actor(notification_id, user_id, actor_row)
        if error_response:
            return error_response

        execute_safe_query(
            'UPDATE NotificationEvents SET is_deleted = 0, deleted_at = NULL, is_archived = 0, archived_at = NULL WHERE notification_id = ?',
            (notification_id,),
            fetch=False,
        )
        _log_super_admin_notification_action(
            actor_row,
            'notification_restored',
            notification_id=notification_id,
            target_user_id=target_row.get('user_id'),
        )
        return jsonify({'message': 'Notification restored'}), 200
    except Exception as e:
        logging.error(f"Restore notification error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/notifications/<int:notification_id>', methods=['DELETE'])
@jwt_required()
def delete_notification(notification_id):
    try:
        user_id = _identity_user_id()
        actor_row = _get_user_row(user_id)
        if not actor_row:
            return jsonify({'error': 'User not found'}), 404
        if bool(actor_row.get('is_deleted')):
            return jsonify({'error': 'User account is disabled'}), 403

        target_row, error_response = _resolve_notification_target_for_actor(notification_id, user_id, actor_row)
        if error_response:
            return error_response

        execute_safe_query(
            'UPDATE NotificationEvents SET is_deleted = 1, deleted_at = ? WHERE notification_id = ?',
            (datetime.now(timezone.utc).isoformat(), notification_id),
            fetch=False,
        )
        _log_super_admin_notification_action(
            actor_row,
            'notification_deleted',
            notification_id=notification_id,
            target_user_id=target_row.get('user_id'),
        )
        return jsonify({'message': 'Notification deleted'}), 200
    except Exception as e:
        logging.error(f"Delete notification error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/notifications/clear-all', methods=['POST'])
@jwt_required()
def clear_all_notifications():
    try:
        user_id = _identity_user_id()
        actor_row = _get_user_row(user_id)
        if not actor_row:
            return jsonify({'error': 'User not found'}), 404
        if bool(actor_row.get('is_deleted')):
            return jsonify({'error': 'User account is disabled'}), 403

        payload = request.get_json(silent=True) or {}
        scope = _resolve_notification_scope(actor_row, payload.get('scope'), default_scope='mine')
        if scope is None:
            return jsonify({'error': 'Only super admin can request global notification scope'}), 403

        tab = str(payload.get('tab') or 'all').strip().lower()
        channel = str(payload.get('channel') or 'all').strip().lower()

        scope_where, scope_params = _notification_scope_clause(user_id, scope)
        where = [scope_where, 'COALESCE(is_deleted, 0) = 0']
        params = list(scope_params)

        if tab == 'archived':
            where.append('COALESCE(is_archived, 0) = 1')
        elif tab == 'received':
            where.append("direction = 'received'")
        elif tab == 'sent':
            where.append("direction = 'sent'")
        elif tab == 'read':
            where.append('is_read = 1')
        elif tab == 'unread':
            where.append('is_read = 0')
        elif tab == 'deleted':
            return jsonify({'error': 'Deleted notifications are already cleared.'}), 400

        if channel in {'email', 'push'}:
            where.append('channel = ?')
            params.append(channel)

        now_iso = datetime.now(timezone.utc).isoformat()
        db = get_db()
        cursor = db.execute(
            f'''
            UPDATE NotificationEvents
            SET is_deleted = 1,
                deleted_at = ?,
                is_archived = 0,
                archived_at = NULL
            WHERE {' AND '.join(where)}
            ''',
            (now_iso, *params)
        )
        db.commit()
        cleared_count = cursor.rowcount or 0

        if cleared_count and scope == 'all':
            _log_super_admin_notification_action(
                actor_row,
                'notifications_cleared_all',
                extra_details={
                    'target': 'all_users',
                    'tab': tab,
                    'channel': channel,
                    'cleared_count': cleared_count,
                },
            )

        return jsonify({
            'message': 'Notifications cleared',
            'cleared_count': cleared_count,
            'scope': scope,
            'tab': tab,
            'channel': channel,
        }), 200
    except Exception as e:
        logging.error(f"Clear all notifications error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
@jwt_required()
def mark_notification_read(notification_id):
    try:
        user_id = _identity_user_id()
        actor_row = _get_user_row(user_id)
        if not actor_row:
            return jsonify({'error': 'User not found'}), 404
        if bool(actor_row.get('is_deleted')):
            return jsonify({'error': 'User account is disabled'}), 403

        target_row, error_response = _resolve_notification_target_for_actor(notification_id, user_id, actor_row)
        if error_response:
            return error_response

        execute_safe_query(
            'UPDATE NotificationEvents SET is_read = 1, read_at = ? WHERE notification_id = ?',
            (datetime.now(timezone.utc).isoformat(), notification_id),
            fetch=False,
        )
        _log_super_admin_notification_action(
            actor_row,
            'notification_marked_read',
            notification_id=notification_id,
            target_user_id=target_row.get('user_id'),
        )
        return jsonify({'message': 'Notification marked as read'}), 200
    except Exception as e:
        logging.error(f"Mark notification read error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/notifications/read-all', methods=['POST'])
@jwt_required()
def mark_all_notifications_read():
    try:
        user_id = _identity_user_id()
        user_row = _get_user_row(user_id)
        if not user_row:
            return jsonify({'error': 'User not found'}), 404
        if bool(user_row.get('is_deleted')):
            return jsonify({'error': 'User account is disabled'}), 403

        scope = _resolve_notification_scope(user_row, request.args.get('scope'), default_scope='mine')
        if scope is None:
            return jsonify({'error': 'Only super admin can request global notification scope'}), 403

        scope_where, scope_params = _notification_scope_clause(user_id, scope)
        params = [datetime.now(timezone.utc).isoformat()]
        params.extend(scope_params)
        execute_safe_query(
            f'UPDATE NotificationEvents SET is_read = 1, read_at = ? WHERE {scope_where}',
            tuple(params),
            fetch=False,
        )

        if scope == 'all':
            _log_super_admin_notification_action(
                user_row,
                'notifications_marked_all_read',
                extra_details={'target': 'all_users'}
            )

        return jsonify({'message': 'All notifications marked as read', 'scope': scope}), 200
    except Exception as e:
        logging.error(f"Mark all notifications read error: {e}")
        return jsonify({'error': 'Server error'}), 500


@app.route('/api/notifications/send-bulk-email', methods=['POST'])
@jwt_required()
def send_bulk_email_for_transcripts():
    """Send selected records to recipient(s). Supports transcript CSV exports and selected report rows."""
    try:
        payload = request.get_json() or {}
        recipient = (payload.get('recipient_email') or '').strip()
        transcript_ids = payload.get('transcript_ids') or []
        rows = payload.get('rows') or []
        report_type = (payload.get('report_type') or 'transcripts').strip().lower()
        subject = payload.get('subject') or 'Selected transcripts from Board Minutes Analyser'
        message = payload.get('message') or ''

        normalized_rows = [row for row in rows if isinstance(row, dict)]
        if not recipient or (len(transcript_ids) == 0 and len(normalized_rows) == 0):
            return jsonify({'error': 'recipient_email and selected rows are required'}), 400

        attachment = None
        html_body = ''
        text_body = ''

        if len(normalized_rows) > 0:
            # Build a readable email body for report rows (summaries, topics, keywords, sentiment, actions)
            pretty_rows = []
            for index, row in enumerate(normalized_rows, start=1):
                if report_type == 'summaries':
                    main_text = row.get('summary_text') or row.get('summary') or ''
                    extra = f"Meeting {row.get('meeting_id') or '-'}"
                elif report_type == 'topics':
                    main_text = row.get('name') or row.get('topic_name') or ''
                    extra = f"Occurrences {row.get('topic_occurrences') or row.get('occurrences') or 1}"
                elif report_type == 'keywords':
                    main_text = row.get('keywords') or ''
                    extra = f"Confidence {row.get('confidence') or '-'}"
                elif report_type == 'actions':
                    main_text = row.get('item_text') or row.get('action_item') or ''
                    extra = f"Status {row.get('status') or '-'}"
                elif report_type == 'sentiment':
                    main_text = row.get('sentiment') or ''
                    extra = f"Confidence {row.get('confidence') or '-'}"
                else:
                    main_text = row.get('transcript_text') or row.get('summary_text') or row.get('name') or ''
                    extra = ''

                pretty_rows.append({
                    'index': index,
                    'main': str(main_text or '').strip(),
                    'extra': str(extra or '').strip(),
                })

            items_html = ''.join(
                f"<li><strong>{item['index']}.</strong> {item['main'] or '-'}" + (f" <em>({item['extra']})</em>" if item['extra'] else '') + '</li>'
                for item in pretty_rows
            )
            html_body = f"<p>{message}</p><p>Selected {len(pretty_rows)} {report_type} item(s):</p><ul>{items_html}</ul>"
            text_body = message or f"Selected {len(pretty_rows)} {report_type} item(s)."
        else:
            # Fallback: fetch transcript rows by id and build a CSV attachment
            placeholders = ','.join('?' for _ in transcript_ids)
            transcript_rows = execute_safe_query(
                f'SELECT transcript_id, created_at, keywords, transcript_text, sentiment FROM Transcripts WHERE transcript_id IN ({placeholders})',
                tuple(transcript_ids)
            )

            import io, csv
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['transcript_id', 'created_at', 'keywords', 'transcript_text', 'sentiment'])
            for r in transcript_rows:
                writer.writerow([r.get('transcript_id'), r.get('created_at'), r.get('keywords') or '', r.get('transcript_text') or '', r.get('sentiment') or ''])
            csv_content = output.getvalue()
            output.close()

            html_body = f"<p>{message}</p><p>Attached are {len(transcript_rows)} selected transcripts.</p>"
            text_body = message or f"Attached are {len(transcript_rows)} selected transcripts."
            attachment = {'filename': f'selected_transcripts_{int(time.time())}.csv', 'content': csv_content, 'mimetype': 'text/csv'}

        actor_id = _identity_user_id()
        actor = _get_user_row(actor_id) or {}

        notification_event = {
            'user_id': None,
            'actor_user_id': actor_id,
            'actor_username': actor.get('username'),
            'direction': 'sent',
            'notification_type': 'bulk_export',
            'title': subject,
            'body': message,
            'source': 'bulk_email_export',
            'reference_id': None,
            'metadata': {'count': len(normalized_rows) if normalized_rows else len(transcript_ids), 'report_type': report_type}
        }

        ok = send_email(recipient, subject, html_body, text_body, notification_event=notification_event, attachments=[attachment] if attachment else None)
        if not ok:
            return jsonify({'error': 'Email delivery failed'}), 502

        return jsonify({'message': 'Email sent', 'count': len(normalized_rows) if normalized_rows else len(transcript_ids)}), 200
    except Exception as e:
        logging.error(f"Send bulk email error: {e}")
        return jsonify({'error': 'Server error'}), 500

@app.route('/api/auth/change-password', methods=['POST'])
@jwt_required()
def change_password():
    try:
        data = request.get_json()
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        
        identity = get_jwt_identity()
        
        # Handle both str and dict identity formats
        user_id = identity
        if isinstance(identity, dict):
            user_id = identity['user_id']
        
        user = execute_safe_query(
            'SELECT password_hash FROM Users WHERE user_id = ?',
            (user_id,)
        )
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        if not check_password_hash(user[0]['password_hash'], current_password):
            return jsonify({'error': 'Current password incorrect'}), 400
        
        password_hash = generate_password_hash(new_password)
        execute_safe_query(
            'UPDATE Users SET password_hash = ?, must_change_password = 0 WHERE user_id = ?',
            (password_hash, user_id),
            fetch=False
        )
        
        # Send security notification email
        user_info = execute_safe_query(
            'SELECT email, username FROM Users WHERE user_id = ?',
            (user_id,)
        )
        if user_info:
            email = user_info[0]['email']
            username = user_info[0]['username']
            send_password_changed_email(email, username, recipient_user_id=user_id)
        
        logging.info(f"Password changed for user {user_info[0]['username'] if user_info else user_id}")
        return jsonify({'message': 'Password changed successfully. Security notification sent.'}), 200
    except Exception as e:
        logging.error(f"Change password error: {e}")
        return jsonify({'error': 'Server error'}), 500

# Removed duplicate /api/admin/users route - use admin_bp instead

@app.route('/api/auth/forgot-password', methods=['POST'])
def forgot_password():
    try:
        data = request.get_json()
        email = data.get("email")
        
        if not email:
            return jsonify({"error": "Email is required"}), 400

        result = execute_safe_query(
            "SELECT user_id, username FROM Users WHERE email = ?",
            (email,)
        )

        if not result:
            return jsonify({
                "message": "If the email exists, reset instructions were sent"
            }), 200

        user_id = result[0]['user_id']
        username = result[0]['username']
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        
        execute_safe_query(
            "UPDATE Users SET reset_token = ?, reset_token_expires = ? WHERE user_id = ?",
            (token, expires, user_id),
            fetch=False
        )
        
        if send_reset_email(email, username, token, recipient_user_id=user_id):
            logging.info(f"Reset email sent successfully to {email}")
            return jsonify({
                "message": "If the email exists, password reset instructions have been sent to your inbox."
            }), 200
        else:
            logging.warning(f"Failed to send reset email to {email} (token generated)")
            return jsonify({
                "message": "Reset token generated but email delivery failed. Contact admin."
            }), 200

    except Exception as e:
        logging.error(f"Forgot password error: {e}")
        return jsonify({"error": "Server error"}), 500

@app.route('/api/auth/reset-password', methods=['POST'])
def reset_password():
    try:
        data = request.get_json()
        token = data.get('token')
        new_password = data.get('newPassword')
        
        if not token or not new_password:
            return jsonify({'error': 'Token and password required'}), 400
        
        # Verify token and get user info
        user_result = execute_safe_query(
            'SELECT user_id, email, username FROM Users WHERE reset_token = ? AND reset_token_expires > ?',
            (token, datetime.now(timezone.utc))
        )
        
        if not user_result:
            return jsonify({'error': 'Invalid or expired token'}), 400
        
        user = user_result[0]
        user_id = user['user_id']
        email = user['email']
        username = user['username']
        
        # Update password and clear token
        password_hash = generate_password_hash(new_password)
        execute_safe_query(
            'UPDATE Users SET password_hash = ?, reset_token = NULL, reset_token_expires = NULL WHERE user_id = ?',
            (password_hash, user_id),
            fetch=False
        )
        
        # Send confirmation email
        send_password_reset_confirmation(email, username, recipient_user_id=user_id)
        
        logging.info(f"Password reset complete for user {username} (ID:{user_id})")
        return jsonify({'message': 'Password reset successful. Confirmation email sent.'}), 200
        
    except Exception as e:
        logging.error(f"Reset password error: {e}")
        return jsonify({'error': 'Server error'}), 500

# ============================================
# DASHBOARD ROUTES
# ============================================

@app.route('/api/user/upload-profile-image', methods=['POST'])
@jwt_required()
def upload_profile_image():
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image file'}), 400
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Validate
        if not file.content_type.startswith('image/'):
            return jsonify({'error': 'Invalid file type (image only)'}), 400

        # Calculate file size safely on FileStorage
        file.stream.seek(0, os.SEEK_END)
        file_size = file.stream.tell()
        file.stream.seek(0)
        if file_size > 2 * 1024 * 1024:  # 2MB
            return jsonify({'error': 'File too large (max 2MB)'}), 400
        
        identity = get_jwt_identity()
        user_id = str(identity) if isinstance(identity, (int, str)) else identity.get('user_id', identity)
        
        import uuid
        from werkzeug.utils import secure_filename
        filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
        filepath = os.path.join('uploads/profile_images', filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        file.save(filepath)
        
        # Get current profile image
        current_user = execute_safe_query(
            'SELECT profile_image FROM Users WHERE user_id = ?',
            (user_id,)
        )
        old_filename = current_user[0]['profile_image'] if current_user and current_user[0]['profile_image'] else None
        
        # Delete old image if exists and different from new
        if old_filename and old_filename != filename:
            try:
                old_filepath = os.path.join('uploads/profile_images', old_filename)
                if os.path.exists(old_filepath):
                    os.remove(old_filepath)
                    logging.info(f"Deleted old profile image: {old_filename}")
            except Exception as delete_err:
                logging.warning(f"Failed to delete old image {old_filename}: {delete_err}")
        
        # Update database with new image
        execute_safe_query(
            'UPDATE Users SET profile_image = ? WHERE user_id = ?',
            (filename, user_id),
            fetch=False
        )
        
        result = execute_safe_query(
            'SELECT user_id, username, email, full_name, role, profile_image, must_change_password FROM Users WHERE user_id = ?',
            (user_id,)
        )
        return jsonify(result[0]), 200
        
    except Exception as e:
        logging.error(f"Profile image upload error: {e}")
        return jsonify({'error': 'Upload failed'}), 500

# ============================================
# UPLOAD ROUTES
# ============================================

UPLOAD_JOBS = {}
UPLOAD_JOBS_LOCK = threading.Lock()


def _set_upload_job_state(upload_id, updates):
    with UPLOAD_JOBS_LOCK:
        job = UPLOAD_JOBS.get(upload_id, {})
        job.update(updates)
        UPLOAD_JOBS[upload_id] = job


def _get_upload_job_state(upload_id):
    with UPLOAD_JOBS_LOCK:
        job = UPLOAD_JOBS.get(upload_id)
        return dict(job) if job else None


def _cleanup_temp_upload_file(temp_filepath):
    try:
        if temp_filepath and os.path.exists(temp_filepath):
            os.remove(temp_filepath)
    except Exception:
        pass


def _get_temp_upload_dir():
    upload_dir = os.path.join(tempfile.gettempdir(), 'itds_minutes_uploads')
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def _process_upload_job(upload_id, temp_filepath, original_filename, meeting_date, meeting_metadata=None):
    ext = os.path.splitext(original_filename)[1].lower()
    source_filename = original_filename

    try:
        _set_upload_job_state(upload_id, {
            'status': 'running',
            'phase': 'extracting',
            'progress': 5,
            'message': 'Starting document extraction',
            'source_filename': source_filename,
            'meeting_date': meeting_date,
            'meeting_metadata': None,
        })

        if ext == '.txt':
            with open(temp_filepath, 'r', encoding='utf-8', errors='replace') as file_handle:
                raw_text = file_handle.read()
        else:
            raw_text = extract_text(temp_filepath)

        _set_upload_job_state(upload_id, {
            'phase': 'segmenting',
            'progress': 35,
            'message': 'Extracting text and preparing segments',
        })

        segments = transform_text(raw_text)
        cleaned_segments = [segment for segment in segments if segment.strip()]

        _set_upload_job_state(upload_id, {
            'phase': 'saving',
            'progress': 55,
            'message': 'Saving extracted content',
        })

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO Meetings (meeting_date, source_filename) VALUES (?, ?)',
            (meeting_date, source_filename)
        )
        meeting_id = cursor.lastrowid

        total_segments = max(len(cleaned_segments), 1)
        inserted_segments = 0

        for index, segment_text in enumerate(cleaned_segments, start=1):
            cursor.execute(
                'INSERT INTO Segments (meeting_id, original_text) VALUES (?, ?)',
                (meeting_id, segment_text)
            )
            inserted_segments += 1

            progress = 55 + int((index / total_segments) * 35)
            _set_upload_job_state(upload_id, {
                'progress': min(progress, 95),
                'message': f'Saving extracted content ({inserted_segments}/{total_segments})',
                'meeting_id': meeting_id,
                'segments_count': inserted_segments,
            })

        conn.commit()
        conn.close()

        _set_upload_job_state(upload_id, {
            'status': 'completed',
            'phase': 'completed',
            'progress': 100,
            'message': 'Document extraction completed',
            'meeting_id': meeting_id,
            'segments_count': inserted_segments,
            'meeting_date': meeting_date,
        })
    except Exception as exc:
        logging.error(f"Upload job failed for {original_filename}: {exc}")
        _set_upload_job_state(upload_id, {
            'status': 'failed',
            'phase': 'failed',
            'progress': 100,
            'message': 'Document extraction failed',
            'error': str(exc),
            'meeting_date': meeting_date,
            'source_filename': source_filename,
        })
    finally:
        _cleanup_temp_upload_file(temp_filepath)

@app.route('/api/upload', methods=['POST'])
@jwt_required()
def upload_file():
    """Upload a file and process it asynchronously with progress reporting."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Validate file type
        allowed_extensions = {'.pdf', '.docx', '.txt', '.png', '.jpg', '.jpeg', '.tiff', '.tif', '.webp'}
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed_extensions:
            return jsonify({'error': f'Unsupported file type: {ext}. Allowed: PDF, DOCX, TXT, PNG, JPG, JPEG, TIFF'}), 400

        meeting_date_match = re.search(r'(\d{4}-\d{2}-\d{2})', file.filename)
        meeting_date = meeting_date_match.group(1) if meeting_date_match else datetime.now().strftime('%Y-%m-%d')

        # Save file temporarily and process it in a background worker so the UI can poll progress.
        import uuid
        from werkzeug.utils import secure_filename
        upload_id = uuid.uuid4().hex
        temp_filename = f"{upload_id}_{secure_filename(file.filename)}"
        temp_filepath = os.path.join(_get_temp_upload_dir(), temp_filename)

        file.save(temp_filepath)

        _set_upload_job_state(upload_id, {
            'upload_id': upload_id,
            'status': 'queued',
            'phase': 'queued',
            'progress': 0,
            'message': 'File received, starting extraction',
            'source_filename': file.filename,
            'meeting_date': meeting_date,
            'meeting_metadata': None,
            'meeting_id': None,
            'segments_count': 0,
            'error': None,
            'created_at': datetime.now(timezone.utc).isoformat(),
        })

        thread = threading.Thread(
            target=_process_upload_job,
            args=(upload_id, temp_filepath, file.filename, meeting_date, None),
            daemon=True,
        )
        thread.start()

        return jsonify({
            'message': 'File upload accepted. Extraction is running in the background.',
            'upload_id': upload_id,
            'status': 'queued',
            'progress': 0,
            'meeting_date': meeting_date,
            'source_filename': file.filename,
            'meeting_metadata': None,
        }), 202

    except Exception as e:
        logging.error(f"Upload error: {e}")
        return jsonify({'error': 'Upload failed'}), 500

@app.route('/api/upload/multiple', methods=['POST'])
@jwt_required()
def upload_multiple_files():
    """Upload and process multiple files."""
    try:
        if 'files' not in request.files:
            return jsonify({'error': 'No files provided'}), 400
        
        files = request.files.getlist('files')
        if not files or all(file.filename == '' for file in files):
            return jsonify({'error': 'No files selected'}), 400
        
        results = []
        total_segments = 0
        raw_metadata = request.form.get('meeting_metadata') or request.form.get('metadata')
        batch_metadata = None
        if raw_metadata:
            try:
                batch_metadata = json.loads(raw_metadata)
            except Exception:
                batch_metadata = {'raw': str(raw_metadata)}
        
        for file in files:
            if file.filename == '':
                continue
                
            # Validate file type
            allowed_extensions = {'.pdf', '.docx', '.txt', '.png', '.jpg', '.jpeg', '.tiff'}
            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in allowed_extensions:
                results.append({
                    'filename': file.filename,
                    'status': 'error',
                    'error': f'Unsupported file type: {ext}. Allowed: PDF, DOCX, TXT, PNG, JPG, JPEG, TIFF'
                })
                continue
            
            try:
                if ext == '.txt':
                    raw_text = file.read().decode('utf-8', errors='replace')
                    segments = transform_text(raw_text)
                    temp_filepath = None
                else:
                    # Save file temporarily
                    import uuid
                    from werkzeug.utils import secure_filename
                    temp_filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
                    temp_filepath = os.path.join(_get_temp_upload_dir(), temp_filename)
                    file.save(temp_filepath)
                    
                    # Extract and process text
                    raw_text = extract_text(temp_filepath)
                    segments = transform_text(raw_text)
                
                # Extract meeting date
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', file.filename)
                meeting_date = date_match.group(1) if date_match else datetime.now().strftime('%Y-%m-%d')
                source_filename = file.filename
                
                # Store in database
                conn = get_db()
                cursor = conn.cursor()
                
                cursor.execute(
                    'INSERT INTO Meetings (meeting_date, source_filename, metadata) VALUES (?, ?, ?)',
                    (meeting_date, source_filename, json.dumps(batch_metadata) if isinstance(batch_metadata, dict) else None)
                )
                meeting_id = cursor.lastrowid
                
                for segment_text in segments:
                    if segment_text.strip():
                        cursor.execute(
                            'INSERT INTO Segments (meeting_id, original_text) VALUES (?, ?)',
                            (meeting_id, segment_text)
                        )
                
                conn.commit()
                conn.close()
                
                # Clean up (only remove temp file if we created one)
                if temp_filepath:
                    try:
                        os.remove(temp_filepath)
                    except:
                        pass
                
                results.append({
                    'filename': file.filename,
                    'status': 'success',
                    'meeting_id': meeting_id,
                    'segments_count': len(segments),
                    'meeting_date': meeting_date,
                    'meeting_metadata': None,
                })
                total_segments += len(segments)
                
            except Exception as file_error:
                results.append({
                    'filename': file.filename,
                    'status': 'error',
                    'error': str(file_error)
                })
                # Clean up on error
                if temp_filepath:
                    try:
                        os.remove(temp_filepath)
                    except:
                        pass
        
        successful_uploads = len([r for r in results if r['status'] == 'success'])
        
        logging.info(f"Multiple file upload completed: {successful_uploads}/{len(results)} successful, total segments: {total_segments}")
        
        return jsonify({
            'message': f'Processed {successful_uploads}/{len(results)} files successfully',
            'results': results,
            'total_segments': total_segments
        }), 200
        
    except Exception as e:
        logging.error(f"Multiple upload error: {e}")
        return jsonify({'error': 'Upload failed'}), 500

def _build_realtime_analytics_snapshot(limit=20):
    """Build a realtime analytics snapshot from transcript analysis outputs."""
    if not transcripts_table_exists():
        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'stats': {
                'totalRecordings': 0,
                'avgSentimentScore': 0,
                'mostFrequentKeyword': None,
                'analyzedCount': 0,
            },
            'liveFeed': [],
            'charts': {
                'sentimentDistribution': {'labels': [], 'datasets': [{'label': 'Sentiment', 'data': [], 'backgroundColor': ['#22c55e', '#ef4444', '#64748b', '#f59e0b']}]},
                'keywordFrequency': {'labels': [], 'datasets': [{'label': 'Keyword Frequency', 'data': [], 'backgroundColor': '#2563eb'}]},
                'sentimentTrend': {'labels': [], 'datasets': [{'label': 'Avg Sentiment Score', 'data': [], 'borderColor': '#8b5cf6', 'backgroundColor': 'rgba(139, 92, 246, 0.15)', 'fill': True, 'tension': 0.25}]},
            },
        }

    total_recordings_row = execute_safe_query('''
        SELECT COUNT(*) AS total
        FROM Transcripts
        WHERE COALESCE(is_deleted, 0) = 0
    ''')
    total_recordings = total_recordings_row[0]['total'] if total_recordings_row else 0

    avg_sentiment_row = execute_safe_query('''
        SELECT AVG(
            CASE LOWER(COALESCE(sentiment, 'neutral'))
                WHEN 'positive' THEN 1.0
                WHEN 'negative' THEN -1.0
                ELSE 0.0
            END
        ) AS avg_score
        FROM Transcripts
        WHERE analysis_complete = 1
    ''')
    avg_sentiment_score = round(float(avg_sentiment_row[0]['avg_score'] or 0), 3) if avg_sentiment_row else 0

    transcripts = execute_safe_query(
        '''
        SELECT transcript_id, transcript_text, sentiment, keywords, created_at
        FROM Transcripts
        ORDER BY created_at DESC
        LIMIT ?
        ''',
        (limit,)
    )

    sentiment_distribution = execute_safe_query('''
        SELECT UPPER(COALESCE(sentiment, 'NEUTRAL')) AS sentiment, COUNT(*) AS count
        FROM Transcripts
        WHERE analysis_complete = 1
          AND COALESCE(is_deleted, 0) = 0
        GROUP BY UPPER(COALESCE(sentiment, 'NEUTRAL'))
        ORDER BY count DESC
    ''')

    trend_rows = execute_safe_query('''
        SELECT
            strftime('%Y-%m-%d %H:00', created_at) AS bucket,
            AVG(
                CASE LOWER(COALESCE(sentiment, 'neutral'))
                    WHEN 'positive' THEN 1.0
                    WHEN 'negative' THEN -1.0
                    ELSE 0.0
                END
            ) AS avg_score,
            COUNT(*) AS total
        FROM Transcripts
        WHERE created_at >= datetime('now', '-24 hours')
        GROUP BY strftime('%Y-%m-%d %H:00', created_at)
        ORDER BY bucket
    ''')

    keyword_rows = execute_safe_query('''
        SELECT COALESCE(keywords, '') AS keywords
        FROM Transcripts
        WHERE created_at >= datetime('now', '-7 days')
          AND COALESCE(keywords, '') <> ''
    ''')
    keyword_counts = {}
    for row in keyword_rows:
        for keyword in str(row.get('keywords') or '').split(','):
            normalized = keyword.strip().lower()
            if normalized:
                keyword_counts[normalized] = keyword_counts.get(normalized, 0) + 1

    top_keywords = sorted(keyword_counts.items(), key=lambda item: item[1], reverse=True)[:15]

    return {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'stats': {
            'totalRecordings': total_recordings,
            'avgSentimentScore': avg_sentiment_score,
            'mostFrequentKeyword': top_keywords[0][0] if top_keywords else None,
            'analyzedCount': sum(item['count'] for item in sentiment_distribution),
        },
        'liveFeed': transcripts,
        'charts': {
            'sentimentDistribution': {
                'labels': [item['sentiment'] for item in sentiment_distribution],
                'datasets': [{
                    'label': 'Sentiment',
                    'data': [item['count'] for item in sentiment_distribution],
                    'backgroundColor': ['#22c55e', '#ef4444', '#64748b', '#f59e0b'],
                }],
            },
            'keywordFrequency': {
                'labels': [item[0] for item in top_keywords],
                'datasets': [{
                    'label': 'Keyword Frequency',
                    'data': [item[1] for item in top_keywords],
                    'backgroundColor': '#2563eb',
                }],
            },
            'sentimentTrend': {
                'labels': [item['bucket'] for item in trend_rows],
                'datasets': [{
                    'label': 'Avg Sentiment Score',
                    'data': [round(float(item['avg_score'] or 0), 3) for item in trend_rows],
                    'borderColor': '#8b5cf6',
                    'backgroundColor': 'rgba(139, 92, 246, 0.15)',
                    'fill': True,
                    'tension': 0.25,
                }],
            },
        },
    }


@app.route('/api/dashboard/realtime', methods=['GET'])
def get_realtime_dashboard():
    """Realtime dashboard data for transcript analytics."""
    try:
        stream_token = (request.args.get('token') or '').strip()
        if stream_token:
            decode_token(stream_token)

        recent_data = execute_safe_query('''
            SELECT
                COUNT(DISTINCT m.meeting_id) as new_meetings_24h,
                COUNT(s.segment_id) as new_segments_24h
            FROM Meetings m
            LEFT JOIN Segments s ON m.meeting_id = s.meeting_id
            WHERE m.created_at >= datetime('now', '-24 hours')
        ''')
        recent_stats = recent_data[0] if recent_data else {'new_meetings_24h': 0, 'new_segments_24h': 0}
        snapshot = _build_realtime_analytics_snapshot(limit=10)

        return jsonify({
            'recentStats': recent_stats,
            'realtimeAnalytics': snapshot,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }), 200
    except Exception as e:
        logging.error(f"Realtime dashboard error: {e}")
        return jsonify({'error': 'Realtime data unavailable'}), 500


@app.route('/api/dashboard/stream', methods=['GET'])
def stream_realtime_dashboard():
    """SSE stream for near realtime dashboard updates."""
    stream_token = (request.args.get('token') or '').strip()
    if not stream_token:
        return jsonify({'error': 'Auth token required for realtime stream'}), 401

    try:
        decode_token(stream_token)
    except Exception:
        return jsonify({'error': 'Invalid or expired token for realtime stream'}), 401

    def event_stream():
        while True:
            try:
                payload = _build_realtime_analytics_snapshot(limit=10)
                yield f"event: analytics\\ndata: {json.dumps(payload)}\\n\\n"
                time.sleep(3)
            except GeneratorExit:
                break
            except Exception as exc:
                error_payload = {'error': str(exc), 'timestamp': datetime.now(timezone.utc).isoformat()}
                yield f"event: error\\ndata: {json.dumps(error_payload)}\\n\\n"
                time.sleep(3)

    return Response(
        event_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )

@app.route('/api/upload/status/<upload_id>', methods=['GET'])
@jwt_required()
def get_upload_status(upload_id):
    """Get progress for an in-flight upload/extraction job."""
    job = _get_upload_job_state(upload_id)
    if not job:
        return jsonify({'error': 'Upload job not found', 'upload_id': upload_id}), 404

    return jsonify(job), 200


@app.route('/api/_routecheck', methods=['GET'])
def routecheck():
    """Diagnostics endpoint to verify active routes in the running server."""
    routes = sorted([rule.rule for rule in app.url_map.iter_rules() if rule.rule.startswith('/api/')])
    return jsonify({'count': len(routes), 'routes': routes}), 200

@app.route('/api/activity/logs', methods=['GET'])
@app.route('/api/activity/logins', methods=['GET'])
@jwt_required()
def get_activity_logs():
    """Get real login/logout activity with metadata for admin interface. Supports archived/active filters & advanced search."""
    try:
        claims = get_jwt()
        if claims.get('role') not in ['admin', 'super_admin']:
            return jsonify({'error': 'Admin access required'}), 403

        # Parse params
        limit = int(request.args.get('limit', 50))
        days = int(request.args.get('days', 7))
        archived_param = request.args.get('archived', None)  # 'true', 'false', 'all', None (false)
        start_date = request.args.get('start_date', None)
        end_date = request.args.get('end_date', None)
        user_id_str = request.args.get('user_id', None)
        status = request.args.get('status', None)
        device_type = request.args.get('device_type', None)
        location = request.args.get('location', None)

        # Build WHERE clause dynamically
        where_conditions = []
        params = []

        # Action filter (always)
        where_conditions.append("al.action IN ('login', 'logout', 'failed_login')")

        # Archived filter
        if archived_param is None or archived_param.lower() == 'false':
            where_conditions.append("al.archived_at IS NULL")
        elif archived_param.lower() == 'true':
            where_conditions.append("al.archived_at IS NOT NULL")
        # 'all' or no param: no filter

        # Date range
        if start_date:
            where_conditions.append("al.timestamp >= ?")
            params.append(start_date)
        if end_date:
            where_conditions.append("al.timestamp <= ?")
            params.append(end_date)
        elif days:  # Legacy days param
            where_conditions.append("al.timestamp >= datetime('now', ?)")
            params.append(f"-{days} days")

        # User ID
        if user_id_str:
            where_conditions.append("al.user_id = ? OR u.user_id = ?")
            params.extend([user_id_str, user_id_str])

        # Status
        if status:
            where_conditions.append("LOWER(al.login_status) LIKE LOWER(?)")
            params.append(f'%{status}%')

        # Device type
        if device_type:
            where_conditions.append("LOWER(al.device_type) LIKE LOWER(?)")
            params.append(f'%{device_type}%')

        # Location (city/country/region)
        if location:
            where_conditions.append("(LOWER(al.city) LIKE LOWER(?) OR LOWER(al.country) LIKE LOWER(?) OR LOWER(al.region) LIKE LOWER(?))")
            loc_param = f'%{location}%'
            params.extend([loc_param, loc_param, loc_param])

        where_clause = " AND ".join(where_conditions)

        query = f'''
            SELECT
                al.log_id,
                al.user_id,
                COALESCE(al.username, u.username, 'unknown') AS username,
                al.action,
                al.details,
                COALESCE(al.ip_address, '') AS ip_address,
                COALESCE(al.user_agent, '') AS user_agent,
                COALESCE(al.login_status, '') AS login_status,
                COALESCE(al.device_type, '') AS device_type,
                COALESCE(al.browser, '') AS browser,
                COALESCE(al.os, '') AS os,
                COALESCE(al.country, '') AS country,
                COALESCE(al.region, '') AS region,
                COALESCE(al.city, '') AS city,
                al.latitude,
                al.longitude,
                al.timestamp,
                al.archived_at
            FROM AuditLogs al
            LEFT JOIN Users u ON al.user_id = u.user_id
            WHERE {where_clause}
            ORDER BY al.timestamp DESC
            LIMIT ?
        '''

        params.append(limit)

        logs = execute_safe_query(query, params)

        # Rest of processing unchanged...
        def _pick_non_empty(*values):
            for value in values:
                if value is None:
                    continue
                if isinstance(value, str):
                    normalized = value.strip()
                    if not normalized:
                        continue
                    if normalized.lower() in {'unknown', 'n/a', 'na', 'none', 'null'}:
                        continue
                    return normalized
                return value
            return None

        def _pick_non_empty(*values):
            for value in values:
                if value is None:
                    continue
                if isinstance(value, str):
                    normalized = value.strip()
                    if not normalized:
                        continue
                    if normalized.lower() in {'unknown', 'n/a', 'na', 'none', 'null'}:
                        continue
                    return normalized
                return value
            return None

        events = []
        for row in logs:
            details_obj = {}
            details_raw = row.get('details')
            if isinstance(details_raw, str):
                try:
                    details_obj = json.loads(details_raw)
                except json.JSONDecodeError:
                    details_obj = {'details': details_raw}

            nested_meta = details_obj.get('client_metadata') if isinstance(details_obj.get('client_metadata'), dict) else {}
            nested_location = details_obj.get('location')
            if isinstance(nested_location, dict):
                lat = nested_location.get('latitude')
                lon = nested_location.get('longitude')
                accuracy = nested_location.get('accuracy_m')
                if lat is not None and lon is not None:
                    if accuracy is not None:
                        nested_location = f"{lat}, {lon} (+/-{accuracy}m)"
                    else:
                        nested_location = f"{lat}, {lon}"
                else:
                    nested_location = None

            meta_location = nested_meta.get('location') if isinstance(nested_meta, dict) else None
            if isinstance(meta_location, dict):
                m_lat = meta_location.get('latitude')
                m_lon = meta_location.get('longitude')
                m_acc = meta_location.get('accuracy_m')
                if m_lat is not None and m_lon is not None:
                    if m_acc is not None:
                        meta_location = f"{m_lat}, {m_lon} (+/-{m_acc}m)"
                    else:
                        meta_location = f"{m_lat}, {m_lon}"
                else:
                    meta_location = None

            device_value = _pick_non_empty(
                details_obj.get('device_name'),
                details_obj.get('device'),
                nested_meta.get('device_name'),
                nested_meta.get('device'),
                row.get('user_agent'),
                details_obj.get('user_agent'),
                nested_meta.get('user_agent'),
                details_obj.get('platform'),
                nested_meta.get('platform'),
            )

            location_value = _pick_non_empty(
                nested_location,
                meta_location,
                row.get('city') and row.get('country') and f"{row.get('city')}, {row.get('country')}",
                row.get('city'),
                row.get('country'),
                details_obj.get('city'),
                details_obj.get('country'),
                details_obj.get('timezone'),
                nested_meta.get('timezone'),
            )

            ip_value = _pick_non_empty(
                row.get('ip_address'),
                details_obj.get('ip_address'),
                nested_meta.get('client_ip'),
                nested_meta.get('ip_address'),
            )

            events.append({
                'id': row.get('log_id'),
                'user_id': row.get('user_id'),
                'username': row.get('username') or 'unknown',
                'action': row.get('action') or 'unknown',
                'login_status': _pick_non_empty(
                    row.get('login_status'),
                    details_obj.get('login_status'),
                    'failed' if row.get('action') == 'failed_login' else 'success',
                ),
                'timestamp': row.get('timestamp'),
                'archived_at': row.get('archived_at'),
                'ip_address': ip_value or 'Unknown',
                'device': device_value or 'Unknown',
                'device_type': _pick_non_empty(
                    row.get('device_type'),
                    details_obj.get('device_type'),
                    nested_meta.get('device_type'),
                ) or 'desktop',
                'browser': _pick_non_empty(
                    row.get('browser'),
                    details_obj.get('browser'),
                    nested_meta.get('browser'),
                ) or 'Unknown',
                'os': _pick_non_empty(
                    row.get('os'),
                    details_obj.get('os'),
                    nested_meta.get('os'),
                ) or 'Unknown',
                'country': _pick_non_empty(row.get('country'), details_obj.get('country'), nested_meta.get('country')),
                'region': _pick_non_empty(row.get('region'), details_obj.get('region'), nested_meta.get('region')),
                'city': _pick_non_empty(row.get('city'), details_obj.get('city'), nested_meta.get('city')),
                'latitude': row.get('latitude') if row.get('latitude') is not None else details_obj.get('latitude'),
                'longitude': row.get('longitude') if row.get('longitude') is not None else details_obj.get('longitude'),
                'user_agent': row.get('user_agent') or details_obj.get('user_agent') or nested_meta.get('user_agent') or '',
                'location': location_value or 'Unknown',
                'details': details_obj.get('details') or '',
            })
        
        return jsonify({
            'logs': logs,
            'events': events,
            'recent_sessions': events,
            'total_logs': len(logs),
            'filters': {
                'limit': limit,
                'days': days,
                'archived': archived_param,
                'start_date': start_date,
                'end_date': end_date,
                'user_id': user_id_str,
                'status': status,
                'device_type': device_type,
                'location': location
            }
        }), 200
    except Exception as e:
        logging.error(f"Activity logs error: {e}")
        return jsonify({'error': 'Failed to fetch activity logs'}), 500


@app.route('/api/search', methods=['GET'])
def search_content():
    """Full-text search across Segments + Transcripts."""
    try:
        query = request.args.get('q', '').strip()
        limit = int(request.args.get('limit', 20))
        type_filter = request.args.get('type', 'all')  # segments, transcripts, all
        
        if len(query) < 2:
            return jsonify({'results': [], 'message': 'Query too short (min 2 chars)'}), 200
        
        if type_filter == 'segments':
            results = execute_safe_query('''
                SELECT s.*, m.meeting_date 
                FROM Segments s JOIN Meetings m ON s.meeting_id = m.meeting_id
                WHERE s.original_text LIKE ?
                ORDER BY s.created_at DESC LIMIT ?
            ''', (f'%{query}%', limit))
        elif type_filter == 'transcripts':
            results = execute_safe_query('''
                SELECT * FROM Transcripts 
                WHERE transcript_text LIKE ?
                ORDER BY created_at DESC LIMIT ?
            ''', (f'%{query}%', limit))
        else:
            # Combined search
            results = execute_safe_query('''
                SELECT 'segment' as type, s.*, m.meeting_date as ref_date, NULL as sentiment
                FROM Segments s JOIN Meetings m ON s.meeting_id = m.meeting_id
                WHERE s.original_text LIKE ?
                UNION ALL
                SELECT 'transcript' as type, t.*, NULL as ref_date, t.sentiment
                FROM Transcripts t
                WHERE t.transcript_text LIKE ?
                ORDER BY created_at DESC LIMIT ?
            ''', (f'%{query}%', f'%{query}%', limit))
        
        return jsonify({
            'query': query,
            'results': results,
            'total': len(results),
            'filters': {'type': type_filter, 'limit': limit}
        }), 200
    except Exception as e:
        logging.error(f"Search error: {e}")
        return jsonify({'error': 'Search failed'}), 500


@app.route('/api/reports', methods=['GET'])
@jwt_required()
def get_reports():
    """Dynamic reports from analyzed data."""
    try:
        report_type = (request.args.get('type', 'summary') or 'summary').strip().lower()
        report_type_aliases = {
            'summary': 'summaries',
            'sentiment': 'sentiments',
            'action': 'action_items',
            'actions': 'action_items',
            'keyword': 'keywords',
            'topic': 'topics',
        }
        report_type = report_type_aliases.get(report_type, report_type)
        meeting_id = request.args.get('meeting_id')
        sentiment_filter = (request.args.get('sentiment') or '').strip().lower()
        start_date = (request.args.get('start_date') or '').strip()
        end_date = (request.args.get('end_date') or '').strip()
        format_ = request.args.get('format', 'json')  # json, csv, pdf
        
        if report_type == 'action_items':
            query = '''
                SELECT ai.*, s.original_text as context, m.meeting_id, m.meeting_date,
                       COALESCE(aconf.confidence_score, 0) as confidence
                FROM ActionItems ai
                JOIN Segments s ON ai.segment_id = s.segment_id
                JOIN Meetings m ON s.meeting_id = m.meeting_id
                LEFT JOIN (
                    SELECT segment_id, MAX(confidence_score) as confidence_score
                    FROM Analysis
                    GROUP BY segment_id
                ) aconf ON aconf.segment_id = ai.segment_id
            '''
            params = []
            if meeting_id:
                query += ' WHERE m.meeting_id = ?'
                params = [meeting_id]
            query += ' ORDER BY ai.created_at DESC LIMIT 500'
        elif report_type == 'summaries':
            query = '''
                SELECT sm.summary_id, sm.meeting_id, sm.segment_id, sm.summary_text, sm.created_at, m.meeting_date,
                       COALESCE(sm.confidence_score, aconf.confidence_score, 0) as confidence
                FROM Summaries sm
                JOIN Meetings m ON sm.meeting_id = m.meeting_id
                LEFT JOIN (
                    SELECT s.meeting_id as meeting_id, AVG(COALESCE(a.confidence_score, 0)) as confidence_score
                    FROM Analysis a
                    JOIN Segments s ON a.segment_id = s.segment_id
                    GROUP BY s.meeting_id
                ) aconf ON aconf.meeting_id = sm.meeting_id
                WHERE sm.summary_id = (
                    SELECT sm2.summary_id
                    FROM Summaries sm2
                    WHERE sm2.meeting_id = sm.meeting_id
                    ORDER BY sm2.created_at DESC, sm2.summary_id DESC
                    LIMIT 1
                )
            '''
            params = []
            if meeting_id:
                query += ' AND m.meeting_id = ?'
                params.append(meeting_id)
            if start_date:
                query += ' AND DATE(sm.created_at) >= DATE(?)'
                params.append(start_date)
            if end_date:
                query += ' AND DATE(sm.created_at) <= DATE(?)'
                params.append(end_date)
            query += ' ORDER BY sm.created_at DESC LIMIT 500'
        elif report_type == 'sentiments':
            query = '''
                SELECT se.sentiment_id, se.segment_id, se.sentiment, se.confidence, se.created_at, m.meeting_id, m.meeting_date
                FROM Sentiments se
                JOIN Segments s ON se.segment_id = s.segment_id
                JOIN Meetings m ON s.meeting_id = m.meeting_id
                WHERE 1=1
            '''
            params = []
            if meeting_id:
                query += ' AND m.meeting_id = ?'
                params.append(meeting_id)
            if sentiment_filter:
                query += ' AND LOWER(COALESCE(se.sentiment, "")) = ?'
                params.append(sentiment_filter)
            if start_date:
                query += ' AND DATE(se.created_at) >= DATE(?)'
                params.append(start_date)
            if end_date:
                query += ' AND DATE(se.created_at) <= DATE(?)'
                params.append(end_date)
            query += ' ORDER BY se.created_at DESC LIMIT 500'
        elif report_type == 'keywords':
            query = '''
                SELECT k.keyword_id, k.segment_id, k.keywords, k.created_at, m.meeting_id, m.meeting_date,
                       COALESCE(aconf.confidence_score, 0) as confidence
                FROM Keywords k
                JOIN Segments s ON k.segment_id = s.segment_id
                JOIN Meetings m ON s.meeting_id = m.meeting_id
                LEFT JOIN (
                    SELECT segment_id, MAX(confidence_score) as confidence_score
                    FROM Analysis
                    GROUP BY segment_id
                ) aconf ON aconf.segment_id = k.segment_id
            '''
            params = []
            if meeting_id:
                query += ' WHERE m.meeting_id = ?'
                params = [meeting_id]
            query += ' ORDER BY k.created_at DESC LIMIT 500'
        elif report_type == 'topics':
            query = '''
                SELECT topic_id, meeting_id, topic_name, confidence_score, keywords, created_at
                FROM Topics
            '''
            params = []
            if meeting_id:
                query += ' WHERE meeting_id = ?'
                params = [meeting_id]
            query += ' ORDER BY created_at DESC LIMIT 500'
        elif report_type == 'themes':
            query = '''
                SELECT t.theme_name, COUNT(a.analysis_id) as occurrences, 
                       GROUP_CONCAT(DISTINCT m.meeting_date) as meetings
                FROM Themes t JOIN Analysis a ON t.theme_id = a.theme_id
                JOIN Segments s ON a.segment_id = s.segment_id
                JOIN Meetings m ON s.meeting_id = m.meeting_id
                GROUP BY t.theme_id ORDER BY occurrences DESC
            '''
            params = []
        elif report_type == 'transcript_analytics':
            if not transcripts_table_exists():
                return jsonify({
                    'type': report_type,
                    'data': [],
                    'generated_at': datetime.now().isoformat(),
                    'message': 'No transcript analytics table found yet.',
                }), 200
            query = '''
                SELECT
                    transcript_id,
                    user_id,
                    transcript_text,
                    COALESCE(sentiment, 'NEUTRAL') AS sentiment,
                    COALESCE(keywords, '') AS keywords,
                    created_at
                FROM Transcripts
                WHERE 1=1
            '''
            params = []
            if sentiment_filter:
                query += ' AND LOWER(COALESCE(sentiment, \"\")) = ?'
                params.append(sentiment_filter)
            if start_date:
                query += ' AND DATE(created_at) >= DATE(?)'
                params.append(start_date)
            if end_date:
                query += ' AND DATE(created_at) <= DATE(?)'
                params.append(end_date)
            query += ' ORDER BY created_at DESC LIMIT 500'
        else:  # summary
            query = '''
                SELECT 
                    COUNT(DISTINCT m.meeting_id) as total_meetings,
                    COUNT(s.segment_id) as total_segments,
                    COUNT(DISTINCT t.theme_id) as unique_themes,
                    COUNT(ai.item_id) as action_items
                FROM Meetings m
                LEFT JOIN Segments s ON m.meeting_id = s.meeting_id
                LEFT JOIN Analysis a ON s.segment_id = a.segment_id
                LEFT JOIN Themes t ON a.theme_id = t.theme_id
                LEFT JOIN ActionItems ai ON s.segment_id = ai.segment_id
            '''
            params = []
        
        results = execute_safe_query(query, params)
        
        if format_ == 'csv':
            import csv
            from io import StringIO
            output = StringIO()
            writer = csv.DictWriter(output, fieldnames=results[0].keys() if results else [])
            writer.writeheader()
            writer.writerows(results)
            return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename=report_{report_type}.csv'})

        if format_ == 'pdf':
            try:
                from io import BytesIO
                letter = importlib.import_module('reportlab.lib.pagesizes').letter
                canvas = importlib.import_module('reportlab.pdfgen.canvas')

                buffer = BytesIO()
                pdf = canvas.Canvas(buffer, pagesize=letter)
                width, height = letter
                y = height - 40

                pdf.setFont('Helvetica-Bold', 14)
                pdf.drawString(40, y, f'ITDS Report: {report_type}')
                y -= 24
                pdf.setFont('Helvetica', 9)
                pdf.drawString(40, y, f'Generated at: {datetime.now(timezone.utc).isoformat()}')
                y -= 18

                if not results:
                    pdf.drawString(40, y, 'No data available for selected filters.')
                else:
                    keys = list(results[0].keys())[:6]
                    for row in results[:80]:
                        if y < 40:
                            pdf.showPage()
                            y = height - 40
                            pdf.setFont('Helvetica', 9)
                        line = ' | '.join(f"{k}: {str(row.get(k, ''))[:40]}" for k in keys)
                        pdf.drawString(40, y, line)
                        y -= 12

                pdf.save()
                pdf_bytes = buffer.getvalue()
                buffer.close()
                return Response(
                    pdf_bytes,
                    mimetype='application/pdf',
                    headers={'Content-Disposition': f'attachment; filename=report_{report_type}.pdf'},
                )
            except Exception as pdf_error:
                logging.error(f'PDF report error: {pdf_error}')
                return jsonify({'error': 'PDF export failed. Ensure reportlab is installed.'}), 500
        
        return jsonify({
            'type': report_type,
            'data': results,
            'generated_at': datetime.now().isoformat()
        }), 200
    except Exception as e:
        logging.error(f"Reports error: {e}")
        return jsonify({'error': 'Report generation failed'}), 500


@app.route('/api/analytics/search', methods=['GET'])
@jwt_required()
def search_transcript_analytics():
    """Search analytics across transcripts and segments with sentiment/date/category filters."""
    try:
        q = (request.args.get('q') or '').strip()
        sentiment = (request.args.get('sentiment') or '').strip().lower()
        start_date = (request.args.get('start_date') or '').strip()
        end_date = (request.args.get('end_date') or '').strip()
        category = (request.args.get('category') or '').strip().lower()
        limit = min(max(int(request.args.get('limit', 50)), 1), 300)

        transcript_results = []
        segment_results = []

        if transcripts_table_exists():
            t_where = ['1=1']
            t_params = []
            if q:
                t_where.append('transcript_text LIKE ?')
                t_params.append(f'%{q}%')
            if sentiment:
                t_where.append('LOWER(COALESCE(sentiment, "")) = ?')
                t_params.append(sentiment)
            if start_date:
                t_where.append('DATE(created_at) >= DATE(?)')
                t_params.append(start_date)
            if end_date:
                t_where.append('DATE(created_at) <= DATE(?)')
                t_params.append(end_date)
            if category:
                t_where.append('LOWER(COALESCE(keywords, "")) LIKE ?')
                t_params.append(f'%{category}%')

            transcript_results = execute_safe_query(
                f'''
                SELECT
                    transcript_id,
                    user_id,
                    transcript_text,
                    COALESCE(sentiment, 'NEUTRAL') AS sentiment,
                    COALESCE(keywords, '') AS keywords,
                    created_at,
                    'transcript' AS source
                FROM Transcripts
                WHERE {' AND '.join(t_where)}
                ORDER BY created_at DESC
                LIMIT ?
                ''',
                t_params + [limit],
            )

        s_where = ['1=1']
        s_params = []
        if q:
            s_where.append('seg.original_text LIKE ?')
            s_params.append(f'%{q}%')
        if sentiment:
            s_where.append('LOWER(COALESCE(sn.sentiment, "")) = ?')
            s_params.append(sentiment)
        if start_date:
            s_where.append('DATE(COALESCE(m.meeting_date, seg.created_at)) >= DATE(?)')
            s_params.append(start_date)
        if end_date:
            s_where.append('DATE(COALESCE(m.meeting_date, seg.created_at)) <= DATE(?)')
            s_params.append(end_date)
        if category:
            s_where.append('(LOWER(COALESCE(k.keywords, "")) LIKE ? OR LOWER(COALESCE(tp.topic_name, "")) LIKE ?)')
            s_params.append(f'%{category}%')
            s_params.append(f'%{category}%')

        segment_results = execute_safe_query(
            f'''
            SELECT
                seg.segment_id AS transcript_id,
                NULL AS user_id,
                seg.original_text AS transcript_text,
                COALESCE(sn.sentiment, 'NEUTRAL') AS sentiment,
                COALESCE(k.keywords, tp.topic_name, '') AS keywords,
                COALESCE(seg.created_at, m.created_at) AS created_at,
                'segment' AS source
            FROM Segments seg
            LEFT JOIN Meetings m ON seg.meeting_id = m.meeting_id
            LEFT JOIN Sentiments sn ON sn.segment_id = seg.segment_id
            LEFT JOIN Keywords k ON k.segment_id = seg.segment_id
            LEFT JOIN Topics tp ON tp.meeting_id = seg.meeting_id
            WHERE {' AND '.join(s_where)}
            GROUP BY seg.segment_id
            ORDER BY created_at DESC
            LIMIT ?
            ''',
            s_params + [limit],
        )

        results = sorted(
            [*transcript_results, *segment_results],
            key=lambda x: x.get('created_at') or '',
            reverse=True,
        )[:limit]

        return jsonify({
            'results': results,
            'total': len(results),
            'filters': {
                'q': q,
                'sentiment': sentiment,
                'start_date': start_date,
                'end_date': end_date,
                'category': category,
                'limit': limit,
            },
        }), 200
    except Exception as exc:
        logging.error(f'Analytics search error: {exc}')
        return jsonify({'error': 'Analytics search failed'}), 500


if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', '0') == '1', host='0.0.0.0', quiet=True)
