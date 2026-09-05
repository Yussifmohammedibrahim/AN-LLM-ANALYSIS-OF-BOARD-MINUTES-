"""
Security Configurations for ITDS Framework
"""
import os
from datetime import timedelta

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'jwt-secret-key-change-in-production'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    
    # Session security
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Database
    SQLALCHEMY_DATABASE_URI = 'sqlite:///../itds_minutes.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # CORS
    CORS_ORIGINS = ['http://localhost:3000']

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SESSION_COOKIE_SECURE = False

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    
    # Use stronger keys in production
    SECRET_KEY = os.environ.get('SECRET_KEY')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY')

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

# Allowed themes for validation
ALLOWED_THEMES = [
    "Curriculum Development",
    "Student Internships",
    "Tech Fair",
    "Faculty Research",
    "Examinations",
    "Infrastructure Development",
    "Accreditation",
    "Budget Planning",
    "Staff Development",
    "Student Affairs"
]

# Allowed roles
ALLOWED_ROLES = ['super_admin', 'admin', 'editor', 'viewer']

# Rate limiting
RATE_LIMIT_PER_MINUTE = 100
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = 15  # minutes