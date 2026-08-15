# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
#
# @brief    Top-level CMakeLists.txt for twoTanksR example
# @details
#           Mirrors twoTankJulia but the macroscopic solver is an R script
#           rather than a Julia script.
#
#             *
#             |-- CMakeLists.txt
#             |-- python
#             |   |-- CMakeLists.txt
#             |   |-- twoTanksR.py
#             |   `-- __init__.py
#             `-- src
#                 |-- CMakeLists.txt
#                 `-- twoTanksMacroscopicProblemR.R
#
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
cmake_minimum_required(VERSION 3.22...3.28)

set(CMAKE_DISABLE_SOURCE_CHANGES ON)
set(CMAKE_DISABLE_IN_SOURCE_BUILD ON)

project(twoTankR VERSION 1.0 LANGUAGES NONE)

set(CMAKE_INCLUDE_CURRENT_DIR ON)
set(CMAKE_INCLUDE_CURRENT_DIR_IN_INTERFACE ON)

# ---------------------------------------------------------------------- #
# Install destination                                                      #
# scikit-build-core sets SKBUILD_PLATLIB_DIR when building a wheel.       #
# Fall back to a prefix-relative path for standalone cmake use.           #
# ---------------------------------------------------------------------- #
find_package(Python3 COMPONENTS Interpreter REQUIRED)

if(DEFINED SKBUILD_PLATLIB_DIR)
  set(PKG_DIR "${SKBUILD_PLATLIB_DIR}/${CMAKE_PROJECT_NAME}")
else()
  execute_process(
    COMMAND "${Python3_EXECUTABLE}" -c
      "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    OUTPUT_VARIABLE Python3_VERSION_MAJMIN
    OUTPUT_STRIP_TRAILING_WHITESPACE
  )
  set(PKG_DIR
    "${CMAKE_INSTALL_PREFIX}/lib/python${Python3_VERSION_MAJMIN}/site-packages/${CMAKE_PROJECT_NAME}")
endif()

message("********************************************************************")
message("-- Info about project: '${PROJECT_NAME}'")
message("---- System Name:       ${CMAKE_SYSTEM}")
message("---- Project Version:   ${PROJECT_VERSION}")
message("---- Project Directory: ${CMAKE_SOURCE_DIR}")
message("---- Install Prefix:    ${CMAKE_INSTALL_PREFIX}")
message("---- Package Dir:       ${PKG_DIR}")
message("********************************************************************")

# Check R prerequisites ------------------------------------------------------ #
find_program(R_EXECUTABLE R)

if(NOT R_EXECUTABLE)
    message(FATAL_ERROR
        "R executable not found.\n"
        "The twoTankR example requires R.\n"
        "Install R from https://www.r-project.org/ and re-configure."
    )
endif()

message(STATUS "R found: ${R_EXECUTABLE}")

# Check that the modena R package is installed -------------------------------- #
execute_process(
    COMMAND "${R_EXECUTABLE}" --quiet --no-save -e "library(modena)"
    RESULT_VARIABLE _r_modena_result
    OUTPUT_QUIET
    ERROR_QUIET
)

if(NOT _r_modena_result EQUAL 0)
    message(FATAL_ERROR
        "The modena R package is not installed.\n"
        "Install the modena package with -DWITH_R=ON and re-run cmake --install,\n"
        "or install manually: R CMD INSTALL <prefix>/share/modena/R/modena"
    )
endif()

message(STATUS "modena R package is installed — R solver will be installed")

# Install Python package files ---------------------------------------------- #
file(GLOB _py_files "${CMAKE_CURRENT_SOURCE_DIR}/python/*.py")
install(FILES ${_py_files} DESTINATION "${PKG_DIR}")

# Install R solver ---------------------------------------------------------- #
add_subdirectory(src)
