cmake_minimum_required(VERSION 3.22...3.28)

add_executable(twoTanksMacroscopicProblem "${CMAKE_CURRENT_SOURCE_DIR}/twoTanksFullProblem.C")
target_link_libraries(twoTanksMacroscopicProblem modena)

#
