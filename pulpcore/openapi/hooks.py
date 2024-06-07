from django.conf import settings


def add_info_hook(result, generator, request, **kwargs):
    # Basically I'm doing it to get pulp logo at redoc page
    result["info"]["x-logo"] = {
        "url": "https://pulp.plan.io/attachments/download/517478/pulp_logo_word_rectangle.svg"
    }

    # Adding plugin version config
    result["info"]["x-pulp-app-versions"] = {app.label: app.version for app in request.apps}

    # Add domain-settings value
    result["info"]["x-pulp-domain-enabled"] = settings.DOMAIN_ENABLED

    # Add x-isDomain flag to domain path parameters
    # Save a copy of the bad operationId in case we generate bindings
    for path, path_spec in result["paths"].items():
        for operation, operation_spec in path_spec.items():
            if request.bindings:
                # Keep the operation id before sanitization
                operation_spec["x-copy-operationId"] = operation_spec["operationId"]
            if settings.DOMAIN_ENABLED:
                parameters = operation_spec.get("parameters")
                if parameters:
                    for parameter in parameters:
                        if parameter["name"] == "pulp_domain" and parameter["in"] == "path":
                            parameter["x-isDomain"] = True

    # Adding current host as server (it will provide a default value for the bindings)
    result["servers"] = [{"url": request.build_absolute_uri("/")}]

    return result
