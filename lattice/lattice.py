"""Classes that encapsulate the basic data model architecture for lattice"""

import re
import warnings
import os
import subprocess
from fnmatch import fnmatch
from pathlib import Path
from typing import List
from jsonschema.exceptions import RefResolutionError

import lattice.cpp.support_files as support
from lattice.docs.process_template import process_template
from .file_io import check_dir, make_dir, load, dump, get_file_basename, get_base_stem
from .meta_schema import generate_meta_schema, meta_validate_file
from .schema_to_json import generate_json_schema, validate_file, postvalidate_file
from .docs import MkDocsWeb, DocumentFile
from .header_entries import HeaderTranslator
from .cpp_entries import CPPTranslator


class SchemaFile:  # pylint:disable=R0902
    """Parse the components of a schema file."""

    def __init__(self, path) -> None:
        """Open and parse source schema"""

        self.path = Path(path).absolute()
        self.file_base_name = get_base_stem(self.path)
        self.schema_type = self.file_base_name  # Overwritten if it is actually specified

        self._content: dict = load(self.path)
        self._meta_schema_path: Path = None
        self._json_schema_path: Path = None
        self._root_data_group: str = None

        # Check for required content
        if "Schema" not in self._content:
            raise Exception(f'Required "Schema" object not found in schema file, "{self.path}".')

        self.schema_author = None
        if "Root Data Group" in self._content["Schema"]:
            self._root_data_group = self._content["Schema"]["Root Data Group"]
            self.schema_type = self._root_data_group
            if self._root_data_group in self._content:
                # Get metadata
                if "Data Elements" not in self._content[self._root_data_group]:
                    raise Exception(f'Root Data Group, "{self._root_data_group}" ' 'does not contain "Data Elements".')
                if "metadata" in self._content[self._root_data_group]["Data Elements"]:
                    self._get_schema_constraints()
                else:
                    pass  # Warning?
            else:
                raise Exception(
                    f'Root Data Group, "{self._root_data_group}", ' f'not found in schema file, "{self.path}"'
                )

            # TODO: Version? # pylint: disable=fixme

    def _get_schema_constraints(self):
        """Populate instance variables from schema constraints"""

        constraints = self._content[self._root_data_group]["Data Elements"]["metadata"].get("Constraints")
        data_element_pattern = "([a-z]+)(_([a-z]|[0-9])+)*"
        enumerator_pattern = "([A-Z]([A-Z]|[0-9])*)(_([A-Z]|[0-9])+)*"
        constraint_pattern = re.compile(
            f"^(?P<data_element>{data_element_pattern})=(?P<enumerator>{enumerator_pattern})$"
        )
        if not isinstance(constraints, list):
            constraints = [constraints]
        for constraint in [c for c in constraints if c]:
            match = constraint_pattern.match(constraint)
            if match:
                if match.group(1) == "schema_author":
                    self.schema_author = match.group(5)
                else:
                    pass  # Warning?

                if match.group(1) == "schema":
                    self.schema_type = match.group(5)
                else:
                    pass  # Warning?

                if match.group("data_element") == "schema":
                    self.schema_type = match.group("enumerator")
                else:
                    pass  # Warning?

    @property
    def meta_schema_path(self) -> Path:
        """Path to this SchemaFile's validating metaschema"""
        return self._meta_schema_path

    @meta_schema_path.setter
    def meta_schema_path(self, meta_schema_path):
        self._meta_schema_path = Path(meta_schema_path).absolute()

    @property
    def json_schema_path(self) -> Path:
        """Path to this SchemaFile as translated JSON"""
        return self._json_schema_path

    @json_schema_path.setter
    def json_schema_path(self, json_schema_path):
        self._json_schema_path = Path(json_schema_path).absolute()

    @property
    def cpp_header_file_path(self):  # pylint:disable=C0116
        return self._cpp_header_path

    @cpp_header_file_path.setter
    def cpp_header_file_path(self, value):
        self._cpp_header_path = Path(value).absolute()

    @property
    def cpp_source_file_path(self):  # pylint:disable=C0116
        return self._cpp_source_path

    @cpp_source_file_path.setter
    def cpp_source_file_path(self, value):
        self._cpp_source_path = Path(value).absolute()


