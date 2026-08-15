# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
#
# @brief    Top-level CMakeLists.txt for twoTankMatlab example
# @details
#           Mirrors twoTankCxx/twoTankJulia but the macroscopic solver is a
#           MATLAB/Octave script launched via a generated shell script.
#
#             *
#             |-- CMakeLists.txt
#             |-- python
#             |   |-- CMakeLists.txt
#             |   |-- twoTankMatlab.py
#             |   `-- __init__.py
#             `-- src
#                 |-- CMakeLists.txt
#                 |-- twoTanksMacroscopicProblemMatlab.m
#                 `-- launcher.sh.in
#
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
cmake_minimum_required(VERSION 3.22...3.28)

set(CMAKE_DISABLE_SOURCE_CHANGES ON)
set(CMAKE_DISABLE_IN_SOURCE_BUILD ON)

project(twoTankMatlab VERSION 1.0 LANGUAGES NONE)

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
message("---- Build Directory:   ${CMAKE_BINARY_DIR}")
message("---- Install Prefix:    ${CMAKE_INSTALL_PREFIX}")
message("---- Package Dir:       ${PKG_DIR}")
message("********************************************************************")

# Check MATLAB/Octave prerequisites ---------------------------------------- #

# Locate the Modena MATLAB/Octave wrapper.  We search common install prefixes
# directly (no Python import, which may not be on PATH at cmake configure time).
# The user can also pass -DMATLAB_PKG_DIR=<path> to override.
find_path(MATLAB_PKG_DIR
  NAMES Modena.m
  HINTS
    "$ENV{HOME}/share/modena/matlab"
    "${CMAKE_INSTALL_PREFIX}/share/modena/matlab"
    "/usr/local/share/modena/matlab"
    "/usr/share/modena/matlab"
  DOC "Directory containing Modena.m and modena_gateway MEX/OCT"
)

if(NOT MATLAB_PKG_DIR OR NOT EXISTS "${MATLAB_PKG_DIR}/Modena.m")
  message(FATAL_ERROR
    "Modena MATLAB/Octave wrapper (Modena.m) not found.\n"
    "Build and install modena with -DWITH_MATLAB=ON first:\n"
    "  cmake -DWITH_MATLAB=ON <modena-source>\n"
    "  cmake --install <modena-build>\n"
    "Or specify the wrapper directory explicitly:\n"
    "  cmake -DMATLAB_PKG_DIR=<path/to/share/modena/matlab> ..."
  )
endif()

# Check that modena_gateway MEX is present (Octave .mex or MATLAB .mexa64).
file(GLOB _mex_files "${MATLAB_PKG_DIR}/modena_gateway.*")
if(NOT _mex_files)
  message(FATAL_ERROR
    "No modena_gateway MEX/OCT file found in '${MATLAB_PKG_DIR}'.\n"
    "Ensure the modena wrapper was compiled (requires octave or MATLAB mex)."
  )
endif()

# Check that at least one runtime is available.
find_program(OCTAVE_EXECUTABLE octave)
find_program(MATLAB_EXECUTABLE matlab)
if(NOT OCTAVE_EXECUTABLE AND NOT MATLAB_EXECUTABLE)
  message(FATAL_ERROR
    "Neither Octave nor MATLAB found in PATH.\n"
    "Install one of them before building this example.\n"
    "  Ubuntu/Debian: sudo apt install octave"
  )
endif()

if(OCTAVE_EXECUTABLE)
  message(STATUS "Octave found: ${OCTAVE_EXECUTABLE} — will use as solver runtime")
else()
  message(STATUS "MATLAB found: ${MATLAB_EXECUTABLE} — will use as solver runtime")
endif()

message(STATUS "Modena MATLAB/Octave wrapper found in ${MATLAB_PKG_DIR}")

# Install Python package files ---------------------------------------------- #
file(GLOB _py_files "${CMAKE_CURRENT_SOURCE_DIR}/python/*.py")
install(FILES ${_py_files} DESTINATION "${PKG_DIR}")

# Install MATLAB/Octave solver ---------------------------------------------- #
add_subdirectory(src)
