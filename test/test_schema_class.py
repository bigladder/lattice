from lattice.schema import Schema
import pathlib


def test_schema():
    schema = Schema(pathlib.Path("examples", "fan_spec", "schema", "RS0003.schema.yaml"))
    for data_group in schema.data_groups.values():
        print(f"\nData Group: {data_group.name}")
        for data_element in data_group.data_elements.values():
            print(f"  {data_element.name}")
            print(f"    {data_element.description}")
    for enumeration in schema.enumerations.values():
        print(f"\nEnumeration: {enumeration.name}")
        for enumerator in enumeration.enumerators.values():
            print(f"  {enumerator.name}")

    print(schema.root_data_group.name)
