import os
import json
import posixpath
import jsonschema
import yaml
import sys
import re
import copy

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

  regex_base_types = core_types["Data Type"]

  base_types = '|'.join(regex_base_types)
  base_types = f"({base_types})"

  string_types = core_types["String Type"]
  if schema:
    schema_types = get_types(schema)
    if "String Type" in schema_types:
      string_types += ["String Type"]

  re_string_types = '|'.join(string_types)
  re_string_types = f"({re_string_types})"

  template_data_group_prefixes = []
  if schema:
    if 'Schema' in schema:
      # Data Group Template definitions
      if 'Data Group Templates' in schema['Schema']:
        for data_group in schema['Schema']["Data Group Templates"]:
          template_data_group_prefixes.append(data_group)

  type_base_names = "[A-Z]([A-Z]|[a-z]|[0-9])*"
  type_base_names_anchored = f"^{type_base_names}$"
  if len(template_data_group_prefixes) > 0:
    data_group_names_anchored = f"(^(?!({'|'.join(template_data_group_prefixes)})){type_base_names}$)"
  else:
    data_group_names_anchored = type_base_names_anchored
  data_groups = fr"\{{{type_base_names}\}}"
  enumerations = fr"<{type_base_names}>"
  optional_base_types = fr"{base_types}{{1}}(\/{base_types})*"
  single_type = fr"({optional_base_types}|{re_string_types}|{data_groups}|{enumerations})"
  alternatives = fr"\(({single_type})(,\s*{single_type})+\)"
  arrays = fr"\[({single_type})\](\[\d*\.*\d*\])?"
  data_types = f"({single_type})|({alternatives})|({arrays})"
  data_types_anchored = f"^{data_types}$"

  pattern = re.compile(data_types_anchored)

  valid_tests = [
    "Numeric",
    "[Numeric]",
    "{DataGroup}",
    "[String][1..]",
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

  enumerator_anchored = f"^{enumerator}$"

  re.compile(values)

  # Constraints
  element_names = "([a-z]+)(_([a-z]|[0-9])+)*"
  element_names_anchored = f"^{element_names}$"
  ranges = f"(>|>=|<=|<){number}"
  multiples = f"%{number}"
  data_element_value = f"({element_names})=({values})"
  sets = f"\\[{number}(, {number})*\\]"
  reference_scope = f":{type_base_names}:"

  constraints = f"({ranges})|({multiples})|({sets})|({data_element_value})|({reference_scope})"
  constraints_anchored = f"^{constraints}$"

  re.compile(constraints)

  # Conditional Requirements
  conditional_requirements = f"if (!?{element_names})(!?=({values}))?"
  conditional_requirements_anchored = f"^{conditional_requirements}$"

  re.compile(conditional_requirements)

  meta_schema = load(core_meta_schema_path)

  # Replace generated patterns
  meta_schema["definitions"]["Meta"]["properties"]["Unit Systems"]["patternProperties"][type_base_names_anchored] = meta_schema["definitions"]["Meta"]["properties"]["Unit Systems"]["patternProperties"].pop("**GENERATED**")
  meta_schema["definitions"]["Meta"]["properties"]["Data Group Templates"]["patternProperties"][type_base_names_anchored] = meta_schema["definitions"]["Meta"]["properties"]["Data Group Templates"]["patternProperties"].pop("**GENERATED**")
  meta_schema["definitions"]["Meta"]["properties"]["Data Group Templates"]["patternProperties"][type_base_names_anchored]["properties"]["Required Data Elements"]["patternProperties"][element_names_anchored] = meta_schema["definitions"]["Meta"]["properties"]["Data Group Templates"]["patternProperties"][type_base_names_anchored]["properties"]["Required Data Elements"]["patternProperties"].pop("**GENERATED**")
  meta_schema["definitions"]["Meta"]["properties"]["Data Group Templates"]["patternProperties"][type_base_names_anchored]["properties"]["Object Type Name"]["pattern"] = type_base_names
  meta_schema["definitions"]["ConstraintsPattern"]["pattern"] = constraints_anchored
  meta_schema["definitions"]["Required"]["oneOf"][1]["pattern"] = conditional_requirements_anchored
  meta_schema["definitions"]["Enumerator"]["patternProperties"][enumerator_anchored] = meta_schema["definitions"]["Enumerator"]["patternProperties"].pop("**GENERATED**")
  meta_schema["definitions"]["DataTypePattern"]["pattern"] = data_types_anchored
  meta_schema["definitions"]["DataGroup"]["properties"]["Data Elements"]["patternProperties"][element_names_anchored] = meta_schema["definitions"]["DataGroup"]["properties"]["Data Elements"]["patternProperties"].pop("**GENERATED**")
  meta_schema["patternProperties"][data_group_names_anchored] = meta_schema["patternProperties"].pop("**GENERATED**")

  for string_obj_name in [name for name in core_schema if core_schema[name]['Object Type'] == 'String Type']:
    if 'Is Regex' in core_schema[string_obj_name]:
        meta_schema["definitions"][string_obj_name] = {"type":"string", "regex":True}
    else:
        meta_schema["definitions"][string_obj_name] = {"type":"string", "pattern":core_schema[string_obj_name]['JSON Schema Pattern']}

  if schema:
    if 'Schema' in schema:
      if 'Title' in schema['Schema']:
        meta_schema["title"] = f"{schema['Schema']['Title']} Meta-schema"
      # Special Unit Systems
      if 'Unit Systems' in schema['Schema']:
        # Unit system definitions
        for unit_system in schema['Schema']["Unit Systems"]:
          meta_schema["definitions"][unit_system] = {"type": "string", "enum": schema['Schema']["Unit Systems"][unit_system]}

      # Special Data Groups
      if 'Data Group Templates' in schema['Schema']:
        for data_group_type in schema['Schema']["Data Group Templates"]:
          # Data Element Attributes
          data_group = schema['Schema']["Data Group Templates"][data_group_type]
          meta_schema["definitions"][f"{data_group_type}DataElementAttributes"] = copy.deepcopy(meta_schema["definitions"]["DataElementAttributes"])

          if "Unit System" in data_group:
            meta_schema["definitions"][f"{data_group_type}DataElementAttributes"]["properties"]["Units"] = {"$ref": f"meta.schema.json#/definitions/{data_group['Unit System']}"}

          if "Required Data Types" in data_group:
            meta_schema["definitions"][f"{data_group_type}DataElementAttributes"]["properties"]["Data Type"] = {"type": "string", "enum": data_group["Required Data Types"]}

          if "Data Elements Required" in data_group:
            meta_schema["definitions"][f"{data_group_type}DataElementAttributes"]["properties"]["Required"]["const"] = data_group["Data Elements Required"]

          # Data Group
          meta_schema["definitions"][f"{data_group_type}DataGroup"] = copy.deepcopy(meta_schema["definitions"]["DataGroup"])
          meta_schema["definitions"][f"{data_group_type}DataGroup"]["properties"]["Object Type"]["const"] = data_group["Object Type Name"]

          if "Required Data Elements" in data_group:
            required_names = []
            meta_schema["definitions"][f"{data_group_type}DataGroup"]["properties"]["Data Elements"]["properties"] = {}
            for data_element_name in data_group["Required Data Elements"]:
              required_names.append(data_element_name)
              data_element = data_group["Required Data Elements"][data_element_name]
              meta_schema["definitions"][f"{data_group_type}-{data_element_name}-DataElementAttributes"] = copy.deepcopy(meta_schema["definitions"][f"{data_group_type}DataElementAttributes"])
              meta_schema["definitions"][f"{data_group_type}DataGroup"]["properties"]["Data Elements"]["properties"][data_element_name] = copy.deepcopy(meta_schema["definitions"][f"{data_group_type}DataGroup"]["properties"]["Data Elements"]["patternProperties"][element_names_anchored])
              meta_schema["definitions"][f"{data_group_type}DataGroup"]["properties"]["Data Elements"]["properties"][data_element_name]["$ref"] = f"meta.schema.json#/definitions/{data_group_type}-{data_element_name}-DataElementAttributes"
              for attribute in data_element:
                meta_schema["definitions"][f"{data_group_type}-{data_element_name}-DataElementAttributes"]["properties"][attribute]["const"] = data_element[attribute]
                if attribute not in meta_schema["definitions"][f"{data_group_type}DataGroup"]["properties"]["Data Elements"]["properties"][data_element_name]["required"]:
                  meta_schema["definitions"][f"{data_group_type}DataGroup"]["properties"]["Data Elements"]["properties"][data_element_name]["required"].append(attribute)
            meta_schema["definitions"][f"{data_group_type}DataGroup"]["properties"]["Data Elements"]["required"] = required_names
            exclusive_element_names_anchored = f"(?!^({'|'.join(required_names)})$)(^{element_names}$)"
            meta_schema["definitions"][f"{data_group_type}DataGroup"]["properties"]["Data Elements"]["patternProperties"][exclusive_element_names_anchored] = meta_schema["definitions"][f"{data_group_type}DataGroup"]["properties"]["Data Elements"]["patternProperties"].pop(element_names_anchored)
            meta_schema["definitions"][f"{data_group_type}DataGroup"]["properties"]["Data Elements"]["patternProperties"][exclusive_element_names_anchored]["$ref"] = f"meta.schema.json#/definitions/{data_group_type}DataElementAttributes"
          else:
            meta_schema["definitions"][f"{data_group_type}DataGroup"]["properties"]["Data Elements"]["patternProperties"][element_names_anchored]["$ref"] = f"meta.schema.json#/definitions/{data_group_type}DataElementAttributes"

          # Main schema
          meta_schema["patternProperties"][f"(^{data_group_type}({type_base_names})*$)"] = {"$ref": f"meta.schema.json#/definitions/{data_group_type}DataGroup"}

  dump(meta_schema, output_path)


def get_types(schema):
  '''For each Object Type in a schema, map a list of Objects matching that type.'''
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