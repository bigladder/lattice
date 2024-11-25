import re
from lattice.util import snake_style
from typing import Callable


def remove_prefix(text, prefix):
    return text[len(prefix) :] if text.startswith(prefix) else text


data_group_plugins: dict[str, Callable] = {}


def register_data_group_operation(data_group_template_name: str, header_entry: Callable):
    data_group_plugins[data_group_template_name] = header_entry


data_element_plugins: dict[str, Callable] = {}


def register_data_element_operation(data_group_template_name: str, header_entry: Callable):
    data_element_plugins[data_group_template_name] = header_entry


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
        self.external_reference_sources = list()
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
        tab = "\t"
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
        tab = "\t"
        entry = f"{self._level * tab}{self.type} {self.name} {self._opener}\n"
        for e in self._enumerants:
            entry += f"{(self._level + 1) * tab}{e},\n"
        entry += f"{(self._level + 1) * tab}UNKNOWN\n{self._level * tab}{self._closure}"

        # Incorporate an enum_info map into this object
        map_type = f"const static std::unordered_map<{self.name}, enum_info>"
        entry += f"\n" f"{self._level * tab}{map_type} {self.name}_info {self._opener}\n"
        for e in self._enumerants:
            display_text = self._enumerants[e].get("Display Text", e)
            description = self._enumerants[e].get("Description")
            entry += (
                f"{(self._level + 1) * tab}" f'{{{self.name}::{e}, {{"{e}", "{display_text}", "{description}"}}}},\n'
            )
        entry += f"{(self._level + 1) * tab}" f'{{{self.name}::UNKNOWN, {{"UNKNOWN", "None", "None"}}}}\n'
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
        tab = "\t"
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
                self.type = f"std::vector<{self._get_simple_type(m[0])}>"
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
        # nested_type = None
        m = re.match(enum_or_def, type_str)
        if m:
            # # Find the internal type. It might be inside nested-type syntax, but more likely
            # # is a simple definition or enumeration.
            # m_nested = re.match(r".*?\((.*)\)", m.group(2))
            # if m_nested:
            #     # Rare case of a nested specification e.g. 'ASHRAE205(RS_ID=RS0005)'
            #     internal_type = m.group(2).split("(")[0]
            #     nested_type = m_nested.group(1)
            # else:
            #     internal_type = m.group(2)
            internal_type = m.group(2)
        else:
            internal_type = type_str
        # Look through the references to assign a source to the type. 'key' is generally a
        # schema name; its value will be a list of matchable data object names
        for key in self._refs:
            if internal_type in self._refs[key]:
                self.external_reference_sources.append(f"{snake_style(key)}")
                return f"{snake_style(key)}_ns::{internal_type}"

        try:
            if "/" in type_str:
                # e.g. "Numeric/Null"
                return self._datatypes[type_str.split("/")[0]]
            else:
                return self._datatypes[type_str]
        except KeyError:
            print("Type not processed:", type_str)

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


# -------------------------------------------------------------------------------------------------
class DataIsSetElement(HeaderEntry):
    def __init__(self, name, parent):
        super().__init__(name, parent)

    @property
    def value(self):
        tab = "\t"
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
        tab = "\t"
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
        tab = "\t"
        return (
            f"{self._level * tab}{self._type_specifier } {self.type} {self.name}{self._closure}"
            "\n"
            f"{self._level * tab}void set_{self.name}({self.type} value);"
        )


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
        tab = "\t"
        return f"{self._level * tab}{' '.join([self.ret_type, self.fname])}{self.args}{self._closure}"


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

    def __init__(self, name, parent):
        super().__init__("virtual void", "initialize", "(const nlohmann::json& j)", name, parent)


# -------------------------------------------------------------------------------------------------
class VirtualDestructor(FunctionalHeaderEntry):

    def __init__(self, f_name, name, parent):
        super().__init__("virtual", f"~{f_name}", "() = default", name, parent)


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
