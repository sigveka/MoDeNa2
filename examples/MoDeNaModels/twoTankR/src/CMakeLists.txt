# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
# R simulation script — no compilation, install as executable.
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #

# install(PROGRAMS sets 755 permissions, making the script directly executable.
install(
    PROGRAMS "${CMAKE_CURRENT_SOURCE_DIR}/twoTanksMacroscopicProblemR.R"
    DESTINATION "${PKG_DIR}/bin"
    RENAME "twoTanksMacroscopicProblemR"
)
