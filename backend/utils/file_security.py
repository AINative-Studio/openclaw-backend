"""
Secure File Handling Utilities

Provides path validation and sanitization to prevent path traversal attacks.
All file operations should use these utilities to ensure security.

OWASP References:
- A01:2021 - Broken Access Control
- CWE-22: Path Traversal
- CWE-23: Relative Path Traversal

Created for Issue #129 - Path Traversal Vulnerability Risk
"""

import os
import re
from pathlib import Path
from typing import Optional, Set, Union
import logging

logger = logging.getLogger(__name__)


class PathTraversalError(Exception):
    """Raised when path traversal attack is detected."""
    pass


class InvalidFilenameError(Exception):
    """Raised when filename contains invalid characters."""
    pass


class FileExtensionError(Exception):
    """Raised when file extension is not in allowed list."""
    pass


# Default allowed file extensions (can be overridden per use case)
DEFAULT_ALLOWED_EXTENSIONS: Set[str] = {
    # Documents
    '.txt', '.md', '.pdf', '.doc', '.docx',
    # Images
    '.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp',
    # Data
    '.json', '.yaml', '.yml', '.xml', '.csv',
    # Code
    '.py', '.js', '.ts', '.go', '.rs',
    # Config
    '.conf', '.config', '.ini', '.toml',
    # Archives
    '.tar', '.gz', '.zip', '.bz2',
}

