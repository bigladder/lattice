from __future__ import (
    annotations,
)  # Needed for type hinting classes that are not yet fully defined

import pathlib
from typing import Any, Dict, List, Tuple, Type, Union

import regex

from .file_io import get_file_basename, load

core_schema_path = pathlib.Path(pathlib.Path(__file__).parent, "core.schema.yaml")


class RegularExpressionPattern:
    def __init__(self, pattern_string: str) -> None:
        self.pattern = regex.compile(pattern_string)
        self.anchored_pattern = regex.compile(self.anchor(pattern_string))

    def __str__(self):
        return self.pattern.pattern

    def match(self, test_string: str, anchored: bool = False) -> Union[regex.Match, None]:
        return self.pattern.match(test_string) if not anchored else self.anchored_pattern.match(test_string)

    def anchored(self):
        return self.anchored_pattern.pattern

    def cleaned(self) -> str:
        return regex.sub(r"\?P<\w+>", "?:", self.pattern.pattern)

    @staticmethod
    def anchor(pattern_text: str) -> str:
        return f"^{pattern_text}$"


# Data Types
_type_base_names = RegularExpressionPattern("[A-Z]([A-Z]|[a-z]|[0-9])*")
_data_element_names = RegularExpressionPattern("([a-z][a-z,0-9]*)(_([a-z,0-9])+)*")

_alternation_segment = rf"\({_data_element_names}(\|{_data_element_names})*\)"
_path_segment = rf"({_alternation_segment}|{_data_element_names})"

# A path segment is a literal name, or an alternation of literal names (a|b|c). There is no
# wildcard segment: every path names its targets explicitly. A wildcard reaching into a
# heterogeneous subtree (e.g. across an Alternative(...)'s branches) can silently apply a
# well-formed-but-wrong value with no error, since attributes like Units have no correctness
# check, only a presence check — so paths must always be explicit about what they target.
PathSegment = Union[str, Tuple[str, ...]]


def _parse_path_segment(raw: str) -> Union[str, Tuple[str, ...]]:
    if raw.startswith("(") and raw.endswith(")"):
        return tuple(raw[1:-1].split("|"))
    return raw


class DataType:
    pattern: RegularExpressionPattern
    value_pattern: RegularExpressionPattern

    def __init__(self, text: str, parent_data_element: DataElement):
        self.text = text
        self.parent_data_element = parent_data_element
        self.required_attributes = [
            "Description",
            "Type",
        ]
        self.optional_attributes = [
            "Constraints",
            "Required",
            "Notes",
            "Nested Attribute Overrides",
        ]

    def get_path(self) -> str:
        return (
            f"{self.parent_data_element.parent_data_group.parent_schema.name}."
            f"{self.parent_data_element.parent_data_group.name}."
            f"{self.parent_data_element.name}."
            f"Type"
        )

    def resolve(self):
        pass


class IntegerType(DataType):
    pattern = RegularExpressionPattern("(Integer)")
    value_pattern = RegularExpressionPattern("([-+]?[0-9]+)")


class NumericType(DataType):
    pattern = RegularExpressionPattern("(Numeric)")
    value_pattern = RegularExpressionPattern("(?P<NumericTypeValue>[-+]?[0-9]*\\.?[0-9]+([eE][-+]?[0-9]+)?)")

    def __init__(self, text, parent_data_element):
        super().__init__(text, parent_data_element)
        self.required_attributes += ["Units"]


class BooleanType(DataType):
    pattern = RegularExpressionPattern("(Boolean)")
    value_pattern = RegularExpressionPattern("True|False")


class StringType(DataType):
    pattern = RegularExpressionPattern("(String)")
    value_pattern = RegularExpressionPattern('".*"')

    def __init__(self, text, parent_data_element):
        super().__init__(text, parent_data_element)
        self.optional_attributes += ["ID"]


class PatternType(DataType):
    pattern = RegularExpressionPattern("(Pattern)")
    value_pattern = RegularExpressionPattern('".*"')


class DataGroupType(DataType):
    pattern = RegularExpressionPattern(
        rf"{{(?P<DataGroupName>{_type_base_names})}}|Group\((?P<DataGroupName>{_type_base_names})\)"
    )  # noqa: E501

    def __init__(self, text, parent_data_element):
        super().__init__(text, parent_data_element)
        match = self.pattern.match(text)
        assert match is not None
        self.data_group_name = match.group("DataGroupName")
        self.data_group: DataGroup | None = None  # only valid once resolve() is called

    def resolve(self):
        self.data_group = self.parent_data_element.parent_data_group.parent_schema.get_data_group(self.data_group_name)
        assert self.data_group is not None
        self.optional_attributes += self.data_group.custom_element_attributes


class EnumerationType(DataType):
    pattern = RegularExpressionPattern(
        rf"<(?P<EnumerationTypeName>{_type_base_names})>|"
        rf"Enumeration\((?P<EnumerationTypeName>{_type_base_names})\)"
    )
    value_pattern = RegularExpressionPattern("([A-Z]([A-Z]|[0-9])*)(_([A-Z]|[0-9])+)*")


class AlternativeType(DataType):
    pattern = RegularExpressionPattern(
        r"\((?P<AlternativeTypeName>[^\s,]+)((, ?(?P<AlternativeTypeName>[^\s,]+))+)\)|"
        r"Alternative\((?P<AlternativeTypeName>[^\s,]+)((, ?(?P<AlternativeTypeName>[^\s,]+))+)\)"
    )  # noqa: E501

    def __init__(self, text, parent_data_element):
        super().__init__(text, parent_data_element)
        match = self.pattern.match(text)
        assert match is not None
        self.alternative_type_names = match.captures("AlternativeTypeName")
        self.alternative_data_types: List[DataType] = [
            self.parent_data_element.get_data_type(name) for name in self.alternative_type_names
        ]

    def resolve(self):
        for alternative_data_type in self.alternative_data_types:
            alternative_data_type.resolve()


class ReferenceType(DataType):
    pattern = RegularExpressionPattern(
        rf":(?P<ReferenceTypeName>{_type_base_names}):|"
        rf"Reference\(Group\((?P<ReferenceTypeName>{_type_base_names})\)\)"
    )


