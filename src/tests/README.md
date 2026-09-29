# MoDeNa Test Suite

Tests live under `src/tests/` in three directories:

```
src/tests/
├── pytest.ini       tier markers (installed, live) + --strict-markers
├── python/          pytest suite for the Python library (unit + installed)
├── c/               CTest executables for the C library (unit)
└── interface-tests/ language-wrapper smokes and cross-language contracts
                     (installed + live)
```

---

## Test tiers

Every test belongs to **exactly one** tier, chosen by what it needs to run.
Each tier needs everything the one above it does.  The CTest label and the
pytest marker have the same name.

| Tier (CTest label / pytest marker) | Needs | Examples |
|---|---|---|
| `unit` (pytest: unmarked) | the source tree only; MongoDB is a MagicMock or mongomock | `modena_python_unit`, `modena_c_*`, `modena_portal_unit` |
| `installed` | `cmake --install` has run: headers, `libmodena`, wrapper packages at the prefix | `modena_python_installed`, `modena_status_codes` |
| `live` | a real MongoDB at `MODENA_URI` holding a fitted `flowRate` | every `modena_iface_*` smoke, `modena_generated_snippets`, `modena_oob_exception` |

Language labels (`python`, `c`, `cpp`, `fortran`, `julia`, `r`, `octave`,
`matlab`) are a second, independent axis: `ctest -L live -L julia` runs the
Julia smoke only.

`test_suite_integrity.py` enforces the scheme: a CTest entry with no tier,
two tiers, or the retired `integration` label fails the `unit` tier, as does
a pytest file under `interface-tests/` whose marker disagrees with the `-m`
its CTest entry selects (it would be deselected and never run).

`live` tests live only in `interface-tests/`.  The `conftest.py` in `python/`
stubs out the database connection, so a `live` test there could never pass.

---

## Running the tests

Tests are **opt-in** — they are not built or run during a normal
`cmake --build .`.  Enable them with the `MODENA_BUILD_TESTS` flag (the `dev`
and `full` presets set it).

```bash
cmake --preset dev && cmake --build --preset dev
ctest --preset dev -L unit          # no install, no database

cmake --install build
ctest --preset dev -L installed     # needs the install

# live: needs MongoDB and a fitted flowRate first
(cd examples/twoTanks && ./buildModels && modena fw reset --force && ./initModels)
ctest --preset dev -L live
```

`modena fw reset --force` clears the FireWorks launchpad in the database
`MODENA_URI` names.  Point `MODENA_URI` at a throwaway database before running
the `live` tier on a machine whose launchpad you care about.

Directly with pytest (it picks up `src/tests/pytest.ini` from any of these):

```bash
pytest src/tests/python -m "not installed and not live"   # unit
pytest src/tests/python -m installed
pytest src/tests/interface-tests -m live
```

---

## Python tests

Located in `src/tests/python/`.  Run directly with pytest without CMake:

```bash
cd src/tests/python
pytest -v                       # unit + installed (installed skips if nothing is built)
pytest -m installed -v          # installed tier only
pytest -v --tb=long             # verbose tracebacks
```

### Dependencies

Install the test extras:

```bash
pip install pytest pytest-cov mongomock
```

| Package | Purpose |
|---|---|
| `pytest` | Test runner and framework |
| `pytest-cov` | Coverage reporting (optional) |
| `mongomock` | In-memory MongoDB for unit tests |

R and `rpy2` are **not** required for unit tests — they are stubbed out
automatically by `conftest.py`.  Integration tests require the full
MoDeNa stack including R.

### How the stubs work

`conftest.py` runs before any test module is imported and:

1. Stubs `rpy2` and `blessings` in `sys.modules` so `Strategy.py`'s
   module-level R initialisation calls become no-ops.
2. Creates a minimal `modena` package stub that points `__path__` at the
   source tree without executing `__init__.py`.  This prevents
   `import_helper()` from trying to load `libmodena.so`.
3. Patches `mongoengine.connect` with a MagicMock so importing
   `modena.SurrogateModel` (which calls `connect()` at module scope)
   does not require a live database.
4. Eagerly imports `modena.SurrogateModel` so its module-level
   `connect()` runs through the MagicMock stub before any test-level
   fixture can swap the connection.

