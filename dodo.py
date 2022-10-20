from lattice import Lattice
import os

from doit.tools import create_folder

SOURCE_PATH = "lattice"
EXAMPLES_PATH = "examples"
BUILD_PATH = "build"

examples = []

for example_dir in os.listdir(EXAMPLES_PATH):
  example_dir_path = os.path.join(EXAMPLES_PATH, example_dir)
  if os.path.isdir(example_dir_path):
    build_dir_path = os.path.join(BUILD_PATH, example_dir)
    create_folder(build_dir_path)
    examples.append(Lattice(example_dir_path, example_dir, build_dir_path, build_output_directory_name=None, build_validation=False))

BASE_META_SCHEMA_PATH = os.path.join(SOURCE_PATH, "meta.schema.yaml")
CORE_SCHEMA_PATH = os.path.join(SOURCE_PATH, "core.schema.yaml")

DOIT_CONFIG = {"default_tasks": ["validate_example_files", "generate_markdown"]}

def task_generate_meta_schemas():
  '''Generate JSON meta schemas'''
  for example in examples:
    yield {
      'name': example.name,
      'file_dep': [schema.path for schema in example.schemas] +
                  [BASE_META_SCHEMA_PATH,
                   CORE_SCHEMA_PATH,
                   os.path.join(SOURCE_PATH, "meta_schema.py")],
      'targets': [schema.meta_schema_path for schema in example.schemas],
      'actions': [
        (example.generate_meta_schemas, [])
      ],
      'clean': True
    }


def task_validate_schemas():
  '''Validate the example schemas against the JSON meta schema'''
  for example in examples:
    yield {
      'name': example.name,
      'task_dep': [f"generate_meta_schemas:{example.name}"],
      'file_dep': [schema.path for schema in example.schemas] +
                  [schema.meta_schema_path for schema in example.schemas] +
                  [BASE_META_SCHEMA_PATH,
                   CORE_SCHEMA_PATH,
                   os.path.join(SOURCE_PATH, "meta_schema.py")],
      'actions': [
        (example.validate_schemas, [])
      ]
    }

def task_generate_json_schemas():
  '''Generate JSON schemas'''
  for example in examples:
    yield {
      'name': example.name,
      'task_dep': [f"validate_schemas:{example.name}"],
      'file_dep': [schema.path for schema in example.schemas] +
                  [schema.meta_schema_path for schema in example.schemas] +
                  [CORE_SCHEMA_PATH,
                   BASE_META_SCHEMA_PATH,
                   os.path.join(SOURCE_PATH, "schema_to_json.py")],
      'targets': [schema.json_schema_path for schema in example.schemas] + [schema.flat_schema_path for schema in example.schemas] + [example.core_json_schema_path],
      'actions': [
        (example.generate_json_schemas, [])
      ],
      'clean': True
    }

def task_validate_example_files():
  '''Validate example files against JSON schema'''
  for example in examples:
    yield {
      'name': example.name,
      'file_dep': [schema.json_schema_path for schema in example.schemas] + example.examples + [os.path.join(SOURCE_PATH, "schema_to_json.py")],
      'task_dep': [f"generate_json_schemas:{example.name}"],
      'actions': [
        (example.validate_example_files, [])
      ]
    }

def task_generate_markdown():
  '''Generate markdown documentation from templates'''
  for example in examples:
    yield {
      'name': example.name,
      'targets': [template.markdown_output_path for template in example.doc_templates],
      'file_dep': [schema.path for schema in example.schemas] + [template.path for template in example.doc_templates],
      'task_dep': [f"validate_schemas:{example.name}"],
      'actions': [
        (example.generate_markdown_documents, [])
      ],
      'clean': True
    }

def task_generate_web_docs():
  '''Generate markdown documentation from templates'''
  for example in examples:
    yield {
      'name': example.name,
      'task_dep': [f"validate_schemas:{example.name}"],
      'file_dep': [schema.path for schema in example.schemas] + [template.path for template in example.doc_templates],
      'targets': [os.path.join(example.web_docs_directory_path,"public")],
      'actions': [
        (example.generate_web_documentation, [])
      ],
      'clean': True
    }
