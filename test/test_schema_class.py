from lattice.schema import Schema, DataGroupType
import pathlib


def test_schema_class():
    schema = Schema(pathlib.Path("examples", "fan_spec", "schema", "RS0003.schema.yaml"))
    # for data_group in schema.data_groups.values():
    #     print(f"\nData Group: {data_group.name}")
    #     for data_element in data_group.data_elements.values():
    #         print(f"  {data_element.name}")
    #         print(f"    {data_element.description}")
    # for enumeration in schema.enumerations.values():
    #     print(f"\nEnumeration: {enumeration.name}")
    #     for enumerator in enumeration.enumerators.values():
    #         print(f"  {enumerator.name}: {enumerator.description}")

    print("\n" * 2)

    # print(schema.root_data_group.name)

    for data_group_data_element, level in schema.walk():
        print(f"{'  '*level}- {data_group_data_element.name}: {data_group_data_element.data_type.data_group_name}")

    print("\n" * 2)

    print(schema.to_json_schema())
