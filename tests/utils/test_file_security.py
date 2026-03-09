"""
Tests for File Security Utilities (Issue #129)

Tests path traversal prevention and secure file operations.
"""
import os
import tempfile
import pytest
from pathlib import Path

from backend.utils.file_security import (
    sanitize_filename,
    validate_file_extension,
    validate_file_path,
    safe_read_file,
    safe_write_file,
    validate_directory_path,
    validate_npm_package_name,
    validate_go_package_path,
    validate_config_directory,
    PathTraversalError,
    InvalidFilenameError,
    FileExtensionError,
)


class TestSanitizeFilename:
    """Test filename sanitization"""

    def test_valid_filename(self):
        """Test that valid filenames pass through unchanged"""
        assert sanitize_filename("file.txt") == "file.txt"
        assert sanitize_filename("my-file_123.json") == "my-file_123.json"

    def test_path_separator_removal(self):
        """Test that path separators are removed"""
        assert sanitize_filename("path/to/file.txt") == "file.txt"
        assert sanitize_filename("path\\to\\file.txt") == "file.txt"
        assert sanitize_filename("/etc/passwd") == "passwd"

    def test_parent_directory_reference(self):
        """Test that parent directory references are rejected"""
        with pytest.raises(InvalidFilenameError, match="dangerous pattern"):
            sanitize_filename("../../../etc/passwd")

    def test_null_byte_removal(self):
        """Test that null bytes are removed"""
        assert sanitize_filename("file\x00.txt") == "file.txt"

    def test_hidden_file_dots(self):
        """Test that leading dots are removed"""
        assert sanitize_filename(".htaccess") == "htaccess"
        assert sanitize_filename("...hidden") == "hidden"

    def test_empty_filename(self):
        """Test that empty filenames are rejected"""
        with pytest.raises(InvalidFilenameError, match="empty"):
            sanitize_filename("")

        with pytest.raises(InvalidFilenameError, match="empty"):
            sanitize_filename(".")

    def test_max_length(self):
        """Test filename length limits"""
        long_name = "a" * 300
        with pytest.raises(InvalidFilenameError, match="too long"):
            sanitize_filename(long_name)


class TestValidateFileExtension:
    """Test file extension validation"""

    def test_valid_extensions(self):
        """Test that valid extensions pass"""
        validate_file_extension("file.txt")
        validate_file_extension("document.pdf")
        validate_file_extension("image.PNG")  # Case insensitive

    def test_invalid_extension(self):
        """Test that invalid extensions are rejected"""
        with pytest.raises(FileExtensionError):
            validate_file_extension("malware.exe")

        with pytest.raises(FileExtensionError):
            validate_file_extension("script.sh")

    def test_no_extension(self):
        """Test that files without extensions are rejected"""
        with pytest.raises(FileExtensionError, match="no extension"):
            validate_file_extension("README")

    def test_custom_allowed_extensions(self):
        """Test custom extension whitelist"""
        validate_file_extension("file.custom", allowed_extensions={".custom"})

        with pytest.raises(FileExtensionError):
            validate_file_extension("file.txt", allowed_extensions={".custom"})


class TestValidateFilePath:
    """Test path validation with directory containment"""

    def test_valid_file_path(self, tmp_path):
        """Test that valid paths within base directory are allowed"""
        test_file = tmp_path / "file.txt"
        test_file.write_text("content")

        validated = validate_file_path(tmp_path, "file.txt")
        assert validated == test_file

    def test_path_traversal_parent_dir(self, tmp_path):
        """Test that parent directory traversal is blocked"""
        with pytest.raises(PathTraversalError):
            validate_file_path(tmp_path, "../../../etc/passwd")

    def test_path_traversal_absolute(self, tmp_path):
        """Test that absolute paths are blocked"""
        with pytest.raises(InvalidFilenameError):
            validate_file_path(tmp_path, "/etc/passwd")

    def test_symlink_traversal(self, tmp_path):
        """Test that symlinks outside base dir are blocked"""
        # Create symlink to /etc/passwd
        symlink = tmp_path / "evil_link"
        if os.name != 'nt':  # Skip on Windows
            symlink.symlink_to("/etc/passwd")

            with pytest.raises((PathTraversalError, FileNotFoundError)):
                # Should fail either due to traversal or file not found
                validate_file_path(tmp_path, "evil_link")

    def test_file_not_found(self, tmp_path):
        """Test that missing files are rejected by default"""
        with pytest.raises(FileNotFoundError):
            validate_file_path(tmp_path, "nonexistent.txt", allow_create=False)

    def test_allow_create(self, tmp_path):
        """Test that allow_create permits non-existent files"""
        validated = validate_file_path(tmp_path, "new_file.txt", allow_create=True)
        assert validated == tmp_path / "new_file.txt"

    def test_extension_validation(self, tmp_path):
        """Test extension validation during path validation"""
        with pytest.raises(FileExtensionError):
            validate_file_path(
                tmp_path,
                "malware.exe",
                allowed_extensions={".txt"},
                allow_create=True
            )


class TestSafeReadFile:
    """Test safe file reading"""

    def test_safe_read_success(self, tmp_path):
        """Test successful file read"""
        test_file = tmp_path / "test.txt"
        test_content = b"Hello, World!"
        test_file.write_bytes(test_content)

        content = safe_read_file(tmp_path, "test.txt")
        assert content == test_content

    def test_safe_read_size_limit(self, tmp_path):
        """Test that oversized files are rejected"""
        test_file = tmp_path / "large.txt"
        large_content = b"x" * (11 * 1024 * 1024)  # 11MB
        test_file.write_bytes(large_content)

        with pytest.raises(ValueError, match="too large"):
            safe_read_file(tmp_path, "large.txt", max_size_bytes=10 * 1024 * 1024)

    def test_safe_read_traversal_blocked(self, tmp_path):
        """Test that path traversal is blocked during read"""
        with pytest.raises(PathTraversalError):
            safe_read_file(tmp_path, "../../../etc/passwd")


