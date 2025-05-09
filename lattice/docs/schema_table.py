"""
Specifics for setting up schema tables.
"""

from copy import deepcopy
import io
import re

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


def compress_notes(a_dict):
    """
    - a_dict: Dict, a dictionary that may contain the key, 'Notes"
    RETURN:
    None
    SIDE-EFFECTS:
    modifies d in place to replace the "Notes" value with a string if it is an
    array.
    """
    notes = "Notes"
    if notes in a_dict:
        if isinstance(a_dict[notes], list):
            a_dict[notes] = "\n   ".join([f"- {note}" for note in a_dict[notes]])


def data_elements_dict_from_data_groups(data_groups):
    """
    - data_groups: Dict, the data groups dictionary
    RETURN: Dict with data elements as an array
    """
    output = {}
    for dat_gr in data_groups:
        data_elements = []
        for element in data_groups[dat_gr]["Data Elements"]:
            new_obj = data_groups[dat_gr]["Data Elements"][element]
            new_obj["Name"] = f"`{element}`"
            if "Required" in new_obj:
                if isinstance(new_obj["Required"], bool):
                    if new_obj["Required"]:
                        check = "\N{CHECK MARK}"
                        new_obj["Req"] = f"{check}" if new_obj["Required"] else ""
                    else:
                        new_obj["Req"] = ""
                else:
                    new_obj["Req"] = f"`{new_obj['Required']}`"
                    new_obj.pop("Required")
            new_obj["Data Type"] = f"`{new_obj['Data Type']}`"
            if "Constraints" in new_obj:
                gte = "\N{GREATER-THAN OR EQUAL TO}"
                lte = "\N{LESS-THAN OR EQUAL TO}"
                if isinstance(new_obj["Constraints"], list):
                    new_obj["Constraints"] = ", ".join(new_obj["Constraints"])
                new_obj["Constraints"] = f"`{new_obj['Constraints'].replace('<=', lte).replace('>=', gte)}`"
            if "Units" in new_obj:
                if new_obj["Units"] == "-":
                    new_obj["Units"] = r"\-"
                else:
                    new_obj["Units"] = new_obj["Units"].replace("-", r"·")
                    new_obj["Units"] = re.sub(r"(\d+)", r"^\1^", new_obj["Units"])
            compress_notes(new_obj)
            data_elements.append(new_obj)
        output[dat_gr] = data_elements
    return output


def enumerators_dict_from_enumerations(enumerations):
    """
    - enumerations: dict, the enumeration objects
    RETURN: list of dict, the enumeration objects as a list
    """
    output = {}
    for enum in enumerations:
        output[enum] = []
        for enumerator in enumerations[enum]["Enumerators"]:
            if enumerations[enum]["Enumerators"][enumerator]:
                item = deepcopy(enumerations[enum]["Enumerators"][enumerator])
            else:
                item = {}
            item["Enumerator"] = f"`{enumerator}`"
            compress_notes(item)
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
        if object_type == "Data Type":
            new_obj = instance[obj]
            new_obj["Data Type"] = f"`{obj}`"
            new_obj["Examples"] = ", ".join(new_obj["Examples"])
            data_types.append(new_obj)
        elif object_type == "String Type":
            new_obj = instance[obj]
            new_obj["String Type"] = f"`{obj}`"
            new_obj["Examples"] = ", ".join(new_obj["Examples"])
            string_types.append(new_obj)
        elif object_type == "Enumeration":
            new_obj = instance[obj]
            compress_notes(new_obj)
            enumerations[obj] = new_obj
        elif object_type == "Data Group Template":
            new_obj = instance[obj]
        elif "Data Elements" in instance[obj]:
            data_groups[obj] = instance[obj]
        elif object_type == "Meta":
            pass
        else:
            print(f"Unknown object type: {object_type}.")
    return {
        "data_types": data_types,
        "string_types": process_string_types(string_types),
        "enumerations": enumerators_dict_from_enumerations(enumerations),
        "data_groups": data_elements_dict_from_data_groups(data_groups),
    }


def create_table_from_list(columns, data_list, description=None, style="2 Columns", level=1):
    """
    - columns: array of string, the column headers
    - data_list: array of dict with keys corresponding to columns array
    - description: None or string, if specified, adds a caption
    - caption: None or string, if specified, adds a caption
    RETURN: string, the table in Pandoc markdown grid table format
    """
    if len(data_list) == 0:
        return ""
    if style == "Table":
        data = {col: [] for col in columns}
        for col in columns:
            data[col] = []
            for item in data_list:
                if col in item:
                    data[col].append(item[col])
                else:
                    data[col].append("")
        table_string = write_table(data, columns, description) + "\n\n"
    if style == "Descriptions":
        table_string = write_header(f"{description} {{-}}", level)
        for item in data_list:
            table_string += write_header(f"{item[columns[0]]} {{-}}", level + 1) + "\n"
            for attribute in item:
                if attribute != columns[0]:
                    table_string += f"> {attribute}:\n>\n>   ~ {item[attribute]}\n>\n"
            table_string += "\n"
    if style == "2 Columns":
        second_column_name = "Attributes"
        data = {columns[0]: [], second_column_name: []}
        table_string = write_header(f"{description}", level)
        for item in data_list:
            data[columns[0]].append(item[columns[0]])
            details = ""
            for column in columns[1:]:
                for attribute in item:
                    if attribute == column:
                        details += f"**{attribute}:**\n\n:   {item[attribute]}\n\n"
            data[second_column_name].append(details[:-1])  # drop last new line
        table_string += write_table(data, [columns[0], second_column_name]) + "\n\n"

    return table_string


def write_data_model(instance, base_level=1, style="2 Columns"):
    """
    - instance:
    - make_headers:
    - base_level:
    """
    struct = load_structure_from_object(instance)
    output = None
    with io.StringIO() as output_file:
        # Data Types
        table_type = "data_types"
        if len(struct[table_type]) > 0:
            output_file.writelines(write_header("Data Types", base_level))
            output_file.writelines(
                create_table_from_list(
                    ["Data Type", "Description", "JSON Schema Type", "Examples"],
                    struct["data_types"],
                    level=base_level + 1,
                    style=style,
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
                    level=base_level + 1,
                    style=style,
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
                        level=base_level + 1,
                        style=style,
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
                        ["Name", "Description", "Data Type", "Units", "Constraints", "Req", "Scalable", "Notes"],
                        data_elements,
                        description=dg,
                        level=base_level + 1,
                        style=style,
                    )
                )
        else:
            output_file.writelines(["None.", "\n" * 2])
        output = output_file.getvalue()
    return output
