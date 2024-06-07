from gettext import gettext as _

import re
from urllib.parse import urljoin

from django.conf import settings
from django.core.exceptions import FieldDoesNotExist
from django.http import HttpRequest
from django.utils.html import strip_tags
from drf_spectacular.drainage import reset_generator_stats
from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.plumbing import (
    ResolvedComponent,
    build_basic_type,
    build_parameter_type,
    build_root_object,
    force_instance,
    normalize_result_object,
    process_webhooks,
    resolve_django_path_parameter,
    resolve_regex_path_parameter,
)
from drf_spectacular.settings import spectacular_settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema_field
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import mixins, serializers
from rest_framework.exceptions import ParseError
from rest_framework.request import Request
from rest_framework.schemas.utils import get_pk_description

from pulpcore.app.apps import pulp_plugin_configs
from pulpcore.app.loggers import deprecation_logger


if settings.DOMAIN_ENABLED:
    API_ROOT_NO_FRONT_SLASH = settings.V3_DOMAIN_API_ROOT_NO_FRONT_SLASH.replace("slug:", "")
else:
    API_ROOT_NO_FRONT_SLASH = settings.V3_API_ROOT_NO_FRONT_SLASH
API_ROOT_NO_FRONT_SLASH = API_ROOT_NO_FRONT_SLASH.replace("<", "{").replace(">", "}")


# Python does not distinguish integer sizes. The safest assumption is that they are large.
extend_schema_field(OpenApiTypes.INT64)(serializers.IntegerField)


class PulpAutoSchema(AutoSchema):
    """Pulp Auto Schema."""

    method_mapping = {
        "get": "read",
        "post": "create",
        "put": "update",
        "patch": "partial_update",
        "delete": "delete",
    }

    def _tokenize_path(self):
        """
        Tokenize path.

        drf_spectacular uses this to tokenize the path:
            "/my/path/to/{variable}/api" => ["my", "path", "to", "api"]

        But pulp manipulates the path:
            "/pulp/api/v3/artifacts/{pulp_id}" == "{artifact_href}"

        This method extends _tokenize_path to handle pulp cases.

        """
        tokenized_path = []

        if getattr(self.view, "parent_viewset", None):
            tokenized_path.extend(self.view.parent_viewset.endpoint_pieces())

        if getattr(self.view, "endpoint_pieces", None):
            tokenized_path.extend(self.view.endpoint_pieces())

        if not tokenized_path:
            tokenized_path = super()._tokenize_path()
            if not tokenized_path and getattr(self.view, "get_view_name", None):
                tokenized_path.extend(self.view.get_view_name().split())

        path = "/".join(tokenized_path).replace(settings.V3_API_ROOT_NO_FRONT_SLASH, "")
        tokenized_path = path.split("/")

        return tokenized_path

    def get_tags(self):
        """
        Generate tags.

        For bindings, tags are used to group operation ids into same class.
        Example:
            "Content: Files" => ContentFilesAPI

        The path is used to generate a tag:
            "/pulp/api/v3/content/file/files/" => "Content: Files"

        For customize the tag, please set `pulp_tag_name` at your view.
        Example:
            class MyViewSet(ViewSet):
                pulp_tag_name = "Pulp: Customized Tag"

        """
        pulp_tag_name = getattr(self.view, "pulp_tag_name", False)
        if pulp_tag_name:
            return [pulp_tag_name]

        tokenized_path = self._tokenize_path()

        subpath = "/".join(tokenized_path)
        operation_keys = subpath.replace(settings.V3_API_ROOT_NO_FRONT_SLASH, "").split("/")
        operation_keys = [i.title() for i in operation_keys]
        if len(operation_keys) > 2:
            del operation_keys[1]
        if len(operation_keys) > 1:
            operation_keys[0] = "{key}:".format(key=operation_keys[0])
        tags = [" ".join(operation_keys)]

        return tags

    def get_operation_id_action(self):
        """
        Get action from operation_id.

        - For default actions: maps methods to action
            "patch" => "partial_update"
        - For customized actions: return the customized action
            e.g. "sync"
        """
        action_name = getattr(self.view, "action", self.method.lower())
        if action_name not in ["retrieve", "list", "destroy", "create"]:
            return action_name

        if self.method.lower() == "get" and self._is_list_view():
            return "list"

        return self.method_mapping[self.method.lower()]

    def get_operation_id(self):
        """
        Get operation id.

        Combines tokenized_path with action.
        Example:
            path = "/my/path/to/{variable}/api"
            method = "patch"

            Return "my_path_to_api_partial_update"

        """
        tokenized_path = self._tokenize_path()
        tokenized_path = [t.replace("-", "_").replace("/", "_").lower() for t in tokenized_path]

        return "_".join(tokenized_path + [self.get_operation_id_action()])

    def get_summary(self):
        """
        Returns summary of operation.
        This is the value that is displayed in the ReDoc document as the short name for the API
        operation.
        """
        if not hasattr(self.view, "queryset") or self.view.queryset is None:
            return None
        model = self.view.queryset.model
        operation = self.get_operation_id().split("_")[-1]
        resource = model._meta.verbose_name
        article = "a"
        if resource[0].lower() in "aeiou":
            article = "an"
        if operation == "read":
            return f"Inspect {article} {resource}"
        if operation == "list":
            resource = model._meta.verbose_name_plural
            return f"List {resource}"
        if operation == "create":
            return f"Create {article} {resource}"
        if operation == "update":
            return f"Update {article} {resource}"
        if operation == "delete":
            return f"Delete {article} {resource}"
        if operation == "partial_update":
            return f"Partially update {article} {resource}"

    def _get_serializer_name(self, serializer, direction, bypass_extensions=False):
        """
        Get serializer name.
        """
        name = super()._get_serializer_name(
            serializer, direction, bypass_extensions=bypass_extensions
        )
        if direction == "request":
            name = name[:-7]
        elif direction == "response" and "Response" not in name:
            name = name + "Response"
        return name

    def map_parsers(self):
        """
        Get request parsers.

        Handling cases with `FileField`.
        """
        parsers = super().map_parsers()
        serializer = force_instance(self.get_request_serializer())
        for field_name, field in getattr(serializer, "fields", {}).items():
            if isinstance(field, serializers.FileField) and self.method in ("PUT", "PATCH", "POST"):
                return ["multipart/form-data", "application/x-www-form-urlencoded"]
        return parsers

    def _get_request_body(self):
        """Get request body."""
        request_body = super()._get_request_body()
        if request_body:
            request_body["required"] = True
        return request_body

    def _get_response_bodies(self):
        """
        Handle response status code.
        """
        response = super()._get_response_bodies()
        if (
            self.method == "POST"
            and issubclass(self.view.__class__, mixins.CreateModelMixin)
            and "200" in response
        ):
            response["201"] = response.pop("200")

        return response