# Dangerous patterns to reject
DANGEROUS_PATTERNS = [
    r'\.\.',  # Parent directory reference
    r'~',  # Home directory expansion
    r'\x00',  # Null byte
    r'[\r\n]',  # Line breaks
    r'[<>:"|?*]',  # Windows reserved characters
]


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    Sanitize a filename to prevent path traversal and injection attacks.

    Removes:
    - Path separators (/, \\)
    - Null bytes
    - Leading dots (hidden files)
    - Dangerous characters

    Args:
        filename: The filename to sanitize
        max_length: Maximum allowed filename length (default: 255)

    Returns:
        Sanitized filename

    Raises:
        InvalidFilenameError: If filename is invalid or becomes empty after sanitization

    Examples:
        >>> sanitize_filename("file.txt")
        'file.txt'
        >>> sanitize_filename("../../../etc/passwd")
        'passwd'
        >>> sanitize_filename(".htaccess")
        'htaccess'
    """
    if not filename or not isinstance(filename, str):
        raise InvalidFilenameError("Filename must be a non-empty string")

    # Remove null bytes
    filename = filename.replace('\x00', '')

    # Get basename to remove any directory components
    filename = os.path.basename(filename)

    # Check for dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, filename):
            raise InvalidFilenameError(
                f"Filename contains dangerous pattern: {pattern}"
            )

    # Remove leading dots (hidden files)
    filename = filename.lstrip('.')

    # Remove any remaining path separators (defense in depth)
    filename = filename.replace('/', '').replace('\\', '')

    # Validate length
    if len(filename) == 0:
        raise InvalidFilenameError("Filename is empty after sanitization")

    if len(filename) > max_length:
        raise InvalidFilenameError(
            f"Filename too long: {len(filename)} > {max_length}"
        )

    return filename


def validate_file_extension(
    filename: str,
    allowed_extensions: Optional[Set[str]] = None
) -> None:
    """
    Validate that file has an allowed extension.

    Args:
        filename: The filename to check
        allowed_extensions: Set of allowed extensions (with leading dot)
                          If None, uses DEFAULT_ALLOWED_EXTENSIONS

    Raises:
        FileExtensionError: If extension is not allowed

    Examples:
        >>> validate_file_extension("file.txt")  # OK
        >>> validate_file_extension("file.exe")  # Raises FileExtensionError
    """
    if allowed_extensions is None:
        allowed_extensions = DEFAULT_ALLOWED_EXTENSIONS

    # Get file extension (lowercase for case-insensitive comparison)
    ext = Path(filename).suffix.lower()

    if not ext:
        raise FileExtensionError("File has no extension")

    if ext not in allowed_extensions:
        raise FileExtensionError(
            f"File extension '{ext}' not allowed. "
            f"Allowed: {', '.join(sorted(allowed_extensions))}"
        )


def validate_file_path(
    base_dir: Union[str, Path],
    user_path: str,
    allowed_extensions: Optional[Set[str]] = None,
    allow_create: bool = False
) -> Path:
    """
    Validate that a user-provided path is safe and within the base directory.

    This function prevents path traversal attacks by:
    1. Sanitizing the filename
    2. Resolving symbolic links
    3. Ensuring the resolved path is within base_dir
    4. Validating file extension

    Args:
        base_dir: Base directory that files must be within
        user_path: User-provided path component (filename or relative path)
        allowed_extensions: Set of allowed file extensions (with leading dot)
        allow_create: If False, file must exist (default: False)

    Returns:
        Validated absolute Path object

    Raises:
        PathTraversalError: If path traversal is detected
        InvalidFilenameError: If filename is invalid
        FileExtensionError: If extension not allowed
        FileNotFoundError: If file doesn't exist and allow_create=False

    Examples:
        >>> validate_file_path("/var/uploads", "file.txt")
        Path('/var/uploads/file.txt')

        >>> validate_file_path("/var/uploads", "../../../etc/passwd")
        # Raises PathTraversalError
    """
    # Convert base_dir to absolute Path
    base_dir = Path(base_dir).resolve()

    if not base_dir.exists():
        raise PathTraversalError(f"Base directory does not exist: {base_dir}")

    if not base_dir.is_dir():
        raise PathTraversalError(f"Base directory is not a directory: {base_dir}")

    # Sanitize the user-provided filename/path
    safe_name = sanitize_filename(os.path.basename(user_path))

    # Validate extension if required
    if allowed_extensions is not None:
        validate_file_extension(safe_name, allowed_extensions)

    # Construct full path
    full_path = (base_dir / safe_name).resolve()

    # CRITICAL: Check if resolved path is within base_dir
    # Use resolve() to handle symlinks and .. components
    try:
        # relative_to() will raise ValueError if not a subpath
        full_path.relative_to(base_dir)
    except ValueError:
        raise PathTraversalError(
            f"Path traversal detected: '{user_path}' resolves outside base directory"
        )

    # Additional check: ensure path starts with base_dir (defense in depth)
    if not str(full_path).startswith(str(base_dir) + os.sep):
        # Edge case: if paths are equal (file at base_dir root)
        if full_path != base_dir:
            raise PathTraversalError(
                f"Path traversal detected: '{user_path}' is not within base directory"
            )

    # Check file exists if required
    if not allow_create and not full_path.exists():
        raise FileNotFoundError(f"File not found: {safe_name}")

    return full_path


def safe_read_file(
    base_dir: Union[str, Path],
    filename: str,
    max_size_bytes: int = 10 * 1024 * 1024,  # 10MB default
    allowed_extensions: Optional[Set[str]] = None
) -> bytes:
    """
    Safely read a file with path validation and size limits.

    Args:
        base_dir: Base directory where file must be located
        filename: Filename to read (must be within base_dir)
        max_size_bytes: Maximum file size in bytes (default: 10MB)
        allowed_extensions: Set of allowed file extensions

    Returns:
        File contents as bytes

    Raises:
        PathTraversalError: If path traversal detected
        FileNotFoundError: If file doesn't exist
        ValueError: If file is too large
        InvalidFilenameError: If filename is invalid
        FileExtensionError: If extension not allowed

    Examples:
        >>> content = safe_read_file("/var/uploads", "file.txt")
    """
    # Validate path
    file_path = validate_file_path(
        base_dir=base_dir,
        user_path=filename,
        allowed_extensions=allowed_extensions,
        allow_create=False  # File must exist
    )

    # Check file size
    file_size = file_path.stat().st_size
    if file_size > max_size_bytes:
        raise ValueError(
            f"File too large: {file_size} bytes > {max_size_bytes} bytes"
        )

    # Read file
    try:
        return file_path.read_bytes()
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        raise


def safe_write_file(
    base_dir: Union[str, Path],
    filename: str,
    content: bytes,
    max_size_bytes: int = 10 * 1024 * 1024,  # 10MB default
    allowed_extensions: Optional[Set[str]] = None,
    atomic: bool = True
) -> Path:
    """
    Safely write a file with path validation, size limits, and atomic writes.

    Uses atomic write (temp file + rename) to prevent corruption.

    Args:
        base_dir: Base directory where file will be written
        filename: Filename to write (must be within base_dir)
        content: File contents as bytes
        max_size_bytes: Maximum file size in bytes (default: 10MB)
        allowed_extensions: Set of allowed file extensions
        atomic: Use atomic writes (temp file + rename) (default: True)

    Returns:
        Path to written file

    Raises:
        PathTraversalError: If path traversal detected
        ValueError: If content is too large
        InvalidFilenameError: If filename is invalid
        FileExtensionError: If extension not allowed

    Examples:
        >>> path = safe_write_file("/var/uploads", "file.txt", b"content")
    """
    # Validate path
    file_path = validate_file_path(
        base_dir=base_dir,
        user_path=filename,
        allowed_extensions=allowed_extensions,
        allow_create=True  # File can be created
    )

    # Check content size
    if len(content) > max_size_bytes:
        raise ValueError(
            f"Content too large: {len(content)} bytes > {max_size_bytes} bytes"
        )

    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if atomic:
            # Atomic write: temp file + rename
            import tempfile
            import shutil

            # Create temp file in same directory (for atomic rename)
            temp_fd, temp_path = tempfile.mkstemp(
                dir=file_path.parent,
                prefix=f".{file_path.stem}_",
                suffix=f"{file_path.suffix}.tmp"
            )

            try:
                # Write content to temp file
                with os.fdopen(temp_fd, 'wb') as f:
                    f.write(content)

                # Set permissions (owner read/write only)
                os.chmod(temp_path, 0o600)

                # Atomic rename
                shutil.move(temp_path, file_path)

            except Exception:
                # Clean up temp file on error
                try:
                    os.unlink(temp_path)
                except:
                    pass
                raise
        else:
            # Non-atomic write
            file_path.write_bytes(content)
            os.chmod(file_path, 0o600)

        logger.info(f"Successfully wrote file: {file_path}")
        return file_path

    except Exception as e:
        logger.error(f"Error writing file {file_path}: {e}")
        raise


def validate_directory_path(
    base_dir: Union[str, Path],
    user_path: str,
    allow_create: bool = False
) -> Path:
    """
    Validate that a user-provided directory path is safe and within base_dir.

    Args:
        base_dir: Base directory that subdirectories must be within
        user_path: User-provided directory path component
        allow_create: If False, directory must exist (default: False)

    Returns:
        Validated absolute Path object

    Raises:
        PathTraversalError: If path traversal detected
        InvalidFilenameError: If directory name is invalid
        FileNotFoundError: If directory doesn't exist and allow_create=False

    Examples:
        >>> validate_directory_path("/var/data", "subdir")
        Path('/var/data/subdir')
    """
    # Convert base_dir to absolute Path
    base_dir = Path(base_dir).resolve()

    if not base_dir.exists():
        raise PathTraversalError(f"Base directory does not exist: {base_dir}")

    if not base_dir.is_dir():
        raise PathTraversalError(f"Base directory is not a directory: {base_dir}")

    # Sanitize the directory name (treat as filename without extension check)
    dir_name = sanitize_filename(os.path.basename(user_path))

    # Construct full path
    full_path = (base_dir / dir_name).resolve()

    # CRITICAL: Check if resolved path is within base_dir
    try:
        full_path.relative_to(base_dir)
    except ValueError:
        raise PathTraversalError(
            f"Path traversal detected: '{user_path}' resolves outside base directory"
        )

    # Additional check (defense in depth)
    if not str(full_path).startswith(str(base_dir) + os.sep):
        if full_path != base_dir:
            raise PathTraversalError(
                f"Path traversal detected: '{user_path}' is not within base directory"
            )

    # Check directory exists if required
    if not allow_create and not full_path.exists():
        raise FileNotFoundError(f"Directory not found: {dir_name}")

    if full_path.exists() and not full_path.is_dir():
        raise PathTraversalError(f"Path exists but is not a directory: {full_path}")

    return full_path


def validate_npm_package_name(package_name: str) -> str:
    """
    Validate NPM package name to prevent path traversal via package names.

    NPM package names must match: ^(@[a-z0-9-~][a-z0-9-._~]*/)?[a-z0-9-~][a-z0-9-._~]*$

    Args:
        package_name: NPM package name to validate

    Returns:
        Validated package name

    Raises:
        InvalidFilenameError: If package name is invalid

    Examples:
        >>> validate_npm_package_name("@instinctx_dev/neuro-skill-blucli")
        '@instinctx_dev/neuro-skill-blucli'
        >>> validate_npm_package_name("../../../etc/passwd")
        # Raises InvalidFilenameError
    """
    # NPM package name regex (simplified)
    # Scoped: @scope/package-name
    # Unscoped: package-name
    npm_pattern = r'^(@[a-z0-9-_][a-z0-9-._]*\/)?[a-z0-9-_][a-z0-9-._]*$'

    if not re.match(npm_pattern, package_name.lower()):
        raise InvalidFilenameError(
            f"Invalid NPM package name: '{package_name}'. "
            "Must match NPM naming conventions."
        )

    # Additional checks for path traversal patterns
    if '..' in package_name or '~' in package_name or '\x00' in package_name:
        raise InvalidFilenameError(
            f"NPM package name contains dangerous characters: '{package_name}'"
        )

    return package_name


def validate_go_package_path(package_path: str) -> str:
    """
    Validate Go package import path to prevent path traversal.

    Go import paths should match: ^[a-zA-Z0-9.-]+(/[a-zA-Z0-9._-]+)*(@[a-zA-Z0-9._-]+)?$

    Args:
        package_path: Go package import path to validate

    Returns:
        Validated package path

    Raises:
        InvalidFilenameError: If package path is invalid

    Examples:
        >>> validate_go_package_path("github.com/user/package@v1.0.0")
        'github.com/user/package@v1.0.0'
        >>> validate_go_package_path("../../etc/passwd")
        # Raises InvalidFilenameError
    """
    # Go package path regex
    # Format: domain.com/user/package@version
    go_pattern = r'^[a-zA-Z0-9.-]+(/[a-zA-Z0-9._-]+)*(@[a-zA-Z0-9._-]+)?$'

    if not re.match(go_pattern, package_path):
        raise InvalidFilenameError(
            f"Invalid Go package path: '{package_path}'. "
            "Must match Go import path conventions."
        )

    # Additional checks
    if '..' in package_path or '~' in package_path or '\x00' in package_path:
        raise InvalidFilenameError(
            f"Go package path contains dangerous characters: '{package_path}'"
        )

    return package_path


# Whitelist of allowed configuration directories
ALLOWED_CONFIG_DIRS = {
    Path.home() / ".openclaw",
    Path.home() / ".wireguard",
    Path("/etc/wireguard"),  # System-wide WireGuard config
}


def validate_config_directory(config_dir: Union[str, Path]) -> Path:
    """
    Validate that a configuration directory is in the whitelist.

    Args:
        config_dir: Configuration directory to validate

    Returns:
        Validated Path object

    Raises:
        PathTraversalError: If directory is not in whitelist

    Examples:
        >>> validate_config_directory("~/.openclaw")
        Path('/home/user/.openclaw')
        >>> validate_config_directory("/etc/passwd")
        # Raises PathTraversalError
    """
    config_path = Path(config_dir).expanduser().resolve()

    # Check if in whitelist
    if config_path not in ALLOWED_CONFIG_DIRS:
        # Allow subdirectories of whitelisted paths
        is_subdir = any(
            str(config_path).startswith(str(allowed_dir))
            for allowed_dir in ALLOWED_CONFIG_DIRS
        )

        if not is_subdir:
            raise PathTraversalError(
                f"Configuration directory not in whitelist: {config_path}. "
                f"Allowed: {', '.join(str(d) for d in ALLOWED_CONFIG_DIRS)}"
            )

    return config_path
