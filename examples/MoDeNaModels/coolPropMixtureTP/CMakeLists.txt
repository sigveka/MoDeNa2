# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
#
# @brief    Top-level CMakeLists.txt for the coolPropMixtureTP surrogate model.
# @details
#           Trains a 2nd-order polynomial surrogate for the mass density of a
#           N2/O2/Ar mixture as a function of T, p, x_N2, x_O2.
#
#           Demonstrates ExpandedCASTROSampling: T and p sampled via standard
#           LHS; composition (x_N2, x_O2) sampled via the CASTRO constrained
#           algorithm; joint distance-based selection in the full input space.
#
#             *
#             |-- CMakeLists.txt
#             `-- python
#                 |-- CMakeLists.txt
#                 |-- coolPropMixtureTP.py
#                 |-- setup.py.in
#                 `-- __init__.py
#
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
cmake_minimum_required(VERSION 3.22...3.28)

set(CMAKE_DISABLE_SOURCE_CHANGES ON)
set(CMAKE_DISABLE_IN_SOURCE_BUILD ON)

project(coolPropMixtureTP VERSION 1.0 LANGUAGES NONE)

set(CMAKE_INCLUDE_CURRENT_DIR ON)
set(CMAKE_INCLUDE_CURRENT_DIR_IN_INTERFACE ON)

# Set install path relative to Python's site-packages directory -------------- #
find_package(Python3 COMPONENTS Interpreter REQUIRED)

execute_process(
    COMMAND "${Python3_EXECUTABLE}" -c
        "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    OUTPUT_VARIABLE Python3_VERSION_MAJMIN
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
set(PYTHON_SITE
    "${CMAKE_INSTALL_PREFIX}/lib/python${Python3_VERSION_MAJMIN}/site-packages")

set(INSTALL_LIB_DIR     lib     CACHE PATH "Library install directory")
set(INSTALL_BIN_DIR     bin     CACHE PATH "Executables install directory")
set(INSTALL_INCLUDE_DIR include CACHE PATH "Header files install directory")

foreach(p LIB BIN INCLUDE CMAKE)
    set(var INSTALL_${p}_DIR)
    if(NOT IS_ABSOLUTE "${${var}}")
        set(${var} "${PYTHON_SITE}/${CMAKE_PROJECT_NAME}/${${var}}")
    endif()
endforeach()

message("********************************************************************")
message("-- Info about project: '${PROJECT_NAME}'")
message("---- System Name:       ${CMAKE_SYSTEM}")
message("---- Project Version:   ${PROJECT_VERSION}")
message("---- Project Directory: ${CMAKE_SOURCE_DIR}")
message("---- Install Prefix:    ${CMAKE_INSTALL_PREFIX}")
message("********************************************************************")

# Check CoolProp prerequisite ------------------------------------------------ #
execute_process(
    COMMAND "${Python3_EXECUTABLE}" -c "import CoolProp"
    RESULT_VARIABLE _coolprop_result
    OUTPUT_QUIET
    ERROR_QUIET
)

if(NOT _coolprop_result EQUAL 0)
    message(FATAL_ERROR
        "CoolProp Python package not found.\n"
        "Install it with: pip install CoolProp\n"
        "Then re-configure."
    )
endif()

message(STATUS "CoolProp found — mixture density surrogate will be installed")

# Build sub-directories ------------------------------------------------------ #
add_subdirectory(python)
