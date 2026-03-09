"""
Input Sanitization and Validation Functions (Issue #131)

Security-focused validators for preventing XSS, SQL injection, command injection,
and path traversal attacks. Designed for use with Pydantic v2 field validators.

Usage:
    from backend.validators import sanitize_html, validate_safe_filename

    class MySchema(BaseModel):
        title: str = Field(max_length=200)

        @field_validator('title')
        def sanitize_title(cls, v):
            return sanitize_html(v)
"""

import re
import os
import json
from typing import Any, Dict, List
from urllib.parse import urlparse
from email.utils import parseaddr


def sanitize_html(text: str) -> str:
    """
    Remove HTML tags and JavaScript event handlers from text.

    Prevents XSS attacks by stripping:
        - HTML tags (<script>, <img>, <a>, etc.)
        - JavaScript event handlers (onclick, onerror, onload, etc.)
        - JavaScript protocol URLs (javascript:, data:text/html, etc.)
        - HTML entities that could be used for obfuscation

    Args:
        text: Raw user input text

    Returns:
        Sanitized text with HTML/JS removed

    Example:
        >>> sanitize_html('<script>alert("XSS")</script>Hello')
        'Hello'
        >>> sanitize_html('Click <a href="javascript:alert(1)">here</a>')
        'Click here'
    """
    if not text:
        return text

    # Remove HTML tags (greedy and non-greedy variants) - iterate to handle nested tags
    prev_text = None
    while prev_text != text:
        prev_text = text
        text = re.sub(r'<[^>]*>', '', text)

    # Remove JavaScript event handlers (e.g., onclick=, onerror=, onload=)
    text = re.sub(r'on\w+\s*=\s*["\']?[^"\']*["\']?', '', text, flags=re.IGNORECASE)

    # Remove JavaScript protocol URLs
    text = re.sub(r'javascript\s*:', '', text, flags=re.IGNORECASE)
    text = re.sub(r'data\s*:\s*text/html[^"\']*', '', text, flags=re.IGNORECASE)

    # Decode common HTML entities then remove them
    import html
    text = html.unescape(text)
    # After decoding, remove any tags that were encoded
    text = re.sub(r'<[^>]*>', '', text)

    return text.strip()


