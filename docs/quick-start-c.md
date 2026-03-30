# Quick-Start — Calling MoDeNa Models from C/C++

This guide covers the raw C API (`modena.h`).  If you are writing C++ and
prefer RAII and exceptions see [quick-start-cpp.md](quick-start-cpp.md).

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| `libmodena` | Installed by MoDeNa's CMake build |
| CMake ≥ 3.0 | For the `find_package(MODENA)` integration |
| MongoDB running | `MODENA_URI` must point to a populated database |

```bash
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:${HOME}/lib"
export PYTHONPATH="${PYTHONPATH}:${HOME}/lib/python3.10/site-packages"
```

---

## CMake integration

```cmake
cmake_minimum_required(VERSION 3.0)
project(myApp C CXX)

find_package(MODENA REQUIRED)

add_executable(myApp main.c)
target_link_libraries(myApp MODENA::modena)
```

`find_package(MODENA)` reads `MODENAConfig.cmake` installed alongside the
library.  If MoDeNa is not in a standard prefix, pass
`-DCMAKE_PREFIX_PATH=/path/to/modena/install` to cmake.

---

## The pattern

Every call site follows the same four-phase structure:

```
1. Load once     modena_model_new  + inputs_new + outputs_new
2. Cache once    modena_model_inputs_argPos  (before the loop)
3. Per step      inputs_set → model_call → outputs_get
4. Clean up      inputs_destroy + outputs_destroy + model_destroy
```

---

## Example — twoTanks

Adapted from `examples/MoDeNaModels/twoTank/src/twoTanksMacroscopicProblem.C`.

```c
#include "modena.h"
#include <stdio.h>
#include <stdlib.h>

int main(void)
{
    /* Physical constants */
    const double D      = 0.01;
    const double R      = 287.1;
    const double T      = 300.0;
    const double V0     = 0.1,   V1     = 1.0;
    const double deltat = 1e-3,  tend   = 5.5;

    double p0 = 3e5, p1 = 1e4;
    double m0 = p0*V0/R/T, m1 = p1*V1/R/T;
    double rho0 = m0/V0,   rho1 = m1/V1;
    double t = 0.0;

    /* ── 1. Load model ──────────────────────────────────────────────────── */
    modena_model_t   *model   = modena_model_new("flowRate");
    modena_inputs_t  *inputs  = modena_inputs_new(model);
    modena_outputs_t *outputs = modena_outputs_new(model);

    /* ── 2. Cache input/output positions (do this ONCE before the loop) ── */
    size_t pos_D      = modena_model_inputs_argPos(model, "D");
    size_t pos_rho0   = modena_model_inputs_argPos(model, "rho0");
    size_t pos_p0     = modena_model_inputs_argPos(model, "p0");
    size_t pos_p1p0   = modena_model_inputs_argPos(model, "p1Byp0");
    size_t pos_mdot   = modena_model_outputs_argPos(model, "flowRate");

    /* Verify every declared input/output was queried — catches typos */
    modena_model_argPos_check(model);

    /* ── 3. Time-step loop ──────────────────────────────────────────────── */
    while (t + deltat < tend + 1e-10)
    {
        t += deltat;

        /* Set inputs depending on flow direction */
        if (p0 > p1) {
            modena_inputs_set(inputs, pos_D,    D);
            modena_inputs_set(inputs, pos_rho0, rho0);
            modena_inputs_set(inputs, pos_p0,   p0);
            modena_inputs_set(inputs, pos_p1p0, p1/p0);
        } else {
            modena_inputs_set(inputs, pos_D,    D);
            modena_inputs_set(inputs, pos_rho0, rho1);
            modena_inputs_set(inputs, pos_p0,   p1);
            modena_inputs_set(inputs, pos_p1p0, p0/p1);
        }

        int ret = modena_model_call(model, inputs, outputs);

        /* Handle return codes */
        if (ret == 100) { t -= deltat; continue; } /* retrained — retry step */
        if (ret != 0)   { exit(ret); }              /* 200/201 — FireWorks handles */

        double mdot = modena_outputs_get(outputs, pos_mdot);

        /* Update state */
        if (p0 > p1) { m0 -= mdot*deltat; m1 += mdot*deltat; }
        else         { m0 += mdot*deltat; m1 -= mdot*deltat; }

        rho0 = m0/V0;   p0 = rho0*R*T;
        rho1 = m1/V1;   p1 = rho1*R*T;

        printf("t=%.3f  p0=%.1f  p1=%.1f\n", t, p0, p1);
    }

    /* ── 4. Clean up ────────────────────────────────────────────────────── */
    modena_inputs_destroy(inputs);
    modena_outputs_destroy(outputs);
    modena_model_destroy(model);
    return 0;
}
```

---

## Return codes

| Code | Meaning | Required action |
|------|---------|----------------|
| `0` | Success | Continue normally |
| `100` | Surrogate retrained (out of bounds) | Decrement time, retry step |
| `200` | Exit and restart | `exit(200)` — FireWorks relaunches |
| `201` | Clean exit | `exit(201)` — workflow complete |

---

## Inspecting model metadata

Before caching positions you can print the names MoDeNa knows:

