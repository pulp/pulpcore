# -*- coding: utf-8 -*-
"""
    sphinx.ext.napoleon.docstring
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


    Classes for docstring parsing and formatting.


    :copyright: Copyright 2007-2016 by the Sphinx team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

from sphinx.domains.python import PyObject, PyTypedField
from sphinx.ext.napoleon.docstring import GoogleDocstring

# Extend the python sphinx domain with support for :field: and :relation: directives,
# as well as their related type directives. These then get used by DjangoGoogleDocstring.
# Using the 'data' role for the :field: and :relation: directives prevents sphinx from trying
# cross-reference them. This role is intended to be used at the module level, but renders
# correctly when used in Model definitions and prevents warnings from sphinx about duplicate
# cross-reference targets on something that shouldn't be cross-referenced.
PyObject.doc_field_types.extend([
    PyTypedField('field', label=('Fields'), rolename='data',
                 names=('field',), typerolename='obj', typenames=('fieldtype',),
                 can_collapse=True),
    PyTypedField('relation', label=('Relations'), rolename='data',
                 names=('relation',), typerolename='obj', typenames=('reltype',),
                 can_collapse=True),
])

# Similar to the extensions above, but this rewrites the 'variable' type used for class attrs to
# use the data rolename, which prevents sphinx from attempting to cross-reference class attrs.
for field in PyObject.doc_field_types:
    if field.name == 'variable':
        field.rolename = 'data'


class DjangoGoogleDocstring(GoogleDocstring):
    """Add support for Django-specific sections to napoleon's GoogleDocstring parser.

    Parameters
    ----------
    docstring : str or List[str]
        The docstring to parse, given either as a string or split into
        individual lines.
    config : Optional[sphinx.ext.napoleon.Config or sphinx.config.Config]
        The configuration settings to use. If not given, defaults to the
        config object on `app`; or if `app` is not given defaults to the
        a new `sphinx.ext.napoleon.Config` object.

        See Also
        --------
        :class:`sphinx.ext.napoleon.Config`

    Other Parameters
    ----------------
    app : Optional[sphinx.application.Sphinx]
        Application object representing the Sphinx process.
    what : Optional[str]
        A string specifying the type of the object to which the docstring
        belongs. Valid values: "module", "class", "exception", "function",
        "method", "attribute".
    name : Optional[str]
        The fully qualified name of the object.
    obj : module, class, exception, function, method, or attribute
        The object to which the docstring belongs.
    options : Optional[sphinx.ext.autodoc.Options]
        The options given to the directive: an object with attributes
        inherited_members, undoc_members, show_inheritance and noindex that
        are True if the flag option of same name was given to the auto
        directive.

    """
    def __init__(self, docstring, config=None, app=None, what='', name='',
                 obj=None, options=None):
        # super's __init__ calls _parse, so we need to wrap it to make sure the custom
        # django-ness is added to the class before _parse runs. Thus, self._initialized.
        # See _parse below for how this attr gets used to delay parsing.
        self._initialized = False
        super().__init__(docstring, config, app, what, name, obj, options)
        self._sections.update({
            'fields': self._parse_fields_section,
            'relations': self._parse_relations_section,
        })
        self._initialized = True
        self._parse()

    def _parse(self):
        if self._initialized:
            return super()._parse()

    def _parse_fields_section(self, section):
        return self._parse_django_section(section, 'field')

    def _parse_relations_section(self, section):
        return self._parse_django_section(section, 'relation')

    def _parse_django_section(self, section, directive):
        # a "django" directive is either field or relation. Use the correct type definition
        # based on the value of 'directive' to generate a correctly cross-referenced type link.
        # directive and typedirective need to match the name and typename of the custom
        # PyTypedFields added to the python sphinx domain above.
        if directive == 'field':
            typedirective = 'fieldtype'
        else:
            typedirective = 'reltype'

        lines = []
        for _name, _type, _desc in self._consume_fields():
            field = ':%s %s: ' % (directive, _name)
            lines.extend(self._format_block(field, _desc))
            if _type:
                lines.append(':%s %s: %s' % (typedirective, _name, _type))
            lines.append('')
        return lines
