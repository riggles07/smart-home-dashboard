"""Integration Functions - API Utilities"""
import json
from functools import wraps

def api_call(endpoint: str, method: str = "GET", data: dict = None):
    """Generic API call wrapper"""
    return {
        "endpoint": endpoint,
        "method": method,
        "status": "success"
    }

def validate_response(response: dict) -> bool:
    """Validate API response"""
    return "status" in response and response["status"] == "success"

def retry_on_failure(max_retries: int = 3, delay: int = 1):
    """Retry decorator for failed API calls"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    print(f"Attempt {attempt + 1} failed: {e}")
            return None
        return wrapper
    return decorator

def parse_json_response(response_text: str):
    """Parse JSON response"""
    return json.loads(response_text)
