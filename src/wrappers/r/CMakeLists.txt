# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
# R wrapper — pure R + C source package, compiled by R CMD INSTALL.
#
# The package does NOT link against libmodena at compile time; libmodena.so is
# loaded via dlopen() at runtime (same approach as the MATLAB MEX gateway).
# This means the package can be compiled on any machine with R and a C
# compiler, regardless of whether MoDeNa is installed.
#
# At install time, if R is available, cmake --install runs R CMD INSTALL to
# compile the C extension and register the package into R's default library.
# If R is not found, the source tree is still installed so the user can run
# R CMD INSTALL manually later.
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #

set(R_PKG_SRC_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
set(R_PKG_INST_DIR "${CMAKE_INSTALL_PREFIX}/share/modena/R/modena")

# Install the full R package source tree so `R CMD INSTALL <path>` always works.
modena_status_block(MODENA_STATUS_BLOCK r)
modena_status_exports(MODENA_STATUS_EXPORTS)
configure_file(
    "${R_PKG_SRC_DIR}/NAMESPACE.in"
    "${CMAKE_CURRENT_BINARY_DIR}/NAMESPACE"
    @ONLY
)
install(
    FILES       "${CMAKE_CURRENT_BINARY_DIR}/NAMESPACE"
    DESTINATION "${R_PKG_INST_DIR}"
)
configure_file(
    "${R_PKG_SRC_DIR}/R/status_codes.R.in"
    "${CMAKE_CURRENT_BINARY_DIR}/status_codes.R"
    @ONLY
)
# Must land in the copied source tree BEFORE R CMD INSTALL runs, so it is
# installed with the rest of the package rather than after it.
install(
    FILES       "${CMAKE_CURRENT_BINARY_DIR}/status_codes.R"
    DESTINATION "${R_PKG_INST_DIR}/R"
)

install(
    DIRECTORY   "${R_PKG_SRC_DIR}/"
    DESTINATION "${R_PKG_INST_DIR}"
    PATTERN     "*.in"           EXCLUDE
    PATTERN     "CMakeLists.txt" EXCLUDE
    PATTERN     ".git"           EXCLUDE
)

find_program(R_EXECUTABLE R)

if(R_EXECUTABLE)
    # `R CMD INSTALL` with no -l targets the first entry of .libPaths(), which
    # on a distro R is the root-owned /usr/local/lib/R/site-library.  A normal
    # user install therefore fails with
    #
    #     ERROR: no permission to install to directory '.../site-library'
    #
    # and the failure only surfaces as a cmake WARNING buried in the install
    # log, so WITH_R=ON silently produced no installed package.
    #
    # Install into the project's own prefix instead of R's per-user library:
    # every other component honours INSTALL_LIB_DIR, and a build configured
    # with -DCMAKE_INSTALL_PREFIX=/opt/modena must not quietly write into
    # ~/R/... behind the packager's back (it would also escape DESTDIR
    # staging).  modena-env.sh puts this directory on R_LIBS so that
    # `library(modena)` resolves it.
    message(STATUS
        "R found: ${R_EXECUTABLE} — modena R package will be installed to ${R_LIB_DIR}")

    install(CODE "
        message(STATUS \"Compiling and installing the modena R package...\")
        file(MAKE_DIRECTORY \"\$ENV{DESTDIR}${R_LIB_DIR}\")
        execute_process(
            COMMAND \"${R_EXECUTABLE}\" CMD INSTALL
                    -l \"\$ENV{DESTDIR}${R_LIB_DIR}\"
                    \"\$ENV{DESTDIR}${R_PKG_INST_DIR}\"
            RESULT_VARIABLE _r_result
            ERROR_VARIABLE  _r_error
            OUTPUT_VARIABLE _r_output
        )
        if(NOT _r_result EQUAL 0)
            message(WARNING
                \"R CMD INSTALL failed (exit \${_r_result}):\n\${_r_error}\n\"
                \"Install manually with:\n\"
                \"  R CMD INSTALL -l ${R_LIB_DIR} ${R_PKG_INST_DIR}\")
        else()
            message(STATUS \"modena R package installed to ${R_LIB_DIR}\")
        endif()
    ")
else()
    message(STATUS
        "R not found — R package source installed but not compiled")
    install(CODE "
        message(STATUS \"modena R package source installed to ${R_PKG_INST_DIR}\")
        message(STATUS \"R was not found at configure time.\")
        message(STATUS \"Once R is installed, compile the package with:\")
        message(STATUS \"  R CMD INSTALL ${R_PKG_INST_DIR}\")
    ")
endif()

# Expose the install directory to the parent scope so examples can reference it.
set(R_PKG_DIR "${R_PKG_INST_DIR}" PARENT_SCOPE)
