from .file_io import load, dump

import os
import re
import jsonschema
import posixpath

# -------------------------------------------------------------------------------------------------
class DataGroup:

    # The following regular expressions are explicity not Unicode
    array_type = r'^\[(.*?)\]'                       # Array of type 'Type' e.g. '[Type]'
                                                    # just the first [] pair; using non-greedy '?'
    minmax_range_type = r'^(?P<min>[0-9]*)(?P<ellipsis>\.*)(?P<max>[0-9]*)'    # Parse ellipsis range-notation e.g. '[1..]'
    alternative_type = r'^\((.*)\)'                  # Parentheses encapsulate a list of options
    enum_or_def = r'(\{|\<)(.*)(\}|\>)'
    numeric_type = r'[+-]?[0-9]*\.?[0-9]+|[0-9]+'   # Any optionally signed, floating point number
    scope_constraint = r'^:(.*):'                    # Lattice scope constraint for ID/Reference

    def __init__(self, name, type_list, ref_list=None, **kwargs):
        self._name = name
        self._types = type_list
        self._refs = ref_list

    def add_data_group(self, group_name, group_subdict):
        '''
        Process Data Group from the source schema into a properties node in json.

        :param group_name:      Data Group name; this will become a schema definition key
        :param group_subdict:   Dictionary of Data Elements where each element is a key
        '''
        elements = {'type': 'object',
                    'properties' : dict()}
        required = list()
        dependencies = dict()
        for e in group_subdict:
            element = group_subdict[e]
            if 'Description' in element:
                elements['properties'][e] = {'description' : element['Description']}
            if 'Data Type' in element:
                self._create_type_entry(group_subdict[e], elements, e)
            if 'Units' in element:
                elements['properties'][e]['units'] = element['Units']
            if 'Notes' in element:
                elements['properties'][e]['notes'] = element['Notes']
            if 'Required' in element:
                req = element['Required']
                if isinstance(req, bool):
                    if req == True:
                        required.append(e)
                elif req.startswith('if'):
                    self._construct_requirement_if_then(elements, dependencies, req[3:], e)
        if required:
            elements['required'] = required
        if dependencies:
            elements['dependencies'] = dependencies
        elements['additionalProperties'] = False
        return {group_name : elements}


    def _construct_requirement_if_then(self,
                                       conditionals_list : dict,
                                       dependencies_list : dict,
                                       requirement_str : str,
                                       requirement : str):
        '''
        Construct paired if-then json entries for conditional requirements.

        :param target_list_to_append:   List of dictionaries, modified in-situ with an if key and
                                        an associated then key
        :param requirement_str:         Raw requirement string using A205 syntax
        :param requirement:             This item's presence is dependent on the above condition
        '''
        separator = r'\sand\s'
        collector = 'allOf'
        selector_dict = {'properties' : {collector : dict()}}
        requirement_list = re.split(separator, requirement_str)
        dependent_req = r'(?P<selector>!?[0-9a-zA-Z_]*)((?P<is_equal>!?=)(?P<selector_state>[0-9a-zA-Z_]*))?'

        for req in requirement_list:
            m = re.match(dependent_req, req)
            if m:
                selector = m.group('selector')
                if m.group('is_equal'):
                    is_equal = False if '!' in m.group('is_equal') else True
                    selector_state = m.group('selector_state')
                    if 'true' in selector_state.lower():
                        selector_state = True
                    elif 'false' in selector_state.lower():
                        selector_state = False
                    selector_dict['properties'][collector][selector] = {'const' : selector_state} if is_equal else {'not' : {'const' : selector_state} }
                else: # prerequisite type
                    if dependencies_list.get(selector):
                        dependencies_list[selector].append(requirement)
                    else:
                        if '!' in selector:
                            dependencies_list[selector.lstrip('!')] = {'not' : {'required' : [requirement]}}
                        else:
                            dependencies_list[selector] = [requirement]

        if selector_dict['properties'][collector].keys():
            # Conditional requirements are each a member of a list
            if conditionals_list.get('allOf') == None:
                conditionals_list['allOf'] = list()

            for conditional_req in conditionals_list['allOf']:
                if conditional_req.get('if') == selector_dict: # condition already exists
                    conditional_req['then']['required'].append(requirement)
                    return
            conditionals_list['allOf'].append(dict())
            conditionals_list['allOf'][-1]['if'] = selector_dict
            conditionals_list['allOf'][-1]['then'] = {'required' : [requirement]}


    def _create_type_entry(self, parent_dict, target_dict, entry_name):
        '''
        Create json type node and its nested nodes if necessary.
        :param parent_dict:     A Data Element's subdictionary, from source schema
        :param target_dict:     The json definition node that will be populated
        :param entry_name:      Data Element name
        '''
        m = re.findall(DataGroup.array_type, parent_dict['Data Type'])
        if entry_name not in target_dict['properties']:
            target_dict['properties'][entry_name] = dict()
        target_property_entry = target_dict['properties'][entry_name]
        if m: # Data Element is an array
            # 1. 'type' entry
            target_property_entry['type'] = 'array'
            # 2. 'm[in/ax]Items' entry
            if len(m) > 1:
                # Parse ellipsis range-notation e.g. '[1..]'
                mnmx = re.match(DataGroup.minmax_range_type, m[1])
                target_property_entry['minItems'] = int(mnmx.group('min'))
                if (mnmx.group('ellipsis') and mnmx.group('max')):
                    target_property_entry['maxItems'] = int(mnmx.group('max'))
                elif not mnmx.group(2):
                    target_property_entry['maxItems'] = int(mnmx.group('min'))
            # 3. 'items' entry
            target_property_entry['items'] = dict()
            self._get_simple_type(m[0], target_property_entry['items'])
            self._get_numeric_constraints(parent_dict.get('Constraints'), target_property_entry['items'])
        else:
            # If the type is oneOf a set
            m = re.match(DataGroup.alternative_type, parent_dict['Data Type'])
            if m:
                types = [t.strip() for t in m.group(1).split(',')]
                selection_key, selections = parent_dict['Constraints'].split('(')
                target_dict['allOf'] = list()
                for s, t in zip(selections.split(','), types):
                    target_dict['allOf'].append(dict())
                    self._construct_selection_if_then(target_dict['allOf'][-1], selection_key, s, entry_name)
                    self._get_simple_type(t, target_dict['allOf'][-1]['then']['properties'][entry_name])
            elif parent_dict['Data Type'] in ['ID', 'Reference']:
                m = re.match(DataGroup.scope_constraint, parent_dict['Constraints'])
                if m:
                    target_property_entry['scopedType'] = parent_dict['Data Type']
                    target_property_entry['scope'] = m.group(1)
                    self._get_simple_type(parent_dict['Data Type'], target_property_entry)
            else:
                # 1. 'type' entry
                self._get_simple_type(parent_dict['Data Type'], target_property_entry)
                # 2. 'm[in/ax]imum' entry
                self._get_numeric_constraints(parent_dict.get('Constraints'), target_property_entry)


    def _construct_selection_if_then(self, target_dict_to_append, selector, selection, entry_name):
        '''
        Construct paired if-then json entries for allOf collections translated from source-schema
        "selector" Constraints.

        :param target_dict_to_append:   This dictionary is modified in-situ with an if key and
                                        associated then key
        :param selector:                Constraints key
        :param selection:               Item from constraints values list.
        :param entry_name:              Data Element for which the Data Type must match the
                                        Constraint
        '''
        target_dict_to_append['if'] = {'properties' : {selector : {'const' : ''.join(ch for ch in selection if ch.isalnum())} } }
        target_dict_to_append['then'] = {'properties' : {entry_name : dict()}}


    def _get_simple_type(self, type_str, target_dict_to_append):
        ''' Return the internal type described by type_str, along with its json-appropriate key.
            First, attempt to capture enum, definition, or special string type as references;
            then default to fundamental types with simple key "type".

            :param type_str:                Input string from source schema's Data Type key
            :param target_dict_to_append:   The json "items" node
        '''
        internal_type = None
        m = re.match(DataGroup.enum_or_def, type_str)
        if m:
            internal_type = m.group(2)
        else:
            internal_type = type_str
        # Look through the references to assign a source to the type
        for key in self._refs:
            if internal_type in self._refs[key]:
                internal_type = key + '.schema.json#/definitions/' + internal_type
                target_dict_to_append['$ref'] = internal_type
                return
        try:
            if '/' in type_str:
                # e.g. "Numeric/Null" becomes a list of 'type's
                target_dict_to_append['type'] = [self._types[t] for t in type_str.split('/')]
            else:
                target_dict_to_append['type'] = self._types[type_str]
        except KeyError:
            print('Type not processed:', type_str)
        return


    def _get_numeric_constraints(self, constraints_str, target_dict):
        '''
        Process numeric Constraints into fields.

        :param constraints_str:     Raw numerical limits and/or multiple information
        :param target_dict:         json property node
        '''
        if constraints_str is not None:
            constraints = constraints_str if isinstance(constraints_str, list) else [constraints_str]
            minimum=None
            maximum=None
            for c in constraints:
                try:
                    # Process numeric constraints
                    numerical_value = re.findall(DataGroup.numeric_type, c)[0]
                    if '>' in c:
                        minimum = (float(numerical_value) if 'number' in target_dict['type'] else int(numerical_value))
                        mn = 'exclusiveMinimum' if '=' not in c else 'minimum'
                        target_dict[mn] = minimum
                    elif '<' in c:
                        maximum = (float(numerical_value) if 'number' in target_dict['type']  else int(numerical_value))
                        mx = 'exclusiveMaximum' if '=' not in c else 'maximum'
                        target_dict[mx] = maximum
                    elif '%' in c:
                        target_dict['multipleOf'] = int(numerical_value)
                except IndexError:
                    pass
                except ValueError:
                    pass
                except KeyError:
                    # 'type' not in dictionary
                    pass


