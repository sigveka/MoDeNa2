# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
#
#
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
project (flowRateExact VERSION 1.0 LANGUAGES C CXX)

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

find_package(MODENA REQUIRED)

include(CheckCInline)
check_c_inline(C_INLINE)

add_executable(flowRateExact flowRateExact.C)

install(
  TARGETS flowRateExact
  RUNTIME DESTINATION       "${PKG_DIR}/bin"
  LIBRARY DESTINATION       "${PKG_DIR}/lib"
  ARCHIVE DESTINATION       "${PKG_DIR}/lib/static"
  PUBLIC_HEADER DESTINATION "${PKG_DIR}/lib"
)


