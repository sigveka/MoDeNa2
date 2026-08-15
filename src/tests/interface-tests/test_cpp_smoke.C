/*
 * test_cpp_smoke.C
 *
 * Smoke test for the C++ RAII wrapper (modena::Model).
 *
 * Loads the `flowRate` surrogate model, evaluates it at one known-good
 * point, and asserts that the resulting mass flow rate is finite and
 * positive.  This exercises the full round-trip:
 *
 *     C++ ctor -> modena_model_new -> Python -> MongoDB
 *     C++ setters -> modena_inputs_set
 *     C++ call() -> modena_model_call -> compiled surrogate .so -> outputs
 *     C++ output() -> modena_outputs_get
 *     C++ dtor -> modena_model_destroy + friends
 *
 * Requires the `flowRate` model to be initialized in the MongoDB pointed
 * to by MODENA_URI (default mongodb://localhost:27017/test).  If the
 * model is missing the ctor throws modena::ModelNotFound and the process
 * exits with a non-zero status — the CTest harness catches that.
 *
 * The test is registered under the "integration" label because it needs
 * a live MongoDB with the model pre-initialized.
 */

#include <modena/modena.hpp>

#include <cassert>
#include <cmath>
#include <iostream>

int main()
{
    // ── Load ────────────────────────────────────────────────────────────
    modena::Model m("flowRate");

    // ── Metadata sanity ─────────────────────────────────────────────────
    assert(m.inputs_size()  == 4);   // D, rho0, p0, p1Byp0
    assert(m.outputs_size() == 1);   // flowRate

    // ── Cache positions (per developer guide) ───────────────────────────
    const std::size_t Dpos      = m.input_pos("D");
    const std::size_t rho0Pos   = m.input_pos("rho0");
    const std::size_t p0Pos     = m.input_pos("p0");
    const std::size_t p1Byp0Pos = m.input_pos("p1Byp0");
    const std::size_t mdotPos   = m.output_pos("flowRate");
    m.check();

    // ── Evaluate at a known-good point (matches the twoTanks initial set) ─
    m.set(Dpos,      0.01);
    m.set(rho0Pos,   3.4);
    m.set(p0Pos,     3.0e5);
    m.set(p1Byp0Pos, 0.03);

    m.call();

    const double mdot = m.output(mdotPos);

    // ── Assertions ──────────────────────────────────────────────────────
    assert(std::isfinite(mdot));
    assert(mdot > 0.0);
    // The trained flowRate model at this point is ~0.024 kg/s — a loose
    // range check catches gross regressions without pinning to an exact
    // value that would break on refit.
    assert(mdot > 1e-4 && mdot < 1.0);

    // Note: the named-access proxy (m["D"] = 0.01) is deliberately NOT
    // exercised here.  It calls modena_model_inputs_argPos on every
    // access, which is a Python call — after m.check() has released the
    // GIL for the "time-step loop", such calls segfault deep inside
    // libpython.  The positional API is the intended fast path (per the
    // wrapper's own docstring) and what production code uses.

    std::cout << "PASS  test_cpp_smoke  (flowRate mdot = " << mdot
              << " kg/s at D=0.01, rho0=3.4, p0=3e5, p1/p0=0.03)"
              << std::endl;
    return 0;
}
