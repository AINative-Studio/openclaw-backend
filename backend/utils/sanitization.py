"""
Input Sanitization Utilities for XSS Prevention

Provides HTML escaping, cleaning, and sanitization functions to prevent
Cross-Site Scripting (XSS) attacks and ensure safe handling of user-generated content.

Issue #131: Implement comprehensive input validation and XSS prevention
"""

import html
import re
from typing import Any, Dict, List, Optional, Union
import bleach


# Allowed HTML tags for rich content (very restrictive by default)
ALLOWED_TAGS = [
    'p', 'br', 'strong', 'em', 'u', 'ol', 'ul', 'li', 'a', 'code', 'pre'
]

# Allowed HTML attributes for specific tags
ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title'],
    'code': ['class'],
}

# Allowed URL protocols
ALLOWED_PROTOCOLS = ['http', 'https', 'mailto']

# Maximum lengths for various content types
MAX_STRING_LENGTH = 10000
MAX_METADATA_JSON_LENGTH = 5000
MAX_DESCRIPTION_LENGTH = 5000
MAX_NAME_LENGTH = 255
MAX_TITLE_LENGTH = 500


def escape_html(text: str) -> str:
    """
    Escape HTML special characters to prevent XSS attacks.

    Converts:
    - < to &lt;
    - > to &gt;
    - & to &amp;
    - " to &quot;
    - ' to &#x27;

    Args:
        text: Raw text that may contain HTML

    Returns:
        HTML-escaped text safe for display

    Example:
        >>> escape_html("<script>alert('XSS')</script>")
        "&lt;script&gt;alert(&#x27;XSS&#x27;)&lt;/script&gt;"
    """
    if not isinstance(text, str):
        return str(text)
    return html.escape(text, quote=True)


def unescape_html(text: str) -> str:
    """
    Unescape HTML entities back to regular text.

    Use with caution - only when you need to reverse escaping
    and are certain the content is safe.

    Args:
        text: HTML-escaped text

    Returns:
        Unescaped text
    """
    if not isinstance(text, str):
        return str(text)
    return html.unescape(text)


def clean_html(
    text: str,
    allowed_tags: Optional[List[str]] = None,
    allowed_attributes: Optional[Dict[str, List[str]]] = None,
    strip: bool = True
) -> str:
    """
    Clean and sanitize HTML content, removing potentially dangerous elements.

    Uses bleach library to strip or escape disallowed HTML tags and attributes.

    Args:
        text: HTML content to sanitize
        allowed_tags: List of allowed HTML tags (defaults to ALLOWED_TAGS)
        allowed_attributes: Dict mapping tags to allowed attributes
        strip: If True, remove disallowed tags; if False, escape them

    Returns:
        Sanitized HTML safe for rendering

    Example:
        >>> clean_html('<p>Safe</p><script>alert("XSS")</script>')
        '<p>Safe</p>alert("XSS")'
    """
    if not isinstance(text, str):
        text = str(text)

    if allowed_tags is None:
        allowed_tags = ALLOWED_TAGS

    if allowed_attributes is None:
        allowed_attributes = ALLOWED_ATTRIBUTES

    return bleach.clean(
        text,
        tags=allowed_tags,
        attributes=allowed_attributes,
        protocols=ALLOWED_PROTOCOLS,
        strip=strip
    )


def strip_html(text: str) -> str:
    """
    Strip all HTML tags from text, leaving only plain text.

    Useful for contexts where no HTML should be allowed at all.

    Args:
        text: Text that may contain HTML

    Returns:
        Plain text with all HTML removed

    Example:
        >>> strip_html('<p>Hello <strong>World</strong></p>')
        'Hello World'
    """
    if not isinstance(text, str):
        text = str(text)

    return bleach.clean(text, tags=[], strip=True)


def sanitize_for_storage(text: str) -> str:
    """
    Sanitize text for safe storage in database.

    This is the recommended function for sanitizing user-generated content
    before storing it in the database.

    Args:
        text: User-provided text

    Returns:
        Sanitized text safe for storage
    """
    if not isinstance(text, str):
        text = str(text)

    # Strip all HTML tags for storage
    # We'll escape on output if needed
    text = strip_html(text)

    # Normalize whitespace
    text = ' '.join(text.split())

    return text


def sanitize_for_display(text: str, allow_basic_html: bool = False) -> str:
    """
    Sanitize text for safe display in HTML context.

    Args:
        text: Text to display
        allow_basic_html: If True, allow basic formatting tags

    Returns:
        Sanitized text safe for HTML rendering
    """
    if not isinstance(text, str):
        text = str(text)

    if allow_basic_html:
        # Allow basic formatting but strip dangerous tags
        return clean_html(text)
    else:
        # Full HTML escape for plain text display
        return escape_html(text)


def sanitize_metadata(metadata: Dict[str, Any], max_depth: int = 3) -> Dict[str, Any]:
    """
    Sanitize metadata dictionary by escaping all string values.

    Recursively processes nested dictionaries up to max_depth.

    Args:
        metadata: Dictionary containing metadata
        max_depth: Maximum nesting depth to process

    Returns:
        Sanitized metadata with escaped string values

    Raises:
        ValueError: If nesting exceeds max_depth
    """
    if not isinstance(metadata, dict):
        return {}

    def _sanitize_recursive(obj: Any, depth: int = 0) -> Any:
        if depth > max_depth:
            raise ValueError(f"Metadata nesting exceeds maximum depth of {max_depth}")

        if isinstance(obj, dict):
            return {
                sanitize_for_storage(str(k)): _sanitize_recursive(v, depth + 1)
                for k, v in obj.items()
            }
        elif isinstance(obj, list):
            return [_sanitize_recursive(item, depth + 1) for item in obj]
        elif isinstance(obj, str):
            return sanitize_for_storage(obj)
        else:
            # Numbers, booleans, None pass through
            return obj

    return _sanitize_recursive(metadata)


