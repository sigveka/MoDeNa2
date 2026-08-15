# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
# Julia wrapper — pure Julia package, no compilation required.
#
# At install time, if Julia is available, Modena.jl is registered into Julia's
# default shared environment via Pkg.develop so that `using Modena` works
# without any extra configuration.
#
# If Julia is not found during install, a message is printed with the manual
# registration command.  The package files are still installed regardless.
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #

set(JULIA_PKG_DIR "${CMAKE_INSTALL_PREFIX}/share/julia/packages/Modena")

install(
  FILES "${CMAKE_CURRENT_SOURCE_DIR}/Project.toml"
  DESTINATION "${JULIA_PKG_DIR}"
)
install(
  FILES "${CMAKE_CURRENT_SOURCE_DIR}/src/Modena.jl"
  DESTINATION "${JULIA_PKG_DIR}/src"
)

# Write the registration script at configure time — no escaping needed.
# Explicitly target the global shared environment via the depot path so the
# result is independent of the working directory at install time.
set(_REG_SCRIPT "${CMAKE_CURRENT_BINARY_DIR}/register_modena.jl")
file(WRITE "${_REG_SCRIPT}"
  "import Pkg\n"
  "env_dir = joinpath(first(Base.DEPOT_PATH), \"environments\",\n"
  "                   \"v\$(VERSION.major).\$(VERSION.minor)\")\n"
  "mkpath(env_dir)\n"
  "Pkg.activate(env_dir)\n"
  "Pkg.develop(Pkg.PackageSpec(path=\"${JULIA_PKG_DIR}\"))\n"
)

# Register the package with Julia's package manager at install time.
find_program(Julia_EXECUTABLE julia)
find_program(lld_EXECUTABLE lld)

# Some Julia installations shell out to a system lld to precompile packages;
# others (juliaup binaries, for instance) ship their own linker and need
# nothing from the system.  Warn rather than fail — a missing system lld is
# only a problem for the former, and Pkg.develop below reports it clearly if
# precompilation does break.
if(Julia_EXECUTABLE AND NOT lld_EXECUTABLE)
  message(WARNING
    "lld (LLVM linker) not found.\n"
    "Some Julia builds need it to precompile packages; others bundle their own.\n"
    "If Modena.jl fails to precompile, install it with:  sudo apt install lld"
  )
endif()

if(Julia_EXECUTABLE)
  message(STATUS "Julia found: ${Julia_EXECUTABLE} — Modena.jl will be registered on install")
  install(CODE "
    message(STATUS \"Registering Modena.jl with Julia's package manager...\")
    execute_process(
      COMMAND \"${Julia_EXECUTABLE}\" --startup-file=no \"${_REG_SCRIPT}\"
      RESULT_VARIABLE _julia_result
      ERROR_VARIABLE  _julia_error
    )
    if(NOT _julia_result EQUAL 0)
      message(WARNING \"Pkg.develop failed (exit \${_julia_result}):\\n\${_julia_error}\")
      message(WARNING \"Register manually: julia --startup-file=no ${_REG_SCRIPT}\")
    else()
      message(STATUS \"Modena.jl registered successfully\")
    endif()
  ")
else()
  message(STATUS "Julia not found — Modena.jl files will be installed but not registered")
  install(CODE "
    message(STATUS \"Modena.jl installed to ${JULIA_PKG_DIR}\")
    message(STATUS \"Julia was not found at configure time. Once Julia is installed, run:\")
    message(STATUS \"  julia --startup-file=no ${_REG_SCRIPT}\")
  ")
endif()
