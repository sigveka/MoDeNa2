cmake_minimum_required(VERSION 3.22...3.28)

enable_testing()

find_package(Python3 COMPONENTS Interpreter REQUIRED)

# ---------------------------------------------------------------------------
# The database the live tier runs against
#
# The live fixture below drops this database and resets its FireWorks
# launchpad, so it must never be one that holds real work.  It is therefore
# a setting of its own rather than whatever MODENA_URI happens to be in the
# environment, and its database name must start with `modena_` and contain
# `test` -- which rules out both `modena` (the conventional working
# database) and `test` (SurrogateModel's default when MODENA_URI is unset).
# ---------------------------------------------------------------------------
set(MODENA_TEST_URI "mongodb://localhost:27017/modena_ctest" CACHE STRING
    "MongoDB URI the live test tier uses; its database is dropped by the tests")

string(REGEX MATCH "/([^/?]+)(\\?.*)?$" _modena_test_db_match "${MODENA_TEST_URI}")
set(_modena_test_db "${CMAKE_MATCH_1}")
if(NOT _modena_test_db MATCHES "^modena_.*test")
    message(FATAL_ERROR
        "MODENA_TEST_URI=${MODENA_TEST_URI} names the database "
        "'${_modena_test_db}'.  The live tests drop that database, so its "
        "name must start with 'modena_' and contain 'test' "
        "(default: mongodb://localhost:27017/modena_ctest).")
endif()

# Everything the live fixture writes -- installed model packages, compiled
# surrogates, FireWorks launch directories -- stays under the build tree.
set(MODENA_TEST_WORKDIR "${CMAKE_BINARY_DIR}/test-live")

#: The environment every live test and the live fixture share.  Applied with
#: modena_require_live() in interface-tests/CMakeLists.txt.
set(MODENA_LIVE_ENVIRONMENT
    "MODENA_URI=${MODENA_TEST_URI}"
    "MODENA_PATH=${MODENA_TEST_WORKDIR}/models"
    "MODENA_SURROGATE_LIB_DIR=${MODENA_TEST_WORKDIR}/surrogates"
)

# ---------------------------------------------------------------------------
# Fixtures
#
#   modena_installed  the install prefix holds this build (not an older one)
#   modena_live_db    MODENA_TEST_URI holds a freshly fitted flowRate
#
# Required by the installed and live tiers respectively, so `ctest -L live`
# pulls in the setup on its own: there is no manual buildModels / fw reset /
# initModels step to remember, and no way to run the live tier against a
# stale database left over from a previous run.
# ---------------------------------------------------------------------------
set(_FIXTURE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/fixtures")

add_test(
    NAME    modena_fixture_installed
    COMMAND ${Python3_EXECUTABLE} "${_FIXTURE_DIR}/check_installed.py"
            --built-lib     "$<TARGET_FILE:modena>"
            --installed-lib "${INSTALL_LIB_DIR}/modena/$<TARGET_FILE_NAME:modena>"
            --source-python "${CMAKE_SOURCE_DIR}/src/python"
)
set_tests_properties(modena_fixture_installed PROPERTIES
    LABELS         "installed;fixture"
    FIXTURES_SETUP modena_installed
)

add_test(
    NAME    modena_fixture_live_setup
    COMMAND ${Python3_EXECUTABLE} "${_FIXTURE_DIR}/live_db.py" setup
            --workdir    "${MODENA_TEST_WORKDIR}"
            --models-src "${CMAKE_SOURCE_DIR}/examples/MoDeNaModels"
)
set_tests_properties(modena_fixture_live_setup PROPERTIES
    LABELS            "live;fixture"
    FIXTURES_SETUP    modena_live_db
    FIXTURES_REQUIRED modena_installed
    RESOURCE_LOCK     modena_live_db
    ENVIRONMENT       "${MODENA_LIVE_ENVIRONMENT}"
    TIMEOUT           900
)

add_test(
    NAME    modena_fixture_live_cleanup
    COMMAND ${Python3_EXECUTABLE} "${_FIXTURE_DIR}/live_db.py" cleanup
            --workdir    "${MODENA_TEST_WORKDIR}"
)
set_tests_properties(modena_fixture_live_cleanup PROPERTIES
    LABELS           "live;fixture"
    FIXTURES_CLEANUP modena_live_db
    RESOURCE_LOCK    modena_live_db
    ENVIRONMENT      "${MODENA_LIVE_ENVIRONMENT}"
)

add_subdirectory(python)
add_subdirectory(c)
add_subdirectory(interface-tests)
