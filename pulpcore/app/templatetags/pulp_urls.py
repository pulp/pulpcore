import re

from django import template
from django.conf import settings
from django.utils.encoding import force_text
from django.utils.html import escape
from django.utils.safestring import SafeData, mark_safe

register = template.Library()


TRAILING_PUNCTUATION = [".", ",", ":", ".)", '"', "'", "&quot;", ";"]
WRAPPING_PUNCTUATION = [
    ("(", ")"),
    ("<", ">"),
    ("[", "]"),
    ("&lt;", "&gt;"),
    ('"', '"'),
    ("'", "'"),
    ("&quot;", "&quot;"),
]
word_split_re = re.compile(r"(\s+)")


@register.filter(needs_autoescape=True)
def urlize_quoted_hrefs(text, trim_url_limit=None, nofollow=True, autoescape=True):
    """
    Converts href in text into clickable links. If trim_url_limit is not None, the URLs in link
    text longer than this limit will truncated to trim_url_limit-3 characters and appended with
    an ellipsis. If nofollow is True, the URLs in link text will get a rel="nofollow" attribute.

    """

    def trim_url(x, limit=trim_url_limit):
        return limit is not None and (len(x) > limit and ("%s..." % x[: max(0, limit - 3)])) or x

    safe_input = isinstance(text, SafeData)
    words = word_split_re.split(force_text(text))
    for i, word in enumerate(words):
        if settings.V3_API_ROOT in word:
            # Deal with punctuation.
            lead, middle, trail = "", word, ""
            for punctuation in TRAILING_PUNCTUATION:
                if middle.endswith(punctuation):
                    middle = middle[: -len(punctuation)]
                    trail = punctuation + trail
            for opening, closing in WRAPPING_PUNCTUATION:
                if middle.startswith(opening):
                    middle = middle[len(opening) :]
                    lead = lead + opening
                # Keep parentheses at the end only if they're balanced.
                if middle.endswith(closing) and middle.count(closing) == middle.count(opening) + 1:
                    middle = middle[: -len(closing)]
                    trail = closing + trail

            # Make URL we want to point to.
            url = None
            nofollow_attr = ' rel="nofollow"' if nofollow else ""

            # Check if it's a real URL
            if url and ("{" in url or "%7B" in url):
                url = None

            # Make link.
            if url:
                trimmed = trim_url(middle)
                if autoescape and not safe_input:
                    lead, trail = escape(lead), escape(trail)
                    url, trimmed = escape(url), escape(trimmed)
                middle = '<a href="%s"%s>%s</a>' % (url, nofollow_attr, trimmed)
                words[i] = mark_safe("%s%s%s" % (lead, middle, trail))
            else:
                if safe_input:
                    words[i] = mark_safe(word)
                elif autoescape:
                    words[i] = escape(word)
        elif safe_input:
            words[i] = mark_safe(word)
        elif autoescape:
            words[i] = escape(word)
    return "".join(words)
