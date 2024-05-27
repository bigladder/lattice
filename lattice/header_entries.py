import os
import re
from .file_io import load, get_base_stem
from .util import snake_style, hyphen_separated_lowercase_style
from typing import Optional
import pathlib


def remove_prefix(text, prefix):
    return text[len(prefix) :] if text.startswith(prefix) else text


# -------------------------------------------------------------------------------------------------
class HeaderEntryFormat:
    def __init__(self, name, parent=None):
        self._opener = "{"
        self._closure = "}"


# -------------------------------------------------------------------------------------------------
class HeaderEntry:
    def __init__(self, name, parent=None):
        self.type = "namespace"
        self.name = name
        self.superclass = None
        self._opener = "{"
        self._closure = "}"
        self._parent_entry = parent
        self._child_entries = list()  # of Header_entry(s)

        if parent:
            self._parent_entry._add_child_entry(self)

    def __lt__(self, other):
        """Rich-comparison method to allow sorting.

        A Header_entry must be "less than" any another Header_entry that references it, i.e.
        you must define a value before you reference it.
        """
        return self._less_than(other)

    def _less_than(self, other):
        """ """
        lt = False
        t = f"{other.type} {other.name}"
        # \b is a "boundary" character, or specifier for a whole word
        if re.search(r"\b" + self.name + r"\b", t):
            return True
        for c in other.child_entries:
            t = f"{c.type} {c.name}"
            if re.search(r"\b" + self.name + r"\b", t):
                # Shortcut around checking siblings; if one child matches, then self < other
                return True
            else:
                # Check grandchildren
                lt = self._less_than(c)
        return lt

    def __gt__(self, other):
        return other < self

    def _add_child_entry(self, child):
        self._child_entries.append(child)

    @property
    def value(self):
        entry = self._level * "\t" + self.type + " " + self.name
        if self.superclass:
            entry += " : " + self.superclass
        entry += " " + self._opener + "\n"
        for c in self._child_entries:
            entry += c.value + "\n"
        entry += self._level * "\t" + self._closure
        return entry

    @property
    def parent(self):
        return self._parent_entry

    @property
    def child_entries(self):
        return self._child_entries

    def _get_level(self, level=0):
        if self._parent_entry:
            return self._parent_entry._get_level(level + 1)
        else:
            return level

    @property
    def _level(self):
        return self._get_level()


# -------------------------------------------------------------------------------------------------
class Typedef(HeaderEntry):
    def __init__(self, name, parent, typedef):
        super().__init__(name, parent)
        self.type = "typedef"
        self._typedef = typedef

    @property
    def value(self):
        tab = '\t'
        return f"{self._level * tab}{self.type} {self._typedef} {self.name};"


# -------------------------------------------------------------------------------------------------
class Enumeration(HeaderEntry):
    def __init__(self, name, parent, item_dict):
        super().__init__(name, parent)
        self.type = "enum class"
        self._closure = "};"
        self._enumerants: dict = item_dict

    @property
    def value(self):
        tab = '\t'
        entry = f"{self._level * tab}{self.type} {self.name} {self._opener}\n"
        for e in self._enumerants:
            entry += f"{(self._level + 1) * tab}{e},\n"
        entry += f"{(self._level + 1) * tab}UNKNOWN\n{self._level * tab}{self._closure}"

        # Incorporate an enum_info map into this object
        map_type = f"const static std::unordered_map<{self.name}, enum_info>"
        entry += (f"\n"
                  f"{self._level * tab}{map_type} {self.name}_info {self._opener}\n")
        for e in self._enumerants:
            display_text = self._enumerants[e].get("Display Text", e)
            description = self._enumerants[e].get("Description")
            entry += f"{(self._level + 1) * tab}{{{self.name}::{e}, {{\"{e}\", \"{display_text}\", \"{description}\"}}}},\n"
        entry += f"{(self._level + 1) * tab}{{{self.name}::UNKNOWN, {{\"UNKNOWN\", \"None\", \"None\"}}}}\n"
        entry += f"{self._level * tab}{self._closure}"

        return entry


