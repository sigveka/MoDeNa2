# Library source for MoDeNa.
# This file is included via add_subdirectory(src) from the repository root
# CMakeLists.txt.  It can also be used as a standalone build root:
#   cd build && cmake ../src
# In standalone mode cmake_minimum_required and project() below take effect.
# When included as a subdirectory they are ignored by CMake (>= 3.14).

cmake_minimum_required(VERSION 3.22...3.28)
project(modena VERSION 2.0 LANGUAGES C CXX)

set(CMAKE_INCLUDE_CURRENT_DIR ON)
set(CMAKE_INCLUDE_CURRENT_DIR_IN_INTERFACE ON)

# Build Types --------------------------------------------------------------- #
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Debug CACHE STRING "Build type (Debug|Release|RelWithDebInfo|MinSizeRel)" FORCE)
endif()

add_custom_target(debug
  COMMAND ${CMAKE_COMMAND} -DCMAKE_BUILD_TYPE=Debug ${CMAKE_CURRENT_LIST_DIR}
  COMMAND ${CMAKE_COMMAND} --build ${CMAKE_BINARY_DIR} --target all
  COMMENT "Switch CMAKE_BUILD_TYPE to Debug"
  )

add_custom_target(release
  COMMAND ${CMAKE_COMMAND} -DCMAKE_BUILD_TYPE=Release ${CMAKE_CURRENT_LIST_DIR}
  COMMAND ${CMAKE_COMMAND} --build ${CMAKE_BINARY_DIR} --target all
  COMMENT "Switch CMAKE_BUILD_TYPE to Release"
  )

# Standardise Install Locations --------------------------------------------- #
set(INSTALL_ARCH_DIR    lib/static CACHE PATH "Archive install directory")
set(INSTALL_BIN_DIR     bin        CACHE PATH "Executables install directory")
set(INSTALL_INCLUDE_DIR include    CACHE PATH "Header files install directory")
set(INSTALL_LIB_DIR     lib        CACHE PATH "Library install directory")

foreach(p ARCH BIN CMAKE INCLUDE LIB)            # Make relative paths absolute
  set(var INSTALL_${p}_DIR)
  if(NOT IS_ABSOLUTE "${${var}}")
    set(${var} "${CMAKE_INSTALL_PREFIX}/${${var}}")
  endif()
endforeach()

# R library directory.  The R package installs under the project prefix like
# every other component rather than into R's per-user library -- see
# src/wrappers/r/CMakeLists.txt.  Defined here because both that file and the
# modena-env.sh generator in src/python/ need it, and PARENT_SCOPE from
# wrappers/r/ would only reach wrappers/.
set(R_LIB_DIR "${INSTALL_LIB_DIR}/R")

# Options -------------------------------------------------------------------- #

# Probe for a Fortran compiler before exposing the WITH_FORTRAN option so the
# default matches what the system can actually provide. ---------------------- #
include(CheckLanguage)
check_language(Fortran)
if(CMAKE_Fortran_COMPILER)
    enable_language(Fortran)
    set(_MODENA_FORTRAN_AVAILABLE TRUE)
else()
    set(_MODENA_FORTRAN_AVAILABLE FALSE)
endif()

# Wrapper options — Fortran defaults ON when a compiler was found. ----------- #
option(WITH_FORTRAN "Build the Fortran 2003 OOP wrapper (requires gfortran/ifort)"
    ${_MODENA_FORTRAN_AVAILABLE})
option(WITH_JULIA   "Install the Julia wrapper (requires Julia)"               OFF)
option(WITH_MATLAB  "Install the MATLAB/Octave wrapper"                        OFF)
option(WITH_R       "Install the R wrapper (requires R)"                       OFF)

# Probe for Julia (only when WITH_JULIA=ON) ---------------------------------- #
if(WITH_JULIA)
    find_program(_JULIA_EXECUTABLE julia)
    if(_JULIA_EXECUTABLE)
        execute_process(
            COMMAND "${_JULIA_EXECUTABLE}" --version
            OUTPUT_VARIABLE _julia_version_raw
            ERROR_QUIET
            OUTPUT_STRIP_TRAILING_WHITESPACE
        )
        # "julia version 1.x.y"
        string(REGEX MATCH "julia version ([0-9]+\\.[0-9]+\\.[0-9]+)"
               _julia_version_match "${_julia_version_raw}")
        set(_JULIA_VERSION "${CMAKE_MATCH_1}")
    endif()
