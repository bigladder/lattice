from __future__ import annotations
import yaml
from pathlib import Path
from enum import Enum
from typing import Dict, List, Optional, Union, Literal, Any, ClassVar, Type, Set

from pydantic import (
    BaseModel,
    RootModel,
    Field,
    model_validator,
    create_model,
    BeforeValidator,
    InstanceOf
)
from pydantic.types import StringConstraints
from typing_extensions import Annotated, Self

from lattice import schema

schema_path: Path = Path().cwd()

# TODO: A template may have a Unit System attribute that must be available in "Unit Systems"
# TODO: Different constraints, requirements
# TODO: Add Schema class' regexs and stuff
# TODO: Things like RequiredDataTypes, that are read in as strs, should be valid types
# TODO: If enum type (etc), has correct regex
# TODO: find missing required data elements in template-derived Data Groups, and Array constraints like [Numeric][1..] where I guess the size value has been moved to the Constraints list.

class JSONSchemaType(Enum):
    string = 'string'
    number = 'number'
    integer = 'integer'
    boolean = 'boolean'
    null = 'null'


class DataType(BaseModel):
    class Config:
        extra = "forbid"

    Object_Type: Literal['Data Type'] = Field( alias='Object Type')
    Description: str
    JSON_Schema_Type: JSONSchemaType = Field(..., alias='JSON Schema Type')
    Examples: List[str]


class StringType(BaseModel):
    class Config:
        extra = "forbid"

    Object_Type: Literal['String Type'] = Field( alias='Object Type')
    Description: str
    Regular_Expression_Pattern: Optional[str] = Field(None, alias='Regular Expression Pattern')
    Examples: List[str]
    Is_Regex: Optional[bool] = Field(None, alias='Is Regex')


# class Integer(DataType):
#     JSON_Schema_Type: JSONSchemaType = Field(JSONSchemaType.integer, alias='JSON Schema Type')


# class Numeric(DataType):
#     JSON_Schema_Type: JSONSchemaType = Field(JSONSchemaType.number, alias='JSON Schema Type')


# class Boolean(DataType):
#     JSON_Schema_Type: JSONSchemaType = Field(JSONSchemaType.boolean, alias='JSON Schema Type')


# class String(DataType):
#     JSON_Schema_Type: JSONSchemaType = Field(JSONSchemaType.string, alias='JSON Schema Type')


# class Pattern(DataType):
#     JSON_Schema_Type: JSONSchemaType = Field(JSONSchemaType.string, alias='JSON Schema Type')


# class UUID(StringType):
#     ...

# class Date(StringType):
#     ...

# class Timestamp(StringType):
#     ...

# class Version(StringType):
#     ...

class ObjectType(Enum):
    Meta = 'Meta'
    Data_Type = 'Data Type'
    String_Type = 'String Type'
    Enumeration = 'Enumeration'
    Data_Group = 'Data Group'
    Data_Group_Template = 'Data Group Template'


def get_references(refs: List[str]) -> List[LatticeSchema]:
    # TODO: validate the strings (schema.ReferenceType) first? or just allow the open to throw?
    schema: List[LatticeSchema] = []
    for ref in refs:
        with open(LatticeSchema.schema_path / f"{ref}.schema.yaml", 'r') as stream:
            config = yaml.load(stream, Loader=yaml.CLoader)
            schema.append(LatticeSchema(lattice_schema=config))
    return schema


def get_unit_systems(systems: Dict[str, List[str]]) -> List[DynamicUnitSystem]:
    UnitSystemClasses: List[DynamicUnitSystem] = [StandardUnits]
    for system in systems:
        units = systems[system]
        UnitSystemClass = DynamicUnitSystem(system, {k:str(k) for k in units})
        UnitSystemClasses.append(UnitSystemClass)

    return UnitSystemClasses


class DynamicUnitSystem(Enum):
    ...


