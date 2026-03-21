"""
@file    Registry.py
@brief   Layered model search-path registry and modena.lock provenance.

Model paths are resolved from (lowest to highest priority):
  1. /etc/modena/config.toml        (system-wide)
  2. ~/.modena/config.toml          (user-level)
  3. modena.toml  (nearest ancestor of cwd)    (project-level)
  4. MODENA_PATH env var  (colon-separated list of prefixes)

Each prefix is expected to contain lib/pythonX.Y/site-packages/ directories.
All resolved site-packages dirs are prepended to sys.path so that installed
model packages (e.g. flowRate, idealGas) are importable.

Binary search path (MODENA_BIN_PATH) is resolved from (lowest to highest priority):
  1. /etc/modena/config.toml        [binaries] paths
  2. ~/.modena/config.toml          [binaries] paths
  3. modena.toml                    [binaries] paths
  4. MODENA_BIN_PATH env var  (colon-separated list of directories)

When find_binary() is called with a caller_file, the directory
  dirname(caller_file)/bin/
is checked as a final fallback after all configured paths.

Lock file (modena.lock) format – TOML:

    [meta]
    modena_version = "1.0"
    generated      = "2026-03-14T10:05:33"

    [packages]
    flowRate = "1.0"

    [models.flowRate]
    surrogate_function = "flowRate"
    n_samples          = 42
    parameters         = [1.234, 5.678]
    last_fitted        = "2026-03-14T09:55:00"
"""

import glob as _glob
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_log = logging.getLogger('modena.registry')

try:
    import tomllib          # Python 3.11+ (stdlib)
except ImportError:
    try:
        import tomli as tomllib   # pip install tomli
    except ImportError:
        tomllib = None      # type: ignore[assignment]

__all__ = ('ModelRegistry',)

_LOCK_FILE = 'modena.lock'
_CONFIG_FILE = 'modena.toml'


# --------------------------------------------------------------------------- #
# File helpers                                                                 #
# --------------------------------------------------------------------------- #

def _load_toml(path: 'str | Path') -> dict:
    """Load a TOML file; return {} if not found or tomllib unavailable."""
    path = Path(path)
    if not path.is_file():
        return {}
    if tomllib is None:
        _log.warning(
            "cannot read '%s' — install 'tomli' (pip install tomli) for Python < 3.11.",
            path,
        )
        return {}
    with open(path, 'rb') as fh:
        return tomllib.load(fh)


def _find_project_config() -> 'Path | None':
    """Walk up from cwd to find the nearest modena.toml."""
    pth = Path.cwd().resolve()
    while True:
        candidate = pth / _CONFIG_FILE
        if candidate.is_file():
            return candidate
        parent = pth.parent
        if parent == pth:   # filesystem root
            return None
        pth = parent


def _site_packages_in_prefix(prefix: str) -> list:
    """Return all lib/pythonX.Y/site-packages dirs inside *prefix*."""
    pattern = str(Path(prefix) / 'lib' / 'python*' / 'site-packages')
    return _glob.glob(pattern)


# --------------------------------------------------------------------------- #
# Registry                                                                     #
# --------------------------------------------------------------------------- #

