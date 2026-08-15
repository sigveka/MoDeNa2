cmake_minimum_required(VERSION 3.22...3.28)

# libmodena publicly includes global.h which includes Python.h.
# Test targets that link against modena must also see Python headers.
find_package(Python3 COMPONENTS Development REQUIRED)

add_executable(twoTanksMacroscopicProblem "${CMAKE_CURRENT_SOURCE_DIR}/twoTanksFullProblem.C")
target_link_libraries(twoTanksMacroscopicProblem modena)
target_include_directories(twoTanksMacroscopicProblem PRIVATE ${Python3_INCLUDE_DIRS})

# ---------------------------------------------------------------------------
# Interface smoke tests — one per language wrapper.  Each links a real
# language binding against libmodena and evaluates the `flowRate` model
# to end-to-end verify the wrapper is wired correctly.
#
# Registered under the "integration" label because they require:
#   * a live MongoDB pointed to by MODENA_URI
#   * the `flowRate` model already initialized (run examples/twoTanks/initModels)
# Run with:  ctest -L integration
# ---------------------------------------------------------------------------

# -- C++ (modena::Model, RAII wrapper) ------------------------------------
add_executable(test_cpp_smoke "${CMAKE_CURRENT_SOURCE_DIR}/test_cpp_smoke.C")
target_link_libraries(test_cpp_smoke PRIVATE modena_cpp modena)
target_include_directories(test_cpp_smoke PRIVATE ${Python3_INCLUDE_DIRS})
target_compile_features(test_cpp_smoke PRIVATE cxx_std_17)
add_test(NAME modena_iface_cpp_smoke COMMAND test_cpp_smoke)
set_tests_properties(modena_iface_cpp_smoke PROPERTIES LABELS "cpp;integration")

# -- Fortran (fmodena_oop) ------------------------------------------------
# Only built if the Fortran wrapper is enabled.
if(TARGET fmodena_oop)
    add_executable(test_fortran_smoke
        "${CMAKE_CURRENT_SOURCE_DIR}/test_fortran_smoke.f90"
    )
    target_link_libraries(test_fortran_smoke PRIVATE fmodena_oop fmodena modena)
    add_test(NAME modena_iface_fortran_smoke COMMAND test_fortran_smoke)
    set_tests_properties(modena_iface_fortran_smoke
        PROPERTIES LABELS "fortran;integration"
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
    PROPERTIES LABELS "cpp;integration;thread"
)

# -- MATLAB / Octave (via MEX gateway + Modena.m class) -------------------
# Runs test_matlab_smoke.m through Octave (or MATLAB when available).
# Only wired up when WITH_MATLAB=ON so that the MEX gateway is built
# and installed to MATLAB_PKG_DIR — the test relies on
# ``octave --path <MATLAB_PKG_DIR>`` finding both the .mex and
# Modena.m there.
#
# Prefer Octave when both are available (faster startup, no license).
if(WITH_MATLAB)
    find_program(OCTAVE_EXECUTABLE octave)
    find_program(MATLAB_EXECUTABLE matlab)
    if(OCTAVE_EXECUTABLE)
        add_test(NAME modena_iface_matlab_smoke
            COMMAND "${OCTAVE_EXECUTABLE}" --no-gui --quiet
                --path "${MATLAB_PKG_DIR}"
                "${CMAKE_CURRENT_SOURCE_DIR}/test_matlab_smoke.m"
        )
        set_tests_properties(modena_iface_matlab_smoke PROPERTIES
            LABELS "octave;integration"
        )
    elseif(MATLAB_EXECUTABLE)
        add_test(NAME modena_iface_matlab_smoke
            COMMAND "${MATLAB_EXECUTABLE}" -batch
                "addpath('${MATLAB_PKG_DIR}'); run('${CMAKE_CURRENT_SOURCE_DIR}/test_matlab_smoke.m');"
        )
        set_tests_properties(modena_iface_matlab_smoke PROPERTIES
            LABELS "matlab;integration"
        )
    endif()
endif()