# -------------------------------------------------------------------------------------------------
class EnumSerializationDeclaration(HeaderEntry):
    def __init__(self, name, parent, item_dict):
        super().__init__(name, parent)
        self.type = "NLOHMANN_JSON_SERIALIZE_ENUM"
        self._opener = "(" + name + ", {"
        self._closure = "})"
        self._enumerants: list = ["UNKNOWN"] + (list(item_dict.keys()))

    @property
    def value(self):
        entry = self._level * "\t" + self.type + " " + self._opener + "\n"
        for e in self._enumerants:
            entry += (self._level + 1) * "\t"
            mapping = "{" + self.name + "::" + e + ', "' + e + '"}'
            entry += mapping + ",\n"
        entry += self._level * "\t" + self._closure
        return entry


# -------------------------------------------------------------------------------------------------
class Struct(HeaderEntry):
    def __init__(self, name, parent, superclass=""):
        super().__init__(name, parent)
        self.type = "struct"
        self._closure = "};"
        if superclass:
            self.superclass = superclass
            self._inheritance_decl = f" : public {superclass}"


# -------------------------------------------------------------------------------------------------
class DataElement(HeaderEntry):
    def __init__(self, name, parent, element, data_types, references, find_func=None):
        super().__init__(name, parent)
        self._closure = ";"
        self._datatypes = data_types
        self._refs = references
        self._selector = dict()
        self.is_required = element.get("Required", False)

        self._create_type_entry(element, find_func)

    @property
    def value(self):
        tab = '\t'
        return f"{self._level * tab}{self.type} {self.name}{self._closure}"

    # .............................................................................................
    @property
    def selector(self):
        return self._selector

    def _create_type_entry(self, parent_dict, type_finder=None):
        """Create type node."""
        try:
            # If the type is an array, extract the surrounding [] first (using non-greedy qualifier "?")
            m = re.findall(r"\[(.*?)\]", parent_dict["Data Type"])
            if m:
                self.type = "std::vector<" + self._get_simple_type(m[0]) + ">"
            else:
                # If the type is oneOf a set
                m = re.match(r"\((.*)\)", parent_dict["Data Type"])
                if m:
                    # Choices can only be mapped to enums, so store the mapping for future use
                    # Constraints (of selection type) are of the form
                    # selection_key(ENUM_VAL_1, ENUM_VAL_2, ENUM_VAL_3)
                    # They connect pairwise with Data Type of the form ({Type_1}, {Type_2}, {Type_3})
                    oneof_selection_key = parent_dict["Constraints"].split("(")[0]
                    if type_finder:
                        selection_key_type = (
                            self._get_simple_type(
                                "".join(ch for ch in type_finder(oneof_selection_key) if ch.isalnum())
                            )
                            + "::"
                        )
                    else:
                        selection_key_type = ""
                    types = [self._get_simple_type(t.strip()) for t in m.group(1).split(",")]
                    m_opt = re.match(r".*\((.*)\)", parent_dict["Constraints"])
                    if not m_opt:
                        raise TypeError
                    selectors = [(selection_key_type + s.strip()) for s in m_opt.group(1).split(",")]

                    # the _selector dictionary would have a form like:
                    # { operation_speed_control_type : { CONTINUOUS : PerformanceMapContinuous, DISCRETE : PerformanceMapDiscrete} }
                    self._selector[oneof_selection_key] = dict(zip(selectors, types))

                    # The elements of 'types' are Data Groups that derive from a Data Group Template.
                    # The template is a verbatim "base class," which is what makes the selector
                    # polymorphism possible
                    self.type = f"std::unique_ptr<{type_finder(types[0]) if type_finder else None}>"
                else:
                    # 1. 'type' entry
                    self.type = self._get_simple_type(parent_dict["Data Type"])
        except KeyError as ke:
            pass

    def _get_simple_type(self, type_str):
        """Return the internal type described by type_str.

        First, attempt to capture enum, definition, or special string type as references;
        then default to fundamental types with simple key "type".
        """
        enum_or_def = r"(\{|\<)(.*)(\}|\>)"
        internal_type = None
        nested_type = None
        m = re.match(enum_or_def, type_str)
        if m:
            # Find the internal type. It might be inside nested-type syntax, but more likely
            # is a simple definition or enumeration.
            m_nested = re.match(r".*?\((.*)\)", m.group(2))
            if m_nested:
                # Rare case of a nested specification e.g. 'ASHRAE205(RS_ID=RS0005)'
                internal_type = m.group(2).split("(")[0]
                nested_type = m_nested.group(1)
            else:
                internal_type = m.group(2)
        else:
            internal_type = type_str
        # Look through the references to assign a source to the type. 'key' is generally a
        # schema name; its value will be a list of matchable data object names
        for key in self._refs:
            if internal_type in self._refs[key]:
                simple_type = f"{snake_style(key)}_ns::{internal_type}"
                # simple_type = internal_type
                # #
                # if key == internal_type:
                #     simple_type = f'{key}_ns::{internal_type}'
                if nested_type:
                    # e.g. 'ASHRAE205' from the composite 'ASHRAE205(RS_ID=RSXXXX)'
                    # simple_type = f'std::shared_ptr<{internal_type}>'
                    simple_type = f"{internal_type}"
                return simple_type

        try:
            if "/" in type_str:
                # e.g. "Numeric/Null"
                simple_type = self._datatypes[type_str.split("/")[0]]
            else:
                simple_type = self._datatypes[type_str]
        except KeyError:
            print("Type not processed:", type_str)
        return simple_type

    def _get_simple_minmax(self, range_str, target_dict):
        """Process Range into min and max fields."""
        if range_str is not None:
            ranges = range_str.split(",")
            minimum = None
            maximum = None
            if "type" not in target_dict:
                target_dict["type"] = None
            for r in ranges:
                try:
                    numerical_value = re.findall(r"[+-]?\d*\.?\d+|\d+", r)[0]
                    if ">" in r:
                        minimum = float(numerical_value) if "number" in target_dict["type"] else int(numerical_value)
                        mn = "exclusiveMinimum" if "=" not in r else "minimum"
                        target_dict[mn] = minimum
                    elif "<" in r:
                        maximum = float(numerical_value) if "number" in target_dict["type"] else int(numerical_value)
                        mx = "exclusiveMaximum" if "=" not in r else "maximum"
                        target_dict[mx] = maximum
                except ValueError:
                    pass


