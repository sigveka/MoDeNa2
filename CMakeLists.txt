cmake_minimum_required(VERSION 3.22...3.28)

# Outlaw in-source builds --------------------------------------------------- #
set(CMAKE_DISABLE_SOURCE_CHANGES ON)
set(CMAKE_DISABLE_IN_SOURCE_BUILD ON)

# One project declaration for the whole repository -------------------------- #
project(modena VERSION 2.0 LANGUAGES C CXX)

# Options ------------------------------------------------------------------- #
option(MODENA_BUILD_DOCS  "Build Doxygen API documentation"                 OFF)

# Testing ------------------------------------------------------------------- #
# enable_testing() must be called here, in the TOP-LEVEL CMakeLists, for ctest
# to emit a root CTestTestfile.cmake that recurses into the subdirectories.
# src/CMakeLists.txt also calls it (it is dual-use and must work standalone),
# but a call in a subdirectory only registers that subtree — without this line
# `ctest --preset dev` from the root build dir reports "Total Tests: 0" while
# every test is in fact registered under build/src/tests/.
enable_testing()

# Library source (defines modena targets and all sub-options) --------------- #
add_subdirectory(src)

# Documentation ------------------------------------------------------------- #
# Doxygen is run from the repository root so that the relative INPUT paths
# in doc/Doxyfile (src/, examples/, applications/, README.md) resolve correctly.
if(MODENA_BUILD_DOCS)
    find_package(Doxygen)
    if(DOXYGEN_FOUND)
        add_custom_target(doc
            COMMAND ${DOXYGEN_EXECUTABLE} ${CMAKE_SOURCE_DIR}/doc/Doxyfile
            WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
            COMMENT "Generating API documentation with Doxygen"
            VERBATIM
        )
    else()
        message(WARNING
            "MODENA_BUILD_DOCS=ON but Doxygen was not found. "
            "Install doxygen and re-run cmake.")
    endif()
endif()