class ArrayType(DataType):
    pattern = RegularExpressionPattern(
        rf"\[(?P<ArrayTypeName>{_type_base_names}|{DataGroupType.pattern}|{EnumerationType.pattern})\]|"  # noqa: E501
        rf"Array\((?P<ArrayTypeName>{_type_base_names}|{DataGroupType.pattern}|{EnumerationType.pattern})\)"
    )

    def __init__(self, text, parent_data_element):
        super().__init__(text, parent_data_element)
        match = self.pattern.match(text)
        assert match is not None
        self.array_type_name = match.group("ArrayTypeName")
        self.array_data_type: DataType = self.parent_data_element.get_data_type(self.array_type_name)
        self.optional_attributes = self.array_data_type.optional_attributes
        self.required_attributes = self.array_data_type.required_attributes

    def resolve(self):
        self.array_data_type.resolve()


_value_pattern = RegularExpressionPattern(
    f"(({NumericType.value_pattern})|"
    f"({StringType.value_pattern})|"
    f"({EnumerationType.value_pattern})|"
    f"({BooleanType.value_pattern}))"
)


# Constraints
class Constraint:
    pattern: RegularExpressionPattern
    # Data Types this constraint may be applied to. Empty means unrestricted.
    # If the parent Data Element's Type is an ArrayType, the constraint is checked
    # against the array's element type unless `applies_to_array_container` is set.
    applicable_data_types: List[Type[DataType]] = []
    applies_to_array_container: bool = False

    def __init__(self, text: str, parent_data_element: DataElement):
        self.text = text
        self.parent_data_element = parent_data_element
        self._validate_applicable_data_type()

    def _context(self) -> str:
        data_group = self.parent_data_element.parent_data_group
        fields = [
            ("Schema", data_group.parent_schema.file_path),
            ("Data Group", data_group.name),
            ("Data Element", self.parent_data_element.name),
            ("Constraint Type", type(self).__name__),
        ]
        width = max(len(label) for label, _ in fields)
        return "".join(f"\n    {(label + ':'):<{width + 1}} {value}" for label, value in fields)

    def _validate_applicable_data_type(self) -> None:
        if not self.applicable_data_types:
            return
        data_type = self.parent_data_element.data_type
        if isinstance(data_type, ArrayType) and not self.applies_to_array_container:
            data_type = data_type.array_data_type
        if not isinstance(data_type, tuple(self.applicable_data_types)):
            raise Exception(
                f"Constraint '{self.text}' is not applicable to Data Type '{data_type.text}'.{self._context()}"
            )

    def resolve(self):
        pass


class RangeConstraint(Constraint):
    pattern = RegularExpressionPattern(f"(>|>=|<=|<)({NumericType.value_pattern})")
    applicable_data_types = [IntegerType, NumericType]


class MultipleConstraint(Constraint):
    pattern = RegularExpressionPattern(f"%({NumericType.value_pattern})")
    applicable_data_types = [IntegerType, NumericType]


class SetConstraint(Constraint):
    pattern = RegularExpressionPattern(rf"\[{_value_pattern}(, ?{_value_pattern})*\]")
    applicable_data_types = [IntegerType, NumericType, StringType, EnumerationType]


class SelectorConstraint(Constraint):
    # Selects which of an Alternative(...)'s types applies, based on the value of a sibling
    # Enumeration-typed Data Element: selector_values[i] corresponds positionally to the i-th
    # type in the Alternative. E.g. "statistic_type(SINGLE_VALUE, COINCIDENT_VALUES)" on a
    # percent_exceedance: Alternative(Group(A), Group(B)) field means statistic_type=SINGLE_VALUE
    # selects Group(A), and statistic_type=COINCIDENT_VALUES selects Group(B).
    pattern = RegularExpressionPattern(
        rf"(?P<SelectorElementName>{_data_element_names})\((?P<SelectorValue>{EnumerationType.value_pattern})(, ?(?P<SelectorValue>{EnumerationType.value_pattern}))*\)"  # noqa: E501
    )
    applicable_data_types = [AlternativeType]

    def __init__(self, text: str, parent_data_element: DataElement):
        super().__init__(text, parent_data_element)
        match = self.pattern.match(text)
        assert match is not None
        self.selector_element_name = match.group("SelectorElementName")
        self.selector_values = match.captures("SelectorValue")


class StringPatternConstraint(Constraint):
    pattern = RegularExpressionPattern('".*"')
    applicable_data_types = [StringType, PatternType]

    def __init__(self, text: str, parent_data_element: DataElement):
        super().__init__(text, parent_data_element)
        try:
            regex.compile(text)
        except regex.error:
            raise Exception(f"Invalid regular expression: {text}")  # pylint:disable=W0707


class DataElementValueConstraint(Constraint):
    # Asserts that a (possibly nested) Data Element's value is fixed to a specific constant,
    # e.g. "schema_name=CLIMATE_INFORMATION" or, nested, "(annual|monthly).statistic_type=
    # SINGLE_VALUE". Nesting reuses the same path grammar as NestedAttributeOverride (a literal
    # name or an "(a|b|c)" alternation per segment); unlike NestedAttributeOverride this is a
    # regular Constraint, so it participates in _constraint_factory dispatch and is one of the
    # ways a Data Element pins a sibling's value for other machinery to read back (e.g. the
    # occurrence walker uses a pinned Enumeration value to prune which Alternative(...) branch
    # actually applies; see _pruned_alternative_types).
    pattern = RegularExpressionPattern(
        rf"(?P<DataElementName>{_path_segment}(\.{_path_segment})*)=(?P<ConstrainedValue>{_value_pattern})"
    )  # noqa: E501
    applicable_data_types = [DataGroupType]

    def __init__(self, text: str, parent_data_element: DataElement):
        super().__init__(text, parent_data_element)
        self.pattern = parent_data_element.parent_data_group.parent_schema.schema_patterns.data_element_value_constraint
        match = self.pattern.match(self.text)
        assert match is not None

        self.data_element_name = match.group("DataElementName")
        self.data_element_value = match.group("ConstrainedValue")
        self.path = [_parse_path_segment(segment) for segment in self.data_element_name.split(".")]
        self.data_elements: List[DataElement] = []

    def resolve(self):
        # _validate_applicable_data_type (run during __init__, since applicable_data_types =
        # [DataGroupType]) already guarantees this is a DataGroupType, array-unwrapped the same
        # way as here.
        data_type = self.parent_data_element.data_type
        if isinstance(data_type, ArrayType) and not self.applies_to_array_container:
            data_type = data_type.array_data_type
        assert isinstance(data_type, DataGroupType)
        if data_type.data_group is None:
            raise Exception(
                f"Data Group '{data_type.data_group_name}' referenced by this Data Element's Type "
                f"could not be resolved.{self._context()}"
            )

        current_groups = [data_type.data_group]
        matched_elements: List[DataElement] = []
        for segment in self.path:
            names = segment if isinstance(segment, tuple) else (segment,)
            next_groups: List[DataGroup] = []
            matched_elements = []
            for name in names:
                matching_groups = [group for group in current_groups if name in group.data_elements]
                if not matching_groups:
                    group_names = ", ".join(sorted(group.name for group in current_groups))
                    raise Exception(
                        f"Data Element Value Constraint '{self.data_element_name}' references Data "
                        f"Element '{name}', which was not found in Data Group(s) "
                        f"'{group_names}'.{self._context()}"
                    )
                for group in matching_groups:
                    element = group.data_elements[name]
                    matched_elements.append(element)
                    child_type = element.data_type
                    if isinstance(child_type, ArrayType):
                        child_type = child_type.array_data_type
                    if isinstance(child_type, DataGroupType):
                        resolved_group = self.parent_data_element.parent_data_group.parent_schema.get_data_group(
                            child_type.data_group_name
                        )
                        if resolved_group is not None:
                            next_groups.append(resolved_group)
            current_groups = next_groups
        self.data_elements = matched_elements

        for element in self.data_elements:
            match = element.data_type.value_pattern.match(self.data_element_value)
            if match is None:
                raise Exception(
                    f"Data Element Value Constraint '{self.data_element_value}' does not match the "
                    f"value pattern of '{element.name}'.{self._context()}"
                )


