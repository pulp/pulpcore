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

    # Adding current host as server (it will provide a default value for the bindings)
    result["servers"] = [{"url": request.build_absolute_uri("/")}]

    return result
