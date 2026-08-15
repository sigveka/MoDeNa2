include(${CMAKE_CURRENT_LIST_DIR}/MODENATargets.cmake)

list(APPEND CMAKE_MODULE_PATH ${CMAKE_CURRENT_LIST_DIR})

find_package(LTDL REQUIRED)

# MoDeNa requires Python 3.  Surrogate-function sub-builds must use the same
# Python headers so that modena_model_t (which embeds PyObject_HEAD) has the
# same layout as the one inside libmodena.so.
find_package(Python3 COMPONENTS Development REQUIRED)
include_directories(${Python3_INCLUDE_DIRS})
