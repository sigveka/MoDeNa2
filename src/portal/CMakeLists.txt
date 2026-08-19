# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
#
#
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #

# PYTHON_SITE comes from src/CMakeLists.txt.  This file used to recompute it,
# but only ever emitted the ${CMAKE_INSTALL_PREFIX} branch -- so with the
# default $HOME prefix modena went to user site-packages while modena_portal
# went to ${prefix}/lib/pythonX.Y/site-packages, which is not on sys.path.
# `modena-portal` then failed with ModuleNotFoundError: No module named
# 'modena_portal'.  Never recompute it here.

set(SETUP_PY_IN   ${CMAKE_CURRENT_SOURCE_DIR}/setup.py.in)
set(SETUP_PY      ${CMAKE_CURRENT_BINARY_DIR}/setup.py)
set(ENTRY_IN      ${CMAKE_CURRENT_SOURCE_DIR}/modena-portal.in)
set(ENTRY_SCRIPT  ${CMAKE_CURRENT_BINARY_DIR}/modena-portal)
file(GLOB_RECURSE DEPS "*.py" "assets/*.css")
set(OUTPUT        ${CMAKE_CURRENT_BINARY_DIR}/build/timestamp)

configure_file(${SETUP_PY_IN} ${SETUP_PY})
configure_file(${ENTRY_IN}    ${ENTRY_SCRIPT})

# `cmake -E touch` does not create missing parent directories, so the build/
# subdirectory has to be made first — otherwise the target fails outright on a
# clean build tree.  Same pattern as src/python/CMakeLists.txt.
add_custom_command(OUTPUT ${OUTPUT}
                   COMMAND ${CMAKE_COMMAND} -E make_directory "${CMAKE_CURRENT_BINARY_DIR}/build"
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

# ---------------------------------------------------------------------------
# Portal unit tests.
#
# These existed (data/test_queries.py) but were never registered, so three of
# them had rotted through the named-parameter rework unnoticed -- they still
# passed parameters as a positional list years after the schema became a dict.
# Registered here so that cannot happen again.
#
# Pure logic: no MongoDB, no libmodena, no browser.
# ---------------------------------------------------------------------------
if(MODENA_BUILD_TESTS)
    add_test(
        NAME    modena_portal_unit
        COMMAND ${Python3_EXECUTABLE} -m pytest "${CMAKE_CURRENT_SOURCE_DIR}"
                --tb=short -q
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
    )
    set_tests_properties(modena_portal_unit PROPERTIES LABELS "python;unit;portal")
endif()
