Documentation
=============

Principles
----------

Pulp's documentation is designed with the following principles:

#. Avoid documenting external projects, providing links wherever reasonable.
#. Documentation layout should be designed for users to intuitively find information.
#. The structure should present introductory material before advanced topics.
#. Documentation should cross reference to limit repitition.
#. Pulp terminology should be be explicitly defined and added to the glossary.
#. Documentation should stay consistent with the language used in the :doc:`/concepts`.
#. Where reasonable, documents should include:

   #. Summary of content.
   #. Intended audience.
   #. Links to prerequisite material.
   #. Links to related material.

Building the Docs:
------------------

If you are using a developer Vagrant box, the docs requirements should already be installed.

Otherwise, (in your virtualenv), you should install the docs requirements.::

    (pulp) $ pip install -r doc_requirements.txt

To build the docs, from the docs directory, use ``make``::

    (pulp) $ cd docs
    (pulp) $ make html

Use your browser to load the generated html, which lives in ``docs/_build/html/``

You do not need to clean the docs before rebuilding, however you can do it by running::

    (pulp) $ cd docs
    (pulp) $ make clean