_NESTED_ATTRIBUTES = {"Units", "Constraints", "Required"}


class NestedAttributeOverride:
    # Overrides an attribute (Units, Constraints, Required) on a Data Element reached via a
    # dotted path from the Data Element that declares this override, at any depth. Declared
    # under a Data Element's "Nested Attribute Overrides" key, grouped by attribute name:
    #   Nested Attribute Overrides:
    #     Units:
    #       path: mean
    #       value: "K"
    #     Constraints:
    #     - path: (annual|monthly).(mean|maximum)
    #       value: ">0"
    # A single entry's "value" may itself be a list, for multiple Constraints that must all
    # simultaneously apply to the same path (mirroring how a Data Element's own "Constraints"
    # key already accepts a list). A path segment is either a literal name (matching exactly
    # one child) or "(a|b|c)", an alternation matching any one of a finite, explicitly named set
    # of children — there is no wildcard segment; every path names its targets explicitly. A
    # wildcard reaching into a heterogeneous subtree (e.g. across an Alternative(...)'s
    # branches, where sibling fields represent different quantities) could silently apply a
    # well-formed-but-wrong value with no error, since an attribute like Units has no
    # correctness check, only a presence check. Unlike a Constraint, this isn't a restriction on
    # a value; it's a contextual override applied at the point a (possibly shared) Data Group is
    # adopted. Because a Data Group may be shared by many Data Elements (e.g. a generic
    # "Statistics" group reused for many physical quantities), this does NOT mutate the
    # referenced Data Element; it registers the override on the *referencing* Data Element, and
    # effective values are resolved per-occurrence (see resolve_occurrences).
    path_pattern = RegularExpressionPattern(rf"{_path_segment}(\.{_path_segment})*")

    def __init__(
        self,
        attribute_name: str,
        path_text: str,
        value: Union[str, List[str]],
        parent_data_element: DataElement,
    ):
        self.attribute_name = attribute_name
        self.path_text = path_text
        self.value = value
        self.parent_data_element = parent_data_element
        if self.attribute_name not in _NESTED_ATTRIBUTES:
            raise Exception(
                f"Unsupported attribute '{self.attribute_name}' in Nested Attribute Overrides. "
                f"Supported attributes: {sorted(_NESTED_ATTRIBUTES)}.{self._context()}"
            )
        if not isinstance(path_text, str) or self.path_pattern.match(path_text, anchored=True) is None:
            raise Exception(
                f"Invalid path '{path_text}' for Nested Attribute Override '{attribute_name}'. "
                f"Expected dotted segments, each a literal name or '(a|b|c)'.{self._context()}"
            )
        self.path = [_parse_path_segment(segment) for segment in path_text.split(".")]

        concrete_types = self._resolve_concrete_types(parent_data_element.data_type)
        if not any(isinstance(t, DataGroupType) for t in concrete_types):
            raise Exception(
                f"Nested Attribute Override '{self.text}' requires a Data Group type "
                f"(e.g., 'Group(...)'), but its Type is "
                f"'{parent_data_element.data_type.text}'.{self._context()}"
            )
        self._validate_path(self._resolve_data_groups(parent_data_element.data_type))

    @property
    def text(self) -> str:
        return f"{self.attribute_name}: {{path: {self.path_text}, value: {self.value!r}}}"

    def _context(self) -> str:
        data_group = self.parent_data_element.parent_data_group
        fields = [
            ("Schema", data_group.parent_schema.file_path),
            ("Data Group", data_group.name),
            ("Data Element", self.parent_data_element.name),
        ]
        width = max(len(label) for label, _ in fields)
        return "".join(f"\n    {(label + ':'):<{width + 1}} {value}" for label, value in fields)

    def _resolve_concrete_types(self, data_type: DataType) -> List[DataType]:
        # Flattens Array(...) and Alternative(...) wrappers down to the concrete leaf type(s) a
        # segment could resolve to. An Alternative legitimately yields more than one type, since
        # only one branch is present in any given instance and the schema can't know which
        # ahead of time.
        if isinstance(data_type, ArrayType):
            return self._resolve_concrete_types(data_type.array_data_type)
        if isinstance(data_type, AlternativeType):
            concrete_types: List[DataType] = []
            for alternative_data_type in data_type.alternative_data_types:
                concrete_types.extend(self._resolve_concrete_types(alternative_data_type))
            return concrete_types
        return [data_type]

    def _resolve_data_groups(self, data_type: DataType) -> List[DataGroup]:
        groups = []
        for concrete_type in self._resolve_concrete_types(data_type):
            if isinstance(concrete_type, DataGroupType):
                # Look up the Data Group by name rather than reading concrete_type.data_group:
                # this runs inline during the flat resolve pass, where the intermediate Data
                # Element's own Type may not have had .resolve() called on it yet (that depends
                # on Data Group declaration order, not traversal order).
                resolved = self.parent_data_element.parent_data_group.parent_schema.get_data_group(
                    concrete_type.data_group_name
                )
                if resolved is None:
                    raise Exception(
                        f"Data Group '{concrete_type.data_group_name}' referenced by this Data "
                        f"Element's Type could not be resolved.{self._context()}"
                    )
                groups.append(resolved)
        return groups

    def _validate_path(self, data_groups: List[DataGroup]) -> None:
        current_groups = data_groups
        for segment in self.path:
            names = segment if isinstance(segment, tuple) else (segment,)
            next_groups: List[DataGroup] = []
            for name in names:
                matching_groups = [group for group in current_groups if name in group.data_elements]
                if not matching_groups:
                    group_names = ", ".join(sorted(group.name for group in current_groups))
                    raise Exception(
                        f"Nested Attribute Override '{self.text}' references Data Element "
                        f"'{name}', which was not found in Data Group(s) '{group_names}'.{self._context()}"
                    )
                for group in matching_groups:
                    next_groups.extend(self._resolve_data_groups(group.data_elements[name].data_type))
            current_groups = next_groups


