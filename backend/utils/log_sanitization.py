"""
Log Sanitization Utility

Automatically redacts sensitive information from log messages to prevent credential leakage.
Supports both string-based and structured logging with configurable redaction patterns.
"""

import re
from typing import Any, Dict, List, Pattern
from enum import Enum


class SensitivePattern(Enum):
    """Enumeration of sensitive data patterns to redact"""
    PASSWORD = "password"
    API_KEY = "api_key"
    TOKEN = "token"
    SECRET = "secret"
    BEARER = "bearer"
    AUTHORIZATION = "authorization"
    JWT = "jwt"
    CREDIT_CARD = "credit_card"
    SSH_KEY = "ssh_key"
    PRIVATE_KEY = "private_key"


# Compiled regex patterns for performance
_SENSITIVE_PATTERNS: Dict[SensitivePattern, Pattern] = {
    # Password patterns
    SensitivePattern.PASSWORD: re.compile(
        r'(password["\']?\s*[:=]\s*["\']?)([^"\'\s&]+)',
        re.IGNORECASE
    ),

    # API key patterns (common formats)
    SensitivePattern.API_KEY: re.compile(
        r'(api[_-]?key["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9_\-]{20,})',
        re.IGNORECASE
    ),

    # Token patterns
    SensitivePattern.TOKEN: re.compile(
        r'(token["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9_\-\.]{20,})',
        re.IGNORECASE
    ),

    # Secret patterns
    SensitivePattern.SECRET: re.compile(
        r'(secret["\']?\s*[:=]\s*["\']?)([a-zA-Z0-9_\-]{16,})',
        re.IGNORECASE
    ),

    # Bearer token patterns
    SensitivePattern.BEARER: re.compile(
        r'(bearer\s+)([a-zA-Z0-9_\-\.]{20,})',
        re.IGNORECASE
    ),

    # Authorization header patterns
    SensitivePattern.AUTHORIZATION: re.compile(
        r'(authorization["\']?\s*[:=]\s*["\']?)([^"\'\s&]+)',
        re.IGNORECASE
    ),

    # JWT patterns (three base64 segments separated by dots)
    SensitivePattern.JWT: re.compile(
        r'\b(eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*)\b'
    ),

    # Credit card patterns (basic Luhn-valid patterns)
    SensitivePattern.CREDIT_CARD: re.compile(
        r'\b([0-9]{4}[\s\-]?[0-9]{4}[\s\-]?[0-9]{4}[\s\-]?[0-9]{4})\b'
    ),

    # SSH private key patterns
    SensitivePattern.SSH_KEY: re.compile(
        r'(-----BEGIN [A-Z\s]+ PRIVATE KEY-----)(.*?)(-----END [A-Z\s]+ PRIVATE KEY-----)',
        re.DOTALL
    ),

    # Generic private key patterns
    SensitivePattern.PRIVATE_KEY: re.compile(
        r'(private[_-]?key["\']?\s*[:=]\s*["\']?)([^"\'\s&]{20,})',
        re.IGNORECASE
    ),
}

# Redaction placeholder
REDACTED = "***REDACTED***"


def sanitize_message(message: str, enabled_patterns: List[SensitivePattern] = None) -> str:
    """
    Sanitize a log message by redacting sensitive information

    Args:
        message: Raw log message that may contain sensitive data
        enabled_patterns: List of patterns to check (defaults to all patterns)

    Returns:
        Sanitized message with sensitive data replaced by ***REDACTED***
    """
    if not message:
        return message

    if enabled_patterns is None:
        enabled_patterns = list(SensitivePattern)

    sanitized = message

    for pattern_type in enabled_patterns:
        pattern = _SENSITIVE_PATTERNS.get(pattern_type)
        if pattern is None:
            continue

        # Handle multi-group patterns (preserve prefix, redact value)
        if pattern_type in (SensitivePattern.SSH_KEY,):
            # For SSH keys, redact the entire key block
            sanitized = pattern.sub(
                r'\1' + REDACTED + r'\3',
                sanitized
            )
        elif pattern.groups >= 2:
            # For patterns with prefix and value groups, preserve prefix
            sanitized = pattern.sub(
                r'\1' + REDACTED,
                sanitized
            )
        else:
            # For patterns with single capture group, replace entire match
            sanitized = pattern.sub(REDACTED, sanitized)

    return sanitized


def sanitize_dict(data: Dict[str, Any], enabled_patterns: List[SensitivePattern] = None) -> Dict[str, Any]:
    """
    Sanitize a dictionary by redacting sensitive values

    Recursively processes nested dictionaries and lists.
    Redacts values for keys that match sensitive patterns.

    Args:
        data: Dictionary that may contain sensitive data
        enabled_patterns: List of patterns to check (defaults to all patterns)

    Returns:
        Dictionary with sensitive values replaced by ***REDACTED***
    """
    if not isinstance(data, dict):
        return data

    if enabled_patterns is None:
        enabled_patterns = list(SensitivePattern)

    sanitized = {}

    # Sensitive key names (case-insensitive)
    sensitive_keys = {
        'password', 'passwd', 'pwd',
        'api_key', 'apikey', 'api-key',
        'token', 'access_token', 'refresh_token',
        'secret', 'secret_key', 'client_secret',
        'authorization', 'auth',
        'jwt', 'bearer',
        'private_key', 'private-key', 'privatekey',
        'credit_card', 'creditcard', 'card_number',
        'ssn', 'social_security',
    }

    for key, value in data.items():
        key_lower = key.lower()

        # Check if key is in sensitive list
        if key_lower in sensitive_keys:
            sanitized[key] = REDACTED
        # Recursively sanitize nested dictionaries
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value, enabled_patterns)
        # Recursively sanitize lists
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_dict(item, enabled_patterns) if isinstance(item, dict)
                else sanitize_message(str(item), enabled_patterns) if isinstance(item, str)
                else item
                for item in value
            ]
        # Sanitize string values
        elif isinstance(value, str):
            sanitized[key] = sanitize_message(value, enabled_patterns)
        else:
            sanitized[key] = value

    return sanitized


class SanitizingFilter:
    """
    Logging filter that sanitizes log records before output

    Usage:
        import logging
        from backend.utils.log_sanitization import SanitizingFilter

        handler = logging.StreamHandler()
        handler.addFilter(SanitizingFilter())
        logger.addHandler(handler)
    """

    def __init__(self, enabled_patterns: List[SensitivePattern] = None):
        """
        Initialize sanitizing filter

        Args:
            enabled_patterns: List of patterns to check (defaults to all patterns)
        """
        self.enabled_patterns = enabled_patterns

    def filter(self, record):
        """
        Filter and sanitize a log record

        Args:
            record: LogRecord to sanitize

        Returns:
            True (always allows record through after sanitization)
        """
        # Sanitize the main message
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            record.msg = sanitize_message(record.msg, self.enabled_patterns)

        # Sanitize arguments if present
        if hasattr(record, 'args') and record.args:
            if isinstance(record.args, dict):
                record.args = sanitize_dict(record.args, self.enabled_patterns)
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(
                    sanitize_message(str(arg), self.enabled_patterns) if isinstance(arg, str)
                    else sanitize_dict(arg, self.enabled_patterns) if isinstance(arg, dict)
                    else arg
                    for arg in record.args
                )

        return True
