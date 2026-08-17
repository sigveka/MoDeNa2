# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
#
#
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #

find_package(Python3 COMPONENTS Interpreter)


# Compute Python site-packages install destination.
#
# When CMAKE_INSTALL_PREFIX is $HOME (the default user install), put the
# Python package in ~/.local/lib/pythonX.Y/site-packages (user site-packages).
# site.py adds this directory automatically even in embedded mode, so
# libmodena's Py_Initialize() finds modena without PYTHONPATH.
#
# For any other prefix (e.g. /opt/modena, /usr/local) put the package
# alongside the C library under the prefix. The admin is then responsible
# for adding the prefix's site-packages to PYTHONPATH (e.g. via a module file).
execute_process(
  COMMAND "${Python3_EXECUTABLE}" -c
    "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
  OUTPUT_VARIABLE Python3_VERSION_MAJMIN
  OUTPUT_STRIP_TRAILING_WHITESPACE
)
if(CMAKE_INSTALL_PREFIX_INITIALIZED_TO_DEFAULT OR
   CMAKE_INSTALL_PREFIX STREQUAL "$ENV{HOME}")
    execute_process(
        COMMAND "${Python3_EXECUTABLE}" -c "import site; print(site.getusersitepackages())"
        OUTPUT_VARIABLE PYTHON_SITE
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
else()
    set(PYTHON_SITE
        "${CMAKE_INSTALL_PREFIX}/lib/python${Python3_VERSION_MAJMIN}/site-packages")
endif()

set(SETUP_PY_IN ${CMAKE_CURRENT_SOURCE_DIR}/setup.py.in)
set(SETUP_PY    ${CMAKE_CURRENT_BINARY_DIR}/setup.py)
file(GLOB DEPS "${CMAKE_CURRENT_SOURCE_DIR}/*.py")
set(OUTPUT      ${CMAKE_CURRENT_BINARY_DIR}/build/timestamp)

configure_file(${SETUP_PY_IN} ${SETUP_PY})

# Generate _paths.py from template (no runtime path discovery needed)
configure_file(
  "${CMAKE_CURRENT_SOURCE_DIR}/_paths.py.in"
  "${CMAKE_CURRENT_BINARY_DIR}/_paths.py"
  @ONLY
)

# Resolve the shared-library directory to an absolute path for the env script.
# INSTALL_LIB_DIR is declared as a CACHE PATH, which CMake absolutises, but it
# is documented as a relative directory -- handle both so the script is correct
# either way.
if(IS_ABSOLUTE "${INSTALL_LIB_DIR}")
    set(MODENA_ENV_LIB_DIR "${INSTALL_LIB_DIR}/modena")
else()
    set(MODENA_ENV_LIB_DIR "${CMAKE_INSTALL_PREFIX}/${INSTALL_LIB_DIR}/modena")
endif()

# Generate the shell environment script.
#
# This lives here rather than at the top level because PYTHON_SITE is computed
# above and is the one path the script cannot derive on its own.  Sourcing it
# is never required for a default $HOME install -- Python and the $ORIGIN
# RUNPATH already resolve everything -- but it is the supported answer for a
# custom prefix, for virtualenvs (where user site-packages is dropped from
# sys.path), and for applications that link against libmodena.
configure_file(
  "${CMAKE_CURRENT_SOURCE_DIR}/modena-env.sh.in"
  "${CMAKE_CURRENT_BINARY_DIR}/modena-env.sh"
  @ONLY
)

add_custom_command(OUTPUT ${OUTPUT}
                   COMMAND ${CMAKE_COMMAND} -E make_directory "${CMAKE_CURRENT_BINARY_DIR}/build"
                   COMMAND ${CMAKE_COMMAND} -E touch ${OUTPUT}
                   DEPENDS modena ${DEPS}
                  )

add_custom_target(python ALL DEPENDS ${OUTPUT})

install(FILES ${DEPS}
  DESTINATION "${PYTHON_SITE}/modena"
)
install(FILES "${CMAKE_CURRENT_BINARY_DIR}/_paths.py"
  DESTINATION "${PYTHON_SITE}/modena"
)

install(FILES "${CMAKE_CURRENT_BINARY_DIR}/modena-env.sh"
  DESTINATION "share/modena"
)

# Console entry point.  setup.py.in declares `modena = modena.__main__:_main`
# under console_scripts, but the package is installed by the install(FILES)
# rule above rather than by running setup.py, so nothing ever generates the
# launcher pip would have produced.  Generate it here instead, with the
# shebang pinned to the configured interpreter exactly as pip does.
configure_file(
  "${CMAKE_CURRENT_SOURCE_DIR}/modena.py.in"
  "${CMAKE_CURRENT_BINARY_DIR}/modena"
  @ONLY
)
install(PROGRAMS "${CMAKE_CURRENT_BINARY_DIR}/modena"
  DESTINATION "bin"
)

file(MAKE_DIRECTORY
  "${CMAKE_CURRENT_BINARY_DIR}/modena-${PROJECT_VERSION}.dist-info"
)
file(WRITE
  "${CMAKE_CURRENT_BINARY_DIR}/modena-${PROJECT_VERSION}.dist-info/METADATA"
  "Metadata-Version: 2.1\nName: modena\nVersion: ${PROJECT_VERSION}\n"
)
install(
  FILES "${CMAKE_CURRENT_BINARY_DIR}/modena-${PROJECT_VERSION}.dist-info/METADATA"
  DESTINATION "${PYTHON_SITE}/modena-${PROJECT_VERSION}.dist-info"
)


