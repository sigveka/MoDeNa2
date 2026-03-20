# MoDeNa Model Registry

## Philosophy

Surrogate models in MoDeNa are distributable Python packages.  A single
model package (e.g. `flowRate`, `idealGas`) can be installed once and shared
across many projects, or kept isolated to a single project — the choice
belongs to the user.

The framework never assumes a fixed models directory.  Instead it reads a
layered configuration to find where models are installed, and fails
gracefully with a helpful message when a required model cannot be found.

---

## How model paths are resolved

The `ModelRegistry` reads model search prefixes from four sources, in order
from lowest to highest priority:

| Priority | Source | Format |
|----------|--------|--------|
| 1 (lowest) | `/etc/modena/config.toml` | system-wide |
| 2 | `~/.modena/config.toml` | user-level |
| 3 | `modena.toml` (nearest ancestor of `cwd`) | project-level |
| 4 (highest) | `MODENA_PATH` env var | colon-separated list |

Each source contributes a list of **prefix directories**.  Inside each prefix,
MoDeNa looks for `lib/pythonX.Y/site-packages/` directories and prepends them
to `sys.path` so that installed model packages become importable.

### Config file format

```toml
# modena.toml  (or config.toml)
[models]
paths = [
    "~/.modena/models",          # shared user-level pool
    "./local_models",            # project-local overrides
]

[binaries]
paths = [
    "~/.modena/bin",             # user-level exact-simulation binaries
    "./models/bin",              # project-local binaries
]
```

### Environment variables

```bash
export MODENA_PATH="$HOME/.modena/models:/opt/company/modena-models"
export MODENA_BIN_PATH="$HOME/.modena/bin:/opt/company/modena-models/bin"
```

Paths in `MODENA_PATH` and `MODENA_BIN_PATH` are added **after** all config-file
paths, so they take highest precedence.

---

## Sharing models across projects

Install a model package once into a shared prefix:

```bash
cd examples/MoDeNaModels/flowRate
pip install --prefix ~/.modena/models .
```

Then declare that prefix in your user config:

```toml
# ~/.modena/config.toml
[models]
paths = ["~/.modena/models"]
```

Every project that runs `import modena` will now find `flowRate` automatically.

---

## Keeping models project-local

Install into the project's own prefix and point to it from a project-level
config file:

```bash
# Inside the project directory
cd examples/twoTanksCxx
./buildModels          # installs to ./models/
```

```toml
# examples/twoTanksCxx/modena.toml
[models]
paths = ["./models"]
```

MoDeNa walks up from the current working directory to find the nearest
`modena.toml`, so any sub-directory of the project inherits the config
automatically.

---

## Graceful failure

If MoDeNa cannot find a model package at import time it raises an
`ImportError` with a message that names the missing package and suggests
where to look:

```
ImportError: Model package 'flowRate' not found.
  Searched paths: /home/user/.modena/models/lib/python3.11/site-packages
  Install it with:  pip install --prefix <prefix> <path-to-flowRate>
  Or set MODENA_PATH to a directory that contains it.
```

---

## Dependency resolution at runtime

MoDeNa resolves model dependencies lazily.  When simulation A calls model B,
and model B depends on model C, the framework discovers C only when B is
first evaluated — the master project does not need to list C explicitly.  If
C's package is available anywhere on the registry search path the import
succeeds silently; if not, MoDeNa raises an `ImportError` and stops with a
clear message rather than producing silent wrong results.

---

## Self-documenting projects — `modena.lock`

At the end of every successful simulation run MoDeNa writes a `modena.lock`
file in the working directory.  This file records:

* the version of every installed model package that was active during the run;
* the fitted surrogate parameters for every model in the database;
* the timestamp of the last fitting for each model.

### Lock file format

```toml
[meta]
modena_version = "1.0"
generated      = "2026-03-14T10:05:33"

[packages]
flowRate = "1.0"
idealGas = "2.3"

[models.flowRate]
surrogate_function = "flowRate"
n_samples          = 42
parameters         = [1.234, 5.678, 9.012]
last_fitted        = "2026-03-14T09:55:00"

[models.idealGas]
surrogate_function = "idealGas"
n_samples          = 100
parameters         = [8.314]
last_fitted        = "2026-03-14T08:30:00"
```

### Incremental updates

