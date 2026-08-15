# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
# @brief  Build Python-specific files for coolPropMixtureTP model
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #

set(SETUP_PY_IN "${CMAKE_CURRENT_SOURCE_DIR}/setup.py.in")
set(SETUP_PY    "${CMAKE_CURRENT_BINARY_DIR}/setup.py")
file(GLOB DEPS  "${CMAKE_CURRENT_SOURCE_DIR}/*.py")
set(OUTPUT      "${CMAKE_CURRENT_BINARY_DIR}/timestamp")

add_custom_command(OUTPUT ${OUTPUT}
                   COMMAND ${CMAKE_COMMAND} -E touch ${OUTPUT}
                   WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}"
                   DEPENDS ${DEPS}
)

configure_file(${SETUP_PY_IN} ${SETUP_PY})

add_custom_target(coolPropMixtureTP ALL DEPENDS ${OUTPUT})

file(MAKE_DIRECTORY
  "${CMAKE_CURRENT_BINARY_DIR}/${CMAKE_PROJECT_NAME}-${CMAKE_PROJECT_VERSION}.dist-info"
)
file(WRITE
  "${CMAKE_CURRENT_BINARY_DIR}/${CMAKE_PROJECT_NAME}-${CMAKE_PROJECT_VERSION}.dist-info/METADATA"
  "Metadata-Version: 2.1\nName: ${CMAKE_PROJECT_NAME}\nVersion: ${CMAKE_PROJECT_VERSION}\n"
)

install(FILES ${DEPS}
  DESTINATION "${PYTHON_SITE}/${CMAKE_PROJECT_NAME}"
)
install(
  FILES "${CMAKE_CURRENT_BINARY_DIR}/${CMAKE_PROJECT_NAME}-${CMAKE_PROJECT_VERSION}.dist-info/METADATA"
  DESTINATION "${PYTHON_SITE}/${CMAKE_PROJECT_NAME}-${CMAKE_PROJECT_VERSION}.dist-info"
)
