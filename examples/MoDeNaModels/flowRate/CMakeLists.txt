# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
#
# @brief    Top-level CMakeLists.txt for flowRate.
#           Builds the C exact solver and installs Python files + binary.
#
#             *
#             |-- CMakeLists.txt
#             |-- pyproject.toml        ← scikit-build-core entry point
#             |-- python
#             |   |-- __init__.py
#             |   `-- flowRate.py
#             `-- src
#                 |-- CMakeLists.txt
#                 `-- flowRateExact.C
#
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
cmake_minimum_required(VERSION 3.22...3.28)

set(CMAKE_DISABLE_SOURCE_CHANGES ON)
set(CMAKE_DISABLE_IN_SOURCE_BUILD ON)

project(flowRate VERSION 1.0 LANGUAGES C)

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

# Install Python package files ---------------------------------------------- #
file(GLOB _py_files "${CMAKE_CURRENT_SOURCE_DIR}/python/*.py")
install(FILES ${_py_files} DESTINATION "${PKG_DIR}")

# Build C solver ------------------------------------------------------------ #
add_subdirectory(src)

