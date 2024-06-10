from textwrap import dedent

from django.core.management.base import BaseCommand, CommandError
from django.http import HttpRequest
from django.utils import translation
from django.utils.module_loading import import_string

from rest_framework.request import Request

from drf_spectacular.renderers import OpenApiJsonRenderer, OpenApiYamlRenderer
from drf_spectacular.settings import patched_settings
from drf_spectacular.validation import validate_schema

from pulpcore.openapi import PulpSchemaGenerator


class SchemaValidationError(CommandError):
    pass


class Command(BaseCommand):
    help = dedent(
        """
        Generate OpenAPI3 schema for the Pulp API.

        The type of schema generated can be modified by providing some options.
          --component <str> comma separated list of app_labels
          --bindings flag, to produce operation ids used for bindings generation
          --pk-path flag, whether paths are presented with PK or href variable
    """
    )

    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--component", dest="component", default=None, type=str)
        parser.add_argument("--bindings", dest="bindings", action="store_true")
        parser.add_argument("--pk-path", dest="pk_path", action="store_true")
        parser.add_argument(
            "--format",
            dest="format",
            choices=["openapi", "openapi-json"],
            default="openapi-json",
            type=str,
        )
        parser.add_argument("--urlconf", dest="urlconf", default=None, type=str)
        parser.add_argument("--file", dest="file", default=None, type=str)
        parser.add_argument("--validate", dest="validate", default=False, action="store_true")
        parser.add_argument("--lang", dest="lang", default=None, type=str)
        parser.add_argument("--custom-settings", dest="custom_settings", default=None, type=str)

    def handle(self, *args, **options):
        generator = PulpSchemaGenerator(
            urlconf=options["urlconf"],
        )

        if options["custom_settings"]:
            custom_settings = import_string(options["custom_settings"])
        else:
            custom_settings = None

        with patched_settings(custom_settings):
            request = Request(HttpRequest())
            request.META["SERVER_NAME"] = "localhost"
            request.META["SERVER_PORT"] = "24817"
            if options["component"]:
                request.query_params["component"] = options["component"]
            if options["bindings"]:
                request.query_params["bindings"] = 1
            if options["pk_path"]:
                request.query_params["pk_path"] = 1

            if options["lang"]:
                with translation.override(options["lang"]):
                    schema = generator.get_schema(request=request, public=True)
            else:
                schema = generator.get_schema(request=request, public=True)

        if options["validate"]:
            try:
                validate_schema(schema)
            except Exception as e:
                raise SchemaValidationError(e)

        renderer = self.get_renderer(options["format"])
        output = renderer.render(schema, renderer_context={})

        if options["file"]:
            with open(options["file"], "wb") as f:
                f.write(output)
        else:
            self.stdout.write(output.decode())

    def get_renderer(self, format):
        renderer_cls = {
            "openapi": OpenApiYamlRenderer,
            "openapi-json": OpenApiJsonRenderer,
        }[format]
        return renderer_cls()
