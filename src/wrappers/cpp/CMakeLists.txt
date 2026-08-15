# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
# MODENA::modena_cpp — header-only C++17 RAII wrapper
#
# Users link against this target:
#   target_link_libraries(myapp PRIVATE MODENA::modena_cpp)
#
# and include the single header:
#   #include <modena/modena.hpp>
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #

add_library(modena_cpp INTERFACE)
add_library(MODENA::modena_cpp ALIAS modena_cpp)

target_include_directories(modena_cpp INTERFACE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

target_link_libraries(modena_cpp INTERFACE modena)
target_compile_features(modena_cpp INTERFACE cxx_std_17)

# Install the header tree: include/modena/modena.hpp
install(
    DIRECTORY include/
    DESTINATION include
)

install(
    TARGETS modena_cpp
    EXPORT  MODENATargets
)