```c
size_t n;
const char **names;

names = modena_model_inputs_names(model);
n     = modena_model_inputs_size(model);
for (size_t i = 0; i < n; i++) printf("input[%zu] = %s\n", i, names[i]);

names = modena_model_outputs_names(model);
n     = modena_model_outputs_size(model);
for (size_t i = 0; i < n; i++) printf("output[%zu] = %s\n", i, names[i]);

names = modena_model_parameters_names(model);
n     = modena_model_parameters_size(model);
for (size_t i = 0; i < n; i++) printf("param[%zu] = %s\n", i, names[i]);
```

---

## Thread-safe evaluation

`modena_model_t` is **read-only after `modena_model_new()` returns** and can
be shared across any number of threads simultaneously.  The only per-thread
requirement is a private pair of I/O vectors.

### What the library handles for you

`modena_model_call()` manages the CPython GIL internally:

- If the calling thread holds the GIL (typical single-threaded main), it
  releases it before the pure-C evaluation and re-acquires it on return.
- Worker threads in a pthread/OpenMP pool do not hold the GIL; the
  release/restore is skipped — zero overhead on the fast path.
- When an out-of-bounds event fires, the library re-acquires the GIL only
  for the Python callback, then releases it again before returning.

You do not need `Py_BEGIN_ALLOW_THREADS` or any other GIL bookkeeping in
your application.

### Pattern — pthreads parametric sweep

```c
#include "modena.h"
#include <pthread.h>
#include <stdlib.h>

#define N 4

static modena_model_t *g_model;
static size_t g_pos_D, g_pos_rho0, g_pos_p0, g_pos_p1p0;

static void *worker(void *varg)
{
    /* Each thread allocates its own I/O vectors */
    modena_inputs_t  *in  = modena_inputs_new(g_model);
    modena_outputs_t *out = modena_outputs_new(g_model);

    /* … ODE loop … */
    modena_inputs_set(in, g_pos_D,    0.01);
    modena_inputs_set(in, g_pos_rho0, rho0);
    modena_inputs_set(in, g_pos_p0,   p0);
    modena_inputs_set(in, g_pos_p1p0, p1/p0);

    int ret = modena_model_call(g_model, in, out);  /* GIL-safe, concurrent */
    /* handle ret … */

    modena_inputs_destroy(in);
    modena_outputs_destroy(out);
    return NULL;
}

int main(void)
{
    /* Load model once — shared across all threads */
    g_model = modena_model_new("flowRate");
    if (modena_error_occurred()) return modena_error();

    g_pos_D    = modena_model_inputs_argPos(g_model, "D");
    g_pos_rho0 = modena_model_inputs_argPos(g_model, "rho0");
    g_pos_p0   = modena_model_inputs_argPos(g_model, "p0");
    g_pos_p1p0 = modena_model_inputs_argPos(g_model, "p1Byp0");
    modena_model_argPos_check(g_model);

    pthread_t threads[N];
    for (int i = 0; i < N; i++)
        pthread_create(&threads[i], NULL, worker, NULL);
    for (int i = 0; i < N; i++)
        pthread_join(threads[i], NULL);

    modena_model_destroy(g_model);
    return 0;
}
```

**CMakeLists.txt** — add `Threads::Threads`:

```cmake
find_package(MODENA   REQUIRED)
find_package(Threads  REQUIRED)
target_link_libraries(myApp MODENA::modena Threads::Threads)
```

### OpenMP

OpenMP threads are pthreads.  The same pattern applies inside a parallel
region — each thread allocates its own I/O vectors and calls
`modena_model_call()` independently.  No `omp critical` section or
`Py_BEGIN_ALLOW_THREADS` is needed.

```c
/* Shared: model loaded before parallel region */
modena_model_t *model = modena_model_new("flowRate");
/* … argPos setup … */

#pragma omp parallel
{
    modena_inputs_t  *in  = modena_inputs_new(model);
    modena_outputs_t *out = modena_outputs_new(model);

    #pragma omp for schedule(dynamic)
    for (int i = 0; i < N; i++)
    {
        /* … set inputs … */
        int ret = modena_model_call(model, in, out);
        /* … handle ret … */
    }

    modena_inputs_destroy(in);
    modena_outputs_destroy(out);
}

modena_model_destroy(model);
```

### MPI

MPI ranks are separate OS processes, each with their own Python interpreter.
Thread safety is irrelevant between ranks — treat each rank as an independent
single-process application.  For hybrid MPI+OpenMP, the OpenMP pattern above
applies within each rank.

### Working example

`examples/MoDeNaModels/twoTankMT/` is a complete multi-threaded example that
runs four simultaneous two-tank discharge simulations in parallel, all sharing
one `modena_model_t`.

---

## Working with IndexSets

Some models are parameterised by a named set of species or components
(e.g. `fullerEtAlDiffusion[A=H2O,B=N2]`).  The `modena_index_set_t` API
lets you iterate over members and convert between names and positions.

```c
/* Load an index set by its registered name */
modena_index_set_t *species = modena_index_set_new("species");

/* Name → position */
size_t idx_N2 = modena_index_set_get_index(species, "N2");

/* Iterate over all members */
size_t start = modena_index_set_iterator_start(species);
size_t end   = modena_index_set_iterator_end(species);
for (size_t i = start; i < end; i++)
    printf("%s\n", modena_index_set_get_name(species, i));

modena_index_set_destroy(species);

/* Load the parameterised model */
modena_model_t *model = modena_model_new("fullerEtAlDiffusion[A=H2O,B=N2]");
```

See `examples/MoDeNaModels/fullerEtAlDiffusion/` for the full example.
