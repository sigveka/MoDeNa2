# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
#
# @brief    Top-level CMakeLists.txt for twoTanksJulia example
# @details
#           Mirrors twoTankCxx but the macroscopic solver is a Julia script
#           rather than a compiled C++ executable.
#
#             *
#             |-- CMakeLists.txt
#             |-- python
#             |   |-- CMakeLists.txt
#             |   |-- twoTankJulia.py
#             |   `-- __init__.py
#             `-- src
#                 |-- CMakeLists.txt
#                 `-- twoTanksMacroscopicProblemJulia.jl
#
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
cmake_minimum_required(VERSION 3.22...3.28)

# Outlaw "in-source" build -------------------------------------------------- #
set(CMAKE_DISABLE_SOURCE_CHANGES ON)
set(CMAKE_DISABLE_IN_SOURCE_BUILD ON)

# Start Project ------------------------------------------------------------- #
project(twoTankJulia VERSION 1.0 LANGUAGES NONE)

# Automatically include all project directories containing CMakeLists.txt --- #
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


# Check Julia prerequisites ------------------------------------------------- #
find_program(Julia_EXECUTABLE julia)

if(NOT Julia_EXECUTABLE)
  message(FATAL_ERROR
    "Julia executable not found.\n"
    "The twoTankJulia example requires Julia.\n"
    "Install Julia from https://julialang.org/downloads/ and re-configure."
  )
endif()

message(STATUS "Julia found: ${Julia_EXECUTABLE}")

# Check that Modena.jl is registered by reading the global Project.toml
# directly — avoids triggering precompilation which can fail for unrelated
# reasons and gives a reliable yes/no answer.
execute_process(
  COMMAND "${Julia_EXECUTABLE}" --startup-file=no -e
    "print(joinpath(first(Base.DEPOT_PATH), \"environments\",
           \"v$(VERSION.major).$(VERSION.minor)\", \"Project.toml\"))"
  OUTPUT_VARIABLE _julia_project_toml
  OUTPUT_STRIP_TRAILING_WHITESPACE
)

set(_modena_registered FALSE)
if(EXISTS "${_julia_project_toml}")
  file(READ "${_julia_project_toml}" _project_content)
  if("${_project_content}" MATCHES "Modena")
    set(_modena_registered TRUE)
  endif()
endif()

if(NOT _modena_registered)
  message(FATAL_ERROR
    "Modena.jl is not registered in Julia's package manager.\n"
    "Install the modena package with -DWITH_JULIA=ON and re-run cmake --install,\n"
    "or register manually: julia --startup-file=no <modena-build>/wrappers/julia/register_modena.jl"
  )
endif()

message(STATUS "Modena.jl is registered — Julia solver will be installed")

# Install Python package files ---------------------------------------------- #
file(GLOB _py_files "${CMAKE_CURRENT_SOURCE_DIR}/python/*.py")
install(FILES ${_py_files} DESTINATION "${PKG_DIR}")

# Install Julia solver ------------------------------------------------------ #
add_subdirectory(src)
