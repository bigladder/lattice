from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional, Union

logger = logging.getLogger()


def remove_prefix(text, prefix):
    return text[len(prefix) :] if text.startswith(prefix) else text


@dataclass
class ReferencedDataType:
    name: str
    namespace: str
    superclass_name: Union[str, None] = None


@dataclass()
class EntryFormat:
    _opener: str = field(init=False, default="{")
    _closure: str = field(init=False, default="}")
    _level: int = field(init=False, default=0)
    _indent: str = field(init=False, default="")

    def trace(self):
        logger.debug(type(self).__name__)
        logger.debug(self.__str__())


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
        return self._less_than(self, other)

    @staticmethod
    def _less_than(this: HeaderEntry | FunctionalHeaderEntry, other: HeaderEntry | FunctionalHeaderEntry):
        """ """
        lt = False
        t = f"{other._f_ret} {other.args}" if isinstance(other, FunctionalHeaderEntry) else f"{other.type} {other.name}"
        # \b is a "boundary" character, or specifier for a whole word
        if re.search(r"\b" + this.name + r"\b", t):
            return True
        for c in other.child_entries:
            t = f"{c._f_ret} {c.args}" if isinstance(c, FunctionalHeaderEntry) else f"{c.type} {c.name}"
            if re.search(r"\b" + this.name + r"\b", t):
                # Shortcut around checking siblings; if one child matches, then self < other
                return True
            else:
                # Check grandchildren
                lt = HeaderEntry._less_than(this, c)
        return lt

    def __str__(self):
        entry = f"{self._indent}{self.type} {self.name} {self._opener}\n"
        entry += "\n".join([str(c) for c in self.child_entries])
        entry += f"\n{self._indent}{self._closure}"
        return entry


@dataclass
class Typedef(HeaderEntry):
    _typedef: str

    def __post_init__(self):
        super().__post_init__()
        self.type = "typedef"
        self.trace()

    def __str__(self):
        return f"{self._indent}{self.type} {self._typedef} {self.name};"


@dataclass
class Enumeration(HeaderEntry):
    _enumerants: dict

    def __post_init__(self):
        super().__post_init__()
        self.type = "enum class"
        self._closure = "};"
        self.trace()

    def __str__(self):
        entry = f"{self._indent}{self.type} {self.name} {self._opener}\n"
        for e in self._enumerants:
            entry += f"{self._indent}\t{e},\n"
        entry += f"{self._indent}\tUNKNOWN\n{self._indent}{self._closure}"

        # Incorporate an enum_info map into this object
        map_type = f"const static std::unordered_map<{self.name}, enum_info>"
        entry += f"\n{self._indent}{map_type} {self.name}_info {self._opener}\n"
        for e in self._enumerants:
            display_text = self._enumerants[e].get("Display Text", e)
            description = self._enumerants[e].get("Description")
            entry += f'{self._indent}\t{{{self.name}::{e}, {{"{e}", "{display_text}", "{description}"}}}},\n'
        entry += f'{self._indent}\t{{{self.name}::UNKNOWN, {{"UNKNOWN", "None", "None"}}}}\n'
        entry += f"{self._indent}{self._closure}"

        return entry


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
        entry = f"{self._indent}{self.type} {self._opener}\n"
        entry += ",\n".join([f'{self._indent}\t{{{self.name}::{e}, "{e}"}}' for e in enums_with_placeholder])
        entry += f"\n{self._indent}{self._closure}"
        return entry


@dataclass
class Struct(HeaderEntry):
    superclass: str = ""

    def __post_init__(self):
        super().__post_init__()
        self.type = "struct"
        self._closure = "};"
        self.trace()

    def __str__(self):
        entry = f"{self._indent}{self.type} {self.name}"
        if self.superclass:
            entry += f" : {self.superclass}"
        entry += f" {self._opener}\n"
        entry += "\n".join([str(c) for c in self.child_entries])
        entry += f"\n{self._indent}{self._closure}"
        return entry


