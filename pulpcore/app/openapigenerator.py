from collections import OrderedDict
import re

from drf_yasg.generators import OpenAPISchemaGenerator
from drf_yasg import openapi
import uritemplate


class Paths(openapi.SwaggerDict):
    def __init__(self, paths, **extra):
        """A listing of all the paths in the API.

        :param dict[str,.PathItem] paths:
        """
        super(Paths, self).__init__(**extra)
        for path, path_obj in paths.items():
            if path_obj is not None:  # pragma: no cover
                self[path] = path_obj
        self._insert_extras__()


class PulpOpenAPISchemaGenerator(OpenAPISchemaGenerator):

    def get_paths(self, endpoints, components, request, public):
        """Generate the Swagger Paths for the API from the given endpoints.

        Args:
            endpoints (dict): endpoints as returned by get_endpoints
            components (ReferenceResolver): resolver/container for Swagger References
            request (Request): the request made against the schema view; can be None
            public (bool): if True, all endpoints are included regardless of access through
                           `request`

        Returns:
            tuple[openapi.Paths,str]: The :class:`openapi.Paths` object and the longest common path
                                      prefix, as a 2-tuple
        """
        if not endpoints:
            return openapi.Paths(paths={}), ''

        prefix = ''
        resources = {}
        resource_example = {}
        paths = OrderedDict()
        for path, (view_cls, methods) in sorted(endpoints.items()):
            operations = {}
            for method, view in methods:
                if not public and not self._gen.has_view_permissions(path, method, view):
                    continue

                operation = self.get_operation(view, path, prefix, method, components, request)
                if operation is not None:
                    operation.operation_id = operation.operation_id.replace('pulp_api_v3_', '')
                    operations[method.lower()] = operation

            if operations:
                path_param = None

                if '}' in path:
                    resource_path = '%s}/' % path.rsplit(sep='}', maxsplit=1)[0]
                    resource_other_path = self.get_resource_from_path(path)
                    if resource_other_path in endpoints:
                        resource_model = endpoints[resource_other_path][0].queryset.model
                        resource_name = self.get_parameter_name(resource_model)
                        param_name = self.get_parameter_slug_from_model(resource_model)
                        if resource_path in resources:
                            path = path.replace(resource_path, '{%s}' % resources[resource_path])
                        elif resource_other_path in resources:
                            path = path.replace(resource_path, '{%s}' % resources[
                                resource_other_path])
                        else:
                            resources[resource_path] = param_name
                            resource_example[resource_path] = self.get_example_uri(path)
                            path = path.replace(resource_path, '{%s}' % resources[resource_path])
                        example = resource_example[resource_other_path]
                        resource_description = self.get_resource_description(resource_name, example)
                        path_param = openapi.Parameter(
                            name=param_name,
                            description=resource_description,
                            required=True,
                            in_=openapi.IN_PATH,
                            type=openapi.TYPE_STRING,
                        )
                        paths[path] = openapi.PathItem(parameters=[path_param], **operations)
                    else:
                        if not path.startswith('/'):
                            path = '/' + path
                        paths[path] = self.get_path_item(path, view_cls, operations)
                else:
                    paths[path] = openapi.PathItem(parameters=[path_param], **operations)

        return Paths(paths=paths), prefix

    @staticmethod
    def get_resource_from_path(path):
        """
        Returns a path for a resource nested in the specified path

        Args:
            path (str): Full path to be searched for a nested resource

        Returns:
            str: path of nested resource
        """
        resource_path = '%s}/' % path.rsplit(sep='}', maxsplit=1)[0]
        if resource_path.endswith('_pk}/'):
            resource_path = '%s{_id}/' % resource_path.rsplit(sep='{', maxsplit=1)[0]
        return resource_path

    @staticmethod
    def get_resource_description(name, example_uri):
        """Returns a description of an *_href path parameter

        Args:
            name (str): Name of the resource referenced by the *_href path parameter
            example_uri (str): An example of the URI that is a reference for a specific resource

        Returns:
            str: Description of an *_href path parameter
        """
        return "URI of %s. e.g.: %s" % (name, example_uri)

    @staticmethod
    def get_example_uri(path):
        """Returns an example URI for a path template

        Args:
            path (openapi.Path): path object for a specific resource


        Returns:
            str: The path with concrete path parameters.
        """
        params = {}
        for variable in uritemplate.variables(path):
            params[variable] = '1'
        return uritemplate.expand(path, **params)

    @staticmethod
    def get_parameter_slug_from_model(model):
        """Returns a path parameter name for the resource associated with the model.

        Args:
            model (django.db.models.Model): The model for which a path parameter name is needed

        Returns:
            str: *_href where * is the model name in all lower case letters
        """
        return '%s_href' % '_'.join([part.lower() for part in re.findall('[A-Z][^A-Z]*',
                                                                         model.__name__)])

    @staticmethod
    def get_parameter_name(model):
        """Returns the human readable name of the resource associated with the model

        Args:
            model (django.db.models.Model): The model for which a name is needed

        Returns:
            str: name of the resource associated with the model
        """
        return ' '.join(re.findall('[A-Z][^A-Z]*', model.__name__))
