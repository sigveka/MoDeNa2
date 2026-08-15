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
    message(STATUS
        "R found: ${R_EXECUTABLE} — modena R package will be compiled on install")
    install(CODE "
        message(STATUS \"Compiling and installing the modena R package...\")
        execute_process(
            COMMAND \"${R_EXECUTABLE}\" CMD INSTALL \"${R_PKG_INST_DIR}\"
            RESULT_VARIABLE _r_result
            ERROR_VARIABLE  _r_error
            OUTPUT_VARIABLE _r_output
        )
        if(NOT _r_result EQUAL 0)
            message(WARNING
                \"R CMD INSTALL failed (exit \${_r_result}):\n\${_r_error}\n\"
                \"Install manually once R is available:\n\"
                \"  R CMD INSTALL ${R_PKG_INST_DIR}\")
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
