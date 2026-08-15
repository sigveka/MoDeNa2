# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
#
# @brief    Top-level CMakeLists.txt for twoTank.
#           Builds the C++ solver and installs Python files + binary.
#
#             *
#             |-- CMakeLists.txt
#             |-- pyproject.toml        ← scikit-build-core entry point
#             |-- python
#             |   |-- __init__.py
#             |   `-- twoTank.py
#             `-- src
#                 |-- CMakeLists.txt
#                 `-- twoTankMacroscopicModel.C
#
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
cmake_minimum_required(VERSION 3.22...3.28)

set(CMAKE_DISABLE_SOURCE_CHANGES ON)
set(CMAKE_DISABLE_IN_SOURCE_BUILD ON)

project(twoTank VERSION 1.0 LANGUAGES CXX)

set(CMAKE_INCLUDE_CURRENT_DIR ON)
set(CMAKE_INCLUDE_CURRENT_DIR_IN_INTERFACE ON)

# ---------------------------------------------------------------------- #
# Install destination                                                      #
# scikit-build-core sets SKBUILD_PLATLIB_DIR when building a wheel.       #
# Fall back to a prefix-relative path for standalone cmake use.           #
# ---------------------------------------------------------------------- #
find_package(Python3 COMPONENTS Interpreter Development REQUIRED)

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
message("---- Build Directory:   ${CMAKE_BINARY_DIR}")
message("---- Install Prefix:    ${CMAKE_INSTALL_PREFIX}")
message("---- Package Dir:       ${PKG_DIR}")
message("********************************************************************")

# Install Python package files ---------------------------------------------- #
file(GLOB _py_files "${CMAKE_CURRENT_SOURCE_DIR}/python/*.py")
install(FILES ${_py_files} DESTINATION "${PKG_DIR}")

# Build C++ solver ---------------------------------------------------------- #
add_subdirectory(src)

