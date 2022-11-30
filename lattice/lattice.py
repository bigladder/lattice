import os
import re
from fnmatch import fnmatch
import warnings

from lattice.docs.process_template import process_template
from .file_io import check_dir, make_dir, load, get_file_basename
from .meta_schema import generate_meta_schema, meta_validate_file
from .schema_to_json import generate_json_schema, validate_file, postvalidate_file
from .docs import HugoWeb, DocumentFile

class SchemaFile:
  def __init__(self, path):
    self.path = os.path.abspath(path)
    self.content = load(self.path)

    self.file_base_name = get_file_basename(self.path, depth=2)

    # Check for required content
    if "Schema" not in self.content:
      raise Exception(f"Required \"Schema\" object not found in schema file, \"{self.path}\".")

    self.schema_type = self.file_base_name # Overwritten if it is actually specified
    self.data_model_type = None
    self.root_data_group = None
    if "Root Data Group" in self.content["Schema"]:
      self.root_data_group = self.content["Schema"]["Root Data Group"]
      self.schema_type = self.root_data_group
      if self.root_data_group in self.content:
        # Get metadata
        self.data_model_type = None
        if "Data Elements" not in self.content[self.root_data_group]:
          raise Exception(f"Root Data Group, \"{self.root_data_group}\" does not contain \"Data Elements\".")
        else:
          if "metadata" in self.content[self.root_data_group]["Data Elements"]:
            if "Constraints" in self.content[self.root_data_group]["Data Elements"]["metadata"]:
              constraints = self.content[self.root_data_group]["Data Elements"]["metadata"]["Constraints"]
              data_element_pattern = "([a-z]+)(_([a-z]|[0-9])+)*"
              enumeration_pattern = "[A-Z]([A-Z]|[a-z]|[0-9])*"
              constraint_pattern = re.compile(f"^({data_element_pattern})=({enumeration_pattern})$")
              for constraint in constraints:
                match = constraint_pattern.match(constraint)
                if match:

                  if match.group(1) == "data_model":
                    self.data_model_type = match.group(5)
                  else:
                    pass # Warning?

                  if match.group(1) == "schema":
                    self.schema_type = match.group(5)
                  else:
                    pass # Warning?

          else:
            pass # Warning?

      else:
        raise Exception(f"Root Data Group, \"{self.root_data_group}\", not found in schema file, \"{self.path}\"")


      # TODO: Version?



  def set_meta_schema_path(self, meta_schema_path):
    self.meta_schema_path = os.path.abspath(meta_schema_path)

  def set_json_schema_path(self, json_schema_path):
    self.json_schema_path = os.path.abspath(json_schema_path)

  def set_schema_patterns(self, patterns):
    self.schema_patterns = patterns


