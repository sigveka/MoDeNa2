find_package(Python3 COMPONENTS Interpreter REQUIRED)

set(_TEST_DIR ${CMAKE_CURRENT_SOURCE_DIR})

# ---------------------------------------------------------------------------
# Unit tests — no MongoDB, no R, no libmodena required
# ---------------------------------------------------------------------------
add_test(
    NAME    modena_python_unit
    COMMAND ${Python3_EXECUTABLE} -m pytest ${_TEST_DIR}
            -m "not integration"
            --tb=short -q
    WORKING_DIRECTORY ${_TEST_DIR}
)
# MODENA_PATHS_FILE points conftest.py at the _paths.py this build generated,
# so the tests exercise the tree that was just built rather than whatever
# happens to be installed.  Without it the conftest stub carries no
# MODENA_INCLUDE_DIR / MODENA_LIB_DIR and every "is modena built?" guard
# answers no -- which is how the integration tier went unrun for months.
set(_MODENA_PATHS_FILE "${CMAKE_BINARY_DIR}/src/python/_paths.py")

set_tests_properties(modena_python_unit PROPERTIES
    LABELS      "python;unit"
    ENVIRONMENT "MODENA_PATHS_FILE=${_MODENA_PATHS_FILE}"
)

# ---------------------------------------------------------------------------
# Integration tests — compile real surrogates against the built libmodena and
# exercise the MongoEngine document layer through mongomock.
#
# This entry used to carry DISABLED TRUE with a comment saying to "enable with
# ctest -L integration".  DISABLED overrides label selection, so that
# invocation silently listed 10 tests and never this one: the tier had no way
# to run at all.  It is enabled here and runs with every other test.
# ---------------------------------------------------------------------------
add_test(
    NAME    modena_python_integration
    COMMAND ${Python3_EXECUTABLE} -m pytest ${_TEST_DIR}
            -m "integration"
            --tb=short -q
    WORKING_DIRECTORY ${_TEST_DIR}
)
set_tests_properties(modena_python_integration PROPERTIES
    LABELS      "python;integration"
    ENVIRONMENT "MODENA_PATHS_FILE=${_MODENA_PATHS_FILE}"
)
