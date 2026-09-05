import sys
import os
import logging
import signal
import threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'itds_env'))
import logging.config

# Suppress torch fake_tensor atexit noise (before config load)
logging.getLogger("torch._subclasses.fake_tensor").disabled = True
logging.getLogger("torch").setLevel(logging.ERROR)

# Suppress werkzeug access logs (the 127.0.0.1 - - [06/May/2026 07:26:04] "GET ... 200 - logs)
# Set werkzeug log level to WARNING to filter out info/debug messages
logging.getLogger("werkzeug").setLevel(logging.WARNING)

# Suppress werkzeug's default console handler that prints access logs to stdout
# This requires adding a NullHandler to prevent the default propagation
import io
class NullWriter(io.IOBase):
    def write(self, x): pass
    def flush(self): pass

# Get werkzeug logger and remove its handlers
werkzeug_logger = logging.getLogger("werkzeug")
for h in werkzeug_logger.handlers[:]:
    werkzeug_logger.removeHandler(h)
# Add a null handler to suppress all werkzeug logs
null_handler = logging.NullHandler()
werkzeug_logger.addHandler(null_handler)
werkzeug_logger.propagate = False

# Also redirect werkzeug's server log output to suppress access logs
# This is done after importing werkzeug but before app.run()
# Use werkzeug's _log function to suppress access logs
import werkzeug.serving
def suppress_log(self, type, message, *args):
    # Only log errors, suppress info (type 'info') logs
    if type != 'info':
        pass  # Could add logging here if needed
werkzeug.serving.WSGIRequestHandler.log = suppress_log


if __name__ == '__main__':
    def graceful_shutdown(signum, frame):
        print("\nShutting down ITDS Backend gracefully...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, graceful_shutdown)
    
    # Load logging config (from itds_env/app)
    logging.config.fileConfig('itds_env/app/logging.conf', disable_existing_loggers=False)

    # Import app only after logging is configured to avoid silent startup stalls.
    from app.app import app

    def warm_models_async():
        """Warm AI models without blocking server startup."""
        try:
            from app.model_manager import initialize_models
            logging.info("Starting background AI model warm-up...")
            initialize_models()
            logging.info("[OK] Background AI model warm-up completed")
        except Exception as exc:
            logging.warning(f"Background AI model warm-up skipped: {exc}")

    threading.Thread(target=warm_models_async, daemon=True).start()
    
    port = int(os.getenv('ITDS_BACKEND_PORT', '5001'))
    print(f"Starting ITDS Backend on http://localhost:{port} (Press CTRL+C to quit)")
    print("Login: admin / admin123")
    
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
