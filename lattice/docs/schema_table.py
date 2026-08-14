"""
Specifics for setting up schema tables.
"""

import io
import re
from copy import deepcopy

import yaml

from .grid_table import write_table


def write_header(heading, level=1):
    """
    - heading: string, the heading
    - level: integer, level > 0, the markdown level
    RETURN: string
    """
    return ("#" * level) + " " + heading + "\n\n"


def process_string_types(string_types):
    """
    - string_types: array of dict, the string types
    RETURN: list of dict, copy of string types list with regexes handled
    properly
    """
    new_list = []
    for str_typ in string_types:
        new_item = deepcopy(str_typ)
        if "Is Regex" in new_item and new_item["Is Regex"]:
            new_item["Regular Expression Pattern"] = "(Not applicable)"
        new_item["Regular Expression Pattern"] = (
            new_item["Regular Expression Pattern"]
            .replace("*", r"\*")
            .replace(r"(?", "\n" r"(?")
            .replace(r"-[", "\n" r"-[")
        )
        new_list.append(new_item)
    return new_list


def compress_list(a_dict, key="Notes"):
    """
    - a_dict: Dict, a dictionary that may contain the key
    RETURN:
    None
    SIDE-EFFECTS:
    modifies d in place to replace the key value with a string if it is an
    array.
    """
    if key in a_dict:
        if isinstance(a_dict[key], list):
            if len(a_dict[key]) == 1:
                # Every key this is called for (Notes, Constraints, ...) accepts either a
                # bare scalar or a list per the meta-schema; a one-item list and a scalar
                # mean the same thing to the schema author, so render them the same way
                # instead of bulleting only the list form.
                a_dict[key] = a_dict[key][0]
            else:
                a_dict[key] = "\n    ".join(
                    [f"- {item}" for item in a_dict[key]]
                )  # TODO: 4 spaces for pandoc, but 3 needed for mkdocs


_KNOWN_DATA_ELEMENT_ATTRIBUTES = {
    "Name",
    "Description",
    "Type",
    "Units",
    "Constraints",
    "Required",
    "ID",
    "Notes",
    "Scalable",  # TODO: Custom from 205. Needs to be generalized.
    "Cycling Order",  # TODO: Custom from 205. Needs to be generalized.
}


def _format_custom_attribute_values(new_obj):
    """
    - new_obj: Dict, a single Data Element's attributes, mutated in place
    RETURN: None

    Renders any custom attribute (any key not among the core Data Element attributes above)
    whose value is a list or dict as a fenced YAML block. Generalizes what was previously
    hardcoded per attribute name (just "Canonical End Uses") -- any custom attribute shaped
    this way, from any project's schema, gets the same treatment automatically. Still requires
    the attribute's name to be added to the Data Groups table's own column list to be
    displayed at all; that part isn't generalized here.
    """
    for attribute, value in new_obj.items():
        if attribute in _KNOWN_DATA_ELEMENT_ATTRIBUTES:
            continue
        if isinstance(value, (list, dict)):
            new_obj[attribute] = "```\n" + yaml.dump(value, sort_keys=False) + "```"


