"""
Specifics for setting up schema tables.
"""

import io
import re
from copy import deepcopy

import yaml

from .autorefs import link_mentions
from .grid_table import scoped_anchor_id, write_table


def write_header(heading, level=1, anchor=None):
    """
    - heading: string, the heading
    - level: integer, level > 0, the markdown level
    - anchor: None or string, if given, an explicit attr_list id attached to the heading (e.g.
      "rs0003:assemblycomponent"), so other content can link directly to this section regardless
      of how Markdown's own heading-slugify would have named it
    RETURN: string
    """
    anchor_suffix = f" {{: #{anchor} }}" if anchor is not None else ""
    return ("#" * level) + " " + heading + anchor_suffix + "\n\n"


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
            item["Name"] = f"`{enumerator}`"
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


_TYPE_REFERENCE_NAME = re.compile(r"(?:Group|Enumeration)\((\w+)\)")


def _style_type_predicate(predicate):
    """
    - predicate: string, a Type predicate already expanded to its spelled-out form (e.g.
      "Array(Group(LiquidComponent))")
    RETURN: string, `predicate` with everything wrapped in code spans except any Data
    Group/Enumeration name it references, which is left bare. A Markdown link can't open inside
    a code span, so leaving the name bare is what lets a later pass turn it into one (see
    autorefs.py); "Group(", "Enumeration(", "Array(", ")", etc. stay styled as code either way.
    """
    pieces = []
    last_end = 0
    for match in _TYPE_REFERENCE_NAME.finditer(predicate):
        pieces.append(f"`{predicate[last_end:match.start(1)]}`")
        pieces.append(match.group(1))
        last_end = match.end(1)
    pieces.append(f"`{predicate[last_end:]}`")
    return "".join(piece for piece in pieces if piece != "``")


def create_table_from_list(  # noqa: PLR0912, PLR0913 Too many branches, too many arguments
    columns, data_list, description=None, level=1, scope=None, reference_index=None, note=None
):
    """
    - columns: array of string, the column headers
    - data_list: array of dict with keys corresponding to columns array
    - description: None or string, if specified, adds a caption
    - level: Heading level for the description (or use 0 to make description a caption instead)
    - reference_index: None or autorefs.ReferenceIndex, if given, every attribute value is
      scanned for mentions of a known Data Group/Enumeration name and linked back to its own
      section (see autorefs.link_mentions).
    - note: None or string, if given (and `level > 0`), a line of Markdown placed right after the
      `description` heading and before the table itself -- e.g. to mark a common Data
      Group/Enumeration embedded here from elsewhere (see write_data_model).
    RETURN: string, the table in Pandoc markdown grid table format
    """
    if len(data_list) == 0:
        return ""
    second_column_name = "Attributes"
    data = {columns[0]: [], second_column_name: []}
    table_string = ""
    if description is not None and level > 0:
        anchor = scoped_anchor_id(description, scope) if scope is not None else None
        table_string += write_header(f"{description}", level, anchor=anchor)
        if note is not None:
            table_string += note + "\n\n"
    for item in data_list:
        data[columns[0]].append(item[columns[0]])
        details = ""
        for column in columns[1:]:
            for attribute in item:
                if attribute == column:
                    attribute_string = item[attribute]
                    if attribute == "Type":
                        # Each substitution expands a compact wrapper ("(X)", "[X]", "{X}",
                        # "<X>", ":X:") into its spelled-out predicate form. A Type string is also
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
                        attribute_string = re.sub(
                            r"(?<![A-Za-z]):([A-Z]([A-Z]|[a-z]|[0-9])*):", r"Reference(Group(\1))", attribute_string
                        )
                        attribute_string = _style_type_predicate(attribute_string)
                    if reference_index is not None:
                        attribute_string = link_mentions(attribute_string, reference_index, scope)
                    details += f"{attribute}:\n\n:   {attribute_string}\n\n"
        data[second_column_name].append(details[:-1])  # drop last new line
    if level == 0:
        table_string += write_table(data, [columns[0], second_column_name], description, scope=scope) + "\n\n"
    else:
        table_string += write_table(data, [columns[0], second_column_name]) + "\n\n"

    return table_string


