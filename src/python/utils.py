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

    Modena is free software; you can redistribute it and/or modify it under
    the terms of the GNU General Public License as published by the Free
    Software Foundation, either version 3 of the License, or (at your option)
    any later version.

    Modena is distributed in the hope that it will be useful, but WITHOUT ANY
    WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
    FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
    details.

    You should have received a copy of the GNU General Public License along
    with Modena.  If not, see <http://www.gnu.org/licenses/>.
@endcond'''

"""
@file
Shared helpers for locating executables, data files, and loading model config.

Model packages call external tools (LAMMPS, Quantum ESPRESSO, …) and need
bundled data files (EAM potentials, pseudopotentials, …).  These helpers
centralise the search logic so each package does not re-implement it.

``load_model_config`` and ``build_strategy`` support the optional
``config.toml`` system — see :mod:`modena.config_schema` for the schema.
"""

import os
import shutil
from pathlib import Path


def find_executable(
    name: str,
    *,
    env_var: str | None = None,
    extra_names: list[str] | None = None,
) -> str:
    """Return the path to an executable, searching env var then PATH.

    Search order:

    1. If *env_var* is set and its value is a regular file, return it directly
       (full-path override, e.g. ``LAMMPS_EXE=/opt/lammps/bin/lmp_mpi``).
    2. If *env_var* is set and its value is a directory, look for *name*
       inside that directory (bin-dir override, e.g.
       ``QE_BIN_DIR=/opt/qe/bin``).
    3. If *env_var* is set to a bare name, try ``shutil.which`` on that value.
    4. Try ``shutil.which`` on *name*, then on each entry in *extra_names*.

    Args:
        name:        Primary executable name to search for.
        env_var:     Optional environment variable name.  Its value may be
                     a full executable path, a directory, or a bare name.
        extra_names: Additional names to try on PATH after *name* (e.g.
                     alternative binary names such as ``lmp_serial``).

    Returns:
        Absolute path string of the found executable.

    Raises:
        FileNotFoundError: if no executable can be located.
    """
    if env_var:
        val = os.environ.get(env_var, '')
        if val:
            p = Path(val)
            if p.is_file():
                return str(p)               # explicit full path
            if p.is_dir():
                candidate = p / name
                if candidate.exists():
                    return str(candidate)   # bin_dir / name
            found = shutil.which(val)       # bare name or unknown path
            if found:
                return found

    for n in [name] + (extra_names or []):
        found = shutil.which(n)
        if found:
            return found

    names_str = ', '.join([name] + (extra_names or []))
    env_hint = f' or set {env_var}' if env_var else ''
    raise FileNotFoundError(
        f"Executable '{names_str}' not found on PATH{env_hint}."
    )


def find_file(
    filename: str,
    search_dirs: list[Path],
    *,
    env_var: str | None = None,
) -> str:
    """Return the absolute path to a data file (potential, pseudopotential, …).

    Search order:

    1. If *filename* is an absolute path and the file exists, return it as-is.
    2. If *env_var* is set, prepend its value (treated as a directory) to the
       search list.
    3. Search each directory in *search_dirs* (non-existent dirs are skipped).

    Args:
        filename:    File name (or absolute path) to locate.
        search_dirs: Directories to search, in priority order.
        env_var:     Optional environment variable name whose value is a
                     directory to search before *search_dirs*.

    Returns:
        Absolute path string of the found file.

    Raises:
        FileNotFoundError: if the file cannot be located in any directory.
    """
    candidate = Path(filename)
    if candidate.is_absolute() and candidate.exists():
        return str(candidate)

    dirs: list[Path] = []
    if env_var:
        val = os.environ.get(env_var, '')
        if val:
            dirs.append(Path(val))
    dirs.extend(search_dirs)

    for directory in dirs:
        if not directory or not directory.is_dir():
            continue
        found = directory / filename
        if found.exists():
            return str(found.resolve())

    env_hint = f' Set {env_var} to its directory.' if env_var else ''
    raise FileNotFoundError(
        f"File '{filename}' not found in any search directory.{env_hint}"
    )


# ------------------------------------------------------------------ #
# Config loading                                                       #
# ------------------------------------------------------------------ #

def load_model_config(model_file: str) -> 'ModelConfig':
    """Parse and validate ``config.toml`` alongside *model_file*.

    Looks for ``config.toml`` in the same directory as the given Python
    module file (pass ``__file__`` from the model package).

    Args:
        model_file: Path to the calling module (pass ``__file__``).

    Returns:
        A validated :class:`~modena.config_schema.ModelConfig` instance.

    Raises:
        FileNotFoundError: if ``config.toml`` does not exist.
        pydantic.ValidationError: if the TOML content fails validation.
    """
    from modena.config_schema import ModelConfig

    config_path = Path(model_file).parent / 'config.toml'
    if not config_path.exists():
        raise FileNotFoundError(
            f"config.toml not found alongside '{model_file}'. "
            f"Expected at: {config_path}"
        )

    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

    with open(config_path, 'rb') as fh:
        data = tomllib.load(fh)

    return ModelConfig.model_validate(data)


def build_strategy(cfg: 'StrategyConfig') -> dict:
    """Convert a :class:`~modena.config_schema.StrategyConfig` to kwargs.

    Returns a dict with keys ``initialisationStrategy``,
    ``outOfBoundsStrategy``, ``parameterFittingStrategy``, and optionally
    ``nonConvergenceStrategy`` — ready to be unpacked into
    :class:`~modena.SurrogateModel.BackwardMappingModel`.

    Args:
        cfg: Validated strategy configuration from ``config.toml``.

    Returns:
        Dict of strategy kwargs for ``BackwardMappingModel``.
    """
    import modena.Strategy as Strategy
    import modena.ErrorMetrics as ErrorMetrics

    result = {
        'initialisationStrategy':   _build_one(cfg.initialisationStrategy,   Strategy, ErrorMetrics),
        'outOfBoundsStrategy':      _build_one(cfg.outOfBoundsStrategy,      Strategy, ErrorMetrics),
        'parameterFittingStrategy': _build_one(cfg.parameterFittingStrategy, Strategy, ErrorMetrics),
    }
    if cfg.nonConvergenceStrategy is not None:
        result['nonConvergenceStrategy'] = _build_one(cfg.nonConvergenceStrategy, Strategy)
    return result


def _build_one(cfg_model, *lookup_modules) -> object:
    """Instantiate a single Strategy object from a Pydantic config model."""
    if cfg_model is None:
        return None
    data = cfg_model.model_dump(exclude_none=True)
    return _instantiate_from_dict(data, *lookup_modules)


def _instantiate_from_dict(d: dict, *lookup_modules) -> object:
    """Recursively instantiate a Strategy from a plain dict with a 'type' key.

    Looks up the class name in each module in *lookup_modules* in order,
    using the first match.  Nested dicts that contain a ``'type'`` key are
    instantiated recursively with the same module list.
    """
    d = dict(d)
    strategy_type = d.pop('type')
    cls = None
    for mod in lookup_modules:
        cls = getattr(mod, strategy_type, None)
        if cls is not None:
            break
    if cls is None:
        names = ', '.join(getattr(m, '__name__', str(m)) for m in lookup_modules)
        raise AttributeError(
            f"Strategy type '{strategy_type}' not found in: {names}"
        )
    for key, val in list(d.items()):
        if isinstance(val, dict) and 'type' in val:
            d[key] = _instantiate_from_dict(val, *lookup_modules)
    return cls(d)
