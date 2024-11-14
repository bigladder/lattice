import os
import json
import posixpath
import jsonschema
import yaml
import copy

from .file_io import load, dump, get_file_basename
from .schema import SchemaPatterns


class MetaSchema:
    def __init__(self, schema_path):
        with open(schema_path) as meta_schema_file:
            uri_path = os.path.abspath(os.path.dirname(schema_path))
            if os.sep != posixpath.sep:
                uri_path = posixpath.sep + uri_path

            resolver = jsonschema.RefResolver(f"file://{uri_path}/", meta_schema_file)
            self.validator = jsonschema.Draft7Validator(json.load(meta_schema_file), resolver=resolver)

    def validate(self, instance_path):
        instance = load(instance_path)
        errors = sorted(self.validator.iter_errors(instance), key=lambda e: e.path)
        file_name = os.path.basename(instance_path)
        if len(errors) == 0:
            print(f"Validation successful for {file_name}")
        else:
            messages = []
            for error in errors:
                messages.append(f"{error.message} ({'.'.join([str(x) for x in error.path])})")
            messages = [f"{i}. {message}" for i, message in enumerate(messages, start=1)]
            message_str = "\n  ".join(messages)
            raise Exception(f"Validation failed for {file_name} with {len(messages)} errors:\n  {message_str}")


def meta_validate_file(file_path, meta_schema_path):
    meta_schema = MetaSchema(meta_schema_path)
    meta_schema.validate(file_path)


# Generate Meta Schema

core_meta_schema_path = os.path.join(os.path.dirname(__file__), "meta.schema.yaml")


