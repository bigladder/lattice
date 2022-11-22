import os
import json
import posixpath
import jsonschema
import yaml
import sys
import re
import copy

from .file_io import load, dump, get_file_basename
from .schema_to_json import JSON_translator


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

# Generate Meta Schema

class SchemaTypes:

    def __init__(self, core_schema, schema=None):
        # Generate Regular Expressions

        # Data Types
        core_types = get_types(core_schema)
        self.combined_types = set(core_types.keys())

        regex_base_types = core_types["Data Type"]

        base_types = '|'.join(regex_base_types)
        base_types = f"({base_types})"

        string_types = core_types["String Type"]
        if schema:
            schema_types = get_types(schema)
            self.combined_types |= set(schema_types.keys())
            if "String Type" in schema_types:
                string_types += ["String Type"]

        re_string_types = '|'.join(string_types)
        re_string_types = f"({re_string_types})"

        template_data_group_prefixes = []
        if schema:
            template_data_group_prefixes = [key for key in schema if schema[key]['Object Type'] == 'Data Group Template']

        self.type_base_names = "[A-Z]([A-Z]|[a-z]|[0-9])*"
        self.type_base_names_anchored = f"^{self.type_base_names}$"
        if len(template_data_group_prefixes) > 0:
            self.data_group_names_anchored = f"(^(?!({'|'.join(template_data_group_prefixes)})){self.type_base_names}$)"
        else:
            self.data_group_names_anchored = self.type_base_names_anchored
        data_groups = fr"\{{{self.type_base_names}\}}"
        enumerations = fr"<{self.type_base_names}>"
        optional_base_types = fr"{base_types}{{1}}(\/{base_types})*"
        single_type = fr"({optional_base_types}|{re_string_types}|{data_groups}|{enumerations})"
        alternatives = fr"\(({single_type})(,\s*{single_type})+\)"
        arrays = fr"\[({single_type})\](\[\d*\.*\d*\])?"
        data_types = f"({single_type})|({alternatives})|({arrays})"
        self.data_types_anchored = f"^{data_types}$"

        pattern = re.compile(self.data_types_anchored)

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

        self.enumerator_anchored = f"^{enumerator}$"

        re.compile(values)

        # Constraints
        self.element_names = "([a-z]+)(_([a-z]|[0-9])+)*"
        self.element_names_anchored = f"^{self.element_names}$"
        alpha_array = "(\[A-Z\]{[1-9]+})"
        numeric_array = "(\[0-9\]{[1-9]+})"
        ranges = f"(>|>=|<=|<){number}"
        multiples = f"%{number}"
        data_element_value = f"{self.element_names}={values}"
        sets = f"\[{number}(, {number})*\]"
        reference_scope = f":{self.type_base_names}:"
        selector = fr"{self.element_names}\({values}(,\s*{values})*\)"

        constraints = f"({alpha_array}|{numeric_array}|{ranges})|({multiples})|({sets})|({data_element_value})|({reference_scope})|({selector})"
        self.constraints_anchored = f"^{constraints}$"

        re.compile(constraints)

        # Conditional Requirements
        conditional_requirements = f"if (!?{self.element_names})(!?=({values}))?"
        self.conditional_requirements_anchored = f"^{conditional_requirements}$"

        re.compile(conditional_requirements)


core_meta_schema_path = os.path.join(os.path.dirname(__file__),'meta.schema.yaml')
core_schema_path = os.path.join(os.path.dirname(__file__),'core.schema.yaml')

