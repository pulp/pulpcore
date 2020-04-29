Style Guide
===========

Python Version
--------------
All Pulp 3+ code will use Python 3.6+. It is not necessary to maintain backwards compatibility
with Python 2.Y.

PEP-8
-----
All code should be compliant with PEP-8_ where reasonable.

It is recommended that contributors check for compliance by running flake8_. We include
``flake8.cfg`` files in our git repositories for convenience.

.. _PEP-8: https://www.python.org/dev/peps/pep-0008
.. _flake8: http://flake8.pycqa.org/en/latest/

Black
-----
All python code (except for the usually generated files in the migration folder) must be formatted according to the ruleset defined by black_.
As black_ is able to automatically reformat python code, contributors are supposed to run `black .` in the repositories root directory.
For various IDEs / editors, there is also an integration_ for black_.

.. _black: https://github.com/psf/black
.. _integration: https://github.com/psf/black#editor-integration

Modifications:
**************
line length: We limit to 100 characters, rather than 79.


.. _google-docstrings:

In-code Documentation
---------------------
Most classes and functions should have a docstring that follows the conventions described in
`Google's Python Style Guide <https://google.github.io/styleguide/pyguide.html?showone=Comments#Comments>`_.

Exceptions and Clarifications
*****************************
#. Modules should not include license information.
#. The type of each Args value should be included after the variable name in parentheses. The type of each Returns value should be the first item on the line.
#. Following the type of Args and Returns values, there will be a colon and a single space followed by the description. Additional spaces should not be used to align types and descriptions.
#. Fields and Relations sections will be used when documenting fields on Django models. The Fields section will be used for non-related fields on Model classes. The Relations section will be used for related fields on Model classes.

Auto-Documentation
******************
Docstrings will be used for auto-documentation and must be parsable by the
`Napoleon plugin for Sphinx <http://www.sphinx-doc.org/en/stable/ext/napoleon.html>`_.

Example Docstring
*****************

.. code-block:: python

    def example_function():
        """
        The first section is a summary, which should be restricted to a single line.

        More detailed information follows the summary after a blank line. This section can be as
        many lines as necessary.

        Args:
            arg1 (str): The argument is visible, and its type is clearly indicated.
            much_longer_argument (str): Types and descriptions are not aligned.

        Returns:
            bool: The return value and type is very clearly visible.

        """

Encoding
--------
Python 3 assumes that files are encoded with UTF-8, so it is not necessary to declare this in the
file.
