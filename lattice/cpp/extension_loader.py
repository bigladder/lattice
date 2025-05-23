"""From https://github.com/ArjanCodes/2021-plugin-architecture/blob/main/after/game/loader.py"""

import sys
from importlib import util
from pathlib import Path


def import_module(path: Path):
    """Imports a module given a path."""
    spec = util.spec_from_file_location(path.stem, path)
    try:
        module = util.module_from_spec(spec)
        sys.modules[path.stem] = module
        spec.loader.exec_module(module)
        return module
    except AttributeError:
        raise ModuleNotFoundError(f"{path} is not a valid extension module") from None


def load_extensions(from_path: Path) -> None:
    """Loads the plugins defined in the plugins list."""
    if from_path.is_dir():
        for plugin_file in [x for x in from_path.iterdir() if x.suffix == ".py"]:
            import_module(plugin_file)