# # -------------------------------------------------------------------------------------------------
# class Lookup_struct(Header_entry):
#     '''
#     Special case struct for Lookup Variables. Its value property adds a LookupStruct declaration.

#     This class could initialize correctly by simply deriving from Struct; however, the rich-
#     comparison between Header_entry(s) only works when items being compared are not a subclass and
#     sub-subclass.
#     '''

#     def __init__(self, name, parent, superclass=''):
#         super().__init__(name, parent)
#         self.type = 'struct'
#         self._closure = '};'
#         if superclass:
#             self.superclass = superclass

#     @property
#     def value(self):
#         entry = self._level*'\t' + self.type + ' ' + self.name
#         if self.superclass:
#             entry += ' ' + self.superclass
#         entry += ' ' + self._opener + '\n'
#         for c in self._child_entries:
#             entry += (c.value + '\n')
#         entry += (self._level*'\t' + self._closure)

#         # Add a LookupStruct that offers a SOA access rather than AOS
#         entry += '\n'
#         entry += self._level*'\t' + self.type + ' ' + f'{self.name}Struct' + ' ' + self._opener + '\n'
#         for c in [ch for ch in self._child_entries if isinstance(ch, Data_element)]:
#             m = re.match(r'std::vector\<(.*)\>', c.type)
#             entry += (self._level+1)*'\t' + m.group(1) + ' ' + c.name + ';\n'
#         entry += (self._level*'\t' + self._closure)
#         return entry


# -------------------------------------------------------------------------------------------------
class DataIsSetElement(HeaderEntry):
    def __init__(self, name, parent):
        super().__init__(name, parent)

    @property
    def value(self):
        tab = '\t'
        return f"{self._level * tab}bool {self.name}_is_set;"


