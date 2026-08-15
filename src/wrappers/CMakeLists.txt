# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
# Language wrapper sub-directories.
#
# Each sub-directory defines an INTERFACE (header-only) or compiled target
# that layers on top of the core MODENA::modena C library:
#
#   MODENA::modena_cpp   — header-only C++17 RAII wrapper    (always built)
#   MODENA::fmodena_oop  — compiled Fortran 2003 OOP module  (WITH_FORTRAN)
#   Modena.jl            — pure Julia package                (WITH_JULIA)
#   modena_gateway       — MEX/OCT extension                 (WITH_MATLAB)
#   modena (R package)   — R + C extension                   (WITH_R)
#
# Wrapper options and Fortran availability are set in the parent CMakeLists.txt.
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #

# C++ wrapper is header-only — no compiler requirements. -------------------- #
add_subdirectory(cpp)

# Fortran wrapper ------------------------------------------------------------ #
if(WITH_FORTRAN)
    if(_MODENA_FORTRAN_AVAILABLE)
        add_subdirectory(fortran)
    else()
        message(WARNING
            "WITH_FORTRAN=ON but no Fortran compiler was found. "
            "Install gfortran (>= 4.9) or ifort and re-run cmake. "
            "The rest of the library will be built without the Fortran wrapper.")
    endif()
endif()

# Julia wrapper -------------------------------------------------------------- #
if(WITH_JULIA)
    add_subdirectory(julia)
endif()

# MATLAB / Octave wrapper ---------------------------------------------------- #
if(WITH_MATLAB)
    add_subdirectory(matlab)
endif()

# R wrapper ------------------------------------------------------------------ #
if(WITH_R)
    add_subdirectory(r)
endif()