endif()

# Probe for MATLAB/Octave (only when WITH_MATLAB=ON) ------------------------- #
if(WITH_MATLAB)
    find_program(_MATLAB_EXECUTABLE matlab)
    find_program(_OCTAVE_EXECUTABLE octave)
    if(_OCTAVE_EXECUTABLE)
        execute_process(
            COMMAND "${_OCTAVE_EXECUTABLE}" --version
            OUTPUT_VARIABLE _octave_version_raw
            ERROR_QUIET
            OUTPUT_STRIP_TRAILING_WHITESPACE
        )
        # First line: "GNU Octave, version x.y.z"
        string(REGEX MATCH "GNU Octave, version ([0-9]+\\.[0-9]+\\.[0-9]+)"
               _octave_version_match "${_octave_version_raw}")
        set(_OCTAVE_VERSION "${CMAKE_MATCH_1}")
    endif()
endif()

# Probe for R interpreter (only when WITH_R=ON) ------------------------------ #
if(WITH_R)
    find_program(_R_EXECUTABLE R)
    if(_R_EXECUTABLE)
        execute_process(
            COMMAND "${_R_EXECUTABLE}" --version
            OUTPUT_VARIABLE _r_version_raw
            ERROR_QUIET
            OUTPUT_STRIP_TRAILING_WHITESPACE
        )
        # First line: "R version 4.x.y (YYYY-MM-DD)"
        string(REGEX MATCH "R version ([0-9]+\\.[0-9]+\\.[0-9]+)"
               _r_version_match "${_r_version_raw}")
        set(_R_VERSION "${CMAKE_MATCH_1}")
    endif()
endif()

# Test option ---------------------------------------------------------------- #
# Tests are opt-in.  Enable with:
#   cmake -DMODENA_BUILD_TESTS=ON ..
#   cmake --build .
#   ctest --output-on-failure
option(MODENA_BUILD_TESTS
    "Build and register the MoDeNa test suite (Python + C)"                    OFF)

# RPATH handling ------------------------------------------------------------ #
# Installed shared libraries (libmodena, libfmodena, libfmodena_oop) all land
# in the same directory (${INSTALL_LIB_DIR}/modena).  Setting the install RPATH
# to $ORIGIN lets each library find its siblings in that directory without
# requiring LD_LIBRARY_PATH, and without hard-coding an absolute prefix.
#
# CMAKE_BUILD_WITH_INSTALL_RPATH=FALSE keeps the build tree using its own
# linker search paths; the install RPATH is written only at install time.
# CMAKE_INSTALL_RPATH_USE_LINK_PATH=TRUE additionally embeds the paths of any
# external libraries found at link time (e.g. Python, gfortran runtime).
set(CMAKE_INSTALL_RPATH "$ORIGIN")
set(CMAKE_BUILD_WITH_INSTALL_RPATH FALSE)
set(CMAKE_INSTALL_RPATH_USE_LINK_PATH TRUE)

# --------------------------------------------------------------------------- #
set(MODENA_SRC_DIR ${CMAKE_CURRENT_LIST_DIR}/src)
list(APPEND CMAKE_MODULE_PATH ${CMAKE_CURRENT_LIST_DIR}/cmake)

set(ConfigPackageLocation ${INSTALL_LIB_DIR}/cmake/modena)
install(DIRECTORY cmake/ DESTINATION ${ConfigPackageLocation})

# Build Source -------------------------------------------------------------- #
add_subdirectory(src)
add_subdirectory(wrappers)
add_subdirectory(python)
option(MODENA_BUILD_PORTAL "Build and install the web portal" OFF)
if(MODENA_BUILD_PORTAL)
    add_subdirectory(portal)
endif()