class ArrayLengthLimitsConstraint(Constraint):
    # An array length may be given as a "min..max" range (per ASHRAE 232 5.5.7, with either
    # side omittable) or as a bare integer denoting an exact length (e.g. "[12]" == "[12..12]").
    pattern = RegularExpressionPattern(r"\[(\d*)\.\.(\d*)\]|\[(\d+)\]")
    applicable_data_types = [ArrayType]
    applies_to_array_container = True


_constraint_list: List[Type[Constraint]] = [
    RangeConstraint,
    MultipleConstraint,
    SetConstraint,
    SelectorConstraint,
    StringPatternConstraint,
    DataElementValueConstraint,
    ArrayLengthLimitsConstraint,
]


def _compatible_data_type(constraint: Type[Constraint], parent_data_element: DataElement) -> bool:
    if not constraint.applicable_data_types:
        return True
    data_type = parent_data_element.data_type
    if isinstance(data_type, ArrayType) and not constraint.applies_to_array_container:
        data_type = data_type.array_data_type
    return isinstance(data_type, tuple(constraint.applicable_data_types))


def _constraint_factory(text: str, parent_data_element: DataElement) -> Constraint:
    matches = [constraint for constraint in _constraint_list if constraint.pattern.match(text)]

    if len(matches) > 1:
        # Some constraint patterns overlap (e.g. a bare "[12]" is valid Set syntax and valid
        # Array Length Limits syntax); prefer whichever candidate actually fits the Data
        # Element's Type instead of failing outright.
        compatible_matches = [
            constraint for constraint in matches if _compatible_data_type(constraint, parent_data_element)
        ]
        if len(compatible_matches) > 1 and isinstance(parent_data_element.data_type, ArrayType):
            # E.g. "[12]" on an Array(Numeric) is compatible with both Set (a set containing the
            # single value 12) and Array Length Limits (an array of exactly 12 elements) once
            # Set's applicability is checked against the array's element type. When the Data
            # Element's own Type is an Array, prefer the constraint that treats the array itself
            # as the subject over one that reaches into its element type.
            array_container_matches = [c for c in compatible_matches if c.applies_to_array_container]
            if len(array_container_matches) == 1:
                compatible_matches = array_container_matches
        if len(compatible_matches) == 1:
            matches = compatible_matches

    if len(matches) == 1:
        return matches[0](text, parent_data_element)
    if len(matches) == 0:
        raise Exception(f"No matching constraint for {text} in element {parent_data_element.name}.")
    raise Exception(f"Multiple matches found for constraint, {text}")


# Required
class Required:
    pattern: RegularExpressionPattern

    def __init__(self, text: str, parent_data_element: DataElement):
        self.text = text
        self.parent_data_element = parent_data_element

    def resolve(self):
        pass


class PrerequisiteDefinitionRequired(Required):
    pattern = RegularExpressionPattern(f"if !?({_data_element_names})")


class PrerequisiteValueRequired(Required):
    pattern = RegularExpressionPattern(f"if ({_data_element_names})!?=({_value_pattern})")


class PrerequisiteArrayValueRequired(Required):
    pattern = RegularExpressionPattern(rf"if ({_data_element_names}) contains\(({_value_pattern})\)")


# Required attributes that a NestedAttributeOverride may supply on behalf of a Data Element,
# instead of that Data Element declaring them inline. Checked per-occurrence; see
# resolve_occurrences.
_DEFERRED_REQUIRED_ATTRIBUTES = {"Units"}


