from django.template.defaultfilters import stringfilter, urlize as orig_urlize, register
from django.conf import settings
from django.utils.safestring import SafeData, mark_safe


@register.filter(needs_autoescape=True)
@stringfilter
def urlize(text, autoescape=True):
    """
    Converts hrefs and urls in the input in to clickable links.

    This filter overwrites the django default implementation to also handle pulp api hrefs.
    """
    safe_input = isinstance(text, SafeData)
    text = text.replace(settings.V3_API_ROOT, "http://SENTINEL.org" + settings.V3_API_ROOT)
    if safe_input:
        text = mark_safe(text)
    text = orig_urlize(text, autoescape=autoescape)
    safe_input = isinstance(text, SafeData)
    text = text.replace("http://SENTINEL.org" + settings.V3_API_ROOT, settings.V3_API_ROOT)
    if safe_input:
        text = mark_safe(text)
    return text
