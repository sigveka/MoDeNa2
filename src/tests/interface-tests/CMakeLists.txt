cmake_minimum_required(VERSION 3.22...3.28)

# libmodena publicly includes global.h which includes Python.h.
# Test targets that link against modena must also see Python headers.
find_package(Python3 COMPONENTS Development REQUIRED)

# ---------------------------------------------------------------------------
# Interface smoke tests — one per language wrapper.  Each links a real
# language binding against libmodena and evaluates the `flowRate` model
# to end-to-end verify the wrapper is wired correctly.
#
# Tier labels (see ../pytest.ini) -- every entry here carries exactly one:
#
#   installed  needs `cmake --install`: headers, libmodena, wrapper packages
#   live       also needs a MongoDB holding a fitted `flowRate`
#
# The live tests do not prepare that database themselves: the fixtures in
# ../CMakeLists.txt do, in the database MODENA_TEST_URI names, and every
# live test is attached to them by modena_require_live() at the bottom of
# this file.  `ctest -L live` therefore runs the whole chain -- install
# check, flowRate install + fit, the tests, cleanup -- with no manual step.
# ---------------------------------------------------------------------------

# -- C++ (modena::Model, RAII wrapper) ------------------------------------
add_executable(test_cpp_smoke "${CMAKE_CURRENT_SOURCE_DIR}/test_cpp_smoke.C")
target_link_libraries(test_cpp_smoke PRIVATE modena_cpp modena)
target_include_directories(test_cpp_smoke PRIVATE ${Python3_INCLUDE_DIRS})
target_compile_features(test_cpp_smoke PRIVATE cxx_std_17)
add_test(NAME modena_iface_cpp_smoke COMMAND test_cpp_smoke)
set_tests_properties(modena_iface_cpp_smoke PROPERTIES LABELS "cpp;live")

# -- Fortran (fmodena_oop) ------------------------------------------------
# Only built if the Fortran wrapper is enabled.
if(TARGET fmodena_oop)
    add_executable(test_fortran_smoke
        "${CMAKE_CURRENT_SOURCE_DIR}/test_fortran_smoke.f90"
    )
    target_link_libraries(test_fortran_smoke PRIVATE fmodena_oop fmodena modena)
    add_test(NAME modena_iface_fortran_smoke COMMAND test_fortran_smoke)
    set_tests_properties(modena_iface_fortran_smoke
        PROPERTIES LABELS "fortran;live"
    )
endif()

# -- Multi-threaded C (twoTanksMT-style) ----------------------------------
# Multiple pthreads share one modena_model_t, each with its own I/O
# vectors.  Regression guard for the modena_substitute_model_t per-call
# allocation fix and the internal GIL protocol in modena_model_call.
find_package(Threads REQUIRED)
add_executable(test_thread_safety
    "${CMAKE_CURRENT_SOURCE_DIR}/test_thread_safety.C"
)
target_link_libraries(test_thread_safety PRIVATE modena Threads::Threads)
target_include_directories(test_thread_safety PRIVATE ${Python3_INCLUDE_DIRS})
target_compile_features(test_thread_safety PRIVATE cxx_std_17)
add_test(NAME modena_iface_thread_safety COMMAND test_thread_safety)
set_tests_properties(modena_iface_thread_safety
    PROPERTIES LABELS "cpp;live;thread"
)

