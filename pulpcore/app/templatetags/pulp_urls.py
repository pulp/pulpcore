from django.template.defaultfilters import register, stringfilter
from django.template.defaultfilters import urlize as orig_urlize
from django.utils.safestring import SafeData, mark_safe

from pulpcore.app.find_url import find_api_root


@register.filter(needs_autoescape=True)
@stringfilter
def urlize(text, autoescape=True):
    """
    Converts hrefs and urls in the input in to clickable links.

    This filter overwrites the django default implementation to also handle pulp api hrefs.
    """
    #    urlize() will turn strings into links of they're of the form protocol://site/path.
    #    We force it to recognize Pulp-api-links by replacing strings in the incoming text of
    #    the form "API_ROOT/api/v3/whatever", forcing them to look like
    #    "http://SENTINEL.org/(string)", urlize()ing the result, then undoing the replace to
    #    lose the http://SENTINEL.org's.
    _, current_path = find_api_root(set_domain=False, rewrite_header=False)
    safe_input = isinstance(text, SafeData)
    text = text.replace(current_path, "http://SENTINEL.org" + current_path)
    if safe_input:
        text = mark_safe(text)
    text = orig_urlize(text, autoescape=autoescape)
    safe_input = isinstance(text, SafeData)
    text = text.replace("http://SENTINEL.org" + current_path, current_path)
    if safe_input:
        text = mark_safe(text)
    return text
