import os
import json
import posixpath
import jsonschema
import yaml
import sys
import re

from .file_io import load, dump


class MetaSchema:
  def __init__(self, schema_path):
    with open(schema_path) as meta_schema_file:
      uri_path = os.path.abspath(os.path.dirname(schema_path))
      if os.sep != posixpath.sep:
        uri_path = posixpath.sep + uri_path

      resolver = jsonschema.RefResolver(f'file://{uri_path}/', meta_schema_file)
      self.validator = jsonschema.Draft7Validator(json.load(meta_schema_file), resolver=resolver)

  def validate(self, instance_path):
    with open(os.path.join(instance_path), 'r') as input_file:
      instance = yaml.load(input_file, Loader=yaml.FullLoader)
    errors = sorted(self.validator.iter_errors(instance), key=lambda e: e.path)
    file_name =  os.path.basename(instance_path)
    if len(errors) == 0:
      print(f"Validation successful for {file_name}")
    else:
      messages = []
      for error in errors:
        messages.append(f"{error.message} ({'.'.join([str(x) for x in error.path])})")
      messages = [f"{i}. {message}" for i, message in enumerate(messages, start=1)]
      message_str = '\n  '.join(messages)
      raise Exception(f"Validation failed for {file_name} with {len(messages)} errors:\n  {message_str}")

def meta_validate_file(file_path, meta_schema_path):
  meta_schema = MetaSchema(meta_schema_path)
  meta_schema.validate(file_path)

def meta_validate_dir(dir_path, meta_schema_dir_path, errors=[]):
  for file in sorted(os.listdir(dir_path)):
    path = os.path.join(dir_path,file)
    if os.path.isdir(path):
      meta_validate_dir(path, os.path.join(meta_schema_dir_path, file), errors)
    else:
      if '.schema.yaml' in file:
        try:
          meta_schema_path = os.path.join(meta_schema_dir_path, 'meta.schema.json')
          meta_validate_file(os.path.join(dir_path,file), meta_schema_path)
        except Exception as e:
          errors.append(e)
  if len(errors) > 0:
    error_str = '\n\n'.join([f"{e}" for e in errors])
    raise Exception(f"{error_str}")

# Generate Meta Schema

core_meta_schema_path = os.path.join(os.path.dirname(__file__),'meta.schema.yaml')
core_schema_path = os.path.join(os.path.dirname(__file__),'core.schema.yaml')

def generate_meta_schema(output_path, schema_path=None):

  core_schema = load(core_schema_path)

  if schema_path is not None:
    schema = load(schema_path)
  else:
    schema = None

  # Generate Regular Expressions

  # Data Types
  core_types = get_types(core_schema)

  base_types = '|'.join(core_types["Data Type"])
  base_types = f"({base_types})"

  string_types = core_types["String Type"]
  if schema:
    schema_types = get_types(schema)
    if "String Type" in schema_types:
      string_types += ["String Type"]
  string_types = '|'.join(string_types)
  string_types = f"({string_types})"

  if schema:
    if 'Schema' in schema:
      # Data Group Template definitions
      if 'Data Group Templates' in schema['Schema']:
        for data_group in schema['Schema']["Data Group Templates"]:
          pass

  type_base_names = "[A-Z]([A-Z]|[a-z]|[0-9])*"
  element_names = "([a-z]+)(_([a-z]|[0-9])+)*"
  data_groups = f"\\{{{type_base_names}\\}}"
  enumerations = f"<{type_base_names}>"
  optional_base_types = f"{base_types}{{1}}(\\/{base_types})*"
  single_type = f"({optional_base_types}|{string_types}|{data_groups}|{enumerations})"
  alternatives = f"\\({single_type}(,\\s*{single_type})+\\)"
  arrays = f"\\[{base_types}\\]"
  data_types = f"({single_type})|({alternatives})|({arrays})"

  pattern = re.compile(data_types)

  valid_tests = [
    "Numeric",
    "[Numeric]",
    "{DataGroup}"
    ]

  invalid_tests = [
    "Wrong"
  ]

  for test in valid_tests:
    if not re.search(pattern,test):
      raise Exception(f"\"{test}\" does not match: {pattern}")

  for test in invalid_tests:
    if re.search(pattern,test):
      raise Exception(f"\"{test}\" matches: {pattern}")

  # Values
  number = "([-+]?[0-9]*\\.?[0-9]+([eE][-+]?[0-9]+)?)"
  string = "\".*\""
  enumerator = "([A-Z]([A-Z]|[0-9])*)(_([A-Z]|[0-9])+)*"
  boolean = "True|False"
  values = f"({number})|({string})|({enumerator})|({boolean})"

  re.compile(values)

  # Constraints
  ranges = f"(>|>=|<=|<){number}"
  multiples = f"%{number}"
  data_element_value = f"({element_names})=({values})"
  sets = f"\\[{number}(, {number})*\\]"
  constraints = f"({ranges})|({multiples})|({sets})|({data_element_value})"

  re.compile(constraints)

  # Conditional Requirements
  conditional_requirements = f"if ({element_names})(!?=({values}))?"

  re.compile(conditional_requirements)

  meta_schema = load(core_meta_schema_path)

  meta_schema["definitions"]["ConstraintsPattern"]["pattern"] = constraints
  meta_schema["definitions"]["Required"]["oneOf"][1]["pattern"] = conditional_requirements
  meta_schema["definitions"]["Enumerator"]["patternProperties"][enumerator] = meta_schema["definitions"]["Enumerator"]["patternProperties"].pop("**GENERATED**")
  meta_schema["definitions"]["DataTypePattern"]["pattern"] = data_types
  meta_schema["definitions"]["DataElement"]["patternProperties"][element_names] = meta_schema["definitions"]["DataElement"]["patternProperties"].pop("**GENERATED**")
  meta_schema["patternProperties"][type_base_names] = meta_schema["patternProperties"].pop("**GENERATED**")

  # Special Unit Systems
  if schema:
    if 'Schema' in schema:
      if 'Unit Systems' in schema['Schema']:
        # Unit system definitions
        for unit_system in schema['Schema']["Unit Systems"]:
          meta_schema["definitions"][unit_system] = {"type": "string", "enum": schema['Schema']["Unit Systems"][unit_system]}

  # Special Data Groups


  dump(meta_schema, output_path)


def get_types(schema):
  types = {}
  for object in schema:
    if schema[object]["Object Type"] not in types:
      types[schema[object]["Object Type"]] = []
    types[schema[object]["Object Type"]].append(object)
  return types

def generate_meta_schemas(input_dir, output_dir):
  for file in sorted(os.listdir(input_dir)):
    path = os.path.join(input_dir,file)
    if os.path.isdir(path):
      new_output_dir = os.path.join(output_dir, file)
      if not os.path.exists(new_output_dir):
        os.mkdir(new_output_dir)
      generate_meta_schemas(path, new_output_dir)
    elif '.schema.yaml' in file:
      generate_meta_schema(os.path.join(output_dir,'meta.schema.json'), os.path.join(input_dir,file))

if __name__ == '__main__':
  if len(sys.argv) != 2:
    exit(1)
  source = sys.argv[1]
  if not os.path.exists(source):
    exit(1)
  elif os.path.isfile(source):
    meta_validate_file(source)
  else: # is directory
    meta_validate_dir(source)