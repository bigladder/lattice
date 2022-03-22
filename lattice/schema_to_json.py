from . import meta_schema
from .file_io import load, dump, get_extension

import json
import yaml
import os
from collections import OrderedDict
import re
import jsonschema
import cbor2


def compare_dicts(original, modified, error_list):
    o = load(original)
    m = load(modified)
    return dict_compare(o, m, error_list, level=0, lineage=None, hide_value_mismatches=False)

# https://stackoverflow.com/questions/4527942/comparing-two-dictionaries-and-checking-how-many-key-value-pairs-are-equal
def dict_compare(d1, d2, errors, level=0, lineage=None, hide_value_mismatches=False, hide_key_mismatches=False):
    ''' Compare two order-independent dictionaries, labeling added or deleted keys or mismatched values. '''
    if not lineage:
        lineage = list()
    if d1 == d2:
        return True
    else:
        if isinstance(d1, dict) and isinstance(d2, dict):
            d1_keys = sorted(list(d1.keys()))
            d2_keys = sorted(list(d2.keys()))
            if d1_keys != d2_keys:
                added = [k for k in d2_keys if k not in d1_keys]
                removed = [k for k in d1_keys if k not in d2_keys]
                err = ''
                if added and not hide_key_mismatches:
                    errors.append(f'Keys added to second dictionary at level {level}, lineage {lineage}: {added}')
                if removed and not hide_key_mismatches:
                    errors.append(f'Keys removed from first dictionary at level {level}, lineage {lineage}: {removed}.')
                return False
            else:
            # Enter this part of the code if both dictionaries have all keys shared at this level
                shared_keys = d1_keys
                for k in shared_keys:
                    dict_compare(d1[k], d2[k], errors, level+1, lineage+[k], hide_value_mismatches, hide_key_mismatches)
        elif d1 != d2:
            # Here, we could use the util.objects_near_equal to compare objects. Currently, d1 and
            # d2 may have any type, i.e. float 1.0 will be considered equal to int 1.
            err = f'Mismatch in values: "{d1}" vs. "{d2}" at lineage {lineage}.'
            if not hide_value_mismatches:
                errors.append(err)
            return False


