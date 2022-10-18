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

def make_dir(dir_path):
  if not os.path.exists(dir_path):
      os.mkdir(dir_path)
  return dir_path

def remove_dir(dir_path):
    if os.path.exists(dir_path) and os.path.isdir(dir_path):
        shutil.rmtree(dir_path)

def check_dir(dir_path, dir_description="Directory"):
    if not os.path.exists(dir_path):
      raise Exception(f"{dir_description}, \"{dir_path}\", does not exist.")
    elif not os.path.isdir(dir_path):
      raise Exception(f"{dir_description}, \"{dir_path}\", is not a directory.")