def generate_meta_schema(output_path, schema=None):
    ''' '''
    core_schema = load(core_schema_path)

    referenced_schema = []
    if schema is not None:
        source_schema = load(schema)
        schema_dir = os.path.dirname(schema)
        if 'References' in source_schema:
            referenced_schema = [load(schema_file) for schema_file in [os.path.join(schema_dir, f'{ref}.yaml') for ref in source_schema['References']]]
        meta_schema_file_name = f"{get_file_basename(schema, depth=2)}.meta.schema.json"
    else:
        source_schema = None

    schematypes = SchemaTypes(core_schema, source_schema)

    meta_schema = load(core_meta_schema_path)

    # Replace generated patterns from core schema analysis

    meta_schema["definitions"]["Meta"]["properties"]["Unit Systems"]["patternProperties"][schematypes.type_base_names_anchored] = meta_schema["definitions"]["Meta"]["properties"]["Unit Systems"]["patternProperties"].pop("**GENERATED**")
    #meta_schema["definitions"]["DataGroupTemplate"]["patternProperties"][schematypes.type_base_names_anchored] = meta_schema["definitions"]["DataGroupTemplate"]["patternProperties"].pop("**GENERATED**")
    meta_schema["definitions"]["DataGroupTemplate"]["properties"]["Required Data Elements"]["patternProperties"][schematypes.element_names_anchored] = meta_schema["definitions"]["DataGroupTemplate"]["properties"]["Required Data Elements"]["patternProperties"].pop("**GENERATED**")
    meta_schema["definitions"]["DataGroupTemplate"]["properties"]["Object Type"]["pattern"] = schematypes.type_base_names
    meta_schema["definitions"]["ConstraintsPattern"]["pattern"] = schematypes.constraints_anchored
    meta_schema["definitions"]["Required"]["oneOf"][1]["pattern"] = schematypes.conditional_requirements_anchored
    meta_schema["definitions"]["Enumerator"]["patternProperties"][schematypes.enumerator_anchored] = meta_schema["definitions"]["Enumerator"]["patternProperties"].pop("**GENERATED**")
    meta_schema["definitions"]["DataTypePattern"]["pattern"] = schematypes.data_types_anchored
    meta_schema["definitions"]["DataGroup"]["properties"]["Data Elements"]["patternProperties"][schematypes.element_names_anchored] = meta_schema["definitions"]["DataGroup"]["properties"]["Data Elements"]["patternProperties"].pop("**GENERATED**")
    meta_schema["patternProperties"][schematypes.data_group_names_anchored] = meta_schema["patternProperties"].pop("**GENERATED**")

    # Replace generated patterns from schema instance

    if source_schema:
        if 'Schema' in source_schema:
            if 'Title' in source_schema['Schema']:
                meta_schema["title"] = f"{source_schema['Schema']['Title']} Meta-schema"
            # Special Unit Systems
            if 'Unit Systems' in source_schema['Schema']:
                # Unit system definitions
                for unit_system in source_schema['Schema']["Unit Systems"]:
                    meta_schema["definitions"][unit_system] = {"type": "string", "enum": source_schema['Schema']["Unit Systems"][unit_system]}
                    meta_schema["definitions"]["DataElementAttributes"]["properties"]["Units"]["anyOf"].append({"$ref":f"meta.schema.json#/definitions/{unit_system}"})
        # Special Data Groups (gather from referenced Schema as well)
        combined_schema = source_schema.copy()
        for d in referenced_schema:
            combined_schema.update(d)
        for data_group_type in [key for key in combined_schema if combined_schema[key]['Object Type'] == 'Data Group Template']:
            # Data Element Attributes
            data_group = source_schema[data_group_type]
            data_group_type_name = data_group["Name"]
         
            for template_data_group in [template_key for template_key in source_schema if data_group_type_name == combined_schema[template_key]['Object Type']]:
                meta_schema["definitions"][f"{template_data_group}DataElementAttributes"] = copy.deepcopy(meta_schema["definitions"]["DataElementAttributes"])

                if "Unit System" in data_group:
                    meta_schema["definitions"][f"{template_data_group}DataElementAttributes"]["properties"]["Units"] = {"$ref": f"meta.schema.json#/definitions/{data_group['Unit System']}"}

                if "Required Data Types" in data_group:
                    meta_schema["definitions"][f"{template_data_group}DataElementAttributes"]["properties"]["Data Type"] = {"type": "string", "enum": data_group["Required Data Types"]}

                if "Data Elements Required" in data_group:
                    meta_schema["definitions"][f"{template_data_group}DataElementAttributes"]["properties"]["Required"]["const"] = data_group["Data Elements Required"]

                # Data Group
                meta_schema["definitions"][f"{template_data_group}DataGroup"] = copy.deepcopy(meta_schema["definitions"]["DataGroup"])
                meta_schema["definitions"][f"{template_data_group}DataGroup"]["properties"]["Object Type"]["const"] = data_group["Name"]

                if "Required Data Elements" in data_group:
                    required_names = []
                    meta_schema["definitions"][f"{template_data_group}DataGroup"]["properties"]["Data Elements"]["properties"] = {}
                    for data_element_name in data_group["Required Data Elements"]:
                        required_names.append(data_element_name)
                        data_element = data_group["Required Data Elements"][data_element_name]
                        meta_schema["definitions"][f"{template_data_group}-{data_element_name}-DataElementAttributes"] = copy.deepcopy(meta_schema["definitions"][f"{template_data_group}DataElementAttributes"])
                        meta_schema["definitions"][f"{template_data_group}DataGroup"]["properties"]["Data Elements"]["properties"][data_element_name] = copy.deepcopy(meta_schema["definitions"][f"{template_data_group}DataGroup"]["properties"]["Data Elements"]["patternProperties"][schematypes.element_names_anchored])
                        meta_schema["definitions"][f"{template_data_group}DataGroup"]["properties"]["Data Elements"]["properties"][data_element_name]["$ref"] = f"meta.schema.json#/definitions/{template_data_group}-{data_element_name}-DataElementAttributes"
                        for attribute in data_element:
                            meta_schema["definitions"][f"{template_data_group}-{data_element_name}-DataElementAttributes"]["properties"][attribute]["const"] = data_element[attribute]
                            if attribute not in meta_schema["definitions"][f"{template_data_group}DataGroup"]["properties"]["Data Elements"]["properties"][data_element_name]["required"]:
                                meta_schema["definitions"][f"{template_data_group}DataGroup"]["properties"]["Data Elements"]["properties"][data_element_name]["required"].append(attribute)
                    meta_schema["definitions"][f"{template_data_group}DataGroup"]["properties"]["Data Elements"]["required"] = required_names
                    exclusive_element_names_anchored = f"(?!^({'|'.join(required_names)})$)(^{schematypes.element_names}$)"
                    meta_schema["definitions"][f"{template_data_group}DataGroup"]["properties"]["Data Elements"]["patternProperties"][exclusive_element_names_anchored] = meta_schema["definitions"][f"{template_data_group}DataGroup"]["properties"]["Data Elements"]["patternProperties"].pop(schematypes.element_names_anchored)
                    meta_schema["definitions"][f"{template_data_group}DataGroup"]["properties"]["Data Elements"]["patternProperties"][exclusive_element_names_anchored]["$ref"] = f"meta.schema.json#/definitions/{template_data_group}DataElementAttributes"
                else:
                    meta_schema["definitions"][f"{template_data_group}DataGroup"]["properties"]["Data Elements"]["patternProperties"][schematypes.element_names_anchored]["$ref"] = f"meta.schema.json#/definitions/{template_data_group}DataElementAttributes"

                # Main schema
                meta_schema["patternProperties"][f"(^{template_data_group}*$)"] = {"$ref": f"meta.schema.json#/definitions/{template_data_group}DataGroup"}
            meta_schema["patternProperties"][f"^{data_group_type}$"] = {"$ref": f"meta.schema.json#/definitions/DataGroupTemplate"}

    dump(meta_schema, output_path)

    with open(output_path, 'r') as file:
      content = file.read()
    with open(output_path, 'w') as file:
      file.writelines(content.replace("meta.schema.json", meta_schema_file_name))

    return schematypes


def get_types(schema):
    '''For each Object Type in a schema, map a list of Objects matching that type.'''
    types = {}
    for object in schema:
        if schema[object]["Object Type"] not in types:
            types[schema[object]["Object Type"]] = []
        types[schema[object]["Object Type"]].append(object)
    return types
