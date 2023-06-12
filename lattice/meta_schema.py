"""This module defines classes and functions to generate lattice metaschema."""

import re
import copy
from pathlib import Path
from dataclasses import dataclass
import jsonschema
import yaml

from .file_io import load, dump, get_file_basename


class MetaSchema: #pylint: disable=R0903
    """Load and validate a metaschema"""

    def __init__(self, schema_path: Path):
        """Set up validator"""
        meta_schema_file = load(schema_path)
        uri_path = Path(schema_path).absolute().parent.as_uri() + \
            r'/'  # TODO: Why is trailing slash needed here
        resolver = jsonschema.RefResolver(uri_path, meta_schema_file)
        self.validator = jsonschema.Draft7Validator(meta_schema_file, resolver=resolver)

    def validate(self, instance_path: Path):
        """Collect validation errors"""
        with open(instance_path, 'r', encoding='utf-8') as input_file:
            instance = yaml.load(input_file, Loader=yaml.FullLoader)
        errors = sorted(self.validator.iter_errors(instance), key=lambda e: e.path)
        file_name = instance_path.name
        if len(errors) == 0:
            print(f"Validation successful for {file_name}")
        else:
            messages = []
            for error in errors:
                messages.append(f"{error.message} ({'.'.join([str(x) for x in error.path])})")
            messages = [f"{i}. {message}" for i, message in enumerate(messages, start=1)]
            message_str = '\n  '.join(messages)
            raise Exception(
                f"Validation failed for {file_name} with {len(messages)} errors:\n  {message_str}")


def meta_validate_file(file_path: Path, meta_schema_path: Path):
    """Validate schema against metaschema"""
    meta_schema = MetaSchema(meta_schema_path)
    meta_schema.validate(file_path)

# Generate Meta Schema

@dataclass
class SchemaTypes: #pylint: disable=R0902
    """Encapsulate the patterns used to describe schema types"""

    core_schema: dict
    schema: dict
    type_base_names: str = "[A-Z]([A-Z]|[a-z]|[0-9])*"
    type_base_names_anchored: str = f"^{type_base_names}$"
    data_group_names_anchored: str = type_base_names_anchored
    data_types_anchored: str = ""
    enumerator_anchored: str = ""
    element_names: str = "([a-z][a-z,0-9]*)(_([a-z,0-9])+)*"
    element_names_anchored: str = f"^{element_names}$"
    conditional_requirements_anchored: str = ""

    def __post_init__(self): #pylint: disable=R0914
        """Generate regular expressions describing lattice types"""

        if self.schema is None:
            self.schema = {}
        # Data Types
        core_types = get_types(self.core_schema)

        regex_base_types = core_types["Data Type"]

        base_types = f"({'|'.join(regex_base_types)})"

        string_types = core_types["String Type"]
        if self.schema:
            schema_types = get_types(self.schema)
            if "String Type" in schema_types:
                string_types += ["String Type"]

        re_string_types = f"({'|'.join(string_types)})"

        template_data_group_prefixes = []
        if self.schema:
            template_data_group_prefixes = [
                key for key in self.schema if self.schema[key]['Object Type'] == 'Data Group Template']

        if template_data_group_prefixes:
            self.data_group_names_anchored = f"(^(?!({'|'.join(template_data_group_prefixes)})){self.type_base_names}$)"

        data_groups = fr"\{{{self.type_base_names}\}}"
        enumerations = fr"<{self.type_base_names}>"
        optional_base_types = fr"{base_types}{{1}}(\/{base_types})*"
        single_type = fr"({optional_base_types}|{re_string_types}|{data_groups}|{enumerations})"
        alternatives = fr"\(({single_type})(,\s*{single_type})+\)"
        arrays = fr"\[({single_type})\](\[\d*\.*\d*\])?"
        data_types = f"({single_type})|({alternatives})|({arrays})"
        self.data_types_anchored = f"^{data_types}$"

        # Values
        number = "([-+]?[0-9]*\\.?[0-9]+([eE][-+]?[0-9]+)?)"
        string = "\".*\""
        enumerator = "([A-Z]([A-Z]|[0-9])*)(_([A-Z]|[0-9])+)*"
        boolean = "True|False"
        values = f"({number})|({string})|({enumerator})|({boolean})"

        re.compile(values) # test only

        self.enumerator_anchored = f"^{enumerator}$"
        
        alpha_array = "(\\[A-Z\\]{[1-9]+})" # type: ignore : meta string; eventually yields e.g. ([A-Z]{231})
        numeric_array = "(\\[0-9\\]{[1-9]+})"  # type: ignore : yields e.g. [0-9]{17}
        ranges = f"(>|>=|<=|<){number}"
        multiples = f"%{number}"
        data_element_value = f"{self.element_names}={values}"
        sets = f"\\[{number}(, {number})*\\]"  # type: ignore
        reference_scope = f":{self.type_base_names}:"
        selector = fr"{self.element_names}\({values}(,\s*{values})*\)"

        constraints = f"({alpha_array}|{numeric_array}|{ranges})|({multiples})|({sets})|({data_element_value})|({reference_scope})|({selector})"
        re.compile(constraints)  # test only
        self.constraints_anchored = f"^{constraints}$"

        # Conditional Requirements
        conditional_requirements = f"if (!?{self.element_names})(!?=({values}))?"
        re.compile(conditional_requirements)  # test only
        self.conditional_requirements_anchored = f"^{conditional_requirements}$"

    def test_patterns(self):
        """Test that complex regex patterns compile"""

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
            if not re.search(pattern, test):
                raise Exception(f"\"{test}\" does not match: {pattern}")

        for test in invalid_tests:
            if re.search(pattern, test):
                raise Exception(f"\"{test}\" matches: {pattern}")


