# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
#
# @brief    Top-level CMakeLists.txt for twoTankPython.
#           Installs Python package files and the Python simulation script.
#
#             *
#             |-- CMakeLists.txt
#             |-- pyproject.toml        ← scikit-build-core entry point
#             `-- python
#                 |-- __init__.py
#                 |-- twoTankPython.py
#                 `-- bin
#                     `-- twoTanksSim.py
#
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
cmake_minimum_required(VERSION 3.22...3.28)

set(CMAKE_DISABLE_SOURCE_CHANGES ON)
set(CMAKE_DISABLE_IN_SOURCE_BUILD ON)

project(twoTankPython VERSION 1.0 LANGUAGES NONE)

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
message("---- Project Directory: ${CMAKE_SOURCE_DIR}")
message("---- Install Prefix:    ${CMAKE_INSTALL_PREFIX}")
message("---- Package Dir:       ${PKG_DIR}")
message("********************************************************************")

# Install Python package files ---------------------------------------------- #
file(GLOB _py_files "${CMAKE_CURRENT_SOURCE_DIR}/python/*.py")
install(FILES ${_py_files} DESTINATION "${PKG_DIR}")

# Install the Python simulation script into bin/ ---------------------------- #
install(
  PROGRAMS "${CMAKE_CURRENT_SOURCE_DIR}/python/bin/twoTanksSim.py"
  DESTINATION "${PKG_DIR}/bin"
)