class Lattice:
  def __init__(self, root_directory=".", build_directory=None, build_output_directory_name=".lattice/", build_validation=True):
    # Check if directories exists
    check_dir(root_directory, "Root directory")
    if build_directory is None:
      build_directory = root_directory
    else:
      check_dir(build_directory, "Build directory")

    self.root_directory = root_directory

    if build_output_directory_name is None:
      self.build_directory = build_directory
    else:
      self.build_directory = os.path.join(build_directory, build_output_directory_name)
    make_dir(self.build_directory)

    self.collect_schemas()

    self.setup_meta_schemas()

    self.setup_json_schemas()

    self.collect_example_files()

    self.collect_doc_templates()

    self.web_docs_directory_path = os.path.join(self.doc_output_dir,"web")

    if build_validation:
      self.generate_meta_schemas()
      self.validate_schemas()
      self.generate_json_schemas()
      self.validate_example_files()


  def collect_schemas(self):
    # Make sure root directory has minimum content (i.e., schema directory, or at least one schema file)
    schema_directory_path = os.path.join(self.root_directory,"schema")
    if os.path.exists(schema_directory_path):
      self.schema_directory_path = schema_directory_path
    else:
      self.schema_directory_path = self.root_directory

    # Collect list of schema files
    self.schemas = []
    for file_name in os.listdir(self.schema_directory_path):
      file_path = os.path.join(self.schema_directory_path, file_name)
      if fnmatch(file_path, "*.schema.yaml") or fnmatch(file_path, "*.schema.yml"):
        self.schemas.append(SchemaFile(file_path))

    if len(self.schemas) == 0:
      raise Exception(f"No schemas found in \"{self.schema_directory_path}\".")

  def setup_meta_schemas(self):
    self.meta_schema_directory = os.path.join(self.build_directory,"meta_schema")
    make_dir(self.meta_schema_directory)
    for schema in self.schemas:
      meta_schema_path = os.path.join(self.meta_schema_directory,f"{schema.file_base_name}.meta.schema.json")
      schema.set_meta_schema_path(meta_schema_path)

  def generate_meta_schemas(self):
    for schema in self.schemas:
      schema.set_schema_patterns(generate_meta_schema(schema.meta_schema_path, schema.path))

  def validate_schemas(self):
    for schema in self.schemas:
      meta_validate_file(schema.path, schema.meta_schema_path)

  def setup_json_schemas(self):
    self.json_schema_directory = os.path.join(self.build_directory,"json_schema")
    make_dir(self.json_schema_directory)
    self.core_json_schema_path = os.path.join(self.json_schema_directory,f"core.schema.json")
    for schema in self.schemas:
      json_schema_path = os.path.join(self.json_schema_directory,f"{schema.file_base_name}.schema.json")
      schema.set_json_schema_path(json_schema_path)

  def generate_json_schemas(self):
    for schema in self.schemas:
      generate_json_schema(schema.path, schema.json_schema_path)

  def validate_file(self, input_path, schema_type=None):
    instance = load(input_path)
    if schema_type is None:
      if "metadata" in instance:
        if "schema" in instance["metadata"]:
          schema_type = instance["metadata"]["schema"]

    if schema_type is None:
      if len(self.schemas) > 1:
        raise Exception(f"Multiple schemas defined, and no schema type provide. Unable to validate file, \"{input_path}\".")
      else:
        validate_file(input_path, self.schemas[0].json_schema_path)
        postvalidate_file(input_path, self.schemas[0].json_schema_path)
    else:
      # Find corresponding schema
      for schema in self.schemas:
        if schema.schema_type == schema_type:
          validate_file(input_path, schema.json_schema_path)
          postvalidate_file(input_path, schema.json_schema_path)
          break

  def collect_example_files(self):
    example_directory_path = os.path.join(self.root_directory,"examples")
    if os.path.exists(example_directory_path):
      self.example_directory_path = example_directory_path
    else:
      self.example_directory_path = None

    # Collect list of example files
    self.examples = []
    if self.example_directory_path is not None:
      for file_name in os.listdir(self.example_directory_path):
        file_path = os.path.join(self.example_directory_path, file_name)
        if os.path.isfile(file_path):
          self.examples.append(os.path.abspath(file_path))

  def validate_example_files(self):
    for example in self.examples:
      self.validate_file(example)

  def collect_doc_templates(self):
    doc_templates_directory_path = os.path.join(self.root_directory,"docs")
    if os.path.exists(doc_templates_directory_path):
      self.doc_templates_directory_path = doc_templates_directory_path
    else:
      self.doc_templates_directory_path = None

    # Collect list of doc template files
    self.doc_templates = []
    if self.doc_templates_directory_path is not None:
      for file_name in os.listdir(self.doc_templates_directory_path):
        file_path = os.path.join(self.doc_templates_directory_path, file_name)
        if os.path.isfile(file_path) and ".md" in file_name:
          self.doc_templates.append(DocumentFile(file_path))
    self.doc_output_dir = os.path.join(self.build_directory,"docs")
    if len(self.doc_templates) > 0:
      make_dir(self.doc_output_dir)
      for template in self.doc_templates:
        markdown_path = os.path.join(self.doc_output_dir,f"{get_file_basename(template.path, depth=1)}")
        template.set_markdown_output_path(markdown_path)

  def generate_markdown_documents(self):
    for template in self.doc_templates:
      process_template(template.path, template.markdown_output_path, self.schema_directory_path)

  def generate_web_documentation(self):
    make_dir(self.doc_output_dir)
    make_dir(self.web_docs_directory_path)

    if self.doc_templates_directory_path:
        HugoWeb(self.doc_templates_directory_path, self.web_docs_directory_path).build()
    else:
        warnings.warn('Template directory "doc" does not exist under {self.root_directory}')