class StandardUnits(DynamicUnitSystem):
    field_ = '-'
    m = 'm'
    m2 = 'm2'
    m3 = 'm3'
    s = 's'
    m_s = 'm/s'
    m2_s = 'm2/s'
    m3_s = 'm3/s'
    kg = 'kg'
    kg_s = 'kg/s'
    N = 'N'
    J = 'J'
    W = 'W'
    Pa = 'Pa'
    K = 'K'
    J_K = 'J/K'
    W_K = 'W/K'
    m2_K_W = 'm2-K/W'
    V = 'V'
    A = 'A'
    C = 'C'
    Hz = 'Hz'
    rev_s = 'rev/s'


class Meta(BaseModel):
    class Config:
        extra = "forbid"

    Object_Type: Literal['Meta'] = Field( alias='Object Type')
    Title: Optional[str] = None
    Description: Optional[str] = None
    Version: Optional[str] = None
    Root_Data_Group: Optional[str] = Field(None, alias='Root Data Group')
    References: Optional[Annotated[List[LatticeSchema], BeforeValidator(get_references)]] = None
    Unit_Systems: Optional[Annotated[List[Type[DynamicUnitSystem]], BeforeValidator(get_unit_systems)]] = Field(
        [StandardUnits], alias='Unit Systems'
    )


class ConstraintsPattern(RootModel):
    root: Annotated[str, StringConstraints(
        pattern=rf'^((>|>=|<=|<)(([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)))|(%(([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)))|(\[([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)(, ?([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?))*\])|(({schema._data_element_names.pattern.pattern})=(((([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?))|(".*")|(([A-Z]([A-Z]|[0-9])*)(_([A-Z]|[0-9])+)*)|(True|False))))|(:[A-Z]([A-Z]|[a-z]|[0-9])*:)|(([a-z][a-z,0-9]*)(_([a-z,0-9])+)*\(([A-Z]([A-Z]|[0-9])*)(_([A-Z]|[0-9])+)*(, ?([A-Z]([A-Z]|[0-9])*)(_([A-Z]|[0-9])+)*)*\))|(\[(\d*)\.\.(\d*)\])|(".*")$'
    )]


class ConstraintsAttribute(RootModel):
    root: Union[ConstraintsPattern, List[ConstraintsPattern]]


class ElementBasedConditionalRequiredPattern(RootModel):
    # TODO: Should we use schema.DataElementValueConstraint.pattern? What about the "if"?
    root: Annotated[str, StringConstraints(pattern=rf'if ({schema._data_element_names.pattern.pattern})(!=|=)({schema.BooleanType.value_pattern})')]


class EnumValueBasedConditionalRequiredPattern(RootModel):
    # TODO: Should we use schema.DataElementValueConstraint.pattern? What about the "if"?
    root: Annotated[str, StringConstraints(pattern=rf'if ({schema._data_element_names.pattern.pattern})(!=|=)({schema.EnumerationType.value_pattern})')]


class ExclusionaryRequiredPattern(RootModel):
    # TODO: Should we use schema.DataElementValueConstraint.pattern? What about the "if"?
    root: Annotated[str, StringConstraints(pattern=rf'if !({schema._data_element_names.pattern.pattern})')]


class RequiredAttribute(RootModel):
    root: Union[bool, ElementBasedConditionalRequiredPattern, EnumValueBasedConditionalRequiredPattern, ExclusionaryRequiredPattern]


class EnumeratorAttributes(BaseModel):
    class Config:
        extra = "forbid"

    Description: Optional[str] = None
    Display_Text: Optional[str] = Field(None, alias='Display Text')
    Notes: Optional[Union[str, List[str]]] = None


class Enumerants(BaseModel):
    root: Dict[Annotated[str, StringConstraints(pattern=schema.EnumerationType.value_pattern.pattern)], Optional[EnumeratorAttributes]] = Field(
        None)


class Enumeration(BaseModel):
    class Config:
        extra = "forbid"

    Object_Type: Literal['Enumeration'] = Field(alias='Object Type')
    Enumerators: Enumerants


