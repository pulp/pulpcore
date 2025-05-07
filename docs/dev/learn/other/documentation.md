# Documentation

## Principles

Pulp's documentation is designed with the following principles:

1. Avoid documenting external projects, providing links wherever reasonable.

1. Documentation layout should be designed for users to intuitively find information.

1. The structure should present introductory material before advanced topics.

1. Documentation should cross reference to limit repitition.

1. Pulp terminology should be be explicitly defined and added to the glossary.

1. Documentation should stay consistent with the language used in the `concepts`.

1. Where reasonable, documents should include:

    1. Summary of content.
    1. Intended audience.
    1. Links to prerequisite material.
    1. Links to related material.

## Building the Docs:

If you are using a developer Vagrant box, the docs requirements should already be installed.

Otherwise, (in your virtualenv), you should install the docs requirements.:

```
(pulp) $ pip install -r doc_requirements.txt
```

To build the docs, from the docs directory, use `make`:

```
(pulp) $ cd docs
(pulp) $ make html
```

Use your browser to load the generated html, which lives in `docs/_build/html/`

You do not need to clean the docs before rebuilding, however you can do it by running:

```
(pulp) $ cd docs
(pulp) $ make clean
```