class DataElement:
    pattern = _data_element_names

    def __init__(  # noqa: PLR0912 too-many-branches
        self,
        name: str,
        data_element_dictionary: dict,
        parent_data_group: DataGroup,
    ):
        self.name = name
        self.dictionary = data_element_dictionary
        self.parent_data_group = parent_data_group
        self.constraints: List[Constraint] = []
        # Overrides registered against *this* Data Element by its own Nested Attribute Overrides,
        # applying to its descendants. Not applied to descendants directly (they may be a Data
        # Group shared by many other Data Elements); resolved per-occurrence by
        # resolve_occurrences() instead.
        self.attribute_overrides: List[NestedAttributeOverride] = []
        self.is_id = False
        # Data Type is required by subsequent attribute processing; e.g. some Constraints
        if "Type" in self.dictionary:
            data_type_str = self.dictionary["Type"]
            self.data_type = self.get_data_type(data_type_str)
        else:
            raise ValueError(
                f"Type is a required attribute for Data Element '"
                f"{self.parent_data_group.parent_schema.name}.{self.parent_data_group.name}.{self.name}.'"
            )

    def get_data_type(self, attribute_str: str) -> DataType:
        """
        Returns the data type from the attribute string.
        """
        try:
            return self.parent_data_group.parent_schema.data_type_factory(attribute_str, self)
        except RuntimeError:
            for reference_schema in self.parent_data_group.parent_schema.reference_schemas.values():
                try:
                    return reference_schema.data_type_factory(attribute_str, self)
                except RuntimeError:
                    continue
        raise RuntimeError  # if you haven't returned a valid DataType by now

    def set_constraints(self, constraints_input: Union[str, List[str]]) -> None:
        if not isinstance(constraints_input, list):
            constraints_input = [constraints_input]

        for constraint in constraints_input:
            self.constraints.append(_constraint_factory(constraint, self))

    def set_nested_attribute_overrides(self, overrides_input: dict) -> None:
        if not isinstance(overrides_input, dict):
            raise Exception(
                f"'Nested Attribute Overrides' must be a mapping of attribute name to entry "
                f"(or list of entries), each with 'path' and 'value' keys. Got: "
                f"{overrides_input!r}. Schema={self.parent_data_group.parent_schema.file_path}, "
                f"Data Group={self.parent_data_group.name}, Data Element={self.name}"
            )
        for attribute_name, entries in overrides_input.items():
            entry_list = entries if isinstance(entries, list) else [entries]
            for entry in entry_list:
                if not isinstance(entry, dict) or "path" not in entry or "value" not in entry:
                    raise Exception(
                        f"Nested Attribute Override for '{attribute_name}' must be a mapping with "
                        f"'path' and 'value' keys. Got: {entry!r}. "
                        f"Schema={self.parent_data_group.parent_schema.file_path}, "
                        f"Data Group={self.parent_data_group.name}, Data Element={self.name}"
                    )
                self.attribute_overrides.append(
                    NestedAttributeOverride(attribute_name, entry["path"], entry["value"], self)
                )

    def resolve(self):
        # Resolve attributes
        for attribute in self.data_type.required_attributes:
            # Attributes in _DEFERRED_REQUIRED_ATTRIBUTES may instead be supplied by a
            # NestedAttributeOverride declared on an ancestor Data Element; that can only be
            # checked per-occurrence (see resolve_occurrences), since this Data Element's own
            # Data Group may be shared by many other Data Elements with different ancestors.
            if attribute not in self.dictionary and attribute not in _DEFERRED_REQUIRED_ATTRIBUTES:
                raise ValueError(
                    f'Missing required attribute, "{attribute}", for Data Type: "{self.data_type.text}". '
                    f"Schema={self.parent_data_group.parent_schema.file_path}, "
                    f"Data Group={self.parent_data_group.name}, "
                    f"Data Element={self.name}"
                )

        allowed_attributes = self.data_type.required_attributes + self.data_type.optional_attributes

        allowed_attributes += self.parent_data_group.custom_element_attributes

        for attribute in self.dictionary:
            if attribute not in allowed_attributes:
                raise UnrecognizedAttributeError(
                    f'Unrecognized attribute, "{attribute}", for Data Type: "{self.data_type.text}". '
                    f"Schema={self.parent_data_group.parent_schema.file_path}, "
                    f"Data Group={self.parent_data_group.name}, "
                    f"Data Element={self.name}",
                    f"{attribute}",
                )

        self.description = self.dictionary["Description"]
        self.notes = self.dictionary.get("Notes", None)
        self.units = self.dictionary.get("Units", None)
        self.required = self.dictionary.get("Required", False)

        self.is_id = self.dictionary.get("ID", False)
        if self.is_id:
            if self.parent_data_group.id_data_element is None:
                self.parent_data_group.id_data_element = self
            else:
                raise RuntimeError(
                    f"Multiple ID data elements found for Data Group '{self.parent_data_group.name}':"
                    f" '{self.parent_data_group.id_data_element.name}' and '{self.name}'"
                )

        if "Constraints" in self.dictionary:
            self.set_constraints(self.dictionary["Constraints"])

        self.data_type.resolve()
        for constraint in self.constraints:
            constraint.resolve()

        # Nested Attribute Overrides are resolved after the Data Type (so Group references are
        # already resolved) and independently of Constraints (they aren't value restrictions;
        # see NestedAttributeOverride).
        if "Nested Attribute Overrides" in self.dictionary:
            self.set_nested_attribute_overrides(self.dictionary["Nested Attribute Overrides"])


class FundamentalDataType:
    def __init__(self, name: str, data_type_dictionary: dict, parent_schema: Schema):
        self.name = name
        self.dictionary = data_type_dictionary
        self.parent_schema = parent_schema


class CommonStringType:
    def __init__(self, name: str, string_type_dictionary: dict, parent_schema: Schema):
        self.name = name
        self.dictionary = string_type_dictionary
        self.parent_schema = parent_schema
        self.value_pattern = self.dictionary["Regular Expression Pattern"]

        # Make new DataType class
        def init_method(self, text, parent_data_element):
            StringType.__init__(self, text, parent_data_element)

        self.data_type_class = type(
            self.name,
            (StringType,),
            {
                "__init__": init_method,
                "pattern": RegularExpressionPattern(self.name),
                "value_pattern": RegularExpressionPattern(self.value_pattern),
            },
        )

        parent_schema.add_data_type(self.data_type_class)


class DataGroup:
    def __init__(self, name: str, data_group_dictionary: dict, parent_schema: Schema):
        self.name = name
        self.dictionary = data_group_dictionary
        self.parent_schema = parent_schema
        self.parent_template: DataGroupTemplate | None = self._assign_template(
            self.dictionary.get("Data Group Template")
        )
        self.custom_element_attributes: list[str] = []
        if "Custom Attributes" in self.dictionary:
            for attribute in self.dictionary["Custom Attributes"]:
                self.custom_element_attributes.append(attribute)
        # Inherit custom attributes from template if applicable
        if self.parent_template is not None:
            for attribute in self.parent_template.custom_element_attributes:
                if attribute not in self.custom_element_attributes:
                    self.custom_element_attributes.append(attribute)
        self.id_data_element: Union[DataElement, None] = None  # data element containing unique id for this data group
        self.data_elements: dict[str, DataElement] = {}
        for data_element in self.dictionary["Data Elements"]:
            self.data_elements[data_element] = DataElement(
                data_element, self.dictionary["Data Elements"][data_element], self
            )

    def _assign_template(self, template_name: str | None) -> DataGroupTemplate | None:
        if template_name is None:
            return None
        reference_schemas = {self.parent_schema.name: self.parent_schema}
        reference_schemas.update(self.parent_schema.reference_schemas)
        for reference_schema in reference_schemas.values():
            template_assigned = None
            if template_name in reference_schema.data_group_templates.keys():
                template_assigned = reference_schema.data_group_templates[template_name]
                return template_assigned
        if isinstance(template_name, str) and template_assigned is None:
            raise KeyError(
                f"Template named {template_name} not found in {self.parent_schema.name} or referenced schema."
            )
        return template_assigned

    def resolve(self):
        for data_element in self.data_elements.values():
            data_element.resolve()


def _path_matches(pattern: List[PathSegment], actual: List[str]) -> bool:
    # Every segment is a literal name or an alternation, and each consumes exactly one actual
    # segment — there's no wildcard to consume a variable number, so the lengths must match.
    if len(pattern) != len(actual):
        return False
    return all(
        actual_segment in segment if isinstance(segment, tuple) else actual_segment == segment
        for segment, actual_segment in zip(pattern, actual)
    )


