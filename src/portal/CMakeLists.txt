# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
#
#
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #

find_package(Python3 COMPONENTS Interpreter REQUIRED)

# Compute the same site-packages path used by src/python/CMakeLists.txt so
# that modena_portal lands alongside modena in the same directory.
execute_process(
  COMMAND "${Python3_EXECUTABLE}" -c
    "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
  OUTPUT_VARIABLE Python3_VERSION_MAJMIN
  OUTPUT_STRIP_TRAILING_WHITESPACE
)
set(PYTHON_SITE "${CMAKE_INSTALL_PREFIX}/lib/python${Python3_VERSION_MAJMIN}/site-packages")

set(SETUP_PY_IN   ${CMAKE_CURRENT_SOURCE_DIR}/setup.py.in)
set(SETUP_PY      ${CMAKE_CURRENT_BINARY_DIR}/setup.py)
set(ENTRY_IN      ${CMAKE_CURRENT_SOURCE_DIR}/modena-portal.in)
set(ENTRY_SCRIPT  ${CMAKE_CURRENT_BINARY_DIR}/modena-portal)
file(GLOB_RECURSE DEPS "*.py" "assets/*.css")
set(OUTPUT        ${CMAKE_CURRENT_BINARY_DIR}/build/timestamp)

configure_file(${SETUP_PY_IN} ${SETUP_PY})
configure_file(${ENTRY_IN}    ${ENTRY_SCRIPT})

add_custom_command(OUTPUT ${OUTPUT}
                   COMMAND ${CMAKE_COMMAND} -E touch ${OUTPUT}
                   DEPENDS ${DEPS}
                  )

add_custom_target(portal ALL DEPENDS ${OUTPUT})

# Install modena_portal into the same site-packages directory as modena so
# the user's PYTHONPATH (which already finds modena) also finds modena_portal.
install(
    CODE "execute_process(COMMAND ${Python3_EXECUTABLE} -m pip install --target=${PYTHON_SITE} --upgrade ${CMAKE_CURRENT_BINARY_DIR})"
)

# Install the entry-point script directly, replacing any stale egg-based one.
install(
    PROGRAMS ${ENTRY_SCRIPT}
    DESTINATION ${INSTALL_BIN_DIR}
)