# -- MATLAB / Octave (via MEX gateway + Modena.m class) -------------------
# Runs test_matlab_smoke.m through Octave (or MATLAB when available).
# Only wired up when WITH_MATLAB=ON so that the MEX gateway is built
# and installed to MATLAB_PKG_DIR — the test relies on
# ``octave --path <MATLAB_PKG_DIR>`` finding both the .mex and
# Modena.m there.
#
# Prefer Octave when both are available (faster startup, no license).
# MODENA_MATLAB_GATEWAY_BUILT, not WITH_MATLAB: the smoke test calls into
# libmodena through the MEX gateway, so an interpreter without a mex compiler
# would register a test that cannot possibly pass.
if(WITH_MATLAB AND MODENA_MATLAB_GATEWAY_BUILT)
    find_program(OCTAVE_EXECUTABLE octave)
    find_program(MATLAB_EXECUTABLE matlab)
    if(OCTAVE_EXECUTABLE)
        add_test(NAME modena_iface_matlab_smoke
            COMMAND "${OCTAVE_EXECUTABLE}" --no-gui --quiet
                --path "${MATLAB_PKG_DIR}"
                "${CMAKE_CURRENT_SOURCE_DIR}/test_matlab_smoke.m"
        )
        set_tests_properties(modena_iface_matlab_smoke PROPERTIES
            LABELS "octave;live"
        )
    elseif(MATLAB_EXECUTABLE)
        add_test(NAME modena_iface_matlab_smoke
            COMMAND "${MATLAB_EXECUTABLE}" -batch
                "addpath('${MATLAB_PKG_DIR}'); run('${CMAKE_CURRENT_SOURCE_DIR}/test_matlab_smoke.m');"
        )
        set_tests_properties(modena_iface_matlab_smoke PROPERTIES
            LABELS "matlab;live"
        )
    endif()
endif()

# -- Julia (Modena.jl, pure ccall bindings) -------------------------------
# Runs test_julia_smoke.jl through the julia executable.  Only wired up when
# WITH_JULIA=ON, which is also what makes src/wrappers/julia the configured
# wrapper.
#
# ``--project`` points at the wrapper SOURCE directory rather than the
# installed copy in JULIA_PKG_DIR: Modena.jl is pure Julia, copied verbatim at
# install time, so testing the source tree catches wrapper edits without
# requiring `cmake --install` first.  The C side is still the installed one —
# Modena.__init__ resolves libmodena.so through the installed modena Python
# package.
#
# Julia is located by the parent CMakeLists' probe (_JULIA_EXECUTABLE, set
# under WITH_JULIA); fall back to a local search if that cache entry is empty.
if(WITH_JULIA)
    if(_JULIA_EXECUTABLE)
        set(_julia_test_exe "${_JULIA_EXECUTABLE}")
    else()
        find_program(_julia_test_exe julia)
    endif()
    if(_julia_test_exe)
        add_test(NAME modena_iface_julia_smoke
            COMMAND "${_julia_test_exe}" --startup-file=no
                --project=${CMAKE_CURRENT_LIST_DIR}/../../wrappers/julia
                "${CMAKE_CURRENT_SOURCE_DIR}/test_julia_smoke.jl"
        )
        set_tests_properties(modena_iface_julia_smoke PROPERTIES
            LABELS "julia;live"
        )
    else()
        message(WARNING
            "WITH_JULIA=ON but no julia executable was found — "
            "skipping modena_iface_julia_smoke."
        )
    endif()
endif()

