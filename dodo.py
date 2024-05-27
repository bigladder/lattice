from lattice import Lattice
from pathlib import Path

from doit.tools import create_folder

SOURCE_PATH = "lattice"
EXAMPLES_PATH = "examples"
BUILD_PATH = "build"

examples = []

for example_dir in sorted([str(dir_name) for dir_name in Path(EXAMPLES_PATH).iterdir()]):
    example_dir_path = Path(example_dir)
    example_name = example_dir_path.name
    if example_dir_path.is_dir():
        build_dir_path = Path(BUILD_PATH, example_name)
        create_folder(build_dir_path)
        examples.append(
            Lattice(example_dir_path, build_dir_path, build_output_directory_name=None, build_validation=False)
        )

BASE_META_SCHEMA_PATH = Path(SOURCE_PATH, "meta.schema.yaml")
CORE_SCHEMA_PATH = Path(SOURCE_PATH, "core.schema.yaml")


def task_generate_meta_schemas():
    """Generate JSON meta schemas"""
    for example in examples:
        name = Path(example.root_directory).name
        yield {
            "name": name,
            "file_dep": [schema.path for schema in example.schemas]
            + [BASE_META_SCHEMA_PATH, CORE_SCHEMA_PATH, Path(SOURCE_PATH, "meta_schema.py")],
            "targets": [schema.meta_schema_path for schema in example.schemas],
            "actions": [(example.generate_meta_schemas, [])],
            "clean": True,
        }


def task_validate_schemas():
    """Validate the example schemas against the JSON meta schema"""
    for example in examples:
        name = Path(example.root_directory).name
        yield {
            "name": name,
            "task_dep": [f"generate_meta_schemas:{name}"],
            "file_dep": [schema.path for schema in example.schemas]
            + [schema.meta_schema_path for schema in example.schemas]
            + [BASE_META_SCHEMA_PATH, CORE_SCHEMA_PATH, Path(SOURCE_PATH, "meta_schema.py")],
            "actions": [(example.validate_schemas, [])],
        }


def task_generate_json_schemas():
    """Generate JSON schemas"""
    for example in examples:
        name = Path(example.root_directory).name
        yield {
            "name": name,
            "task_dep": [f"validate_schemas:{name}"],
            "file_dep": [schema.path for schema in example.schemas]
            + [schema.meta_schema_path for schema in example.schemas]
            + [CORE_SCHEMA_PATH, BASE_META_SCHEMA_PATH, Path(SOURCE_PATH, "schema_to_json.py")],
            "targets": [schema.json_schema_path for schema in example.schemas],
            "actions": [(example.generate_json_schemas, [])],
            "clean": True,
        }


def task_validate_example_files():
    """Validate example files against JSON schema"""
    for example in examples:
        name = Path(example.root_directory).name
        yield {
            "name": name,
            "file_dep": [schema.json_schema_path for schema in example.schemas]
            + example.examples
            + [Path(SOURCE_PATH, "schema_to_json.py")],
            "task_dep": [f"generate_json_schemas:{name}"],
            "actions": [(example.validate_example_files, [])],
        }


def task_generate_markdown():
    """Generate markdown documentation from templates"""
    for example in examples:
        name = Path(example.root_directory).name
        yield {
            "name": name,
            "targets": [template.markdown_output_path for template in example.doc_templates],
            "file_dep": [schema.path for schema in example.schemas]
            + [template.path for template in example.doc_templates]
            + [Path(SOURCE_PATH, "docs", "grid_table.py")],
            "task_dep": [f"validate_schemas:{name}"],
            "actions": [(example.generate_markdown_documents, [])],
            "clean": True,
        }


def task_generate_cpp_code():
    """Generate CPP headers and source for example schema."""
    for example in examples:
        name = Path(example.root_directory).name
        yield {
            "name": name,
            "task_dep": [f"validate_schemas:{name}"],
            "file_dep": [schema.path for schema in example.cpp_schemas]
            + [schema.meta_schema_path for schema in example.schemas]
            + [CORE_SCHEMA_PATH, BASE_META_SCHEMA_PATH, Path(SOURCE_PATH, "header_entries.py"), Path(SOURCE_PATH, "cpp_entries.py")],
            "targets": [schema.cpp_header_path for schema in example.cpp_schemas]
            + [schema.cpp_source_path for schema in example.cpp_schemas]
            + example.cpp_support_headers(),
            "actions": [(example.generate_cpp_headers, [])],
            "clean": True,
        }


def task_generate_web_docs():
    """Generate markdown documentation from templates"""
    for example in examples:
        name = Path(example.root_directory).name
        yield {
            "name": name,
            "task_dep": [f"validate_schemas:{name}", f"generate_json_schemas:{name}", f"validate_example_files:{name}"],
            "file_dep": [schema.path for schema in example.schemas]
            + [template.path for template in example.doc_templates]
            + [Path(SOURCE_PATH, "docs", "mkdocs_web.py")],
            "targets": [Path(example.web_docs_directory_path, "public")],
            "actions": [(example.generate_web_documentation, [])],
            "clean": True,
        }


def task_test():
    """Run unit tests"""
    return {"actions": ["pytest -v test"]}