def _replace_generated_patterns(meta_schema: dict, schematypes: SchemaTypes):
    """Replace generated patterns from core schema analysis"""

    definitions = meta_schema["definitions"]
    definitions["Meta"]["properties"]["Unit Systems"]["patternProperties"][schematypes.type_base_names_anchored] = definitions["Meta"]["properties"]["Unit Systems"]["patternProperties"].pop("**GENERATED**")
    definitions["DataGroupTemplate"]["properties"]["Required Data Elements"]["patternProperties"][schematypes.element_names_anchored] = definitions["DataGroupTemplate"]["properties"]["Required Data Elements"]["patternProperties"].pop("**GENERATED**")
    definitions["DataGroupTemplate"]["properties"]["Object Type"]["pattern"] = schematypes.type_base_names
    definitions["ConstraintsPattern"]["pattern"] = schematypes.constraints_anchored
    definitions["Required"]["oneOf"][1]["pattern"] = schematypes.conditional_requirements_anchored
    definitions["Enumerator"]["patternProperties"][schematypes.enumerator_anchored] = definitions["Enumerator"]["patternProperties"].pop("**GENERATED**")
    definitions["DataTypePattern"]["pattern"] = schematypes.data_types_anchored
    definitions["DataGroup"]["properties"]["Data Elements"]["patternProperties"][schematypes.element_names_anchored] = definitions["DataGroup"]["properties"]["Data Elements"]["patternProperties"].pop("**GENERATED**")
    meta_schema["patternProperties"][schematypes.data_group_names_anchored] = meta_schema["patternProperties"].pop("**GENERATED**")


def _populate_schema_specifics(meta_schema: dict, source_schema: dict):
    """Populate top-level, schema-specific desciptive elements"""

    if 'Schema' in source_schema:
        if 'Title' in source_schema['Schema']:
            meta_schema["title"] = f"{source_schema['Schema']['Title']} Meta-schema"
        # Special Unit Systems
        if 'Unit Systems' in source_schema['Schema']:
            # Unit system definitions
            for unit_system in source_schema['Schema']["Unit Systems"]:
                meta_schema["definitions"][unit_system] = {
                    "type": "string", "enum": source_schema['Schema']["Unit Systems"][unit_system]}
                meta_schema["definitions"]["DataElementAttributes"]["properties"]["Units"]["anyOf"].append(
                    {"$ref": f"meta.schema.json#/definitions/{unit_system}"})

def _populate_template_group_rules(definitions: dict,
                                   data_group: dict,
                                   template_data_group: str):
    """Create meta-schema validation entries for each of the custom data groups"""

    # Data Element Attributes component for the template data group
    definitions[f"{template_data_group}DataElementAttributes"] = copy.deepcopy(
        definitions["DataElementAttributes"])

    if "Unit System" in data_group:
        definitions[f"{template_data_group}DataElementAttributes"]["properties"]["Units"] = {
            "$ref": f"meta.schema.json#/definitions/{data_group['Unit System']}"}

    if "Required Data Types" in data_group:
        definitions[f"{template_data_group}DataElementAttributes"]["properties"]["Data Type"] = {
            "type": "string", "enum": data_group["Required Data Types"]}

    if "Data Elements Required" in data_group:
        definitions[f"{template_data_group}DataElementAttributes"][
            "properties"]["Required"]["const"] = data_group["Data Elements Required"]

    # Data Group component for the template data group
    definitions[f"{template_data_group}DataGroup"] = copy.deepcopy(definitions["DataGroup"])
    definitions[f"{template_data_group}DataGroup"]["properties"]["Object Type"]["const"] = data_group["Name"]