def data_elements_dict_from_data_groups(data_groups):  # TODO: Really needs to be handled with Schema class
    """
    - data_groups: Dict, the data groups dictionary
    RETURN: Dict with data elements as an array
    """
    output = {}
    for dat_gr in data_groups:
        data_elements = []
        for element in data_groups[dat_gr]["Data Elements"]:
            new_obj = deepcopy(data_groups[dat_gr]["Data Elements"][element])
            new_obj["Name"] = f"`{element}`"
            if "Required" in new_obj:
                if isinstance(new_obj["Required"], bool):
                    if new_obj["Required"]:
                        new_obj["Required"] = "`True`" if new_obj["Required"] else ""
                    else:
                        new_obj["Required"] = ""
                else:
                    new_obj["Required"] = f"`{new_obj['Required']}`"
            new_obj["Type"] = f"`{new_obj['Type']}`"
            if "Constraints" in new_obj:
                gte = "\N{GREATER-THAN OR EQUAL TO}"
                lte = "\N{LESS-THAN OR EQUAL TO}"
                if isinstance(new_obj["Constraints"], list):
                    for i, constraint in enumerate(new_obj["Constraints"]):
                        new_obj["Constraints"][i] = f"`{constraint.replace('<=', lte).replace('>=', gte)}`"
                else:
                    new_obj["Constraints"] = f"`{new_obj['Constraints'].replace('<=', lte).replace('>=', gte)}`"
            if "Units" in new_obj:
                if new_obj["Units"] == "-":
                    new_obj["Units"] = r"\-"
                else:
                    new_obj["Units"] = new_obj["Units"].replace("-", r"·")
                    new_obj["Units"] = re.sub(r"(\d+)", r"^\1^", new_obj["Units"])
            if "Scalable" in new_obj:  # TODO: Custom from 205. Needs to be generalized.
                if isinstance(new_obj["Scalable"], bool):
                    if new_obj["Scalable"]:
                        new_obj["Scalable"] = "`True`" if new_obj["Scalable"] else ""
                    else:
                        new_obj["Scalable"] = ""
                else:
                    raise ValueError("Scalable must be a boolean value.")
            if "Cycling Order" in new_obj:  # TODO: Custom from 205. Needs to be generalized.
                new_obj["Cycling Order"] = f"`[{', '.join(new_obj['Cycling Order'])}]`"
            _format_custom_attribute_values(new_obj)
            compress_list(new_obj)
            compress_list(new_obj, key="Constraints")
            data_elements.append(new_obj)
        output[dat_gr] = data_elements
    return output


def enumerators_dict_from_enumerations(enumerations):
    """
    - enumerations: dict, the enumeration objects
    RETURN: list of dict, the enumeration objects as a list
    """
    output: dict[str, list] = {}
    for enum in enumerations:
        output[enum] = []
        for enumerator in enumerations[enum]["Enumerators"]:
            if enumerations[enum]["Enumerators"][enumerator]:
                item = deepcopy(enumerations[enum]["Enumerators"][enumerator])
            else:
                item = {}
            item["Enumerator"] = f"`{enumerator}`"
            compress_list(item)
            output[enum].append(item)
    return output


def load_structure_from_object(instance):
    """
    - instance: dictionary, the result of loading a *.schema.yaml file
    RETURN: {
        'data_types': array,
        'string_types': array,
        'enumerations': dict,
        'data_groups': dict,
    }
    """
    data_types = []
    string_types = []
    enumerations = {}
    data_groups = {}

    for obj in instance:
        object_type = instance[obj]["Object Type"]
        if object_type == "Type":
            new_obj = instance[obj]
            new_obj["Type"] = f"`{obj}`"
            new_obj["Examples"] = ", ".join(new_obj["Examples"])
            data_types.append(new_obj)
        elif object_type == "String Type":
            new_obj = instance[obj]
            new_obj["String Type"] = f"`{obj}`"
            new_obj["Examples"] = ", ".join(new_obj["Examples"])
            string_types.append(new_obj)
        elif object_type == "Enumeration":
            new_obj = instance[obj]
            compress_list(new_obj)
            enumerations[obj] = new_obj
        elif object_type == "Data Group Template":
            new_obj = instance[obj]
        elif "Data Elements" in instance[obj]:
            data_groups[obj] = instance[obj]
        elif object_type in ("Meta", "Custom Attribute", "Data Type"):
            pass  # TODO: "Data Type" objects (from core.schema.yaml) are silenced here pending a full Markdown generation overhaul
        else:
            print(f"Unknown object type: {object_type}.")
    return {
        "data_types": data_types,
        "string_types": process_string_types(string_types),
        "enumerations": enumerators_dict_from_enumerations(enumerations),
        "data_groups": data_elements_dict_from_data_groups(data_groups),
    }