def _path_specificity(pattern: List[PathSegment]) -> int:
    # A literal path (no alternations) is more specific than one that uses alternation groups;
    # fewer alternation segments is more specific.
    return sum(1 for segment in pattern if isinstance(segment, tuple))


def _find_override_value(
    attribute_name: str, override_sources: List[Tuple[DataElement, List[str]]]
) -> Union[str, List[str], None]:
    # Closer ancestors take precedence over farther ones; within one ancestor's own overrides,
    # the most specific (fewest alternation segments) matching override wins.
    for ancestor, relative_path in reversed(override_sources):
        candidates = [
            override
            for override in ancestor.attribute_overrides
            if override.attribute_name == attribute_name and _path_matches(override.path, relative_path)
        ]
        if candidates:
            return min(candidates, key=lambda override: _path_specificity(override.path)).value
    return None


def resolve_occurrences(schema: Schema) -> None:
    """
    Validate attributes deferred by _DEFERRED_REQUIRED_ATTRIBUTES once per concrete occurrence
    (e.g. "dry_bulb_temperature.annual.mean"), rather than once per (possibly shared) Data
    Group, so a NestedAttributeOverride declared on one occurrence's ancestor cannot affect
    any other occurrence of the same underlying Data Group.
    """
    if schema.root_data_group is None:
        return
    for data_element in schema.root_data_group.data_elements.values():
        _walk_occurrence(data_element, [], [data_element.name], frozenset())


def _walk_occurrence(
    data_element: DataElement,
    override_sources: List[Tuple[DataElement, List[str]]],
    path_labels: List[str],
    visited_group_names: frozenset,
) -> None:
    # Tracked for both NestedAttributeOverride lookups (attribute_overrides) and pinned-selector
    # lookups (constraints, e.g. a nested DataElementValueConstraint elsewhere in the ancestor
    # chain); see _pruned_alternative_types.
    if data_element.attribute_overrides or data_element.constraints:
        override_sources = [*override_sources, (data_element, [])]
    _walk_type(data_element, data_element.data_type, override_sources, path_labels, visited_group_names)


def _pruned_alternative_types(
    data_element: DataElement,
    data_type: AlternativeType,
    override_sources: List[Tuple[DataElement, List[str]]],
) -> List[DataType]:
    # If percent_exceedance-style field has a SelectorConstraint (e.g.
    # "statistic_type(SINGLE_VALUE, COINCIDENT_VALUES)") and some ancestor has pinned that
    # sibling Enumeration Data Element to one specific value via a (possibly nested)
    # DataElementValueConstraint (e.g. "annual.statistic_type=SINGLE_VALUE"), only the
    # corresponding Alternative branch actually applies here — the others don't need to be
    # validated (and shouldn't have to satisfy required-attribute/Constraints-override checks
    # that were never meant for them). Otherwise, fall back to walking every branch.
    selector = next((c for c in data_element.constraints if isinstance(c, SelectorConstraint)), None)
    if selector is None:
        return data_type.alternative_data_types
    pinned_value = None
    for ancestor, relative_path in reversed(override_sources):
        sibling_path = [*relative_path[:-1], selector.selector_element_name]
        for constraint in ancestor.constraints:
            if isinstance(constraint, DataElementValueConstraint) and _path_matches(constraint.path, sibling_path):
                pinned_value = constraint.data_element_value
                break
        if pinned_value is not None:
            break
    if pinned_value is None or pinned_value not in selector.selector_values:
        return data_type.alternative_data_types
    index = selector.selector_values.index(pinned_value)
    if index >= len(data_type.alternative_data_types):
        return data_type.alternative_data_types
    return [data_type.alternative_data_types[index]]


def _walk_type(
    data_element: DataElement,
    data_type: DataType,
    override_sources: List[Tuple[DataElement, List[str]]],
    path_labels: List[str],
    visited_group_names: frozenset,
) -> None:
    if isinstance(data_type, ArrayType):
        data_type = data_type.array_data_type

    if isinstance(data_type, AlternativeType):
        # Only one alternative is actually present in any given instance; validate/support
        # overrides for all of them unless a pinned selector rules some out (see
        # _pruned_alternative_types). Passes the same data_element through (its own
        # attribute_overrides/constraints were already registered by _walk_occurrence), just
        # with a different data_type to traverse.
        for alternative_data_type in _pruned_alternative_types(data_element, data_type, override_sources):
            _walk_type(data_element, alternative_data_type, override_sources, path_labels, visited_group_names)
        return

    if isinstance(data_type, DataGroupType):
        if data_type.data_group is None:
            return
        if data_type.data_group_name in visited_group_names:
            # Data Groups may legitimately reference themselves (directly or transitively), so
            # this is not an error; just stop descending rather than recursing forever.
            return
        child_visited = visited_group_names | {data_type.data_group_name}
        for child_name, child in data_type.data_group.data_elements.items():
            child_sources = [(ancestor, [*relative, child_name]) for ancestor, relative in override_sources]
            _walk_occurrence(child, child_sources, [*path_labels, child_name], child_visited)
    else:
        for attribute in _DEFERRED_REQUIRED_ATTRIBUTES:
            if attribute in data_type.required_attributes and attribute not in data_element.dictionary:
                if _find_override_value(attribute, override_sources) is None:
                    raise ValueError(
                        f'Missing required attribute, "{attribute}", for Data Type: "{data_type.text}". '
                        f"Schema={data_element.parent_data_group.parent_schema.file_path}, "
                        f"Data Group={data_element.parent_data_group.name}, "
                        f"Data Element={data_element.name}, "
                        f"Occurrence={'.'.join(path_labels)}"
                    )

        _validate_constraint_overrides(data_element, override_sources, path_labels)


def _validate_constraint_overrides(
    data_element: DataElement,
    override_sources: List[Tuple[DataElement, List[str]]],
    path_labels: List[str],
) -> None:
    # A Constraints override is a value restriction, so (unlike Units) it needs real type
    # validation against its target — reusing the same factory/applicability checks a normal
    # Constraints entry would go through, without attaching anything to the (possibly shared)
    # target. Every path names its targets explicitly (there are no wildcards), so a mismatch
    # here always means the same thing: an authoring error.
    for ancestor, relative_path in override_sources:
        for override in ancestor.attribute_overrides:
            if override.attribute_name != "Constraints" or not _path_matches(override.path, relative_path):
                continue
            values = override.value if isinstance(override.value, list) else [override.value]
            for value in values:
                try:
                    _constraint_factory(value, data_element)
                except Exception as exc:
                    raise Exception(
                        f"Nested Attribute Override '{override.text}' does not apply at occurrence "
                        f"'{'.'.join(path_labels)}': {exc}"
                    ) from exc


