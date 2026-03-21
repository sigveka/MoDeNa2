'''@cond

   ooo        ooooo           oooooooooo.             ooooo      ooo
   `88.       .888'           `888'   `Y8b            `888b.     `8'
    888b     d'888   .ooooo.   888      888  .ooooo.   8 `88b.    8   .oooo.
    8 Y88. .P  888  d88' `88b  888      888 d88' `88b  8   `88b.  8  `P  )88b
    8  `888'   888  888   888  888      888 888ooo888  8     `88b.8   .oP"888
    8    Y     888  888   888  888     d88' 888    .o  8       `888  d8(  888
   o8o        o888o `Y8bod8P' o888bood8P'   `Y8bod8P' o8o        `8  `Y888""8o

Copyright
    2014-2026 MoDeNa Consortium, All rights reserved.

License
    This file is part of Modena.

    The Modena interface library is free software; you can redistribute it
    and/or modify it under the terms of the GNU Lesser General Public License
    as published by the Free Software Foundation, either version 3 of the
    License, or (at your option) any later version.

    Modena is distributed in the hope that it will be useful, but WITHOUT ANY
    WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
    FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
    details.

    You should have received a copy of the GNU General Public License along
    with Modena.  If not, see <http://www.gnu.org/licenses/>.
@endcond'''

"""
@file
Module providing the MoDeNa python interface

@copyright  2014-2026, MoDeNa Project. GNU Public License.
"""

import os, sys
from importlib.metadata import version
from pathlib import Path

# Platform-specific shared library name and dynamic-linker search-path variable.
if sys.platform == 'darwin':
    _LIBMODENA_NAME  = 'libmodena.dylib'
    _LIBPATH_ENV_VAR = 'DYLD_LIBRARY_PATH'
elif sys.platform == 'win32':
    _LIBMODENA_NAME  = 'modena.dll'
    _LIBPATH_ENV_VAR = 'PATH'
else:  # Linux and other POSIX
    _LIBMODENA_NAME  = 'libmodena.so'
    _LIBPATH_ENV_VAR = 'LD_LIBRARY_PATH'

from modena._logging import configure_logging  # noqa: F401 — public API
from modena._logging import logger as _logger

__version__ = version('modena')

# Apply MODENA_LOG_LEVEL env var on import.
configure_logging()


MODENA_WORKING_DIR = str(Path.cwd().resolve())

try:
    from modena._paths import MODENA_LIB_DIR, MODENA_CMAKE_MINIMUM_VERSION
except ImportError:
    # _paths.py has not been generated yet (cmake configure not run).
    # Infer from __file__ as a development fallback.
    MODENA_LIB_DIR = str(
        (Path(__file__).parent / '..' / '..' / 'lib').resolve()
    )
    MODENA_CMAKE_MINIMUM_VERSION = '3.0'

def find_module(target: str, startsearch: str = MODENA_WORKING_DIR) -> str | None:
    """Function recursively searching through the file tree for "target".
    Checks the environment variable MODENA_<TARGET>_DIR first before
    falling back to a directory walk.

    @arg target: 'str' name of directory e.g. "Desktop"
    """

    # 1. Check environment variable first
    env_var = f"MODENA_{target.upper()}_DIR"
    env_path = os.environ.get(env_var)
    if env_path:
        if Path(env_path).is_dir():
            _logger.info("Found '%s' via %s: %s", target, env_var, env_path)
            sys.path.insert(0, env_path)
            return env_path
        else:
            _logger.warning("%s is set to '%s' but that directory does not exist.", env_var, env_path)

    # 2. Fall back to directory walk
    pth = Path(startsearch).resolve()
    searched = []

    while target not in [p.name for p in pth.iterdir() if p.is_dir()]:
        searched.append(str(pth))
        pth = (pth / '..').resolve()  # step back a directory
        if pth.is_mount():             # break if we hit "root"
            _logger.warning(
                "'%s' not found. Searched the following directories:\n%s",
                target,
                "\n".join(f"  - {s}" for s in searched),
            )
            return None

    found = pth / target
    _logger.info("Found '%s' at: %s", target, found)
    sys.path.insert(0, str(found))
    return str(found)

def import_helper() -> object:
    # MODENA_LIB_DIR is set by CMake at install time to the exact location
    # of the shared library. This is also the directory users must add to
    # the platform dynamic-linker search path (_LIBPATH_ENV_VAR) for
    # C/Fortran programs that link against the library.
    import importlib.util
    lib_path = str(Path(MODENA_LIB_DIR) / _LIBMODENA_NAME)
    spec = importlib.util.spec_from_file_location('libmodena', lib_path)
    if spec is None or spec.loader is None:
        raise ImportError(
            f"Could not load '{lib_path}'. "
            f"Ensure {_LIBPATH_ENV_VAR} includes '{MODENA_LIB_DIR}'."
        )
    _mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_mod)
    return _mod


from .Registry import ModelRegistry
_reg = ModelRegistry().load()        # Resolve model paths from layered config

# Re-apply logging if modena.toml has a [logging] section AND the env var
# is not set (env var always wins over the config file).
if _reg._toml_log_level is not None and 'MODENA_LOG_LEVEL' not in os.environ:
    configure_logging(level=_reg._toml_log_level, file=_reg._toml_log_file)

libmodena = import_helper()
del import_helper

from .Strategy import *
from .SurrogateModel import *
from .Runner import run

# Auto-import every model package discovered in registered prefixes.
# This ensures all @explicit_serialize FireTask classes are registered in
# the FireWorks _fw_registry before any rocket deserializes tasks from
# MongoDB, so ADD_USER_PACKAGES: [modena] in FW_config.yaml is sufficient.
# NOTE: must run AFTER the modena symbols above are imported so that model
# packages doing "from modena import ForwardMappingModel" do not hit a
# circular-import error (modena partially initialised at that point).
import importlib as _importlib
for _pkg in _reg.active_packages():
    try:
        _importlib.import_module(_pkg)
        _logger.debug('modena: auto-imported model package %r', _pkg)
    except ImportError as _e:
        _logger.debug('modena: could not auto-import %r: %s', _pkg, _e)
del _importlib, _reg


def lpad():
    """Return a :class:`ModenaLaunchPad` connected to the active MODENA_URI.

    This is the recommended entry point for interactive launchpad access::

        import modena
        lp = modena.lpad()
        lp.status()
        lp.state_counts()
        lp.defuse_orphans()
    """
    from modena.Launchpad import ModenaLaunchPad
    return ModenaLaunchPad.from_modena_uri()


def load(model_id: str) -> 'SurrogateModel':
    """Load a surrogate model by name.

    This is the recommended way to obtain a model in Python code:

        import modena
        model = modena.load('flowRate')
        outputs = model({'D': 0.01, 'rho0': 3.4, 'p0': 3e5, 'p1Byp0': 0.03})

    Args:
        model_id: the ``_id`` of the surrogate model as registered in the database.

    Returns:
        The loaded :class:`SurrogateModel` instance.

    Raises:
        DoesNotExist: if no model with that ID exists. Run ``initModels`` first.
    """
    return SurrogateModel.load(model_id)
##
# @defgroup python_interface_library
# Module providing the MoDeNa python interface

