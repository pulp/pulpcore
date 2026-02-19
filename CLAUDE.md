# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pulpcore is a Django-based REST API platform for managing and distributing software package repositories. It includes two bundled plugins: `pulp_file` (file content management) and `pulp_certguard` (certificate-based access control).

## Commands

### Installation
```bash
pip install -e .
pip install -r unittest_requirements.txt   # For unit tests
pip install -r lint_requirements.txt       # For linting
pip install -r functest_requirements.txt   # For functional tests
```

### Running Tests
```bash
# All unit tests
pytest pulpcore/tests/unit -v

# Single test file
pytest pulpcore/tests/unit/test_cache.py -v

# Single test by name
pytest pulpcore/tests/unit/test_cache.py::TestClass::test_method -v

# Functional tests (requires a running Pulp instance)
pytest pulpcore/tests/functional -m parallel -n 8
pytest pulpcore/tests/functional -m "not parallel"
```

### Linting
```bash
black --check --diff .          # Check formatting
black .                         # Auto-format
flake8                          # Lint
check-manifest                  # Verify MANIFEST.in
```

### Django Management
```bash
pulpcore-manager makemigrations
pulpcore-manager migrate
pulpcore-manager openapi --file api.json
pulpcore-manager openapi --bindings --component core --file core-api.json
```

### Running Services
```bash
pulpcore-api        # API server (gunicorn)
pulpcore-content    # Content download server
pulpcore-worker     # Async task worker
```

## Architecture

### Request Lifecycle
1. **API server** (`pulpcore/app/entrypoint.py`) receives requests via gunicorn
2. **Django middleware** (`pulpcore/middleware.py`) handles context tracking (domain, current task)
3. **Viewsets** (`pulpcore/plugin/viewsets.py`, `pulpcore/app/`) dispatch to serializers and models
4. **Access control** via `drf-access-policy` — policies live in `pulpcore/app/access_policy.py` and `global_access_conditions.py`
5. **Long-running operations** are dispatched as async tasks to the worker

### Async Task System (`pulpcore/tasking/`)
The worker is a custom implementation (not Celery). Workers poll for tasks stored in PostgreSQL, execute them, and persist results. Task state flows through the `Task` model (`pulpcore/app/models/task.py`). Kafka event streaming is optional (`pulpcore/tasking/kafka.py`).

### Content Model
Content follows a **Repository → RepositoryVersion → Publication → Distribution** workflow:
- `Repository`: Tracks content membership over time via immutable `RepositoryVersion` snapshots
- `Publication`: A versioned snapshot prepared for serving
- `Distribution`: A URL endpoint serving a Publication (or directly a RepositoryVersion)
- Content objects are content-addressed (SHA-256); files stored once regardless of how many repos reference them

### Plugin System
Plugins register via Python entry points (`pulpcore.plugin` group in `pyproject.toml`). Each plugin is a Django app that extends pulpcore's base models (`pulpcore/plugin/models.py`) and viewsets. The `pulpcore/pytest_plugin.py` provides shared test fixtures for all plugins.

### Configuration
Settings use **Dynaconf** — configuration is loaded from environment variables prefixed `PULP_` or from a file pointed to by `PULP_SETTINGS`. Never import `pulpcore.app.settings` directly; use `from django.conf import settings`.

### Multi-tenancy
Domain-based isolation: each request carries a `Domain` context (stored in thread-local via `pulpcore/app/contexts.py`). All querysets are domain-scoped automatically via model managers.

## Code Style

- **Line length**: 100 characters (black + flake8)
- Migrations are excluded from black/flake8

## Changelog

Each PR requires a changelog fragment in `CHANGES/`:
```bash
echo "Description of change" > CHANGES/<PR_NUMBER>.<type>
# types: feature, bugfix, doc, removal, deprecation, misc
# For plugin-specific changes, use subdirectories:
# CHANGES/plugin_api/<PR_NUMBER>.<type>
# CHANGES/pulp_file/<PR_NUMBER>.<type>
# CHANGES/pulp_certguard/<PR_NUMBER>.<type>
```