Individual submodules (`modena.Launchpad`, `modena.Registry`, `modena.Runner`)
are imported directly in each test file — they work because the stub package's
`__path__` resolves them from the source tree.

### The `mongo_db` fixture — real MongoEngine query path via mongomock

Some code paths (`exceptionOutOfBounds`, `exceptionParametersNotValid`,
`loadFailing`, `loadParametersNotValid`, the `_pending_*_launch_id`
concurrency mechanism) need to actually execute MongoDB queries.  For
these, request the `mongo_db` fixture — it suspends the MagicMock stub,
opens an in-memory mongomock connection as the default alias, and
restores the stub after the test:

```python
def test_stamps_launch_id(mongo_db):
    from modena.SurrogateModel import SurrogateModel
    coll = SurrogateModel._get_collection()
    coll.insert_one({'_id': 'flowRate', '_cls': 'SurrogateModel'})
    SurrogateModel.objects(_id='flowRate').update_one(
        __raw__={'$set': {'_pending_init_launch_id': 'uuid-1234'}}
    )
    found = SurrogateModel.objects(
        __raw__={'_pending_init_launch_id': 'uuid-1234'}
    ).first()
    assert found._id == 'flowRate'
```

Tests using `mongo_db` run in ~5 ms each with per-test DB isolation.
See `test_mongo_integration.py` for the current suite (10 tests
covering the launch_id UUID mechanism and fallback loaders).

### Coverage report

```bash
cd src/tests/python
pytest --cov=modena --cov-report=term-missing
```

---

## C tests

Located in `src/tests/c/`.  Each test is a standalone executable that
returns `0` on success and non-zero on failure (detected by CTest).

### Current tests

| Executable | What it tests |
|---|---|
| `test_siunits` | `modena_siunits_new`, `modena_siunits_destroy`, exponent read/write |
| `test_inputsoutputs` | `modena_inputs_new/destroy`, `modena_outputs_new/destroy`, and the inline `modena_inputs_set/get` / `modena_outputs_get` roundtrip helpers — the C API almost every application uses |

`src/tests/python/test_auto_argpos.py` — Phase 1+2 of the named-parameter
rework: auto-assigned argPos for outputs+parameters, rejection of
user-supplied argPos, invalid-name rejection, SHA256 hash mixes in
declaration order (reordering forces recompile), `MinMaxArgPos` deleted.

`src/tests/python/test_named_parameters.py` — Phase 3+4: dict-typed
`SurrogateModel.parameters` schema, named accessors (get/set_parameter,
set_parameters, named_parameters, parameter_names, parameters_array,
set_parameters_array), constructor rejection of positional list,
dict persistence via mongomock, reordering-safety guarantee.

## Interface tests

Language-wrapper smoke tests live under `src/tests/interface-tests/`.
Each links a real language binding against libmodena and evaluates the
`flowRate` surrogate to end-to-end verify the wrapper is wired
correctly.  They are in the `live` tier because they require:

* a live MongoDB pointed to by `MODENA_URI` (default `mongodb://localhost:27017/test`),
* the `flowRate` model already initialized (`cd examples/twoTanks && ./initModels`).

Run with:

```bash
ctest --preset dev -L live
```

| Executable | Wrapper | What it tests |
|---|---|---|
| `test_cpp_smoke` | C++ (`modena::Model`) | RAII ctor + `input_pos`/`output_pos`/`set`/`call`/`output` end-to-end; asserts finite positive output in a plausible range; exercises the Phase 3 named-parameter accessors (`m.parameters()`, `m.parameter("P0")`) |
| `test_fortran_smoke` | Fortran 2003 (`fmodena_oop`) | Same coverage via `m%init` / `m%input_pos` / `m%set` / `m%call` / `m%get_output` |
| `test_thread_safety` | C (`libmodena` directly, `std::thread`) | N pthreads share one `modena_model_t` with per-thread I/O vectors; every call must reproduce the reference `mdot` bit-for-bit.  Regression guard for the `modena_substitute_model_t` per-call allocation fix and the internal GIL protocol. |
| `test_matlab_smoke` | MATLAB / Octave (via MEX gateway + `Modena.m` class) | Same coverage via `m.set_input`/`m.call`/`m.get_output`, plus Phase 3 named-parameter accessors (`m.parameters()` returning a struct, `m.get_parameter('P0')`).  Registered when `WITH_MATLAB=ON`; prefers Octave over MATLAB (faster startup, no license). |
| `test_julia_smoke.jl` | Julia (`Modena.jl`, pure `ccall` bindings) | Same coverage via `set!`/`call!`/`output`, plus `parameters(m)` / `parameter(m, "P0")` and the 1-based↔0-based argPos conversion.  Also covers the Libdl discovery of `libmodena.so`, the `RTLD_GLOBAL` libpython priming, and named access *after* `check` (the GIL-release segfault class).  Registered when `WITH_JULIA=ON`. |