# -- R (modena R package, dlopen'd libmodena) -----------------------------
# Runs the package's own testthat suite, which already covers construction,
# evaluation and the named parameter accessors.  The suite lived in
# src/wrappers/r/tests/testthat/ with nothing referencing it, so R was the one
# wrapper with tests that never ran.
#
# ``test_dir`` is pointed at the SOURCE tests directory for the same reason the
# Julia test uses --project on the source tree: it picks up edits without
# requiring a reinstall first.  stop_on_failure makes testthat raise, and
# `R -e` exits non-zero on an uncaught error, which is what ctest reads.
#
# Gated on testthat being importable -- it is a test-only dependency that the
# wrapper itself does not need, so a missing testthat should skip the test
# rather than fail the suite.
if(WITH_R AND R_EXECUTABLE)
    execute_process(
        COMMAND "${R_EXECUTABLE}" --no-save --slave
                -e "cat(requireNamespace('testthat', quietly=TRUE))"
        OUTPUT_VARIABLE _r_has_testthat
        OUTPUT_STRIP_TRAILING_WHITESPACE
        ERROR_QUIET
    )
    if(_r_has_testthat STREQUAL "TRUE")
        add_test(NAME modena_iface_r_smoke
            COMMAND "${R_EXECUTABLE}" --no-save --slave -e
                "library(testthat); library(modena); test_dir('${CMAKE_CURRENT_LIST_DIR}/../../wrappers/r/tests/testthat', stop_on_failure = TRUE)"
        )
        # The package installs under the project prefix, not R's per-user
        # library, so R only finds it with R_LIBS set -- the same thing
        # modena-env.sh does for an interactive shell.
        set_tests_properties(modena_iface_r_smoke PROPERTIES
            LABELS "r;live"
            ENVIRONMENT "R_LIBS=${R_LIB_DIR};MODENA_LIB_DIR=${INSTALL_LIB_DIR}/modena"
        )
    else()
        # WARNING, not STATUS.  A STATUS line scrolls past unread, so the only
        # visible effect was the test count dropping from 13 to 12 -- and CI
        # installed testthat on purpose, got a silent failure from
        # install.packages(), and registered no R test for weeks without
        # anything turning red.
        message(WARNING
            "WITH_R=ON but the testthat package is not installed — "
            "skipping modena_iface_r_smoke.  Install it with:  "
            "apt install r-cran-testthat   (or, from source: "
            "R -e \"install.packages('testthat')\")")
    endif()
endif()

# -- Generated integration snippets ---------------------------------------
# modena.Integration renders per-model example code for seven languages.
# Compile the compiled-language ones and run them: a snippet that does not
# build is worse than none, because it looks authoritative.  Four template
# bugs were caught this way and would have passed any string assertion.
find_package(Python3 COMPONENTS Interpreter REQUIRED)
add_test(
    NAME    modena_generated_snippets
    COMMAND ${Python3_EXECUTABLE} -m pytest
            "${CMAKE_CURRENT_SOURCE_DIR}/test_generated_snippets.py"
            -m live --tb=short -q
)
set_tests_properties(modena_generated_snippets PROPERTIES
    LABELS      "python;live;snippets"
    ENVIRONMENT "MODENA_PREFIX=${CMAKE_INSTALL_PREFIX};MODENA_LIB_DIR=${INSTALL_LIB_DIR}/modena"
)

# -- OutOfBounds exception contract ---------------------------------------
# model.c constructs the OutOfBounds instance itself, so its argument list is
# a Python<->C contract: dropping the return code there silently degrades
# every pure-Python caller.  Lives here rather than in tests/python/ because
# that directory's conftest stubs out `modena` to keep the unit tier free of
# libmodena -- this test needs the real thing.
add_test(
    NAME    modena_oob_exception
    COMMAND ${Python3_EXECUTABLE} -m pytest
            "${CMAKE_CURRENT_SOURCE_DIR}/test_oob_exception.py"
            -m live --tb=short -q
)
set_tests_properties(modena_oob_exception PROPERTIES
    LABELS      "python;live"
    ENVIRONMENT "MODENA_LIB_DIR=${INSTALL_LIB_DIR}/modena"
)

# -- The out-of-bounds -> refit loop, end to end --------------------------
# Runs the twoTanks simulation against a freshly initialised flowRate and
# asserts it leaves the trained box, refits, and finishes -- in 1..6 refits.
# Installs the example packages itself and uses a database of its own
# (modena_looptest_<id> on the MODENA_TEST_URI server, dropped afterwards),
# so it does not use the live fixture and cannot disturb the tests that do.
add_test(
    NAME    modena_twotanks_loop
    COMMAND ${Python3_EXECUTABLE} -m pytest
            "${CMAKE_CURRENT_SOURCE_DIR}/test_twotanks_loop.py"
            -m live --tb=short -q
)
set_tests_properties(modena_twotanks_loop PROPERTIES
    LABELS            "python;live;workflow"
    TIMEOUT           900
    ENVIRONMENT       "MODENA_URI=${MODENA_TEST_URI}"
    FIXTURES_REQUIRED modena_installed
)

