# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
# Install the .m solver and the generated shell launcher.
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #

# Generate the launcher shell script with the correct MATLAB_PKG_DIR embedded.
configure_file(
  "${CMAKE_CURRENT_SOURCE_DIR}/launcher.sh.in"
  "${CMAKE_CURRENT_BINARY_DIR}/twoTanksMacroscopicProblemMatlab"
  @ONLY
)

# Install the .m solver alongside the launcher so SCRIPT_DIR contains both.
install(
  FILES "${CMAKE_CURRENT_SOURCE_DIR}/twoTanksMacroscopicProblemMatlab.m"
  DESTINATION "${PKG_DIR}/bin"
)

# install(PROGRAMS sets 755 permissions, making the launcher directly executable.
install(
  PROGRAMS "${CMAKE_CURRENT_BINARY_DIR}/twoTanksMacroscopicProblemMatlab"
  DESTINATION "${PKG_DIR}/bin"
)