# -------------------------------------------------------------------------------------------------
class Enumeration:

    def __init__(self, name, description=None):
        self._name = name
        self._enumerants = list() # list of tuple:[value, description, display_text, notes]
        self.entry = dict()
        self.entry[self._name] = dict()
        if description:
            self.entry[self._name]['description'] = description

    def add_enumerator(self, value, description=None, display_text=None, notes=None):
        '''Store information grouped as a tuple per enumerant.'''
        self._enumerants.append((value, description, display_text, notes))

    def create_dictionary_entry(self):
        '''
        Convert information currently grouped per enumerant, into json groups for
        the whole enumeration.
        '''
        z = list(zip(*self._enumerants))
        enums = {'type': 'string',
                 'enum' : z[0]}
        if any(z[2]):
            enums['enum_text'] = z[2]
        if any(z[1]):
            enums['descriptions'] = z[1]
        if any(z[3]):
            enums['notes'] = z[3]
        self.entry[self._name] = {**self.entry[self._name], **enums}
        return self.entry


# -------------------------------------------------------------------------------------------------
class JSON_translator:
    def __init__(self, **kwargs):
        ''' '''
        self._references = dict()
        self._fundamental_data_types = dict()
        self._schema_object_types = ['Data Group', 'String Type', 'Enumeration'] # "Basic" object types - are there more?
        self._kwargs = kwargs

    def load_source_schema(self, input_file_path):
        '''Load and process a yaml schema into its json schema equivalent.'''
        self._schema = {'$schema': 'http://json-schema.org/draft-07/schema#',
                        'title': None,
                        'description': None,
                        'definitions' : dict()}
        self._references.clear()
        self._source_dir = os.path.dirname(os.path.abspath(input_file_path))
        self._schema_name = os.path.splitext(os.path.splitext(os.path.basename(input_file_path))[0])[0]
        self._fundamental_data_types.clear()
        self._contents = load(input_file_path)
        sch = dict()
        # Iterate through the dictionary, looking for known types
        for base_level_tag in self._contents:
            if 'Object Type' in self._contents[base_level_tag]:
                obj_type = self._contents[base_level_tag]['Object Type']
                if obj_type == 'Meta':
                    self._load_meta_info(self._contents[base_level_tag])
                elif obj_type == 'String Type':
                    if 'Is Regex' in self._contents[base_level_tag]:
                        sch.update({base_level_tag : {"type":"string", "regex":True}})
                    else:
                        sch.update({base_level_tag : {"type":"string", "pattern":self._contents[base_level_tag]['JSON Schema Pattern']}})
                elif obj_type == 'Enumeration':
                    sch.update(self._process_enumeration(base_level_tag))
                elif obj_type in self._schema_object_types:
                    dg = DataGroup(base_level_tag, self._fundamental_data_types, self._references)
                    sch.update(dg.add_data_group(base_level_tag, self._contents[base_level_tag]['Data Elements']))
        self._schema['definitions'] = sch
        return self._schema

    def _load_meta_info(self, schema_section):
        '''Store the global/common types and the types defined by any named references.'''
        self._schema['title'] = schema_section['Title']
        self._schema['description'] = schema_section['Description']
        if 'Version' in schema_section:
            self._schema['version'] = schema_section['Version']
        if 'Root Data Group' in schema_section:
            self._schema['$ref'] = self._schema_name + '.schema.json#/definitions/' + schema_section['Root Data Group']
        # Create a dictionary of available external objects for reference
        refs = {'core' : os.path.join(os.path.dirname(__file__),'core.schema.yaml'),
                f'{self._schema_name}' : os.path.join(self._source_dir, f'{self._schema_name}.schema.yaml')}
        if 'References' in schema_section:
            for ref in schema_section['References']:
                refs.update({f'{ref}' : os.path.join(self._source_dir, ref + '.schema.yaml')})
        for ref_name in refs:
            try:
                ext_dict = load(refs[ref_name])
                # Only one of the references should contain Data Group Templates
                for template_name in [ext_dict[name]['Name'] for name in ext_dict if ext_dict[name]['Object Type'] == 'Data Group Template']:
                    self._schema_object_types.append(template_name)
                # Template data groups may exist in any of the references
                self._references[ref_name] = [base_item for base_item in ext_dict if ext_dict[base_item]['Object Type'] in self._schema_object_types]
                for base_item in [name for name in ext_dict if ext_dict[name]['Object Type'] == 'Data Type']:
                    self._fundamental_data_types[base_item] = ext_dict[base_item]['JSON Schema Type']
            except RuntimeError:
                raise RuntimeError(f'{refs[ref_name]} reference file does not exist.') from None

    def _process_enumeration(self, name_key):
        ''' Collect all Enumerators in an Enumeration block. '''
        enums = self._contents[name_key]['Enumerators']
        description = self._contents[name_key].get('Description')
        definition = Enumeration(name_key, description)
        for key in enums:
            try:
                descr = enums[key]['Description']  if 'Description'  in enums[key] else None
                displ = enums[key]['Display Text'] if 'Display Text' in enums[key] else None
                notes = enums[key]['Notes']        if 'Notes'        in enums[key] else None
                definition.add_enumerator(key, descr, displ, notes)
            except TypeError: # key's value is None
                definition.add_enumerator(key)
        return definition.create_dictionary_entry()


