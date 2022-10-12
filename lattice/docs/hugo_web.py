import os
from ..file_io import dump, dump_to_string, get_file_basename, make_dir, get_extension
from distutils.dir_util import copy_tree
from .process_template import process_template

def setup_hugo_structure(output_dir_path, config={"name": "Test"}):
  # Setup Hugo Config
  dump(make_hugo_config(config),os.path.join(output_dir_path,"config.yaml"))

  # npm package.json
  dump(make_npm_package_json(),os.path.join(output_dir_path,"package.json"))

  # Create directories
  hugo_dirs = ["assets", "content", "layouts"]
  content_dirs = ["about","specifications","schema","examples"]
  hugo_dirs += [os.path.join("content",content_dir) for content_dir in content_dirs]
  for hugo_dir in hugo_dirs:
    make_dir(os.path.join(output_dir_path,hugo_dir))

  # Copy layouts
  copy_tree(os.path.join(os.path.dirname(__file__),"hugo_layouts"),os.path.join(output_dir_path,"layouts"))


def make_hugo_config(config):
  return {
    "baseURL": config["base_url"],
    "title": config["name"],
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
      "github_repo": config["git_repo"],
      "github_branch": config["git_branch"],
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

def make_front_matter(front_matter):
  return f"---\n{dump_to_string(front_matter,'yaml')}---\n\n"

def make_new_menu_page(output_file_path, title, order=1, content="", schema_path=None, content_type=None, content_path=None):
  front_matter = {
    "title": title,
    "linkTitle": title,
    "weight": 1,
    "menu": {
      "main": {
        "weight": order
      }
    }
  }

  if content_type is not None:
    front_matter["type"] = content_type

  if schema_path is not None:
    front_matter["github_schema"] = schema_path

  if content_path is not None:
    front_matter["github_content"] = content_path

  with open(output_file_path,'w') as output_file:
    output_file.writelines(f"{make_front_matter(front_matter)}{content}")

def make_specification_html(template_path, output_path, schema_dir_path, template_relative_path=None, order=1):

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
    "weight": order
  }

  if template_relative_path is None:
    template_relative_path = template_path

  front_matter["github_schema"] = schema_dir_path

  front_matter["github_content"] = template_relative_path

  with open(output_path,'r') as original_file:
    content = original_file.read()
  with open(output_path,'w') as output_file:
    output_file.writelines(f"{make_front_matter(front_matter)}{content}")

def prepend_file_content(file_path, new_content):
  with open(file_path,'r') as original_file:
    original_content = original_file.read()
  with open(file_path,'w') as modified_file:
    modified_file.write(new_content + original_content)

def make_examples_html():
  pass

def make_npm_package_json():
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
