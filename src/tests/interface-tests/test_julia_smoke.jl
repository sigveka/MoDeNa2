# test_julia_smoke.jl
#
# Julia smoke test for the Modena wrapper (src/wrappers/julia/src/Modena.jl).
#
# Loads the `flowRate` surrogate through the Julia ccall bindings, evaluates
# it at the same known-good point as test_cpp_smoke.C / test_fortran_smoke.f90
# / test_matlab_smoke.m, and asserts the resulting mass flow rate is finite
# and positive.  Also exercises the named-parameter accessors
# (`parameters(m)`, `parameter(m, "P0")`) that layer on top of
# `modena_model_parameters_get`.
#
# Coverage unique to this file — a regression that only surfaces on the Julia
# side gets caught here:
#   * Libdl discovery of libmodena.so (MODENA_LIB_DIR / python3 / find_library)
#   * the RTLD_GLOBAL libpython priming in _prime_python_env()
#   * the Py_DecRef-based finalizer in _destroy!
#   * 1-based Julia index <-> 0-based C argPos conversion in parameter(m, name)
#
# Requires `flowRate` to be initialized in the MongoDB pointed to by
# MODENA_URI (run examples/twoTanks/initModels), hence the "integration"
# CTest label.
#
# Exit code: 0 on success, non-zero on any assertion failure or ccall error.

using Modena
using Test

println("-- test_julia_smoke --")

# ── Load ─────────────────────────────────────────────────────────────────────
m = Model("flowRate")
println("loaded flowRate")

# ── Metadata sanity ──────────────────────────────────────────────────────────
@test inputs_size(m)     == 4      # D, rho0, p0, p1Byp0
@test outputs_size(m)    == 1      # flowRate
@test parameters_size(m) == 2      # P0, P1

@test inputs_names(m)     == ["D", "rho0", "p0", "p1Byp0"]
@test outputs_names(m)    == ["flowRate"]
@test parameters_names(m) == ["P0", "P1"]

# ── Cache positions (per developer guide) ────────────────────────────────────
# Every input must be queried before check(), which asserts none was missed.
posD      = input_pos(m, "D")
posRho0   = input_pos(m, "rho0")
posP0     = input_pos(m, "p0")
posP1Byp0 = input_pos(m, "p1Byp0")
posMdot   = output_pos(m, "flowRate")
check(m)

# Positions must be a permutation of 0:3 — catches argPos drift.
@test sort([posD, posRho0, posP0, posP1Byp0]) == collect(0:3)
@test posMdot == 0

# ── Evaluate at a known-good point ───────────────────────────────────────────
set!(m, posD,      0.01)
set!(m, posRho0,   3.4)
set!(m, posP0,     3.0e5)
set!(m, posP1Byp0, 0.03)

call!(m)                            # throws on any non-zero return code

mdot = output(m, posMdot)

@test isfinite(mdot)
@test mdot > 0.0
# A loose range check catches gross regressions without pinning an exact
# value that would break on refit (the C++ smoke uses the same bounds).
@test 1e-4 < mdot < 1.0

# ── Named access — same computation, different path ──────────────────────────
# set!(m, name, v) and output(m, name) resolve the position on every call;
# they must agree with the cached-position path bit for bit.
set!(m, "D",      0.01)
set!(m, "rho0",   3.4)
set!(m, "p0",     3.0e5)
set!(m, "p1Byp0", 0.03)
call!(m)
@test output(m, "flowRate") == mdot

# ── Named-parameter accessors ────────────────────────────────────────────────
# parameters() returns the full {name => value} map, the Julia equivalent of
# Python's model.named_parameters().
p = parameters(m)
@test p isa Dict{String, Float64}
@test length(p) == 2
@test haskey(p, "P0")
@test haskey(p, "P1")
@test isfinite(p["P0"])
@test isfinite(p["P1"])

# Named and positional access must agree — guards the 1-based/0-based
# conversion in parameter(m, ::AbstractString).
@test parameter(m, "P0") == parameter(m, 0)
@test parameter(m, "P1") == parameter(m, 1)
@test parameter(m, "P0") == p["P0"]
@test parameter(m, "P1") == p["P1"]

# Unknown parameter name must raise rather than silently return garbage.
@test_throws KeyError parameter(m, "does_not_exist")

# ── Regression guard: unknown input/output names ─────────────────────────────
# These resolve from the ctor-time cache, so they raise KeyError instead of
# calling modena_model_inputs_argPos without the GIL (which segfaults — the
# same bug that was fixed in the C++ wrapper).  Reaching this line at all
# means the earlier post-check() named access did not crash the process.
@test_throws KeyError input_pos(m, "does_not_exist")
@test_throws KeyError output_pos(m, "does_not_exist")

println("PASS  test_julia_smoke  (flowRate mdot = ", round(mdot, digits = 6), " kg/s)")
