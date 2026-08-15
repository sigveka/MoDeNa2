cmake_minimum_required(VERSION 3.22...3.28)

set(CMAKE_BUILD_TYPE Release)

add_custom_target(debug
  COMMAND ${CMAKE_COMMAND} -DCMAKE_BUILD_TYPE=Debug ${CMAKE_SOURCE_DIR}
  COMMAND ${CMAKE_COMMAND} --build ${CMAKE_BINARY_DIR} --target all
  COMMENT "Switch CMAKE_BUILD_TYPE to Debug"
  )

add_custom_target(release
  COMMAND ${CMAKE_COMMAND} -DCMAKE_BUILD_TYPE=Release ${CMAKE_SOURCE_DIR}
  COMMAND ${CMAKE_COMMAND} --build ${CMAKE_BINARY_DIR} --target all
  COMMENT "Switch CMAKE_BUILD_TYPE to Release"
  )

set (CMAKE_NO_SYSTEM_FROM_IMPORTED yes)

find_package(MODENA REQUIRED)

include(CheckCInline)
check_c_inline(C_INLINE)

# Use, i.e. don't skip, the full RPATH for the build tree
SET(CMAKE_SKIP_BUILD_RPATH  FALSE)

# Do not use the install RPATH when building (but later on when installing)
set(CMAKE_BUILD_WITH_INSTALL_RPATH FALSE)

# Set the RPATH to be used when installing (colon separated list)
# set(CMAKE_INSTALL_RPATH "$ENV{HOME}/lib/modena:$ORIGIN/..")

# Adding automatically determined parts of the RPATH
# which point to directories outside the build tree to the install RPATH
SET(CMAKE_INSTALL_RPATH_USE_LINK_PATH TRUE)

add_executable(fullerEtAlDiffusionTest fullerEtAlDiffusionTest.C)
target_link_libraries(fullerEtAlDiffusionTest MODENA::modena)

install(
  TARGETS fullerEtAlDiffusionTest
  RUNTIME DESTINATION       "${INSTALL_BIN_DIR}"
  LIBRARY DESTINATION       "${INSTALL_LIB_DIR}"
  ARCHIVE DESTINATION       "${INSTALL_LIB_DIR}/static"
  PUBLIC_HEADER DESTINATION "${INSTALL_LIB_DIR}"
)