# -------------------------------------------------------------------------------------------------
class JSONSchemaValidator:
    def __init__(self, schema_path):
        with open(schema_path) as schema_file:
            uri_path = os.path.abspath(os.path.dirname(schema_path))
            if os.sep != posixpath.sep:
                uri_path = posixpath.sep + uri_path
            resolver = jsonschema.RefResolver(f'file://{uri_path}/', schema_file)
            self.validator = jsonschema.Draft7Validator(load(schema_path), resolver=resolver)

    def validate(self, instance_path):
        instance = load(instance_path)
        errors = sorted(self.validator.iter_errors(instance), key=lambda e: e.path)
        file_name =  os.path.basename(instance_path)
        if len(errors) == 0:
            print(f"Validation successful for {file_name}")
        else:
            messages = []
            for error in errors:
                messages.append(f"{error.message} ({'.'.join([str(x) for x in error.path])})")
            messages = [f"{i}. {message}" for i, message in enumerate(messages, start=1)]
            message_str = '\n  '.join(messages)
            raise Exception(f"Validation failed for {file_name} with {len(messages)} errors:\n  {message_str}")

# -------------------------------------------------------------------------------------------------
def generate_core_json_schema():
    '''Create JSON schema from core YAML schema'''
    j = JSON_translator()
    core_instance = j.load_source_schema(os.path.join(os.path.dirname(__file__),'core.schema.yaml'))
    return core_instance

