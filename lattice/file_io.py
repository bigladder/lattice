import os
import json
import cbor2
import yaml
import shutil

def get_extension(file):
    return os.path.splitext(file)[1]

def get_file_basename(file, depth=0):
    basename = os.path.basename(file)
    for i in range(depth):
        basename = os.path.splitext(basename)[0]
    return basename

def load(input_file_path):
    ext = get_extension(input_file_path).lower()
    if (ext == '.json'):
        with open(input_file_path, 'r') as input_file:
            return json.load(input_file)
    elif (ext == '.cbor'):
        with open(input_file_path, 'rb') as input_file:
            return cbor2.load(input_file)
    elif (ext == '.yaml') or (ext == '.yml'):
        with open(input_file_path, 'r') as input_file:
            return yaml.load(input_file, Loader=yaml.FullLoader)
    else:
        raise Exception(f"Unsupported input \"{ext}\".")

def dump(content, output_file_path):
    ext = get_extension(output_file_path).lower()
    if (ext == '.json'):
        with open(output_file_path,'w') as output_file:
            json.dump(content, output_file, indent=4)
    elif (ext == '.cbor'):
        with open(output_file_path,'wb') as output_file:
            cbor2.dump(content, output_file)
    elif (ext == '.yaml') or (ext == '.yml'):
        with open(output_file_path, 'w') as out_file:
            yaml.dump(content, out_file, sort_keys=False)

    else:
        raise Exception(f"Unsupported output \"{ext}\".")

def dump_to_string(content, output_type='json'):
    if (output_type == 'json'):
        return json.dump(content, indent=4)
    elif (output_type == 'yaml') or (output_type == 'yml'):
        return yaml.dump(content, sort_keys=False)
    else:
        raise Exception(f"Unsupported output \"{output_type}\".")


def translate(input, output):
    dump(load(input),output)

def translate_directory_recursive(source_dir, output_dir, output_extension):
    if len(os.listdir(source_dir)) ==0: # if directory is empty, do nothing
        return
    for source in os.listdir(source_dir):
        source_path = os.path.join(source_dir, source)
        if os.path.isdir(source_path):
            output_dir_path = os.path.join(output_dir, source)
            os.mkdir(output_dir_path)
            translate_directory_recursive(source_path, output_dir_path, output_extension)
        else:
            base_name = os.path.basename(source_path)
            file_name = os.path.splitext(base_name)[0]
            output_path = os.path.join(output_dir,file_name + output_extension)
            translate(source_path, output_path)

def translate_directory(source_dir, output_dir):
    output_extension = '.' + os.path.split(output_dir)[-1]
    translate_directory_recursive(source_dir, output_dir, output_extension)

def collect_files(input_dir, pattern, output_dir=None, new_name=None, new_extension=None):
  file_list = []
  for file in sorted(os.listdir(input_dir)):
    file_path = os.path.join(input_dir,file)
    if os.path.isdir(file_path):
      # Recursive search
      if output_dir is not None:
        new_output_dir = os.path.join(output_dir, file)
      else:
        new_output_dir = None
      file_list += collect_files(file_path, pattern, new_output_dir, new_name, new_extension)
    else:
      if output_dir is None:
        output_dir = input_dir
      if pattern in file:
        if new_name is not None:
            file_name_root = new_name
        else:
            file_name_root = os.path.splitext(file)[0]
        if new_extension is not None:
          file_extension = new_extension
        else:
          file_extension = os.path.splitext(file)[1]
        file_name = f'{file_name_root}{file_extension}'
        file_list.append(os.path.join(output_dir,file_name))
  return file_list

def make_dir(dir_path):
  if not os.path.exists(dir_path):
      os.mkdir(dir_path)

def remove_dir(dir_path):
    if os.path.exists(dir_path) and os.path.isdir(dir_path):
        shutil.rmtree(dir_path)

def check_dir(dir_path, dir_description="Directory"):
    if not os.path.exists(dir_path):
      raise Exception(f"{dir_description}, \"{dir_path}\", does not exist.")
    elif not os.path.isdir(dir_path):
      raise Exception(f"{dir_description}, \"{dir_path}\", is not a directory.")