class Lattice:  # pylint:disable=R0902
    """
    Main class that provides schema transformations for the schema-based data model framework.
    """

    def __init__(
        self,
        root_directory=Path.cwd(),
        build_directory: Path = None,
        build_output_directory_name=".lattice",
        build_validation=True,
    ):
        """Set up file structure"""

        # Check if directories exists
        check_dir(root_directory, "Root directory")
        if build_directory is None:
            build_directory = root_directory
        else:
            check_dir(build_directory, "Build directory")

        self.root_directory: Path = Path(root_directory)

        if build_output_directory_name is None:
            self.build_directory: Path = Path(build_directory)
        else:
            self.build_directory: Path = Path(build_directory) / build_output_directory_name
        make_dir(self.build_directory)

        self.collect_schemas()

        self.setup_meta_schemas()

        self.setup_json_schemas()

        self.collect_example_files()

        self.collect_doc_templates()

        self.web_docs_directory_path: Path = self.doc_output_dir / "web"

        if build_validation:
            self.generate_meta_schemas()
            self.validate_schemas()
            self.generate_json_schemas()
            self.validate_example_files()

        self.collect_cpp_schemas()

        self.setup_cpp_source_files()

    def collect_schemas(self):
        """Collect source schemas into list of SchemaFiles"""

        # Make sure root directory has minimum content (i.e., schema directory,
        # or at least one schema file)
        schema_directory_path = self.root_directory / "schema"
        if schema_directory_path.exists():
            self.schema_directory_path = schema_directory_path
        else:
            self.schema_directory_path = self.root_directory

        # Collect list of schema files
        self.schemas: List[SchemaFile] = []
        for file_name in sorted(list(self.schema_directory_path.iterdir())):
            if fnmatch(file_name, "*.schema.yaml") or fnmatch(file_name, "*.schema.yml"):
                self.schemas.append(SchemaFile(file_name))

        if len(self.schemas) == 0:
            raise Exception(f'No schemas found in "{self.schema_directory_path}".')

    def setup_meta_schemas(self):
        """Set up meta_schema subdirectory"""

        self.meta_schema_directory = Path(self.build_directory) / "meta_schema"
        make_dir(self.meta_schema_directory)
        for schema in self.schemas:
            meta_schema_path = self.meta_schema_directory / f"{schema.file_base_name}.meta.schema.json"
            schema.meta_schema_path = meta_schema_path

    def generate_meta_schemas(self):
        """Generate metaschemas"""

        for schema in self.schemas:
            generate_meta_schema(Path(schema.meta_schema_path), Path(schema.path))

    def validate_schemas(self):
        """Validate source schema using metaschema file"""

        for schema in self.schemas:
            meta_validate_file(Path(schema.path), Path(schema.meta_schema_path))

    def setup_json_schemas(self):
        """Set up json_schema subdirectory"""
        self.json_schema_directory = Path(self.build_directory) / "json_schema"
        make_dir(self.json_schema_directory)
        for schema in self.schemas:
            json_schema_path = self.json_schema_directory / f"{schema.file_base_name}.schema.json"
            schema.json_schema_path = json_schema_path

    def generate_json_schemas(self):
        """Generate JSON schemas"""

        for schema in self.schemas:
            generate_json_schema(schema.path, schema.json_schema_path)

    def validate_file(self, input_path, schema_type=None):
        """
        Validate an input instance against JSON schema.
        :param input_path:  Path to data model instance
        :param schema_type: Corresponds to source schema's SchemaType enumeration
        """

        instance = load(input_path)
        if schema_type is None:
            if "metadata" in instance:
                if "schema" in instance["metadata"]:
                    schema_type = instance["metadata"]["schema"]

        if schema_type is None:
            if len(self.schemas) > 1:
                raise Exception(
                    f"Multiple schemas defined, and no schema type provided. "
                    f'Unable to validate file, "{input_path}".'
                )
            validate_file(input_path, self.schemas[0].json_schema_path)
            postvalidate_file(input_path, self.schemas[0].json_schema_path)
        else:
            # Find corresponding schema
            for schema in self.schemas:
                if schema.schema_type == schema_type:
                    try:
                        validate_file(input_path, schema.json_schema_path)
                        postvalidate_file(input_path, schema.json_schema_path)
                    except RefResolutionError as e:
                        raise Exception(f"Reference in schema {schema.json_schema_path} cannot be resolved: {e}") from e
                    return
            raise Exception(f'Unable to find matching schema, "{schema_type}", for file, "{input_path}".')

    def collect_example_files(self) -> None:
        """Collect data model instances from examples subdirectory"""

        example_directory_path = self.root_directory / "examples"
        if example_directory_path.exists():
            self.example_directory_path = example_directory_path
        else:
            self.example_directory_path = None

        # Collect list of example files
        self.examples = []
        if self.example_directory_path is not None:
            for file_name in sorted(list(self.example_directory_path.iterdir())):
                if file_name.is_file():
                    self.examples.append(file_name.absolute())

    def validate_example_files(self):
        """Validate example instance(s) against JSON schema"""

        for example in self.examples:
            self.validate_file(example)

    def collect_doc_templates(self):
        """Collect documentation templates from docs subdirectory"""

        doc_templates_directory_path = self.root_directory / "docs"
        if doc_templates_directory_path.exists():
            self.doc_templates_directory_path = doc_templates_directory_path
        else:
            self.doc_templates_directory_path = None

        # Collect list of doc template files
        self.doc_templates = []
        if self.doc_templates_directory_path is not None:
            for file_name in list(self.doc_templates_directory_path.iterdir()):
                # file_path = self.doc_templates_directory_path / file_name
                if file_name.is_file() and ".md" in file_name.name:
                    self.doc_templates.append(DocumentFile(file_name))
        self.doc_output_dir = self.build_directory / "docs"
        if len(self.doc_templates) > 0:
            make_dir(self.doc_output_dir)
            for template in self.doc_templates:
                markdown_path = self.doc_output_dir / f"{get_file_basename(template.path, depth=1)}"
                template.markdown_output_path = markdown_path

    def generate_markdown_documents(self):
        """Generate markdown from doc templates"""

        for template in self.doc_templates:
            process_template(template.path, template.markdown_output_path, self.schema_directory_path)

    def generate_web_documentation(self):
        """Generate web docs from doc templates"""

        make_dir(self.doc_output_dir)
        make_dir(self.web_docs_directory_path)

        if self.doc_templates_directory_path:
            MkDocsWeb(self).build()
        else:
            warnings.warn('Template directory "doc" does not exist under {self.root_directory}')

    def collect_cpp_schemas(self):
        """Collect source schemas into list of SchemaFiles"""
        self.cpp_schemas = self.schemas + [SchemaFile(Path(__file__).with_name("core.schema.yaml"))]

    def setup_cpp_source_files(self):
        """Create directories for generated CPP source"""
        self.cpp_output_dir = Path(self.build_directory) / "cpp"
        make_dir(self.cpp_output_dir)
        include_dir = make_dir(self.cpp_output_dir / "include")
        self._cpp_output_include_dir = make_dir(include_dir / f"{self.root_directory.name}")
        self._cpp_output_src_dir = make_dir(self.cpp_output_dir / "src")
        for schema in self.cpp_schemas:
            schema.cpp_header_file_path = self._cpp_output_include_dir / f"{schema.file_base_name.lower()}.h"
            schema.cpp_source_file_path = self._cpp_output_src_dir / f"{schema.file_base_name.lower()}.cpp"

    def setup_cpp_repository(self, submodules: list[str]):
        """Initialize the CPP output directory as a Git repo."""
        cwd = os.getcwd()
        os.chdir(self.cpp_output_dir)
        subprocess.run(["git", "init"], check=True)
        vendor_dir = make_dir("vendor")
        os.chdir(vendor_dir)
        # subprocess.run(["git", "remote", "add", "-f -t", "main", "--no-tags", "origin_atheneum", "https://github.com/bigladder/atheneum.git"])
        try:
            for submodule in submodules:
                subprocess.run(["git", "submodule", "add", submodule], check=False)
        finally:
            os.chdir(cwd)
        os.chdir(cwd)

    @property
    def cpp_support_headers(self) -> list[Path]:
        """Wrap list of template-generated headers."""
        return support.support_header_pathnames(self.cpp_output_dir)

    def generate_cpp_project(self, submodules: list[str]):
        """Generate CPP header files, source files, and build support files."""
        h = HeaderTranslator()
        c = CPPTranslator()
        for schema in self.cpp_schemas:
            h.translate(schema.path, self.schema_directory_path, self._cpp_output_include_dir, self.root_directory.name)
            dump(str(h), schema.cpp_header_file_path)
            c.translate(self.root_directory.name, h)
            dump(str(c), schema.cpp_source_file_path)
        self.setup_cpp_repository(submodules)
        support.render_support_headers(self.root_directory.name, self._cpp_output_include_dir)
        support.render_build_files(self.root_directory.name, submodules, self.cpp_output_dir)
