from lattice.schema import Schema


def schema_to_json_schema(schema: Schema) -> dict:
    json_schema_dictionary = {}
    if schema.parent_schema is None:
        pass
