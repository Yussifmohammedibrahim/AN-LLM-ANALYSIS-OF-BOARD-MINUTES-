import functools
import bleach
from flask import request, jsonify

# Simple request JSON validator and sanitizer
# usage: @validate_json({'name': str, 'age': int, 'tags': list})

def sanitize_value(v):
    if isinstance(v, str):
        return bleach.clean(v)
    if isinstance(v, list):
        return [sanitize_value(x) for x in v]
    if isinstance(v, dict):
        return {k: sanitize_value(vv) for k, vv in v.items()}
    return v


def validate_json(schema):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not request.is_json:
                return jsonify({'error': 'invalid_request', 'message': 'JSON body required'}), 400
            data = request.get_json()
            cleaned = {}
            for key, expected in schema.items():
                if key not in data:
                    return jsonify({'error': 'invalid_request', 'message': f"Missing field '{key}'"}), 400
                value = data.get(key)
                # type check (basic)
                if expected is not None and not isinstance(value, expected):
                    # allow ints for floats
                    if expected is float and isinstance(value, int):
                        value = float(value)
                    else:
                        return jsonify({'error': 'invalid_request', 'message': f"Field '{key}' must be {expected.__name__}"}), 400
                cleaned[key] = sanitize_value(value)
            # attach cleaned to request for handler use
            request.cleaned_json = cleaned
            return fn(*args, **kwargs)
        return wrapper
    return decorator
