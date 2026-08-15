# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
# NOTE: The Doxygen 'doc' target is registered in the repository root
# CMakeLists.txt (enabled with -DMODENA_BUILD_DOCS=ON).  This file is kept
# only as a reference for the Doxyfile variables below.
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #

# find_package(Doxygen)
# Variables:
# DOXYGEN_SKIP_DOT       = If true this module will skip trying to find Dot
#                          (an optional component often used by Doxygen)
#
# This modules defines the following variables:
#
# DOXYGEN_EXECUTABLE     = The path to the doxygen command.
# DOXYGEN_FOUND          = Was Doxygen found or not?
# DOXYGEN_VERSION        = The version reported by doxygen --version
#
# DOXYGEN_DOT_EXECUTABLE = The path to the dot program used by doxygen.
# DOXYGEN_DOT_FOUND      = Was Dot found or not?
# DOXYGEN_DOT_PATH       = The path to dot not including the executable

if(DOXYGEN_FOUND)
  configure_file(${CMAKE_CURRENT_SOURCE_DIR}/Doxyfile.in ${CMAKE_CURRENT_BINARY_DIR}/Doxyfile @ONLY)
  add_custom_target(doc
    ${DOXYGEN_EXECUTABLE} ${CMAKE_CURRENT_BINARY_DIR}/Doxyfile
    WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
    COMMENT "Generating API documentation with Doxygen" VERBATIM
    )
endif(DOXYGEN_FOUND)


