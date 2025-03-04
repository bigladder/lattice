C++ Generation
==============

The C++ header and source generation are accomplished through a Python class hierarchy rooted in the classes HeaderEntry and ImplementationEntry. Each translateable element in schema has an associated subclass that parses and formats it as a node of a data tree. The entire tree is then serialized into a compilable C++ code file.

For example, high-level schema Objects are translated as follows.

| Object Type           | C++ type              | _HeaderEntry_ Python subclass(es)
|-------------------    | --------              | --------------------
| Schema                | `namespace`           | _HeaderEntry_
| Data Group            | `struct`              | _Struct_
| Data Element          | public data member    | _DataElement_
|||                                               _DataElementIsSetFlag_
|||                                               _DataElementStaticMetainfo_
| Enumerator            | `enum`                | _Enumeration_
|||                                               _EnumSerializationDeclaration_
| Data Group Template   | base class            | Realization of _HeaderEntryExtensionInterface_
|||                                               _MemberFunctionOverrideDeclaration_
|

A _Struct_ is initialized as a child node of a _HeaderEntry_ (a namespace). A _DataElement_, _DataElementIsSetFlag_, or _DataElementStaticMetainfo_ object is initialized as a child node of a _Struct_ object. The resulting tree for a data element named "impeller_type" would serialize like so:
```
namespace RS0003 {
    struct ProductInformation {
        rs0003::ImpellerType impeller_type;
        bool impeller_type_is_set;
        const static std::string_view impeller_type_units;
        const static std::string_view impeller_type_description;
        const static std::string_view impeller_type_name;
    };
}
```

## Customizations

### Header declarations

Data Group and Data Element customizations are possible for any Data Group that has an Object Type of "Data Group Template." A Python extension class must inherit the interface `lattice.cpp.header_translator.HeaderEntryExtensionInterface` for each data group template that needs customization, and implement the method `process_data_group(self, parent_node: HeaderEntry)`.

In addition, a user should define a HeaderEntry subclass that defines a sub-node of any node in the namespace, plus its text representation. The subclass will automatically inherit the parameters `name` and `parent` as its first two `__init__` parameters, and the user may add others. At minimum, the subclass must define a `__str__` function to serialize the node into text. (Beginning the string(s) with `self._indent` will bring the code into place under its parent node.) Because the Schema is parsed into a tree-like data structure, simply constructing the user-defined subclass inside `process_data_group` when its parent node is processed will place it correctly in the header serialization.

Method `process_data_group` is called once for each Data Group Template object in a schema; the parent_node at that call is the Schema namespace. The `child_entries` of the namespace node are iterable and correspond to Objects of the Schema. (The method may be called recursively to traverse all the nodes of the header "tree," if necessary.) In this way, an extension fleshing out a particular template or base class has access to all other Schema objects, no matter their type, and can augment or modify each one by its _HeaderEntry_ subclass type.

The extension is registered to the application when it defines the extension class with keyword "base_class" set equal to the fully-qualified template (base class) name. For example,
```
class GridVarExtension(HeaderEntryExtensionInterface, base_class="ashrae205::GridVariablesTemplate"):
    def process_data_group(self, parent_node: HeaderEntry):
        ...
```



> See [this example](./examples/fan_spec/cpp/extensions\add_performance_variable_enums.py) for a working extension that generates a counting enum for the variables in a struct, such as the one below:
> ```
> struct GridVariables : ashrae205::GridVariablesTemplate {
>     std::vector<double> shaft_power;
>     bool shaft_power_is_set;
>     const static std::string_view shaft_power_description;
>     const static std::string_view shaft_power_name;
>     std::vector<double> shaft_rotational_speed;
>     bool shaft_rotational_speed_is_set;
>     const static std::string_view shaft_rotational_speed_description;
>     const static std::string_view shaft_rotational_speed_name;
> };
> ```
> This is appended to become:
>```
> struct GridVariables : ashrae205::GridVariablesTemplate {
>     std::vector<double> shaft_power;
>     bool shaft_power_is_set;
>     const static std::string_view shaft_power_description;
>     const static std::string_view shaft_power_name;
>     std::vector<double> shaft_rotational_speed;
>     bool shaft_rotational_speed_is_set;
>     const static std::string_view shaft_rotational_speed_description;
>     const static std::string_view shaft_rotational_speed_name;
>     enum {
>         shaft_power_index,
>         shaft_rotational_speed_index,
>         index_count
>     };
> };
> ```

### Implementation entries

Implementation extensions are also supported. In practice, a _HeaderEntry_ subclass contains all of the information needed for both the .h entry and the .cpp entry for a data structure. An _ImplementationEntry_ is built from a corresponding _HeaderEntry_; its subclasses require an initialization parameter of type _HeaderEntry_ (or a subclass).

For example, here are a few mappings used internally to serialize Schema objects:

| _ImplementationEntry_ subclass    | uses _HeaderEntry_ subclass
|----------------------             | --------------------
|  StructSerialization              | Struct
|  ElementSerialization             | DataElement
|  DataElementStaticInitialization  | DataElementStaticMetainfo
|  FunctionalDefinition             | FunctionalHeaderEntry
|  MemberFunctionDefinition         | FunctionalHeaderEntry
|

As with extensions to the header-declared objects, a user may define a new extension module with a user-defined _ImplementationEntry_ that generates the necessary implementation code using parameters extracted from its corresponding _HeaderEntry_. Then, the module should create an extension class that realizes the `lattice.cpp.cpp_entries.CPPExtensionInterface`.  The class must provide an override of
```
process_data_group(self,
                   reference_header_entry: HeaderEntry,
                   parent_node: ImplementationEntry)
```
where the `reference_header_entry` and `parent_node` are linked (and exist at the top level as children of the Schema namespace). The implication is that based on the header entry's (or its children's) type, instances of the associated user-defined _ImplementationEntry(s)_ will be constructed as sub-nodes of `parent_node`.

(Note that there is no class keyword "base_class" required for these extensions; because header entries have all been constructed, simply checking the type of `reference_header_entry` (or, equivalently, `parent_node`) inside the method is all that's needed to associate an implementation with a declaration.)

### Loading and registering

Import:

`from lattice.cpp.extension_loader import load_extensions`

Before calling `lattice.generate_cpp_project()`, call
`load_extensions(path_to_extensions_directory)`

### Debugging with logging

There is a tracing log embedded in the C++ code generating classes, which may be used in user-derived classes as well. The user must have an active logger in their project with the active level set to DEBUG.

Simply add a call to `self.trace()` at the end of a derived dataclass' `__post_init__` code for an output containing each piece of serialized text and the class that generated it.