import pytest
from dynaconf.validator import ValidationError


def test_content_origin(settings):
    """Test validation error is raised when CONTENT_ORIGIN is missing."""
    # force needs to be True in order to remove CONTENT_ORIGIN since keep makes it a default
    settings.unset("CONTENT_ORIGIN", force=True)
    with pytest.raises(ValidationError):
        settings.validators.validate()


def test_cache_enabled(settings):
    """Test that when CACHE_ENABLED is set REDIS_URL or REDIS_HOST & REDIS_PORT."""
    settings.set("CACHE_ENABLED", True)
    settings.unset("REDIS_URL", force=True)
    settings.unset("REDIS_HOST", force=True)
    settings.unset("REDIS_PORT", force=True)
    with pytest.raises(ValidationError):
        settings.validators.validate()

    settings.set("REDIS_HOST", "localhost")
    with pytest.raises(ValidationError):
        settings.validators.validate()

    settings.unset("REDIS_HOST", force=True)
    settings.set("REDIS_PORT", 8000)
    with pytest.raises(ValidationError):
        settings.validators.validate()


def test_allowed_content_checksums(settings):
    """Test that removing 'sha256' from ALLOWED_CONTENT_CHECKSUMS raises ValidationError."""
    settings.set("ALLOWED_CONTENT_CHECKSUMS", ["sha224", "sha512"])
    with pytest.raises(ValidationError):
        settings.validators.validate()


def test_unknown_content_checksums(settings):
    """Test that providing invalid checksum for ALLOWED_CONTENT_CHECKSUMS fails."""
    settings.set("ALLOWED_CONTENT_CHECKSUMS", ["aaa"])
    with pytest.raises(ValidationError):
        settings.validators.validate()


def test_api_root(settings):
    """Test that API_ROOT validation checks for beginning and ending '/'."""
    settings.set("API_ROOT", "/hi/there")
    with pytest.raises(ValidationError):
        settings.validators.validate()

    settings.set("API_ROOT", "hi/there/")
    with pytest.raises(ValidationError):
        settings.validators.validate()
