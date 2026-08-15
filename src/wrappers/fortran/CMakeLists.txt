# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
# MODENA::fmodena_oop — Fortran 2003 OOP wrapper around the MoDeNa C library.
#
# Requires a Fortran compiler with Fortran 2003 support (gfortran 4.9+,
# ifort 12+).
#
# Users link against this single target:
#   target_link_libraries(myapp PRIVATE MODENA::fmodena_oop)
#
# and access the wrapper module:
#   use fmodena_oop
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #

add_library(fmodena_oop SHARED fmodena_oop.f90)

# Expose the generated .mod file to dependents at build time.
set_target_properties(fmodena_oop PROPERTIES
    Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
)
target_include_directories(fmodena_oop PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}>
    $<INSTALL_INTERFACE:include/modena>
)

# Pull in the raw C bindings (fmodena) and the C library (modena) both
# transitively, so users only need to list MODENA::fmodena_oop.
target_link_libraries(fmodena_oop PUBLIC fmodena modena)

add_library(MODENA::fmodena_oop ALIAS fmodena_oop)

install(
    TARGETS fmodena_oop
    EXPORT  MODENATargets
    LIBRARY DESTINATION ${INSTALL_LIB_DIR}/modena
    ARCHIVE DESTINATION ${INSTALL_LIB_DIR}/static
)

install(
    FILES ${CMAKE_CURRENT_BINARY_DIR}/fmodena_oop.mod
    DESTINATION ${INSTALL_INCLUDE_DIR}/modena
)
