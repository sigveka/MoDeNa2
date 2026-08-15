
set(CMAKE_BUILD_TYPE Release)

set (CMAKE_NO_SYSTEM_FROM_IMPORTED yes)

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


# Use, i.e. don't skip, the full RPATH for the build tree
SET(CMAKE_SKIP_BUILD_RPATH  FALSE)

# Do not use the install RPATH when building (but later on when installing)
set(CMAKE_BUILD_WITH_INSTALL_RPATH FALSE)

# Set the RPATH to be used when installing (colon separated list)
# set(CMAKE_INSTALL_RPATH "$ENV{HOME}/lib/modena:$ORIGIN/..")

# Adding automatically determined parts of the RPATH
# which point to directories outside the build tree to the install RPATH
SET(CMAKE_INSTALL_RPATH_USE_LINK_PATH TRUE)


find_package(MODENA REQUIRED)

add_executable(twoTanksMacroscopicProblemFortran twoTanksMacroscopicProblemFortran.f90)
target_link_libraries(twoTanksMacroscopicProblemFortran MODENA::fmodena_oop)

install(
  TARGETS twoTanksMacroscopicProblemFortran
  RUNTIME DESTINATION       "${PKG_DIR}/bin"
  LIBRARY DESTINATION       "${PKG_DIR}/lib"
  ARCHIVE DESTINATION       "${PKG_DIR}/lib/static"
  PUBLIC_HEADER DESTINATION "${PKG_DIR}/lib"
)

