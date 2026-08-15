# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
#
# @brief    Top-level CMakeLists.txt for idealGas (pure Python).
#           No compiled binary — only installs Python files and config.toml.
#
#             *
#             |-- CMakeLists.txt
#             |-- pyproject.toml   ← scikit-build-core entry point
#             |-- __init__.py
#             |-- idealGas.py
#             `-- config.toml
#
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
cmake_minimum_required(VERSION 3.22...3.28)

set(CMAKE_DISABLE_SOURCE_CHANGES ON)
set(CMAKE_DISABLE_IN_SOURCE_BUILD ON)

project(idealGas VERSION 1.0 LANGUAGES NONE)

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

# Install Python package files and config ----------------------------------- #
file(GLOB _py_files "${CMAKE_CURRENT_SOURCE_DIR}/*.py")
install(FILES ${_py_files} DESTINATION "${PKG_DIR}")
install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/config.toml" DESTINATION "${PKG_DIR}")
