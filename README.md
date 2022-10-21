[![Build and Test](https://github.com/bigladder/lattice/actions/workflows/build-and-test.yaml/badge.svg)](https://github.com/bigladder/lattice/actions/workflows/build-and-test.yaml)

[![Web Documentation](https://github.com/bigladder/lattice/actions/workflows/build-web.yaml/badge.svg)](https://github.com/bigladder/lattice/actions/workflows/build-web.yaml)

Lattice
===========

A toolkit that provides support for a schema-based building data model framework, currently under development as ASHRAE Standard 232P. Lattice performs data model validation, intermediate schema generation, and data file validation in 


Installing the Toolkit
--------------------

We are currently supporting python 3.6 - 3.9.

To install and use the Lattice project, you must have a supported version of Python. We also use the [poetry](https://python-poetry.org/) tool to manage Lattice's dependencies. Follow the [instructions](https://python-poetry.org/docs/#installation) to install poetry on your specific platform.

To initialize dependencies in your poetry virtual environment, simply type

`poetry install`

from the main Lattice directory. To test the schema-building process, type

`poetry run doit`.

### Products

_lattice_ is both a python module and a standalone tool. See Example Usage for details.


Example Usage
-------------

TODO