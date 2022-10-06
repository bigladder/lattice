import lattice
import os

from doit.tools import create_folder

SOURCE_PATH = "lattice"
EXAMPLES_PATH = "examples"
BUILD_PATH = "build"

BASE_META_SCHEMA_PATH = os.path.join(SOURCE_PATH, "meta.schema.yaml")
CORE_SCHEMA_PATH = os.path.join(SOURCE_PATH, "core.schema.yaml")

ROOT_SCHEMAS = sorted([os.path.join(EXAMPLES_PATH, "address", "Address.schema.yaml"),
                os.path.join(EXAMPLES_PATH, "fan_spec", "ASHRAE205.schema.yaml"),
                os.path.join(EXAMPLES_PATH, "lookup_table", "LookupTable.schema.yaml"),
                os.path.join(EXAMPLES_PATH, "ratings", "Rating.schema.yaml"),
                os.path.join(EXAMPLES_PATH, "time_series", "TimeSeries.schema.yaml")])

META_SCHEMAS = sorted(set(lattice.file_io.collect_files(EXAMPLES_PATH, 'schema.yaml', output_dir=BUILD_PATH, new_name='meta.schema', new_extension=".json")))

CORE_SCHEMAS = sorted(set(lattice.file_io.collect_files(EXAMPLES_PATH, 'schema.yaml', output_dir=BUILD_PATH, new_name='core.schema', new_extension=".json")))

JSON_SCHEMAS = lattice.file_io.collect_files(EXAMPLES_PATH, 'schema.yaml', output_dir=BUILD_PATH, new_extension=".json")

EXAMPLE_SCHEMAS = lattice.file_io.collect_files(EXAMPLES_PATH, 'schema.yaml')

EXAMPLE_TEMPLATES = lattice.file_io.collect_files(EXAMPLES_PATH, 'md.j2')

OUTPUT_MD = lattice.file_io.collect_files(EXAMPLES_PATH, 'md.j2', output_dir=BUILD_PATH, new_extension="")

DOIT_CONFIG = {"default_tasks": ["file_validation", "markdown_generation"]}

def task_generate_meta_schemas():
  '''Generate JSON meta schemas'''
  return {
    'file_dep': EXAMPLE_SCHEMAS +
                [BASE_META_SCHEMA_PATH,
                 CORE_SCHEMA_PATH,
                 os.path.join(SOURCE_PATH, "meta_schema.py")],
    'targets': META_SCHEMAS,
    'actions': [
      (create_folder, [BUILD_PATH]),
      (lattice.generate_meta_schemas, [META_SCHEMAS, ROOT_SCHEMAS])
    ],
    'clean': True
  }

def task_meta_validation():
  '''Validate the examples against the JSON meta schema'''
  return {
    'task_dep': ['generate_meta_schemas'],
    'file_dep': META_SCHEMAS + EXAMPLE_SCHEMAS,
    'actions': [(lattice.meta_validate_dir,[EXAMPLES_PATH, BUILD_PATH])]
  }

def task_json_translation():
  '''Generate JSON schemas'''
  return {
    'task_dep': ['meta_validation'],
    'file_dep': EXAMPLE_SCHEMAS +
                [BASE_META_SCHEMA_PATH,
                 CORE_SCHEMA_PATH,
                 os.path.join(SOURCE_PATH, "meta_schema.py")],
    'targets': JSON_SCHEMAS + CORE_SCHEMAS,
    'actions': [
      (create_folder, [BUILD_PATH]),
      (lattice.generate_json_schemas, [EXAMPLES_PATH, BUILD_PATH])
    ],
    'clean': True
  }

def task_file_validation():
  '''Validate input file against JSON schema'''
  return {
    'file_dep': [os.path.join(SOURCE_PATH, "schema_to_json.py")],
    'task_dep': ['json_translation'],
    'actions': [
      (lattice.validate_json_file, [os.path.join(EXAMPLES_PATH, "fan_spec", "Fan-Continuous.RS0003.a205.json"), os.path.join(BUILD_PATH, "fan_spec", "RS0003.schema.json")])
    ],
    'clean': []
  }

def task_markdown_generation():
  '''Generate markdown documentation from templates'''
  return {
    'task_dep': ['meta_validation'],
    'targets': OUTPUT_MD,
    'file_dep': META_SCHEMAS + EXAMPLE_SCHEMAS + EXAMPLE_TEMPLATES,
    'actions': [
      (lattice.process_templates, [EXAMPLES_PATH, BUILD_PATH])
    ],
    'clean': True
  }

def task_web_doc_generation():
  '''Generate markdown documentation from templates'''
  OUTPUT_DIR = os.path.join(BUILD_PATH, "lookup_table")
  WEB_DIR = os.path.join(OUTPUT_DIR, "web")
  return {
    'task_dep': ['meta_validation'],
    'actions': [
      (lattice.make_web_docs,
      [os.path.join(EXAMPLES_PATH, "lookup_table"),
      os.path.join(EXAMPLES_PATH, "lookup_table", "lookup_table.md.j2"),
      os.path.join(BUILD_PATH, "lookup_table")
      ]),
      f"cd {WEB_DIR} && hugo mod init lookup_table",
      f"cd {WEB_DIR} && hugo mod get github.com/google/docsy@v0.4.0",
      f"cd {WEB_DIR} && npm install",
      f"cd {WEB_DIR} && hugo --minify",
    ],
    'clean': True
  }