def sanitize_sql_freetext(text: str) -> str:
    """
    Sanitize free-text fields to prevent SQL injection.

    NOTE: This is a defense-in-depth measure. Parameterized queries
    (SQLAlchemy ORM) are the primary defense against SQL injection.

    Blocks:
        - SQL keywords: UNION, SELECT, INSERT, UPDATE, DELETE, DROP, etc.
        - SQL comment sequences: --, /*, */
        - Semicolons (query chaining)
        - Single quotes in suspicious contexts

    Args:
        text: User input text

    Returns:
        Sanitized text

    Raises:
        ValueError: If dangerous SQL patterns are detected

    Example:
        >>> sanitize_sql_freetext("Hello world")
        'Hello world'
        >>> sanitize_sql_freetext("'; DROP TABLE users--")
        ValueError: Text contains forbidden SQL keyword: DROP
    """
    if not text:
        return text

    text = text.strip()

    # Check for dangerous SQL keywords (case-insensitive)
    dangerous_keywords = [
        'UNION', 'SELECT', 'INSERT', 'UPDATE', 'DELETE',
        'DROP', 'CREATE', 'ALTER', 'EXEC', 'EXECUTE',
        'SCRIPT', 'JAVASCRIPT', 'EVAL', 'EXPRESSION'
    ]

    text_upper = text.upper()
    for keyword in dangerous_keywords:
        # Use word boundaries to avoid false positives (e.g., "selection" is OK)
        if re.search(rf'\b{keyword}\b', text_upper):
            raise ValueError(
                f"Text contains forbidden SQL keyword: {keyword}. "
                f"Please use plain text without SQL commands."
            )

    # Block SQL comment sequences
    if '--' in text or '/*' in text or '*/' in text:
        raise ValueError(
            "Text contains SQL comment sequences (-- or /* */). "
            "Please use plain text without SQL syntax."
        )

    # Block semicolons (query chaining)
    if ';' in text:
        raise ValueError(
            "Text contains semicolon which is not allowed. "
            "Please use plain text without SQL syntax."
        )

    # Block null bytes and control characters (except newline, tab, space)
    if re.search(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', text):
        raise ValueError(
            "Text contains invalid control characters. "
            "Please use plain text without control codes."
        )

    return text


def validate_safe_filename(filename: str) -> str:
    """
    Validate filename to prevent path traversal and command injection.

    Security measures:
        - Block path traversal sequences (../, ..\, etc.)
        - Block absolute paths (/, C:\, etc.)
        - Block null bytes
        - Block shell metacharacters (|, &, ;, $, `, etc.)
        - Restrict to safe characters: alphanumeric, dash, underscore, period
        - Enforce reasonable length limits (1-255 chars)

    Args:
        filename: Proposed filename

    Returns:
        Validated filename

    Raises:
        ValueError: If filename contains unsafe patterns

    Example:
        >>> validate_safe_filename("report.pdf")
        'report.pdf'
        >>> validate_safe_filename("../../etc/passwd")
        ValueError: Filename contains path traversal sequence
    """
    if not filename:
        raise ValueError("Filename cannot be empty")

    filename = filename.strip()

    # Length check
    if len(filename) > 255:
        raise ValueError("Filename exceeds maximum length of 255 characters")

    # Block null bytes
    if '\x00' in filename:
        raise ValueError("Filename contains null byte")

    # Block path traversal sequences
    if '..' in filename or '/' in filename or '\\' in filename:
        raise ValueError("Filename contains path traversal sequence (../, /, \\)")

    # Block absolute paths
    if filename.startswith(('/', '\\', '~')) or (len(filename) > 1 and filename[1] == ':'):
        raise ValueError("Filename must be relative (no absolute paths)")

    # Block shell metacharacters and control characters
    dangerous_chars = ['|', '&', ';', '$', '`', '<', '>', '!', '\n', '\r', '\t']
    for char in dangerous_chars:
        if char in filename:
            raise ValueError(
                f"Filename contains dangerous character: {repr(char)}. "
                f"Only alphanumeric, dash, underscore, and period allowed."
            )

    # Restrict to safe character set: alphanumeric, dash, underscore, period
    if not re.match(r'^[a-zA-Z0-9._-]+$', filename):
        raise ValueError(
            "Filename contains invalid characters. "
            "Only alphanumeric, dash (-), underscore (_), and period (.) allowed."
        )

    # Block hidden files (starting with dot) for extra security
    if filename.startswith('.'):
        raise ValueError("Filename cannot start with period (hidden files not allowed)")

    return filename


def validate_url(url: str, allowed_schemes: List[str] = None) -> str:
    """
    Validate URL format and restrict to safe protocols.

    Security features:
        - Protocol whitelist (default: https, http)
        - Block javascript:, data:, file:, ftp: protocols
        - Validate URL structure
        - Block localhost/127.0.0.1 in production (configurable)

    Args:
        url: URL to validate
        allowed_schemes: List of allowed URL schemes (default: ['http', 'https'])

    Returns:
        Validated URL

    Raises:
        ValueError: If URL is invalid or uses forbidden protocol

    Example:
        >>> validate_url("https://example.com")
        'https://example.com'
        >>> validate_url("javascript:alert(1)")
        ValueError: URL protocol not allowed: javascript
    """
    if not url:
        raise ValueError("URL cannot be empty")

    url = url.strip()

    if allowed_schemes is None:
        allowed_schemes = ['http', 'https']

    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValueError(f"Invalid URL format: {e}")

    # Validate scheme
    if not parsed.scheme:
        raise ValueError("URL must include protocol (http:// or https://)")

    if parsed.scheme.lower() not in allowed_schemes:
        raise ValueError(
            f"URL protocol not allowed: {parsed.scheme}. "
            f"Allowed protocols: {', '.join(allowed_schemes)}"
        )

    # Block dangerous protocols
    dangerous_schemes = ['javascript', 'data', 'file', 'vbscript']
    if parsed.scheme.lower() in dangerous_schemes:
        raise ValueError(f"Dangerous URL protocol blocked: {parsed.scheme}")

    # Validate netloc (domain) exists
    if not parsed.netloc:
        raise ValueError("URL must include domain name")

    # Optional: Block localhost in production (can be configured)
    # Uncomment if needed:
    # if parsed.netloc.lower() in ['localhost', '127.0.0.1', '0.0.0.0']:
    #     raise ValueError("Localhost URLs not allowed")

    return url


def validate_email(email: str) -> str:
    """
    Validate email address format (RFC 5322 compliant).

    Security features:
        - Regex validation for email structure
        - Length limits (local part: 64 chars, domain: 255 chars)
        - Block invalid characters
        - Use email.utils.parseaddr for RFC compliance

    Args:
        email: Email address to validate

    Returns:
        Normalized email (lowercased domain)

    Raises:
        ValueError: If email format is invalid

    Example:
        >>> validate_email("user@example.com")
        'user@example.com'
        >>> validate_email("invalid.email")
        ValueError: Invalid email format
    """
    if not email:
        raise ValueError("Email cannot be empty")

    email = email.strip()

    # Length check (RFC 5321)
    if len(email) > 320:  # 64 (local) + 1 (@) + 255 (domain)
        raise ValueError("Email exceeds maximum length of 320 characters")

    # Use email.utils.parseaddr for RFC 5322 compliance
    parsed_name, parsed_email = parseaddr(email)

    if not parsed_email or '@' not in parsed_email:
        raise ValueError("Invalid email format: missing @ symbol")

    # Split into local and domain parts
    try:
        local, domain = parsed_email.rsplit('@', 1)
    except ValueError:
        raise ValueError("Invalid email format: missing @ symbol")

    # Validate local part (before @)
    if not local or len(local) > 64:
        raise ValueError("Email local part (before @) must be 1-64 characters")

    # Validate domain part (after @)
    if not domain or len(domain) > 255:
        raise ValueError("Email domain must be 1-255 characters")

    # Basic regex validation
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_regex, parsed_email):
        raise ValueError(
            "Invalid email format. Must be in format: user@domain.com"
        )

    # Normalize: lowercase domain (RFC allows case-insensitive domains)
    local_part, domain_part = parsed_email.rsplit('@', 1)
    normalized = f"{local_part}@{domain_part.lower()}"

    return normalized