def generate_meta_schema(output_path, schema=None):
    """ """
    referenced_schema = []
    if schema is not None:
        source_schema = load(schema)  # TODO: Replace with Schema class
        schema_dir = os.path.dirname(schema)
        if "References" in source_schema["Schema"]:
            referenced_schema = [
                load(schema_file)
                for schema_file in [
                    os.path.join(schema_dir, f"{ref}.schema.yaml") for ref in source_schema["Schema"]["References"]
                ]
            ]
        meta_schema_file_name = f"{get_file_basename(schema, depth=2)}.meta.schema.json"
    else:
        source_schema = None

    schema_patterns = SchemaPatterns(source_schema)

    meta_schema = load(core_meta_schema_path)

    # Replace generated patterns from core schema analysis

    meta_schema["definitions"]["Meta"]["properties"]["Unit Systems"]["patternProperties"][
        schema_patterns.type_base_names.anchored()
    ] = meta_schema["definitions"]["Meta"]["properties"]["Unit Systems"]["patternProperties"].pop("**GENERATED**")
    meta_schema["definitions"]["DataGroupTemplate"]["properties"]["Required Data Elements"]["patternProperties"][
        schema_patterns.data_element_names.anchored()
    ] = meta_schema["definitions"]["DataGroupTemplate"]["properties"]["Required Data Elements"][
        "patternProperties"
    ].pop(
        "**GENERATED**"
    )
    meta_schema["definitions"]["ConstraintsPattern"]["pattern"] = schema_patterns.constraints.anchored()
    meta_schema["definitions"]["Required"]["oneOf"][1]["pattern"] = schema_patterns.conditional_requirements.anchored()
    meta_schema["definitions"]["Enumerator"]["patternProperties"][schema_patterns.enumerator.anchored()] = meta_schema[
        "definitions"
    ]["Enumerator"]["patternProperties"].pop("**GENERATED**")
    meta_schema["definitions"]["DataTypePattern"]["pattern"] = schema_patterns.data_types.anchored()
    meta_schema["definitions"]["DataGroup"]["properties"]["Data Elements"]["patternProperties"][
        schema_patterns.data_element_names.anchored()
    ] = meta_schema["definitions"]["DataGroup"]["properties"]["Data Elements"]["patternProperties"].pop("**GENERATED**")
    meta_schema["patternProperties"][schema_patterns.type_base_names.anchored()] = meta_schema["patternProperties"].pop(
        "**GENERATED**"
    )

    # Replace generated patterns from schema instance

    if source_schema:
        if "Schema" in source_schema:
            if "Title" in source_schema["Schema"]:
                meta_schema["title"] = f"{source_schema['Schema']['Title']} Meta-schema"
            # Special Unit Systems
            if "Unit Systems" in source_schema["Schema"]:
                # Unit system definitions
                for unit_system in source_schema["Schema"]["Unit Systems"]:
                    meta_schema["definitions"][unit_system] = {
                        "type": "string",
                        "enum": source_schema["Schema"]["Unit Systems"][unit_system],
                    }
                    meta_schema["definitions"]["DataElementAttributes"]["properties"]["Units"]["anyOf"].append(
                        {"$ref": f"meta.schema.json#/definitions/{unit_system}"}
                    )
        # Data Group Templates (gather from referenced Schema as well)
        data_group_templates = {}
        for template_name in [t for t in source_schema if source_schema[t]["Object Type"] == "Data Group Template"]:
            data_group_templates[template_name] = source_schema[template_name]

        for ref in referenced_schema:
            for template_name in [t for t in ref if ref[t]["Object Type"] == "Data Group Template"]:
                data_group_templates[template_name] = ref[template_name]

        if len(data_group_templates) > 0:
            meta_schema["definitions"]["DataGroup"]["properties"]["Data Group Template"]["enum"] = list(
                data_group_templates.keys()
            )
        else:
            # If no Data Group Templates are defined, Data Groups should not define that property
            meta_schema["definitions"]["DataGroup"]["properties"].pop("Data Group Template")

        # Data Groups based on Data Group Templates still have to match the normal Data Group pattern
        meta_schema["patternProperties"][schema_patterns.type_base_names.anchored()]["allOf"].append(
            {
                "if": {"properties": {"Object Type": {"const": "Data Group"}, "Data Group Template": True}},
                "then": {"$ref": f"meta.schema.json#/definitions/DataGroup"},
            }
        )

        for data_group_template_name in data_group_templates:
            data_group_template = data_group_templates[data_group_template_name]
            meta_schema["definitions"][f"{data_group_template_name}DataElementAttributes"] = copy.deepcopy(
                meta_schema["definitions"]["DataElementAttributes"]
            )

            if "Unit System" in data_group_template:
                meta_schema["definitions"][f"{data_group_template_name}DataElementAttributes"]["properties"][
                    "Units"
                ] = {"$ref": f"meta.schema.json#/definitions/{data_group_template['Unit System']}"}

            if "Required Data Types" in data_group_template:
                meta_schema["definitions"][f"{data_group_template_name}DataElementAttributes"]["properties"][
                    "Data Type"
                ] = {"type": "string", "enum": data_group_template["Required Data Types"]}

            if "Data Elements Required" in data_group_template:
                meta_schema["definitions"][f"{data_group_template_name}DataElementAttributes"]["properties"][
                    "Required"
                ]["const"] = data_group_template["Data Elements Required"]

            # Data Group
            meta_schema["definitions"][f"{data_group_template_name}DataGroup"] = copy.deepcopy(
                meta_schema["definitions"]["DataGroup"]
            )

            meta_schema["definitions"][f"{data_group_template_name}DataGroup"]["properties"]["Data Group Template"][
                "enum"
            ] = [data_group_template_name]

            if "Required Data Elements" in data_group_template:
                required_names = []
                meta_schema["definitions"][f"{data_group_template_name}DataGroup"]["properties"]["Data Elements"][
                    "properties"
                ] = {}
                for data_element_name in data_group_template["Required Data Elements"]:
                    required_names.append(data_element_name)
                    data_element = data_group_template["Required Data Elements"][data_element_name]
                    meta_schema["definitions"][
                        f"{data_group_template_name}-{data_element_name}-DataElementAttributes"
                    ] = copy.deepcopy(meta_schema["definitions"][f"{data_group_template_name}DataElementAttributes"])
                    meta_schema["definitions"][f"{data_group_template_name}DataGroup"]["properties"]["Data Elements"][
                        "properties"
                    ][data_element_name] = copy.deepcopy(
                        meta_schema["definitions"][f"{data_group_template_name}DataGroup"]["properties"][
                            "Data Elements"
                        ]["patternProperties"][schema_patterns.data_element_names.anchored()]
                    )
                    meta_schema["definitions"][f"{data_group_template_name}DataGroup"]["properties"]["Data Elements"][
                        "properties"
                    ][data_element_name][
                        "$ref"
                    ] = f"meta.schema.json#/definitions/{data_group_template_name}-{data_element_name}-DataElementAttributes"
                    for attribute in data_element:
                        meta_schema["definitions"][
                            f"{data_group_template_name}-{data_element_name}-DataElementAttributes"
                        ]["properties"][attribute]["const"] = data_element[attribute]
                        if (
                            attribute
                            not in meta_schema["definitions"][f"{data_group_template_name}DataGroup"]["properties"][
                                "Data Elements"
                            ]["properties"][data_element_name]["required"]
                        ):
                            meta_schema["definitions"][f"{data_group_template_name}DataGroup"]["properties"][
                                "Data Elements"
                            ]["properties"][data_element_name]["required"].append(attribute)
                meta_schema["definitions"][f"{data_group_template_name}DataGroup"]["properties"]["Data Elements"][
                    "required"
                ] = required_names
                exclusive_element_names_anchored = (
                    f"(?!^({'|'.join(required_names)})$)(^{schema_patterns.data_element_names}$)"
                )
                meta_schema["definitions"][f"{data_group_template_name}DataGroup"]["properties"]["Data Elements"][
                    "patternProperties"
                ][exclusive_element_names_anchored] = meta_schema["definitions"][
                    f"{data_group_template_name}DataGroup"
                ][
                    "properties"
                ][
                    "Data Elements"
                ][
                    "patternProperties"
                ].pop(
                    schema_patterns.data_element_names.anchored()
                )
                meta_schema["definitions"][f"{data_group_template_name}DataGroup"]["properties"]["Data Elements"][
                    "patternProperties"
                ][exclusive_element_names_anchored][
                    "$ref"
                ] = f"meta.schema.json#/definitions/{data_group_template_name}DataElementAttributes"
            else:
                meta_schema["definitions"][f"{data_group_template_name}DataGroup"]["properties"]["Data Elements"][
                    "patternProperties"
                ][schema_patterns.data_element_names.anchored()][
                    "$ref"
                ] = f"meta.schema.json#/definitions/{data_group_template_name}DataElementAttributes"

            meta_schema["patternProperties"][schema_patterns.type_base_names.anchored()]["allOf"].append(
                {
                    "if": {
                        "properties": {
                            "Object Type": {"const": "Data Group"},
                            "Data Group Template": {"const": data_group_template_name},
                        },
                        "required": ["Data Group Template"],
                    },
                    "then": {"$ref": f"meta.schema.json#/definitions/{data_group_template_name}DataGroup"},
                }
            )

    dump(meta_schema, output_path)

    with open(output_path, "r") as file:
        content = file.read()
    with open(output_path, "w") as file:
        file.writelines(content.replace("meta.schema.json", meta_schema_file_name))

    return schema_patterns
