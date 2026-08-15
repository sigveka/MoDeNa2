cmake_minimum_required(VERSION 3.22...3.28)

# Outlaw in-source builds --------------------------------------------------- #
set(CMAKE_DISABLE_SOURCE_CHANGES ON)
set(CMAKE_DISABLE_IN_SOURCE_BUILD ON)

# One project declaration for the whole repository -------------------------- #
project(modena VERSION 2.0 LANGUAGES C CXX)

# Options ------------------------------------------------------------------- #
option(MODENA_BUILD_DOCS  "Build Doxygen API documentation"                 OFF)

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
