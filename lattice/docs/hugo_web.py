import os
import pygit2
from distutils.dir_util import copy_tree
import subprocess
import shutil
import platform

from jinja2 import Environment, FileSystemLoader

from ..file_io import dump, load, dump_to_string, get_file_basename, make_dir, get_extension, check_executable, translate
from .process_template import process_template
from .grid_table import write_table

class DocumentFile:
  def __init__(self, path):
    self.path = os.path.abspath(path)
    self.file_base_name = get_file_basename(path, depth=2)
    self.markdown_output_path = None
    self.corresponding_schema_path = None

  def set_markdown_output_path(self, path):
    self.markdown_output_path = os.path.abspath(path)

  def set_corresponding_schema_path(self, path):
    self.corresponding_schema_path = os.path.relpath(path)


class HugoWeb:
  def __init__(self, lattice):
    self.lattice = lattice
    self.build_directory = os.path.abspath(self.lattice.web_docs_directory_path)
    self.docs_source_directory = os.path.abspath(self.lattice.doc_templates_directory_path)
    self.docs_config_directory = os.path.join(self.docs_source_directory,"web")
    self.source_schema_directory_path = self.lattice.schema_directory_path
    self.title = os.path.relpath(self.docs_source_directory)
    self.description = ""
    self.author = ""
    self.has_logo = False
    self.colors = {
      "primary": "#30638E",
      "secondary": "#FFA630",
      "menu_text": "#000"
      }
    self.setup_build_directory_structure()
    self.get_git_info()
    self.main_menu_item_counter = 1
    self.specification_order = None
    self.specification_counter = 1
    self.specification_templates = []

  def setup_build_directory_structure(self):
    self.assets_directory_path = make_dir(os.path.join(self.build_directory, "assets"))
    self.content_directory_path = make_dir(os.path.join(self.build_directory, "content"))
    self.layouts_directory_path = make_dir(os.path.join(self.build_directory, "layouts"))
    self.static_directory_path = make_dir(os.path.join(self.build_directory, "static"))
    self.static_assets_directory_path = make_dir(os.path.join(self.static_directory_path, "assets"))


    # Asset directories
    self.icon_directory_path = make_dir(os.path.join(self.assets_directory_path, "icons"))
    self.scss_directory_path = make_dir(os.path.join(self.assets_directory_path, "scss"))

    # Content directories
    self.about_directory_path = make_dir(os.path.join(self.content_directory_path, "about"))
    self.specifications_directory_path = make_dir(os.path.join(self.content_directory_path, "specifications"))
    self.schema_directory_path = make_dir(os.path.join(self.content_directory_path, "schema"))
    self.examples_directory_path = make_dir(os.path.join(self.content_directory_path, "examples"))

    # Copy layouts
    copy_tree(os.path.join(os.path.dirname(__file__),"hugo_layouts"),self.layouts_directory_path)

  def get_git_info(self):
    self.git_repo = pygit2.Repository(pygit2.discover_repository(self.docs_source_directory))
    self.git_remote_url = os.path.splitext(self.git_repo.remotes[0].url)[0]
    git_url_parts = self.git_remote_url.split('/')
    self.git_repo_name = git_url_parts[-1]
    self.git_repo_owner = git_url_parts[-2]
    self.git_repo_host = os.path.splitext(git_url_parts[-3])[0]
    if self.git_repo.head_is_detached:
      self.git_ref_name = "main"
    else:
      self.git_ref_name = self.git_repo.head.name
    self.base_url = fr"https://{self.git_repo_owner}.{self.git_repo_host}.io/{self.git_repo_name}/"

  def make_pages(self):
    # Check config directory
    landing_page_content = ""
    about_page_content = None
    background_image_path = None
    logo_path = None
    config_path = None
    favicons_path = None
    if os.path.exists(self.docs_config_directory):
      for file_name in os.listdir(self.docs_config_directory):
        file_path = os.path.join(self.docs_config_directory, file_name)
        if "landing" in file_name:
          with open(file_path,'r') as file:
            landing_page_content = file.read()
        elif "about" in file_name:
          with open(file_path,'r') as file:
            about_page_content = file.read()
        elif "featured-background" in file_name:
          background_image_path = file_path
        elif "logo" in file_name:
          logo_path = file_path
        elif "config" in file_name:
          config_path = file_path
        elif "favicons" in file_name:
          favicons_path = file_path

    if config_path is not None:
      config = load(config_path)
      if "title" in config:
        self.title = config["title"]
      if "author" in config:
        self.author = config["author"]
      if "description" in config:
        self.description = config["description"]
      if "specifications" in config:
        self.specification_order = config["specifications"]
      if "colors" in config:
        for item in config["colors"]:
          self.colors[item] = config["colors"][item]

    # Create scss file
    render_template(os.path.join(os.path.dirname(__file__),"scss_template.scss.j2"), os.path.join(self.scss_directory_path, "_variables_project.scss"), self.colors)

    landing_page_path = os.path.join(self.content_directory_path,"_index.pdc")
    self.make_page(landing_page_path,{"title": self.title, "type": "landing", "description": self.description}, content=landing_page_content)

    if about_page_content is not None:
      self.make_main_menu_page(self.about_directory_path,"About",content=about_page_content)

    if background_image_path is not None:
      shutil.copy(background_image_path, self.content_directory_path)
      if about_page_content is not None:
        shutil.copy(background_image_path, self.about_directory_path)

    if logo_path is not None:
      shutil.copy(logo_path, self.icon_directory_path)
      self.has_logo = True

    if favicons_path is not None:
      copy_tree(favicons_path, os.path.join(self.static_directory_path,"favicons"))

    # Specifications
    self.make_main_menu_page(self.specifications_directory_path,"Specifications",content="This data model contains the following specifications:",content_path=os.path.relpath(self.docs_source_directory),schema_path=os.path.relpath(self.source_schema_directory_path))

    self.make_specification_pages()

    # Schema
    self.make_schema_page()

    # Examples
    self.make_examples_page()

  def make_specification_pages(self):
    # Collect list of doc template files
    if self.specification_order is not None:
      for specification_name in self.specification_order:
        file_name = f"{specification_name}.md.j2"
        file_path = os.path.join(self.docs_source_directory, file_name)
        if os.path.exists(file_path):
          self.specification_templates.append(DocumentFile(file_path))
        else:
          raise Exception(f"Unable to find specification file, \"{file_path}\", referenced in configuration.")
    else:
      for file_name in os.listdir(self.docs_source_directory):
        file_path = os.path.join(self.docs_source_directory, file_name)
        if os.path.isfile(file_path):
          self.specification_templates.append(DocumentFile(file_path))

    # Identify corresponding schema files
    for template in self.specification_templates:
      for schema_file in os.listdir(self.source_schema_directory_path):
        if template.file_base_name in schema_file:
          file_path = os.path.join(self.source_schema_directory_path, schema_file)
          template.set_corresponding_schema_path(file_path)


    # Process templates
    for template in self.specification_templates:
      template.set_markdown_output_path(os.path.join(self.specifications_directory_path,f"{get_file_basename(template.path, depth=2)}.pdc"))
      self.make_specification_page(template.path, template.markdown_output_path, self.source_schema_directory_path, template.corresponding_schema_path)

  def make_schema_page(self):
    schema_files = {
      "Schema": [],
      "Description": []
    }
    schema_assets_directory = os.path.join(self.static_assets_directory_path,"schema")
    make_dir(schema_assets_directory)
    references = {}
    reference_counter = 1
    reference_string = "\n"
    for schema in self.lattice.schemas:
      content = load(schema.json_schema_path)
      output_path = os.path.join(schema_assets_directory, get_file_basename(schema.json_schema_path))
      shutil.copy(schema.json_schema_path, output_path)
      references[reference_counter] = f"/{self.git_repo_name}/{os.path.relpath(output_path, self.static_directory_path)}"
      schema_files["Schema"].append(f"[{content['title']}][{reference_counter}]")
      reference_string += f"\n[{reference_counter}]: {references[reference_counter]}"
      reference_counter += 1
      schema_files["Description"].append(content["description"])

    content = "# JSON Schema\n\n" + write_table(schema_files,["Schema","Description"]) + reference_string + "\n"
    self.make_main_menu_page(self.schema_directory_path,"Schema",content=content)

  def make_examples_page(self):
    example_files = {
      "File Name": [],
      "Description": [],
      "Download": []
    }
    example_assets_directory = os.path.join(self.static_assets_directory_path,"examples")
    make_dir(example_assets_directory)
    references = {}
    reference_counter = 1
    reference_string = "\n"
    for example in self.lattice.examples:
      content = load(example)
      file_base_name = get_file_basename(example, depth=1)
      formats = ['yaml', 'json', 'cbor']
      output_path = {}
      web_links = {}
      for format in formats:
        output_path[format] = os.path.join(example_assets_directory, f"{file_base_name}.{format}")
        references[reference_counter] = f"/{self.git_repo_name}/{os.path.relpath(output_path[format], self.static_directory_path)}"
        web_links[format] = f"[{format.upper()}][{reference_counter}]"
        reference_string += f"\n[{reference_counter}]: {references[reference_counter]}"
        reference_counter += 1
        translate(example, output_path[format])
      example_files["File Name"].append(file_base_name)
      example_files["Description"].append(content["metadata"]["description"])
      example_files["Download"].append(f"{web_links['yaml']} {web_links['json']} {web_links['cbor']}")


    content = "# Example Files\n\n" + write_table(example_files,["File Name","Description","Download"]) + reference_string + "\n"
    self.make_main_menu_page(self.examples_directory_path,"Examples",content=content)

  def make_page(self, page_path, front_matter, content=""):
    with open(page_path,'w') as file:
      file.writelines(f"{make_front_matter(front_matter)}{content}")

  def make_main_menu_page(self, page_dir_path, title, content="", schema_path=None, content_type=None, content_path=None):
    front_matter = {
      "title": title,
      "linkTitle": title,
      "weight": 1,
      "menu": {
        "main": {
          "weight": self.main_menu_item_counter
        }
      }
    }

    self.main_menu_item_counter += 1

    if content_type is not None:
      front_matter["type"] = content_type

    if schema_path is not None:
      front_matter["github_schema"] = schema_path

    if content_path is not None:
      front_matter["github_content"] = content_path

    page_path = os.path.join(page_dir_path, "_index.pdc")
    self.make_page(page_path, front_matter, content)

  def make_specification_page(self, template_path, output_path, schema_dir_path, corresponding_schema_path=None):

    if get_extension(template_path) == ".j2":
      # Process template
      process_template(template_path, output_path, schema_dir=schema_dir_path)
    else:
      copy_tree(template_path, output_path)

    title = get_file_basename(template_path, depth=2)

    # Run Pandoc

    # Append front matter
    front_matter = {
      "title": title,
      "linkTitle": title,
      "type": "specifications",
      "weight": self.specification_counter
    }

    self.specification_counter += 1

    template_relative_path = os.path.relpath(template_path)

    if corresponding_schema_path is None:
      corresponding_schema_path = schema_dir_path

    front_matter["github_schema"] = corresponding_schema_path

    front_matter["github_content"] = template_relative_path

    with open(output_path,'r') as original_file:
      content = original_file.read()
    self.make_page(output_path, front_matter, content)

  def build(self):
    # Check for dependencies
    check_executable("hugo", "https://gohugo.io/installation/")
    check_executable("npm", "https://nodejs.org/en/download/")

    self.make_pages()

    # Setup Hugo Config
    dump(self.make_hugo_config(),os.path.join(self.build_directory,"config.yaml"))

    # npm package.json
    dump(self.make_npm_package_json(),os.path.join(self.build_directory,"package.json"))

    shell = False
    if platform.system() == "Windows":
      shell = True

    if not os.path.exists(os.path.join(self.build_directory,"go.mod")):
      subprocess.run(["hugo", "mod", "init", os.path.relpath(self.docs_source_directory).replace('\\','/')], cwd=self.build_directory, check=True, shell=shell)

    if not os.path.exists(os.path.join(self.build_directory,"go.sum")):
      subprocess.run(["hugo", "mod", "get", r"github.com/google/docsy@v0.4.0"], cwd=self.build_directory, check=True, shell=shell)

    if not os.path.exists(os.path.join(self.build_directory,"package-lock.json")):
      subprocess.run(["npm", "install"], cwd=self.build_directory, check=True, shell=shell)

    subprocess.run(["hugo", "--minify"], cwd=self.build_directory, check=True, shell=shell)

  def make_hugo_config(self):
    return {
      "baseURL": self.base_url,
      "title": self.title,
      "enableGitInfo": True,
      "module": {
        "hugoVersion": {
          "extended": True,
          "min": "0.73.0"
        },
        "imports": [
          {
            "path": "github.com/google/docsy",
            "disable": False
          },
          {
            "path": "github.com/google/docsy/dependencies",
            "disable": False
          },
        ]
      },
      "params": {
        "copyright": self.author,
        "github_repo": self.git_remote_url,
        "github_branch": self.git_ref_name,
        "ui": {
          "navbar_logo": self.has_logo,
          "breadcrumb_disable": True
        }
      },
      "security": {
        "enableInlineShortcodes": False,
        "exec": {
          "allow": ['^dart-sass-embedded$', '^go$', '^npx$', '^postcss$', '^pandoc$'],
          "osEnv": ['(?i)^(PATH|PATHEXT|APPDATA|TMP|TEMP|TERM)$']
        },
        "funcs": {
          "getenv": ['^HUGO_']
        },
        "http": {
          "methods": ['(?i)GET|POST'],
          "urls": ['.*']
        }
      }
    }

  def make_npm_package_json(self):
    return {
      "name": "lattice",
      "version": "0.0.1",
      "description": "",
      "dependencies": {},
      "devDependencies": {
        "autoprefixer": "^10.4.0",
        "postcss": "^8.3.7",
        "postcss-cli": "^9.0.2"
      }
    }

def make_front_matter(front_matter):
  return f"---\n{dump_to_string(front_matter,'yaml')}---\n\n"

def prepend_file_content(file_path, new_content):
  with open(file_path,'r') as original_file:
    original_content = original_file.read()
  with open(file_path,'w') as modified_file:
    modified_file.write(new_content + original_content)

def render_template(template_path, output_path, values):
  template_directory_path = os.path.abspath(os.path.join(template_path, os.pardir))
  template_environment = Environment(loader=FileSystemLoader(template_directory_path))
  template = template_environment.get_template(os.path.basename(template_path))
  with open(output_path, 'w') as file:
    file.write(template.render(**values))