### The out-of-bounds → refit loop (`modena_twotanks_loop`)

`test_twotanks_loop.py` runs the loop MoDeNa exists for: the twoTanks
simulation (`twoTanksMacroscopicProblem`) calls `flowRate`, leaves its trained
box, exits with 200, and FireWorks samples new points, refits and restarts the
simulation until a run finishes inside the box.  It asserts the workflow
completes and that it took **1 to 6 refits**.

It is self-contained: it installs `examples/MoDeNaModels/flowRate` and
`twoTank` into a temporary prefix, runs with a temporary `HOME` (because
`modena install` writes `~/.modena/config.toml`), and uses its own database
derived from `MODENA_URI` (`modena_looptest_<id>`, dropped afterwards).  It
needs a reachable MongoDB but neither `buildModels` nor `initModels`, and
takes about 25 s.

The refit count follows from `flowRate`'s initial points.  Each out-of-bounds
event widens only the offending input, to 1.2× the offending value, and the
simulation restarts from t = 0; an input therefore needs about
log(range)/log(1.2) events to cover what the simulation visits
(rho0 0.422–3.483, p0 36 364–300 000 Pa, p1Byp0 0.0333–0.9998, D fixed).
The initial box ends each input within one such step of that envelope, so
each input triggers at most one refit.  The earlier, narrow box
(rho0 3.4–3.5, p0 2.8–3.2e5, p1Byp0 0.03–0.04) needed 42.  If this test starts
reporting more than six, the initial points no longer fit the simulation.

### Notes

- The tests link against `libmodena` but never call `Py_Initialize()`.
  Only pure-C functions that have no Python dependency are tested here.
- `modena_siunits_get()` is declared in `inputsoutputs.h` but not yet
  implemented.  Its tests are compiled out with `#if 0` in `test_siunits.c`
  and should be enabled once the implementation is added to `inputsoutputs.c`.

---

## What is not tested here

| Component | Reason | Path forward |
|---|---|---|
| `Strategy.py` sampling / fitting | Requires R + rpy2 + MongoDB | Add under `installed` (mongomock) or `live` once R is available in CI |
| `modena_model_call` in C | Requires `Py_Initialize()` + MongoDB | Covered end-to-end by the `live` smokes |
| `SurrogateFunction` Ccode compilation | Requires gcc | Covered by `modena_python_installed` (`test_compile_surrogate.py`) |

---

## Adding new tests

### Python

Add a new file `src/tests/python/test_<module>.py`.  It is picked up
automatically by pytest.  Leave unit tests unmarked; mark a test that needs
the installed tree `@pytest.mark.installed`.  A test that needs a live MongoDB
goes in `src/tests/interface-tests/` with a module-level
`pytestmark = pytest.mark.live`, and needs a CTest entry there selecting
`-m live`.

### C

Add a new `.c` file to `src/tests/c/` and register it in
`src/tests/c/CMakeLists.txt`:

```cmake
add_executable(test_myfeature test_myfeature.c)
target_include_directories(test_myfeature PRIVATE ${CMAKE_SOURCE_DIR}/src)
target_link_libraries(test_myfeature PRIVATE modena ${Python3_LIBRARIES})
add_test(NAME modena_c_myfeature COMMAND test_myfeature)
set_tests_properties(modena_c_myfeature PROPERTIES LABELS "c;unit")
```