Each time a surrogate is retrained during a simulation the relevant
`[models.<id>]` block is updated immediately, so the lock file always
reflects the current state even if the run is interrupted.

### CLI commands

**Freeze** — write a lock file manually:

```bash
python -m modena freeze                   # writes modena.lock
python -m modena freeze -o my.lock        # custom path
```

**Restore** — reproduce a previous run's surrogate state:

```bash
python -m modena restore                  # reads modena.lock, restores DB
python -m modena restore --verify-only    # only check package versions
python -m modena restore -i my.lock       # custom path
```

### Committing the lock file

Committing `modena.lock` to version control lets collaborators and CI
systems reproduce the exact fitted surrogate state of a simulation:

```bash
git add modena.lock
git commit -m "pin surrogate parameters after calibration run"
```

To reproduce:

```bash
git checkout <commit>
python -m modena restore
```

---

## Installing a model package

Model packages follow the standard Python packaging layout.  A typical
`setup.py` (or `pyproject.toml`) in the model directory is sufficient:

```bash
pip install --prefix ~/.modena/models ./examples/MoDeNaModels/flowRate
```

Or use the `buildModels` helper script provided in each example, which calls
CMake to compile any native extensions before installing:

```bash
cd examples/twoTanksCxx
./buildModels          # compiles + installs flowRate and twoTankCxx
```

---

## Summary of configuration options

### Model packages

| Mechanism | Example | Scope |
|-----------|---------|-------|
| `/etc/modena/config.toml` | `[models] paths = ["/opt/modena/models"]` | system |
| `~/.modena/config.toml` | `[models] paths = ["~/.modena/models"]` | user |
| `modena.toml` in project root | `[models] paths = ["./models"]` | project |
| `MODENA_PATH` env var | `export MODENA_PATH=~/.modena/models` | session |
| `modena freeze` / `modena restore` | — | provenance |

### Exact-simulation binaries

| Mechanism | Example | Scope |
|-----------|---------|-------|
| `/etc/modena/config.toml` | `[binaries] paths = ["/opt/modena/bin"]` | system |
| `~/.modena/config.toml` | `[binaries] paths = ["~/.modena/bin"]` | user |
| `modena.toml` in project root | `[binaries] paths = ["./models/bin"]` | project |
| `MODENA_BIN_PATH` env var | `export MODENA_BIN_PATH=~/.modena/bin` | session |
| package-relative fallback | `dirname(FireTask.__file__)/bin/` | automatic |

---

## Environment variable reference

| Variable | Default | Purpose |
|----------|---------|---------|
| `MODENA_URI` | `mongodb://localhost:27017/test` | MongoDB connection URI used by all Python components. Set this to point at a remote or non-default database. |
| `MODENA_PATH` | _(none)_ | Colon-separated list of model prefix directories, appended after all config-file paths. Highest-priority source for model search paths. |
| `MODENA_BIN_PATH` | _(none)_ | Colon-separated list of directories to search for exact-simulation binaries. Appended after all `[binaries] paths` from config files. When absent, MoDeNa falls back to `bin/` alongside the FireTask's `.py` file. |
| `MODENA_SURROGATE_LIB_DIR` | `~/.modena/surrogate_functions` | Directory where compiled surrogate-function shared libraries (`.so` files) are stored. Overrides the value in any config file. Use `"."` to compile into the current working directory. |
| `MODENA_LIB_DIR` | _(set by CMake at install time)_ | Location of `libmodena.so`. Normally set automatically; can be overridden for the MATLAB/Octave MEX gateway when Python is not on `PATH`. |

### Examples

```bash
# Use a remote MongoDB instance
export MODENA_URI=mongodb://dbserver.example.com:27017/modena

# Add a shared model pool at the session level
export MODENA_PATH=/opt/company/modena-models:$HOME/.modena/models

# Add a shared binary pool at the session level
export MODENA_BIN_PATH=/opt/company/modena-models/bin:$HOME/.modena/bin

# Compile surrogate functions into a project-local directory
export MODENA_SURROGATE_LIB_DIR=$(pwd)/surrogate_functions
```

These can also be set persistently via the layered config files
(see [How model paths are resolved](#how-model-paths-are-resolved)):

```toml
# modena.toml
[models]
paths = ["./models"]

[binaries]
paths = ["./models/bin"]

[surrogate_functions]
lib_dir = "./surrogate_functions"
```