# Build Tests --------------------------------------------------------------- #
enable_testing()
if(MODENA_BUILD_TESTS)
    add_subdirectory("${CMAKE_CURRENT_LIST_DIR}/tests")
endif()

# --------------------------------------------------------------------------- #
# Build summary
# --------------------------------------------------------------------------- #

# Fortran status string
if(_MODENA_FORTRAN_AVAILABLE AND WITH_FORTRAN)
    set(_fortran_status
        "YES  (${CMAKE_Fortran_COMPILER_ID} ${CMAKE_Fortran_COMPILER_VERSION})")
elseif(WITH_FORTRAN AND NOT _MODENA_FORTRAN_AVAILABLE)
    set(_fortran_status "NO   *** requested but no Fortran compiler found ***")
elseif(_MODENA_FORTRAN_AVAILABLE AND NOT WITH_FORTRAN)
    set(_fortran_status "NO   (available — set -DWITH_FORTRAN=ON to enable)")
else()
    set(_fortran_status "NO   (no Fortran compiler found — install gfortran to enable)")
endif()

# Julia status string
if(NOT WITH_JULIA)
    set(_julia_status  "NO   (set -DWITH_JULIA=ON to enable)")
elseif(_JULIA_EXECUTABLE)
    set(_julia_status  "YES  (Julia ${_JULIA_VERSION})")
else()
    set(_julia_status  "NO   *** requested but Julia not found ***")
endif()

# MATLAB/Octave status string
if(NOT WITH_MATLAB)
    set(_matlab_status "NO   (set -DWITH_MATLAB=ON to enable)")
elseif(_MATLAB_EXECUTABLE)
    set(_matlab_status "YES  (matlab)")
elseif(_OCTAVE_EXECUTABLE)
    set(_matlab_status "YES  (Octave ${_OCTAVE_VERSION})")
else()
    set(_matlab_status "NO   *** requested but neither matlab nor octave found ***")
endif()

# R status string
if(NOT WITH_R)
    set(_r_status      "NO   (set -DWITH_R=ON to enable)")
elseif(_R_EXECUTABLE)
    set(_r_status      "YES  (R ${_R_VERSION})")
else()
    set(_r_status      "NO   *** requested but R not found ***")
endif()

# Portal status string
if(MODENA_BUILD_PORTAL)
    set(_portal_status "YES")
else()
    set(_portal_status "NO   (set -DMODENA_BUILD_PORTAL=ON to enable)")
endif()

# Tests status string
if(MODENA_BUILD_TESTS)
    set(_tests_status  "YES")
else()
    set(_tests_status  "NO   (set -DMODENA_BUILD_TESTS=ON to enable)")
endif()

# Docs status string (only relevant when built from repo root)
if(MODENA_BUILD_DOCS)
    set(_docs_status   "YES")
elseif(DEFINED MODENA_BUILD_DOCS)
    set(_docs_status   "NO   (set -DMODENA_BUILD_DOCS=ON to enable)")
else()
    set(_docs_status   "N/A  (configure from repository root to enable)")
endif()

message("")
message("*************************************************")
message("  MoDeNa ${PROJECT_VERSION}  —  build summary")
message("  Build dir : ${CMAKE_BINARY_DIR}")
message("  Install   : ${CMAKE_INSTALL_PREFIX}")
message("")
message("  Compiler")
message("    C   : ${CMAKE_C_COMPILER_ID} ${CMAKE_C_COMPILER_VERSION}")
message("          (${CMAKE_C_COMPILER})")
message("    C++ : ${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}")
message("          (${CMAKE_CXX_COMPILER})")
message("    Build type : ${CMAKE_BUILD_TYPE}")
message("")
message("  Wrappers")
message("    C++ (header-only)  : YES")
message("    Fortran            : ${_fortran_status}")
message("    Julia              : ${_julia_status}")
message("    MATLAB/Octave      : ${_matlab_status}")
message("    R                  : ${_r_status}")
message("")
message("  Tests                : ${_tests_status}")
message("  Portal               : ${_portal_status}")
message("  Docs                 : ${_docs_status}")
message("*************************************************")
message("")