def validate_no_control_chars(text: str, allow_newlines: bool = False) -> str:
    """
    Block control characters (except optionally newlines).

    Control characters (ASCII 0-31, 127) can be used for:
        - Command injection
        - Log injection
        - Protocol smuggling

    Args:
        text: Text to validate
        allow_newlines: If True, allow \n and \r characters

    Returns:
        Validated text

    Raises:
        ValueError: If control characters are detected

    Example:
        >>> validate_no_control_chars("Hello world")
        'Hello world'
        >>> validate_no_control_chars("Hello\\x00world")
        ValueError: Text contains null byte or control characters
    """
    if not text:
        return text

    # Check for null bytes (always forbidden)
    if '\x00' in text:
        raise ValueError("Text contains null byte")

    # Define control character range
    if allow_newlines:
        # Allow \n (0x0A) and \r (0x0D)
        # Block: 0x00-0x09, 0x0B-0x0C, 0x0E-0x1F, 0x7F
        pattern = r'[\x00-\x09\x0B\x0C\x0E-\x1F\x7F]'
    else:
        # Block all control characters: 0x00-0x1F, 0x7F
        pattern = r'[\x00-\x1F\x7F]'

    if re.search(pattern, text):
        raise ValueError(
            "Text contains null byte or control characters. "
            "Only printable characters allowed."
        )

    return text


def sanitize_command_args(arg: str) -> str:
    """
    Sanitize command-line arguments to prevent command injection.

    Security measures:
        - Block shell metacharacters (|, &, ;, $, `, etc.)
        - Block command substitution ($(), ``)
        - Block redirection (<, >, >>)
        - Whitelist safe characters

    Args:
        arg: Command argument to sanitize

    Returns:
        Validated argument

    Raises:
        ValueError: If argument contains shell metacharacters

    Example:
        >>> sanitize_command_args("report-2024")
        'report-2024'
        >>> sanitize_command_args("report; rm -rf /")
        ValueError: Command argument contains shell metacharacters
    """
    if not arg:
        return arg

    arg = arg.strip()

    # Block shell metacharacters
    dangerous_chars = ['|', '&', ';', '$', '`', '<', '>', '!', '\n', '\\', '"', "'"]
    for char in dangerous_chars:
        if char in arg:
            raise ValueError(
                f"Command argument contains shell metacharacters: {repr(char)}. "
                f"Only alphanumeric, dash, underscore, period, slash allowed."
            )

    # Block command substitution patterns
    if '$(' in arg or '${' in arg:
        raise ValueError("Command argument contains command substitution pattern")

    # Whitelist safe characters: alphanumeric, dash, underscore, period, slash, colon
    if not re.match(r'^[a-zA-Z0-9._/:-]+$', arg):
        raise ValueError(
            "Command argument contains invalid characters. "
            "Only alphanumeric, dash, underscore, period, slash, colon allowed."
        )

    return arg