# -------------------------------------------------------------------------------------------------
class DataElementStaticMetainfo(HeaderEntry):
    def __init__(self, name, parent, element, meta_key):
        super().__init__(name, parent)
        self._type_specifier = "const static"
        self.type = "std::string_view"
        self.init_val = element.get(meta_key, "") if meta_key != "Name" else name
        self.name = self.name + "_" + meta_key.lower()
        self._closure = ";"

    @property
    def value(self):
        tab = '\t'
        return f"{self._level * tab}{self._type_specifier} {self.type} {self.name}{self._closure}"


# -------------------------------------------------------------------------------------------------
class InlineDependency(HeaderEntry):

    def __init__(self, name, parent, dependency_type):
        super().__init__(name, parent)
        self._type_specifier = "inline"
        self.type = dependency_type
        self._closure = ";"

    @property
    def value(self):
        tab = '\t'
        return f"{self._level * tab}{self._type_specifier } {self.type} {self.name}{self._closure}"


# -------------------------------------------------------------------------------------------------
class FunctionalHeaderEntry(HeaderEntry):
    def __init__(self, f_ret, f_name, f_args, name, parent):
        super().__init__(name, parent)
        self.fname = f_name
        self.ret_type = f_ret
        self.args = f_args
        self._closure = ";"

    @property
    def value(self):
        tab = '\t'
        return f"{self._level * tab}{' '.join([self.ret_type, self.fname, self.args])}{self._closure}"


# -------------------------------------------------------------------------------------------------
class MemberFunctionOverride(FunctionalHeaderEntry):
    def __init__(self, f_ret, f_name, f_args, name, parent):
        super().__init__(f_ret, f_name, f_args, name, parent)
        self._closure = " override;"


# -------------------------------------------------------------------------------------------------
class ObjectSerializationDeclaration(FunctionalHeaderEntry):
    def __init__(self, name, parent):
        super().__init__("void", "from_json", f"(const nlohmann::json& j, {name}& x)", name, parent)


# -------------------------------------------------------------------------------------------------
class InitializeFunction(FunctionalHeaderEntry):
    """Deprecated"""

    def __init__(self, name, parent):
        super().__init__("void", "initialize", "(const nlohmann::json& j)", name, parent)


# # -------------------------------------------------------------------------------------------------
# class Grid_var_counter_enum(Header_entry):

#     def __init__(self, name, parent, item_dict):
#         super().__init__(name, parent)
#         self.type = 'enum'
#         self._closure = '};'
#         self._enumerants = list()

#         for key in item_dict:
#             self._enumerants.append(f'{key}_index')

#     @property
#     def value(self):
#         enums = self._enumerants
#         entry = self._level*'\t' + self.type + ' ' + self.name + ' ' + self._opener + '\n'
#         for e in enums:
#             entry += (self._level + 1)*'\t'
#             entry += (e + ',\n')
#         entry += ((self._level + 1)*'\t' + 'index_count\n')
#         entry += (self._level*'\t' + self._closure)
#         return entry


# # -------------------------------------------------------------------------------------------------
# class CalculatePerformanceOverload(FunctionalHeaderEntry):
#     def __init__(self, f_ret, f_args, name, parent, n_return_values):
#         super().__init__(f_ret, "calculate_performance", "(" + ", ".join(f_args) + ")", name, parent)
#         self.args_as_list = f_args
#         self.n_return_values = n_return_values

#     @property
#     def value(self):
#         complete_decl = self._level * "\t" + "using PerformanceMapBase::calculate_performance;\n"
#         complete_decl += self._level * "\t" + " ".join([self.ret_type, self.fname, self.args]) + self._closure
#         return complete_decl


