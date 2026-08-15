set(CMAKE_BUILD_TYPE Release)

set(CMAKE_SKIP_BUILD_RPATH FALSE)
set(CMAKE_BUILD_WITH_INSTALL_RPATH FALSE)
set(CMAKE_INSTALL_RPATH_USE_LINK_PATH TRUE)

find_package(MODENA REQUIRED)
find_package(Threads REQUIRED)

include(CheckCInline)
check_c_inline(C_INLINE)

add_executable(twoTanksMT twoTanksMT.c)
target_link_libraries(twoTanksMT MODENA::modena Threads::Threads)

install(
    TARGETS twoTanksMT
    RUNTIME DESTINATION "${PKG_DIR}/bin"
)