# -------------------------------------------------------------------------------------------------
def search_for_reference(referenced_schemas: dict, schema_path: str, subdict: dict) -> bool:
    '''Search for $ref keys and replace the associated dictionary entry in-situ.'''
    subbed = False
    if '$ref' in subdict.keys():
        subbed = True
        # parse the ref and locate the sub-dict
        source_file, ref_loc = subdict['$ref'].split('#')
        ref = referenced_schemas[os.path.splitext(source_file)[0]]
        key_tree = ref_loc.lstrip('/').split('/')
        sub_d = ref[key_tree[0]]
        for k in key_tree[1:]:
            sub_d = sub_d[k]
        # replace the $ref with its contents
        subdict.update(sub_d)
        subdict.pop('$ref')
        # re-search the substituted dictionary
        subbed = search_for_reference(referenced_schemas, schema_path, subdict)
    else:
        for key in subdict:
            if isinstance(subdict[key], dict):
                subbed = search_for_reference(referenced_schemas, schema_path, subdict[key])
            if isinstance(subdict[key], list):
                for entry in [item for item in subdict[key] if isinstance(item, dict)]:
                    subbed = search_for_reference(referenced_schemas, schema_path, entry)
    return subbed

# -------------------------------------------------------------------------------------------------
def generate_json_schema(source_schema_input_path, json_schema_output_path):
    '''Create reference-resolved JSON schema from YAML source schema.'''
    if os.path.isfile(source_schema_input_path) and '.schema.yaml' in source_schema_input_path:
        schema_dir = os.path.abspath(os.path.dirname(source_schema_input_path))
        json_schema_output_dir = os.path.abspath(os.path.dirname(json_schema_output_path))
        j = JSON_translator()
        main_schema_instance = j.load_source_schema(source_schema_input_path)
        schema_ref_map = {'core.schema' : generate_core_json_schema()}
        for ref_source in os.listdir(schema_dir):
            schema_ref_map[os.path.splitext(ref_source)[0]] = j.load_source_schema(os.path.join(schema_dir, ref_source))
        while search_for_reference(schema_ref_map, schema_dir, main_schema_instance):
            pass
        dump(main_schema_instance, json_schema_output_path)