class DataTypePattern(RootModel):
    root: Annotated[str, StringConstraints(
        pattern=r'^(((Integer|Numeric|Boolean|String|Pattern)|(UUID|Date|Timestamp|Version)|\{([A-Z]([A-Z]|[a-z]|[0-9])*)\}|<[A-Z]([A-Z]|[a-z]|[0-9])*>|:[A-Z]([A-Z]|[a-z]|[0-9])*:))|(\((((Integer|Numeric|Boolean|String|Pattern)|(UUID|Date|Timestamp|Version)|\{([A-Z]([A-Z]|[a-z]|[0-9])*)\}|<[A-Z]([A-Z]|[a-z]|[0-9])*>|:[A-Z]([A-Z]|[a-z]|[0-9])*:))(,\s*((Integer|Numeric|Boolean|String|Pattern)|(UUID|Date|Timestamp|Version)|\{([A-Z]([A-Z]|[a-z]|[0-9])*)\}|<[A-Z]([A-Z]|[a-z]|[0-9])*>|:[A-Z]([A-Z]|[a-z]|[0-9])*:))+\))|(\[([A-Z]([A-Z]|[a-z]|[0-9])*|\{([A-Z]([A-Z]|[a-z]|[0-9])*)\}|<[A-Z]([A-Z]|[a-z]|[0-9])*>)\])$'
        #pattern=schema._type_base_names.pattern
    )]


class DataElementAttributes(BaseModel):
    Description: Optional[str] = None
    Data_Type: Optional[DataTypePattern] = Field(None, alias='Data Type')
    Units: Optional[str] = None # Re-validate with available unit systems
    Constraints: Optional[ConstraintsAttribute] = None
    Required: Optional[RequiredAttribute] = None
    Notes: Optional[Union[str, List[str]]] = None
    ID: Optional[bool] = None


class DataGroup(BaseModel):
    class Config:
        extra = 'forbid'

    Object_Type: Literal['Data Group'] = Field( alias='Object Type')
    Data_Group_Template: Optional[str] = Field(None, alias='Data Group Template')
    Data_Elements: Dict[Annotated[str, StringConstraints(pattern=schema.DataElement.pattern.pattern)], DataElementAttributes] = Field(
        ..., alias='Data Elements'
    )
    Unit_System: Optional[str] = Field(None, alias='Unit System')


class DataGroupTemplate(BaseModel):
    class Config:
        extra = 'forbid'

    Object_Type: Literal['Data Group Template'] = Field( alias='Object Type')
    Required_Data_Elements: Optional[
        Dict[Annotated[str, StringConstraints(pattern=schema.DataElement.pattern.pattern)], DataElementAttributes]
    ] = Field(None, alias='Required Data Elements')
    Unit_System: Optional[str] = Field(None, alias='Unit System')
    Required_Data_Types: Optional[List[str]] = Field(None, alias='Required Data Types', min_items=1)
    Data_Elements_Required: Optional[bool] = Field(None, alias='Data Elements Required')


class Item(RootModel):
    root: Union[DataType, StringType, DataGroup, DataGroupTemplate, Enumeration, Meta] = Field(..., discriminator="Object_Type")


