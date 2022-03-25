from django.test import TestCase
from django.conf import settings
from dynaconf.validator import ValidationError


class SettingsTestCase(TestCase):
    def test_content_origin(self):
        """Test validation error is raised when CONTENT_ORIGIN is missing."""
        # See https://github.com/rochacbruno/dynaconf/issues/731
        # keep needs to be True in order to copy all the current settings already initialized
        msettings = settings.from_env("development", keep=True, validators=settings.validators)
        # force needs to be True in order to remove CONTENT_ORIGIN since keep makes it a default
        msettings.unset("CONTENT_ORIGIN", force=True)
        with self.assertRaises(ValidationError):
            msettings.validators.validate()

    def test_cache_enabled(self):
        """Test that when CACHE_ENABLED is set REDIS_URL or REDIS_HOST & REDIS_PORT."""
        msettings = settings.from_env("development", keep=True, validators=settings.validators)
        msettings.set("CACHE_ENABLED", True)
        msettings.unset("REDIS_URL", force=True)
        msettings.unset("REDIS_HOST", force=True)
        msettings.unset("REDIS_PORT", force=True)
        with self.assertRaises(ValidationError):
            msettings.validators.validate()

        msettings.set("REDIS_HOST", "localhost")
        with self.assertRaises(ValidationError):
            msettings.validators.validate()

        msettings.unset("REDIS_HOST", force=True)
        msettings.set("REDIS_PORT", 8000)
        with self.assertRaises(ValidationError):
            msettings.validators.validate()

    def test_allowed_content_checksums(self):
        """Test that removing 'sha256' from ALLOWED_CONTENT_CHECKSUMS raises ValidationError."""
        msettings = settings.from_env("development", keep=True, validators=settings.validators)
        msettings.set("ALLOWED_CONTENT_CHECKSUMS", ["sha224", "sha512"])
        with self.assertRaises(ValidationError):
            msettings.validators.validate()

    def test_unknown_content_checksums(self):
        """Test that providing invalid checksum for ALLOWED_CONTENT_CHECKSUMS fails."""
        msettings = settings.from_env("development", keep=True, validators=settings.validators)
        msettings.set("ALLOWED_CONTENT_CHECKSUMS", ["aaa"])
        with self.assertRaises(ValidationError):
            msettings.validators.validate()

    def test_api_root(self):
        """Test that API_ROOT validation checks for beginning and ending '/'."""
        msettings = settings.from_env("development", keep=True, validators=settings.validators)
        msettings.set("API_ROOT", "/hi/there")
        with self.assertRaises(ValidationError):
            msettings.validators.validate()

        msettings.set("API_ROOT", "hi/there/")
        with self.assertRaises(ValidationError):
            msettings.validators.validate()