# -------------------------------------------------------------------------------------------------
def get_scope_locations(schema: dict, scopes_dict: dict, scope_key: str='Reference', lineage: list=None):
    if not lineage:
        lineage = list()
    for key in schema:
        if key == 'scopedType' and schema[key] == scope_key:
            scopes_dict['.'.join(lineage)] = schema['scope'] # key is a dot-separated path
        elif isinstance(schema[key], dict):
            get_scope_locations(schema[key], scopes_dict, scope_key, lineage + [key])
        elif isinstance(schema[key], list):
            for entry in [item for item in schema[key] if isinstance(item, dict)]:
                get_scope_locations(entry, scopes_dict, scope_key, lineage + [key])

# -------------------------------------------------------------------------------------------------
def get_reference_value(data_dict: dict, lineage: list) -> str:
    test_reference = data_dict
    for adr in lineage:
        if test_reference.get(adr):
            if isinstance(test_reference[adr], list):
                for item in test_reference[adr]:
                    return get_reference_value(item, lineage[1:])
            else:
                test_reference = test_reference[adr]
        else:
            return None
    return test_reference

# -------------------------------------------------------------------------------------------------
def postvalidate_references(input_file, input_schema):
    id_scopes = dict()
    reference_scopes = dict()
    get_scope_locations(load(input_schema), scope_key='ID', scopes_dict=id_scopes)
    get_scope_locations(load(input_schema), scope_key='Reference', scopes_dict=reference_scopes)
    data = load(input_file)
    ids = list()
    for id_loc in [id for id in id_scopes if id.startswith('properties')]:
        lineage = [level for level in id_loc.split('.') if level not in ['properties', 'items']]
        ids.append(get_reference_value(data, lineage))
    for ref in [r for r in reference_scopes if r.startswith('properties')]:
        lineage = [level for level in ref.split('.') if level not in ['properties', 'items']]
        reference_scope = get_reference_value(data, lineage)
        if reference_scope != None and reference_scope not in ids:
            raise Exception(f'Scope mismatch in {input_file}; {reference_scope} not in ID scope list {ids}.')

# -------------------------------------------------------------------------------------------------
def validate_file(input_file, input_schema):
    v = JSONSchemaValidator(input_schema)
    v.validate(input_file)

# -------------------------------------------------------------------------------------------------
def postvalidate_file(input_file, input_schema):
    postvalidate_references(input_file, input_schema) 
