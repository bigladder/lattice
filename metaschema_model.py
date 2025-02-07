from __future__ import annotations
import yaml
from pathlib import Path
from enum import Enum
from typing import Dict, List, Optional, Union, Literal, Any, ClassVar

from pydantic import BaseModel, RootModel, Field, model_validator, field_validator, BeforeValidator, AfterValidator
from pydantic.types import StringConstraints
from typing_extensions import Annotated, Self

from lattice import schema

schema_path: Path = Path().cwd()

# TODO: IPUnits
# TODO: validate and include core.schema.yaml items
# TODO: Different constraints, requirements
# TODO: Add Schema class' regexs and stuff
# TODO: Things like RequiredDataTypes, that are read in as strs, should be valid types
# TODO: If enum type (etc), has correct regex
# TODO: find missing required data elements in template-derived Data Groups, and Array constraints like [Numeric][1..] where I guess the size value has been moved to the Constraints list.
# TODO: So, for a schema group in lattice, each meta.schema.json only references definitions inside itself.
# This is posing a problem for Unit Systems that are defined in ASHRAE205.schema.yaml but used in a RatingsTemplate in other schema.
# I added the Unit Systems attribute to the Meta group in each sub-schema to get them to validate.

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

class Meta(BaseModel):
    class Config:
        extra = "forbid"

    Object_Type: Literal['Meta'] = Field( alias='Object Type')
    Title: Optional[str] = None
    Description: Optional[str] = None
    Version: Optional[str] = None
    Root_Data_Group: Optional[str] = Field(None, alias='Root Data Group')
    References: Optional[Annotated[List[LatticeSchema], BeforeValidator(get_references)]] = None
    Unit_Systems: Optional[Dict[Annotated[str, StringConstraints(pattern=r'^[A-Z]([A-Z]|[a-z]|[0-9])*$')], List[str]]] = Field(
        None, alias='Unit Systems'
    )

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
    Examples: List


class StringType(BaseModel):
    class Config:
        extra = "forbid"

    Object_Type: Literal['String Type'] = Field( alias='Object Type')
    Description: str
    Regular_Expression_Pattern: Optional[str] = Field(None, alias='Regular Expression Pattern')
    Examples: List
    Is_Regex: Optional[bool] = Field(None, alias='Is Regex')


class ConstraintsPattern(RootModel):
    root: Annotated[str, StringConstraints(
        pattern=r'^((>|>=|<=|<)(([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)))|(%(([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)))|(\[([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)(, ?([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?))*\])|((([a-z][a-z,0-9]*)(_([a-z,0-9])+)*)=(((([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?))|(".*")|(([A-Z]([A-Z]|[0-9])*)(_([A-Z]|[0-9])+)*)|(True|False))))|(:[A-Z]([A-Z]|[a-z]|[0-9])*:)|(([a-z][a-z,0-9]*)(_([a-z,0-9])+)*\(([A-Z]([A-Z]|[0-9])*)(_([A-Z]|[0-9])+)*(, ?([A-Z]([A-Z]|[0-9])*)(_([A-Z]|[0-9])+)*)*\))|(\[(\d*)\.\.(\d*)\])|(".*")$'
    )]


class ConstraintsAttribute(RootModel):
    root: Union[ConstraintsPattern, List[ConstraintsPattern]]


class ElementBasedConditionalRequiredPattern(RootModel):
    # TODO: Find all instances of data element pattern ^([a-z][a-z,0-9]*)(_([a-z,0-9])+)*$
    root: Annotated[str, StringConstraints(pattern=r'if (([a-z][a-z,0-9]*)(_([a-z,0-9])+)*)(!=|=)(True|False)')]

class RequiredAttribute(RootModel):
    root: Union[bool, ElementBasedConditionalRequiredPattern]


class EnumeratorAttributes(BaseModel):
    class Config:
        extra = "forbid"

    Description: Optional[str] = None
    Display_Text: Optional[str] = Field(None, alias='Display Text')
    Notes: Optional[Union[str, List[str]]] = None


class Enumerants(BaseModel):
    root: Dict[Annotated[str, StringConstraints(pattern=schema.EnumerationType.value_pattern)], Optional[EnumeratorAttributes]] = Field(
        None)


class Enumeration(BaseModel):
    class Config:
        extra = "forbid"

    Object_Type: Literal['Enumeration'] = Field(alias='Object Type')
    Enumerators: Enumerants


class StandardUnits(Enum):
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