class LatticeSchema(BaseModel):
    lattice_schema: Dict[str, Item]
    model_unit_systems: Dict[str, List[str]] = Field(default={})
    schema_path: ClassVar[Path] = Path().cwd()

    @model_validator(mode='after')
    def find_data_group_template(self) -> Self:
        referenceable_templates = []
        for group in self.lattice_schema.values(): # All the subdictionaries in self
            if isinstance(group.root, Meta) and group.root.References:
                for reference in group.root.References:
                    for (template_name,template) in reference.lattice_schema.items():
                        if isinstance(template.root, DataGroupTemplate):
                            referenceable_templates.append((template_name, template))

        # Iterate over all the Data Groups in self that have a Data Group Template attribute
        for _, datagroup in [(k,v) for (k,v) in self.lattice_schema.items() if isinstance(v.root, DataGroup) and v.root.Data_Group_Template]:
            matched = False
            # Iterate over all the possible template names that could be referenced by the group's DGT attribute
            for template_name, _ in [(k,v) for (k,v) in self.lattice_schema.items() if isinstance(v.root, DataGroupTemplate)] + referenceable_templates:
                if datagroup.root.Data_Group_Template == template_name:
                    matched = True
            if not matched:
                raise Exception(f"Data Group Template definition {datagroup.root.Data_Group_Template} not found.")
        return self

    @model_validator(mode='after')
    def validate_data_element_units(self) -> Self:
        # Gather all possible unit systems that are declared in the Meta attribute(s)
        for group in self.lattice_schema.values(): # All the subdictionaries in self
            if isinstance(group.root, Meta):
                if group.root.Unit_Systems:
                    for unit_system in group.root.Unit_Systems:
                        self.model_unit_systems[unit_system.__name__] = [unit.value for unit in unit_system]
                if group.root.References:
                    for reference in group.root.References:
                        for (name,item) in reference.lattice_schema.items():
                            if isinstance(item.root, Meta) and item.root.Unit_Systems:
                                for unit_system in item.root.Unit_Systems:
                                    self.model_unit_systems[unit_system.__name__] = [unit.value for unit in unit_system]

        # Ensure that any unit that is used corresponds to a valid Unit System: one which is declared either in the
        # Data Group itself, or one declared in the Data Group Template that the group derives from
        for _, datagroup in [(k,v) for (k,v) in self.lattice_schema.items() if isinstance(v.root, DataGroup)]:
            # Iterate over all the Data Groups in self
            for name, attributes in datagroup.root.Data_Elements.items():
                if attributes.Units:
                    if datagroup.root.Data_Group_Template:
                        # Look for the DGT object in self + references first, find Unit System defined there
                        for object in self.lattice_schema.values(): # All the subdictionaries in self
                            if isinstance(object.root, Meta) and object.root.References:
                                for reference in object.root.References:
                                    for (template_name,template) in reference.lattice_schema.items():
                                        if isinstance(template.root, DataGroupTemplate):
                                            if datagroup.root.Data_Group_Template == template_name:
                                                if template.root.Unit_System:
                                                    if attributes.Units not in self.model_unit_systems[template.root.Unit_System]:
                                                        raise Exception(f"Unit {attributes.Units} for element {name} was not found in Unit System {template.root.Unit_System}.")
                                                else:
                                                    if attributes.Units not in [u.value for u in StandardUnits]:
                                                        raise Exception(f"Unit {attributes.Units} for element {name} was not found in Standard Units.")
                    elif datagroup.root.Unit_System:
                        if attributes.Units not in self.model_unit_systems[datagroup.root.Unit_System]:
                            raise Exception(f"Unit {attributes.Units} for element {name} was not found in Unit System {datagroup.root.Unit_System}.")
                    else:
                        if attributes.Units not in [u.value for u in StandardUnits]:
                            raise Exception(f"Unit {attributes.Units} for element {name} was not found in Standard Units.")
        return self

if __name__ == "__main__":
    #schema_file = Path("C:/Users/Tanaya Mankad/source/repos/lattice/examples/time_series/schema/TimeSeries.schema.yaml")
    #schema_file = Path("C:/Users/Tanaya Mankad/source/repos/lattice/examples/ratings/schema/Rating.schema.yaml")
    schema_file = Path("C:/Users/Tanaya Mankad/source/repos/lattice/examples/fan_spec/schema/RS0003.schema.yaml")
    #schema_file = Path("C:/Users/Tanaya Mankad/source/repos/lattice/examples/fan_spec/schema/RS0001.schema.yaml")
    #schema_file = Path("C:/Users/Tanaya Mankad/source/repos/lattice/lattice/core.schema.yaml")
    path_to_schema = schema_file.parent
    with open(schema_file, 'r') as stream:
        config = yaml.load(stream, Loader=yaml.CLoader)
        LatticeSchema.schema_path=path_to_schema
        LatticeSchema(lattice_schema=config)
