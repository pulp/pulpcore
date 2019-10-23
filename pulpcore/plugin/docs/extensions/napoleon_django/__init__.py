# -*- coding: utf-8 -*-
"""
    napoleon-django
    ~~~~~~~~~~~~~~~

    An extension to sphinx.ext.napoleon's Google-style Docstring
    with support for custom django blocks "Fields" and "Relations".

    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import sphinx
from napoleon_django.docstring import DjangoGoogleDocstring


class Config(object):
    pass


def setup(app):
    """Sphinx extension setup function.

    When the extension is loaded, Sphinx imports this module and executes
    the ``setup()`` function, which in turn notifies Sphinx of everything
    the extension offers.

    Parameters
    ----------
    app : sphinx.application.Sphinx
        Application object representing the Sphinx process

    See Also
    --------
    `The Sphinx documentation on Extensions
    <http://sphinx-doc.org/extensions.html>`_

    `The Extension Tutorial <http://sphinx-doc.org/extdev/tutorial.html>`_

    `The Extension API <http://sphinx-doc.org/extdev/appapi.html>`_

    """
    from sphinx.application import Sphinx
    if not isinstance(app, Sphinx):
        return  # probably called by tests

    app.connect('autodoc-process-docstring', _process_docstring)

    return {'version': sphinx.__display_version__, 'parallel_read_safe': True}


def _process_docstring(app, what, name, obj, options, lines):
    """Process the docstring for a given python object.

    Called when autodoc has read and processed a docstring. `lines` is a list
    of docstring lines that `_process_docstring` modifies in place to change
    what Sphinx outputs.

    Parameters
    ----------
    app : sphinx.application.Sphinx
        Application object representing the Sphinx process.
    what : str
        A string specifying the type of the object to which the docstring
        belongs. Valid values: "module", "class", "exception", "function",
        "method", "attribute".
    name : str
        The fully qualified name of the object.
    obj : module, class, exception, function, method, or attribute
        The object to which the docstring belongs.
    options : sphinx.ext.autodoc.Options
        The options given to the directive: an object with attributes
        inherited_members, undoc_members, show_inheritance and noindex that
        are True if the flag option of same name was given to the auto
        directive.
    lines : list of str
        The lines of the docstring, see above.

        .. note:: `lines` is modified *in place*

    """
    result_lines = lines
    docstring = DjangoGoogleDocstring(result_lines, app.config, app, what, name, obj, options)
    result_lines = docstring.lines()
    lines[:] = result_lines[:]