def _populate_template_group_element_rules(definitions: dict,
                                           data_group: dict,
                                           template_data_group: str,
                                           schematypes: SchemaTypes):
    """Create meta-schema validation entries for each of the custom data groups' elements"""

    if "Required Data Elements" in data_group:
        required_names = []
        definitions[f"{template_data_group}DataGroup"]["properties"]["Data Elements"]["properties"] = {}
        for data_element_name in data_group["Required Data Elements"]:
            required_names.append(data_element_name)
            data_element = data_group["Required Data Elements"][data_element_name]
            definitions[f"{template_data_group}-{data_element_name}-DataElementAttributes"] = copy.deepcopy(
                definitions[f"{template_data_group}DataElementAttributes"])
            definitions[f"{template_data_group}DataGroup"]["properties"]["Data Elements"]["properties"][data_element_name] = copy.deepcopy(
                definitions[f"{template_data_group}DataGroup"]["properties"]["Data Elements"]["patternProperties"][schematypes.element_names_anchored])
            definitions[f"{template_data_group}DataGroup"]["properties"]["Data Elements"]["properties"][data_element_name][
                "$ref"] = f"meta.schema.json#/definitions/{template_data_group}-{data_element_name}-DataElementAttributes"
            for attribute in data_element:
                definitions[f"{template_data_group}-{data_element_name}-DataElementAttributes"][
                    "properties"][attribute]["const"] = data_element[attribute]
                if attribute not in definitions[f"{template_data_group}DataGroup"]["properties"]["Data Elements"]["properties"][data_element_name]["required"]:
                    definitions[f"{template_data_group}DataGroup"]["properties"]["Data Elements"]["properties"][data_element_name]["required"].append(attribute)
        definitions[f"{template_data_group}DataGroup"]["properties"]["Data Elements"]["required"] = required_names
        exclusive_element_names_anchored = f"(?!^({'|'.join(required_names)})$)(^{schematypes.element_names}$)"
        definitions[f"{template_data_group}DataGroup"]["properties"]["Data Elements"]["patternProperties"][exclusive_element_names_anchored] = definitions[f"{template_data_group}DataGroup"]["properties"]["Data Elements"]["patternProperties"].pop(schematypes.element_names_anchored)
        definitions[f"{template_data_group}DataGroup"]["properties"]["Data Elements"]["patternProperties"][
            exclusive_element_names_anchored]["$ref"] = f"meta.schema.json#/definitions/{template_data_group}DataElementAttributes"
    else:
        definitions[f"{template_data_group}DataGroup"]["properties"]["Data Elements"]["patternProperties"][
            schematypes.element_names_anchored]["$ref"] = f"meta.schema.json#/definitions/{template_data_group}DataElementAttributes"


core_meta_schema_path = Path(__file__).with_name('meta.schema.yaml')
core_schema_path = Path(__file__).with_name('core.schema.yaml')

def generate_meta_schema(output_path: Path, schema: Path): #pylint: disable=R0914
    """Generate metaschema from a combination of core schema and source schema"""

    core_schema = load(core_schema_path)

    source_schema = {}
    referenced_schema = []
    meta_schema_file_name = ""

    if schema.is_file():
        source_schema = load(schema)
        if 'References' in source_schema:
            referenced_schema = [
                load(schema_file) for schema_file in [
                    schema.with_name(f'{ref}.yaml') for ref in source_schema['References']]]
        meta_schema_file_name = f"{get_file_basename(schema, depth=2)}.meta.schema.json"

    schematypes = SchemaTypes(core_schema, source_schema)

    meta_schema = load(core_meta_schema_path)

    _replace_generated_patterns(meta_schema, schematypes)

    # Replace generated patterns from schema instance

    if source_schema:
        _populate_schema_specifics(meta_schema, source_schema)

        # Special Data Groups (gather from referenced Schema as well)
        combined_schema = source_schema.copy()
        for d in referenced_schema:
            combined_schema.update(d)
        for data_group_type in [
                key for key in combined_schema if combined_schema[key]['Object Type'] == 'Data Group Template']:
            # Data Element Attributes
            data_group = source_schema[data_group_type]
            data_group_type_name = data_group["Name"]

            for template_data_group in [
                    template_key for template_key in source_schema if data_group_type_name == combined_schema[template_key]['Object Type']]:

                _populate_template_group_rules(meta_schema["definitions"], data_group, template_data_group)
                _populate_template_group_element_rules(meta_schema["definitions"], data_group, template_data_group, schematypes)

                # Main schema
                meta_schema["patternProperties"][f"(^{template_data_group}*$)"] = {
                    "$ref": f"meta.schema.json#/definitions/{template_data_group}DataGroup"}

            meta_schema["patternProperties"][f"^{data_group_type}$"] = {
                "$ref": "meta.schema.json#/definitions/DataGroupTemplate"}

    dump(meta_schema, output_path)

    with open(output_path, 'r', encoding='utf-8') as file:
        content = file.read()
    if meta_schema_file_name:
        with open(output_path, 'w', encoding='utf-8') as file:
            file.writelines(content.replace("meta.schema.json", meta_schema_file_name))

    return schematypes


def get_types(schema: dict) -> dict:
    """For each Object Type in a schema, map a list of Objects matching that type."""

    types = {}
    for schema_object in schema:
        if schema[schema_object]["Object Type"] not in types:
            types[schema[schema_object]["Object Type"]] = []
        types[schema[schema_object]["Object Type"]].append(schema_object)
    return types