def validate_string_length(
    text: str,
    field_name: str,
    min_length: int = 0,
    max_length: Optional[int] = None
) -> str:
    """
    Validate string length and raise error if outside bounds.

    Args:
        text: Text to validate
        field_name: Name of field (for error messages)
        min_length: Minimum allowed length
        max_length: Maximum allowed length (None for no limit)

    Returns:
        The validated text (stripped of leading/trailing whitespace)

    Raises:
        ValueError: If length is outside bounds
    """
    if not isinstance(text, str):
        raise ValueError(f"{field_name} must be a string")

    text = text.strip()
    length = len(text)

    if length < min_length:
        raise ValueError(f"{field_name} must be at least {min_length} characters")

    if max_length is not None and length > max_length:
        raise ValueError(f"{field_name} must not exceed {max_length} characters")

    return text


def sanitize_url(url: str) -> str:
    """
    Sanitize and validate URL, ensuring it uses safe protocols.

    Args:
        url: URL to sanitize

    Returns:
        Sanitized URL

    Raises:
        ValueError: If URL uses disallowed protocol or is malformed
    """
    if not isinstance(url, str):
        raise ValueError("URL must be a string")

    url = url.strip()

    # Check for javascript: protocol and other dangerous schemes
    dangerous_protocols = ['javascript:', 'data:', 'vbscript:', 'file:']
    url_lower = url.lower()

    for protocol in dangerous_protocols:
        if url_lower.startswith(protocol):
            raise ValueError(f"Disallowed URL protocol: {protocol}")

    # Validate URL format (basic check)
    if '://' in url:
        protocol = url.split('://')[0].lower()
        if protocol not in ALLOWED_PROTOCOLS:
            raise ValueError(f"URL protocol must be one of: {', '.join(ALLOWED_PROTOCOLS)}")

    return url


def remove_control_characters(text: str) -> str:
    """
    Remove control characters from text (except newline, tab, carriage return).

    Control characters can cause issues in JSON, databases, and display.

    Args:
        text: Text to clean

    Returns:
        Text with control characters removed
    """
    if not isinstance(text, str):
        text = str(text)

    # Remove all control characters except \n, \r, \t
    return re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', text)


def sanitize_sql_identifier(identifier: str) -> str:
    """
    Sanitize a string to be safe for use as SQL identifier (table/column name).

    Note: This is for extra safety. Always use parameterized queries!

    Args:
        identifier: Identifier to sanitize

    Returns:
        Sanitized identifier

    Raises:
        ValueError: If identifier is invalid
    """
    if not isinstance(identifier, str):
        raise ValueError("SQL identifier must be a string")

    identifier = identifier.strip()

    # Must start with letter or underscore
    if not re.match(r'^[a-zA-Z_]', identifier):
        raise ValueError("SQL identifier must start with letter or underscore")

    # Can only contain alphanumeric and underscore
    if not re.match(r'^[a-zA-Z0-9_]+$', identifier):
        raise ValueError("SQL identifier can only contain letters, numbers, and underscores")

    # Check for SQL keywords (basic list)
    sql_keywords = {
        'select', 'insert', 'update', 'delete', 'drop', 'create', 'alter',
        'table', 'database', 'index', 'view', 'trigger', 'procedure', 'function'
    }

    if identifier.lower() in sql_keywords:
        raise ValueError(f"SQL identifier cannot be a reserved keyword: {identifier}")

    return identifier


def truncate_with_ellipsis(text: str, max_length: int, ellipsis: str = "...") -> str:
    """
    Truncate text to maximum length and add ellipsis if truncated.

    Args:
        text: Text to truncate
        max_length: Maximum length (including ellipsis)
        ellipsis: String to append when truncated

    Returns:
        Truncated text
    """
    if not isinstance(text, str):
        text = str(text)

    if len(text) <= max_length:
        return text

    return text[:max_length - len(ellipsis)] + ellipsis


# Convenience functions for common use cases

def sanitize_user_message(content: str) -> str:
    """Sanitize user message content for conversation."""
    return sanitize_for_storage(validate_string_length(
        content, "message content", min_length=1, max_length=MAX_STRING_LENGTH
    ))


def sanitize_agent_name(name: str) -> str:
    """Sanitize agent name."""
    return sanitize_for_storage(validate_string_length(
        name, "agent name", min_length=1, max_length=MAX_NAME_LENGTH
    ))


def sanitize_description(description: str) -> str:
    """Sanitize description field."""
    return sanitize_for_storage(validate_string_length(
        description, "description", min_length=0, max_length=MAX_DESCRIPTION_LENGTH
    ))


def sanitize_title(title: str) -> str:
    """Sanitize title field."""
    return sanitize_for_storage(validate_string_length(
        title, "title", min_length=1, max_length=MAX_TITLE_LENGTH
    ))
