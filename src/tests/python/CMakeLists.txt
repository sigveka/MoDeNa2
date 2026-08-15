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
set_tests_properties(modena_python_unit PROPERTIES
    LABELS "python;unit"
)

# ---------------------------------------------------------------------------
# Integration tests — require live MongoDB and the full modena stack
# Run explicitly with: ctest -L integration
# ---------------------------------------------------------------------------
add_test(
    NAME    modena_python_integration
    COMMAND ${Python3_EXECUTABLE} -m pytest ${_TEST_DIR}
            -m "integration"
            --tb=short -q
    WORKING_DIRECTORY ${_TEST_DIR}
)
set_tests_properties(modena_python_integration PROPERTIES
    LABELS           "python;integration"
    DISABLED         TRUE      # skipped by default; enable with ctest -L integration
)
