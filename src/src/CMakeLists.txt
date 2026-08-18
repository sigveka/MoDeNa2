# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
#
#
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
# Build C library

# Locate Libraries ---------------------------------------------------------- #
include(CheckCInline)
check_c_inline(C_INLINE)

find_package(LTDL REQUIRED)

find_package(Python3 COMPONENTS Development REQUIRED)
include_directories(${Python3_INCLUDE_DIRS})


# Obtain Headers and Sources ------------------------------------------------ #

# Generated before the glob so it is picked up as a public header.
modena_status_block(MODENA_STATUS_BLOCK c)
configure_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/modena_status.h.in"
    "${CMAKE_CURRENT_BINARY_DIR}/modena_status.h"
    @ONLY
)
modena_status_message_table(MODENA_STATUS_MESSAGE_TABLE)
configure_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/modena_status_messages.h.in"
    "${CMAKE_CURRENT_BINARY_DIR}/modena_status_messages.h"
    @ONLY
)

file(GLOB HEADERS ${CMAKE_CURRENT_SOURCE_DIR}/*.h)
file(GLOB SOURCES ${CMAKE_CURRENT_SOURCE_DIR}/*.c)
# Only the enum is public.  modena_status_messages.h is include-as-data for
# global.c and is deliberately not self-contained, so it is not installed.
list(APPEND HEADERS "${CMAKE_CURRENT_BINARY_DIR}/modena_status.h")
include_directories(${CMAKE_CURRENT_BINARY_DIR})

# Build Libraries ----------------------------------------------------------- #

# --> C
add_library(modena SHARED ${SOURCES})
target_link_libraries(modena ${LTDL_LIBRARIES} ${Python3_LIBRARIES})


target_include_directories(modena INTERFACE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include/modena>
  $<INSTALL_INTERFACE:include/modena>
)

# global.h includes the generated modena_status.h, so anything that includes
# modena.h -- the wrappers, the tests, the examples -- needs the directory it
# is generated into.  PUBLIC, not INTERFACE: libmodena's own sources need it too.
target_include_directories(modena PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}>
  $<INSTALL_INTERFACE:include/modena>
)


# set_property(TARGET modena APPEND PROPERTY INTERFACE_INCLUDE_DIRECTORIES
#   $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
#   $<INSTALL_INTERFACE:${CMAKE_INSTALL_PREFIX}/include>
# )
#include(GenerateExportHeader)
#generate_export_header(modena)
set_property(TARGET modena PROPERTY VERSION ${PROJECT_VERSION})
set_property(TARGET modena PROPERTY SOVERSION ${PROJECT_VERSION_MAJOR})
set_property(TARGET modena PROPERTY INTERFACE_MODENA_MAJOR_VERSION ${PROJECT_VERSION_MAJOR})
set_property(
  TARGET modena APPEND PROPERTY
  COMPATIBLE_INTERFACE_STRING MODENA_MAJOR_VERSION
)
set_target_properties(modena PROPERTIES PUBLIC_HEADER "${HEADERS}")

# --> FORTRAN
add_library(fmodena SHARED fmodena.f90)
target_link_libraries(fmodena ${LTDL_LIBRARIES} ${Python3_LIBRARIES})

# Build executables
add_executable(twoTanksFullProblem twoTanksFullProblem.C)

# Build configuration files ------------------------------------------------- #
configure_file("${CMAKE_CURRENT_SOURCE_DIR}/libmodena.pc.in"
               "${CMAKE_CURRENT_BINARY_DIR}/libmodena.pc" @ONLY)

include(CMakePackageConfigHelpers)
write_basic_package_version_file(
  ${CMAKE_CURRENT_BINARY_DIR}/MODENAConfigVersion.cmake
  VERSION ${PACKAGE_VERSION}
  COMPATIBILITY AnyNewerVersion
)

#export(
# TARGETS twoTanksFullProblem modena fmodena
#  FILE ${CMAKE_CURRENT_BINARY_DIR}/MODENATargets.cmake
#  NAMESPACE MODENA::
#)

configure_file(
  cmake/MODENAConfig.cmake
  ${CMAKE_CURRENT_BINARY_DIR}/MODENAConfig.cmake
  COPYONLY
)

# Installation -------------------------------------------------------------- #
if(CMAKE_VERSION VERSION_GREATER "2.8.12")
  install(
    TARGETS twoTanksFullProblem modena fmodena
    EXPORT MODENATargets
    RUNTIME DESTINATION ${INSTALL_BIN_DIR}
    LIBRARY DESTINATION ${INSTALL_LIB_DIR}/modena
    ARCHIVE DESTINATION ${INSTALL_LIB_DIR}/static
    PUBLIC_HEADER DESTINATION ${INSTALL_INCLUDE_DIR}/modena
    INCLUDES DESTINATION ${INSTALL_INCLUDE_DIR}/modena
  )
else()
  install(
    TARGETS twoTanksFullProblem modena fmodena
    EXPORT MODENATargets
    RUNTIME DESTINATION ${INSTALL_BIN_DIR}
    LIBRARY DESTINATION ${INSTALL_LIB_DIR}/modena
    ARCHIVE DESTINATION ${INSTALL_LIB_DIR}/static
    PUBLIC_HEADER DESTINATION ${INSTALL_INCLUDE_DIR}/modena
  )
endif()

install(
  FILES
    "${CMAKE_CURRENT_BINARY_DIR}/libmodena.pc"
  DESTINATION
    "${INSTALL_LIB_DIR}/pkgconfig"
)

install(
  FILES
    "${CMAKE_CURRENT_BINARY_DIR}/fmodena.mod"
  DESTINATION
    "${INSTALL_INCLUDE_DIR}/modena"
)

install(EXPORT MODENATargets
  FILE
    MODENATargets.cmake
  NAMESPACE
    MODENA::
  DESTINATION
    ${ConfigPackageLocation}
)

# Install per-configuration targets files (MODENATargets-debug.cmake, etc.)
# install(EXPORT …) generates these in the build tree under an encoded copy of
# the absolute install path, but does not always install them when
# CMAKE_BUILD_TYPE is empty.  This code block runs at install time, globs
# every MODENATargets-*.cmake from the build-tree export cache, and copies it.
set(_modena_export_dir
    "${CMAKE_CURRENT_BINARY_DIR}/CMakeFiles/Export")
install(CODE "
  file(GLOB_RECURSE _cfg_files
    LIST_DIRECTORIES false
    \"${_modena_export_dir}/MODENATargets-*.cmake\"
  )
  foreach(_f IN LISTS _cfg_files)
    get_filename_component(_name \"\${_f}\" NAME)
    set(_dest \"${ConfigPackageLocation}\")
    if(NOT EXISTS \"\${_dest}/\${_name}\")
      file(COPY \"\${_f}\" DESTINATION \"\${_dest}\")
      message(STATUS \"Installing: \${_dest}/\${_name}\")
    else()
      message(STATUS \"Up-to-date: \${_dest}/\${_name}\")
    endif()
  endforeach()
")

install(
  FILES
    cmake/MODENAConfig.cmake
    ${CMAKE_CURRENT_BINARY_DIR}/MODENAConfigVersion.cmake
  DESTINATION
    ${ConfigPackageLocation}
)

