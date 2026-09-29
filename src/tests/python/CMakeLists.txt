find_package(Python3 COMPONENTS Interpreter REQUIRED)

set(_TEST_DIR ${CMAKE_CURRENT_SOURCE_DIR})

# Tiers -- one CTest label each, mirroring the pytest markers in
# ../pytest.ini:
#
#   unit       source tree only; the database is a MagicMock or mongomock
#   installed  needs `cmake --install`: headers and libmodena at the prefix
#
# There is no `live` entry here.  conftest.py in this directory stubs out the
# database connection, so tests needing a real MongoDB live in
# ../interface-tests/ instead; test_suite_integrity.py keeps it that way.
# ---------------------------------------------------------------------------

# MODENA_PATHS_FILE points conftest.py at the _paths.py this build generated.
# Its paths name the install prefix this build was configured for (not the
# build tree), so the installed tier tests what `cmake --install build` put
# there rather than whichever MoDeNa happens to be first on sys.path.
# Without it the conftest stub carries no MODENA_INCLUDE_DIR / MODENA_LIB_DIR
# and every "is modena installed?" guard answers no -- which is how this tier
# went unrun for months.
set(_MODENA_PATHS_FILE "${CMAKE_BINARY_DIR}/src/python/_paths.py")

# ---------------------------------------------------------------------------
# unit -- no MongoDB, no R, no libmodena required
# ---------------------------------------------------------------------------
add_test(
    NAME    modena_python_unit
    COMMAND ${Python3_EXECUTABLE} -m pytest ${_TEST_DIR}
            -m "not installed and not live"
            --tb=short -q
    WORKING_DIRECTORY ${_TEST_DIR}
)
set_tests_properties(modena_python_unit PROPERTIES
    LABELS      "python;unit"
    ENVIRONMENT "MODENA_PATHS_FILE=${_MODENA_PATHS_FILE}"
)

# ---------------------------------------------------------------------------
# installed -- compile real surrogates against the installed libmodena and
# exercise the MongoEngine document layer through mongomock.
#
# This entry used to carry DISABLED TRUE with a comment saying to "enable with
# ctest -L integration".  DISABLED overrides label selection, so that
# invocation silently listed 10 tests and never this one: the tier had no way
# to run at all.  It is enabled here and runs with every other test.
# ---------------------------------------------------------------------------
add_test(
    NAME    modena_python_installed
    COMMAND ${Python3_EXECUTABLE} -m pytest ${_TEST_DIR}
            -m "installed"
            --tb=short -q
    WORKING_DIRECTORY ${_TEST_DIR}
)
set_tests_properties(modena_python_installed PROPERTIES
    LABELS            "python;installed"
    ENVIRONMENT       "MODENA_PATHS_FILE=${_MODENA_PATHS_FILE}"
    FIXTURES_REQUIRED modena_installed
)