class TestSafeWriteFile:
    """Test safe file writing"""

    def test_safe_write_success(self, tmp_path):
        """Test successful file write"""
        content = b"Test content"
        result = safe_write_file(tmp_path, "output.txt", content)

        assert result.exists()
        assert result.read_bytes() == content

    def test_safe_write_atomic(self, tmp_path):
        """Test atomic write (temp file + rename)"""
        content = b"Atomic content"
        result = safe_write_file(tmp_path, "atomic.txt", content, atomic=True)

        assert result.exists()
        assert result.read_bytes() == content

        # Verify no temp files remain
        temp_files = list(tmp_path.glob(".*tmp"))
        assert len(temp_files) == 0

    def test_safe_write_size_limit(self, tmp_path):
        """Test that oversized content is rejected"""
        large_content = b"x" * (11 * 1024 * 1024)  # 11MB

        with pytest.raises(ValueError, match="too large"):
            safe_write_file(
                tmp_path,
                "large.txt",
                large_content,
                max_size_bytes=10 * 1024 * 1024
            )

    def test_safe_write_permissions(self, tmp_path):
        """Test that file permissions are restrictive"""
        if os.name == 'nt':
            pytest.skip("Permission tests not applicable on Windows")

        result = safe_write_file(tmp_path, "secure.txt", b"content")

        # Check permissions are 0600 (owner read/write only)
        stat = result.stat()
        assert stat.st_mode & 0o777 == 0o600

    def test_safe_write_traversal_blocked(self, tmp_path):
        """Test that path traversal is blocked during write"""
        with pytest.raises(PathTraversalError):
            safe_write_file(tmp_path, "../../../tmp/evil.txt", b"content")


class TestValidateDirectoryPath:
    """Test directory path validation"""

    def test_valid_directory(self, tmp_path):
        """Test that valid subdirectories are allowed"""
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        validated = validate_directory_path(tmp_path, "subdir")
        assert validated == subdir

    def test_directory_traversal_blocked(self, tmp_path):
        """Test that directory traversal is blocked"""
        with pytest.raises(PathTraversalError):
            validate_directory_path(tmp_path, "../../../etc")


class TestValidateNpmPackageName:
    """Test NPM package name validation"""

    def test_valid_package_names(self):
        """Test that valid NPM package names pass"""
        validate_npm_package_name("express")
        validate_npm_package_name("@types/node")
        validate_npm_package_name("@instinctx_dev/neuro-skill-blucli")

    def test_invalid_package_names(self):
        """Test that invalid NPM package names are rejected"""
        with pytest.raises(InvalidFilenameError):
            validate_npm_package_name("../../etc/passwd")

        with pytest.raises(InvalidFilenameError):
            validate_npm_package_name("UPPERCASE")  # NPM packages are lowercase

        with pytest.raises(InvalidFilenameError):
            validate_npm_package_name("package name")  # No spaces


class TestValidateGoPackagePath:
    """Test Go package path validation"""

    def test_valid_go_paths(self):
        """Test that valid Go import paths pass"""
        validate_go_package_path("github.com/user/package")
        validate_go_package_path("github.com/user/package@v1.0.0")
        validate_go_package_path("golang.org/x/crypto")

    def test_invalid_go_paths(self):
        """Test that invalid Go paths are rejected"""
        with pytest.raises(InvalidFilenameError):
            validate_go_package_path("../../etc/passwd")

        with pytest.raises(InvalidFilenameError):
            validate_go_package_path("../relative/path")


class TestValidateConfigDirectory:
    """Test configuration directory whitelist"""

    def test_valid_config_dirs(self):
        """Test that whitelisted directories are allowed"""
        home = Path.home()
        openclaw_dir = home / ".openclaw"

        validated = validate_config_directory(openclaw_dir)
        assert validated == openclaw_dir.resolve()

    def test_subdirectory_allowed(self):
        """Test that subdirectories of whitelisted dirs are allowed"""
        home = Path.home()
        subdir = home / ".openclaw" / "plugins"

        validated = validate_config_directory(subdir)
        assert validated == subdir.resolve()

    def test_non_whitelisted_directory(self):
        """Test that non-whitelisted directories are rejected"""
        with pytest.raises(PathTraversalError, match="not in whitelist"):
            validate_config_directory("/tmp/random")


class TestSecurityIntegration:
    """Integration tests for path traversal prevention"""

    def test_personality_file_security(self, tmp_path):
        """Test that personality loader is protected"""
        # Simulate PersonalityLoader behavior
        base_dir = tmp_path / "personalities"
        base_dir.mkdir()

        # Try to access file outside base directory
        with pytest.raises(PathTraversalError):
            validate_file_path(base_dir, "../../../etc/passwd")

    def test_skill_installation_security(self, tmp_path):
        """Test that skill installation is protected"""
        # Simulate skill installation path construction
        npm_prefix = tmp_path / "npm-global"
        npm_prefix.mkdir()

        # Malicious package name should be rejected
        with pytest.raises(InvalidFilenameError):
            validate_npm_package_name("../../../evil")

    def test_config_file_security(self, tmp_path):
        """Test that config file access is protected"""
        config_dir = tmp_path / ".openclaw"
        config_dir.mkdir()

        # Try to write config outside allowed directory
        with pytest.raises(PathTraversalError):
            validate_file_path(config_dir, "../../../tmp/evil.json", allow_create=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