class DataTypePattern(RootModel):
    root: Annotated[str, StringConstraints(
        pattern=r'^(((Integer|Numeric|Boolean|String|Pattern)|(UUID|Date|Timestamp|Version)|\{([A-Z]([A-Z]|[a-z]|[0-9])*)\}|<[A-Z]([A-Z]|[a-z]|[0-9])*>|:[A-Z]([A-Z]|[a-z]|[0-9])*:))|(\((((Integer|Numeric|Boolean|String|Pattern)|(UUID|Date|Timestamp|Version)|\{([A-Z]([A-Z]|[a-z]|[0-9])*)\}|<[A-Z]([A-Z]|[a-z]|[0-9])*>|:[A-Z]([A-Z]|[a-z]|[0-9])*:))(,\s*((Integer|Numeric|Boolean|String|Pattern)|(UUID|Date|Timestamp|Version)|\{([A-Z]([A-Z]|[a-z]|[0-9])*)\}|<[A-Z]([A-Z]|[a-z]|[0-9])*>|:[A-Z]([A-Z]|[a-z]|[0-9])*:))+\))|(\[([A-Z]([A-Z]|[a-z]|[0-9])*|\{([A-Z]([A-Z]|[a-z]|[0-9])*)\}|<[A-Z]([A-Z]|[a-z]|[0-9])*>)\])$'
    )]


class DataElementAttributes(BaseModel):
    Description: Optional[str] = None
    Data_Type: Optional[DataTypePattern] = Field(None, alias='Data Type')
    #Units: Optional[Union[StandardUnits, IPUnits]] = None
    Constraints: Optional[ConstraintsAttribute] = None
    Required: Optional[RequiredAttribute] = None
    Notes: Optional[Union[str, List[str]]] = None
    ID: Optional[bool] = None


class DataGroup(BaseModel):
    class Config:
        extra = 'forbid'

    Object_Type: Literal['Data Group'] = Field( alias='Object Type')
    Data_Group_Template: Optional[str] = Field(None, alias='Data Group Template')
    Data_Elements: Dict[Annotated[str, StringConstraints(pattern=r'^([a-z][a-z,0-9]*)(_([a-z,0-9])+)*$')], DataElementAttributes] = Field(
        ..., alias='Data Elements'
    )


class DataGroupTemplate(BaseModel):
    class Config:
        extra = 'forbid'

    Object_Type: Literal['Data Group Template'] = Field( alias='Object Type')
    Required_Data_Elements: Optional[
        Dict[Annotated[str, StringConstraints(pattern=r'^([a-z][a-z,0-9]*)(_([a-z,0-9])+)*$')], DataElementAttributes]
    ] = Field(None, alias='Required Data Elements')
    Unit_System: Optional[str] = Field(None, alias='Unit System')
    Required_Data_Types: Optional[List[str]] = Field(None, alias='Required Data Types', min_items=1)
    Data_Elements_Required: Optional[bool] = Field(None, alias='Data Elements Required')


class Item(RootModel):
    root: Union[DataGroup, DataGroupTemplate, Enumeration, Meta] = Field(..., discriminator="Object_Type")


class LatticeSchema(BaseModel):
    schema_path: ClassVar[Path] = Path().cwd()
    lattice_schema: Dict[str, Item]

    @model_validator(mode='after')
    def find_data_group_template(self) -> Self:
        referenceable_templates = []
        for group in self.lattice_schema.values(): # All the subdictionaries in self
            if isinstance(group.root, Meta) and group.root.References:
                for reference in group.root.References:
                    for (name,item) in reference.lattice_schema.items():
                        if isinstance(item.root, DataGroupTemplate):
                            referenceable_templates.append((name,item))

        for _, datagroup in [(k,v) for (k,v) in self.lattice_schema.items() if isinstance(v.root, DataGroup) and v.root.Data_Group_Template]:
            matched = False
            for template_name, _ in [(k,v) for (k,v) in self.lattice_schema.items() if isinstance(v.root, DataGroupTemplate)] + referenceable_templates:
                if datagroup.root.Data_Group_Template == template_name:
                    matched = True
            if not matched:
                raise Exception(f"Data Group Template definition {datagroup.root.Data_Group_Template} not found.")
        return self


if __name__ == "__main__":
    #schema_file = Path("C:/Users/Tanaya Mankad/source/repos/lattice/examples/fan_spec/schema/RS0003.schema.yaml")
    schema_file = Path("C:/Users/Tanaya Mankad/source/repos/lattice/lattice/core.schema.yaml")
    path_to_schema = schema_file.parent
    with open(schema_file, 'r') as stream:
        config = yaml.load(stream, Loader=yaml.CLoader)
        LatticeSchema.schema_path=path_to_schema
        LatticeSchema(lattice_schema=config)
