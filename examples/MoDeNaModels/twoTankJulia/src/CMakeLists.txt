# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
# Julia simulation script — no compilation, install as executable.
# Only installed when Julia is present and Modena.jl is registered
# (JULIA_READY set by the parent CMakeLists.txt).
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #

# install(PROGRAMS sets 755 permissions, making the script directly executable.
install(
  PROGRAMS "${CMAKE_CURRENT_SOURCE_DIR}/twoTanksMacroscopicProblemJulia.jl"
  DESTINATION "${PKG_DIR}/bin"
  RENAME "twoTanksMacroscopicProblemJulia"
)