# -- modena doctor --selftest ---------------------------------------------
# The install-only end-to-end check a user runs: install the bundled
# flowRate from <prefix>/share/modena/selftest, fit it, evaluate it from
# Python and C.  Exercising it here keeps the command a user is told to run
# from rotting.  It uses a database of its own on the MODENA_TEST_URI server.
#
# doctor also checks for a project modena.toml, which a build directory does
# not have; run it from one configure writes.
set(_DOCTOR_DIR "${CMAKE_CURRENT_BINARY_DIR}/doctor")
file(WRITE "${_DOCTOR_DIR}/modena.toml"
    "# Written by src/tests/interface-tests/CMakeLists.txt for modena_doctor_selftest.\n[models]\npaths = []\n")
add_test(
    NAME    modena_doctor_selftest
    COMMAND ${Python3_EXECUTABLE} -m modena doctor --selftest
    WORKING_DIRECTORY "${_DOCTOR_DIR}"
)
set_tests_properties(modena_doctor_selftest PROPERTIES
    LABELS            "python;live;selftest"
    TIMEOUT           900
    ENVIRONMENT       "MODENA_URI=${MODENA_TEST_URI}"
    FIXTURES_REQUIRED modena_installed
)

# -- Status codes agree across every binding ------------------------------
# The protocol numbers exist in five places (Python, the C enum, and the
# Fortran / MATLAB / R mirrors).  Five copies is what let "201 = clean exit"
# survive in six documents, so pin them together.
add_test(
    NAME    modena_status_codes
    COMMAND ${Python3_EXECUTABLE} -m pytest
            "${CMAKE_CURRENT_SOURCE_DIR}/test_status_codes.py"
            -m installed --tb=short -q
)
set_tests_properties(modena_status_codes PROPERTIES
    LABELS            "python;installed"
    ENVIRONMENT       "MODENA_PREFIX=${CMAKE_INSTALL_PREFIX};MODENA_LIB_DIR=${INSTALL_LIB_DIR}/modena"
    FIXTURES_REQUIRED modena_installed
)

# ---------------------------------------------------------------------------
# Attach every live test to the live fixture
#
# Appends, rather than sets, so tests that already carry an ENVIRONMENT (the
# R smoke, the snippets) keep it.  Tests registered only for some toolchains
# (Fortran, MATLAB, Julia, R) are skipped when absent.
#
# Every test labelled `live` in this file must appear in exactly one of the
# two lists below; test_suite_integrity.py enforces it, because a live test
# missing from both would run against whatever database the environment
# happens to name.
# ---------------------------------------------------------------------------
set(_MODENA_LIVE_TESTS
    modena_iface_cpp_smoke
    modena_iface_fortran_smoke
    modena_iface_thread_safety
    modena_iface_matlab_smoke
    modena_iface_julia_smoke
    modena_iface_r_smoke
    modena_generated_snippets
    modena_oob_exception
)
#: Live tests that manage a database of their own instead of the fixture's.
set(_MODENA_SELF_CONTAINED_LIVE_TESTS
    modena_twotanks_loop
    modena_doctor_selftest
)

function(modena_require_live name)
    if(NOT TEST ${name})
        return()
    endif()
    set_property(TEST ${name} APPEND PROPERTY ENVIRONMENT ${MODENA_LIVE_ENVIRONMENT})
    set_property(TEST ${name} APPEND PROPERTY
        FIXTURES_REQUIRED modena_installed modena_live_db)
    set_property(TEST ${name} APPEND PROPERTY RESOURCE_LOCK modena_live_db)
endfunction()

foreach(_t IN LISTS _MODENA_LIVE_TESTS)
    modena_require_live(${_t})
endforeach()
