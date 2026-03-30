/**
@file
Multi-threaded two-tank parametric sweep using MoDeNa.

Runs N_THREADS simultaneous two-tank discharge simulations in parallel,
each with different initial pressures, sharing one modena_model_t.

Thread safety is guaranteed because:
  - modena_model_t is read-only after modena_model_new() returns.
  - Each thread allocates its own modena_inputs_t and modena_outputs_t.
  - modena_error_code is thread_local — each thread reads its own error state.
  - write_outside_point() acquires the GIL before calling into CPython,
    so it is safe to trigger from any thread.

Build requirements: POSIX threads (pthreads).

@author    MoDeNa Project
@copyright 2014-2026, MoDeNa Project. GNU Public License.
*/

#include "modena.h"

#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>

#define N_THREADS 4

/* Shared, read-only after init */
static modena_model_t *g_model;
static size_t g_D_pos;
static size_t g_rho0_pos;
static size_t g_p0_pos;
static size_t g_p1Byp0_pos;

typedef struct
{
    double p0_init;  /* initial pressure in tank 0 [Pa] */
    int    retcode;  /* model call return code (0 = success) */
} ThreadArg;


static void *run_simulation(void *varg)
{
    ThreadArg *a = (ThreadArg *)varg;

    /* Per-thread I/O vectors — the only thread-local state required */
    modena_inputs_t  *inputs  = modena_inputs_new(g_model);
    modena_outputs_t *outputs = modena_outputs_new(g_model);

    /* Two-tank constants */
    const double D  = 0.01;    /* nozzle diameter [m] */
    const double R  = 287.1;   /* specific gas constant [J/(kg K)] */
    const double T  = 300.0;   /* temperature [K] */
    const double V0 = 0.1;     /* volume of tank 0 [m^3] */
    const double V1 = 1.0;     /* volume of tank 1 [m^3] */

    double p0 = a->p0_init;
    double p1 = 1e4;
    double m0 = p0 * V0 / R / T;
    double m1 = p1 * V1 / R / T;
    double rho0 = m0 / V0;
    double rho1 = m1 / V1;

    const double dt   = 1e-3;
    const double tend = 5.5;

    for (double t = 0.0; t + dt < tend + 1e-10; t += dt)
    {
        if (p0 > p1)
        {
            modena_inputs_set(inputs, g_D_pos,      D);
            modena_inputs_set(inputs, g_rho0_pos,   rho0);
            modena_inputs_set(inputs, g_p0_pos,     p0);
            modena_inputs_set(inputs, g_p1Byp0_pos, p1 / p0);
        }
        else
        {
            modena_inputs_set(inputs, g_D_pos,      D);
            modena_inputs_set(inputs, g_rho0_pos,   rho1);
            modena_inputs_set(inputs, g_p0_pos,     p1);
            modena_inputs_set(inputs, g_p1Byp0_pos, p0 / p1);
        }

        int ret = modena_model_call(g_model, inputs, outputs);
        if (ret)
        {
            a->retcode = ret;
            goto cleanup;
        }

        const double mdot = modena_outputs_get(outputs, 0);

        if (p0 > p1)
        {
            m0 -= mdot * dt;
            m1 += mdot * dt;
        }
        else
        {
            m0 += mdot * dt;
            m1 -= mdot * dt;
        }

        rho0 = m0 / V0;
        rho1 = m1 / V1;
        p0   = rho0 * R * T;
        p1   = rho1 * R * T;
    }

    printf("p0_init=%.0f Pa  final p0=%.1f Pa  p1=%.1f Pa\n",
           a->p0_init, p0, p1);

cleanup:
    modena_inputs_destroy(inputs);
    modena_outputs_destroy(outputs);
    return NULL;
}


int main(void)
{
    /* Load the surrogate model once — shared across all threads */
    g_model = modena_model_new("flowRate");
    if (modena_error_occurred())
        return modena_error();

    /* Cache argument positions once before spawning threads */
    g_D_pos      = modena_model_inputs_argPos(g_model, "D");
    g_rho0_pos   = modena_model_inputs_argPos(g_model, "rho0");
    g_p0_pos     = modena_model_inputs_argPos(g_model, "p0");
    g_p1Byp0_pos = modena_model_inputs_argPos(g_model, "p1Byp0");
    modena_model_argPos_check(g_model);

    /* Parametric sweep: four initial pressures evaluated in parallel */
    static const double pressures[N_THREADS] =
        { 2.8e5, 3.0e5, 3.2e5, 3.4e5 };

    ThreadArg  args[N_THREADS];
    pthread_t  threads[N_THREADS];
    int worst = 0;

    /* modena_model_call() releases the GIL internally before the pure-C
     * evaluation and re-acquires it only when an OOB event needs Python.
     * No Py_BEGIN_ALLOW_THREADS wrapper is required here. */
    for (int i = 0; i < N_THREADS; i++)
    {

        printf("Starting sim %d out of %d\n", i + 1, N_THREADS);
        args[i].p0_init = pressures[i];
        args[i].retcode = 0;
        pthread_create(&threads[i], NULL, run_simulation, &args[i]);
    }

    for (int i = 0; i < N_THREADS; i++)
    {
        pthread_join(threads[i], NULL);
        if (args[i].retcode > worst)
            worst = args[i].retcode;
    }

    modena_model_destroy(g_model);
    return worst;
}
