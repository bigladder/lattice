[![Build and Test](https://github.com/bigladder/lattice/actions/workflows/build-and-test.yaml/badge.svg)](https://github.com/bigladder/lattice/actions/workflows/build-and-test.yaml)

[![Web Documentation](https://github.com/bigladder/lattice/actions/workflows/build-web.yaml/badge.svg)](https://github.com/bigladder/lattice/actions/workflows/build-web.yaml)

Lattice
===========

A Python package that provides support for a schema-based building data model framework, currently under development as ASHRAE Standard 232P. Lattice performs data model validation, intermediate schema generation, and data file validation for YAML data models compliant with ASHRAE 232P and ASHRAE 205.


Installing the Toolkit
--------------------

To install and use the Lattice project, you must have a supported version of Python. 

To install, simply use 

`pip install .`

from the main Lattice directory. To test the schema-building process, you may add 

`poetry run pip install doit` and
`poetry run doit`.

Example Usage
-------------

_lattice_ is Python package defining the Lattice class. To use the schema-building functions, instantiate a Lattice object with the path to a root directory, which should contain optional predetermined subdirectories for model data. These subdirectories are
**schema** (required): contains YAML source schema describing the data model;
**docs** (optional): contains markdown templates that are used to render model documentation;
**examples** (optional): data corresponding to data model.

The repository's *examples* directory contains sample data models exemplifying different model options, such as Data Group Templates or scoped references. Resources with further examples include:

* https://github.com/IBPSA-USA/climate-information.git
* https://github.com/open205/schema-205.git