def write_data_model(  # noqa: PLR0912, PLR0913 Too many branches, too many arguments
    instance,
    base_level=1,
    make_headers=True,
    scope=None,
    reference_index=None,
    schema=None,
    include_common=True,
    error_log=None,
):
    """
    - instance: dict, the result of loading a *.schema.yaml file (this schema's own raw content)
    - base_level:
    - make_headers: Use descriptions as section headers if True, otherwise use them as captions
    - reference_index: None or autorefs.ReferenceIndex, threaded through to create_table_from_list
    - schema: None or lattice.schema.Schema, given only when `instance`'s own Schema Meta block
      declares a "Root Data Group". When given, Enumerations/Data Groups are ordered by a
      depth-first walk from that root (diving into a Data Element's referenced Data Group before
      moving to the next Data Element) instead of raw file order, and a Data Group/Enumeration
      the walk reaches that isn't defined in `instance` itself -- e.g. a common Data Group from
      `core`, or a schema named in this schema's own Schema.References -- is pulled in and
      rendered too, marked with where it's actually defined. A locally-defined Data
      Group/Enumeration the walk never reaches is omitted, with a warning appended to
      `error_log` -- see Schema.hierarchy_order.
    - include_common: bool, when `schema` is given, whether to embed such common Data
      Groups/Enumerations (True) or omit them, as if `schema` weren't given (False) -- for a
      page that documents its common Data Groups elsewhere.
    - error_log: None or list, a warning is appended here for each locally-defined Data
      Group/Enumeration that `schema`'s hierarchy walk never reaches (only used when `schema` is
      given)
    """
    if make_headers:
        next_level = base_level + 1
    else:
        next_level = 0
    struct = load_structure_from_object(instance)
    origin_by_name = {}
    if schema is not None:
        ordered_groups, ordered_enums, orphan_groups, orphan_enums = schema.hierarchy_order()
        if not include_common:
            ordered_groups = [dg for dg in ordered_groups if dg.parent_schema is schema]
            ordered_enums = [en for en in ordered_enums if en.parent_schema is schema]
        else:
            origin_by_name = {
                item.name: _origin_phrase(item.parent_schema)
                for item in (*ordered_groups, *ordered_enums)
                if item.parent_schema is not schema
            }
        if error_log is not None:
            for orphan in (*orphan_groups, *orphan_enums):
                error_log.append(
                    f'"{orphan.name}" is defined in "{scope}" but is never referenced from its '
                    f'Root Data Group "{schema.root_data_group.name}"; omitted from the generated Data Model.'
                )
        struct["data_groups"] = data_elements_dict_from_data_groups({dg.name: dg.dictionary for dg in ordered_groups})
        struct["enumerations"] = enumerators_dict_from_enumerations({en.name: en.dictionary for en in ordered_enums})
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
                    reference_index=reference_index,
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
                    reference_index=reference_index,
                )
            )
        # Enumerations
        output_file.writelines(write_header("Enumerations", base_level))
        table_type = "enumerations"
        if len(struct[table_type]) > 0:
            for enum, enumerators in struct[table_type].items():
                output_file.writelines(
                    create_table_from_list(
                        ["Name", "Description", "Notes"],
                        enumerators,
                        description=enum,
                        level=next_level,
                        scope=scope,
                        reference_index=reference_index,
                        note=_origin_note(enum, origin_by_name),
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
                        reference_index=reference_index,
                        note=_origin_note(dg, origin_by_name),
                    )
                )
        else:
            output_file.writelines(["None.", "\n" * 2])
        output = output_file.getvalue()
    return output


def _origin_phrase(defining_schema):
    """
    - defining_schema: lattice.schema.Schema, the schema a common Data Group/Enumeration is
      actually defined in (not the one it's being embedded into; see write_data_model)
    RETURN: string, how to describe `defining_schema` in an origin note. `core` is lattice's own
      built-in library of ASHRAE Standard 232 common types -- not something a reader would look
      up by its file-level Title ("Core") -- so it's named after the standard it implements
      instead; any other reference schema (e.g. one named in a Schema.References list) is
      described generically, by its own Title.
    """
    if defining_schema.name == "core":
        return "ANSI/ASHRAE/IBPSA Standard 232"
    return f'the "{defining_schema.title}" schema'


def _origin_note(name, origin_by_name):
    """
    - name: string, a Data Group or Enumeration name
    - origin_by_name: dict, name -> the phrase describing where it's actually defined (see
      _origin_phrase), for a common Data Group/Enumeration embedded here from elsewhere (see
      write_data_model)
    RETURN: None or string, a line of Markdown marking `name` as defined elsewhere, or None if
      `name` is defined locally
    """
    origin = origin_by_name.get(name)
    return f"_Defined in {origin}._" if origin is not None else None