# -------------------------------------------------------------------------------------------------
class DataGroup:

    array_type = r'\[(.*?)\]'                       # Array of Type notation e.g. '[Type]'
    minmax_range_type = r'([0-9]*)(\.*)([0-9]*)'    # Parse ellipsis range-notation e.g. '[1..]'
    alternative_type = r'\((.*)\)'                  # Parentheses encapsulate a list of options
    enum_or_def = r'(\{|\<)(.*)(\}|\>)'

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
                if isinstance(req, bool) and req == True:
                    required.append(e)
                elif req.startswith('if'):
                    if '!=' in req:
                        self._construct_requirement_if_else(elements, req.split(' ')[1].split('!')[0],
                                                            False, req.split('=')[1], e)
                    elif '=' in req:
                        self._construct_requirement_if_else(elements, req.split(' ')[1].split('=')[0],
                                                            True, req.split('=')[1], e)
                    elif '!' in req:
                        # convert yaml (iff !B then A) into json (if B then required(!A))
                        dependency = req.split('!')[1]
                        dependencies[dependency] = {'not' : {'required' : [e]}}
                    else:
                        dependency = req.split(' ')[1]
                        dependencies[dependency] = [e]
        if required:
            elements['required'] = required
        if dependencies:
            elements['dependencies'] = dependencies
        elements['additionalProperties'] = False
        return {group_name : elements}


    def _construct_requirement_if_else(self,
                                       target_dict_to_append,
                                       selector, is_equal, selector_state, requirement):
        '''
        Construct paired if-else json entries for conditional requirements.

        :param target_dict_to_append:   This dictionary is modified in-situ with an if key and
                                        an associated then key
        :param selector:                see selector_state
        :param is_equal:                see selector_state
        :param selector_state:          Format the condition {selector} [is/isn't] {is_equal}
                                        {selector_state}
        :param requirement:             This item's presence is dependent on the above condition
        '''
        if 'true' in selector_state.lower():
            selector_state = True
        elif 'false' in selector_state.lower():
            selector_state = False
        selector_dict = ({'properties' : {selector : {'const' : selector_state} } } if is_equal
                         else {'properties' : {selector : {'not' : {'const' : selector_state} } } })
        if target_dict_to_append.get('if') == selector_dict: # condition already exists
            target_dict_to_append['then']['required'].append(requirement)
        else:
            target_dict_to_append['if'] = selector_dict
            target_dict_to_append['then'] = {'required' : [requirement]}


    def _create_type_entry(self, parent_dict, target_dict, entry_name):
        '''
        Create json type node and its nested nodes if necessary.
        :param parent_dict:     A Data Element's subdictionary, from source schema
        :param target_dict:     The json definition node that will be populated
        :param entry_name:      Data Element name
        '''
        try:
            # If the type is an array, extract the surrounding [] first (using non-greedy qualifier "?")
            m = re.findall(DataGroup.array_type, parent_dict['Data Type'])
            target_property_entry = target_dict['properties'][entry_name]
            if m:
                # 1. 'type' entry
                target_property_entry['type'] = 'array'
                # 2. 'm[in/ax]Items' entry
                if len(m) > 1:
                    # Parse ellipsis range-notation e.g. '[1..]'
                    mnmx = re.match(DataGroup.minmax_range_type, m[1])
                    target_property_entry['minItems'] = int(mnmx.group(1))
                    if (mnmx.group(2) and mnmx.group(3)):
                        target_property_entry['maxItems'] = int(mnmx.group(3))
                    elif not mnmx.group(2):
                        target_property_entry['maxItems'] = int(mnmx.group(1))
                # 3. 'items' entry
                target_property_entry['items'] = dict()
                self._get_simple_type(m[0], target_property_entry['items'])
                if 'Constraints' in parent_dict:
                    self._get_simple_constraints(parent_dict['Constraints'], target_dict['items'])
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
                else:
                    # 1. 'type' entry
                    self._get_simple_type(parent_dict['Data Type'], target_property_entry)
                    # 2. 'm[in/ax]imum' entry
                    self._get_simple_constraints(parent_dict['Constraints'], target_property_entry)
        except KeyError as ke:
            #print('KeyError; no key exists called', ke)
            pass


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


    def _get_simple_constraints(self, constraints_str, target_dict):
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
                    numerical_value = re.findall(r'[+-]?\d*\.?\d+|\d+', c)[0]
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
                    elif 'string' in target_dict['type']:  # String pattern match
                        target_dict['pattern'] = c.replace('"','')  # TODO: Find better way to remove quotes.
                except IndexError:
                    # Constraint was non-numeric
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

    def load_common_schema(self, input_file_path):
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
                        sch = {**sch, **({base_level_tag : {"type":"string", "regex":True}})}
                    else:
                        sch = {**sch, **({base_level_tag : {"type":"string", "pattern":self._contents[base_level_tag]['JSON Schema Pattern']}})}
                elif obj_type == 'Enumeration':
                    sch = {**sch, **(self._process_enumeration(base_level_tag))}
                elif obj_type in self._schema_object_types:
                    dg = DataGroup(base_level_tag, self._fundamental_data_types, self._references)
                    sch = {**sch, **(dg.add_data_group(base_level_tag,
                                     self._contents[base_level_tag]['Data Elements']))}
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
        if 'Data Group Templates' in schema_section:
            self._schema_object_types += [schema_section['Data Group Templates'][f'{obj_type}']['Object Type Name'] for obj_type in schema_section['Data Group Templates']]
        # Create a dictionary of available external objects for reference
        refs = {'core' : os.path.join(os.path.dirname(__file__),'core.schema.yaml'), 
                f'{self._schema_name}' : os.path.join(self._source_dir, f'{self._schema_name}.schema.yaml')}
        if 'References' in schema_section:
            for ref in schema_section['References']:
                refs.update({f'{ref}' : os.path.join(self._source_dir, ref + '.schema.yaml')})
        for ref_name in refs:
            try:
                ext_dict = load(refs[ref_name])
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
        with open(schema_path) as meta_schema_file:
            uri_path = os.path.abspath(os.path.dirname(schema_path))
            # if os.sep != posixpath.sep:
            #     uri_path = posixpath.sep + uri_path
            resolver = jsonschema.RefResolver(f'file://{uri_path}/', meta_schema_file)
            self.validator = jsonschema.Draft7Validator(json.load(meta_schema_file), resolver=resolver)

    def validate(self, instance_path):
        if instance_path.endswith('.json'):
            with open(os.path.join(instance_path), 'r') as input_file:
                instance = json.load(input_file)
        if instance_path.endswith('.cbor'):
            with open(os.path.join(instance_path), 'rb') as fp:
                instance = cbor2.decoder.load(fp)
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
def generate_json_schema(input_path_to_file, output_dir):
    '''Create JSON schema from YAML source schema.'''
    if not os.path.isdir(output_dir):
        os.mkdir(output_dir)
    if os.path.isfile(input_path_to_file) and '.schema.yaml' in input_path_to_file:
        input_dir, file = os.path.split(input_path_to_file)
        j = JSON_translator()
        file_name_root = os.path.splitext(file)[0]
        core_instance = j.load_common_schema(os.path.join(os.path.dirname(__file__),'core.schema.yaml'))
        dump(core_instance, os.path.join(output_dir, 'core.schema.json'))
        schema_instance = j.load_common_schema(input_path_to_file)
        dump(schema_instance, os.path.join(output_dir, file_name_root + '.json'))

