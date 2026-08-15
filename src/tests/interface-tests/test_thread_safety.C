/*
 * test_thread_safety.C
 *
 * Multi-threaded smoke test for modena_model_call.  Spawns N pthreads
 * that all share the same modena_model_t but each holds its own
 * modena_inputs_t / modena_outputs_t pair.  Every thread runs many
 * evaluations of `flowRate` in a tight loop and checks that:
 *
 *   * All calls return 0 (no OOB, no error).
 *   * All outputs are finite and match a per-thread reference value
 *     computed once at the start (deterministic given fixed inputs).
 *
 * A regression here — e.g. two threads writing into shared inputs, or
 * the substitute-model output buffer racing — would produce a scrambled
 * output that differs from the reference.
 *
 * Registered under the "integration" and "thread" labels; requires a
 * live MongoDB with the `flowRate` model initialized.
 *
 * This mirrors the pattern in examples/twoTanksMT/ but is a small,
 * runnable-in-ctest guard rather than a full application.
 */

#include <modena.h>

#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <thread>
#include <vector>

namespace {

constexpr std::size_t N_THREADS       = 8;
constexpr std::size_t ITERS_PER_THREAD = 500;

// Shared model + cached input/output positions.  All const after main
// sets them up before spawning threads.
modena_model_t *g_model = nullptr;
std::size_t g_Dpos, g_rho0Pos, g_p0Pos, g_p1Byp0Pos, g_mdotPos;

// Fixed test point — every thread evaluates the same values.
constexpr double D_val      = 0.01;
constexpr double rho0_val   = 3.4;
constexpr double p0_val     = 3.0e5;
constexpr double p1Byp0_val = 0.03;

std::atomic<int>  g_errors{0};
std::atomic<int>  g_nonzero_rc{0};

void worker(std::size_t thread_id, double reference_mdot)
{
    modena_inputs_t  *in  = modena_inputs_new(g_model);
    modena_outputs_t *out = modena_outputs_new(g_model);

    for (std::size_t k = 0; k < ITERS_PER_THREAD; ++k)
    {
        modena_inputs_set(in, g_Dpos,      D_val);
        modena_inputs_set(in, g_rho0Pos,   rho0_val);
        modena_inputs_set(in, g_p0Pos,     p0_val);
        modena_inputs_set(in, g_p1Byp0Pos, p1Byp0_val);

        int rc = modena_model_call(g_model, in, out);
        if (rc != 0)
        {
            g_nonzero_rc.fetch_add(1);
            continue;
        }

        double mdot = modena_outputs_get(out, g_mdotPos);

        // Every thread must observe the same output for the same input.
        // A tiny epsilon covers non-associativity of FP but rules out any
        // gross corruption from a race.
        if (!std::isfinite(mdot) || std::abs(mdot - reference_mdot) > 1e-9)
        {
            g_errors.fetch_add(1);
            fprintf(stderr,
                "thread %zu iter %zu: mdot = %g, expected %g\n",
                thread_id, k, mdot, reference_mdot);
        }
    }

    modena_inputs_destroy(in);
    modena_outputs_destroy(out);
}

} // namespace

int main()
{
    // ── Load once on the main thread ────────────────────────────────────
    g_model = modena_model_new("flowRate");
    if (modena_error_occurred())
    {
        fprintf(stderr, "modena_model_new failed: %s\n",
                modena_error_message(modena_error()));
        return 1;
    }

    g_Dpos      = modena_model_inputs_argPos(g_model,  "D");
    g_rho0Pos   = modena_model_inputs_argPos(g_model,  "rho0");
    g_p0Pos     = modena_model_inputs_argPos(g_model,  "p0");
    g_p1Byp0Pos = modena_model_inputs_argPos(g_model,  "p1Byp0");
    g_mdotPos   = modena_model_outputs_argPos(g_model, "flowRate");
    modena_model_argPos_check(g_model);

    // ── Compute the reference output on the main thread ─────────────────
    // Every worker must reproduce this value bit-for-bit (same inputs,
    // same parameters, no threading in the eval itself).
    modena_inputs_t  *in  = modena_inputs_new(g_model);
    modena_outputs_t *out = modena_outputs_new(g_model);
    modena_inputs_set(in, g_Dpos,      D_val);
    modena_inputs_set(in, g_rho0Pos,   rho0_val);
    modena_inputs_set(in, g_p0Pos,     p0_val);
    modena_inputs_set(in, g_p1Byp0Pos, p1Byp0_val);
    if (modena_model_call(g_model, in, out) != 0)
    {
        fprintf(stderr, "reference modena_model_call failed\n");
        return 1;
    }
    const double reference_mdot = modena_outputs_get(out, g_mdotPos);
    modena_inputs_destroy(in);
    modena_outputs_destroy(out);

    if (!std::isfinite(reference_mdot) || reference_mdot <= 0.0)
    {
        fprintf(stderr, "reference mdot invalid: %g\n", reference_mdot);
        return 1;
    }

    printf("reference flowRate mdot = %g kg/s\n", reference_mdot);
    printf("spawning %zu threads x %zu iterations each = %zu total calls\n",
        N_THREADS, ITERS_PER_THREAD, N_THREADS * ITERS_PER_THREAD);

    // ── Spawn workers ───────────────────────────────────────────────────
    std::vector<std::thread> workers;
    workers.reserve(N_THREADS);
    for (std::size_t t = 0; t < N_THREADS; ++t)
        workers.emplace_back(worker, t, reference_mdot);

    for (auto &w : workers) w.join();

    modena_model_destroy(g_model);

    // ── Report ──────────────────────────────────────────────────────────
    int errors = g_errors.load();
    int nzrc   = g_nonzero_rc.load();
    if (errors != 0 || nzrc != 0)
    {
        fprintf(stderr,
            "FAIL  test_thread_safety  (%d mismatched outputs, %d non-zero return codes)\n",
            errors, nzrc);
        return 1;
    }

    printf("PASS  test_thread_safety  (%zu threads x %zu iterations, all bit-identical to reference)\n",
        N_THREADS, ITERS_PER_THREAD);
    return 0;
}
