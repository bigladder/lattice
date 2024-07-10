[![Release](https://img.shields.io/pypi/v/lattice.svg)](https://pypi.python.org/pypi/lattice)

[![Build and Test](https://github.com/bigladder/lattice/actions/workflows/build-and-test.yaml/badge.svg)](https://github.com/bigladder/lattice/actions/workflows/build-and-test.yaml)

[![Web Documentation](https://github.com/bigladder/lattice/actions/workflows/release.yaml/badge.svg)](https://github.com/bigladder/lattice/actions/workflows/release.yaml)

Lattice
===========

A Python package that provides support for a schema-based building data model framework, currently under development as ASHRAE Standard 232P, where schema are described in compliant YAML source files. Lattice performs:

- Data model validation: Ensures the YAML schema source files are well-formed.
- Schema generation: Translates the YAML schema source files into equivalent JSON Schema.
- Data file validation: Validates data files against the generated JSON Schema and additional validation requirements not supported by JSON Schema (e.g., reference checking).
- Data model documentation: Generates web documentation of the data model from the YAML schema source files and templated markdown files. This web documentation can be automatically deployed to GitHub pages.

Future additions under development include:

- Generation of PDF documentation of the data model.
- Generation of C/C++ source code for processing compliant data files.


Installing
----------

To install Lattice, simply:

`pip install lattice`

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

### C++ Library Code Generation

#### Translations

Schema can be converted into C++ classes with the following mappings:

| Object Type           | C++ type   |
|-------------------    | --------   |
| Data Group            | `struct`     |
| Data Element          | public data member |
| Enumerator            | `enum`       |
| Data Group Template   | base class*|
|

 *with optional methods, including initialize()

| Data Type             | C++ type  |
|-------------------    | --------  |
| Integer               | `int`       |
| Numeric               | `float`     |
| String                | `std::string` |
| {}                    | `struct`    |
| <>                    | `enum`      |
| []                    | `std::vector` |
| list "(A,B)"          | `std::unique_ptr<BaseOfAB>`|
|

#### Inheritance

The code generator will assume that *Data Group* schema elements with a *Data Group Template* parameter use that template as the element's superclass. However, the code for the superclass itself is _not_ generated; it must be provided by the **lattice** user. An `#include` statement for the expected superclass file is listed at the top of the schema's implemenation (cpp) file (note: see Big Ladder file naming conventions). If the superclass file is not found, building the project (see below) will produce a compiler error to that effect. Virtual functions in the superclass will appear as overridden function stubs in the subclassed *Data Group*'s struct.

In the event that the source schema contains a *Data Element* with a "selector constraint" (i.e. a list of possible *Data Type*s combined with an associated list of possible enumerator values for the selector *Data Element*), the C++ generated code will assume that the *Data Type*s in the list all derive from a common base class, named by the *Data Group Template* of the first *Data Type* in the list. An `#include` statement for the base class will be generated, as above. The code that populates the *Data Group* (the struct's `from_json` function) will use a conditional statement to create a new object of the correct subclass and assign it to a member `unique_ptr`. The base class declaration requires an initialize() function, which must be provided by the superclass implementation with the following signature:

> virtual void initialize(const nlohmann::json& j);

or

> virtual void initialize(const nlohmann::json& j) = 0; // must be subclassed

and contents exactly mirroring `from_json` functions. (In future work this base class with its `initialize` method will be auto-generated.)

Note: If the first *Data Type* in a selector constraint list does not have a *Data Group Template* tag in its schema, the `unique_ptr`'s base class will default to "MissingType."

#### Build information

In addition to `.h` and `.cpp` files containing translated schema data, the code generator adds Git repository and CMake build support to the schema code, creating most of the structure necessary to test-build the schema code as a library. Necessary submodules are also downloaded: [fmt](https://github.com/fmtlib/fmt.git), [json](https://github.com/nlohmann/json), and [courier](https://github.com/bigladder/courier.git). To build a generated project, navigate to your **lattice** project's build directory, cpp subdirectory (e.g. /.lattice/cpp), and use a standard cmake build sequence:

> cmake -B build
>
> cmake --build build --config release




