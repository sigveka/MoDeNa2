# ---------------------------------------------------------------------------
# C unit tests for libmodena
#
# These tests exercise pure-C functions (struct allocation, array writes)
# that have no Python dependency.  They compile the relevant libmodena
# source files directly rather than linking against libmodena.so, which
# carries an __attribute__((constructor)) on PyInit_libmodena() that would
# call Py_Initialize() and attempt "import modena" before main() runs.
# Compiling source files directly avoids the constructor entirely.
# ---------------------------------------------------------------------------

find_package(Python3 COMPONENTS Development REQUIRED)

# -- test_siunits: tests modena_siunits_new/destroy/set --------------------
# Only inputsoutputs.c is needed.  It includes global.h (Python compat
# shims, no Python init) and model.h (forward declarations only here).
add_executable(test_siunits
    test_siunits.c
    ${CMAKE_SOURCE_DIR}/src/src/inputsoutputs.c
    ${CMAKE_BINARY_DIR}/src/src      # generated modena_status.h, via global.h
)

target_include_directories(test_siunits PRIVATE
    ${CMAKE_SOURCE_DIR}/src/src      # inputsoutputs.h, global.h, inline.h
    ${CMAKE_BINARY_DIR}/src/src      # generated modena_status.h, via global.h
    ${Python3_INCLUDE_DIRS}          # Python.h pulled in via global.h
)

# No link against libmodena — avoids PyInit_libmodena constructor.
# Only Python3 libraries needed to satisfy Python.h symbols used in global.h.
target_link_libraries(test_siunits PRIVATE ${Python3_LIBRARIES})

add_test(NAME modena_c_siunits COMMAND test_siunits)
set_tests_properties(modena_c_siunits PROPERTIES LABELS "c;unit")

# -- test_inputsoutputs: alloc + inline set/get roundtrip -----------------
# Exercises modena_inputs_new/destroy, modena_outputs_new/destroy, and the
# inline modena_inputs_set/get / modena_outputs_get helpers from inline.h
# (compiled via inputsoutputs.h) — the C API most every application uses.
# Same pattern as test_siunits: compile inputsoutputs.c directly, no link
# against libmodena so the PyInit_libmodena constructor never fires.
add_executable(test_inputsoutputs
    test_inputsoutputs.c
    ${CMAKE_SOURCE_DIR}/src/src/inputsoutputs.c
    ${CMAKE_BINARY_DIR}/src/src      # generated modena_status.h, via global.h
)

target_include_directories(test_inputsoutputs PRIVATE
    ${CMAKE_SOURCE_DIR}/src/src
    ${CMAKE_BINARY_DIR}/src/src      # generated modena_status.h, via global.h
    ${Python3_INCLUDE_DIRS}
)

target_link_libraries(test_inputsoutputs PRIVATE ${Python3_LIBRARIES})

add_test(NAME modena_c_inputsoutputs COMMAND test_inputsoutputs)
set_tests_properties(modena_c_inputsoutputs PROPERTIES LABELS "c;unit")
