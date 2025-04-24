"""Classes that encapsulate the basic data model architecture for lattice"""

import os
import subprocess
import warnings
from fnmatch import fnmatch
from pathlib import Path
from typing import List, Union

from jsonschema.exceptions import RefResolutionError

import lattice.cpp.support_files as support

from .cpp.cpp_entries import CPPTranslator
from .cpp.header_translator import HeaderTranslator
from .docs import DocumentFile, MkDocsWeb
from .docs.process_template import process_template
from .file_io import check_dir, get_file_basename, load, make_dir, string_to_file
from .meta_schema import generate_meta_schema, meta_validate_file
from .schema import Schema
from .schema_to_json import generate_json_schema, postvalidate_file, validate_file


class Lattice:  # pylint:disable=R0902
    """
    Main class that provides schema transformations for the schema-based data model framework.
    """

    def __init__(
        self,
        root_directory: Path = Path.cwd(),
        build_directory: Union[Path, None] = None,
        build_output_directory_name: Union[Path, None] = Path(".lattice"),
        build_validation: bool = True,
    ) -> None:
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
        self.schemas: List[Schema] = []
        for file_name in sorted(list(self.schema_directory_path.iterdir())):
            if fnmatch(file_name, "*.schema.yaml") or fnmatch(file_name, "*.schema.yml"):
                self.schemas.append(Schema(file_name))

        if len(self.schemas) == 0:
            raise Exception(f'No schemas found in "{self.schema_directory_path}".')

    def setup_meta_schemas(self):
        """Set up meta_schema subdirectory"""

        self.meta_schema_directory = Path(self.build_directory) / "meta_schema"
        make_dir(self.meta_schema_directory)
        for schema in self.schemas:
            meta_schema_path = self.meta_schema_directory / f"{schema.name}.meta.schema.json"
            schema.meta_schema_path = meta_schema_path

    def generate_meta_schemas(self):
        """Generate metaschemas"""

        for schema in self.schemas:
            generate_meta_schema(Path(schema.meta_schema_path), Path(schema.file_path))

    def validate_schemas(self):
        """Validate source schema using metaschema file"""

        for schema in self.schemas:
            meta_validate_file(Path(schema.file_path), Path(schema.meta_schema_path))

    def setup_json_schemas(self):
        """Set up json_schema subdirectory"""
        self.json_schema_directory = Path(self.build_directory) / "json_schema"
        make_dir(self.json_schema_directory)
        for schema in self.schemas:
            json_schema_path = self.json_schema_directory / f"{schema.name}.schema.json"
            schema.json_schema_path = json_schema_path

    def generate_json_schemas(self):
        """Generate JSON schemas"""

        for schema in self.schemas:
            generate_json_schema(schema.file_path, schema.json_schema_path)

    def validate_file(self, input_path, schema_type=None):
        """
        Validate an input instance against JSON schema.
        :param input_path:  Path to data model instance
        :param schema_type: Corresponds to source schema's SchemaType enumeration
        """

        instance = load(input_path)
        if schema_type is None:
            if "metadata" in instance:
                if "schema_name" in instance["metadata"]:
                    schema_type = instance["metadata"]["schema_name"]

        if schema_type is None:
            if len(self.schemas) > 1:
                raise Exception(
                    f"Too many schema available for validation; cannot find a match to"
                    f' "schema_name" {schema_type} in "{input_path}." Unable to validate file.'
                ) from None
            validate_file(input_path, self.schemas[0].json_schema_path)
            postvalidate_file(input_path, self.schemas[0].json_schema_path)
        else:
            # Find corresponding schema
            for schema in self.schemas:
                if schema.schema_name == schema_type:
                    try:
                        validate_file(input_path, schema.json_schema_path)
                        postvalidate_file(input_path, schema.json_schema_path)
                    except RefResolutionError as e:
                        raise Exception(f"Reference in schema {schema.json_schema_path} cannot be resolved: {e}") from e
                    return
            raise Exception(f'Unable to find matching schema, "{schema_type}", for file "{input_path}".')

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
            extensions = ["json", "yaml", "cbor"]
            for ext in extensions:
                self.examples.extend(self.example_directory_path.glob(f"*.{ext}"))
        self.examples.sort()

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
        self.cpp_schemas = self.schemas + [Schema(Path(__file__).with_name("core.schema.yaml"))]

    def setup_cpp_source_files(self):
        """Create directories for generated CPP source"""
        self.cpp_output_dir = Path(self.build_directory) / "cpp"
        make_dir(self.cpp_output_dir)
        include_dir = make_dir(self.cpp_output_dir / "include")
        self._cpp_output_include_dir = make_dir(include_dir / f"{self.root_directory.name}")
        self._cpp_output_src_dir = make_dir(self.cpp_output_dir / "src")
        for schema in self.cpp_schemas:
            schema.cpp_header_file_path = self._cpp_output_include_dir / f"{schema.name}.h"
            schema.cpp_source_file_path = self._cpp_output_src_dir / f"{schema.name}.cpp"

    def setup_cpp_repository(self, submodules: list[str]):
        """Initialize the CPP output directory as a Git repo."""
        cwd = os.getcwd()
        os.chdir(self.cpp_output_dir)
        subprocess.run(["git", "init"], check=True)
        vendor_dir = make_dir("vendor")
        os.chdir(vendor_dir)
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

    def generate_cpp_project(self):
        """Generate CPP header files, source files, and build support files."""
        for schema in self.cpp_schemas:
            h = HeaderTranslator(schema.file_path, None, self._cpp_output_include_dir, self.root_directory.name)
            string_to_file(str(h), schema.cpp_header_file_path)
            c = CPPTranslator(self.root_directory.name, h)
            string_to_file(str(c), schema.cpp_source_file_path)

        submodule_names: list[str] = []
        submodule_urls: list[str] = []

        config_file = Path(self.root_directory / "cpp" / "config.yaml").resolve()
        if config_file.is_file():
            config = load(config_file)
            submodule_names: list[str] = [tuple["name"] for tuple in config["dependencies"]]
            submodule_urls: list[str] = [tuple["url"] for tuple in config["dependencies"] if tuple.get("url")]

        support.render_support_headers(self.root_directory.name, self._cpp_output_include_dir)
        support.render_build_files(self.root_directory.name, submodule_names, self.cpp_output_dir)
        self.setup_cpp_repository(submodule_urls)