def create_table_from_list(columns, data_list, description=None, level=1, scope=None):  # noqa: PLR0912 Too many branches
    """
    - columns: array of string, the column headers
    - data_list: array of dict with keys corresponding to columns array
    - description: None or string, if specified, adds a caption
    - level: Heading level for the description (or use 0 to make description a caption instead)
    RETURN: string, the table in Pandoc markdown grid table format
    """
    if len(data_list) == 0:
        return ""
    second_column_name = "Attributes"
    data = {columns[0]: [], second_column_name: []}
    table_string = ""
    if description is not None and level > 0:
        table_string += write_header(f"{description}", level)
    for item in data_list:
        data[columns[0]].append(item[columns[0]])
        details = ""
        for column in columns[1:]:
            for attribute in item:
                if attribute == column:
                    attribute_string = item[attribute]
                    if attribute == "Type":
                        # Each substitution expands a compact wrapper ("(X)", "[X]", "{X}",
                        # "<X>") into its spelled-out predicate form. A Type string is also
                        # allowed to spell the predicate out already (e.g. "Array(Timestamp)",
                        # per Standard 232 5.3.3), and the two conventions can be mixed freely.
                        # The negative lookbehind keeps this idempotent on that already-spelled
                        # form -- without it, "Array(Timestamp)" (predicate immediately
                        # preceding the bracket) doubles up into "ArrayAlternative(Timestamp)".
                        attribute_string = re.sub(r"(?<![A-Za-z])\((.*)\)", r"Alternative(\1)", attribute_string)
                        attribute_string = re.sub(r"(?<![A-Za-z])\[(.*)\]", r"Array(\1)", attribute_string)
                        attribute_string = re.sub(
                            r"(?<![A-Za-z])\{([A-Z]([A-Z]|[a-z]|[0-9])*)\}", r"Group(\1)", attribute_string
                        )
                        attribute_string = re.sub(
                            r"(?<![A-Za-z])<([A-Z]([A-Z]|[a-z]|[0-9])*)>", r"Enumeration(\1)", attribute_string
                        )
                    details += f"{attribute}:\n\n:   {attribute_string}\n\n"
        data[second_column_name].append(details[:-1])  # drop last new line
    if level == 0:
        table_string += write_table(data, [columns[0], second_column_name], description, scope=scope) + "\n\n"
    else:
        table_string += write_table(data, [columns[0], second_column_name]) + "\n\n"

    return table_string


def write_data_model(instance, base_level=1, make_headers=True, scope=None):
    """
    - instance:
    - base_level:
    - make_headers: Use descriptions as section headers if True, otherwise use them as captions
    """
    if make_headers:
        next_level = base_level + 1
    else:
        next_level = 0
    struct = load_structure_from_object(instance)
    output = None
    with io.StringIO() as output_file:
        # Data Types
        table_type = "data_types"
        if len(struct[table_type]) > 0:
            output_file.writelines(write_header("Data Types", base_level))
            output_file.writelines(
                create_table_from_list(
                    ["Type", "Description", "JSON Schema Type", "Examples"],
                    struct["data_types"],
                    level=next_level,
                    scope=scope,
                )
            )
        # String Types
        table_type = "string_types"
        if len(struct[table_type]) > 0:
            output_file.writelines(write_header("String Types", base_level))
            output_file.writelines(
                create_table_from_list(
                    ["String Type", "Description", "JSON Schema Pattern", "Examples"],
                    struct["string_types"],
                    level=next_level,
                    scope=scope,
                )
            )
        # Enumerations
        output_file.writelines(write_header("Enumerations", base_level))
        table_type = "enumerations"
        if len(struct[table_type]) > 0:
            for enum, enumerators in struct[table_type].items():
                output_file.writelines(
                    create_table_from_list(
                        ["Enumerator", "Description", "Notes"],
                        enumerators,
                        description=enum,
                        level=next_level,
                        scope=scope,
                    )
                )
        else:
            output_file.writelines(["None.", "\n" * 2])
        # Data Groups
        output_file.writelines(write_header("Data Groups", base_level))
        table_type = "data_groups"
        if len(struct[table_type]) > 0:
            for dg, data_elements in struct[table_type].items():
                output_file.writelines(
                    create_table_from_list(
                        [
                            "Name",
                            "Description",
                            "Type",
                            "Units",
                            "Constraints",
                            "Required",
                            "Scalable",  # TODO: Custom from 205. Needs to be generalized.
                            "Cycling Order",  # TODO: Custom from 205. Needs to be generalized.
                            "Canonical End Uses",  # TODO: Custom from output-reporting. Needs to be generalized.
                            "Canonical Energy Sources",  # TODO: Custom from output-reporting. Needs to be generalized.
                            "Notes",
                        ],
                        data_elements,
                        description=dg,
                        level=next_level,
                        scope=scope,
                    )
                )
        else:
            output_file.writelines(["None.", "\n" * 2])
        output = output_file.getvalue()
    return output