# -------------------------------------------------------------------------------------------------
class HeaderTranslator:
    def __init__(self):
        self._references = dict()
        self._fundamental_data_types = dict()
        self._preamble = list()
        self._doxynotes = "/// @note  This class has been auto-generated. Local changes will not be saved!\n"
        self._epilogue = list()
        self._data_group_types = ["Data Group"]
        self._forward_declaration_dir: Optional[pathlib.Path] = None

    def __str__(self):
        s = "\n".join([p for p in self._preamble])
        s += f"\n\n{self._doxynotes}\n{self.root.value}\n"
        s += "\n".join([e for e in self._epilogue])
        return s

    @property
    def root(self):
        return self._top_namespace

    @staticmethod
    def modified_insertion_sort(obj_list):
        """From https://stackabuse.com/sorting-algorithms-in-python/#insertionsort"""
        swapped = False
        # Start on the second element as we assume the first element is sorted
        for i in range(1, len(obj_list)):
            item_to_insert = obj_list[i]
            # And keep a reference of the index of the previous element
            j = i - 1
            # Move all items of the sorted segment forward if they are larger than the item to insert
            while j >= 0 and any(obj > item_to_insert for obj in obj_list[0 : j + 1]):
                obj_list[j + 1] = obj_list[j]
                swapped = True
                j -= 1
            # Insert the item
            obj_list[j + 1] = item_to_insert
        return swapped

    def translate(self, input_file_path, top_namespace: str, forward_declarations_path: pathlib.Path):
        """X"""
        self._source_dir = os.path.dirname(os.path.abspath(input_file_path))
        self._forward_declaration_dir = forward_declarations_path
        self._schema_name = os.path.splitext(os.path.splitext(os.path.basename(input_file_path))[0])[0]
        self._references.clear()
        self._fundamental_data_types.clear()
        self._preamble.clear()
        self._epilogue.clear()

        self._contents = load(input_file_path)

        # Load meta info first (assuming that base level tag == Schema means object type == Meta)
        self._load_meta_info(self._contents["Schema"])
        self._add_include_guard(snake_style(self._schema_name))
        self._add_standard_dependency_headers(self._contents["Schema"].get("References"))

        # Create "root" node(s)
        self._top_namespace = HeaderEntry(top_namespace)
        self._namespace = HeaderEntry(f"{snake_style(self._schema_name)}_ns", parent=self._top_namespace)

        # First, assemble typedefs
        for base_level_tag in [tag for tag in self._contents if self._contents[tag]["Object Type"] == "String Type"]:
            Typedef(base_level_tag, self._namespace, "std::string")

        # Second, enumerations
        for base_level_tag in [
            tag for tag in self._contents if self._contents[tag].get("Object Type") == "Enumeration"
        ]:
            Enumeration(base_level_tag, self._namespace, self._contents[base_level_tag]["Enumerators"])

        # Namespace-level dependencies
        InlineDependency("logger", self._namespace, "std::shared_ptr<Courier::Courier>")

        # Collect member objects and their children
        for base_level_tag in [tag for tag in self._contents if self._contents[tag].get("Object Type") == "Meta"]:
            s = Struct(base_level_tag, self._namespace)
            d = DataElementStaticMetainfo(base_level_tag.lower(), s, self._contents[base_level_tag], "Title")
            d = DataElementStaticMetainfo(base_level_tag.lower(), s, self._contents[base_level_tag], "Version")
            d = DataElementStaticMetainfo(base_level_tag.lower(), s, self._contents[base_level_tag], "Description")
        for base_level_tag in [
            tag for tag in self._contents if self._contents[tag].get("Object Type") in self._data_group_types
        ]:
            s = Struct(
                base_level_tag,
                self._namespace,
                superclass=self._contents[base_level_tag].get("Data Group Template", ""),
            )
            self._add_member_headers(s)
            # When there is a base class, add overrides:
            # self._add_function_overrides(s, self._fundamental_base_class)

            # elif self._contents[base_level_tag].get('Object Type') == 'Grid Variables':
            #     s = Struct(base_level_tag, self._namespace, superclass='GridVariablesBase')
            #     self._add_member_headers(s)
            #     self._add_function_overrides(s, 'GridVariablesBase')
            #     e = Grid_var_counter_enum('', s, self._contents[base_level_tag]['Data Elements'])
            # elif self._contents[base_level_tag].get('Object Type') == 'Lookup Variables':
            #     s = Lookup_struct(base_level_tag, self._namespace, superclass='LookupVariablesBase')
            #     self._add_member_headers(s)
            #     self._add_function_overrides(s, 'LookupVariablesBase')
            #     e = Grid_var_counter_enum('', s, self._contents[base_level_tag]['Data Elements'])
            # elif self._contents[base_level_tag].get('Object Type') == 'Performance Map':
            #     s = Struct(base_level_tag, self._namespace, superclass='PerformanceMapBase')
            #     self._add_member_headers(s)
            #     self._add_function_overrides(s, 'PerformanceMapBase')
            # else:
            #     # Catch-all for when a class of name _schema_name isn't present in the schema
            #     s = Struct(base_level_tag, self._namespace)

            for data_element in self._contents[base_level_tag]["Data Elements"]:
                d = DataElement(
                    data_element,
                    s,
                    self._contents[base_level_tag]["Data Elements"][data_element],
                    self._fundamental_data_types,
                    self._references,
                    self._search_nodes_for_datatype,
                )
                self._add_member_headers(d)
            for data_element in self._contents[base_level_tag]["Data Elements"]:
                d = DataIsSetElement(data_element, s)
            for data_element in self._contents[base_level_tag]["Data Elements"]:
                d = DataElementStaticMetainfo(
                    data_element, s, self._contents[base_level_tag]["Data Elements"][data_element], "Units"
                )
            for data_element in self._contents[base_level_tag]["Data Elements"]:
                d = DataElementStaticMetainfo(
                    data_element, s, self._contents[base_level_tag]["Data Elements"][data_element], "Description"
                )
            for data_element in self._contents[base_level_tag]["Data Elements"]:
                d = DataElementStaticMetainfo(
                    data_element, s, self._contents[base_level_tag]["Data Elements"][data_element], "Name"
                )
        HeaderTranslator.modified_insertion_sort(self._namespace.child_entries)
        # PerformanceMapBase object needs sibling grid/lookup vars to be created, so parse last
        # self._add_performance_overloads()

        # Final passes through dictionary in order to add elements related to serialization
        for base_level_tag in [
            tag for tag in self._contents if self._contents[tag].get("Object Type") == "Enumeration"
        ]:
            EnumSerializationDeclaration(base_level_tag, self._namespace, self._contents[base_level_tag]["Enumerators"])
        for base_level_tag in [
            tag for tag in self._contents if self._contents[tag].get("Object Type") in self._data_group_types
        ]:
            # from_json declarations are necessary in top container, as the header-declared
            # objects might be included and used from elsewhere.
            ObjectSerializationDeclaration(base_level_tag, self._namespace)

    # .............................................................................................
    def _load_meta_info(self, schema_section):
        """Store the global/common types and the types defined by any named references."""
        self._root_data_group = schema_section.get("Root Data Group")
        refs = {
            f"{self._schema_name}": os.path.join(self._source_dir, f"{self._schema_name}.schema.yaml"),
            "core": os.path.join(os.path.dirname(__file__), "core.schema.yaml"),
        }
        if "References" in schema_section:
            for ref in schema_section["References"]:
                refs.update({f"{ref}": os.path.join(self._source_dir, ref + ".schema.yaml")})
        if self._schema_name == "core" and self._forward_declaration_dir and self._forward_declaration_dir.is_dir():
            for file in self._forward_declaration_dir.iterdir():
                ref = get_base_stem(file)
                refs.update({ref: file})

        for ref_file in refs:
            ext_dict = load(refs[ref_file])
            self._data_group_types.extend(
                [name for name in ext_dict if ext_dict[name]["Object Type"] == "Data Group Template"]
            )
            self._references[ref_file] = [
                name for name in ext_dict if ext_dict[name]["Object Type"] in self._data_group_types + ["Enumeration"]
            ]

            cpp_types = {"integer": "int", "string": "std::string", "number": "double", "boolean": "bool"}
            for base_item in [name for name in ext_dict if ext_dict[name]["Object Type"] == "Data Type"]:
                self._fundamental_data_types[base_item] = cpp_types.get(ext_dict[base_item]["JSON Schema Type"])
            for base_item in [name for name in ext_dict if ext_dict[name]["Object Type"] == "String Type"]:
                self._fundamental_data_types[base_item] = "std::string"

    # .............................................................................................
    def _add_include_guard(self, header_name):
        s1 = f"#ifndef {header_name.upper()}_H_"
        s2 = f"#define {header_name.upper()}_H_"
        s3 = f"#endif"
        self._preamble.extend([s1, s2])
        self._epilogue.append(s3)

    # .............................................................................................
    def _add_standard_dependency_headers(self, ref_list):
        if ref_list:
            includes = ""
            for r in ref_list:
                include = f"#include <{hyphen_separated_lowercase_style(r)}.h>"
                self._preamble.append(include)
        self._preamble.extend(
            ["#include <string>",
             "#include <vector>",
             "#include <nlohmann/json.hpp>",
             "#include <enum-info.h>",
             "#include <courier/courier.h>"]
        )

    # .............................................................................................
    def _add_member_headers(self, data_element):
        if "unique_ptr" in data_element.type:
            m = re.search(r"\<(.*)\>", data_element.type)
            if m:
                include = f"#include <{hyphen_separated_lowercase_style(m.group(1))}.h>"
                if include not in self._preamble:
                    self._preamble.append(include)
        if data_element.superclass:
            include = f"#include <{hyphen_separated_lowercase_style(data_element.superclass)}.h>"
            if include not in self._preamble:
                self._preamble.append(include)

    # .............................................................................................
    def _add_function_overrides(self, parent_node, base_class_name):
        """Get base class virtual functions to be overridden."""
        base_class = os.path.join(
            os.path.dirname(__file__), "src", f"{hyphen_separated_lowercase_style(base_class_name)}.h"
        )
        try:
            with open(base_class) as b:
                for line in b:
                    if base_class_name not in line:
                        m = re.match(r"\s*virtual\s(.*)\s(.*)\((.*)\)", line)
                        if m:
                            f_ret_type = m.group(1)
                            f_name = m.group(2)
                            f_args = f"({m.group(3)})"
                            MemberFunctionOverride(f_ret_type, f_name, f_args, "", parent_node)
        except:
            pass

    # .............................................................................................
    def _add_performance_overloads(self, parent_node=None):
        """ """
        if not parent_node:
            parent_node = self.root
        for entry in parent_node.child_entries:
            if entry.parent and entry.superclass == "PerformanceMapBase":
                for lvstruct in [
                    lv
                    for lv in entry.parent.child_entries
                    if lv.superclass == "LookupVariablesBase"
                    and remove_prefix(lv.name, "LookupVariables") == remove_prefix(entry.name, "PerformanceMap")
                ]:
                    f_ret = f"{lvstruct.name}Struct"
                    n_ret = len([c for c in lvstruct.child_entries if isinstance(c, DataElement)])
                    # for each performance map, find GridVariables sibling of PerformanceMap, that has a matching name
                    for gridstruct in [
                        gridv
                        for gridv in entry.parent.child_entries
                        if gridv.superclass == "GridVariablesBase"
                        and remove_prefix(gridv.name, "GridVariables") == remove_prefix(entry.name, "PerformanceMap")
                    ]:
                        f_args = list()
                        for ce in [c for c in gridstruct.child_entries if isinstance(c, DataElement)]:
                            f_args.append(" ".join(["double", ce.name]))
                        f_args.append("Btwxt::Method performance_interpolation_method = Btwxt::Method::LINEAR")
                        CalculatePerformanceOverload(f_ret, f_args, "", entry, n_ret)
            else:
                self._add_performance_overloads(entry)

    # .............................................................................................
    def _search_nodes_for_datatype(self, data_element) -> str:
        """
        If data_element exists, return its data type; else return the data group's 'data type,' which
        is the Data Group Template. Hacky overload.
        """
        for listing in self._contents:
            if "Data Elements" in self._contents[listing]:
                if "Data Group Template" in self._contents[listing] and listing in data_element:
                    return self._contents[listing]["Data Group Template"]

                for element in self._contents[listing]["Data Elements"]:
                    if element == data_element and "Data Type" in self._contents[listing]["Data Elements"][element]:
                        return self._contents[listing]["Data Elements"][element]["Data Type"]
        return "Template"  # Placeholder base class
