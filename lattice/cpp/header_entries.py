from __future__ import annotations
import re
import logging
from lattice.util import snake_style
from typing import Callable, Optional
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger()


def remove_prefix(text, prefix):
    return text[len(prefix) :] if text.startswith(prefix) else text


data_group_extensions: dict[str, Callable] = {}


def register_data_group_operation(data_group_template_name: str, header_entry: Callable):
    data_group_extensions[data_group_template_name] = header_entry


data_element_extensions: dict[str, Callable] = {}


def register_data_element_operation(data_group_template_name: str, header_entry: Callable):
    data_element_extensions[data_group_template_name] = header_entry


# -------------------------------------------------------------------------------------------------
@dataclass()
class EntryFormat:
    _opener: str = field(init=False, default="{")
    _closure: str = field(init=False, default="}")
    _level: int = field(init=False, default=0)
    _indent: str = field(init=False, default="")

    def trace(self):
        logger.debug(type(self).__name__)
        logger.debug(self.__str__())


# -------------------------------------------------------------------------------------------------
@dataclass
class HeaderEntry(EntryFormat):
    name: str
    parent: Optional[HeaderEntry]
    type: str = field(init=False, default="namespace")  # TODO: kw_only=True?
    child_entries: list[HeaderEntry] = field(init=False, default_factory=list)

    def __post_init__(self):
        if self.parent:
            self.parent._add_child_entry(self)
        self._level = self._get_level()
        self._indent = self._level * "\t"

    def _add_child_entry(self, child: HeaderEntry) -> None:
        self.child_entries.append(child)

    def _get_level(self, level: int = 0) -> int:
        if self.parent:
            return self.parent._get_level(level + 1)
        else:
            return level

    def __lt__(self, other):
        """
        A Header_entry must be "less than" any another Header_entry that references it, i.e.
        you must define a C++ value before you reference it.
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

    def __str__(self):
        tab = "\t"
        entry = f"{self._indent}{self.type} {self.name} {self._opener}\n"
        entry += "\n".join([str(c) for c in self.child_entries])
        entry += f"\n{self._indent}{self._closure}"
        return entry


# -------------------------------------------------------------------------------------------------
@dataclass
class Typedef(HeaderEntry):
    _typedef: str

    def __post_init__(self):
        super().__post_init__()
        self.type = "typedef"
        self.trace()

    def __str__(self):
        tab = "\t"
        return f"{self._indent}{self.type} {self._typedef} {self.name};"


# -------------------------------------------------------------------------------------------------
@dataclass
class Enumeration(HeaderEntry):
    _enumerants: dict

    def __post_init__(self):
        super().__post_init__()
        self.type = "enum class"
        self._closure = "};"
        self.trace()

    def __str__(self):
        tab = "\t"
        entry = f"{self._indent}{self.type} {self.name} {self._opener}\n"
        for e in self._enumerants:
            entry += f"{self._indent}\t{e},\n"
        entry += f"{self._indent}\tUNKNOWN\n{self._indent}{self._closure}"

        # Incorporate an enum_info map into this object
        map_type = f"const static std::unordered_map<{self.name}, enum_info>"
        entry += f"\n" f"{self._indent}{map_type} {self.name}_info {self._opener}\n"
        for e in self._enumerants:
            display_text = self._enumerants[e].get("Display Text", e)
            description = self._enumerants[e].get("Description")
            entry += f"{self._indent}\t" f'{{{self.name}::{e}, {{"{e}", "{display_text}", "{description}"}}}},\n'
        entry += f"{self._indent}\t" f'{{{self.name}::UNKNOWN, {{"UNKNOWN", "None", "None"}}}}\n'
        entry += f"{self._indent}{self._closure}"

        return entry


# -------------------------------------------------------------------------------------------------
@dataclass
class EnumSerializationDeclaration(HeaderEntry):
    """Provides shortcut marcros that populate an enumeration from json."""

    _enumerants: dict

    def __post_init__(self):
        super().__post_init__()
        self.type = "NLOHMANN_JSON_SERIALIZE_ENUM"
        self._opener = "(" + self.name + ", {"
        self._closure = "})"
        self.trace()

    def __str__(self):
        enums_with_placeholder = ["UNKNOWN"] + (list(self._enumerants.keys()))
        tab = "\t"
        entry = f"{self._indent}{self.type} {self._opener}\n"
        entry += ",\n".join([f'{self._indent}\t{{{self.name}::{e}, "{e}"}}' for e in enums_with_placeholder])
        # for e in enums_with_placeholder:
        #     entry += (self._level + 1) * "\t"
        #     mapping = "{" + self.name + "::" + e + ', "' + e + '"}'
        #     entry += mapping + ",\n"
        entry += f"\n{self._indent}{self._closure}"
        return entry


# -------------------------------------------------------------------------------------------------
@dataclass
class Struct(HeaderEntry):
    superclass: str = ""

    def __post_init__(self):
        super().__post_init__()
        self.type = "struct"
        self._closure = "};"
        self.trace()

    def __str__(self):
        tab = "\t"
        entry = f"{self._indent}{self.type} {self.name}"
        if self.superclass:
            entry += f" : {self.superclass}"
        entry += f" {self._opener}\n"
        entry += "\n".join([str(c) for c in self.child_entries])
        entry += f"\n{self._indent}{self._closure}"
        return entry


# -------------------------------------------------------------------------------------------------
@dataclass
class DataElement(HeaderEntry):
    _element_attributes: dict
    _pod_datatypes_map: dict[str, str]
    _custom_datatypes_by_location: dict[str, list[str]]
    _type_finder: Callable | None = None
    selector: dict[str, dict[str, str]] = field(init=False, default_factory=dict)

    def __post_init__(self):
        super().__post_init__()
        self._closure = ";"
        self.is_required: bool = self._element_attributes.get("Required", False)  # used externally
        self.scoped_innertype: tuple[str, str] = ("", "")
        # self.external_reference_sources: list = []

        self._create_type_entry(self._element_attributes, self._type_finder)
        self.trace()

    def __str__(self):
        tab = "\t"
        return f"{self._indent}{self.type} {self.name}{self._closure}"

    def _create_type_entry(self, element_attributes: dict, type_finder: Callable | None = None) -> None:
        """Create type node."""
        try:
            # If the type is an array, extract the surrounding [] first (using non-greedy qualifier "?")
            m = re.findall(r"\[(.*?)\]", element_attributes["Data Type"])
            if m:
                self.type = f"std::vector<{self._get_scoped_inner_type(m[0])}>"
            else:
                # If the type is oneOf a set
                m = re.match(r"\((?P<comma_separated_selection_types>.*)\)", element_attributes["Data Type"])
                if m:
                    # Choices can only be mapped to enums, so store the mapping for future use
                    # Constraints (of selection type) are of the form
                    # selection_key(ENUM_VAL_1, ENUM_VAL_2, ENUM_VAL_3)
                    # They connect pairwise with Data Type of the form ({Type_1}, {Type_2}, {Type_3})
                    oneof_selection_key = element_attributes["Constraints"].split("(")[0]
                    if type_finder:
                        selection_key_type = (
                            self._get_scoped_inner_type(
                                "".join(ch for ch in type_finder(oneof_selection_key) if ch.isalnum())
                            )
                            + "::"
                        )
                    else:
                        selection_key_type = ""
                    selection_types = [
                        self._get_scoped_inner_type(t.strip())
                        for t in m.group("comma_separated_selection_types").split(",")
                    ]
                    m_opt = re.match(r".*\((?P<comma_separated_constraints>.*)\)", element_attributes["Constraints"])
                    if not m_opt:
                        raise TypeError
                    constraints = [
                        (selection_key_type + s.strip()) for s in m_opt.group("comma_separated_constraints").split(",")
                    ]

                    # the _selector dictionary would have a form like:
                    # { operation_speed_control_type : { CONTINUOUS : PerformanceMapContinuous, DISCRETE : PerformanceMapDiscrete} }
                    self.selector[oneof_selection_key] = dict(zip(constraints, selection_types))

                    # The elements of 'types' are Data Groups that derive from a Data Group Template.
                    # The template is a verbatim "base class," which is what makes the selector
                    # polymorphism possible
                    self.type = f"std::unique_ptr<{type_finder(selection_types[0]) if type_finder else None}>"
                else:
                    # 1. 'type' entry
                    self.type = self._get_scoped_inner_type(element_attributes["Data Type"])
        except KeyError as ke:
            pass

    def _get_scoped_inner_type(self, type_str: str) -> str:
        """Return the scoped cpp type described by type_str.

        First, attempt to capture enum, definition, or special string type as references;
        then default to fundamental types with simple key "type".
        """
        enum_or_def = r"(\{|\<)(?P<inner_type>.*)(\}|\>)"
        inner_type: str = ""
        m = re.match(enum_or_def, type_str)
        if m:
            inner_type = m.group("inner_type")
        else:
            inner_type = type_str
        # Look through the references to assign a scope to the type. 'location' is generally a
        # schema name; its value will be a list of matchable data object names
        for location in self._custom_datatypes_by_location:
            if inner_type in self._custom_datatypes_by_location[location]:
                self.scoped_innertype = (f"{snake_style(location)}", inner_type)
                return "_ns::".join(self.scoped_innertype)
        try:
            # e.g. "Numeric/Null" or "Numeric" both ok
            self.scoped_innertype = ("", self._pod_datatypes_map[type_str.split("/")[0]])
            return self.scoped_innertype[1]
        except KeyError:
            print("Type not processed:", type_str)
        return f"Type not processed: {type_str}"

    def _get_simple_minmax(self, range_str, target_dict) -> None:
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
@dataclass
class DataElementIsSetFlag(HeaderEntry):

    def __str__(self):
        tab = "\t"
        return f"{self._indent}bool {self.name}_is_set;"


# -------------------------------------------------------------------------------------------------
@dataclass
class DataElementStaticMetainfo(HeaderEntry):
    element: dict
    metainfo_key: str

    def __post_init__(self):
        super().__post_init__()
        self._type_specifier = "const static"
        self.type = "std::string_view"
        self.init_val = self.element.get(self.metainfo_key, "") if self.metainfo_key != "Name" else self.name
        self.name = self.name + "_" + self.metainfo_key.lower()
        self._closure = ";"

        self.trace()

    def __str__(self):
        tab = "\t"
        return f"{self._indent}{self._type_specifier} {self.type} {self.name}{self._closure}"


# -------------------------------------------------------------------------------------------------
@dataclass
class InlineDependency(HeaderEntry):
    type: str  # HeaderEntry does not initialize this in __init__, but InlineDependency will

    def __post_init__(self):
        super().__post_init__()
        self._type_specifier = "inline"
        self._closure = ";"
        self.trace()

    def __str__(self):
        tab = "\t"
        return (
            f"{self._indent}{self._type_specifier} {self.type} {self.name}{self._closure}"
            "\n"
            f"{self._indent}void set_{self.name}({self.type} value);"
        )


# -------------------------------------------------------------------------------------------------
@dataclass
class FunctionalHeaderEntry(HeaderEntry):
    _f_ret: str
    _f_name: str
    _f_args: list[str]

    def __post_init__(self):
        super().__post_init__()
        self.args = f"({', '.join(self._f_args)})"
        self._closure = ";"
        self.trace()

    def __str__(self):
        tab = "\t"
        return f"{self._indent}{' '.join([self._f_ret, self._f_name])}{self.args}{self._closure}"


# -------------------------------------------------------------------------------------------------
@dataclass
class MemberFunctionOverrideDeclaration(FunctionalHeaderEntry):
    def __post_init__(self):
        super().__post_init__()
        self._closure = " override;"
        self.trace()


# -------------------------------------------------------------------------------------------------
@dataclass
class ObjectSerializationDeclaration(FunctionalHeaderEntry):
    _f_ret: str = field(init=False)
    _f_name: str = field(init=False)
    _f_args: list[str] = field(init=False)

    def __post_init__(self):
        self._f_ret = "void"
        self._f_name = "from_json"
        self._f_args = ["const nlohmann::json& j", f"{self.name}& x"]
        super().__post_init__()
        self.trace()


# -------------------------------------------------------------------------------------------------
@dataclass
class VirtualDestructor(FunctionalHeaderEntry):
    _explicit_definition: Optional[str] = None

    def __post_init__(self):
        self._closure = f" = {self._explicit_definition};" if self._explicit_definition else ";"
        self._f_ret = "virtual"
        self._f_name = f"~{self._f_name}"
        self._f_args = []
        super().__post_init__()
        self.trace()


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