class Enumerator:
    pattern = EnumerationType.value_pattern

    def __init__(self, name: str, enumerator_dictionary: dict, parent_enumeration: Enumeration):
        self.name = name
        self.dictionary = enumerator_dictionary
        self.parent_enumeration = parent_enumeration


class Enumeration:
    def __init__(self, name: str, enumeration_dictionary: dict, parent_schema: Schema):
        self.name = name
        self.dictionary = enumeration_dictionary
        self.parent_schema = parent_schema
        self.enumerators = {}
        for enumerator in self.dictionary["Enumerators"]:
            self.enumerators[enumerator] = Enumerator(enumerator, self.dictionary["Enumerators"][enumerator], self)


class DataGroupTemplate:
    def __init__(self, name: str, data_group_template_dictionary: dict, parent_schema: Schema):
        self.name = name
        self.dictionary = data_group_template_dictionary
        self.parent_schema = parent_schema
        self.custom_element_attributes: list[str] = self.dictionary.get(
            "Custom Attributes", []
        )  # TODO: make a list of CustomAttribute objects


class CustomAttribute:
    def __init__(self, name: str, custom_attribute_dictionary: dict, parent_schema: Schema):
        self.name = name
        self.dictionary = custom_attribute_dictionary
        self.parent_schema = parent_schema
        self.type = self.dictionary["Type"]
        self.display_name = self.dictionary.get("Display Name", self.name)
        self.description = self.dictionary.get("Description", "")
        self.applies_to = self.dictionary.get("Applies To", [])
        self.required = self.dictionary.get("Required", False)


class SchemaPatterns:
    # TODO: Remove in favor of class members of respective classes?
    numeric = NumericType.value_pattern
    integer = IntegerType.value_pattern
    string = StringType.value_pattern
    enumerator = Enumerator.pattern
    boolean = BooleanType.value_pattern

    data_group_names = _type_base_names
    enumeration_names = _type_base_names
    data_element_names = DataElement.pattern
    type_base_names = _type_base_names

    def __init__(self, schema=None):
        # Generate Regular Expressions
        core_schema = load(core_schema_path)

        # Fundamental Data Types (from core schema)
        core_types = get_types(core_schema)
        self.combined_types = set(core_types.keys())

        regex_base_types = core_types["Data Type"]

        base_types_string = "|".join(regex_base_types)
        base_types = RegularExpressionPattern(f"({base_types_string})")

        string_types = core_types["String Type"]
        if schema:
            schema_types = get_types(schema)
            self.combined_types |= set(schema_types.keys())
            if "String Type" in schema_types:
                string_types += ["String Type"]

        re_string_types_string = "|".join(string_types)
        re_string_types = RegularExpressionPattern(f"({re_string_types_string})")

        self.data_group_types = DataGroupType.pattern.cleaned()
        self.enumeration_types = EnumerationType.pattern.cleaned()
        references = ReferenceType.pattern.cleaned()
        single_type = rf"({base_types}|{re_string_types}|{self.data_group_types}|{self.enumeration_types}|{references})"
        alternatives = rf"\(({single_type})(,\s*{single_type})+\)"
        arrays = ArrayType.pattern.cleaned()
        self.data_types = RegularExpressionPattern(f"({single_type})|({alternatives})|({arrays})")

        # Values
        self.values = RegularExpressionPattern(
            f"(({self.numeric})|({self.string})|({self.enumerator})|({self.boolean}))"
        )

        # Constraints
        self.range_constraint = RangeConstraint.pattern.cleaned()
        self.multiple_constraint = MultipleConstraint.pattern.cleaned()
        self.data_element_value_constraint = DataElementValueConstraint.pattern
        sets = SetConstraint.pattern.cleaned()
        reference_scope = f":{_type_base_names}:"
        self.selector_constraint = SelectorConstraint.pattern.cleaned()
        array_limits = ArrayLengthLimitsConstraint.pattern
        string_patterns = StringPatternConstraint.pattern

        self.constraints = RegularExpressionPattern(
            f"({self.range_constraint})|"  # pylint:disable=C0301
            f"({self.multiple_constraint})|"
            f"({sets})|"
            f"({self.data_element_value_constraint})|"
            f"({reference_scope})|"
            f"({self.selector_constraint})|"
            f"({array_limits})|"
            f"({string_patterns})"
        )

        # Conditional Requirements
        self.prerequisite_definition_required = PrerequisiteDefinitionRequired.pattern.cleaned()
        self.prerequisite_value_required = PrerequisiteValueRequired.pattern.cleaned()
        self.prerequisite_array_value_required = PrerequisiteArrayValueRequired.pattern.cleaned()

        self.conditional_requirements = RegularExpressionPattern(
            f"({self.prerequisite_definition_required})|"
            f"({self.prerequisite_value_required})|"
            f"({self.prerequisite_array_value_required})"
        )


class UnrecognizedAttributeError(Exception):
    def __init__(self, message, attribute_name):
        self.message = message
        self.attribute_name: str = attribute_name
        super().__init__(message)

    def __str__(self):
        return f"{self.message}"