@dataclass
class DataElement(HeaderEntry):
    _data_group_attributes: dict
    _pod_datatypes_map: dict[str, str]
    _referenced_datatypes: list[ReferencedDataType]
    selector: dict[str, dict[str, str]] = field(init=False, default_factory=dict)

    def __post_init__(self):
        super().__post_init__()
        self._closure = ";"
        self._element_attributes = self._data_group_attributes[self.name]
        self.is_required: bool = True if self._element_attributes.get("Required") == True else False  # noqa E712
        self.scoped_innertype: tuple[str, str] = ("", "")

        self._create_type_entry(self._element_attributes)
        self.trace()

    def __str__(self):
        return f"{self._indent}{self.type} {self.name}{self._closure}"

    def _create_type_entry(self, element_attributes: dict) -> None:
        """Create type node."""
        try:
            # If the type is an array, extract the surrounding [] first (using non-greedy qualifier "?")
            m = re.findall(r"\[(.*?)\]", element_attributes["Data Type"])
            if m:
                self.type = f"std::vector<{self._get_scoped_inner_type(m[0])}>"
            elif m := re.match(r"\((?P<comma_separated_selection_types>.*)\)", element_attributes["Data Type"]):
                self._get_constrained_base_type(element_attributes, m.group("comma_separated_selection_types"))
            else:
                self.type = self._get_scoped_inner_type(element_attributes["Data Type"])
        except KeyError:
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

        # Look through the references to assign a scope to the type
        for custom_type in self._referenced_datatypes:
            if inner_type == custom_type.name:
                self.scoped_innertype = (f"{custom_type.namespace}", inner_type)
                # namespace naming convention is snake_style, regardless of the schema file name
                return "::".join(self.scoped_innertype)
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

    def _get_constrained_base_type(self, element_attributes: dict, match_result: str) -> None:
        """
        Choices can only be mapped to enums; the enum selection key will be stored
        in this object for later code generation, since it constitutes a constraint on this
        Data Element.

        Constraints (of selection type) are of the form
        'selection_key(ENUM_VAL_1, ENUM_VAL_2, ENUM_VAL_3)' They connect pairwise with a Data Type list of the
        form          ({Type_1},   {Type_2},   {Type_3}), all deriving from a base TypeBase
        """
        selection_key = element_attributes["Constraints"].split("(")[0]
        selection_key_enum_class = self._get_scoped_inner_type(self._data_group_attributes[selection_key]["Data Type"])
        selection_types = [self._get_scoped_inner_type(t.strip()) for t in match_result.split(",")]
        m_opt = re.match(r".*\((?P<comma_separated_constraints>.*)\)", element_attributes["Constraints"])
        if not m_opt:
            raise TypeError
        constraints = [
            "::".join([selection_key_enum_class, s.strip()])
            for s in m_opt.group("comma_separated_constraints").split(",")
        ]

        # the self.selector dictionary will have a form like:
        # { operation_speed_control_type : { OperationSpeedControlType::CONTINUOUS : PerformanceMapContinuous, OperationSpeedControlType::DISCRETE : PerformanceMapDiscrete} } # noqa: E501

        # save this mapping to generate the source file contents
        self.selector[selection_key] = dict(zip(constraints, selection_types))

        # The elements of 'selection_types' are Data Groups that derive from a Data Group Template.
        # The template is a verbatim "base class," which is what makes the selector
        # polymorphism possible
        for custom_type in self._referenced_datatypes:
            if custom_type.name == self.scoped_innertype[1]:  # uses last of the selection types list to be processed
                for base_type in self._referenced_datatypes:
                    if base_type.name == custom_type.superclass_name:
                        self.type = f"std::unique_ptr<{base_type.namespace}::{custom_type.superclass_name}>"
                        break


@dataclass
class DataElementIsSetFlag(HeaderEntry):
    def __str__(self):
        return f"{self._indent}bool {self.name}_is_set = false;"


@dataclass
class DataElementStaticMetainfo(HeaderEntry):
    element: dict
    metainfo_key: str

    def __post_init__(self):
        super().__post_init__()
        self._type_specifier = "static constexpr"
        self.type = "std::string_view"
        self._init_val = self.element.get(self.metainfo_key, "") if self.metainfo_key != "Name" else self.name
        self.name = self.name + "_" + self.metainfo_key.lower()
        self._closure = f' = "{self._init_val}";'

        self.trace()

    def __str__(self):
        return f"{self._indent}{self._type_specifier} {self.type} {self.name}{self._closure}"


@dataclass
class InlineDependency(HeaderEntry):
    type: str  # HeaderEntry does not initialize this in __init__, but InlineDependency will

    def __post_init__(self):
        super().__post_init__()
        self._type_specifier = "inline"
        self._closure = ";"
        self.trace()

    def __str__(self):
        return (
            f"{self._indent}{self._type_specifier} {self.type} {self.name}{self._closure}"
            "\n"
            f"{self._indent}void set_{self.name}({self.type} value);"
        )


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
        return f"{self._indent}{' '.join([self._f_ret, self._f_name])}{self.args}{self._closure}"


@dataclass
class MemberFunctionOverrideDeclaration(FunctionalHeaderEntry):
    def __post_init__(self):
        super().__post_init__()
        self._closure = " override;"
        self.trace()


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


@dataclass
class ObjectDeserializationDeclaration(FunctionalHeaderEntry):
    _f_ret: str = field(init=False)
    _f_name: str = field(init=False)
    _f_args: list[str] = field(init=False)

    def __post_init__(self):
        self._f_ret = "void"
        self._f_name = "to_json"
        self._f_args = ["nlohmann::json& j", f"const {self.name}& x"]
        super().__post_init__()
        self.trace()


@dataclass
class VirtualDestructor(FunctionalHeaderEntry):
    _explicit_definition: Optional[str] = None

    def __post_init__(self):
        self._f_ret = "virtual"
        self._f_name = f"~{self._f_name}"
        self._f_args = []
        super().__post_init__()
        self._closure = f" = {self._explicit_definition};" if self._explicit_definition else ";"
        self.trace()
