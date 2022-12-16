[![Release](https://img.shields.io/pypi/v/lattice.svg)](https://pypi.python.org/pypi/lattice)

[![Build and Test](https://github.com/bigladder/lattice/actions/workflows/build-and-test.yaml/badge.svg)](https://github.com/bigladder/lattice/actions/workflows/build-and-test.yaml)

[![Web Documentation](https://github.com/bigladder/lattice/actions/workflows/release.yaml/badge.svg)](https://github.com/bigladder/lattice/actions/workflows/release.yaml)

Lattice
===========

A Python package that provides support for a schema-based building data model framework, currently under development as ASHRAE Standard 232P, where schema are described in compliant YAML source files. Lattice performs:

- Data model validation: Ensures the YAML schema source files are well-formed.
- Schema generation: Translates the YAML schema source files into equivalent JSON Schema.
- Data file validation: Validates data files against the generated JSON Schema and additional validation requirements not supported by JSON Schema (e.g., reference checking).
- Data model documentation: Generates web documentation of the data model from the YAML schema source files and templated markdown files (requires [Go](https://go.dev/), [Hugo](https://gohugo.io/installation/), and [Node.js](https://nodejs.org/en/download/)). This web documentation can be automatically deployed to GitHub pages.

Future additions under development include:

- Generation of PDF documentation of the data model.
- Generation of C/C++ source code for processing compliant data files.


Installing
----------

To install Lattice, simply:

`pip install lattice`

To generate data model documentation, you'll also need to install:

- [Go](https://go.dev/)
- [Hugo](https://gohugo.io/installation/)
- [Node.js](https://nodejs.org/en/download/)

Example Usage
-------------

_lattice_ is Python package defining the `Lattice` class. Lattice relies on a predetermined structure of subdirectories:

- **schema** (optional): Contains YAML source schema files describing the data model. Alternatively, if YAML source schema files are not provided in a "schema" directory, they must be in the root directory.
- **docs** (optional): Contains markdown templates that are used to render model documentation. An optional subdirectory of "docs" called "web" contains additional content required for generating the web documentation including configuration settings, graphics, and supplementary content.
- **examples** (optional): Example data files compliant with the data model.

The `Lattice` class is instantiated with the following parameters:

- `root_directory`: This is the directory containing the source subdirectories.The default is the current working directory.

- `build_directory`: This is the path to the directory where the content related to lattice is stored. The content itself will be located in a subdirectory determined by `build_output_directory_name` (below). It includes intermediate meta-schema(s), JSON Schema(s), generated markdown files, and the generated web documentation. The default is `root_directory`.

- `build_output_directory_name`: The name of the lattice output content directory. The default is `".lattice/"`.

- `build_validation`: A boolean indicator to automatically generate meta-schema, validate the data model, generate the schemas and validate the example data files upon instantiation. If false, these tasks must be executed after instantiation using the `generate_meta_schemas`, `validate_schemas`, `generate_json_schemas`, and `validate_example_files` methods. The default is `True`.

The repository's *examples* directory contains sample data models exemplifying different model options, such as Data Group Templates or scoped references.

More complete examples of projects using the ASHRAE Standard 232P framework include:

- [IBPSA-USA Climate Information](https://github.com/IBPSA-USA/climate-information) (uses lattice)
- [ASHRAE Standard 205](https://github.com/open205/schema-205) (transitioning to lattice)
- [ASHRAE Standard 229](https://github.com/open229/ruleset-model-description-schema) (does not use lattice...yet)

