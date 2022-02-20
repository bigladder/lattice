import lattice
import os

from doit.tools import create_folder

SOURCE_PATH = "lattice"
EXAMPLES_PATH = "examples"
BUILD_PATH = "build"

BASE_META_SCHEMA_PATH = os.path.join(SOURCE_PATH, "meta.schema.yaml")
CORE_SCHEMA_PATH = os.path.join(SOURCE_PATH, "core.schema.yaml")

META_SCHEMAS = list(set(lattice.file_io.collect_files(EXAMPLES_PATH, 'schema.yaml', output_dir=BUILD_PATH, new_name='meta.schema', new_extension=".json")))

JSON_SCHEMAS = lattice.file_io.collect_files(EXAMPLES_PATH, 'schema.yaml', output_dir=BUILD_PATH, new_extension=".json")

EXAMPLE_SCHEMAS = lattice.file_io.collect_files(EXAMPLES_PATH, 'schema.yaml')

EXAMPLE_TEMPLATES = lattice.file_io.collect_files(EXAMPLES_PATH, 'md.j2')

OUTPUT_MD = lattice.file_io.collect_files(EXAMPLES_PATH, 'md.j2', output_dir=BUILD_PATH, new_extension="")


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
      (lattice.generate_meta_schemas, [EXAMPLES_PATH, BUILD_PATH])
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
    'targets': JSON_SCHEMAS,
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
    'actions': [
      (lattice.validate_json_file, ['/Users/tanaya-mankad/src/lattice/examples/fan_spec/Fan-Continuous.RS0003.a205.json', '/Users/tanaya-mankad/src/lattice/build/fan_spec/RS0003.schema.json'])
    ],
    'clean': []
  }

def task_doc_generation():
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