class PulpSchemaGenerator(SchemaGenerator):
    """Pulp Schema Generator."""

    @staticmethod
    def get_parameter_slug_from_model(model, prefix, pulp_model_alias=None):
        """Returns a path parameter name for the resource associated with the model.
        Args:
            model (django.db.models.Model): The model for which a path parameter name is needed
            prefix (str): Optional prefix to add to the slug
            pulp_model_alias (str): Optional model name to use instead of model.__name__
        Returns:
            str: *pulp_href where * is the model name in all lower case letters
        """
        app_label = model._meta.app_label
        model_name = pulp_model_alias or model.__name__
        parts = [part.lower() for part in re.findall("[A-Z][^A-Z]*", model_name)]
        if prefix:
            parts.insert(0, prefix)
        elif app_label != "core":
            parts.insert(0, app_label)
        parts.append("href")
        return "_".join(parts)

    @staticmethod
    def get_pk_path_param_name_from_model(model):
        """Returns a specific name for the primary key of a model.

        Args:
            model (django.db.models.Model): The model for which a path parameter name is needed

        Returns:
            str: *_pk where * is the model name in all lower case letters
        """
        return "%s_pk" % "_".join(
            [part.lower() for part in re.findall("[A-Z][^A-Z]*", model.__name__)]
        )

    def convert_endpoint_path_params(self, path, view, schema):
        """Replaces all 'pulp_id' path parameters with a specific name for the primary key.
        This method is used to ensure that the primary key name is consistent between nested
        endpoints. get_endpoints() returns paths that use 'pulp_id' for the top level path and a
        specific name for the nested paths. e.g.: repository_pk.
        This ensures that when the endpoints are sorted, the parent endpoint appears before the
        endpoints nested under it.
        Returns:
            path(str): The modified path.
        """
        if "{" not in path:
            return path
        if getattr(view, "queryset", None) is None:
            if hasattr(view, "model"):
                resource_model = view.model
            else:
                return path
        else:
            resource_model = view.queryset.model
        if resource_model:
            prefix = None
            pulp_model_alias = getattr(view, "pulp_model_alias", None)
            parent_viewset = getattr(view, "parent_viewset", None)
            if parent_viewset:
                if view.action in ["list", "create"]:
                    resource_model = parent_viewset.queryset.model
                    pulp_model_alias = getattr(parent_viewset, "pulp_model_alias", None)

                else:
                    parent_app_label = parent_viewset.queryset.model._meta.app_label
                    prefix_parts = [parent_viewset.endpoint_name]
                    if parent_app_label != "core":
                        prefix_parts.insert(0, parent_app_label)
                    prefix = "_".join(prefix_parts).replace("-", "_").replace("/", "_").lower()
            param_name = self.get_parameter_slug_from_model(
                resource_model, prefix, pulp_model_alias
            )
            resource_path = "%s}/" % path.rsplit(sep="}", maxsplit=1)[0]
            # This check prevents /pulp/{pulp_domain}/ from being converted for non-detail endpoints
            # Possibly affects plugin-specific urls, depends on their url structure
            if resource_path.lstrip("/") not in API_ROOT_NO_FRONT_SLASH:
                path = path.replace(resource_path, "{%s}" % param_name)
        return path

    def parse(self, input_request, public):
        """Iterate endpoints generating per method path operations."""
        result = {}
        self._initialise_endpoints()
        endpoints = self._get_paths_and_endpoints()

        query_params = {}
        if input_request:
            query_params = {k.replace("amp;", ""): v for k, v in input_request.query_params.items()}

        if spectacular_settings.SCHEMA_PATH_PREFIX is None:
            path_prefix = "/"
        else:
            path_prefix = spectacular_settings.SCHEMA_PATH_PREFIX
        if not path_prefix.startswith("^"):
            path_prefix = "^" + path_prefix  # make sure regex only matches from the start

        # Adding plugin filter
        plugins = getattr(input_request, "plugins", None)

        for path, path_regex, method, view in endpoints:
            if plugins:
                plugin = view.__module__.split(".")[0]
                if plugin not in plugins:  # plugin filter
                    continue

            view.request = spectacular_settings.GET_MOCK_REQUEST(method, path, view, input_request)

            if not (public or self.has_view_permissions(path, method, view)):
                continue

            schema = view.schema

            if input_request is None or "pk_path" not in query_params:
                path = self.convert_endpoint_path_params(path, view, schema)

            # beware that every access to schema yields a fresh object (descriptor pattern)
            operation = schema.get_operation(path, path_regex, path_prefix, method, self.registry)

            # operation was manually removed via @extend_schema
            if not operation:
                continue

            # Removes html tags from OpenAPI schema
            if input_request is None or "include_html" not in query_params:
                if "description" in operation:
                    operation["description"] = strip_tags(operation["description"])

            # operationId as actions [list, read, sync, modify, create, delete, ...]
            if input_request and "bindings" in query_params:
                tokenized_path = schema._tokenize_path()
                tokenized_path = "_".join(
                    [t.replace("-", "_").replace("/", "_").lower() for t in tokenized_path]
                )
                action = schema.get_operation_id_action()
                if f"{tokenized_path}_{action}" == operation["operationId"]:
                    operation["operationId"] = action

            # Adding query parameters
            if "parameters" in operation and schema.method.lower() == "get":
                fields_parameter = build_parameter_type(
                    name="fields",
                    schema={"type": "array", "items": {"type": "string"}},
                    location=OpenApiParameter.QUERY,
                    description="A list of fields to include in the response.",
                )
                operation["parameters"].append(fields_parameter)
                exclude_fields_parameter = build_parameter_type(
                    name="exclude_fields",
                    schema={"type": "array", "items": {"type": "string"}},
                    location=OpenApiParameter.QUERY,
                    description="A list of fields to exclude from the response.",
                )
                operation["parameters"].append(exclude_fields_parameter)

            # Normalise path for any provided mount url.
            if path.startswith("/"):
                path = path[1:]

            if not path.startswith("{"):
                path = urljoin(self.url or "/", path)

            result.setdefault(path, {})
            result[path][method.lower()] = operation

        return result

    def get_schema(self, request=None, public=False):
        """Generate a OpenAPI schema."""
        if request is None:
            request = Request(HttpRequest())
            request.META["SERVER_NAME"] = "localhost"
            request.META["SERVER_PORT"] = "24817"

        apps = list(pulp_plugin_configs())
        if request and "plugin" in request.query_params:
            raise ParseError("'plugin' has been removed. Use 'component' instead.")
        if request and "component" in request.query_params:
            # /pulp/api/v3/docs/api.json?component=core,file
            app_labels = request.query_params["component"].split(",")
            apps = [app for app in apps if app.label in app_labels]
            if len(apps) != len(app_labels):
                raise ParseError("Invalid component specified.")
            request.plugins = [app.name.split(".")[0] for app in apps]
        request.apps = apps

        request.bindings = "bindings" in request.query_params

        result = super().get_schema(request, public)

        if request.bindings:
            # Undo the spectacular sanitization of operation ids
            for path, path_spec in result["paths"].items():
                for operation, operation_spec in path_spec.items():
                    operation_spec["operationId"] = operation_spec.pop("x-copy-operationId")
        return result


class JSONHeaderRemoteAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "pulpcore.app.authentication.JSONHeaderRemoteAuthentication"
    name = "json_header_remote_authentication"

    def get_security_definition(self, auto_schema):
        return settings.AUTHENTICATION_JSON_HEADER_OPENAPI_SECURITY_SCHEME