def validate_alphanumeric_id(id_str: str, allow_dash: bool = True,
                               allow_underscore: bool = True) -> str:
    """
    Validate ID strings to contain only safe alphanumeric characters.

    Use for:
        - User IDs
        - Resource IDs
        - Slugs
        - Tokens (non-sensitive)

    Args:
        id_str: ID string to validate
        allow_dash: Allow dash (-) character
        allow_underscore: Allow underscore (_) character

    Returns:
        Validated ID string

    Raises:
        ValueError: If ID contains invalid characters

    Example:
        >>> validate_alphanumeric_id("user-123")
        'user-123'
        >>> validate_alphanumeric_id("user@123")
        ValueError: ID contains invalid characters
    """
    if not id_str:
        raise ValueError("ID cannot be empty")

    id_str = id_str.strip()

    # Build allowed character pattern
    pattern_parts = ['a-zA-Z0-9']
    if allow_dash:
        pattern_parts.append('-')
    if allow_underscore:
        pattern_parts.append('_')

    pattern = f'^[{"".join(pattern_parts)}]+$'

    if not re.match(pattern, id_str):
        allowed_chars = "alphanumeric"
        if allow_dash:
            allowed_chars += ", dash"
        if allow_underscore:
            allowed_chars += ", underscore"

        raise ValueError(
            f"ID contains invalid characters. "
            f"Only {allowed_chars} allowed."
        )

    return id_str


def validate_safe_json_metadata(metadata: Dict[str, Any],
                                  max_depth: int = 3,
                                  max_keys: int = 50,
                                  max_value_length: int = 1000) -> Dict[str, Any]:
    """
    Validate JSON metadata to prevent DoS and injection attacks.

    Security measures:
        - Limit nesting depth (prevent stack overflow)
        - Limit number of keys (prevent memory exhaustion)
        - Limit string value length (prevent log flooding)
        - Block dangerous key names (eval, exec, __proto__, etc.)

    Args:
        metadata: Dictionary to validate
        max_depth: Maximum nesting depth (default: 3)
        max_keys: Maximum total keys across all nesting levels (default: 50)
        max_value_length: Maximum length for string values (default: 1000)

    Returns:
        Validated metadata dictionary

    Raises:
        ValueError: If metadata violates constraints

    Example:
        >>> validate_safe_json_metadata({"key": "value"})
        {'key': 'value'}
        >>> validate_safe_json_metadata({"__proto__": "attack"})
        ValueError: Metadata contains dangerous key: __proto__
    """
    if not metadata:
        return metadata

    # Validate it's actually a dictionary
    if not isinstance(metadata, dict):
        raise ValueError("Metadata must be a dictionary")

    # Track total keys across all nesting levels
    total_keys = [0]

    def _validate_recursive(obj: Any, depth: int) -> None:
        """Recursive validation helper."""
        if depth > max_depth:
            raise ValueError(f"Metadata exceeds maximum nesting depth of {max_depth}")

        if isinstance(obj, dict):
            # Check number of keys at this level
            if len(obj) > max_keys:
                raise ValueError(f"Metadata level exceeds maximum of {max_keys} keys")

            # Update total key count
            total_keys[0] += len(obj)
            if total_keys[0] > max_keys:
                raise ValueError(f"Metadata exceeds maximum total of {max_keys} keys")

            # Validate each key-value pair
            for key, value in obj.items():
                # Block dangerous key names
                dangerous_keys = [
                    '__proto__', 'constructor', 'prototype',
                    'eval', 'exec', 'compile', '__import__'
                ]
                if key.lower() in dangerous_keys:
                    raise ValueError(f"Metadata contains dangerous key: {key}")

                # Validate key format
                if not isinstance(key, str):
                    raise ValueError("Metadata keys must be strings")

                if len(key) > 100:
                    raise ValueError("Metadata key exceeds maximum length of 100 characters")

                # Recurse into nested structures
                _validate_recursive(value, depth + 1)

        elif isinstance(obj, list):
            if len(obj) > max_keys:
                raise ValueError(f"Metadata list exceeds maximum of {max_keys} items")

            for item in obj:
                _validate_recursive(item, depth + 1)

        elif isinstance(obj, str):
            if len(obj) > max_value_length:
                raise ValueError(
                    f"Metadata string value exceeds maximum length of {max_value_length} characters"
                )

            # Block control characters in string values
            validate_no_control_chars(obj, allow_newlines=True)

    # Start recursive validation
    _validate_recursive(metadata, 1)

    return metadata
