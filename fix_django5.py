#!/usr/bin/env python3
"""Fix Django 5 compatibility issues on backport branches."""
import yaml
import sys
from pathlib import Path


def fix_template_config(branch):
    """Update template_config.yml storage settings from Django 4 to Django 5 format."""
    path = Path("template_config.yml")
    config = yaml.safe_load(path.read_text())
    changed = False

    # Fix azure settings
    azure = config.get("pulp_settings_azure", {})
    if azure and "DEFAULT_FILE_STORAGE" in azure:
        print(f"  Updating pulp_settings_azure to STORAGES format")
        new_azure = {"MEDIA_ROOT": ""}
        new_azure["STORAGES"] = {
            "default": {
                "BACKEND": azure.pop("DEFAULT_FILE_STORAGE"),
                "OPTIONS": {},
            },
            "staticfiles": {
                "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
            },
        }

        # Map old AZURE_ settings to OPTIONS
        azure_option_map = {
            "AZURE_ACCOUNT_KEY": "account_key",
            "AZURE_ACCOUNT_NAME": "account_name",
            "AZURE_CONNECTION_STRING": "connection_string",
            "AZURE_CONTAINER": "azure_container",
            "AZURE_LOCATION": "location",
            "AZURE_OVERWRITE_FILES": "overwrite_files",
            "AZURE_URL_EXPIRATION_SECS": "expiration_secs",
        }
        for old_key, new_key in azure_option_map.items():
            if old_key in azure:
                new_azure["STORAGES"]["default"]["OPTIONS"][new_key] = azure.pop(old_key)

        # Remove MEDIA_ROOT from old config (we set it in new_azure)
        azure.pop("MEDIA_ROOT", None)

        # Keep remaining settings (domain_enabled, api_root_rewrite_header, etc.)
        new_azure.update(azure)
        config["pulp_settings_azure"] = new_azure
        changed = True

    # Fix s3 settings
    s3 = config.get("pulp_settings_s3", {})
    if s3 and "DEFAULT_FILE_STORAGE" in s3:
        print(f"  Updating pulp_settings_s3 to STORAGES format")
        backend = s3.pop("DEFAULT_FILE_STORAGE")

        # Map old AWS_ settings to OPTIONS
        aws_option_map = {
            "AWS_ACCESS_KEY_ID": "access_key",
            "AWS_SECRET_ACCESS_KEY": "secret_key",
            "AWS_STORAGE_BUCKET_NAME": "bucket_name",
            "AWS_S3_ENDPOINT_URL": "endpoint_url",
            "AWS_S3_REGION_NAME": "region_name",
            "AWS_S3_SIGNATURE_VERSION": "signature_version",
            "AWS_S3_ADDRESSING_STYLE": "addressing_style",
            "AWS_DEFAULT_ACL": "default_acl",
        }
        options = {}
        for old_key, new_key in aws_option_map.items():
            if old_key in s3:
                options[new_key] = s3.pop(old_key)

        # Handle the '@none None' -> '@none' conversion for default_acl
        if "default_acl" in options and options["default_acl"] == "@none None":
            options["default_acl"] = "@none"

        if "STORAGES" not in s3:
            s3["STORAGES"] = {
                "default": {
                    "BACKEND": backend,
                    "OPTIONS": options,
                },
                "staticfiles": {
                    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
                },
            }
        config["pulp_settings_s3"] = s3
        changed = True

    if changed:
        path.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))
        print(f"  template_config.yml updated")
    else:
        print(f"  template_config.yml already uses STORAGES format")

    return changed


def fix_handler_timezone(branch):
    """Fix django.utils.timezone.utc -> datetime.timezone.utc in handler.py."""
    path = Path("pulpcore/content/handler.py")
    if not path.exists():
        return False

    content = path.read_text()
    if "timezone.utc" not in content:
        print(f"  handler.py: no timezone.utc usage, skipping")
        return False

    import re

    # On 3.85: has `from datetime import datetime, timedelta` and `from django.utils import timezone`
    # We need to add `from datetime import timezone as dt_timezone` and replace `timezone.utc`
    # with `dt_timezone.utc` (but NOT `timezone.now()`)

    # Add dt_timezone import after existing datetime import
    datetime_import = re.search(r"^from datetime import .+$", content, re.MULTILINE)
    if datetime_import:
        old_line = datetime_import.group(0)
        if "timezone" not in old_line:
            content = content.replace(
                old_line,
                old_line + "\nfrom datetime import timezone as dt_timezone",
            )
    else:
        content = "from datetime import timezone as dt_timezone\n" + content

    # Replace only timezone.utc (not timezone.now, timezone.is_aware, etc.)
    content = re.sub(r"\btimezone\.utc\b", "dt_timezone.utc", content)

    path.write_text(content)
    print(f"  handler.py timezone.utc fixed")
    return True


def fix_serializers_domain(branch):
    """Fix bad import_string import in serializers/domain.py (3.28)."""
    path = Path("pulpcore/app/serializers/domain.py")
    if not path.exists():
        return False

    content = path.read_text()
    old = "from django.core.files.storage import import_string"
    if old not in content:
        return False

    content = content.replace(old, "from django.utils.module_loading import import_string")
    path.write_text(content)
    print(f"  serializers/domain.py import fixed")
    return True


if __name__ == "__main__":
    branch = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    print(f"Fixing Django 5 issues on {branch}...")
    fix_template_config(branch)
    fix_handler_timezone(branch)
    fix_serializers_domain(branch)
