"""
Logging Configuration and Utilities
Provides structured logging for the application.
"""
import logging
import sys
import os
from datetime import datetime
from pathlib import Path
from pythonjsonlogger import jsonlogger

# Create logs directory
LOGS_DIR = Path(__file__).parent.parent.parent / 'logs'
LOGS_DIR.mkdir(parents=True, exist_ok=True)


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter for structured logging."""
    
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record['timestamp'] = datetime.utcnow().isoformat()
        log_record['level'] = record.levelname
        log_record['logger'] = record.name
        log_record['module'] = record.module
        log_record['function'] = record.funcName
        log_record['line'] = record.lineno


def setup_logger(name='itds_app'):
    """
    Set up and configure the application logger.
    
    Args:
        name: Logger name (default: 'itds_app')
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Set log level
    log_level = os.environ.get('LOG_LEVEL', 'INFO')
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Create formatters
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    
    # File handlers
    # Error log file
    error_file_handler = logging.FileHandler(
        LOGS_DIR / 'error.log',
        encoding='utf-8'
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(console_formatter)
    logger.addHandler(error_file_handler)
    
    # Combined log file
    combined_file_handler = logging.FileHandler(
        LOGS_DIR / 'combined.log',
        encoding='utf-8'
    )
    combined_file_handler.setLevel(logging.DEBUG)
    combined_file_handler.setFormatter(console_formatter)
    logger.addHandler(combined_file_handler)
    
    # JSON log file for production
    json_file_handler = logging.FileHandler(
        LOGS_DIR / 'json.log',
        encoding='utf-8'
    )
    json_file_handler.setLevel(logging.INFO)
    json_handler = CustomJsonFormatter(
        '%(timestamp)s %(level)s %(message)s'
    )
    json_file_handler.setFormatter(json_handler)
    logger.addHandler(json_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger


def get_logger(name=None):
    """
    Get a logger instance.
    
    Args:
        name: Optional logger name (uses calling module if not provided)
    
    Returns:
        Logger instance
    """
    if name is None:
        import inspect
        frame = inspect.currentframe()
        caller_frame = frame.f_back
        name = caller_frame.f_globals.get('__name__', 'itds_app')
    
    return logging.getLogger(name)


class LoggerMixin:
    """
    Mixin class to add logging capabilities to any class.
    """
    
    @property
    def logger(self):
        """Get logger for this class."""
        return get_logger(self.__class__.__module__)


# Create default logger
logger = setup_logger()

# Convenience function for quick logging
def log_info(message, **kwargs):
    """Log info message."""
    logger.info(message, extra=kwargs if kwargs else {})


def log_error(message, **kwargs):
    """Log error message."""
    logger.error(message, extra=kwargs if kwargs else {})


def log_warning(message, **kwargs):
    """Log warning message."""
    logger.warning(message, extra=kwargs if kwargs else {})


def log_debug(message, **kwargs):
    """Log debug message."""
    logger.debug(message, extra=kwargs if kwargs else {})


def log_exception(message, exc_info=True):
    """Log exception with traceback."""
    logger.exception(message, exc_info=exc_info)