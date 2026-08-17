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
install(
    DIRECTORY   "${R_PKG_SRC_DIR}/"
    DESTINATION "${R_PKG_INST_DIR}"
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
    # log, so the wrapper silently never gets installed.  Target R_LIBS_USER
    # instead: R's own per-user library, which it prepends to .libPaths()
    # automatically once the directory exists.
    execute_process(
        COMMAND "${R_EXECUTABLE}" --no-save --slave
                -e "cat(path.expand(Sys.getenv('R_LIBS_USER')))"
        OUTPUT_VARIABLE  R_USER_LIB
        OUTPUT_STRIP_TRAILING_WHITESPACE
        ERROR_QUIET
    )

    if(R_USER_LIB)
        message(STATUS
            "R found: ${R_EXECUTABLE} — modena R package will be installed to ${R_USER_LIB}")
    else()
        # R reported no user library; fall back to its default and let the
        # permission error (if any) surface as before.
        message(STATUS
            "R found: ${R_EXECUTABLE} — modena R package will be compiled on install")
    endif()

    install(CODE "
        message(STATUS \"Compiling and installing the modena R package...\")
        set(_r_lib \"${R_USER_LIB}\")
        if(NOT _r_lib STREQUAL \"\")
            file(MAKE_DIRECTORY \"\${_r_lib}\")
            set(_r_args CMD INSTALL -l \"\${_r_lib}\" \"${R_PKG_INST_DIR}\")
        else()
            set(_r_args CMD INSTALL \"${R_PKG_INST_DIR}\")
        endif()
        execute_process(
            COMMAND \"${R_EXECUTABLE}\" \${_r_args}
            RESULT_VARIABLE _r_result
            ERROR_VARIABLE  _r_error
            OUTPUT_VARIABLE _r_output
        )
        if(NOT _r_result EQUAL 0)
            message(WARNING
                \"R CMD INSTALL failed (exit \${_r_result}):\n\${_r_error}\n\"
                \"Install manually once R is available:\n\"
                \"  R CMD INSTALL -l \${_r_lib} ${R_PKG_INST_DIR}\")
        else()
            message(STATUS \"modena R package installed successfully\")
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
