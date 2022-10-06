import os
from ..file_io import dump, dump_to_string, make_dir, remove_dir
from distutils.dir_util import copy_tree
from .process_template import process_template

def make_web_docs(schema_dir_path, template, output_dir="."):
  setup_hugo_structure(output_dir)

  make_new_menu_page(os.path.join(output_dir,"web","content","about","_index.pdc"),"About",1)
  make_specification_html(template, os.path.join(output_dir,"web","content","specifications","_index.pdc"),schema_dir_path)
  make_new_menu_page(os.path.join(output_dir,"web","content","schema","_index.pdc"),"Schema",3)
  make_new_menu_page(os.path.join(output_dir,"web","content","examples","_index.pdc"),"Examples",4)
  return

def setup_hugo_structure(output_dir):
  output_dir_path = os.path.join(output_dir,"web")
  remove_dir(output_dir_path)
  make_dir(output_dir_path)

  # Setup Hugo Config
  dump(make_hugo_config("Test"),os.path.join(output_dir_path,"config.yaml"))

  # Create directories
  hugo_dirs = ["assets", "content", "layouts"]
  content_dirs = ["about","specifications","schema","examples"]
  hugo_dirs += [os.path.join("content",content_dir) for content_dir in content_dirs]
  for hugo_dir in hugo_dirs:
    make_dir(os.path.join(output_dir_path,hugo_dir))

  # Copy layouts
  copy_tree(os.path.join(os.path.dirname(__file__),"hugo_layouts"),os.path.join(output_dir,"web","layouts"))


def make_hugo_config(title):
  return {
    "title": title,
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
      "github_repo": "https://github.com/bigladder/lattice",
      "ui": {
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

def make_front_matter(title, rank=1, schema_path=None, content_path=None):
  front_matter = {
    "title": title,
    "linkTitle": title,
    "weight": 1,
    "menu": {
      "main": {
        "weight": rank
      }
    }
  }

  if schema_path is not None:
    front_matter["github_schema"] = schema_path

  if content_path is not None:
    front_matter["github_content"] = content_path

  return f"---\n{dump_to_string(front_matter,'yaml')}---\n\n"


def make_new_menu_page(output_file_path, title, rank=1, content="", schema_path=None, content_path=None):
  with open(output_file_path,'w') as output_file:
    output_file.writelines(f"{make_front_matter(title, rank, schema_path, content_path)}{content}")

def make_specification_html(template_path, output_path, schema_dir_path):
  # Process template
  process_template(template_path, output_path, schema_dir=schema_dir_path)

  # Run Pandoc

  # Append metadata
  with open(output_path,'r') as original_file:
    content = original_file.read()
  make_new_menu_page(output_path, "Specification", rank=2, content=content, schema_path="", content_path=template_path)

def prepend_file_content(file_path, new_content):
  with open(file_path,'r') as original_file:
    original_content = original_file.read()
  with open(file_path,'w') as modified_file:
    modified_file.write(new_content + original_content)

def make_examples_html():
  pass