class Schema:
    def __init__(  # noqa: PLR0912, PLR0915 too-many-branches, too-many-statements
        self,
        file_path: pathlib.Path,
        parent_schema: Schema | None = None,
    ):
        self.file_path = file_path.absolute()
        self.source_dictionary = load(self.file_path)
        self.name = get_file_basename(self.file_path, depth=2)
        if "Schema" not in self.source_dictionary:
            raise Exception(f'"Schema" node not found in {self.file_path}')

        self.parent_schema = parent_schema
        self.data_types = {}
        self.string_types = {}
        self.enumerations = {}
        self.data_groups = {}
        self.data_group_templates = {}
        self.custom_attributes = {}

        self._data_type_list: List[Type[DataType]] = [
            IntegerType,
            NumericType,
            BooleanType,
            StringType,
            PatternType,
            ArrayType,
            DataGroupType,
            EnumerationType,
            AlternativeType,
            ReferenceType,
        ]

        self.schema_patterns = SchemaPatterns(self.source_dictionary)

        if "Schema" in self.source_dictionary:
            self.title = self.source_dictionary["Schema"]["Title"]
            self.description = self.source_dictionary["Schema"]["Description"]
            self.version = self.source_dictionary["Schema"]["Version"]
            self.root_data_group_name = (
                self.source_dictionary["Schema"]["Root Data Group"]
                if "Root Data Group" in self.source_dictionary["Schema"]
                else None
            )
            self.set_reference_schemas()

        for object_name in self.source_dictionary:
            object_type = self.source_dictionary[object_name]["Object Type"]
            if object_type == "Data Group":
                self.data_groups[object_name] = DataGroup(object_name, self.source_dictionary[object_name], self)
            elif object_type == "Enumeration":
                self.enumerations[object_name] = Enumeration(object_name, self.source_dictionary[object_name], self)
            elif object_type == "Type":
                self.data_types[object_name] = FundamentalDataType(
                    object_name, self.source_dictionary[object_name], self
                )
            elif object_type == "String Type":
                self.string_types[object_name] = CommonStringType(
                    object_name, self.source_dictionary[object_name], self
                )
            elif object_type == "Data Group Template":
                self.data_group_templates[object_name] = DataGroupTemplate(
                    object_name, self.source_dictionary[object_name], self
                )
            elif object_type == "Custom Attribute":
                self.custom_attributes[object_name] = CustomAttribute(
                    object_name, self.source_dictionary[object_name], self
                )
            elif object_type in ["Meta", "Data Type"]:
                pass
            else:
                raise Exception(f'Unrecognized Object Type, "{object_type}" in {self.file_path}')

        # Get top level info.
        #
        # Three distinct names are in play here, and only one of them matters for
        # instance validation:
        #   - `self.name`: this schema *file's* own name (e.g. "ClimateInformation"
        #     from "ClimateInformation.schema.yaml"). Used only to name generated
        #     artifacts (meta-schema/JSON-schema/C++ file names); it's the weakest
        #     fallback for schema_name below, nothing more.
        #   - `self.root_data_group_name`: the "Root Data Group" declared in this
        #     schema's own `Schema:` block. Identifies the entry Data Group type, and
        #     is a stronger fallback for schema_name if no explicit override exists.
        #   - `self.schema_name`: the *public* schema identifier that a compliant
        #     instance file must declare in its own `metadata.schema_name` for
        #     validate_file() to match it to this schema (see lattice.py). Defaults to
        #     the fallbacks above, but a schema may pin it to something else entirely
        #     via a `schema_name="..."` constraint on the root data group's `metadata`
        #     element -- e.g. ClimateInformation's root data group is named
        #     "ClimateInformation" (PascalCase, an internal/code-facing name) but pins
        #     schema_name to "CLIMATE_INFORMATION" (the long-standing public
        #     identifier data files actually carry).
        self.root_data_group = None
        self.metadata = None
        self.schema_author = None
        self.schema_name = self.name

        if self.root_data_group_name is not None:
            self.schema_name = self.root_data_group_name
            self.root_data_group = self.get_data_group(self.root_data_group_name)
            self.metadata = (
                self.root_data_group.data_elements["metadata"]
                if "metadata" in self.root_data_group.data_elements
                else None
            )

        for data_group in self.data_groups.values():
            data_group.resolve()

        # A schema_name/schema_author self-override is a Constraint on the metadata
        # Data Element, and Constraints are only parsed into `.constraints` by
        # DataElement.resolve() (called above via data_group.resolve()) -- so this
        # must run after that loop, not before it, or the override is silently never
        # seen and schema_name quietly falls back to root_data_group_name/self.name.
        if self.metadata is not None:
            for constraint in self.metadata.constraints:
                if isinstance(constraint, DataElementValueConstraint):
                    if constraint.data_element_name == "schema_author":
                        self.schema_author = constraint.data_element_value
                    elif constraint.data_element_name == "schema_name":
                        self.schema_name = constraint.data_element_value.strip('"')

        resolve_occurrences(self)

    def set_reference_schemas(self):
        self.reference_schemas: dict[str, Schema] = {}
        if self.file_path != core_schema_path:
            self.set_reference_schema("core", core_schema_path)
        if "References" in self.source_dictionary["Schema"]:
            parent_directory = self.file_path.parent
            for reference in self.source_dictionary["Schema"]["References"]:
                if reference == "core":
                    raise Exception(f"Illegal reference schema name, {reference}. This name is reserved.")
                self.set_reference_schema(
                    reference,
                    pathlib.Path(parent_directory, f"{reference}.schema.yaml"),
                )

    def set_reference_schema(self, schema_name, schema_path):
        existing_schema = self.get_reference_schema(schema_name)

        if existing_schema is not None:
            self.reference_schemas[schema_name] = existing_schema
        else:
            self.reference_schemas[schema_name] = Schema(schema_path, self)

    def get_reference_schema(self, schema_name: str) -> Schema | None:
        # TODO: verify schema has the same path too?
        # Search this schema first
        if schema_name in self.reference_schemas:
            return self.reference_schemas[schema_name]

        # Search parent schema
        if self.parent_schema is not None:
            return self.parent_schema.get_reference_schema(schema_name)

        return None

    def get_data_group(self, data_group_name: str) -> DataGroup:
        matching_schemas = []
        # 1. Search this schema first
        if data_group_name in self.data_groups:
            matching_schemas.append(self)
        for reference_schema in self.reference_schemas.values():
            if data_group_name in reference_schema.data_groups:
                matching_schemas.append(reference_schema)

        if len(matching_schemas) == 0:
            raise Exception(f'Data Group "{data_group_name}" not found in "{self.file_path}" or its referenced schemas')

        return matching_schemas[0].data_groups[data_group_name]

    def data_type_factory(self, text: str, parent_data_element: DataElement) -> DataType:
        number_of_matches = 0
        for data_type in self._data_type_list:
            if data_type.pattern.match(text):
                match_type = data_type
                number_of_matches += 1

        if number_of_matches == 1:
            return match_type(text, parent_data_element)
        if number_of_matches == 0:
            raise RuntimeError(f"No matching data type for {text}.")
        else:
            raise RuntimeError(f"Multiple matches found for data type, {text}")

    def add_data_type(self, data_type: Type[DataType]) -> None:
        if data_type not in self._data_type_list:
            self._data_type_list.append(data_type)

        if self.parent_schema is not None:
            self.parent_schema.add_data_type(data_type)


def get_types(schema):
    """For each Object Type in a schema, map a list of Objects matching that type."""
    types: Dict[str, Any] = {}
    for object_name in schema:
        if schema[object_name]["Object Type"] not in types:
            types[schema[object_name]["Object Type"]] = []
        types[schema[object_name]["Object Type"]].append(object_name)
    return types
