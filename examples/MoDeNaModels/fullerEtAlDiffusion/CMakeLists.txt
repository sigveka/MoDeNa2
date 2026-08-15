# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
#
# @brief    Generic top-level CMakeLists.txt for Python projects
# @author   Sigve Karolius
# @date     2017-02-14 (started)
# @details
#           The idea is to structure Python development projects.
#
#             *
#             |-- CMakeLists.txt
#             |-- python
#             |   |-- CMakeLists.txt
#             |   |-- setup.py.in
#             |   `-- __init__.py
#             |-- README.txt
#             `-- src
#                 |-- CMakeLists.txt
#                 `-- twoTankMacroscopicModel.C
#
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
cmake_minimum_required(VERSION 3.22...3.28)

# Outlaw "in-source" build -------------------------------------------------- #
set(CMAKE_DISABLE_SOURCE_CHANGES ON)
set(CMAKE_DISABLE_IN_SOURCE_BUILD ON)

# Start Project ------------------------------------------------------------- #
project(fullerEtAlDiffusion VERSION 1.0 LANGUAGES CXX)

# Automatically include all project directories containing CMakeLists.txt --- #
set(CMAKE_INCLUDE_CURRENT_DIR ON)
set(CMAKE_INCLUDE_CURRENT_DIR_IN_INTERFACE ON)

# Set Install Path According to Python's "site-packages" Directory ---------- #
find_package(Python3 COMPONENTS Interpreter Development REQUIRED)

execute_process(
  COMMAND "${Python3_EXECUTABLE}" -c
    "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
  OUTPUT_VARIABLE Python3_VERSION_MAJMIN
  OUTPUT_STRIP_TRAILING_WHITESPACE
)
set(PYTHON_SITE "${CMAKE_INSTALL_PREFIX}/lib/python${Python3_VERSION_MAJMIN}/site-packages")

set(INSTALL_LIB_DIR     lib     CACHE PATH "Library install directories")
set(INSTALL_BIN_DIR     bin     CACHE PATH "Executables install directories")
set(INSTALL_INCLUDE_DIR include CACHE PATH "Header files install directory")

foreach(p LIB BIN INCLUDE CMAKE)
  # set(${var} "${PYTHON_SITE}/site-packages/${CMAKE_PROJECT_NAME}/${${var}}")
  set(var INSTALL_${p}_DIR)
  if(NOT IS_ABSOLUTE "${${var}}")
    set(${var} "${PYTHON_SITE}/${CMAKE_PROJECT_NAME}/${${var}}")
  endif()
endforeach()
# set(${var} "${CMAKE_INSTALL_PREFIX}/${${var}}")


# -------------------------------------------- Display Some Build Information #
message("********************************************************************")
message("-- Info about project: '${PROJECT_NAME}'")
message("---- System Name:       ${CMAKE_SYSTEM}")
message("---- Project Version:   ${PROJECT_VERSION}")
message("---- Project Directory: ${CMAKE_SOURCE_DIR}")
message("---- Source Directory:  ${PROJECT_SOURCE_DIR}")
message("---- Build Directory:   ${CMAKE_BINARY_DIR}")
message("---- Build Type:        ${CMAKE_BUILD_TYPE}")
message("---- Install Prefix:    ${CMAKE_INSTALL_PREFIX}")
message("********************************************************************")


# Build sub-directories ----------------------------------------------------- #
add_subdirectory(python)
add_subdirectory(src)

