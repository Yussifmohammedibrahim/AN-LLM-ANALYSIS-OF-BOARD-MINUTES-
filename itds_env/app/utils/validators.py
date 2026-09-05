"""
Input Validation Utilities
Provides validation functions for user input and data validation.
"""
import re
from typing import Optional, List, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


# ============================================
# Constants
# ============================================

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

ALLOWED_FILE_EXTENSIONS = {
    '.pdf': 'application/pdf',
    '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.txt': 'text/plain'
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

DISPOSABLE_EMAIL_DOMAINS = [
    'tempmail.com', 'throwaway.com', 'fakeinbox.com',
    'guerrillamail.com', 'mailinator.com', '10minutemail.com',
    'sharklasers.com', 'spam4.me', 'grr.la', 'maildrop.cc'
]


# ============================================
# Validation Result Dataclass
# ============================================

@dataclass
class ValidationResult:
    """
    Result of validation check.
    
    Attributes:
        is_valid: Whether validation passed
        errors: List of error messages
    """
    is_valid: bool
    errors: List[str]
    
    @property
    def error_message(self) -> str:
        """Get errors as a single message."""
        return '; '.join(self.errors) if self.errors else ''
    
    def add_error(self, error: str) -> None:
        """Add an error to the result."""
        self.errors.append(error)
        self.is_valid = False
    
    def __bool__(self) -> bool:
        """Allow using ValidationResult in boolean context."""
        return self.is_valid


# ============================================
# Base Validator
# ============================================

class BaseValidator:
    """Base class for validators."""
    
    @staticmethod
    def validate(value: Any, rules: dict) -> ValidationResult:
        """
        Validate a value against rules.
        
        Args:
            value: Value to validate
            rules: Dictionary of validation rules
        
        Returns:
            ValidationResult object
        """
        result = ValidationResult(is_valid=True, errors=[])
        
        # Required check
        if rules.get('required', False):
            if value is None or (isinstance(value, str) and not value.strip()):
                result.add_error('This field is required')
                return result
        
        # Skip further validation if value is empty and not required
        if value is None or (isinstance(value, str) and not value.strip()):
            return result
        
        # Type validation
        if 'type' in rules:
            result = BaseValidator._validate_type(value, rules['type'], result)
            if not result.is_valid:
                return result
        
        # String validations
        if isinstance(value, str):
            result = BaseValidator._validate_string(value, rules, result)
        
        # Numeric validations
        if isinstance(value, (int, float)):
            result = BaseValidator._validate_numeric(value, rules, result)
        
        return result
    
    @staticmethod
    def _validate_type(value: Any, expected_type: str, result: ValidationResult) -> ValidationResult:
        """Validate value type."""
        type_map = {
            'str': str,
            'int': int,
            'float': float,
            'bool': bool,
            'email': str,
            'url': str
        }
        
        expected = type_map.get(expected_type)
        if expected and not isinstance(value, expected):
            result.add_error(f'Must be of type {expected_type}')
        return result
    
    @staticmethod
    def _validate_string(value: str, rules: dict, result: ValidationResult) -> ValidationResult:
        """Validate string value."""
        # Min length
        if 'min_length' in rules and len(value) < rules['min_length']:
            result.add_error(f'Must be at least {rules["min_length"]} characters')
        
        # Max length
        if 'max_length' in rules and len(value) > rules['max_length']:
            result.add_error(f'Must be at most {rules["max_length"]} characters')
        
        # Pattern
        if 'pattern' in rules:
            if not re.match(rules['pattern'], value):
                if 'pattern_error' in rules:
                    result.add_error(rules['pattern_error'])
                else:
                    result.add_error('Invalid format')
        
        # Email
        if rules.get('is_email') and not BaseValidator._is_valid_email(value):
            result.add_error('Invalid email address')
        
        # URL
        if rules.get('is_url') and not BaseValidator._is_valid_url(value):
            result.add_error('Invalid URL')
        
        return result
    
    @staticmethod
    def _validate_numeric(value: float, rules: dict, result: ValidationResult) -> ValidationResult:
        """Validate numeric value."""
        if 'min' in rules and value < rules['min']:
            result.add_error(f'Must be at least {rules["min"]}')
        
        if 'max' in rules and value > rules['max']:
            result.add_error(f'Must be at most {rules["max"]}')
        
        return result
    
    @staticmethod
    def _is_valid_email(email: str) -> bool:
        """Check if email is valid."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def _is_valid_url(url: str) -> bool:
        """Check if URL is valid."""
        pattern = r'^https?:\/\/[\w\-]+(\.[\w\-]+)+[/#?]?.*$'
        return bool(re.match(pattern, url))


# ============================================
# Username Validator
# ============================================

class UsernameValidator:
    """
    Validator for usernames.
    
    Rules:
    - 3-20 characters
    - Only alphanumeric and underscores
    - Must start with a letter
    """
    
    MIN_LENGTH = 3
    MAX_LENGTH = 20
    
    @staticmethod
    def validate(username: str) -> ValidationResult:
        """Validate username."""
        result = ValidationResult(is_valid=True, errors=[])
        
        if not username:
            result.add_error('Username is required')
            return result
        
        if len(username) < UsernameValidator.MIN_LENGTH:
            result.add_error(f'Username must be at least {UsernameValidator.MIN_LENGTH} characters')
        
        if len(username) > UsernameValidator.MAX_LENGTH:
            result.add_error(f'Username must be at most {UsernameValidator.MAX_LENGTH} characters')
        
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', username):
            result.add_error('Username must start with a letter and contain only letters, numbers, and underscores')
        
        if '__' in username:
            result.add_error('Username cannot contain consecutive underscores')
        
        if username.startswith('_') or username.endswith('_'):
            result.add_error('Username cannot start or end with an underscore')
        
        return result
    
    @staticmethod
    def is_valid(username: str) -> bool:
        """Check if username is valid."""
        result = UsernameValidator.validate(username)
        return result.is_valid


# ============================================
# Password Validator
# ============================================

class PasswordValidator:
    """Validator for passwords."""
    
    DEFAULT_MIN_LENGTH = 8
    
    @staticmethod
    def validate(password: str, min_length: int = None) -> ValidationResult:
        """Validate password strength."""
        if min_length is None:
            min_length = PasswordValidator.DEFAULT_MIN_LENGTH
        
        result = ValidationResult(is_valid=True, errors=[])
        
        if not password:
            result.add_error('Password is required')
            return result
        
        if len(password) < min_length:
            result.add_error(f'Password must be at least {min_length} characters')
        
        if not re.search(r'[A-Z]', password):
            result.add_error('Password must contain at least one uppercase letter')
        
        if not re.search(r'[a-z]', password):
            result.add_error('Password must contain at least one lowercase letter')
        
        if not re.search(r'\d', password):
            result.add_error('Password must contain at least one number')
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            result.add_error('Password must contain at least one special character')
        
        return result
    
    @staticmethod
    def check_strength(password: str) -> Tuple[str, int]:
        """Check password strength."""
        score = 0
        
        if len(password) >= 8:
            score += 1
        if len(password) >= 12:
            score += 1
        if len(password) >= 16:
            score += 1
        if re.search(r'[A-Z]', password):
            score += 1
        if re.search(r'[a-z]', password):
            score += 1
        if re.search(r'\d', password):
            score += 1
        if re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            score += 1
        
        levels = {
            0: 'Very Weak',
            1: 'Weak',
            2: 'Fair',
            3: 'Medium',
            4: 'Strong',
            5: 'Very Strong',
            6: 'Excellent'
        }
        
        return levels.get(min(score, 6), 'Unknown'), score
    
    @staticmethod
    def get_requirements(min_length: int = None) -> dict:
        """Get password requirements."""
        if min_length is None:
            min_length = PasswordValidator.DEFAULT_MIN_LENGTH
        
        return {
            'min_length': min_length,
            'require_uppercase': True,
            'require_lowercase': True,
            'require_number': True,
            'require_special': True
        }


# ============================================
# Email Validator
# ============================================

class EmailValidator:
    """Validator for email addresses."""
    
    EMAIL_PATTERN = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    @staticmethod
    def validate(email: str, allow_disposable: bool = False) -> ValidationResult:
        """Validate email address."""
        result = ValidationResult(is_valid=True, errors=[])
        
        if not email:
            result.add_error('Email is required')
            return result
        
        if not re.match(EmailValidator.EMAIL_PATTERN, email):
            result.add_error('Invalid email address')
            return result
        
        if not allow_disposable:
            domain = email.split('@')[-1].lower()
            if domain in DISPOSABLE_EMAIL_DOMAINS:
                result.add_error('Disposable email addresses are not allowed')
        
        if email.count('@') != 1:
            result.add_error('Invalid email format')
        
        if '..' in email:
            result.add_error('Invalid email format')
        
        return result
    
    @staticmethod
    def is_valid(email: str, allow_disposable: bool = False) -> bool:
        """Check if email is valid."""
        result = EmailValidator.validate(email, allow_disposable)
        return result.is_valid
    
    @staticmethod
    def extract_domain(email: str) -> Optional[str]:
        """Extract domain from email."""
        if '@' in email:
            return email.split('@')[-1].lower()
        return None


# ============================================
# Theme Validator
# ============================================

class ThemeValidator:
    """Validator for meeting themes."""
    
    ALLOWED_THEMES = ALLOWED_THEMES
    
    @staticmethod
    def validate(theme: str) -> ValidationResult:
        """Validate theme against allowed list."""
        result = ValidationResult(is_valid=True, errors=[])
        
        if not theme:
            result.add_error('Theme is required')
            return result
        
        if theme not in ThemeValidator.ALLOWED_THEMES:
            result.add_error(f'Invalid theme. Allowed themes: {", ".join(ThemeValidator.ALLOWED_THEMES)}')
        
        return result
    
    @staticmethod
    def is_valid(theme: str) -> bool:
        """Check if theme is valid."""
        result = ThemeValidator.validate(theme)
        return result.is_valid
    
    @staticmethod
    def get_allowed_themes() -> List[str]:
        """Get list of allowed themes."""
        return ThemeValidator.ALLOWED_THEMES


# ============================================
# Year Validator
# ============================================

class YearValidator:
    """Validator for year values."""
    
    MIN_YEAR = 2000
    MAX_YEAR = datetime.now().year + 1
    
    @staticmethod
    def validate(year: str) -> ValidationResult:
        """Validate year format (YYYY)."""
        result = ValidationResult(is_valid=True, errors=[])
        
        if not year:
            result.add_error('Year is required')
            return result
        
        if not re.match(r'^\d{4}$', year):
            result.add_error('Year must be in YYYY format')
            return result
        
        year_int = int(year)
        if year_int < YearValidator.MIN_YEAR:
            result.add_error(f'Year must be at least {YearValidator.MIN_YEAR}')
        
        if year_int > YearValidator.MAX_YEAR:
            result.add_error(f'Year must be at most {YearValidator.MAX_YEAR}')
        
        return result
    
    @staticmethod
    def is_valid(year: str) -> bool:
        """Check if year is valid."""
        result = YearValidator.validate(year)
        return result.is_valid


# ============================================
# Search Query Validator
# ============================================

class SearchQueryValidator:
    """Validator for search queries."""
    
    MIN_LENGTH = 3
    MAX_LENGTH = 100
    
    @staticmethod
    def validate(query: str) -> ValidationResult:
        """Validate search query."""
        result = ValidationResult(is_valid=True, errors=[])
        
        if not query:
            result.add_error('Search query is required')
            return result
        
        if len(query) < SearchQueryValidator.MIN_LENGTH:
            result.add_error(f'Search query must be at least {SearchQueryValidator.MIN_LENGTH} characters')
        
        if len(query) > SearchQueryValidator.MAX_LENGTH:
            result.add_error(f'Search query must be at most {SearchQueryValidator.MAX_LENGTH} characters')
        
        dangerous_patterns = [
            (r'<script', 'Invalid search query'),
            (r'javascript:', 'Invalid search query'),
            (r'--', 'Invalid search query'),
            (r'\/\*', 'Invalid search query'),
            (r'\*\/', 'Invalid search query')
        ]
        
        for pattern, error_msg in dangerous_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                result.add_error(error_msg)
                break
        
        return result
    
    @staticmethod
    def is_valid(query: str) -> bool:
        """Check if search query is valid."""
        result = SearchQueryValidator.validate(query)
        return result.is_valid


# ============================================
# File Validator
# ============================================

class FileValidator:
    """Validator for file uploads."""
    
    ALLOWED_EXTENSIONS = ALLOWED_FILE_EXTENSIONS
    MAX_FILE_SIZE = MAX_FILE_SIZE
    
    @staticmethod
    def validate(filename: str, file_size: int, content_type: str = None) -> ValidationResult:
        """Validate file upload."""
        result = ValidationResult(is_valid=True, errors=[])
        
        if not filename:
            result.add_error('Filename is required')
            return result
        
        # Check extension
        ext = Path(filename).suffix.lower()
        if ext not in FileValidator.ALLOWED_EXTENSIONS:
            result.add_error(f'Invalid file type. Allowed: {", ".join(FileValidator.ALLOWED_EXTENSIONS.keys())}')
        
        # Check size
        if file_size > FileValidator.MAX_FILE_SIZE:
            max_size_mb = FileValidator.MAX_FILE_SIZE / (1024 * 1024)
            result.add_error(f'File too large. Maximum size: {max_size_mb:.0f}MB')
        
        return result
    
    @staticmethod
    def get_extension(filename: str) -> str:
        """Get file extension."""
        return Path(filename).suffix.lower()
    
    @staticmethod
    def is_allowed(filename: str) -> bool:
        """Check if file extension is allowed."""
        ext = FileValidator.get_extension(filename)
        return ext in FileValidator.ALLOWED_EXTENSIONS


# ============================================
# Role Validator
# ============================================

class RoleValidator:
    """Validator for user roles."""
    
    ALLOWED_ROLES = ['super_admin', 'admin', 'editor', 'viewer']
    
    @staticmethod
    def validate(role: str) -> ValidationResult:
        """Validate user role."""
        result = ValidationResult(is_valid=True, errors=[])
        
        if not role:
            result.add_error('Role is required')
            return result
        
        if role not in RoleValidator.ALLOWED_ROLES:
            result.add_error(f'Invalid role. Allowed roles: {", ".join(RoleValidator.ALLOWED_ROLES)}')
        
        return result
    
    @staticmethod
    def is_valid(role: str) -> bool:
        """Check if role is valid."""
        result = RoleValidator.validate(role)
        return result.is_valid
    
    @staticmethod
    def get_allowed_roles() -> List[str]:
        """Get list of allowed roles."""
        return RoleValidator.ALLOWED_ROLES


# ============================================
# Convenience Functions
# ============================================

def validate_username(username: str) -> ValidationResult:
    """Validate username (convenience function)."""
    return UsernameValidator.validate(username)


def validate_password(password: str, min_length: int = 8) -> ValidationResult:
    """Validate password (convenience function)."""
    return PasswordValidator.validate(password, min_length)


def check_password_strength(password: str) -> Tuple[str, int]:
    """Check password strength (convenience function)."""
    return PasswordValidator.check_strength(password)


def validate_email(email: str, allow_disposable: bool = False) -> ValidationResult:
    """Validate email (convenience function)."""
    return EmailValidator.validate(email, allow_disposable)


def validate_theme(theme: str) -> ValidationResult:
    """Validate theme (convenience function)."""
    return ThemeValidator.validate(theme)


def is_valid_theme(theme: str) -> bool:
    """Check if theme is valid (convenience function)."""
    return ThemeValidator.is_valid(theme)


def validate_year(year: str) -> ValidationResult:
    """Validate year (convenience function)."""
    return YearValidator