# -------------------------------------------------------------------------------------------------
def generate_json_schemas(input_dir, output_dir):
    '''Create JSON schemas from YAML source schemas in a directory.'''
    for file in sorted(os.listdir(input_dir)):
        path = os.path.join(input_dir,file)
        if os.path.isdir(path):
            new_output_dir = os.path.join(output_dir, file)
            if not os.path.exists(new_output_dir):
                os.mkdir(new_output_dir)
            generate_json_schemas(path, new_output_dir)
        else:
            generate_json_schema(path, output_dir)

# -------------------------------------------------------------------------------------------------
def search_for_reference(schema_path : str, subdict : dict) -> dict:
    '''Search for $ref keys and replace the associated dictionary entry in-situ.'''
    subbed = False
    if '$ref' in subdict.keys():
        print(subdict['$ref'])
        subbed = True
        # parse the ref and locate the sub-dict
        source_file, ref_loc = subdict['$ref'].split('#')
        ref = load(os.path.join(schema_path, source_file))
        key_tree = ref_loc.lstrip('/').split('/')
        sub_d = ref[key_tree[0]]
        for k in key_tree[1:]:
            sub_d = sub_d[k]
        subdict.update(sub_d)
        subdict.pop('$ref')
    else:
        for key in subdict:
            if isinstance(subdict[key], dict):
                search_for_reference(schema_path, subdict[key])
    return subbed
    
# -------------------------------------------------------------------------------------------------
def flatten_json_schema(input_schema, output_dir):
    '''Generate a flattened schema from a schema with references.'''
    schema_path = os.path.abspath(os.path.dirname(input_schema))
    schema = load(input_schema)
    while search_for_reference(schema_path, schema):
        pass
    file_name_root = os.path.splitext(os.path.basename(input_schema))[0]
    dump(schema, os.path.join(output_dir, file_name_root + '_flat.json'))
    # JsonRef method:
    # path = os.path.abspath(os.path.dirname(input_schema))
    # base_uri = f'file://{path}/'
    # print(base_uri)
    # file_name_root = os.path.splitext(os.path.basename(input_schema))[0]
    # with open(input_schema) as input_file:
    #     schema = jsonref.load(input_file, base_uri=base_uri)
    #     dump(schema, os.path.join(output_dir, file_name_root + '_flat.json'))

# -------------------------------------------------------------------------------------------------
def validate_json_file(input_file, input_schema):
    v = JSONSchemaValidator(input_schema)
    v.validate(input_file)

import sys

if __name__ == '__main__':
    flatten_json_schema(sys.argv[1], sys.argv[2])