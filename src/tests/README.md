# MoDeNa Test Suite

Tests live under `src/tests/` and are split into two directories:

```
src/tests/
├── python/          pytest test suite for the Python library
├── c/               CTest executables for the C library
└── interface-tests/ End-to-end C++ integration tests (pre-existing)
```

---

## Running the tests

Tests are **opt-in** — they are not built or run during a normal
`cmake --build .`.  Enable them with the `MODENA_BUILD_TESTS` flag.

### Quick start

```bash
# From your existing build directory
cmake -DMODENA_BUILD_TESTS=ON ..
cmake --build .
ctest --output-on-failure
```

Or equivalently using the `test` target:

```bash
cmake -DMODENA_BUILD_TESTS=ON ..
cmake --build . --target test
```

### Run only unit tests (no MongoDB required)

```bash
ctest -L unit --output-on-failure
```

### Run only Python tests

```bash
ctest -L python --output-on-failure
```

### Run only C tests

```bash
ctest -L c --output-on-failure
```

### Run integration tests (requires live MongoDB)

Integration tests are disabled by default.  Enable and run them with:

```bash
ctest -L integration --output-on-failure
```

Or directly with pytest:

```bash
cd src/tests/python
pytest -m integration -v
```

---

## Test categories

| CTest label | pytest mark | MongoDB required | Description |
|---|---|---|---|
| `unit` | `not integration` | No | Pure logic, in-memory mocks |
| `integration` | `integration` | Yes | Full workflow with live MongoDB |
| `python` | — | Depends | All Python tests |
| `c` | — | No | C library tests |

---

## Python tests

Located in `src/tests/python/`.  Run directly with pytest without CMake:

```bash
cd src/tests/python
pytest -v                       # unit tests only (default)
pytest -m integration -v        # integration tests
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
3. Sets `MODENA_URI=mongomock://localhost/testdb` so any `mongoengine.connect()`
   call uses an in-memory database.

Individual submodules (`modena.Launchpad`, `modena.Registry`, `modena.Runner`)
are imported directly in each test file — they work because the stub package's
`__path__` resolves them from the source tree.

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
| `Strategy.py` sampling / fitting | Requires R + rpy2 + MongoDB | Add under `integration` once R is available in CI |
| `modena_model_call` in C | Requires `Py_Initialize()` + MongoDB | Test via Python integration tests |
| Full backward-mapping loop | Requires compiled surrogate + MongoDB | Add an `examples/`-based smoke test |
| `SurrogateFunction` Ccode compilation | Requires gcc + MongoDB | Integration test |

---

## Adding new tests

### Python

Add a new file `src/tests/python/test_<module>.py`.  It is picked up
automatically by pytest.  Use the `@pytest.mark.integration` decorator for
any test that requires a live MongoDB connection.

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
