# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
# MATLAB/Octave wrapper — MEX extension + pure M-code class.
#
# The Modena.m handle class delegates all work to modena_gateway (a MEX/OCT
# binary that loads libmodena.so at runtime via dlopen).  Runtime loading lets
# us open libpython with RTLD_GLOBAL *before* libmodena, which is required
# because libmodena.so uses __attribute__((constructor)) to auto-initialise an
# embedded Python interpreter on dlopen.
#
# Build targets
#   modena_gateway_matlab  — compiled with MATLAB's mex compiler (.mexa64 etc.)
#   modena_gateway_oct     — compiled with Octave's mkoctfile (.mex on Linux)
#
# At least one of MATLAB or Octave must be available; both are compiled when
# found.
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #

# Install destination (expose to parent and child CMakeLists via cache)
set(MATLAB_PKG_DIR "${CMAKE_INSTALL_PREFIX}/share/modena/matlab"
    CACHE PATH "Install directory for the MATLAB/Octave wrapper files")

# Always install the pure M-code class — no compilation required.
install(
  FILES "${CMAKE_CURRENT_SOURCE_DIR}/m/Modena.m"
  DESTINATION "${MATLAB_PKG_DIR}"
)

# ── MATLAB ───────────────────────────────────────────────────────────────── #
find_package(Matlab QUIET COMPONENTS MEX_COMPILER)
if(Matlab_FOUND)
  message(STATUS "MATLAB found: ${Matlab_ROOT_DIR} — compiling MEX gateway")
  matlab_add_mex(
    NAME modena_gateway_matlab
    SRC  "${CMAKE_CURRENT_SOURCE_DIR}/mex/modena_gateway.c"
  )
  target_link_libraries(modena_gateway_matlab PRIVATE ${CMAKE_DL_LIBS})
  set_target_properties(modena_gateway_matlab PROPERTIES
    OUTPUT_NAME "modena_gateway"
  )
  install(TARGETS modena_gateway_matlab DESTINATION "${MATLAB_PKG_DIR}")
  set(_MODENA_MATLAB_FOUND TRUE)
endif()

# ── Octave ───────────────────────────────────────────────────────────────── #
find_program(MKOCTFILE mkoctfile)
if(MKOCTFILE)
  message(STATUS "Octave mkoctfile found: ${MKOCTFILE} — compiling OCT gateway")
  set(_OCT_MEX "${CMAKE_CURRENT_BINARY_DIR}/modena_gateway.mex")
  add_custom_command(
    OUTPUT  "${_OCT_MEX}"
    COMMAND "${MKOCTFILE}" --mex
            -o "${_OCT_MEX}"
            "${CMAKE_CURRENT_SOURCE_DIR}/mex/modena_gateway.c"
    DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/mex/modena_gateway.c"
    COMMENT "Compiling modena_gateway MEX for Octave"
  )
  add_custom_target(modena_gateway_oct ALL DEPENDS "${_OCT_MEX}")
  install(FILES "${_OCT_MEX}" DESTINATION "${MATLAB_PKG_DIR}")
  set(_MODENA_OCTAVE_FOUND TRUE)
endif()

if(NOT _MODENA_MATLAB_FOUND AND NOT _MODENA_OCTAVE_FOUND)
  message(FATAL_ERROR
    "Neither MATLAB (mex compiler) nor Octave (mkoctfile) found.\n"
    "Install one of them and re-configure, or disable this wrapper with "
    "-DWITH_MATLAB=OFF.\n"
    "  Ubuntu/Debian: sudo apt install octave octave-dev"
  )
endif()

# Make MATLAB_PKG_DIR visible in the parent scope so the twoTankMatlab
# example can embed it in the generated launcher script.
set(MATLAB_PKG_DIR "${MATLAB_PKG_DIR}" PARENT_SCOPE)