class ModelRegistry:
    """
    Singleton registry that resolves model search paths and writes provenance.

    Typical usage (done automatically by modena.__init__):

        ModelRegistry().load()

    CLI usage:

        modena freeze          # write modena.lock
        modena restore         # read modena.lock and restore DB state
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._prefixes: list = []
            inst._packages: dict = {}
            inst._surrogate_lib_dir: 'str | None' = None
            inst._bin_dirs: list = []
            inst._toml_log_level: 'str | None' = None   # from [logging] level
            inst._toml_log_file:  'str | None' = None   # from [logging] file
            cls._instance = inst
        return cls._instance

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def load(self) -> 'ModelRegistry':
        """
        Read layered config, extend sys.path with resolved site-packages,
        and return self.
        """
        prefixes: list = []
        bin_dirs: list = []
        surrogate_lib_dir: 'str | None' = None
        toml_log_level:    'str | None' = None
        toml_log_file:     'str | None' = None

        def _read_logging(cfg: dict) -> None:
            nonlocal toml_log_level, toml_log_file
            lc = cfg.get('logging', {})
            if 'level' in lc:
                toml_log_level = str(lc['level']).upper()
            if 'file' in lc:
                toml_log_file = str(lc['file'])

        # Layer 1: system-wide
        sys_cfg = _load_toml('/etc/modena/config.toml')
        prefixes.extend(sys_cfg.get('models', {}).get('paths', []))
        bin_dirs.extend(sys_cfg.get('binaries', {}).get('paths', []))
        surrogate_lib_dir = sys_cfg.get('surrogate_functions', {}).get(
            'lib_dir', surrogate_lib_dir
        )
        _read_logging(sys_cfg)

        # Layer 2: user-level
        user_cfg = _load_toml(Path.home() / '.modena' / 'config.toml')
        prefixes.extend(user_cfg.get('models', {}).get('paths', []))
        bin_dirs.extend(user_cfg.get('binaries', {}).get('paths', []))
        surrogate_lib_dir = user_cfg.get('surrogate_functions', {}).get(
            'lib_dir', surrogate_lib_dir
        )
        _read_logging(user_cfg)

        # Layer 3: project-level (nearest modena.toml ancestor of cwd)
        proj_cfg_path = _find_project_config()
        if proj_cfg_path is not None:
            proj_cfg = _load_toml(proj_cfg_path)
            prefixes.extend(proj_cfg.get('models', {}).get('paths', []))
            bin_dirs.extend(proj_cfg.get('binaries', {}).get('paths', []))
            surrogate_lib_dir = proj_cfg.get('surrogate_functions', {}).get(
                'lib_dir', surrogate_lib_dir
            )
            _read_logging(proj_cfg)
            _log.info("ModelRegistry: using project config %s", proj_cfg_path)

        # Layer 4: MODENA_PATH env var (os.pathsep-separated)
        env_path = os.environ.get('MODENA_PATH', '')
        if env_path:
            prefixes.extend(p for p in env_path.split(os.pathsep) if p)

        # Layer 4b: MODENA_BIN_PATH env var (os.pathsep-separated)
        env_bin_path = os.environ.get('MODENA_BIN_PATH', '')
        if env_bin_path:
            bin_dirs.extend(p for p in env_bin_path.split(os.pathsep) if p)

        # Layer 4c: MODENA_SURROGATE_LIB_DIR env var
        env_lib_dir = os.environ.get('MODENA_SURROGATE_LIB_DIR', '')
        if env_lib_dir:
            surrogate_lib_dir = env_lib_dir

        self._surrogate_lib_dir = surrogate_lib_dir
        self._toml_log_level    = toml_log_level
        self._toml_log_file     = toml_log_file

        # Resolve binary search dirs; de-duplicate preserving order
        seen_bin: set = set()
        resolved_bin: list = []
        for raw in bin_dirs:
            p = str(Path(raw).expanduser().resolve())
            if p not in seen_bin:
                seen_bin.add(p)
                resolved_bin.append(p)
        self._bin_dirs = resolved_bin

        # Expand ~ and resolve; de-duplicate preserving order
        seen: set = set()
        resolved: list = []
        for raw in prefixes:
            p = str(Path(raw).expanduser().resolve())
            if p not in seen:
                seen.add(p)
                resolved.append(p)
        self._prefixes = resolved

        # Prepend site-packages dirs to sys.path
        added: list = []
        for prefix in resolved:
            for sp in _site_packages_in_prefix(prefix):
                if sp not in sys.path:
                    sys.path.insert(0, sp)
                    added.append(sp)

        if added:
            _log.info("ModelRegistry: added %d path(s) to sys.path", len(added))
        elif resolved:
            _log.info(
                "ModelRegistry: %d prefix(es) configured; no new site-packages found",
                len(resolved),
            )
        else:
            _log.info(
                "ModelRegistry: no model paths configured. "
                "Create '%s' with [models] paths = [...] or set MODENA_PATH.",
                _CONFIG_FILE,
            )

        return self

    @property
    def surrogate_lib_dir(self) -> Path:
        """
        Directory where compiled surrogate-function shared libraries are stored.

        Resolution order (last wins):
          1. Built-in default: <home>/.modena/surrogate_functions
          2. System config  /etc/modena/config.toml   [surrogate_functions] lib_dir
          3. User config    ~/.modena/config.toml      [surrogate_functions] lib_dir
          4. Project config modena.toml                [surrogate_functions] lib_dir
          5. Env var        MODENA_SURROGATE_LIB_DIR

        Use "." to compile into the current working directory (original behaviour;
        libraries will be re-compiled whenever the working directory changes).
        """
        if self._surrogate_lib_dir is None:
            return Path.home() / '.modena' / 'surrogate_functions'
        raw = self._surrogate_lib_dir
        if raw == '.':
            return Path.cwd()
        return Path(raw).expanduser().resolve()

    @property
    def bin_search_path(self) -> list:
        """
        Ordered list of directories searched by find_binary().

        Populated from (lowest to highest priority):
          1. [binaries] paths in /etc/modena/config.toml
          2. [binaries] paths in ~/.modena/config.toml
          3. [binaries] paths in modena.toml
          4. MODENA_BIN_PATH env var  (colon-separated)

        The package-relative fallback (dirname(caller_file)/bin/) is NOT
        included here — it is checked implicitly by find_binary() when
        caller_file is supplied.
        """
        return list(self._bin_dirs)

    def find_binary(self, name: str, caller_file: 'str | None' = None) -> str:
        """
        Search configured binary paths for *name*.

        Search order:
          1. Each directory in bin_search_path (from config + env var).
          2. If *caller_file* is given: dirname(caller_file)/bin/*name*
             (the package-relative convention used by BackwardMappingScriptTask).

        Args:
            name:        Binary filename to locate (e.g. 'flowRateExact').
            caller_file: Absolute path to the calling .py file.  Typically
                         ``inspect.getfile(type(self))`` from a FireTask.
                         Enables the package-relative fallback.

        Returns:
            Absolute path to the binary.

        Raises:
            FileNotFoundError: if the binary is not found in any location.
        """
        for d in self._bin_dirs:
            candidate = Path(d) / name
            if candidate.is_file():
                return str(candidate)
        if caller_file is not None:
            fallback = Path(caller_file).resolve().parent / 'bin' / name
            if fallback.is_file():
                return str(fallback)
            fallback_dir = str(fallback.parent)
        else:
            fallback_dir = None

        searched = list(self._bin_dirs)
        if fallback_dir is not None:
            searched.append(fallback_dir)
        raise FileNotFoundError(
            f"Binary '{name}' not found. Searched: {searched}"
        )

    def active_packages(self) -> dict:
        """
        Scan .dist-info directories in all registered prefixes.
        Returns {package_name: version} for installed model packages.
        """
        packages: dict = {}
        for prefix in self._prefixes:
            for sp in _site_packages_in_prefix(prefix):
                for di in _glob.glob(str(Path(sp) / '*.dist-info')):
                    name, version = _read_dist_info(di)
                    if name and version:
                        packages[name] = version
        self._packages = packages
        return packages

    def freeze(
        self,
        lock_path: 'str | Path' = _LOCK_FILE,
        model_ids: 'list | None' = None,
    ) -> None:
        """
        Write modena.lock with current package versions and model states
        from MongoDB.

        Args:
            lock_path:  Path to the lock file (default: modena.lock).
            model_ids:  If provided, only snapshot these model IDs (as
                        accumulated by ParameterFitting via fw_spec).  Pass an
                        empty list to write a packages-only lock (no models were
                        retrained in this run).  Pass None to snapshot every
                        model in the database (CLI / manual use).
        """
        data = self._build_lock_data(model_ids=model_ids)
        _write_toml(lock_path, data)

    def restore(
        self,
        lock_path: 'str | Path' = _LOCK_FILE,
        verify_only: bool = False,
    ) -> None:
        """
        Read modena.lock, check package version consistency, and optionally
        restore model parameters to MongoDB.

        Args:
            lock_path:    Path to the lock file (default: modena.lock).
            verify_only:  If True, only report mismatches; do not restore DB.
        """
        data = _load_toml(lock_path)
        if not data:
            _log.info("No lock file found at %s", lock_path)
            return

        # Version check
        pkg_versions = data.get('packages', {})
        current = self.active_packages()
        mismatches: list = []
        for name, locked_ver in pkg_versions.items():
            cur_ver = current.get(name)
            if cur_ver != locked_ver:
                mismatches.append(
                    f"  {name}: locked={locked_ver}, "
                    f"current={cur_ver or 'not installed'}"
                )
        if mismatches:
            _log.warning(
                "Package version mismatches:\n%s",
                "\n".join(mismatches),
            )
        else:
            _log.info("All package versions match lock file.")

        if verify_only:
            return

        # Restore model parameters
        models_data = data.get('models', {})
        if not models_data:
            return

        try:
            from modena.SurrogateModel import SurrogateModel
        except ImportError:
            _log.info("Cannot import SurrogateModel; skipping parameter restore.")
            return

        for model_id, mdata in models_data.items():
            params = mdata.get('parameters')
            if params is None:
                continue
            try:
                model = SurrogateModel.objects.get(_id=model_id)
                model.parameters = params
                model.save()
                _log.info("Restored parameters for model '%s'", model_id)
            except Exception as exc:
                _log.error("Could not restore model '%s': %s", model_id, exc)

    def update_lock(
        self,
        model,
        lock_path: 'str | Path' = _LOCK_FILE,
    ) -> None:
        """
        Update a single model's entry in modena.lock after retraining.
        Creates the lock file if it does not yet exist.
        """
        data = _load_toml(lock_path)
        if 'meta' not in data:
            data['meta'] = {
                'modena_version': _modena_version(),
                'generated': _now_iso(),
            }
        if 'packages' not in data:
            data['packages'] = self.active_packages()
        data.setdefault('models', {})[model._id] = _model_entry(model)
        _write_toml(lock_path, data)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _build_lock_data(self, model_ids: 'list | None' = None) -> dict:
        packages = self.active_packages()
        data: dict = {
            'meta': {
                'modena_version': _modena_version(),
                'generated': _now_iso(),
            },
            'packages': packages,
            'models': {},
        }
        try:
            from modena.SurrogateModel import SurrogateModel
            if model_ids is None:
                # CLI / manual use: snapshot every model in the database.
                for model in SurrogateModel.objects:
                    data['models'][model._id] = _model_entry(model)
            else:
                # Workflow use: only snapshot the models that were actually
                # retrained in this run (as reported by ParameterFitting via
                # fw_spec['_modena_fitted_models']).  This avoids loading and
                # compiling surrogate libraries for unrelated models.
                for mid in dict.fromkeys(model_ids):   # deduplicate, keep order
                    try:
                        model = SurrogateModel.objects.get(_id=mid)
                        data['models'][model._id] = _model_entry(model)
                    except Exception as exc:
                        _log.error("Could not load model '%s': %s", mid, exc)
        except Exception as exc:
            _log.error("Could not read models from MongoDB: %s", exc)
        return data


# --------------------------------------------------------------------------- #
# Module-level helpers                                                         #
# --------------------------------------------------------------------------- #

def _read_dist_info(dist_info_dir: str) -> 'tuple[str | None, str | None]':
    """Extract Name and Version from a .dist-info directory."""
    for fname in ('METADATA', 'PKG-INFO'):
        meta = Path(dist_info_dir) / fname
        if not meta.is_file():
            continue
        name = version = None
        try:
            with open(meta, encoding='utf-8', errors='replace') as fh:
                for line in fh:
                    if line.startswith('Name:'):
                        name = line.split(':', 1)[1].strip()
                    elif line.startswith('Version:'):
                        version = line.split(':', 1)[1].strip()
                    if name and version:
                        break
        except OSError:
            continue
        if name and version:
            return name, version
    return None, None


def _model_entry(model) -> dict:
    """Build a lock-file entry dict for a single SurrogateModel."""
    entry: dict = {}
    if hasattr(model, 'surrogateFunction') and model.surrogateFunction:
        entry['surrogate_function'] = model.surrogateFunction.name
    if hasattr(model, 'fitData') and model.fitData:
        vals = next(iter(model.fitData.values()), [])
        entry['n_samples'] = len(vals)
    if model.parameters:
        entry['parameters'] = list(model.parameters)
    if hasattr(model, 'last_fitted') and model.last_fitted:
        entry['last_fitted'] = model.last_fitted.strftime('%Y-%m-%dT%H:%M:%S')
    return entry


def _modena_version() -> str:
    try:
        from importlib.metadata import version
        return version('modena')
    except Exception:
        return 'unknown'


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')


# --------------------------------------------------------------------------- #
# Minimal TOML writer (no tomli-w dependency)                                 #
# --------------------------------------------------------------------------- #

def _write_toml(path: 'str | Path', data: dict) -> None:
    """
    Write *data* to *path* as TOML.  Uses tomli-w if available, otherwise
    falls back to a minimal built-in writer sufficient for the lock format.
    """
    try:
        import tomli_w
        with open(path, 'wb') as fh:
            tomli_w.dump(data, fh)
    except ImportError:
        _write_toml_minimal(path, data)
    _log.info("Lock written to %s", path)


def _write_toml_minimal(path: 'str | Path', data: dict) -> None:
    """Minimal TOML serialiser for simple flat/nested dicts (no arrays of tables)."""
    lines: list = []

    def _val(v) -> str:
        if isinstance(v, bool):
            return 'true' if v else 'false'
        if isinstance(v, int):
            return str(v)
        if isinstance(v, float):
            return repr(v)
        if isinstance(v, str):
            escaped = v.replace('\\', '\\\\').replace('"', '\\"')
            return f'"{escaped}"'
        if isinstance(v, list):
            inner = ', '.join(_val(x) for x in v)
            return f'[{inner}]'
        return f'"{v}"'

    def _emit(prefix: str, d: dict) -> None:
        flat = {k: v for k, v in d.items() if not isinstance(v, dict)}
        nested = {k: v for k, v in d.items() if isinstance(v, dict)}

        if prefix:
            lines.append(f'\n[{prefix}]')
        for k, v in flat.items():
            lines.append(f'{k} = {_val(v)}')
        for k, v in nested.items():
            _emit(f'{prefix}.{k}' if prefix else k, v)

    _emit('', data)
    Path(path).write_text('\n'.join(lines) + '\n', encoding='utf-8')
